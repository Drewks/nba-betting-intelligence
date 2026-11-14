"""
Stateful Cloud Execution & Auto-Calibration Script (`scripts/run_cloud_cycle.py`):
Designed to run unattended in the cloud (e.g., GitHub Actions cron 2x/day) without a local PC turned on.
- Preserves `data/nba_intelligence.sqlite3` across runs (initializes baseline history only on first run)
- Fetches yesterday's and today's official NBA results from ESPN (`ESPNPublicAdapter`)
- Settles any PENDING simulated bets whose games are now FINAL
- Automatically recalibrates (`ProbabilityCalibrator`) and evaluates walk-forward model promotion
  when new settled outcomes accumulate, strictly without temporal lookahead
- Generates new pre-game predictions and fractional Kelly paper selections (capped per matchday/EV config)
- Updates `reports/*.md` and the `NBA/` Obsidian Vault
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
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
from src.config import load_config
from src.calibration.calibrator import (
    ProbabilityCalibrator,
    VennAbersConformalInterval,
    compute_reliability_curve,
)
from src.features.boxscore_features import compute_boxscore_features
from src.features.builder import build_pregame_features
from src.features.team_ratings import apply_pregame_team_ratings
from src.ingestion.adapters import DataSourceRouter, ESPNPublicAdapter
from src.ingestion.boxscores import backfill_boxscores, load_boxscores
from src.ingestion.live_peru_scraper import LivePeruOddsScraper
from src.models.statistical_models import (
    BaselineModel,
    EnsembleStackingModel,
)
from src.orchestrator import Orchestrator
from src.paper_trading.engine import build_production_engine
from src.paper_trading.parlay_engine import ParlayTradingEngine
from src.prediction.ev_calculator import (
    MAX_MODEL_MARKET_DISAGREEMENT,
    compute_line_steam,
    compute_market_consensus,
    evaluate_market_opportunity,
    select_best_line_shopping_candidates,
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

# Model identity and market-anchor weight come from config/model_config.yaml (single source of truth).
_MODEL_CFG = load_config().model
MODEL_VERSION_ID = _MODEL_CFG.version_id
MARKET_ANCHOR_MODEL_WEIGHT = _MODEL_CFG.market_anchor_model_weight
MONEYLINE_MODEL_WEIGHT = _MODEL_CFG.moneyline_model_weight
MONEYLINE_MAX_DISAGREEMENT = _MODEL_CFG.moneyline_max_disagreement
MONEYLINE_MAX_ODDS = _MODEL_CFG.moneyline_max_odds
MIN_REAL_GAMES_FOR_TRAINING = 120
BOXSCORE_BACKFILL_PER_CYCLE = 600


def _resolve_git_commit_sha() -> str:
    """Resolve current HEAD commit SHA without mutating repo state."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        sha = proc.stdout.strip()
        if proc.returncode == 0 and sha:
            return sha
    except Exception:
        pass
    return os.getenv("GITHUB_SHA", "unknown")


def _compute_config_hash() -> tuple[str, str]:
    """Return (sha256_hex, config_version_id) for config/model_config.yaml."""
    cfg_path = PROJECT_ROOT / "config" / "model_config.yaml"
    if cfg_path.exists():
        raw = cfg_path.read_bytes()
        return hashlib.sha256(raw).hexdigest(), str(_MODEL_CFG.version_id)
    return "missing", str(_MODEL_CFG.version_id)


