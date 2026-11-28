"""
Calibration and walk-forward OOS comparison helpers extracted from `scripts/cloud_cycle_helpers.py`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
import os
from typing import Any
import uuid

from src.calibration.calibrator import (
    ProbabilityCalibrator,
    VennAbersConformalInterval,
    compute_reliability_curve,
)
from src.config import load_config
from src.models.statistical_models import BaselineModel, EnsembleStackingModel
from src.prediction.ev_calculator import (
    compute_line_steam,
    compute_market_consensus,
    evaluate_scheduled_market_opportunity,
)
# Moved to src so the walk-forward simulation selects quotes as the live cycle does; the old name stays.
from src.prediction.market_quotes import pair_valid_pretip_quotes as _pair_valid_pretip_quotes
from src.validation.validator import parse_iso_utc


def compute_totals_line_band_telemetry(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Bucket resolved observed Totals calibration samples by observed `line_value` band."""
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


def _parse_utc_or_none(value: Any) -> datetime | None:
    try:
        return parse_iso_utc(str(value))
    except Exception:
        return None


def _same_line(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return round(float(a), 2) == round(float(b), 2)


def _latest_paired_quote(
    paired: list[dict[str, Any]], market: str, selection: str, line_value: float | None
) -> dict[str, Any] | None:
    """Most recent paired quote of one side (the quote a decision with that consensus would be taken on)."""
    matches = [
        q
        for q in paired
        if q["market"] == market and str(q["selection"]).upper() == selection and _same_line(q.get("line_value"), line_value)
    ]
    if not matches:
        return None
    return max(matches, key=lambda q: (parse_iso_utc(str(q["captured_at"])), str(q.get("provider") or "")))


def _anchored_oos_probability(
    obs: dict[str, Any],
    key: str,
    model_prob: float | None,
    uncertainty_std: float,
    *,
    game_start_time: str,
    model_version_id: str,
    market_anchor_weight: float,
    moneyline_weight: float | None,
    anchor_schedule: Any,
) -> tuple[float | None, float | None]:
    """`(anchored probability, effective model weight)` from the production decision rule, or `(None, None)`."""
    quote = obs.get(f"quote_{key}")
    market_prob = obs.get(f"market_{key}")
    if model_prob is None or market_prob is None or quote is None:
        return None, None
    opp = evaluate_scheduled_market_opportunity(
        estimated_prob=float(model_prob),
        uncertainty_std=float(uncertainty_std),
        odds_record=quote,
        game_start_time=game_start_time,
        model_version_id=model_version_id,
        hours_to_tipoff=obs["hours_to_tipoff"],
        market_anchor_weight=market_anchor_weight,
        moneyline_weight=moneyline_weight,
        anchor_schedule=anchor_schedule,
        simulated_prediction_time=obs["decision_ts"],
        market_consensus_prob=float(market_prob),
        steam_delta=float(obs.get(f"steam_{key}") or 0.0),
    )
    return float(opp["market_anchored_probability"]), float(opp["effective_model_weight"])


def build_walk_forward_oos_comparisons_for_active_model(
    db: Any,
    all_final_games: list[dict[str, Any]],
    model_version_id: str,
    now_str: str,
    *,
    market_anchor_weight: float,
    moneyline_weight: float | None,
    retrain_every_matchdays: int = 12,
    anchor_schedule: Any = None,
) -> list[dict[str, Any]]:
    """
    Reconstructs strictly out-of-sample expanding-window walk-forward comparisons for the
    frozen `model_version_id` vs `BaselineModel` vs observed `v_observed_odds_snapshots`
    market consensus when zero resolved post-m012 predictions exist in DB yet.

    Market-anchored probabilities come from the production decision rule
    (`evaluate_scheduled_market_opportunity`, `anchor_schedule` defaulting to `config.model.anchor_schedule`).
    Each game is decided when its newest paired pre-tip quote was captured, the earliest moment its market
    consensus was known: the weight is the schedule's at that many hours before tip-off, and steam uses the
    snapshots captured up to then. `market_anchor_weight` / `moneyline_weight` are the schedule's fallbacks.
    """
    schedule = anchor_schedule if anchor_schedule is not None else load_config().model.anchor_schedule
    eligible = sorted(
        [
            g
            for g in all_final_games
            if str(g["game_start_time"]) < now_str
            and g.get("home_score") is not None
            and g.get("away_score") is not None
        ],
        key=lambda g: str(g["game_start_time"]),
    )
    if len(eligible) < 150:
        return []

    raw_obs_rows = db.fetch_all(
        """
        SELECT o.*, g.game_start_time
        FROM v_observed_odds_snapshots o
        JOIN games g ON o.game_id = g.game_id
        WHERE g.status = 'FINAL'
          AND o.is_closing_line = 0
          AND o.market IN ('moneyline', 'total_points', 'spread')
          AND o.captured_at < g.game_start_time
        ORDER BY datetime(o.captured_at) ASC, o.captured_at ASC
        """
    )
    raw_by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in raw_obs_rows:
        raw_by_game[str(r["game_id"])].append(r)

    obs_summary_by_game: dict[str, dict[str, Any]] = {}
    for gid, q_rows in raw_by_game.items():
        start_dt = parse_iso_utc(str(q_rows[0]["game_start_time"]))
        paired = _pair_valid_pretip_quotes(q_rows, start_dt)
        if not paired:
            continue
        cons = compute_market_consensus(paired)
        ml_entry = cons.get(("moneyline", "HOME", None))
        tot_candidates = [
            (k[2], v, len([x for x in paired if x["market"] == "total_points" and x.get("line_value") is not None and round(float(x["line_value"]), 2) == k[2]]))
            for k, v in cons.items()
            if k[0] == "total_points" and k[1] == "OVER" and k[2] is not None
        ]
        tot_choice = max(tot_candidates, key=lambda x: x[2]) if tot_candidates else None
        sp_candidates = [
            (k[2], v, len([x for x in paired if x["market"] == "spread" and x.get("line_value") is not None and round(float(x["line_value"]) if x["selection"] == "HOME" else -float(x["line_value"]), 2) == k[2]]))
            for k, v in cons.items()
            if k[0] == "spread" and k[1] == "HOME" and k[2] is not None
        ]
        sp_choice = max(sp_candidates, key=lambda x: x[2]) if sp_candidates else None
        tot_line = float(tot_choice[0]) if tot_choice else None
        sp_line = float(sp_choice[0]) if sp_choice else None
        # Decision time = capture of the newest paired quote; steam only sees snapshots known by then.
        newest = max(paired, key=lambda q: parse_iso_utc(str(q["captured_at"])))
        decision_dt = parse_iso_utc(str(newest["captured_at"]))
        steam_map = compute_line_steam(
            [r for r in q_rows if (cap := _parse_utc_or_none(r.get("captured_at"))) is not None and cap <= decision_dt]
        )
        obs_summary_by_game[gid] = {
            "market_ml": float(ml_entry["p_market"]) if ml_entry else None,
            "tot_line": tot_line,
            "market_tot": float(tot_choice[1]["p_market"]) if tot_choice else None,
            "sp_line": sp_line,
            "market_sp": float(sp_choice[1]["p_market"]) if sp_choice else None,
            "decision_ts": str(newest["captured_at"]),
            "hours_to_tipoff": max(0.0, (start_dt - decision_dt).total_seconds() / 3600.0),
            "quote_ml": _latest_paired_quote(paired, "moneyline", "HOME", None),
            "quote_tot": _latest_paired_quote(paired, "total_points", "OVER", tot_line) if tot_line is not None else None,
            "quote_sp": _latest_paired_quote(paired, "spread", "HOME", sp_line) if sp_line is not None else None,
            "steam_ml": (steam_map.get(("moneyline", "HOME")) or {}).get("steam_delta", 0.0),
            "steam_tot": (steam_map.get(("total_points", "OVER")) or {}).get("steam_delta", 0.0),
            "steam_sp": (steam_map.get(("spread", "HOME")) or {}).get("steam_delta", 0.0),
        }

    obs_indices = [idx for idx, g in enumerate(eligible) if str(g["game_id"]) in obs_summary_by_game and idx >= 120]
    if obs_indices:
        eval_start = max(120, min(obs_indices[0] - 45, len(eligible) - 200))
    else:
        eval_start = max(120, len(eligible) - 160)

    eval_slice = eligible[eval_start:]
    matchdays = sorted({str(g["matchday_date"]) for g in eval_slice})

    base_model = BaselineModel("model_a_baseline_v1")
    ens_model = EnsembleStackingModel(model_version_id)
    ml_cal = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    tot_cal = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    sp_cal = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)

    cal_ml_hist: list[dict[str, Any]] = []
    cal_tot_hist: list[dict[str, Any]] = []
    cal_sp_hist: list[dict[str, Any]] = []
    comparison_records: list[dict[str, Any]] = []

    anchor_policy: dict[str, Any] = {
        "model_version_id": model_version_id,
        "market_anchor_weight": float(market_anchor_weight),
        "moneyline_weight": moneyline_weight,
        "anchor_schedule": schedule,
    }
    models_fitted = False

    for d_idx, m_date in enumerate(matchdays):
        day_games = [g for g in eval_slice if str(g["matchday_date"]) == m_date]
        if not day_games:
            continue
        cutoff_ts = min(str(g["game_start_time"]) for g in day_games)
        cutoff_dt = parse_iso_utc(cutoff_ts)
        prior_games = [g for g in eligible if parse_iso_utc(str(g["game_start_time"])) < cutoff_dt]
        if len(prior_games) < 120:
            continue

        if d_idx % retrain_every_matchdays == 0 or not models_fitted:
            base_model.fit(prior_games, cutoff_ts)
            ens_model.fit(prior_games, cutoff_ts)
            models_fitted = True
        if len(cal_ml_hist) >= 25 and (not ml_cal.is_fitted or d_idx % retrain_every_matchdays == 0):
            ml_cal.fit(cal_ml_hist, cutoff_ts)
        if len(cal_tot_hist) >= 25 and (not tot_cal.is_fitted or d_idx % retrain_every_matchdays == 0):
            tot_cal.fit(cal_tot_hist, cutoff_ts)
        if len(cal_sp_hist) >= 25 and (not sp_cal.is_fitted or d_idx % retrain_every_matchdays == 0):
            sp_cal.fit(cal_sp_hist, cutoff_ts)

        day_ml_updates: list[dict[str, Any]] = []
        day_tot_updates: list[dict[str, Any]] = []
        day_sp_updates: list[dict[str, Any]] = []

        for g in day_games:
            gid = str(g["game_id"])
            home_pts = int(g["home_score"])
            away_pts = int(g["away_score"])
            total_pts = home_pts + away_pts
            home_won = 1 if home_pts > away_pts else 0

            pred_a_ml = float(base_model.predict_moneyline(g, prior_games)["p_home"])
            ens_ml = ens_model.predict_moneyline(g, prior_games)
            raw_ml = float(ens_ml["p_home"])
            day_ml_updates.append(
                {"game_start_time": g["game_start_time"], "raw_probability": raw_ml, "outcome": home_won}
            )

            obs = obs_summary_by_game.get(gid, {})
            mkt_ml = obs.get("market_ml")
            tot_line = obs.get("tot_line")
            mkt_tot = obs.get("market_tot")
            sp_line = obs.get("sp_line")
            mkt_sp = obs.get("market_sp")

            cal_ml = float(ml_cal.transform_single(raw_ml)) if ml_cal.is_fitted else None
            anch_ml, w_ml = _anchored_oos_probability(
                obs, "ml", cal_ml, float(ens_ml.get("uncertainty_std", 0.0)),
                game_start_time=g["game_start_time"], **anchor_policy,
            )

            pred_a_tot = raw_tot = cal_tot = anch_tot = w_tot = None
            over_hit = 0
            has_obs_tot = False
            if tot_line is not None and abs(total_pts - tot_line) > 1e-9:
                has_obs_tot = True
                over_hit = 1 if total_pts > tot_line else 0
                pred_a_tot = float(base_model.predict_total_points(g, prior_games, tot_line)["p_over"])
                ens_tot = ens_model.predict_total_points(g, prior_games, tot_line)
                raw_tot = float(ens_tot["p_over"])
                day_tot_updates.append(
                    {"game_start_time": g["game_start_time"], "raw_probability": raw_tot, "outcome": over_hit}
                )
                if tot_cal.is_fitted:
                    cal_tot = float(tot_cal.transform_single(raw_tot))
                    # Decisive-outcome scoring (pushes are excluded above), so no push mass in the blend.
                    anch_tot, w_tot = _anchored_oos_probability(
                        obs, "tot", cal_tot, float(ens_tot.get("uncertainty_std", 0.0)),
                        game_start_time=g["game_start_time"], **anchor_policy,
                    )

            raw_sp = cal_sp = anch_sp = w_sp = None
            spread_hit: int | None = None
            if sp_line is not None and abs((home_pts - away_pts) + sp_line) > 1e-9:
                spread_hit = 1 if (home_pts - away_pts + sp_line) > 0.0 else 0
                ens_sp = ens_model.predict_spread(g, prior_games, sp_line)
                raw_sp = float(ens_sp["p_cover_home"])
                day_sp_updates.append(
                    {"game_start_time": g["game_start_time"], "raw_probability": raw_sp, "outcome": spread_hit}
                )
                if sp_cal.is_fitted:
                    cal_sp = float(sp_cal.transform_single(raw_sp))
                    anch_sp, w_sp = _anchored_oos_probability(
                        obs, "sp", cal_sp, float(ens_sp.get("uncertainty_std", 0.0)),
                        game_start_time=g["game_start_time"], **anchor_policy,
                    )

            if cal_ml is not None:
                comparison_records.append(
                    {
                        "game_id": gid,
                        "season": g["season"],
                        "matchday_date": m_date,
                        "home_won": home_won,
                        "over_hit": over_hit,
                        "has_observed_tot_line": has_obs_tot,
                        "spread_hit": spread_hit,
                        "model_a_ml": pred_a_ml,
                        "model_raw_ml": raw_ml,
                        "model_cal_ml": cal_ml,
                        "model_c_ml": cal_ml,
                        "model_anchored_ml": anch_ml,
                        "market_ml": mkt_ml,
                        "model_a_tot": pred_a_tot,
                        "model_raw_tot": raw_tot,
                        "model_cal_tot": cal_tot,
                        "model_d_tot": cal_tot,
                        "model_anchored_tot": anch_tot,
                        "market_tot": mkt_tot,
                        "model_raw_sp": raw_sp,
                        "model_cal_sp": cal_sp,
                        "market_sp": mkt_sp,
                        "model_anchored_sp": anch_sp,
                        "anchor_hours_to_tipoff": obs.get("hours_to_tipoff"),
                        "model_anchor_weight_ml": w_ml,
                        "model_anchor_weight_tot": w_tot,
                        "model_anchor_weight_sp": w_sp,
                    }
                )

        cal_ml_hist.extend(day_ml_updates)
        cal_tot_hist.extend(day_tot_updates)
        cal_sp_hist.extend(day_sp_updates)

    return comparison_records


