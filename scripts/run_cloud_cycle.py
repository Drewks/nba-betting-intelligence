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
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any
import uuid

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backfill_espn_history import backfill as backfill_espn_history
from src.agents.specialized_agents import (
    ModelCalibratorAgent,
    NBAAuditorAgent,
    NBADataScoutAgent,
    VisualResearcherAgent,
)
from src.backtesting.backtester import WalkForwardBacktester
from src.calibration.calibrator import (
    ProbabilityCalibrator,
    VennAbersConformalInterval,
    compute_reliability_curve,
)
from src.features.builder import build_pregame_features
from src.features.team_ratings import apply_pregame_team_ratings, is_synthetic_game_id
from src.ingestion.adapters import DataSourceRouter, ESPNPublicAdapter
from src.models.statistical_models import (
    BaselineModel,
    EnsembleStackingModel,
)
from src.orchestrator import Orchestrator
from src.paper_trading.engine import PaperTradingEngine
from src.prediction.ev_calculator import (
    DEFAULT_MODEL_WEIGHT,
    MAX_MODEL_MARKET_DISAGREEMENT,
    compute_line_steam,
    compute_market_consensus,
    evaluate_market_opportunity,
)
from src.reporting.reporter import (
    export_bets_and_tracking_dashboard,
    generate_audit_report,
    generate_daily_report,
    generate_weekly_report,
    sync_obsidian_vault,
)
from src.storage.db import DatabaseManager
from src.validation.validator import parse_iso_utc, validate_game_record, validate_odds_record

