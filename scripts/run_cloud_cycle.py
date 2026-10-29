"""
Stateful Cloud Execution & Auto-Calibration Script (`scripts/run_cloud_cycle.py`):
Designed to run unattended in the cloud (e.g., GitHub Actions cron 2x/day) without a local PC turned on.
- Preserves `data/nba_intelligence.sqlite3` across runs (initializes baseline history only on first run)
- Fetches yesterday's and today's official NBA results from ESPN (`ESPNPublicAdapter`)
- Settles any PENDING simulated bets whose games are now FINAL
- Automatically recalibrates (`ProbabilityCalibrator`) and evaluates walk-forward model promotion
  when new settled outcomes accumulate, strictly without temporal lookahead
- Generates new pre-game predictions and virtual S/1.00 PEN selections (max 3/day, EV > 5%)
- Updates `reports/*.md` and the `NBA/` Obsidian Vault
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any
import uuid

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.specialized_agents import (
    ModelCalibratorAgent,
    NBAAuditorAgent,
    NBADataScoutAgent,
    VisualResearcherAgent,
)
from src.backtesting.backtester import WalkForwardBacktester
from src.calibration.calibrator import ProbabilityCalibrator, compute_reliability_curve
from src.features.builder import build_pregame_features
from src.ingestion.adapters import DataSourceRouter, ESPNPublicAdapter
from src.models.statistical_models import (
    BaselineModel,
    EnsembleStackingModel,
    PointMarginModel,
    TotalPointsModel,
)
from src.orchestrator import Orchestrator
from src.paper_trading.engine import PaperTradingEngine
from src.prediction.ev_calculator import evaluate_market_opportunity
from src.reporting.reporter import (
    export_bets_and_tracking_dashboard,
    generate_audit_report,
    generate_daily_report,
    generate_weekly_report,
    sync_obsidian_vault,
)
from src.storage.db import DatabaseManager
from src.validation.validator import parse_iso_utc, validate_game_record, validate_odds_record


def run_incremental_cloud_cycle(mode: str = "auto") -> dict[str, Any]:
    db_path = PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"

    # Bootstrap database on very first run if it does not exist yet
    if not db_path.exists():
        orch = Orchestrator(
            db_path=db_path,
            reports_dir=PROJECT_ROOT / "reports",
            obsidian_vault_dir=PROJECT_ROOT / "NBA",
            max_retries=2,
        )
        init_res = orch.run_full_pipeline(include_live_espn=True)
        return {"cycle_type": "INITIAL_BOOTSTRAP_AND_LIVE_SYNC", "run_id": init_res["run_id"]}

    db = DatabaseManager(db_path)
    paper_engine = PaperTradingEngine(db=db, initial_bankroll_pen=100.00)
    scout = NBADataScoutAgent(db)
    visual = VisualResearcherAgent()
    calibrator_agent = ModelCalibratorAgent()
    auditor = NBAAuditorAgent(db, paper_engine)

    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    yesterday_str = (now_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    today_str = now_dt.strftime("%Y-%m-%d")

    # 1. Fetch yesterday and today from ESPN Public API to get final scores + new scheduled games/odds
    router = DataSourceRouter([ESPNPublicAdapter(timeout_seconds=10)])
    ingested_dates: list[str] = []
    for dt_str in (yesterday_str, today_str):
        try:
            scout.ingest_and_validate_dataset(router, date_str=dt_str)
            ingested_dates.append(dt_str)
        except Exception:
            pass

    # 2. Settle any PENDING simulated bets whose games are now FINAL, POSTPONED, or CANCELLED
    pending_bets = db.fetch_all(
        """
        SELECT b.bet_id, b.game_id, g.status, g.home_score, g.away_score, g.result_recorded_at
        FROM simulated_bets b
        JOIN games g ON b.game_id = g.game_id
        WHERE b.status = 'PENDING'
          AND g.status IN ('FINAL', 'POSTPONED', 'CANCELLED')
        """
    )
    settled_now: list[dict[str, Any]] = []
    for pb in pending_bets:
        try:
            s_res = paper_engine.settle_bet(
                bet_id=pb["bet_id"],
                game_status=pb["status"],
                home_score=pb["home_score"],
                away_score=pb["away_score"],
                settled_at=pb["result_recorded_at"] or now_str,
            )
            settled_now.append(s_res)
        except Exception:
            pass

    # 3. Auto-Calibration Step: Fit calibrators & models on all strictly prior FINAL games
    all_final_games = db.fetch_all(
        "SELECT * FROM games WHERE status = 'FINAL' AND home_score IS NOT NULL ORDER BY game_start_time ASC"
    )
    model_a = BaselineModel("model_a_baseline_v1")
    model_c = PointMarginModel("model_c_point_margin_v1")
    model_d = TotalPointsModel("model_d_total_points_v1")
    model_f = EnsembleStackingModel("model_f_ensemble_v2")
    db.execute_insert(
        """
        INSERT OR IGNORE INTO model_versions (
            model_version_id, model_family, market, train_start_date, train_end_date,
            trained_at, hyperparameters_json, is_active, approved_by
        ) VALUES ('model_f_ensemble_v2', 'model_f_meta_ensemble', 'moneyline', '2026-01-01', ?, ?, '{}', 1, 'orchestrator_v2')
        """,
        (today_str, now_str),
    )
    model_a.fit(all_final_games, now_str)
    model_c.fit(all_final_games, now_str)
    model_d.fit(all_final_games, now_str)
    model_f.fit(all_final_games, now_str)

    # Fit probability calibrators on historical predictions of resolved games
    resolved_ml_preds = db.fetch_all(
        """
        SELECT p.raw_probability, g.game_start_time, g.result_recorded_at,
               CASE WHEN g.home_score > g.away_score THEN 1 ELSE 0 END AS outcome
        FROM predictions p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.market = 'moneyline' AND p.selection = 'HOME'
          AND g.status = 'FINAL' AND g.game_start_time < ?
        """,
        (now_str,),
    )
    resolved_tot_preds = db.fetch_all(
        """
        SELECT p.raw_probability, g.game_start_time, g.result_recorded_at,
               CASE WHEN (g.home_score + g.away_score) > p.line_value THEN 1 ELSE 0 END AS outcome
        FROM predictions p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.market = 'total_points' AND p.selection = 'OVER'
          AND g.status = 'FINAL' AND g.game_start_time < ?
        """,
        (now_str,),
    )

    ml_cal = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    tot_cal = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    ml_method = ml_cal.fit(resolved_ml_preds, now_str) if resolved_ml_preds else "identity"
    tot_method = tot_cal.fit(resolved_tot_preds, now_str) if resolved_tot_preds else "identity"

    if resolved_ml_preds:
        curve_ml = compute_reliability_curve(
            [float(r["raw_probability"]) for r in resolved_ml_preds],
            [int(r["outcome"]) for r in resolved_ml_preds],
        )
        db.execute_insert(
            """
            INSERT INTO calibration_logs (
                eval_id, evaluated_at, model_version_id, market, sample_size,
                brier_score, log_loss, ece, calibration_method, bins_json, promoted
            ) VALUES (?, ?, ?, 'moneyline', ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                f"CAL_ML_{uuid.uuid4().hex[:8].upper()}",
                now_str,
                model_c.version_id,
                curve_ml["sample_size"],
                curve_ml["brier_score"],
                curve_ml["log_loss"],
                curve_ml["ece"],
                ml_method,
                json.dumps(curve_ml["bins"]),
            ),
        )

    # 4. Evaluate upcoming SCHEDULED games that do not yet have predictions
    scheduled_games = db.fetch_all(
        "SELECT * FROM games WHERE status = 'SCHEDULED' AND game_start_time > ? ORDER BY game_start_time ASC",
        (now_str,),
    )
    new_bets_placed = 0
    for g in scheduled_games:
        existing_pred = db.fetch_one("SELECT prediction_id FROM predictions WHERE game_id = ?", (g["game_id"],))
        if existing_pred:
            continue
        game_odds = db.fetch_all(
            "SELECT * FROM odds_snapshots WHERE game_id = ? AND is_closing_line = 0",
            (g["game_id"],),
        )
        if not game_odds:
            continue

        start_dt = parse_iso_utc(g["game_start_time"])
        avail_dt = parse_iso_utc(g["features_available_at"])
        latest_odds_dt = max(parse_iso_utc(o["captured_at"]) for o in game_odds)
        pred_dt = max(avail_dt, latest_odds_dt)
        if pred_dt >= start_dt:
            continue
        pred_ts = pred_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        validate_game_record(g, simulated_prediction_time=pred_ts)

        feats = build_pregame_features(g, all_final_games, market="total_points")
        pred_f_ml = model_f.predict_moneyline(g, all_final_games)
        raw_p_home = pred_f_ml["p_home"]
        cal_p_home = ml_cal.transform_single(raw_p_home)

        tot_odds = [o for o in game_odds if o["market"] == "total_points"]
        line_val = float(tot_odds[0]["line_value"]) if tot_odds else 228.5
        pred_f_tot = model_f.predict_total_points(g, all_final_games, line_val)
        raw_p_over = pred_f_tot["p_over"]
        cal_p_over = tot_cal.transform_single(raw_p_over)

        candidates: list[dict[str, Any]] = []
        for o in game_odds:
            validate_odds_record(o, g["game_start_time"], simulated_prediction_time=pred_ts)
            mkt = o["market"]
            sel = o["selection"]
            if mkt == "moneyline":
                raw_p = raw_p_home if sel == "HOME" else round(1.0 - raw_p_home, 6)
                cal_p = cal_p_home if sel == "HOME" else round(1.0 - cal_p_home, 6)
                unc = pred_f_ml["uncertainty_std"]
                m_ver = model_f.version_id
            else:
                raw_p = raw_p_over if sel == "OVER" else round(1.0 - raw_p_over, 6)
                cal_p = cal_p_over if sel == "OVER" else round(1.0 - cal_p_over, 6)
                unc = pred_f_tot["uncertainty_std"]
                m_ver = model_f.version_id

            opp = evaluate_market_opportunity(
                estimated_prob=cal_p,
                uncertainty_std=unc,
                odds_record=o,
                game_start_time=g["game_start_time"],
                model_version_id=m_ver,
                simulated_prediction_time=pred_ts,
            )
            pred_id = f"PRED_{g['game_id']}_{mkt}_{sel}_{uuid.uuid4().hex[:6].upper()}"
            db.execute_insert(
                """
                INSERT INTO predictions (
                    prediction_id, game_id, market, selection, line_value,
                    model_version_id, raw_probability, calibrated_probability,
                    uncertainty_std, implied_prob_gross, implied_prob_fair,
                    bookmaker_overround, decimal_odds_used, odds_provider,
                    odds_captured_at, ev_unit, ev_pct, emitted_at, features_snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pred_id, g["game_id"], mkt, sel, o.get("line_value"),
                    m_ver, raw_p, cal_p, unc, opp["implied_prob_gross"],
                    opp["implied_prob_fair"], opp["bookmaker_overround"],
                    opp["decimal_odds_used"], opp["odds_provider"], opp["odds_captured_at"],
                    opp["ev_unit"], opp["ev_pct"], pred_ts, json.dumps(feats),
                ),
            )
            opp["prediction_id"] = pred_id
            opp["raw_probability"] = raw_p
            opp["calibrated_probability"] = cal_p
            opp["emitted_at"] = pred_ts
            candidates.append(opp)

        day_res = paper_engine.evaluate_and_record_matchday_selections(g["matchday_date"], candidates)
        new_bets_placed += len(day_res["placed_bets"])

    # 5. Recompute metrics, audit, and refresh reports + Obsidian
    bt = WalkForwardBacktester(db, paper_engine)
    metrics = bt.compute_comprehensive_metrics(model_comparison_records=[])
    audit_res = auditor.run_independent_audit(metrics)
    promo_eval = calibrator_agent.evaluate_calibration_and_promotion(metrics)
    sources_info = scout.investigate_sources()
    vis_info = visual.inspect_and_extract_context()

    env_status = {
        "python_version": "CPython 3.12 (uv cloud/local runner)",
        "sportradar_status": sources_info["sportradar_api"]["status"],
        "nba_stats_status": sources_info["nba_com_stats"]["direct_http_status"],
        "playwright_status": sources_info["playwright"]["status"],
        "pixelrag_status": vis_info["pixelrag_status"],
        "obsidian_vault_path": str(PROJECT_ROOT / "NBA"),
    }

    daily_md = generate_daily_report(db, target_date=today_str)
    weekly_md = generate_weekly_report(metrics, promo_eval)
    audit_md = generate_audit_report(audit_res, env_status)

    (PROJECT_ROOT / "reports" / "daily_report.md").write_text(daily_md, encoding="utf-8")
    (PROJECT_ROOT / "reports" / "weekly_report.md").write_text(weekly_md, encoding="utf-8")
    (PROJECT_ROOT / "reports" / "audit_report.md").write_text(audit_md, encoding="utf-8")
    export_bets_and_tracking_dashboard(
        db=db,
        metrics=metrics,
        csv_output_path=PROJECT_ROOT / "data" / "apuestas_historial.csv",
        md_output_path=PROJECT_ROOT / "SEGUIMIENTO_APUESTAS.md",
    )
    sync_obsidian_vault(PROJECT_ROOT / "NBA", daily_md, weekly_md, audit_md, metrics, env_status, today_str)

    return {
        "cycle_type": "INCREMENTAL_CLOUD_AUTO_CYCLE",
        "mode": mode,
        "timestamp_utc": now_str,
        "ingested_dates": ingested_dates,
        "bets_settled_in_cycle": len(settled_now),
        "new_bets_placed_in_cycle": new_bets_placed,
        "active_calibration_methods": {"moneyline": ml_method, "total_points": tot_method},
        "bankroll_state": paper_engine.get_bankroll_state(),
        "audit_verdict": audit_res["exit_gates_evaluation"]["recommendation"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run stateful NBA cloud trading & auto-calibration cycle.")
    parser.add_argument("--mode", default="auto", choices=["auto", "pregame", "settle_and_calibrate"])
    args = parser.parse_args()
    out = run_incremental_cloud_cycle(mode=args.mode)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