def fit_and_log_cycle_calibrators(
    db: Any,
    *,
    model_f: EnsembleStackingModel,
    model_version_id: str,
    resolved_ml_preds: list[dict[str, Any]],
    resolved_tot_preds: list[dict[str, Any]],
    resolved_sp_preds: list[dict[str, Any]],
    now_dt: datetime,
    now_str: str,
    mode: str,
    all_final_games: list[dict[str, Any]],
    config_hash: str,
    config_version: str,
    commit_sha: str,
) -> dict[str, Any]:
    """Fits ML/Totals/Spread calibrators + Venn-Abers intervals and logs manifest rows."""
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

    totals_line_bands = compute_totals_line_band_telemetry(resolved_tot_preds)
    totals_fallback = bool(tot_method == "identity" or len(resolved_tot_preds) < 25)
    spread_fallback = bool(sp_method == "identity" or len(resolved_sp_preds) < 25)

    for mkt_name, resolved_rows, cal_method_val in [
        ("moneyline", resolved_ml_preds, ml_method),
        ("total_points", resolved_tot_preds, tot_method),
        ("spread", resolved_sp_preds, sp_method),
    ]:
        if not resolved_rows:
            continue
        curve_m = compute_reliability_curve(
            [float(r["raw_probability"]) for r in resolved_rows],
            [int(r["outcome"]) for r in resolved_rows],
        )
        prefix_m = {"moneyline": "ML", "total_points": "TOT", "spread": "SP"}[mkt_name]
        db.execute_insert(
            """
            INSERT INTO calibration_logs (
                eval_id, evaluated_at, model_version_id, market, sample_size,
                brier_score, log_loss, ece, calibration_method, bins_json, promoted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                f"CAL_{prefix_m}_{now_dt.strftime('%Y%m%dT%H%M%S')}",
                now_str,
                model_version_id,
                mkt_name,
                curve_m["sample_size"],
                curve_m["brier_score"],
                curve_m["log_loss"],
                curve_m["ece"],
                cal_method_val,
                json.dumps(curve_m["bins"]),
            ),
        )

    run_manifest_id = f"RUN_{now_dt.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8].upper()}"
    submodel_versions_map = {
        "model_a": "model_a_baseline_v1",
        "model_b": model_f.model_b.version_id,
        "model_c": model_f.model_c.version_id,
        "model_d": model_f.model_d.version_id,
        "model_e": model_f.model_e.version_id,
        "model_g": model_f.model_g.version_id,
        "model_h": model_f.model_h.version_id,
    }
    calibrator_metadata = {
        "moneyline": {"method": ml_method, "sample_size": len(resolved_ml_preds), "venn_abers_fitted": ml_va.is_fitted},
        "total_points": {
            "method": tot_method,
            "sample_size": len(resolved_tot_preds),
            "venn_abers_fitted": tot_va.is_fitted,
            "fallback_active": totals_fallback,
            "line_bands": totals_line_bands,
        },
        "spread": {
            "method": sp_method,
            "sample_size": len(resolved_sp_preds),
            "venn_abers_fitted": sp_va.is_fitted,
            "fallback_active": spread_fallback,
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
            model_version_id,
            model_f.version_id,
            json.dumps(submodel_versions_map, sort_keys=True),
            config_hash,
            config_version,
            json.dumps(calibrator_metadata, sort_keys=True),
            json.dumps(seeds_metadata, sort_keys=True),
            data_cutoff_utc,
            f"mode={mode};totals_fallback={totals_fallback}",
            now_str,
        ),
    )
    return {
        "ml_cal": ml_cal,
        "tot_cal": tot_cal,
        "sp_cal": sp_cal,
        "ml_va": ml_va,
        "tot_va": tot_va,
        "sp_va": sp_va,
        "ml_method": ml_method,
        "tot_method": tot_method,
        "sp_method": sp_method,
        "totals_line_bands": totals_line_bands,
        "totals_fallback": totals_fallback,
        "run_manifest_id": run_manifest_id,
        "submodel_versions_map": submodel_versions_map,
        "calibrator_metadata": calibrator_metadata,
        "data_cutoff_utc": data_cutoff_utc,
    }