MODEL_VERSION_ID = "model_f_ensemble_v8"
MIN_REAL_GAMES_FOR_TRAINING = 120


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
    paper_engine = PaperTradingEngine(
        db=db,
        initial_bankroll_pen=100.00,
        base_stake_pen=1.00,
        max_stake_pen=2.00,
        min_ev_threshold=0.05,
        dynamic_conviction_staking=True,
        enable_cppi_shield=True,
        staking_mode="CONSERVATIVE",
        exclude_synthetic=True,
    )
    scout = NBADataScoutAgent(db)
    visual = VisualResearcherAgent()
    calibrator_agent = ModelCalibratorAgent()
    auditor = NBAAuditorAgent(db, paper_engine)

    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    yesterday_str = (now_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    today_str = now_dt.strftime("%Y-%m-%d")
    tomorrow_str = (now_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    # 1. Fetch dates based on cycle mode:
    # - settle_and_calibrate: yesterday and today (final results & boxscores)
    # - pregame: today and tomorrow (fresh odds & upcoming lines)
    # - auto: complete slate (yesterday, today, tomorrow)
    if mode == "settle_and_calibrate":
        dates_to_ingest = [yesterday_str, today_str]
    elif mode == "pregame":
        dates_to_ingest = [today_str, tomorrow_str]
    else:
        dates_to_ingest = [yesterday_str, today_str, tomorrow_str]

    # Always ensure any dates with unresolved PENDING bets, pending props, or unfinalized games whose tipoff passed are refreshed
    extra_matchdays = [
        r["matchday_date"]
        for r in db.fetch_all(
            """
            SELECT DISTINCT matchday_date FROM games 
            WHERE status != 'FINAL' AND game_start_time <= ? AND matchday_date IS NOT NULL
            UNION
            SELECT DISTINCT matchday_date FROM player_prop_picks 
            WHERE status = 'PENDING' AND matchday_date IS NOT NULL
            UNION
            SELECT DISTINCT matchday_date FROM simulated_bets 
            WHERE status = 'PENDING' AND matchday_date IS NOT NULL
            """,
            (now_str,),
        )
        if r.get("matchday_date")
    ]
    for p_date in extra_matchdays:
        if p_date not in dates_to_ingest:
            dates_to_ingest.append(p_date)

    router = DataSourceRouter([ESPNPublicAdapter(timeout_seconds=10)])
    ingested_dates: list[str] = []
    for dt_str in dates_to_ingest:
        try:
            scout.ingest_and_validate_dataset(router, date_str=dt_str)
            ingested_dates.append(dt_str)
        except Exception:
            pass

    # 1b. Automatically promote latest pre-tipoff odds to closing lines for started / final games
    new_closing_lines = paper_engine.persist_closing_lines_for_games(now_str)

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

    # 2b. Settle any PENDING player prop & SGP bets whose games are now FINAL, POSTPONED, or CANCELLED
    pending_props = db.fetch_all(
        """
        SELECT DISTINCT p.game_id
        FROM player_prop_picks p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.status = 'PENDING'
          AND g.status IN ('FINAL', 'POSTPONED', 'CANCELLED')
        """
    )
    game_boxscores: dict[str, dict[str, dict[str, float]]] = {}
    espn_adapter = ESPNPublicAdapter(timeout_seconds=10)
    for row in pending_props:
        gid = row["game_id"]
        ev_id = gid.replace("ESPN_", "").split("_")[0]
        try:
            b_stats = espn_adapter.fetch_player_boxscores(ev_id)
            if b_stats:
                game_boxscores[gid] = b_stats
        except Exception:
            pass
    settled_props_now = paper_engine.settle_pending_player_props(game_boxscores=game_boxscores, settled_at=now_str)

    # 3. Auto-Calibration Step: Fit calibrators & models on all strictly prior FINAL games
    # Refresh current timestamp post-ingestion to encompass recently settled games without temporal leakage
    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 3a. Make sure real NBA history exists (one-time ESPN backfill of 2 seasons) and recompute
    #     leakage-free pre-game ratings + real rest days for every real game.
    real_final_count = db.fetch_one(
        "SELECT COUNT(*) AS c FROM games WHERE status = 'FINAL' AND game_id NOT LIKE 'SYN%'"
    )["c"]
    if real_final_count < MIN_REAL_GAMES_FOR_TRAINING:
        try:
            backfill_espn_history(db, date(2024, 10, 22), (now_dt - timedelta(days=1)).date())
        except Exception:
            pass
    apply_pregame_team_ratings(db)

    all_final_games = db.fetch_all(
        "SELECT * FROM games WHERE status = 'FINAL' AND home_score IS NOT NULL ORDER BY game_start_time ASC"
    )
    real_final_games = [g for g in all_final_games if not is_synthetic_game_id(g["game_id"])]
    if len(real_final_games) >= MIN_REAL_GAMES_FOR_TRAINING:
        # Never let synthetic fixtures shape real-game predictions
        all_final_games = real_final_games

    model_a = BaselineModel("model_a_baseline_v1")
    model_f = EnsembleStackingModel(MODEL_VERSION_ID)
    db.execute_insert(
        """
        INSERT OR IGNORE INTO model_versions (
            model_version_id, model_family, market, train_start_date, train_end_date,
            trained_at, hyperparameters_json, is_active, approved_by
        ) VALUES (?, 'model_f_meta_ensemble', 'moneyline', '2024-10-22', ?, ?, ?, 1, 'orchestrator_v4')
        """,
        (
            MODEL_VERSION_ID,
            today_str,
            now_str,
            json.dumps(
                {
                    "montecarlo_sims": 10000,
                    "market_anchor_model_weight": DEFAULT_MODEL_WEIGHT,
                    "max_model_market_disagreement": MAX_MODEL_MARKET_DISAGREEMENT,
                    "training_data": "real_espn_history_only",
                    "team_ratings": "pace_decoupled_huber_multi_horizon_ewma",
                }
            ),
        ),
    )
    db.execute_insert(
        """
        INSERT OR IGNORE INTO model_versions (
            model_version_id, model_family, market, train_start_date, train_end_date,
            trained_at, hyperparameters_json, is_active, approved_by
        ) VALUES ('model_g_ml_montecarlo_v4', 'model_g_ml_montecarlo_hybrid', 'total_points', '2024-10-22', ?, ?, '{"n_simulations": 10000, "regimes": ["Q1_Q3", "Q4_Blowout", "Clutch_Fouling", "Overtime"]}', 1, 'orchestrator_v4')
        """,
        (today_str, now_str),
    )
    model_a.fit(all_final_games, now_str)
    model_f.fit(all_final_games, now_str)

    # Fit probability calibrators on resolved predictions from the current model version,
    # augmented with strictly out-of-sample walk-forward evaluations when live sample < 50
    resolved_ml_preds = db.fetch_all(
        """
        SELECT p.raw_probability, g.game_start_time, g.result_recorded_at,
               CASE WHEN g.home_score > g.away_score THEN 1 ELSE 0 END AS outcome
        FROM predictions p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.market = 'moneyline' AND p.selection = 'HOME' AND p.model_version_id = ?
          AND g.status = 'FINAL' AND g.game_start_time < ?
          AND (g.result_recorded_at IS NULL OR g.result_recorded_at <= ?)
        """,
        (MODEL_VERSION_ID, now_str, now_str),
    )
    resolved_tot_preds = db.fetch_all(
        """
        SELECT p.raw_probability, g.game_start_time, g.result_recorded_at,
               CASE WHEN (g.home_score + g.away_score) > p.line_value THEN 1 ELSE 0 END AS outcome
        FROM predictions p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.market = 'total_points' AND p.selection = 'OVER' AND p.model_version_id = ?
          AND g.status = 'FINAL' AND g.game_start_time < ?
          AND (g.result_recorded_at IS NULL OR g.result_recorded_at <= ?)
        """,
        (MODEL_VERSION_ID, now_str, now_str),
    )

    if len(resolved_ml_preds) < 50 and len(all_final_games) >= 150:
        wf_slice = [g for g in all_final_games[-65:] if str(g["game_start_time"]) < now_str]
        if wf_slice:
            wf_cutoff = wf_slice[0]["game_start_time"]
            wf_train = [g for g in all_final_games if str(g["game_start_time"]) < wf_cutoff]
            wf_model = EnsembleStackingModel(MODEL_VERSION_ID)
            wf_model.fit(wf_train, wf_cutoff)
            for wg in wf_slice:
                rec_ts = wg.get("result_recorded_at")
                if rec_ts and parse_iso_utc(rec_ts) > parse_iso_utc(now_str):
                    rec_ts = None
                p_ml_wf = wf_model.predict_moneyline(wg, all_final_games)["p_home"]
                p_tot_wf = wf_model.predict_total_points(wg, all_final_games, 228.5)["p_over"]
                resolved_ml_preds.append(
                    {
                        "raw_probability": p_ml_wf,
                        "game_start_time": wg["game_start_time"],
                        "result_recorded_at": rec_ts,
                        "outcome": 1 if wg["home_score"] > wg["away_score"] else 0,
                    }
                )
                resolved_tot_preds.append(
                    {
                        "raw_probability": p_tot_wf,
                        "game_start_time": wg["game_start_time"],
                        "result_recorded_at": rec_ts,
                        "outcome": 1 if (wg["home_score"] + wg["away_score"]) > 228.5 else 0,
                    }
                )

    ml_cal = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    tot_cal = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    ml_va = VennAbersConformalInterval(window=1200, min_samples=60)
    tot_va = VennAbersConformalInterval(window=1200, min_samples=60)
    ml_method = ml_cal.fit(resolved_ml_preds, now_str) if resolved_ml_preds else "identity"
    tot_method = tot_cal.fit(resolved_tot_preds, now_str) if resolved_tot_preds else "identity"
    if resolved_ml_preds:
        ml_va.fit(resolved_ml_preds, now_str)
    if resolved_tot_preds:
        tot_va.fit(resolved_tot_preds, now_str)

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
                MODEL_VERSION_ID,
                curve_ml["sample_size"],
                curve_ml["brier_score"],
                curve_ml["log_loss"],
                curve_ml["ece"],
                ml_method,
                json.dumps(curve_ml["bins"]),
            ),
        )

    if resolved_tot_preds:
        curve_tot = compute_reliability_curve(
            [float(r["raw_probability"]) for r in resolved_tot_preds],
            [int(r["outcome"]) for r in resolved_tot_preds],
        )
        db.execute_insert(
            """
            INSERT INTO calibration_logs (
                eval_id, evaluated_at, model_version_id, market, sample_size,
                brier_score, log_loss, ece, calibration_method, bins_json, promoted
            ) VALUES (?, ?, ?, 'total_points', ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                f"CAL_TOT_{uuid.uuid4().hex[:8].upper()}",
                now_str,
                MODEL_VERSION_ID,
                curve_tot["sample_size"],
                curve_tot["brier_score"],
                curve_tot["log_loss"],
                curve_tot["ece"],
                tot_method,
                json.dumps(curve_tot["bins"]),
            ),
        )

    # 4. Evaluate upcoming SCHEDULED games across the entire slate and rank globally by EV per matchday
    # (Skip pre-game evaluation if running exclusively in settle_and_calibrate mode)
    new_bets_placed = 0
    candidates_by_matchday: dict[str, list[dict[str, Any]]] = defaultdict(list)

    if mode != "settle_and_calibrate":
        scheduled_games = db.fetch_all(
            "SELECT * FROM games WHERE status = 'SCHEDULED' AND game_start_time > ? ORDER BY game_start_time ASC",
            (now_str,),
        )
        for g in scheduled_games:
            existing_bet = db.fetch_one("SELECT bet_id FROM simulated_bets WHERE game_id = ?", (g["game_id"],))
            if existing_bet:
                continue
            raw_game_odds = db.fetch_all(
                "SELECT * FROM odds_snapshots WHERE game_id = ? AND is_closing_line = 0 ORDER BY captured_at ASC",
                (g["game_id"],),
            )
            if not raw_game_odds:
                continue

            # Keep only the freshest pre-game line per (market, selection) so stale earlier lines are ignored
            latest_by_mkt_sel: dict[tuple[str, str], dict[str, Any]] = {}
            for o in raw_game_odds:
                latest_by_mkt_sel[(o["market"], o["selection"])] = o
            game_odds = list(latest_by_mkt_sel.values())

            latest_odds_ts = max(str(o["captured_at"]) for o in game_odds)
            existing_pred = db.fetch_one(
                "SELECT MAX(odds_captured_at) AS max_cap FROM predictions WHERE game_id = ? AND model_version_id = ?",
                (g["game_id"], MODEL_VERSION_ID),
            )
            if existing_pred and existing_pred.get("max_cap") and str(existing_pred["max_cap"]) >= latest_odds_ts:
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
            va_home_int = ml_va.predict_interval(raw_p_home)

            tot_odds = [o for o in game_odds if o["market"] == "total_points"]
            line_val = float(tot_odds[0]["line_value"]) if tot_odds else 228.5
            pred_f_tot = model_f.predict_total_points(g, all_final_games, line_val)
            raw_p_over = pred_f_tot["p_over"]
            cal_p_over = tot_cal.transform_single(raw_p_over)
            va_over_int = tot_va.predict_interval(raw_p_over)

            feats["mc_overtime_prob"] = pred_f_tot.get("overtime_prob", 0.05)
            feats["mc_blowout_prob"] = pred_f_tot.get("blowout_prob", 0.12)
            feats["mc_conformal_q10_total"] = pred_f_tot.get("conformal_q10_total", 205.0)
            feats["mc_conformal_q90_total"] = pred_f_tot.get("conformal_q90_total", 250.0)
            feats["va_conformal_home_width"] = va_home_int["width"]
            feats["va_conformal_over_width"] = va_over_int["width"]

            consensus_map = compute_market_consensus(game_odds)
            steam_map = compute_line_steam(raw_game_odds)

            for o in game_odds:
                validate_odds_record(o, g["game_start_time"], simulated_prediction_time=pred_ts)
                mkt = o["market"]
                sel = o["selection"]
                line_v = o.get("line_value")
                cons_entry = consensus_map.get((mkt, sel, line_v))
                cons_p = cons_entry["p_market"] if cons_entry else None
                steam_entry = steam_map.get((mkt, sel))
                s_delta = float(steam_entry["steam_delta"]) if steam_entry else 0.0

                if mkt == "moneyline":
                    raw_p = raw_p_home if sel == "HOME" else round(1.0 - raw_p_home, 6)
                    cal_p = cal_p_home if sel == "HOME" else round(1.0 - cal_p_home, 6)
                    unc = pred_f_ml["uncertainty_std"]
                    m_ver = model_f.version_id
                    if sel == "HOME":
                        conf_int = va_home_int
                    else:
                        conf_int = {
                            "p0": round(1.0 - va_home_int["p1"], 6),
                            "p1": round(1.0 - va_home_int["p0"], 6),
                            "p_va": round(1.0 - va_home_int["p_va"], 6),
                            "width": va_home_int["width"],
                        }
                else:
                    raw_p = raw_p_over if sel == "OVER" else round(1.0 - raw_p_over, 6)
                    cal_p = cal_p_over if sel == "OVER" else round(1.0 - cal_p_over, 6)
                    unc = pred_f_tot["uncertainty_std"]
                    m_ver = model_f.version_id
                    if sel == "OVER":
                        conf_int = va_over_int
                    else:
                        conf_int = {
                            "p0": round(1.0 - va_over_int["p1"], 6),
                            "p1": round(1.0 - va_over_int["p0"], 6),
                            "p_va": round(1.0 - va_over_int["p_va"], 6),
                            "width": va_over_int["width"],
                        }

                opp = evaluate_market_opportunity(
                    estimated_prob=cal_p,
                    uncertainty_std=unc,
                    odds_record=o,
                    game_start_time=g["game_start_time"],
                    model_version_id=m_ver,
                    simulated_prediction_time=pred_ts,
                    market_consensus_prob=cons_p,
                    model_weight=DEFAULT_MODEL_WEIGHT,
                    max_disagreement=MAX_MODEL_MARKET_DISAGREEMENT,
                    steam_delta=s_delta,
                    conformal_interval=conf_int,
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
                        m_ver, raw_p, opp["estimated_probability"], unc, opp["implied_prob_gross"],
                        opp["implied_prob_fair"], opp["bookmaker_overround"],
                        opp["decimal_odds_used"], opp["odds_provider"], opp["odds_captured_at"],
                        opp["ev_unit"], opp["ev_pct"], pred_ts, json.dumps(feats),
                    ),
                )
                opp["prediction_id"] = pred_id
                opp["raw_probability"] = raw_p
                opp["calibrated_probability"] = opp["estimated_probability"]
                opp["uncertainty_std"] = unc
                opp["overtime_prob"] = pred_f_tot.get("overtime_prob", 0.05)
                opp["blowout_prob"] = pred_f_tot.get("blowout_prob", 0.12)
                opp["emitted_at"] = pred_ts
                candidates_by_matchday[g["matchday_date"]].append(opp)

        for m_date in sorted(candidates_by_matchday.keys()):
            day_res = paper_engine.evaluate_and_record_matchday_selections(m_date, candidates_by_matchday[m_date])
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

    # 4b. Sync live official NBA rosters & Scan Player Props & RETAbet SGP Opportunities for upcoming games
    try:
        from src.ingestion.roster_manager import sync_all_nba_rosters
        from src.prediction.player_props import PlayerPropsEngine
        sync_all_nba_rosters(db)
        props_engine = PlayerPropsEngine(db=db, min_ev_threshold=0.03)
        slate_records = db.fetch_all(
            """
            SELECT * FROM games 
            WHERE status = 'SCHEDULED' 
              AND game_start_time > ? 
              AND game_id NOT LIKE 'SYN%'
            ORDER BY game_start_time ASC 
            LIMIT 15
            """,
            (now_str,),
        )
        props_engine.generate_slate_prop_opportunities(
            slate_games=slate_records,
            bankroll_pen=paper_engine.get_bankroll_state()["settled_bankroll_pen"],
        )
    except Exception:
        pass

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

    summary_payload = {
        "cycle_type": "INCREMENTAL_CLOUD_AUTO_CYCLE",
        "mode": mode,
        "timestamp_utc": now_str,
        "ingested_dates": ingested_dates,
        "closing_lines_promoted": new_closing_lines,
        "bets_settled_in_cycle": len(settled_now),
        "new_bets_placed_in_cycle": new_bets_placed,
        "active_calibration_methods": {"moneyline": ml_method, "total_points": tot_method},
        "bankroll_state": paper_engine.get_bankroll_state(),
        "audit_verdict": audit_res["exit_gates_evaluation"]["recommendation"],
        "financial_and_statistical_summary": {
            "initial_bankroll_pen": 100.0,
            "current_settled_bankroll_pen": metrics["current_settled_bankroll_pen"],
            "net_profit_pen": metrics["net_profit_pen"],
            "roi_pct": metrics["roi_pct"],
            "yield_pct": metrics["yield_pct"],
            "settled_bets_count": metrics["settled_bets_count"],
            "won_count": metrics["won_count"],
            "lost_count": metrics["lost_count"],
            "push_count": metrics["push_count"],
            "max_drawdown_pen": metrics["max_drawdown_pen"],
            "overall_brier_score": metrics["overall_brier_score"],
            "baseline_brier_score": metrics["baseline_brier_score"],
            "overall_log_loss": metrics["overall_log_loss"],
            "baseline_log_loss": metrics["baseline_log_loss"],
            "mean_clv_pct": metrics.get("mean_clv_pct"),
            "clv_governor_factor": metrics.get("clv_governor_factor", 1.0),
        },
        "sources_info": sources_info,
        "visual_context": vis_info,
        "environment_status": env_status,
    }

    eval_out_path = PROJECT_ROOT / "data" / "evaluation" / "latest_run_summary.json"
    eval_out_path.parent.mkdir(parents=True, exist_ok=True)
    eval_out_path.write_text(json.dumps(summary_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    return summary_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run stateful NBA cloud trading & auto-calibration cycle.")
    parser.add_argument("--mode", default="auto", choices=["auto", "pregame", "settle_and_calibrate"])
    args = parser.parse_args()
    out = run_incremental_cloud_cycle(mode=args.mode)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
