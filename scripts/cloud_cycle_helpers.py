"""
Modular helpers extracted from `scripts/run_cloud_cycle.py` to keep the stateful
cloud orchestrator concise, testable, and free of oversized monolith functions.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Any

from scripts.cloud_cycle_calibration import (
    _pair_valid_pretip_quotes,
    build_walk_forward_oos_comparisons_for_active_model,
    compute_totals_line_band_telemetry,
    fit_and_log_cycle_calibrators,
)
from src.config import load_config
from src.calibration.calibrator import (
    ProbabilityCalibrator,
    VennAbersConformalInterval,
    calibrate_binary_with_push,
)
from src.features.builder import build_pregame_features
from src.ingestion.adapters import ESPNPublicAdapter
from src.models.statistical_models import EnsembleStackingModel
from src.paper_trading.shadow_ledger import settle_pending_shadow_candidates
from src.prediction.ev_calculator import (
    MAX_MODEL_MARKET_DISAGREEMENT,
    compute_line_steam,
    compute_market_consensus,
    evaluate_scheduled_market_opportunity,
    select_best_line_shopping_candidates,
)
from src.storage.state_live import LIVE_SOURCE_OF_TRUTH
from src.validation.validator import parse_iso_utc, validate_game_record, validate_odds_record

logger = logging.getLogger(__name__)

__all__ = [
    "_pair_valid_pretip_quotes",
    "build_walk_forward_oos_comparisons_for_active_model",
    "compute_config_hash",
    "compute_totals_line_band_telemetry",
    "determine_database_role",
    "evaluate_scheduled_slate_candidates",
    "fit_and_log_cycle_calibrators",
    "resolve_git_commit_sha",
    "settle_cycle_pending_positions",
]


def resolve_git_commit_sha(project_root: Path) -> str:
    """Resolve current HEAD commit SHA without mutating repo state."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_root),
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


def compute_config_hash(project_root: Path, model_version_id: str) -> tuple[str, str]:
    """Return `(sha256_hex, config_version_id)` for `config/model_config.yaml`."""
    cfg_path = project_root / "config" / "model_config.yaml"
    if cfg_path.exists():
        raw = cfg_path.read_bytes()
        return hashlib.sha256(raw).hexdigest(), str(model_version_id)
    return "missing", str(model_version_id)


def determine_database_role(
    project_root: Path,
    target_db_path: Path,
    *,
    explicit_db_path: bool,
) -> dict[str, str]:
    """Documents the provenance/role of the active SQLite database vs frozen CI baseline on `main`."""
    default_repo_db = (project_root / "data" / "nba_intelligence.sqlite3").resolve()
    resolved_target = target_db_path.resolve()
    in_cloud_live = bool(os.getenv("STATE_BASE_SHA")) or (
        os.getenv("GITHUB_ACTIONS") == "true" and resolved_target == default_repo_db
    )
    if in_cloud_live:
        role = "PRODUCTION_STATE_LIVE"
    elif explicit_db_path:
        role = "EXPLICIT_RUNTIME_DB"
    else:
        role = "LOCAL_DEFAULT_DB"
    return {
        "active_role": role,
        "db_path": str(target_db_path),
        "live_source_of_truth": LIVE_SOURCE_OF_TRUTH,
        "main_branch_db_policy": "FROZEN_CI_BASELINE",
    }