def _compute_totals_line_band_telemetry(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Bucket resolved observed Totals calibration samples by observed line_value band."""
    bands: dict[str, list[dict[str, Any]]] = {
        "<=215.0": [],
        "215.5-225.0": [],
        "225.5-235.0": [],
        ">235.0": [],
    }
    for row in rows:
        lv = row.get("line_value")
        if lv is None:
            continue
        val = float(lv)
        if val <= 215.0:
            bands["<=215.0"].append(row)
        elif val <= 225.0:
            bands["215.5-225.0"].append(row)
        elif val <= 235.0:
            bands["225.5-235.0"].append(row)
        else:
            bands[">235.0"].append(row)

    out: dict[str, dict[str, Any]] = {}
    for band, grp in bands.items():
        if not grp:
            continue
        n = len(grp)
        probs = [float(r["raw_probability"]) for r in grp]
        outcomes = [int(r["outcome"]) for r in grp]
        brier = sum((p - y) ** 2 for p, y in zip(probs, outcomes, strict=False)) / n
        out[band] = {
            "sample_size": n,
            "empirical_over_rate": round(sum(outcomes) / n, 4),
            "mean_raw_prob": round(sum(probs) / n, 4),
            "brier_score": round(brier, 5),
        }
    return out


def run_incremental_cloud_cycle(mode: str = "auto", db_path: Path | str | None = None) -> dict[str, Any]:
    target_db_path = Path(db_path) if db_path is not None else (PROJECT_ROOT / "data" / "nba_intelligence.sqlite3")

    # Bootstrap database on very first run if it does not exist yet
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
    # Stake sizing, caps and EV threshold come from config/model_config.yaml (see AGENTS.md).
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

    # US Eastern Time calendar alignment: ESPN organizes scoreboard by US Eastern day.
    # Games tipping off between 00:00Z and 05:00Z on date D belong to ESPN date (D - 1 day).
    et_aligned_dates: list[str] = list(dates_to_ingest)
    for d_str in list(dates_to_ingest):
        try:
            prev_d = (datetime.strptime(d_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            if prev_d not in et_aligned_dates:
                et_aligned_dates.append(prev_d)
        except Exception:
            pass
    dates_to_ingest = sorted(et_aligned_dates)

    router = DataSourceRouter([ESPNPublicAdapter(timeout_seconds=10)])
    ingested_dates: list[str] = []
    for dt_str in dates_to_ingest:
        try:
            scout.ingest_and_validate_dataset(router, date_str=dt_str)
            ingested_dates.append(dt_str)
        except Exception as exc:
            logger.warning(f"Ingestion failed for date {dt_str}: {exc}")

    # 1b. Automatically promote latest pre-tipoff odds to closing lines for started / final games
    new_closing_lines = paper_engine.persist_closing_lines_for_games(now_str)

    # 1c. Sync live Peruvian (Te Apuesto) & Sharp (Pinnacle) pre-game observed quotes into odds_snapshots
    if mode != "settle_and_calibrate":
        try:
            peru_scraper = LivePeruOddsScraper(db=db)
            peru_scraper.scan_and_alert_entire_slate(notify_telegram=False)
        except Exception as exc:
            logger.warning(f"Live Peruvian/Pinnacle odds sync failed cleanly: {exc}")

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
        except Exception as exc:
            logger.warning(f"Failed to settle bet {pb.get('bet_id')}: {exc}")

    # 2b. Settle any PENDING player prop & SGP bets whose games are now FINAL, POSTPONED, or CANCELLED
    pending_prop_rows = db.fetch_all(
        """
        SELECT DISTINCT p.game_id
        FROM player_prop_picks p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.status = 'PENDING'
          AND g.status IN ('FINAL', 'POSTPONED', 'CANCELLED')
        """
    )
    needed_boxscore_gids = {row["game_id"] for row in pending_prop_rows}

    # Also collect game IDs from pending parlays to ensure boxscores are available
    pending_parlay_rows = db.fetch_all("SELECT legs_json FROM parlay_bets WHERE status = 'PENDING'")
    for p_row in pending_parlay_rows:
        try:
            p_legs = json.loads(p_row["legs_json"])
            for pl in p_legs:
                pgid = pl.get("game_id")
                if pgid and pgid != "CROSS_SLATE":
                    needed_boxscore_gids.add(pgid)
        except Exception:
            pass

    game_boxscores: dict[str, dict[str, dict[str, float]]] = {}
    espn_adapter = ESPNPublicAdapter(timeout_seconds=10)
    for gid in needed_boxscore_gids:
        ev_id = gid.replace("ESPN_", "").split("_")[0]
        try:
            b_stats = espn_adapter.fetch_player_boxscores(ev_id)
            if b_stats:
                game_boxscores[gid] = b_stats
        except Exception as exc:
            logger.warning(f"Failed to fetch boxscore for game {gid}: {exc}")
    paper_engine.settle_pending_player_props(game_boxscores=game_boxscores, settled_at=now_str)
    parlay_engine.settle_pending_parlays(game_boxscores=game_boxscores, settled_at=now_str)

    # 3. Auto-Calibration Step: Fit calibrators & models on all strictly prior FINAL games
    # Refresh current timestamp post-ingestion to encompass recently settled games without temporal leakage
    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 3a. Make sure real NBA history exists (one-time ESPN backfill of 2 seasons) and recompute
    #     leakage-free pre-game ratings + real rest days for every real game.
    real_final_count = (db.fetch_one(
        "SELECT COUNT(*) AS c FROM games WHERE status = 'FINAL' AND game_id NOT LIKE 'SYN%'"
    ) or {"c": 0})["c"]
    if real_final_count < MIN_REAL_GAMES_FOR_TRAINING:
        try:
            backfill_espn_history(db, date(2024, 10, 22), (now_dt - timedelta(days=1)).date())
        except Exception as exc:
            logger.error(f"Historical ESPN backfill failed: {exc}", exc_info=True)
    apply_pregame_team_ratings(db)

    all_final_games = db.fetch_all(
        "SELECT * FROM v_observed_games WHERE status = 'FINAL' AND home_score IS NOT NULL ORDER BY game_start_time ASC"
    )
    real_final_games = all_final_games
    if len(real_final_games) >= MIN_REAL_GAMES_FOR_TRAINING:
        # Never let synthetic fixtures shape real-game predictions
        all_final_games = real_final_games

    # 3b. Real box scores (possessions, Four Factors, player minutes): fetch the missing ones and attach
    #     leakage-free pre-game bx_* features to every real game (FINAL and SCHEDULED).
    try:
        bx_res = backfill_boxscores(db, limit=BOXSCORE_BACKFILL_PER_CYCLE)
        logger.info("Box score backfill: %s", bx_res)
    except Exception as exc:
        logger.warning("Box score backfill failed: %s", exc)
    bx_features = compute_boxscore_features(
        db.fetch_all("SELECT * FROM v_observed_games ORDER BY game_start_time ASC"),
        load_boxscores(db),
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

    # Fit probability calibrators on resolved predictions from the current model version,
    # augmented with strictly out-of-sample walk-forward evaluations when live sample < 50
    # One record per game (the latest pre-tip prediction): predictions are append-only, so several
    # snapshots per game exist; counting all of them would overweight games re-priced more often.
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
        FROM latest l
        JOIN games g ON l.game_id = g.game_id
        WHERE l.rn = 1
          AND g.status = 'FINAL' AND g.game_start_time < ?
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
        FROM latest l
        JOIN games g ON l.game_id = g.game_id
        WHERE l.rn = 1
          AND g.status = 'FINAL' AND g.game_start_time < ?
          AND (g.result_recorded_at IS NULL OR g.result_recorded_at <= ?)
          AND l.line_value IS NOT NULL
          AND (g.home_score + g.away_score) != l.line_value
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
        FROM latest l
        JOIN games g ON l.game_id = g.game_id
        WHERE l.rn = 1
          AND g.status = 'FINAL' AND g.game_start_time < ?
          AND (g.result_recorded_at IS NULL OR g.result_recorded_at <= ?)
          AND l.line_value IS NOT NULL
          AND ABS(g.home_score - g.away_score + l.line_value) > 1e-9
        """,
        (MODEL_VERSION_ID, now_str, now_str),
    )

    if len(resolved_ml_preds) < 50 and len(all_final_games) >= 150:
        wf_slice = [g for g in all_final_games[-65:] if str(g["game_start_time"]) < now_str]
        if wf_slice:
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
                gid_r = str(r["game_id"])
                if gid_r not in obs_wf_tot_line:
                    obs_wf_tot_line[gid_r] = float(r["line_value"])

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
                gid_r = str(r["game_id"])
                if gid_r not in obs_wf_sp_line:
                    obs_wf_sp_line[gid_r] = float(r["line_value"])

            wf_cutoff = wf_slice[0]["game_start_time"]
            wf_train = [g for g in all_final_games if str(g["game_start_time"]) < wf_cutoff]
            wf_model = EnsembleStackingModel(MODEL_VERSION_ID)
            wf_model.fit(wf_train, wf_cutoff)
            for wg in wf_slice:
                rec_ts = wg.get("result_recorded_at")
                if rec_ts and parse_iso_utc(rec_ts) > parse_iso_utc(now_str):
                    rec_ts = None
                wg_prior = [fg for fg in all_final_games if str(fg["game_start_time"]) < str(wg["game_start_time"])]
                p_ml_wf = wf_model.predict_moneyline(wg, wg_prior)["p_home"]
                resolved_ml_preds.append(
                    {
                        "raw_probability": p_ml_wf,
                        "game_start_time": wg["game_start_time"],
                        "result_recorded_at": rec_ts,
                        "outcome": 1 if wg["home_score"] > wg["away_score"] else 0,
                    }
                )
                gid_wf = str(wg["game_id"])
                tot_line_wf = obs_wf_tot_line.get(gid_wf)
                if tot_line_wf is not None and abs((float(wg["home_score"]) + float(wg["away_score"])) - tot_line_wf) > 1e-9:
                    p_tot_wf = wf_model.predict_total_points(wg, wg_prior, tot_line_wf)["p_over"]
                    resolved_tot_preds.append(
                        {
                            "raw_probability": p_tot_wf,
                            "line_value": tot_line_wf,
                            "game_start_time": wg["game_start_time"],
                            "result_recorded_at": rec_ts,
                            "outcome": 1 if (wg["home_score"] + wg["away_score"]) > tot_line_wf else 0,
                        }
                    )
                sp_line_wf = obs_wf_sp_line.get(gid_wf)
                if sp_line_wf is not None and abs((float(wg["home_score"]) - float(wg["away_score"])) + sp_line_wf) > 1e-9:
                    p_sp_wf = wf_model.predict_spread(wg, wg_prior, sp_line_wf)["p_cover_home"]
                    resolved_sp_preds.append(
                        {
                            "raw_probability": p_sp_wf,
                            "line_value": sp_line_wf,
                            "game_start_time": wg["game_start_time"],
                            "result_recorded_at": rec_ts,
                            "outcome": 1 if (wg["home_score"] - wg["away_score"] + sp_line_wf) > 0 else 0,
                        }
                    )

    ml_cal = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    tot_cal = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    sp_cal = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    ml_va = VennAbersConformalInterval(window=1200, min_samples=60)
    tot_va = VennAbersConformalInterval(window=1200, min_samples=60)
    sp_va = VennAbersConformalInterval(window=1200, min_samples=60)
    ml_method = ml_cal.fit(resolved_ml_preds, now_str) if resolved_ml_preds else "identity"
    tot_method = tot_cal.fit(resolved_tot_preds, now_str) if resolved_tot_preds else "identity"
    sp_method = sp_cal.fit(resolved_sp_preds, now_str) if resolved_sp_preds else "identity"
    if resolved_ml_preds:
        ml_va.fit(resolved_ml_preds, now_str)
    if resolved_tot_preds:
        tot_va.fit(resolved_tot_preds, now_str)
    if resolved_sp_preds:
        sp_va.fit(resolved_sp_preds, now_str)

    totals_line_bands = _compute_totals_line_band_telemetry(resolved_tot_preds)
    totals_calibration_fallback_active = bool(tot_method == "identity" or len(resolved_tot_preds) < 25)
    spread_calibration_fallback_active = bool(sp_method == "identity" or len(resolved_sp_preds) < 25)

    for mkt_cal_name, resolved_rows_cal, cal_method_val in [
        ("moneyline", resolved_ml_preds, ml_method),
        ("total_points", resolved_tot_preds, tot_method),
        ("spread", resolved_sp_preds, sp_method),
    ]:
        if not resolved_rows_cal:
            continue
        curve_m = compute_reliability_curve(
            [float(r["raw_probability"]) for r in resolved_rows_cal],
            [int(r["outcome"]) for r in resolved_rows_cal],
        )
        prefix_m = {"moneyline": "ML", "total_points": "TOT", "spread": "SP"}[mkt_cal_name]
        db.execute_insert(
            """
            INSERT INTO calibration_logs (
                eval_id, evaluated_at, model_version_id, market, sample_size,
                brier_score, log_loss, ece, calibration_method, bins_json, promoted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                f"CAL_{prefix_m}_{uuid.uuid4().hex[:8].upper()}",
                now_str,
                MODEL_VERSION_ID,
                mkt_cal_name,
                curve_m["sample_size"],
                curve_m["brier_score"],
                curve_m["log_loss"],
                curve_m["ece"],
                cal_method_val,
                json.dumps(curve_m["bins"]),
            ),
        )

    config_hash, config_version = _compute_config_hash()
    commit_sha = _resolve_git_commit_sha()
    run_manifest_id = f"RUN_{now_dt.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8].upper()}"
    submodel_versions_map = {
        "model_a": model_a.version_id,
        "model_b": model_f.model_b.version_id,
        "model_c": model_f.model_c.version_id,
        "model_d": model_f.model_d.version_id,
        "model_e": model_f.model_e.version_id,
        "model_g": model_f.model_g.version_id,
    }
    calibrator_metadata = {
        "moneyline": {
            "method": ml_method,
            "sample_size": len(resolved_ml_preds),
            "venn_abers_fitted": ml_va.is_fitted,
        },
        "total_points": {
            "method": tot_method,
            "sample_size": len(resolved_tot_preds),
            "venn_abers_fitted": tot_va.is_fitted,
            "fallback_active": totals_calibration_fallback_active,
            "line_bands": totals_line_bands,
        },
        "spread": {
            "method": sp_method,
            "sample_size": len(resolved_sp_preds),
            "venn_abers_fitted": sp_va.is_fitted,
            "fallback_active": spread_calibration_fallback_active,
        },
    }
    seeds_metadata = {
        "deep_monte_carlo": "deterministic_game_sha256",
        "block_bootstrap": 42,
        "pythonhashseed": os.getenv("PYTHONHASHSEED", "unset"),
    }
    data_cutoff_utc = str(all_final_games[-1]["game_start_time"]) if all_final_games else now_str
    db.execute_insert(
        """
        INSERT INTO run_manifests (
            run_id, commit_sha, model_version_id, ensemble_version,
            submodel_versions_json, config_hash, config_version,
            calibrator_metadata_json, seeds_json, data_cutoff_utc, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_manifest_id,
            commit_sha,
            MODEL_VERSION_ID,
            model_f.version_id,
            json.dumps(submodel_versions_map, sort_keys=True),
            config_hash,
            config_version,
            json.dumps(calibrator_metadata, sort_keys=True),
            json.dumps(seeds_metadata, sort_keys=True),
            data_cutoff_utc,
            f"mode={mode};totals_fallback={totals_calibration_fallback_active}",
            now_str,
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
            g = {**g, **bx_features.get(g["game_id"], {})}
            existing_bet = db.fetch_one("SELECT bet_id FROM simulated_bets WHERE game_id = ?", (g["game_id"],))
            if existing_bet:
                continue
            # Betting decisions may ONLY use quotes observed in a real market (never quarantined,
            # derived or system-generated prices).
            raw_game_odds = db.fetch_all(
                """
                SELECT * FROM v_observed_odds_snapshots
                WHERE game_id = ? AND is_closing_line = 0 AND market IN ('moneyline', 'total_points', 'spread')
                ORDER BY datetime(captured_at) ASC, captured_at ASC
                """,
                (g["game_id"],),
            )
            if not raw_game_odds:
                continue
            raw_game_odds.sort(key=lambda r: parse_iso_utc(str(r["captured_at"])))

            start_dt = parse_iso_utc(g["game_start_time"])
            avail_dt = parse_iso_utc(g["features_available_at"])

            # Keep only the freshest pre-tipoff quote per (provider, market, canonical_line_key, selection),
            # then keep ALL complete two-sided pre-tip pairs per (provider, market, canonical_line_key):
            # HOME+AWAY for moneyline, OVER+UNDER at the exact same line_value for total_points,
            # and HOME+AWAY for spread matched by canonical home spread line (HOME line = -AWAY line).
            latest_by_key: dict[tuple[str, str, float | None, str], tuple[datetime, dict[str, Any]]] = {}
            for o in raw_game_odds:
                try:
                    cap_dt = parse_iso_utc(str(o["captured_at"]))
                    dec_val = float(o.get("decimal_odds") or 0.0)
                except Exception:
                    continue
                if cap_dt >= start_dt or dec_val <= 1.0:
                    continue
                mkt_str = str(o["market"])
                sel_u = str(o["selection"]).upper()
                raw_lv = o.get("line_value")
                lv_key: float | None
                if mkt_str == "moneyline":
                    if raw_lv is not None or sel_u not in ("HOME", "AWAY"):
                        continue
                    lv_key = None
                elif mkt_str == "total_points":
                    if raw_lv is None or sel_u not in ("OVER", "UNDER"):
                        continue
                    lv_key = round(float(raw_lv), 2)
                    if lv_key <= 50.0:
                        continue
                elif mkt_str == "spread":
                    if raw_lv is None or sel_u not in ("HOME", "AWAY") or abs(float(raw_lv)) > 45.0:
                        continue
                    lv_key = round(float(raw_lv) if sel_u == "HOME" else -float(raw_lv), 2)
                else:
                    continue
                key_t = (str(o["provider"]), mkt_str, lv_key, sel_u)
                prev = latest_by_key.get(key_t)
                if prev is None or cap_dt >= prev[0]:
                    latest_by_key[key_t] = (cap_dt, o)

            sides_by_market = {
                "moneyline": ("HOME", "AWAY"),
                "total_points": ("OVER", "UNDER"),
                "spread": ("HOME", "AWAY"),
            }
            all_valid_provider_pairs: list[dict[str, Any]] = []
            for mkt_name, (side_a, side_b) in sides_by_market.items():
                prov_lines = sorted({(k[0], k[2]) for k in latest_by_key if k[1] == mkt_name})
                for prov, lv_key in prov_lines:
                    entry_a = latest_by_key.get((prov, mkt_name, lv_key, side_a))
                    entry_b = latest_by_key.get((prov, mkt_name, lv_key, side_b))
                    if not entry_a or not entry_b:
                        continue
                    row_a = entry_a[1]
                    row_b = entry_b[1]
                    pair_a = {**row_a, "counterpart_decimal_odds": float(row_b["decimal_odds"])}
                    pair_b = {**row_b, "counterpart_decimal_odds": float(row_a["decimal_odds"])}
                    all_valid_provider_pairs.extend([pair_a, pair_b])

            game_odds = all_valid_provider_pairs
            if not game_odds:
                continue

            latest_odds_dt = max(parse_iso_utc(str(o["captured_at"])) for o in game_odds)
            existing_preds = db.fetch_all(
                "SELECT odds_captured_at FROM predictions WHERE game_id = ? AND model_version_id = ? AND odds_captured_at IS NOT NULL",
                (g["game_id"], MODEL_VERSION_ID),
            )
            if existing_preds:
                max_pred_dt = max(parse_iso_utc(str(r["odds_captured_at"])) for r in existing_preds)
                if max_pred_dt >= latest_odds_dt:
                    continue

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

            tot_odds = [o for o in game_odds if o["market"] == "total_points" and o.get("line_value") is not None]
            tot_preds_by_line: dict[float, dict[str, Any]] = {}
            for tot_row in tot_odds:
                lv_key = round(float(tot_row["line_value"]), 2)
                if lv_key not in tot_preds_by_line:
                    pred_tot_lv = model_f.predict_total_points(g, all_final_games, lv_key)
                    p_push_tot = float(pred_tot_lv.get("p_push", 0.0))
                    non_push_tot = max(1e-9, 1.0 - p_push_tot)
                    raw_over_lv = float(pred_tot_lv["p_over"])
                    cond_raw_over = (
                        min(1.0, max(0.0, raw_over_lv / non_push_tot))
                        if p_push_tot > 0.0
                        else raw_over_lv
                    )
                    cal_cond_over = tot_cal.transform_single(cond_raw_over)
                    cal_over_lv = round(non_push_tot * cal_cond_over, 6)
                    va_raw = tot_va.predict_interval(cond_raw_over)
                    va_over_lv = {
                        **va_raw,
                        "p0": round(non_push_tot * float(va_raw["p0"]), 6),
                        "p1": round(non_push_tot * float(va_raw["p1"]), 6),
                        "p_va": round(non_push_tot * float(va_raw["p_va"]), 6),
                        "width": round(non_push_tot * float(va_raw["width"]), 6),
                    }
                    tot_preds_by_line[lv_key] = {
                        "pred_f_tot": pred_tot_lv,
                        "raw_p_over": raw_over_lv,
                        "raw_p_under": float(pred_tot_lv["p_under"]),
                        "cal_p_over": cal_over_lv,
                        "cal_p_under": round(max(0.0, non_push_tot - cal_over_lv), 6),
                        "p_push": p_push_tot,
                        "va_over_int": va_over_lv,
                    }

            sp_odds = [o for o in game_odds if o["market"] == "spread" and o.get("line_value") is not None]
            sp_preds_by_line: dict[float, dict[str, Any]] = {}
            for sp_row in sp_odds:
                sel_sp = str(sp_row["selection"]).upper()
                canon_home_sp = round(
                    float(sp_row["line_value"]) if sel_sp == "HOME" else -float(sp_row["line_value"]),
                    2,
                )
                if canon_home_sp not in sp_preds_by_line:
                    pred_sp_lv = model_f.predict_spread(g, all_final_games, canon_home_sp)
                    p_push_sp = float(pred_sp_lv.get("p_push", 0.0))
                    non_push_sp = max(1e-9, 1.0 - p_push_sp)
                    raw_cover_home = float(pred_sp_lv["p_cover_home"])
                    cond_raw_sp = (
                        min(1.0, max(0.0, raw_cover_home / non_push_sp))
                        if p_push_sp > 0.0
                        else raw_cover_home
                    )
                    cal_cond_sp = sp_cal.transform_single(cond_raw_sp)
                    cal_cover_home = round(non_push_sp * cal_cond_sp, 6)
                    va_raw_sp = sp_va.predict_interval(cond_raw_sp)
                    va_sp_lv = {
                        **va_raw_sp,
                        "p0": round(non_push_sp * float(va_raw_sp["p0"]), 6),
                        "p1": round(non_push_sp * float(va_raw_sp["p1"]), 6),
                        "p_va": round(non_push_sp * float(va_raw_sp["p_va"]), 6),
                        "width": round(non_push_sp * float(va_raw_sp["width"]), 6),
                    }
                    sp_preds_by_line[canon_home_sp] = {
                        "pred_f_sp": pred_sp_lv,
                        "raw_p_home": raw_cover_home,
                        "raw_p_away": float(pred_sp_lv["p_cover_away"]),
                        "cal_p_home": cal_cover_home,
                        "cal_p_away": round(max(0.0, non_push_sp - cal_cover_home), 6),
                        "p_push": p_push_sp,
                        "va_sp_int": va_sp_lv,
                    }

            if tot_odds:
                # Choose target_total_line for baseline feature diagnostics: prefer Pinnacle/sharp line or best bookmaker coverage
                line_scores: dict[float, tuple[int, int, datetime]] = {}
                for tot_row in tot_odds:
                    lv_k = round(float(tot_row["line_value"]), 2)
                    is_sharp = 1 if "pinnacle" in str(tot_row.get("provider", "")).lower() else 0
                    cap_k_dt = parse_iso_utc(str(tot_row.get("captured_at") or "1970-01-01T00:00:00Z"))
                    prev_score = line_scores.get(lv_k)
                    if prev_score is None:
                        line_scores[lv_k] = (is_sharp, 1, cap_k_dt)
                    else:
                        line_scores[lv_k] = (
                            max(prev_score[0], is_sharp),
                            prev_score[1] + 1,
                            max(prev_score[2], cap_k_dt),
                        )
                target_total_line = max(line_scores.keys(), key=lambda k: line_scores[k])
                base_tot_eval = tot_preds_by_line[target_total_line]
                pred_f_tot = base_tot_eval["pred_f_tot"]
                va_over_int_default = base_tot_eval["va_over_int"]
            else:
                hist_totals = [
                    float(fg["home_score"]) + float(fg["away_score"])
                    for fg in all_final_games
                    if fg.get("home_score") is not None and fg.get("away_score") is not None
                ]
                structural_fallback = feats.get("structural_total")
                if structural_fallback is not None:
                    target_total_line = round(float(structural_fallback) * 2.0) / 2.0
                    pred_f_tot = model_f.predict_total_points(g, all_final_games, target_total_line)
                    va_over_int_default = tot_va.predict_interval(pred_f_tot["p_over"])
                elif hist_totals:
                    target_total_line = round((sum(hist_totals) / len(hist_totals)) * 2.0) / 2.0
                    pred_f_tot = model_f.predict_total_points(g, all_final_games, target_total_line)
                    va_over_int_default = tot_va.predict_interval(pred_f_tot["p_over"])
                else:
                    pred_f_tot = {"overtime_prob": 0.05, "blowout_prob": 0.12}
                    va_over_int_default = va_home_int

            feats["mc_overtime_prob"] = pred_f_tot.get("overtime_prob", 0.05)
            feats["mc_blowout_prob"] = pred_f_tot.get("blowout_prob", 0.12)
            feats["mc_simulation_q10_total"] = pred_f_tot.get("simulation_q10_total", 205.0)
            feats["mc_simulation_q90_total"] = pred_f_tot.get("simulation_q90_total", 250.0)
            feats["va_conformal_home_width"] = va_home_int["width"]
            feats["va_conformal_over_width"] = va_over_int_default["width"]

            consensus_map = compute_market_consensus(all_valid_provider_pairs)
            steam_map = compute_line_steam(raw_game_odds)
            game_opps: list[dict[str, Any]] = []
            pred_meta_by_quote: dict[tuple[str, str, str, float | None, str], tuple[str, str, float, float, dict[str, Any]]] = {}

            for o in game_odds:
                validate_odds_record(o, g["game_start_time"], simulated_prediction_time=pred_ts)
                mkt = str(o["market"])
                sel = str(o["selection"]).upper()
                line_v = o.get("line_value")
                cons_entry = consensus_map.get((mkt, sel, line_v))
                if cons_entry is None and line_v is not None:
                    cons_entry = consensus_map.get((mkt, sel, round(float(line_v), 2)))
                cons_p = cons_entry["p_market"] if cons_entry else None
                steam_entry = steam_map.get((mkt, sel))
                s_delta = float(steam_entry["steam_delta"]) if steam_entry else 0.0

                p_push_val = 0.0
                if mkt == "moneyline":
                    raw_p = raw_p_home if sel == "HOME" else round(1.0 - raw_p_home, 6)
                    cal_p = cal_p_home if sel == "HOME" else round(1.0 - cal_p_home, 6)
                    unc = pred_f_ml["uncertainty_std"]
                    m_ver = model_f.version_id
                    row_tot_pred = pred_f_tot
                    row_feats = feats
                    if sel == "HOME":
                        conf_int = va_home_int
                    else:
                        conf_int = {
                            "p0": round(1.0 - va_home_int["p1"], 6),
                            "p1": round(1.0 - va_home_int["p0"], 6),
                            "p_va": round(1.0 - va_home_int["p_va"], 6),
                            "width": va_home_int["width"],
                            "is_fitted": va_home_int.get("is_fitted", False),
                            "is_conformal": va_home_int.get("is_conformal", False),
                        }
                elif mkt == "spread":
                    canon_home_sp = round(
                        float(line_v) if sel == "HOME" else -float(line_v),  # type: ignore[arg-type]
                        2,
                    )
                    sp_eval_row = sp_preds_by_line[canon_home_sp]
                    row_sp_pred = sp_eval_row["pred_f_sp"]
                    p_push_val = float(sp_eval_row["p_push"])
                    non_push_val = max(1e-9, 1.0 - p_push_val)
                    raw_p = sp_eval_row["raw_p_home"] if sel == "HOME" else sp_eval_row["raw_p_away"]
                    cal_p = sp_eval_row["cal_p_home"] if sel == "HOME" else sp_eval_row["cal_p_away"]
                    unc = row_sp_pred["uncertainty_std"]
                    m_ver = model_f.version_id
                    row_tot_pred = pred_f_tot
                    va_sp_row = sp_eval_row["va_sp_int"]
                    row_feats = {**feats, "va_conformal_spread_width": va_sp_row["width"], "spread_line_home": canon_home_sp}
                    if sel == "HOME":
                        conf_int = va_sp_row
                    else:
                        conf_int = {
                            "p0": round(max(0.0, non_push_val - float(va_sp_row["p1"])), 6),
                            "p1": round(max(0.0, non_push_val - float(va_sp_row["p0"])), 6),
                            "p_va": round(max(0.0, non_push_val - float(va_sp_row["p_va"])), 6),
                            "width": va_sp_row["width"],
                            "is_fitted": va_sp_row.get("is_fitted", False),
                            "is_conformal": va_sp_row.get("is_conformal", False),
                        }
                else:
                    lv_exact = round(float(line_v), 2)  # type: ignore[arg-type]
                    tot_eval_row = tot_preds_by_line[lv_exact]
                    row_tot_pred = tot_eval_row["pred_f_tot"]
                    p_push_val = float(tot_eval_row["p_push"])
                    non_push_val = max(1e-9, 1.0 - p_push_val)
                    raw_p = tot_eval_row["raw_p_over"] if sel == "OVER" else tot_eval_row["raw_p_under"]
                    cal_p = tot_eval_row["cal_p_over"] if sel == "OVER" else tot_eval_row["cal_p_under"]
                    unc = row_tot_pred["uncertainty_std"]
                    m_ver = model_f.version_id
                    va_over_int_row = tot_eval_row["va_over_int"]
                    row_feats = {**feats, "va_conformal_over_width": va_over_int_row["width"]}
                    if sel == "OVER":
                        conf_int = va_over_int_row
                    else:
                        conf_int = {
                            "p0": round(max(0.0, non_push_val - float(va_over_int_row["p1"])), 6),
                            "p1": round(max(0.0, non_push_val - float(va_over_int_row["p0"])), 6),
                            "p_va": round(max(0.0, non_push_val - float(va_over_int_row["p_va"])), 6),
                            "width": va_over_int_row["width"],
                            "is_fitted": va_over_int_row.get("is_fitted", False),
                            "is_conformal": va_over_int_row.get("is_conformal", False),
                        }

                eff_model_weight = (
                    MONEYLINE_MODEL_WEIGHT
                    if (mkt == "moneyline" and MONEYLINE_MODEL_WEIGHT is not None)
                    else MARKET_ANCHOR_MODEL_WEIGHT
                )
                eff_max_disagreement = (
                    MONEYLINE_MAX_DISAGREEMENT
                    if (mkt == "moneyline" and MONEYLINE_MAX_DISAGREEMENT is not None)
                    else MAX_MODEL_MARKET_DISAGREEMENT
                )
                opp = evaluate_market_opportunity(
                    estimated_prob=cal_p,
                    uncertainty_std=unc,
                    odds_record=o,
                    game_start_time=g["game_start_time"],
                    model_version_id=m_ver,
                    simulated_prediction_time=pred_ts,
                    market_consensus_prob=cons_p,
                    model_weight=eff_model_weight,
                    max_disagreement=eff_max_disagreement,
                    steam_delta=s_delta,
                    conformal_interval=conf_int,
                    p_push=p_push_val,
                    raw_model_prob=raw_p,
                )
                pred_id = f"PRED_{m_ver}_{o['odds_id']}"
                opp["prediction_id"] = pred_id
                opp["raw_probability"] = raw_p
                opp["calibrated_probability"] = opp["estimated_probability"]
                opp["run_manifest_id"] = run_manifest_id
                opp["uncertainty_std"] = unc
                opp["overtime_prob"] = row_tot_pred.get("overtime_prob", 0.05)
                opp["blowout_prob"] = row_tot_pred.get("blowout_prob", 0.12)
                opp["emitted_at"] = pred_ts
                if mkt == "moneyline" and MONEYLINE_MAX_ODDS is not None:
                    opp["moneyline_max_odds"] = MONEYLINE_MAX_ODDS

                quote_key = (
                    str(opp["odds_provider"]),
                    str(mkt),
                    str(sel),
                    round(float(line_v), 2) if line_v is not None else None,
                    str(opp["odds_captured_at"]),
                )
                pred_meta_by_quote[quote_key] = (pred_id, m_ver, raw_p, unc, row_feats)
                game_opps.append(opp)

            # Cross-book line shopping: persist & submit only the best accessible quote per contract
            best_game_opps = select_best_line_shopping_candidates(game_opps)
            for opp in best_game_opps:
                lv_raw = opp.get("line_value")
                quote_key = (
                    str(opp["odds_provider"]),
                    str(opp["market"]),
                    str(opp["selection"]),
                    round(float(lv_raw), 2) if lv_raw is not None else None,
                    str(opp["odds_captured_at"]),
                )
                pred_id, m_ver, raw_p, unc, row_feats = pred_meta_by_quote[quote_key]
                snapshot_feats = {
                    **row_feats,
                    "line_shop_books": opp.get("line_shop_books", 1),
                    "line_shop_gain_pct": opp.get("line_shop_gain_pct", 0.0),
                    "runner_up_provider": opp.get("runner_up_provider"),
                }
                db.execute_insert(
                    """
                    INSERT OR IGNORE INTO predictions (
                        prediction_id, game_id, market, selection, line_value,
                        model_version_id, raw_probability, calibrated_probability,
                        raw_model_probability, calibrated_model_probability,
                        market_fair_probability, market_anchored_probability,
                        run_manifest_id, uncertainty_std, implied_prob_gross, implied_prob_fair,
                        bookmaker_overround, decimal_odds_used, odds_provider,
                        odds_captured_at, ev_unit, ev_pct, emitted_at, features_snapshot_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pred_id, g["game_id"], opp["market"], opp["selection"], lv_raw,
                        m_ver, raw_p, opp["estimated_probability"],
                        opp["raw_model_probability"], opp["calibrated_model_probability"],
                        opp["market_fair_probability"], opp["market_anchored_probability"],
                        run_manifest_id, unc, opp["implied_prob_gross"],
                        opp["implied_prob_fair"], opp["bookmaker_overround"],
                        opp["decimal_odds_used"], opp["odds_provider"], opp["odds_captured_at"],
                        opp["ev_unit"], opp["ev_pct"], pred_ts, json.dumps(snapshot_feats),
                    ),
                )
                candidates_by_matchday[g["matchday_date"]].append(opp)

        for m_date in sorted(candidates_by_matchday.keys()):
            day_res = paper_engine.evaluate_and_record_matchday_selections(m_date, candidates_by_matchday[m_date])
            new_bets_placed += len(day_res["placed_bets"])

    # 5. Recompute metrics, audit, and refresh reports + Obsidian
    bt = WalkForwardBacktester(db, paper_engine)
    metrics = bt.compute_comprehensive_metrics(model_comparison_records=[])
    metrics["run_manifest"] = {
        "run_id": run_manifest_id,
        "commit_sha": commit_sha,
        "model_version_id": MODEL_VERSION_ID,
        "ensemble_version": model_f.version_id,
        "submodel_versions": submodel_versions_map,
        "config_hash": config_hash,
        "config_version": config_version,
        "data_cutoff_utc": data_cutoff_utc,
        "calibrators": calibrator_metadata,
    }
    audit_res = auditor.run_independent_audit(metrics)
    promo_eval = calibrator_agent.evaluate_calibration_and_promotion(metrics)
    sources_info = scout.investigate_sources()
    vis_info = visual.inspect_and_extract_context()

    env_status = {
        "python_version": "CPython 3.12 (uv cloud/local runner)",
        "model_version_id": MODEL_VERSION_ID,
        "run_manifest_id": run_manifest_id,
        "commit_sha": commit_sha,
        "config_hash": config_hash,
        "sportradar_status": sources_info["sportradar_api"]["status"],
        "nba_stats_status": sources_info["nba_com_stats"]["direct_http_status"],
        "playwright_status": sources_info["playwright"]["status"],
        "pixelrag_status": vis_info["pixelrag_status"],
        "obsidian_vault_path": str(PROJECT_ROOT / "NBA"),
    }

    # 4b. Fail-closed Player Props & Parlays check (only execute placement when enabled in config/model_config.yaml)
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
                WHERE status = 'SCHEDULED'
                  AND game_start_time > ?
                  AND game_id NOT LIKE 'SYN%'
                ORDER BY game_start_time ASC
                LIMIT 15
                """,
                (now_str,),
            )
            slate_props = props_engine.generate_slate_prop_opportunities(
                slate_games=slate_records,
                bankroll_pen=paper_engine.get_bankroll_state()["settled_bankroll_pen"],
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
        "run_manifest_id": run_manifest_id,
        "run_manifest": metrics["run_manifest"],
        "ingested_dates": ingested_dates,
        "closing_lines_promoted": new_closing_lines,
        "bets_settled_in_cycle": len(settled_now),
        "new_bets_placed_in_cycle": new_bets_placed,
        "predictions_generated": sum(len(v) for v in candidates_by_matchday.values()),
        "active_calibration_methods": {
            "moneyline": ml_method,
            "total_points": tot_method,
            "spread": sp_method,
        },
        "totals_calibration_diagnostics": {
            "sample_size": len(resolved_tot_preds),
            "fallback_active": totals_calibration_fallback_active,
            "line_bands": totals_line_bands,
        },
        "props_parlays_status": props_parlays_status,
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
            "by_market": metrics.get("by_market"),
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
