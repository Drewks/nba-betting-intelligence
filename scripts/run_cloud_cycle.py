"""
Stateful Cloud Execution & Auto-Calibration Script (`scripts/run_cloud_cycle.py`):
Designed to run unattended in the cloud (e.g., GitHub Actions cron 4x/day) without a local PC turned on.
- Preserves live production SQLite state (`state-live` branch) while keeping `main` frozen for CI
- Fetches official NBA results from ESPN (`ESPNPublicAdapter`) and live Peruvian/Pinnacle odds
- Settles PENDING simulated bets, player props, parlays, and immutable `shadow_candidates`
- Automatically recalibrates (`ProbabilityCalibrator`) and evaluates walk-forward model comparison
  strictly without temporal lookahead
- Generates pre-game predictions, fractional Kelly paper selections, reports, and Obsidian Vault sync
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backfill_espn_history import backfill as backfill_espn_history
from scripts.cloud_cycle_helpers import (
    build_walk_forward_oos_comparisons_for_active_model,
    compute_config_hash,
    compute_totals_line_band_telemetry,
    determine_database_role,
    evaluate_scheduled_slate_candidates,
    fit_and_log_cycle_calibrators,
    resolve_git_commit_sha,
    settle_cycle_pending_positions,
)
from src.agents.specialized_agents import (
    ModelCalibratorAgent,
    NBAAuditorAgent,
    NBADataScoutAgent,
    VisualResearcherAgent,
)
from src.backtesting.backtester import WalkForwardBacktester
from src.config import load_config
from src.features.boxscore_features import compute_boxscore_features
from src.features.official_availability import build_official_availability_overrides
from src.features.team_ratings import apply_pregame_team_ratings
from src.ingestion.adapters import DataSourceRouter, ESPNPublicAdapter
from src.ingestion.boxscores import backfill_boxscores, load_boxscores
from src.ingestion.live_peru_scraper import LivePeruOddsScraper
from src.models.statistical_models import BaselineModel, EnsembleStackingModel
from src.orchestrator import Orchestrator
from src.paper_trading.engine import build_production_engine
from src.paper_trading.parlay_engine import ParlayTradingEngine
from src.paper_trading.shadow_ledger import summarize_shadow_ledger
from src.prediction.ev_calculator import MAX_MODEL_MARKET_DISAGREEMENT
from src.reporting.reporter import (
    export_bets_and_tracking_dashboard,
    generate_audit_report,
    generate_daily_report,
    generate_weekly_report,
    sync_obsidian_vault,
)
from src.storage.db import DatabaseManager
from src.validation.odds_integrity import quarantine_copied_live_quotes
from src.validation.validator import parse_iso_utc

# Model identity and market-anchor weight come from config/model_config.yaml (single source of truth).
_MODEL_CFG = load_config().model
MODEL_VERSION_ID = _MODEL_CFG.version_id
MARKET_ANCHOR_MODEL_WEIGHT = _MODEL_CFG.market_anchor_model_weight
MONEYLINE_MODEL_WEIGHT = _MODEL_CFG.moneyline_model_weight
MONEYLINE_MAX_DISAGREEMENT = _MODEL_CFG.moneyline_max_disagreement
MONEYLINE_MAX_ODDS = _MODEL_CFG.moneyline_max_odds
MIN_REAL_GAMES_FOR_TRAINING = 120
BOXSCORE_BACKFILL_PER_CYCLE = 600


def _compute_totals_line_band_telemetry(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Backwards-compatible export for telemetry tests (`T-015`)."""
    return compute_totals_line_band_telemetry(rows)