def settle_cycle_pending_positions(
    db: Any,
    paper_engine: Any,
    parlay_engine: Any,
    now_str: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Settles pending main simulated bets, player props, parlays, and shadow candidates
    against finalized game results and ESPN player boxscores.
    """
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
    pending_parlay_rows = db.fetch_all("SELECT legs_json FROM parlay_bets WHERE status = 'PENDING'")
    for p_row in pending_parlay_rows:
        try:
            for pl in json.loads(p_row["legs_json"]):
                pgid = pl.get("game_id")
                if pgid and pgid != "CROSS_SLATE":
                    needed_boxscore_gids.add(pgid)
        except Exception:
            pass

    game_boxscores: dict[str, dict[str, dict[str, float]]] = {}
    if needed_boxscore_gids:
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
    shadow_settled = settle_pending_shadow_candidates(db, settled_at=now_str)
    return settled_now, shadow_settled


def evaluate_scheduled_slate_candidates(
    db: Any,
    *,
    all_final_games: list[dict[str, Any]],
    bx_features: dict[str, dict[str, Any]],
    model_f: EnsembleStackingModel,
    model_version_id: str,
    cal_bundle: dict[str, Any],
    market_anchor_weight: float,
    moneyline_weight: float | None,
    moneyline_max_disagreement: float | None,
    moneyline_max_odds: float | None,
    now_str: str,
) -> dict[str, list[dict[str, Any]]]:
    """Evaluates pre-game SCHEDULED opportunities, performs cross-book line shopping, and persists predictions."""
    ml_cal: ProbabilityCalibrator = cal_bundle["ml_cal"]
    tot_cal: ProbabilityCalibrator = cal_bundle["tot_cal"]
    sp_cal: ProbabilityCalibrator = cal_bundle["sp_cal"]
    ml_va: VennAbersConformalInterval = cal_bundle["ml_va"]
    tot_va: VennAbersConformalInterval = cal_bundle["tot_va"]
    sp_va: VennAbersConformalInterval = cal_bundle["sp_va"]
    run_manifest_id: str = cal_bundle["run_manifest_id"]

    candidates_by_matchday: dict[str, list[dict[str, Any]]] = defaultdict(list)
    cfg_full = load_config()
    execution_cfg = cfg_full.execution
    anchor_schedule = cfg_full.model.anchor_schedule
    decision_dt = parse_iso_utc(now_str)
    decision_ts = decision_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    scheduled_games = db.fetch_all(
        "SELECT * FROM games WHERE status = 'SCHEDULED' AND game_start_time > ? ORDER BY game_start_time ASC",
        (now_str,),
    )
    for g in scheduled_games:
        g = {**g, **bx_features.get(g["game_id"], {})}
        if db.fetch_one("SELECT bet_id FROM simulated_bets WHERE game_id = ?", (g["game_id"],)):
            continue
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
        # The decision is made now: its timestamp is the wall clock, never a time in the future.
        if decision_dt >= start_dt:
            continue
        hours_to_tipoff = max(0.0, (start_dt - decision_dt).total_seconds() / 3600.0)
        game_odds = _pair_valid_pretip_quotes(
            raw_game_odds,
            start_dt,
            decision_dt=decision_dt,
            max_quote_age_hours=execution_cfg.max_quote_age_hours,
            excluded_provider_markers=execution_cfg.excluded_provider_markers,
            max_overround=execution_cfg.max_bookmaker_overround,
        )
        if not game_odds:
            continue

        latest_odds_dt = max(parse_iso_utc(str(o["captured_at"])) for o in game_odds)
        existing_preds = db.fetch_all(
            "SELECT odds_captured_at FROM predictions WHERE game_id = ? AND model_version_id = ? AND odds_captured_at IS NOT NULL",
            (g["game_id"], model_version_id),
        )
        if existing_preds and max(parse_iso_utc(str(r["odds_captured_at"])) for r in existing_preds) >= latest_odds_dt:
            continue

        # Pre-game features of an upcoming game are computed now from finished games only. Rows stored
        # with the legacy "tip-off − 2 h" availability (a time in the future) are clamped to the decision
        # time, so the audit trail records when the decision was really taken.
        if avail_dt > decision_dt:
            g = {**g, "features_available_at": decision_ts}
        pred_ts = decision_ts
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
                cal_tot_res = calibrate_binary_with_push(
                    float(pred_tot_lv["p_over"]), p_push=p_push_tot, calibrator=tot_cal, va_calibrator=tot_va,
                )
                cal_over_lv = round(float(cal_tot_res["cal_prob"]), 6)
                tot_preds_by_line[lv_key] = {
                    "pred_f_tot": pred_tot_lv,
                    "raw_p_over": float(pred_tot_lv["p_over"]),
                    "raw_p_under": float(pred_tot_lv["p_under"]),
                    "cal_p_over": cal_over_lv,
                    "cal_p_under": round(max(0.0, float(cal_tot_res["non_push"]) - cal_over_lv), 6),
                    "p_push": p_push_tot,
                    "va_over_int": cal_tot_res["va_interval"],
                }

        sp_odds = [o for o in game_odds if o["market"] == "spread" and o.get("line_value") is not None]
        sp_preds_by_line: dict[float, dict[str, Any]] = {}
        for sp_row in sp_odds:
            sel_sp = str(sp_row["selection"]).upper()
            canon_home_sp = round(float(sp_row["line_value"]) if sel_sp == "HOME" else -float(sp_row["line_value"]), 2)
            if canon_home_sp not in sp_preds_by_line:
                pred_sp_lv = model_f.predict_spread(g, all_final_games, canon_home_sp)
                p_push_sp = float(pred_sp_lv.get("p_push", 0.0))
                cal_sp_res = calibrate_binary_with_push(
                    float(pred_sp_lv["p_cover_home"]), p_push=p_push_sp, calibrator=sp_cal, va_calibrator=sp_va,
                )
                cal_cover_home = round(float(cal_sp_res["cal_prob"]), 6)
                sp_preds_by_line[canon_home_sp] = {
                    "pred_f_sp": pred_sp_lv,
                    "raw_p_home": float(pred_sp_lv["p_cover_home"]),
                    "raw_p_away": float(pred_sp_lv["p_cover_away"]),
                    "cal_p_home": cal_cover_home,
                    "cal_p_away": round(max(0.0, float(cal_sp_res["non_push"]) - cal_cover_home), 6),
                    "p_push": p_push_sp,
                    "va_sp_int": cal_sp_res["va_interval"],
                }

        if tot_odds:
            line_scores: dict[float, tuple[int, int, datetime]] = {}
            for tot_row in tot_odds:
                lv_k = round(float(tot_row["line_value"]), 2)
                is_sharp = 1 if "pinnacle" in str(tot_row.get("provider", "")).lower() else 0
                cap_k_dt = parse_iso_utc(str(tot_row.get("captured_at") or "1970-01-01T00:00:00Z"))
                prev_score = line_scores.get(lv_k)
                line_scores[lv_k] = (
                    (is_sharp, 1, cap_k_dt)
                    if prev_score is None
                    else (max(prev_score[0], is_sharp), prev_score[1] + 1, max(prev_score[2], cap_k_dt))
                )
            base_tot_eval = tot_preds_by_line[max(line_scores.keys(), key=lambda k: line_scores[k])]
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
                fallback_line = round(float(structural_fallback) * 2.0) / 2.0
            elif hist_totals:
                fallback_line = round((sum(hist_totals) / len(hist_totals)) * 2.0) / 2.0
            else:
                fallback_line = None
            if fallback_line is not None:
                pred_f_tot = model_f.predict_total_points(g, all_final_games, fallback_line)
                va_over_int_default = calibrate_binary_with_push(
                    float(pred_f_tot["p_over"]),
                    p_push=float(pred_f_tot.get("p_push", 0.0)),
                    calibrator=tot_cal,
                    va_calibrator=tot_va,
                )["va_interval"]
            else:
                pred_f_tot = {"overtime_prob": 0.05, "blowout_prob": 0.12}
                va_over_int_default = va_home_int

        feats["mc_overtime_prob"] = pred_f_tot.get("overtime_prob", 0.05)
        feats["mc_blowout_prob"] = pred_f_tot.get("blowout_prob", 0.12)
        feats["mc_simulation_q10_total"] = pred_f_tot.get("simulation_q10_total", 205.0)
        feats["mc_simulation_q90_total"] = pred_f_tot.get("simulation_q90_total", 250.0)
        feats["va_conformal_home_width"] = va_home_int["width"]
        feats["va_conformal_over_width"] = va_over_int_default["width"]

        consensus_map = compute_market_consensus(game_odds)
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
                row_tot_pred = pred_f_tot
                row_feats = feats
                conf_int = (
                    va_home_int
                    if sel == "HOME"
                    else {
                        "p0": round(1.0 - va_home_int["p1"], 6),
                        "p1": round(1.0 - va_home_int["p0"], 6),
                        "p_va": round(1.0 - va_home_int["p_va"], 6),
                        "width": va_home_int["width"],
                        "is_fitted": va_home_int.get("is_fitted", False),
                        "is_conformal": va_home_int.get("is_conformal", False),
                    }
                )
            elif mkt == "spread":
                canon_home_sp = round(float(line_v) if sel == "HOME" else -float(line_v), 2)  # type: ignore[arg-type]
                sp_eval_row = sp_preds_by_line[canon_home_sp]
                p_push_val = float(sp_eval_row["p_push"])
                non_push_val = max(1e-9, 1.0 - p_push_val)
                raw_p = sp_eval_row["raw_p_home"] if sel == "HOME" else sp_eval_row["raw_p_away"]
                cal_p = sp_eval_row["cal_p_home"] if sel == "HOME" else sp_eval_row["cal_p_away"]
                unc = sp_eval_row["pred_f_sp"]["uncertainty_std"]
                row_tot_pred = pred_f_tot
                va_sp_row = sp_eval_row["va_sp_int"]
                row_feats = {**feats, "va_conformal_spread_width": va_sp_row["width"], "spread_line_home": canon_home_sp}
                conf_int = (
                    va_sp_row
                    if sel == "HOME"
                    else {
                        "p0": round(max(0.0, non_push_val - float(va_sp_row["p1"])), 6),
                        "p1": round(max(0.0, non_push_val - float(va_sp_row["p0"])), 6),
                        "p_va": round(max(0.0, non_push_val - float(va_sp_row["p_va"])), 6),
                        "width": va_sp_row["width"],
                        "is_fitted": va_sp_row.get("is_fitted", False),
                        "is_conformal": va_sp_row.get("is_conformal", False),
                    }
                )
            else:
                tot_eval_row = tot_preds_by_line[round(float(line_v), 2)]  # type: ignore[arg-type]
                row_tot_pred = tot_eval_row["pred_f_tot"]
                p_push_val = float(tot_eval_row["p_push"])
                non_push_val = max(1e-9, 1.0 - p_push_val)
                raw_p = tot_eval_row["raw_p_over"] if sel == "OVER" else tot_eval_row["raw_p_under"]
                cal_p = tot_eval_row["cal_p_over"] if sel == "OVER" else tot_eval_row["cal_p_under"]
                unc = row_tot_pred["uncertainty_std"]
                va_over_row = tot_eval_row["va_over_int"]
                row_feats = {**feats, "va_conformal_over_width": va_over_row["width"]}
                conf_int = (
                    va_over_row
                    if sel == "OVER"
                    else {
                        "p0": round(max(0.0, non_push_val - float(va_over_row["p1"])), 6),
                        "p1": round(max(0.0, non_push_val - float(va_over_row["p0"])), 6),
                        "p_va": round(max(0.0, non_push_val - float(va_over_row["p_va"])), 6),
                        "width": va_over_row["width"],
                        "is_fitted": va_over_row.get("is_fitted", False),
                        "is_conformal": va_over_row.get("is_conformal", False),
                    }
                )

            # Same decision rule as the real-odds backtest, the fallback OOS comparisons and the orchestrator's
            # walk-forward simulation (parity-tested).
            opp = evaluate_scheduled_market_opportunity(
                estimated_prob=cal_p,
                uncertainty_std=unc,
                odds_record=o,
                game_start_time=g["game_start_time"],
                model_version_id=model_f.version_id,
                hours_to_tipoff=hours_to_tipoff,
                market_anchor_weight=market_anchor_weight,
                moneyline_weight=moneyline_weight,
                anchor_schedule=anchor_schedule,
                max_disagreement=MAX_MODEL_MARKET_DISAGREEMENT,
                moneyline_max_disagreement=moneyline_max_disagreement,
                moneyline_max_odds=moneyline_max_odds,
                simulated_prediction_time=pred_ts,
                market_consensus_prob=cons_p,
                steam_delta=s_delta,
                conformal_interval=conf_int,
                p_push=p_push_val,
                raw_model_prob=raw_p,
            )
            pred_id = f"PRED_{model_f.version_id}_{o['odds_id']}"
            opp["prediction_id"] = pred_id
            opp["raw_probability"] = raw_p
            opp["calibrated_probability"] = opp["estimated_probability"]
            opp["run_manifest_id"] = run_manifest_id
            opp["uncertainty_std"] = unc
            opp["overtime_prob"] = row_tot_pred.get("overtime_prob", 0.05)
            opp["blowout_prob"] = row_tot_pred.get("blowout_prob", 0.12)
            final_eff_weight = float(opp["effective_model_weight"])
            opp["emitted_at"] = pred_ts

            quote_key = (
                str(opp["odds_provider"]),
                str(mkt),
                str(sel),
                round(float(line_v), 2) if line_v is not None else None,
                str(opp["odds_captured_at"]),
            )
            pred_meta_by_quote[quote_key] = (
                pred_id,
                model_f.version_id,
                raw_p,
                unc,
                {
                    **row_feats,
                    "hours_to_tipoff": round(hours_to_tipoff, 3),
                    "effective_model_weight": final_eff_weight,
                },
            )
            game_opps.append(opp)

        for opp in select_best_line_shopping_candidates(game_opps):
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

    return dict(candidates_by_matchday)
