"""
Venn-Abers conformal calibration and opportunity EV evaluation for experimental Props.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
import uuid

import numpy as np

from src.calibration.calibrator import VennAbersConformalInterval, conformal_lower_bound_ev
from src.prediction.ev_calculator import (
    calculate_ev,
    devig_multiplicative,
    market_anchored_probability,
)
from src.validation.validator import TemporalLeakageError, parse_iso_utc

logger = logging.getLogger(__name__)


def build_historical_props_calibration_dataset(
    engine: Any,
    as_of_utc: str,
    max_oos_boxscore_samples: int = 350,
) -> list[dict[str, Any]]:
    """Builds a strictly out-of-sample calibration dataset from resolved props prior to `as_of_utc`."""
    parse_iso_utc(as_of_utc)
    if engine.db is None:
        return []

    records: list[dict[str, Any]] = []
    try:
        pick_rows = engine.db.fetch_all(
            """
            SELECT p.game_id, p.player_name, p.prop_category, p.line_value, p.selection,
                   p.decimal_odds, p.model_prob, g.game_start_time, p.settled_at, p.status
            FROM player_prop_picks p
            JOIN games g ON g.game_id = p.game_id
            WHERE p.status IN ('WON', 'LOST')
              AND p.prop_category != 'SGP'
              AND p.settled_at IS NOT NULL
              AND datetime(g.game_start_time) < datetime(?)
              AND datetime(p.settled_at) <= datetime(?)
            ORDER BY g.game_start_time ASC
            """,
            (as_of_utc, as_of_utc),
        )
        for r in pick_rows:
            records.append(
                {
                    "game_id": str(r["game_id"]),
                    "player_name": str(r["player_name"]),
                    "category": str(r["prop_category"]).upper(),
                    "line_value": float(r["line_value"]),
                    "decimal_odds": float(r["decimal_odds"]),
                    "selection": str(r["selection"]).upper(),
                    "raw_probability": float(np.clip(float(r["model_prob"]), 1e-4, 1.0 - 1e-4)),
                    "game_start_time": str(r["game_start_time"]),
                    "result_recorded_at": str(r["settled_at"]),
                    "outcome": 1 if r["status"] == "WON" else 0,
                    "source": "player_prop_picks",
                }
            )
    except Exception as exc:
        logger.debug(f"Settled props dataset query skipped: {exc}")

    if len(records) < 2000:
        try:
            box_rows = engine.db.fetch_all(
                """
                SELECT pb.game_id, pb.player_name, pb.player_key, pb.team, pb.game_start_time,
                       pb.minutes, pb.pts, pb.reb, pb.ast, pb.threed,
                       g.home_team, g.away_team, g.result_recorded_at
                FROM player_boxscores pb
                JOIN games g ON g.game_id = pb.game_id
                WHERE g.status = 'FINAL'
                  AND g.game_id NOT LIKE 'SYN%'
                  AND pb.minutes >= 12.0
                  AND datetime(pb.game_start_time) < datetime(?)
                  AND (g.result_recorded_at IS NULL OR datetime(g.result_recorded_at) <= datetime(?))
                ORDER BY pb.game_start_time ASC, pb.player_key ASC
                """,
                (as_of_utc, as_of_utc),
            )
            if box_rows:
                step = max(1, len(box_rows) // max(1, int(max_oos_boxscore_samples)))
                cat_benchmarks: tuple[tuple[str, float, str], ...] = (
                    ("PTS", 15.5, "pts"),
                    ("REB", 5.5, "reb"),
                    ("AST", 4.5, "ast"),
                    ("3PM", 1.5, "threed"),
                    ("PRA", 24.5, "pra"),
                )
                for r in box_rows[::step][:max_oos_boxscore_samples]:
                    opp_team = r["away_team"] if r["team"] == r["home_team"] else r["home_team"]
                    proj = engine.project_player_stats(
                        player_name=str(r["player_name"]),
                        team=str(r["team"]),
                        opponent_team=str(opp_team),
                        as_of_utc=str(r["game_start_time"]),
                    )
                    actual_map = {
                        "pts": float(r["pts"]),
                        "reb": float(r["reb"]),
                        "ast": float(r["ast"]),
                        "threed": float(r["threed"]),
                        "pra": float(r["pts"]) + float(r["reb"]) + float(r["ast"]),
                    }
                    res_ts = str(r.get("result_recorded_at") or r["game_start_time"])
                    for cat, line_v, expr in cat_benchmarks:
                        cdata = proj["projections"].get(cat)
                        if not cdata or expr not in actual_map:
                            continue
                        act_v = actual_map[expr]
                        if act_v == line_v:
                            continue
                        p_over, _p_under, _p_push = engine.compute_exceedance_probabilities(
                            prop_category=cat,
                            line_value=line_v,
                            proj_mean=float(cdata["mean"]),
                            proj_std=float(cdata["std"]),
                            dist_type=str(cdata["dist"]),
                        )
                        records.append(
                            {
                                "game_id": str(r["game_id"]),
                                "player_name": str(r["player_name"]),
                                "category": cat,
                                "line_value": line_v,
                                "decimal_odds": 1.90,
                                "selection": "OVER",
                                "raw_probability": float(np.clip(p_over, 1e-4, 1.0 - 1e-4)),
                                "game_start_time": str(r["game_start_time"]),
                                "result_recorded_at": res_ts,
                                "outcome": 1 if act_v > line_v else 0,
                                "source": "player_boxscores_oos",
                            }
                        )
        except Exception as exc:
            logger.debug(f"Historical player_boxscores calibration build skipped: {exc}")

    records.sort(key=lambda rec: str(rec.get("game_start_time") or ""))
    engine.oos_calibration_dataset = records
    return records


def fit_props_calibrators(
    engine: Any,
    as_of_utc: str,
    calibration_records: list[dict[str, Any]] | None = None,
    global_min_samples: int | None = None,
    category_min_samples: int | None = None,
) -> dict[str, Any]:
    """Trains pooled global and category-specific Venn-Abers conformal calibrators < `as_of_utc`."""
    parse_iso_utc(as_of_utc)
    recs = (
        list(calibration_records)
        if calibration_records is not None
        else build_historical_props_calibration_dataset(engine, as_of_utc=as_of_utc)
    )

    g_min = int(global_min_samples) if global_min_samples is not None else engine.global_min_samples
    c_min = int(category_min_samples) if category_min_samples is not None else engine.category_min_samples

    engine.calibrator = VennAbersConformalInterval(window=1200, min_samples=g_min)
    global_fitted = engine.calibrator.fit(recs, as_of_utc) if recs else False

    by_cat: dict[str, list[dict[str, Any]]] = {}
    for rec in recs:
        cat = str(rec.get("category") or rec.get("prop_category") or "UNKNOWN").upper()
        by_cat.setdefault(cat, []).append(rec)

    engine.category_calibrators = {}
    cat_stats: dict[str, dict[str, Any]] = {}
    for cat, c_recs in by_cat.items():
        va_cat = VennAbersConformalInterval(window=1200, min_samples=c_min)
        c_fitted = va_cat.fit(c_recs, as_of_utc)
        engine.category_calibrators[cat] = va_cat
        cat_stats[cat] = {
            "is_fitted": bool(c_fitted),
            "sample_size": len(c_recs),
            "cutoff_utc": as_of_utc,
            "min_samples": c_min,
        }

    engine.calibration_cutoff_utc = as_of_utc
    engine.calibration_dataset_size = len(recs)
    engine.calibration_summary = {
        "global": {
            "is_fitted": bool(global_fitted),
            "sample_size": len(recs),
            "cutoff_utc": as_of_utc,
            "min_samples": g_min,
        },
        "categories": cat_stats,
    }
    return engine.calibration_summary


def evaluate_prop_opportunity_impl(
    engine: Any,
    player_name: str,
    team: str,
    game_id: str,
    matchday_date: str,
    prop_category: str,
    line_value: float,
    over_odds: float,
    under_odds: float,
    absent_teammates: list[str] | None = None,
    bankroll_pen: float = 100.0,
    opponent_team: str | None = None,
    expected_game_pace: float | None = None,
    spread_blowout_risk: float | None = None,
    persist: bool = True,
    line_source: str = "OBSERVED",
    as_of_utc: str | None = None,
    as_of_timestamp: str | None = None,
    allow_player_props: bool | None = None,
) -> list[dict[str, Any]]:
    """Evaluates OVER/UNDER player prop sides preserving push mass and conformal bounds."""
    effective_cutoff = as_of_utc or as_of_timestamp
    if engine.db is not None and not effective_cutoff:
        g_row = engine.db.fetch_one("SELECT game_start_time FROM games WHERE game_id = ?", (game_id,))
        if g_row and g_row.get("game_start_time"):
            effective_cutoff = str(g_row["game_start_time"])
        else:
            raise TemporalLeakageError(
                "evaluate_prop_opportunity requires `as_of_timestamp` / `as_of_utc` when querying historical DB records."
            )

    proj_info = engine.project_player_stats(
        player_name=player_name,
        team=team,
        absent_teammates=absent_teammates,
        opponent_team=opponent_team,
        expected_game_pace=expected_game_pace,
        spread_blowout_risk=spread_blowout_risk,
        as_of_timestamp=effective_cutoff,
    )
    cat_data = proj_info["projections"].get(prop_category)
    if not cat_data:
        return []

    mu = float(cat_data["mean"])
    sigma = float(cat_data["std"])
    dist_type = cat_data["dist"]

    p_over_raw, p_under_raw, p_push_raw = engine.compute_exceedance_probabilities(
        prop_category=prop_category,
        line_value=line_value,
        proj_mean=mu,
        proj_std=sigma,
        dist_type=dist_type,
    )

    active_cal, cal_method = engine._select_calibrator_for_category(prop_category)
    opportunities: list[dict[str, Any]] = []

    for sel, p_raw in [("OVER", p_over_raw), ("UNDER", p_under_raw)]:
        dec_odds = over_odds if sel == "OVER" else under_odds
        if dec_odds <= 1.0:
            continue

        p_fair_a, p_fair_b, _ = devig_multiplicative(over_odds, under_odds)
        mkt_fair_cond = p_fair_a if sel == "OVER" else p_fair_b
        non_push = max(1e-9, 1.0 - p_push_raw)
        mkt_fair_win = mkt_fair_cond * non_push

        p_raw_cond = float(np.clip(p_raw / non_push, 1e-4, 1.0 - 1e-4)) if p_push_raw > 0.0 else p_raw
        if active_cal is not None:
            conf_int = active_cal.predict_interval(p_raw_cond)
            cal_fitted = bool(conf_int["is_fitted"])
            is_conformal = bool(conf_int["is_conformal"])
            cal_sample_size = int(conf_int["sample_size"])
            cal_cutoff = conf_int["cutoff_utc"]
            cal_cond = float(conf_int["p_va"])
        else:
            conf_int = engine.calibrator.predict_interval(p_raw_cond)
            cal_fitted = False
            is_conformal = False
            cal_sample_size = int(conf_int.get("sample_size") or engine.calibration_dataset_size)
            cal_cutoff = conf_int.get("cutoff_utc") or engine.calibration_cutoff_utc
            cal_cond = p_raw_cond

        cal_win_prob = cal_cond * non_push if p_push_raw > 0.0 else cal_cond
        p_low_uncond = float(conf_int["p0"]) * non_push if p_push_raw > 0.0 else float(conf_int["p0"])
        p_high_uncond = float(conf_int["p1"]) * non_push if p_push_raw > 0.0 else float(conf_int["p1"])
        conf_w = max(0.0, p_high_uncond - p_low_uncond)

        anchored_cond = market_anchored_probability(cal_cond, mkt_fair_cond, model_weight=0.75)
        anchored_win = anchored_cond * non_push if p_push_raw > 0.0 else anchored_cond
        anchored_loss = max(0.0, non_push - anchored_win)

        ev_metrics = calculate_ev(anchored_win, dec_odds, p_push=p_push_raw, p_loss=anchored_loss)
        ev_pct = float(ev_metrics["ev_pct"])

        lb_metrics = conformal_lower_bound_ev(
            cal_win_prob,
            p_low_uncond,
            mkt_fair_cond,
            model_weight=0.75,
            decimal_odds=dec_odds,
            p_push=p_push_raw,
        )
        lb_ev_pct = float(lb_metrics["ev_lower_bound"]) * 100.0

        line_diff = round((mu - line_value) if sel == "OVER" else (line_value - mu), 1)
        line_diff_pct = round((line_diff / max(1.0, line_value)) * 100.0, 1)

        stake_pen = 0.0
        kelly_frac = 0.0
        if not cal_fitted:
            lower_bound_ev_blocked = True
            lower_bound_ev_status = "BLOCKED_UNFITTED_FALLBACK"
            is_edge_qualified = ev_pct >= (engine.min_ev_threshold * 100.0)
            decision = "NO_BET"
            decision_reason = "UNFITTED_CALIBRATOR_FALLBACK"
        else:
            lower_bound_ev_blocked = False
            lower_bound_ev_status = "CONFORMAL_VERIFIED"
            is_edge_qualified = (lb_ev_pct >= (engine.min_ev_threshold * 100.0)) and (ev_pct > 0.0) and (conf_w <= 0.35)
            if is_edge_qualified:
                b_val = dec_odds - 1.0
                expected_growth_num = anchored_win * b_val - anchored_loss
                f_star = max(0.0, expected_growth_num / max(0.05, b_val * (anchored_win + anchored_loss))) if expected_growth_num > 0.0 else 0.0
                eff_f = min(engine.max_bankroll_fraction, f_star * engine.kelly_fraction)
                raw_s = bankroll_pen * eff_f
                if eff_f > 0.0 and ev_pct > 0.0:
                    stake_pen = round(max(0.0, min(engine.max_stake_pen, raw_s)), 2)
                kelly_frac = round(eff_f, 4)
            decision = "BET_PLACED" if stake_pen > 0.0 else "NO_BET"
            decision_reason = "QUALIFIED_CONFORMAL_EV" if stake_pen > 0.0 else "BELOW_CONFORMAL_LB_EV"

        if not is_edge_qualified:
            continue

        cal_badge = (
            f"[CONFORMAL {cal_method} n={cal_sample_size}] "
            if cal_fitted
            else f"[FALLBACK NO-CONFORMAL n={cal_sample_size} | STAKING BLOCKED] "
        )
        rationale = (
            ("" if line_source == "OBSERVED" else "[LÍNEA ESTIMADA, no observada] ")
            + cal_badge
            + f"[{prop_category} {sel} {line_value}] {player_name} ({team}). "
            + f"Proyección: {mu:.1f} (std: {sigma:.1f}, Ventaja vs Línea: {line_diff:+0.1f} pts, P(push)={p_push_raw:.3f}). "
            + f"Prob Modelo: {anchored_win * 100:.1f}% vs Casa: {mkt_fair_win * 100:.1f}%. "
            + f"Ajustes: +{proj_info['usage_bump_pct']:.1f}% USG, Rival {proj_info.get('opponent_team') or 'NBA'} ({proj_info['matchup_tier']}). "
            + f"LB EV: {lb_ev_pct:+.2f}% ({lower_bound_ev_status}) a cuota {dec_odds:.2f}. Kelly: S/ {stake_pen:.2f} PEN."
        )

        prop_pick = {
            "prop_id": f"PROP_{game_id}_{player_name.replace(' ', '_')}_{prop_category}_{sel}_{uuid.uuid4().hex[:6]}",
            "type": "INDIVIDUAL_PROP",
            "game_id": game_id,
            "matchday_date": matchday_date,
            "player_name": player_name,
            "team": team,
            "opponent_team": proj_info.get("opponent_team"),
            "matchup_tier": proj_info["matchup_tier"],
            "matchup_adjustment_pct": proj_info["matchup_adjustment_pct"],
            "pace_factor": proj_info["pace_factor"],
            "prop_category": prop_category,
            "line_value": line_value,
            "selection": sel,
            "decimal_odds": dec_odds,
            "projected_mean": mu,
            "projected_std": sigma,
            "line_diff": line_diff,
            "line_diff_pct": line_diff_pct,
            "raw_model_prob": round(p_raw, 4),
            "calibrated_model_prob": round(cal_win_prob, 4),
            "market_fair_prob": round(mkt_fair_win, 4),
            "model_prob": round(anchored_win, 4),
            "p_win": round(anchored_win, 6),
            "p_loss": round(anchored_loss, 6),
            "p_push": round(p_push_raw, 6),
            "conformal_p_low": round(p_low_uncond, 4),
            "conformal_p_high": round(p_high_uncond, 4),
            "calibrator_is_fitted": cal_fitted,
            "calibration_is_conformal": is_conformal,
            "calibration_method": cal_method,
            "calibration_sample_size": cal_sample_size,
            "calibration_cutoff_utc": cal_cutoff,
            "lower_bound_ev_blocked": lower_bound_ev_blocked,
            "lower_bound_ev_status": lower_bound_ev_status,
            "decision": decision,
            "decision_reason": decision_reason,
            "ev_pct": round(ev_pct, 2),
            "ev_lower_bound_pct": round(lb_ev_pct, 2),
            "kelly_stake_pen": stake_pen,
            "kelly_optimal_fraction": kelly_frac,
            "usage_bump_pct": proj_info["usage_bump_pct"],
            "effective_minutes": proj_info["effective_minutes"],
            "rationale": rationale,
            "line_source": line_source,
            "emitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        opportunities.append(prop_pick)

        if persist:
            engine._persist_prop_pick(prop_pick, bankroll_pen, allow_player_props=allow_player_props)

    return opportunities