def _augment_resolved_calibration_from_walk_forward(
    db: DatabaseManager,
    all_final_games: list[dict[str, Any]],
    resolved_ml_preds: list[dict[str, Any]],
    resolved_tot_preds: list[dict[str, Any]],
    resolved_sp_preds: list[dict[str, Any]],
    now_str: str,
) -> None:
    """Fills sparse live calibration samples (< 50) using strict chronological OOS slices."""
    if len(resolved_ml_preds) >= 50 or len(all_final_games) < 150:
        return
    wf_slice = [g for g in all_final_games[-65:] if str(g["game_start_time"]) < now_str]
    if not wf_slice:
        return

    wf_gids = [str(g["game_id"]) for g in wf_slice]
    placeholders = ",".join("?" for _ in wf_gids)
    obs_wf_tot_rows = db.fetch_all(
        f"""
        SELECT o.game_id, o.line_value, o.provider, o.captured_at
        FROM v_observed_odds_snapshots o
        JOIN games g ON o.game_id = g.game_id
        WHERE o.game_id IN ({placeholders})
          AND o.market = 'total_points' AND o.selection = 'OVER'
          AND o.line_value IS NOT NULL AND o.line_value > 50.0
          AND o.captured_at < g.game_start_time
        ORDER BY CASE WHEN LOWER(o.provider) LIKE '%pinnacle%' THEN 0 ELSE 1 END ASC,
                 datetime(o.captured_at) DESC
        """,
        tuple(wf_gids),
    )
    obs_wf_tot_line: dict[str, float] = {}
    for r in obs_wf_tot_rows:
        obs_wf_tot_line.setdefault(str(r["game_id"]), float(r["line_value"]))

    obs_wf_sp_rows = db.fetch_all(
        f"""
        SELECT o.game_id, o.line_value, o.provider, o.captured_at
        FROM v_observed_odds_snapshots o
        JOIN games g ON o.game_id = g.game_id
        WHERE o.game_id IN ({placeholders})
          AND o.market = 'spread' AND o.selection = 'HOME'
          AND o.line_value IS NOT NULL AND ABS(o.line_value) <= 45.0
          AND o.captured_at < g.game_start_time
        ORDER BY CASE WHEN LOWER(o.provider) LIKE '%pinnacle%' THEN 0 ELSE 1 END ASC,
                 datetime(o.captured_at) DESC
        """,
        tuple(wf_gids),
    )
    obs_wf_sp_line: dict[str, float] = {}
    for r in obs_wf_sp_rows:
        obs_wf_sp_line.setdefault(str(r["game_id"]), float(r["line_value"]))

    wf_cutoff = wf_slice[0]["game_start_time"]
    wf_train = [g for g in all_final_games if str(g["game_start_time"]) < wf_cutoff]
    wf_model = EnsembleStackingModel(MODEL_VERSION_ID)
    wf_model.fit(wf_train, wf_cutoff)
    for wg in wf_slice:
        rec_ts = wg.get("result_recorded_at")
        if rec_ts and parse_iso_utc(rec_ts) > parse_iso_utc(now_str):
            rec_ts = None
        wg_prior = [fg for fg in all_final_games if str(fg["game_start_time"]) < str(wg["game_start_time"])]
        resolved_ml_preds.append(
            {
                "raw_probability": wf_model.predict_moneyline(wg, wg_prior)["p_home"],
                "game_start_time": wg["game_start_time"],
                "result_recorded_at": rec_ts,
                "outcome": 1 if wg["home_score"] > wg["away_score"] else 0,
            }
        )
        gid_wf = str(wg["game_id"])
        tot_line_wf = obs_wf_tot_line.get(gid_wf)
        if tot_line_wf is not None and abs((float(wg["home_score"]) + float(wg["away_score"])) - tot_line_wf) > 1e-9:
            resolved_tot_preds.append(
                {
                    "raw_probability": wf_model.predict_total_points(wg, wg_prior, tot_line_wf)["p_over"],
                    "line_value": tot_line_wf,
                    "game_start_time": wg["game_start_time"],
                    "result_recorded_at": rec_ts,
                    "outcome": 1 if (wg["home_score"] + wg["away_score"]) > tot_line_wf else 0,
                }
            )
        sp_line_wf = obs_wf_sp_line.get(gid_wf)
        if sp_line_wf is not None and abs((float(wg["home_score"]) - float(wg["away_score"])) + sp_line_wf) > 1e-9:
            resolved_sp_preds.append(
                {
                    "raw_probability": wf_model.predict_spread(wg, wg_prior, sp_line_wf)["p_cover_home"],
                    "line_value": sp_line_wf,
                    "game_start_time": wg["game_start_time"],
                    "result_recorded_at": rec_ts,
                    "outcome": 1 if (wg["home_score"] - wg["away_score"] + sp_line_wf) > 0 else 0,
                }
            )


def run_incremental_cloud_cycle(mode: str = "auto", db_path: Path | str | None = None) -> dict[str, Any]:
    target_db_path = Path(db_path) if db_path is not None else (PROJECT_ROOT / "data" / "nba_intelligence.sqlite3")

    if not target_db_path.exists():
        orch = Orchestrator(
            db_path=target_db_path,
            reports_dir=PROJECT_ROOT / "reports",
            obsidian_vault_dir=PROJECT_ROOT / "NBA",
            max_retries=2,
        )
        init_res = orch.run_full_pipeline(include_live_espn=True)
        return {"cycle_type": "INITIAL_BOOTSTRAP_AND_LIVE_SYNC", "run_id": init_res["run_id"]}

    db = DatabaseManager(target_db_path)
    paper_engine = build_production_engine(db)
    parlay_engine = ParlayTradingEngine(db)
    scout = NBADataScoutAgent(db)
    visual = VisualResearcherAgent()
    calibrator_agent = ModelCalibratorAgent()
    auditor = NBAAuditorAgent(db, paper_engine)

    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    yesterday_str = (now_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    today_str = now_dt.strftime("%Y-%m-%d")
    tomorrow_str = (now_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    if mode == "settle_and_calibrate":
        dates_to_ingest = [yesterday_str, today_str]
    elif mode == "pregame":
        dates_to_ingest = [today_str, tomorrow_str]
    else:
        dates_to_ingest = [yesterday_str, today_str, tomorrow_str]

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

    et_aligned_dates: list[str] = list(dates_to_ingest)
    for d_str in list(dates_to_ingest):
        try:
            prev_d = (datetime.strptime(d_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            if prev_d not in et_aligned_dates:
                et_aligned_dates.append(prev_d)
        except ValueError as exc:
            logger.debug("Ignoring malformed date %r in ET alignment: %s", d_str, exc)
    dates_to_ingest = sorted(et_aligned_dates)

    router = DataSourceRouter([ESPNPublicAdapter(timeout_seconds=10, enrich_with_the_odds_api=(mode != "settle_and_calibrate"))])
    ingested_dates: list[str] = []
    for dt_str in dates_to_ingest:
        try:
            scout.ingest_and_validate_dataset(router, date_str=dt_str)
            ingested_dates.append(dt_str)
        except Exception as exc:
            logger.warning(f"Ingestion failed for date {dt_str}: {exc}")

    new_closing_lines = paper_engine.persist_closing_lines_for_games(now_str)

    if mode != "settle_and_calibrate":
        try:
            allow_props = bool(load_config().risk.allow_player_props_betting)
            LivePeruOddsScraper(db=db).scan_and_alert_entire_slate(
                notify_telegram=False,
                include_player_props=allow_props,
            )
        except Exception as exc:
            logger.warning(f"Live Peruvian/Pinnacle odds sync failed cleanly: {exc}")

    # 2. Settle pending simulated bets, props, parlays, and immutable shadow candidates
    settled_now, shadow_settled_now = settle_cycle_pending_positions(
        db=db,
        paper_engine=paper_engine,
        parlay_engine=parlay_engine,
        now_str=now_str,
    )

    # 3. Auto-Calibration Step: Fit calibrators & models on strictly prior FINAL games
    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    real_final_count = (
        db.fetch_one("SELECT COUNT(*) AS c FROM games WHERE status = 'FINAL' AND game_id NOT LIKE 'SYN%'") or {"c": 0}
    )["c"]
    if real_final_count < MIN_REAL_GAMES_FOR_TRAINING:
        try:
            backfill_espn_history(db, date(2024, 10, 22), (now_dt - timedelta(days=1)).date())
        except Exception as exc:
            logger.error(f"Historical ESPN backfill failed: {exc}", exc_info=True)
    apply_pregame_team_ratings(db)

    all_final_games = db.fetch_all(
        "SELECT * FROM v_observed_games WHERE status = 'FINAL' AND home_score IS NOT NULL ORDER BY game_start_time ASC"
    )
    try:
        logger.info("Box score backfill: %s", backfill_boxscores(db, limit=BOXSCORE_BACKFILL_PER_CYCLE))
    except Exception as exc:
        logger.warning("Box score backfill failed: %s", exc)
    # Official NBA injury report (fetched now, at decision time) replaces the "missed last game" proxy
    # in the availability features of the upcoming games it covers; on any failure the proxy stays.
    availability_overrides: dict[str, dict[str, frozenset[str]]] = {}
    if mode != "settle_and_calibrate":
        try:
            from src.ingestion.nba_injury_report import NBAOfficialInjuryFeed

            availability_overrides = build_official_availability_overrides(
                db, NBAOfficialInjuryFeed().fetch_latest_report(), datetime.now(timezone.utc)
            )
        except Exception as exc:
            logger.warning("Official injury report not applied (proxy kept): %s", exc)
    bx_features = compute_boxscore_features(
        db.fetch_all("SELECT * FROM v_observed_games ORDER BY game_start_time ASC"),
        load_boxscores(db),
        availability_overrides=availability_overrides,
    )
    all_final_games = [{**g, **bx_features.get(g["game_id"], {})} for g in all_final_games]

    model_a = BaselineModel("model_a_baseline_v1")
    model_f = EnsembleStackingModel(MODEL_VERSION_ID)
    for m_id, m_fam, m_mkt, m_hp in [
        (
            MODEL_VERSION_ID,
            "model_f_meta_ensemble",
            "moneyline",
            {
                "montecarlo_sims": 10000,
                "market_anchor_model_weight": MARKET_ANCHOR_MODEL_WEIGHT,
                "max_model_market_disagreement": MAX_MODEL_MARKET_DISAGREEMENT,
                "training_data": "real_espn_history_only",
                "team_ratings": "pace_decoupled_huber_multi_horizon_ewma",
            },
        ),
        (model_f.model_b.version_id, "model_b_elo", "moneyline", {"family": "elo"}),
        (model_f.model_c.version_id, "model_c_point_margin", "moneyline", {"family": "huber_margin"}),
        (model_f.model_d.version_id, "model_d_total_points", "total_points", {"family": "ridge_totals"}),
        (model_f.model_e.version_id, "model_e_lightgbm", "moneyline", {"family": "hist_gbm"}),
        (
            model_f.model_g.version_id,
            "model_g_ml_montecarlo_hybrid",
            "total_points",
            {"n_simulations": 10000, "regimes": ["Q1_Q3", "Q4_Blowout", "Clutch_Fouling", "Overtime"]},
        ),
    ]:
        db.execute_insert(
            """
            INSERT OR IGNORE INTO model_versions (
                model_version_id, model_family, market, train_start_date, train_end_date,
                trained_at, hyperparameters_json, is_active, approved_by
            ) VALUES (?, ?, ?, '2024-10-22', ?, ?, ?, 1, 'orchestrator_v8')
            """,
            (m_id, m_fam, m_mkt, today_str, now_str, json.dumps(m_hp)),
        )
    model_a.fit(all_final_games, now_str)
    model_f.fit(all_final_games, now_str)

    resolved_ml_preds = db.fetch_all(
        """
        WITH latest AS (
            SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.game_id ORDER BY p.emitted_at DESC, p.prediction_id DESC) AS rn
            FROM v_observed_predictions p
            WHERE p.market = 'moneyline' AND p.selection = 'HOME' AND p.model_version_id = ?
        )
        SELECT COALESCE(l.raw_model_probability, l.raw_probability) AS raw_probability,
               g.game_start_time, g.result_recorded_at,
               CASE WHEN g.home_score > g.away_score THEN 1 ELSE 0 END AS outcome
        FROM latest l JOIN games g ON l.game_id = g.game_id
        WHERE l.rn = 1 AND g.status = 'FINAL' AND g.game_start_time < ?
          AND (g.result_recorded_at IS NULL OR g.result_recorded_at <= ?)
        """,
        (MODEL_VERSION_ID, now_str, now_str),
    )
    resolved_tot_preds = db.fetch_all(
        """
        WITH latest AS (
            SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.game_id ORDER BY p.emitted_at DESC, p.prediction_id DESC) AS rn
            FROM v_observed_predictions p
            WHERE p.market = 'total_points' AND p.selection = 'OVER' AND p.model_version_id = ?
        )
        SELECT COALESCE(l.raw_model_probability, l.raw_probability) AS raw_probability,
               l.line_value, g.game_start_time, g.result_recorded_at,
               CASE WHEN (g.home_score + g.away_score) > l.line_value THEN 1 ELSE 0 END AS outcome
        FROM latest l JOIN games g ON l.game_id = g.game_id
        WHERE l.rn = 1 AND g.status = 'FINAL' AND g.game_start_time < ?
          AND (g.result_recorded_at IS NULL OR g.result_recorded_at <= ?)
          AND l.line_value IS NOT NULL AND (g.home_score + g.away_score) != l.line_value
        """,
        (MODEL_VERSION_ID, now_str, now_str),
    )
    resolved_sp_preds = db.fetch_all(
        """
        WITH latest AS (
            SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.game_id ORDER BY p.emitted_at DESC, p.prediction_id DESC) AS rn
            FROM v_observed_predictions p
            WHERE p.market = 'spread' AND p.selection = 'HOME' AND p.model_version_id = ?
        )
        SELECT COALESCE(l.raw_model_probability, l.raw_probability) AS raw_probability,
               l.line_value, g.game_start_time, g.result_recorded_at,
               CASE WHEN (g.home_score - g.away_score + l.line_value) > 0 THEN 1 ELSE 0 END AS outcome
        FROM latest l JOIN games g ON l.game_id = g.game_id
        WHERE l.rn = 1 AND g.status = 'FINAL' AND g.game_start_time < ?
          AND (g.result_recorded_at IS NULL OR g.result_recorded_at <= ?)
          AND l.line_value IS NOT NULL AND ABS(g.home_score - g.away_score + l.line_value) > 1e-9
        """,
        (MODEL_VERSION_ID, now_str, now_str),
    )

    _augment_resolved_calibration_from_walk_forward(
        db, all_final_games, resolved_ml_preds, resolved_tot_preds, resolved_sp_preds, now_str
    )

    config_hash, config_version = compute_config_hash(PROJECT_ROOT, MODEL_VERSION_ID)
    commit_sha = resolve_git_commit_sha(PROJECT_ROOT)
    cal_bundle = fit_and_log_cycle_calibrators(
        db,
        model_f=model_f,
        model_version_id=MODEL_VERSION_ID,
        resolved_ml_preds=resolved_ml_preds,
        resolved_tot_preds=resolved_tot_preds,
        resolved_sp_preds=resolved_sp_preds,
        now_dt=now_dt,
        now_str=now_str,
        mode=mode,
        all_final_games=all_final_games,
        config_hash=config_hash,
        config_version=config_version,
        commit_sha=commit_sha,
    )

    # 4. Evaluate upcoming SCHEDULED games across the slate
    new_bets_placed = 0
    candidates_by_matchday: dict[str, list[dict[str, Any]]] = {}
    # Defense in depth: a live quote copied onto another game of the same teams must never reach a
    # decision, even if a feed regresses; the auditor reports any that slipped past this point.
    with db.connect() as integrity_conn:
        copied_quotes_quarantined = quarantine_copied_live_quotes(integrity_conn, now_str)
    if copied_quotes_quarantined:
        logging.warning("Quarantined %d copied cross-game live quotes before evaluation", copied_quotes_quarantined)
    if mode != "settle_and_calibrate":
        candidates_by_matchday = evaluate_scheduled_slate_candidates(
            db,
            all_final_games=all_final_games,
            bx_features=bx_features,
            model_f=model_f,
            model_version_id=MODEL_VERSION_ID,
            cal_bundle=cal_bundle,
            market_anchor_weight=MARKET_ANCHOR_MODEL_WEIGHT,
            moneyline_weight=MONEYLINE_MODEL_WEIGHT,
            moneyline_max_disagreement=MONEYLINE_MAX_DISAGREEMENT,
            moneyline_max_odds=MONEYLINE_MAX_ODDS,
            now_str=now_str,
        )
        for m_date in sorted(candidates_by_matchday.keys()):
            day_res = paper_engine.evaluate_and_record_matchday_selections(m_date, candidates_by_matchday[m_date])
            new_bets_placed += len(day_res["placed_bets"])

    # 4b. Fail-closed Player Props & Parlays check
    risk_cfg = load_config().risk
    props_parlays_status: dict[str, Any] = {
        "allow_player_props_betting": bool(risk_cfg.allow_player_props_betting),
        "allow_parlays": bool(risk_cfg.allow_parlays),
        "executed": False,
        "placed_parlays_count": 0,
    }
    if risk_cfg.allow_player_props_betting or risk_cfg.allow_parlays:
        try:
            from src.ingestion.roster_manager import sync_all_nba_rosters
            from src.prediction.player_props import PlayerPropsEngine

            sync_all_nba_rosters(db)
            props_engine = PlayerPropsEngine(db=db, min_ev_threshold=0.03)
            slate_records = db.fetch_all(
                """
                SELECT * FROM games
                WHERE status = 'SCHEDULED' AND game_start_time > ? AND game_id NOT LIKE 'SYN%'
                ORDER BY game_start_time ASC LIMIT 15
                """,
                (now_str,),
            )
            slate_props = props_engine.generate_slate_prop_opportunities(
                slate_games=slate_records,
                bankroll_pen=paper_engine.get_bankroll_state()["settled_bankroll_pen"],
                output_file=PROJECT_ROOT / "data" / "evaluation" / "latest_player_props.json",
            )
            placed_parlays_list = parlay_engine.record_candidate_parlays(
                candidates=slate_props,
                matchday_date=today_str,
                allow_parlays=bool(risk_cfg.allow_parlays),
            )
            props_parlays_status["executed"] = True
            props_parlays_status["placed_parlays_count"] = len(placed_parlays_list)
        except Exception as exc:
            logger.warning(f"Handled exception in run_cloud_cycle props/parlays gate: {exc}")
            props_parlays_status["error"] = str(exc)
    else:
        logger.info("SKIPPED_PROPS_AND_PARLAYS: allow_player_props_betting=false and allow_parlays=false in model_config.yaml")

    # 5. Recompute metrics: use live post-m012 resolved active-version rows when available,
    # otherwise construct expanding-window OOS walk-forward comparisons for the frozen MODEL_VERSION_ID.
    live_active_m012_row = db.fetch_one(
        """
        SELECT COUNT(*) AS c
        FROM v_observed_predictions p
        JOIN games g ON g.game_id = p.game_id
        WHERE p.model_version_id = ?
          AND p.calibrated_model_probability IS NOT NULL
          AND g.status = 'FINAL'
          AND g.home_score IS NOT NULL
          AND g.away_score IS NOT NULL
          AND p.game_id NOT LIKE 'SYN%'
        """,
        (MODEL_VERSION_ID,),
    )
    live_active_m012_count = int((live_active_m012_row or {}).get("c") or 0)

    bt = WalkForwardBacktester(db, paper_engine)
    if live_active_m012_count > 0:
        metrics = bt.compute_comprehensive_metrics(model_comparison_records=[])
    else:
        oos_records = build_walk_forward_oos_comparisons_for_active_model(
            db,
            all_final_games,
            MODEL_VERSION_ID,
            now_str,
            market_anchor_weight=MARKET_ANCHOR_MODEL_WEIGHT,
            moneyline_weight=MONEYLINE_MODEL_WEIGHT,
        )
        metrics = bt.compute_comprehensive_metrics(
            model_comparison_records=oos_records,
            calibration_evaluation_source=(
                "WALK_FORWARD_FROZEN_ACTIVE_VERSION_OOS"
                if oos_records
                else "INSUFFICIENT_M012_OBSERVED_PREDICTIONS"
            ),
        )

    shadow_summary = summarize_shadow_ledger(db)
    db_role = determine_database_role(PROJECT_ROOT, target_db_path, explicit_db_path=(db_path is not None))
    metrics["shadow_ledger"] = shadow_summary
    metrics["database_role"] = db_role
    metrics["run_manifest"] = {
        "run_id": cal_bundle["run_manifest_id"],
        "commit_sha": commit_sha,
        "model_version_id": MODEL_VERSION_ID,
        "ensemble_version": model_f.version_id,
        "submodel_versions": cal_bundle["submodel_versions_map"],
        "config_hash": config_hash,
        "config_version": config_version,
        "data_cutoff_utc": cal_bundle["data_cutoff_utc"],
        "calibrators": cal_bundle["calibrator_metadata"],
    }
    audit_res = auditor.run_independent_audit(metrics)
    audit_res["shadow_ledger"] = shadow_summary
    promo_eval = calibrator_agent.evaluate_calibration_and_promotion(metrics)
    sources_info = scout.investigate_sources()
    vis_info = visual.inspect_and_extract_context()

    env_status = {
        "python_version": "CPython 3.12 (uv cloud/local runner)",
        "model_version_id": MODEL_VERSION_ID,
        "run_manifest_id": cal_bundle["run_manifest_id"],
        "commit_sha": commit_sha,
        "config_hash": config_hash,
        "database_role": db_role,
        "peru_scraper_policy": load_config().sources.peru_scraper_policy,
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

    summary_payload = {
        "cycle_type": "INCREMENTAL_CLOUD_AUTO_CYCLE",
        "mode": mode,
        "timestamp_utc": now_str,
        "run_manifest_id": cal_bundle["run_manifest_id"],
        "run_manifest": metrics["run_manifest"],
        "database_role": db_role,
        "ingested_dates": ingested_dates,
        "closing_lines_promoted": new_closing_lines,
        "official_injury_report_games": len(availability_overrides),
        "bets_settled_in_cycle": len(settled_now),
        "shadow_settled_in_cycle": len(shadow_settled_now),
        "new_bets_placed_in_cycle": new_bets_placed,
        "predictions_generated": sum(len(v) for v in candidates_by_matchday.values()),
        "active_calibration_methods": {
            "moneyline": cal_bundle["ml_method"],
            "total_points": cal_bundle["tot_method"],
            "spread": cal_bundle["sp_method"],
        },
        "totals_calibration_diagnostics": {
            "sample_size": len(resolved_tot_preds),
            "fallback_active": cal_bundle["totals_fallback"],
            "line_bands": cal_bundle["totals_line_bands"],
        },
        "props_parlays_status": props_parlays_status,
        "shadow_ledger": shadow_summary,
        "bankroll_state": paper_engine.get_bankroll_state(),
        "sub_bankroll_state": parlay_engine.get_bankroll_state(),
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
            "active_model_version_id": metrics.get("active_model_version_id"),
            "calibration_evaluation_source": metrics.get("calibration_evaluation_source"),
            "by_model_version": metrics.get("by_model_version"),
            "overall_brier_score": metrics["overall_brier_score"],
            "baseline_brier_score": metrics["baseline_brier_score"],
            "overall_log_loss": metrics["overall_log_loss"],
            "market_brier_score": metrics.get("market_brier_score"),
            "model_brier_on_market_subset": metrics.get("model_brier_on_market_subset"),
            "market_comparison_sample_size": metrics.get("market_comparison_sample_size"),
            "history_integrity": audit_res.get("history_integrity"),
            "baseline_log_loss": metrics["baseline_log_loss"],
            "mean_clv_pct": metrics.get("mean_clv_pct"),
            "clv_governor_factor": metrics.get("clv_governor_factor", 1.0),
            "by_market": metrics.get("performance_by_market"),
            "shadow_ledger": shadow_summary,
        },
        "sources_info": sources_info,
        "visual_context": vis_info,
        "environment_status": env_status,
    }

    eval_out_path = PROJECT_ROOT / "data" / "evaluation" / "latest_run_summary.json"
    eval_out_path.parent.mkdir(parents=True, exist_ok=True)
    eval_out_path.write_text(json.dumps(summary_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        db.checkpoint(truncate=True)
    except Exception as cp_exc:
        logger.warning(f"Database checkpoint warning: {cp_exc}")

    return summary_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run stateful NBA cloud trading & auto-calibration cycle.")
    parser.add_argument("--mode", default="auto", choices=["auto", "pregame", "settle_and_calibrate"])
    args = parser.parse_args()
    out = run_incremental_cloud_cycle(mode=args.mode)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
