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
from src.models.statistical_models import BaselineModel, EnsembleStackingModel
from src.prediction.ev_calculator import compute_market_consensus
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


def _pair_valid_pretip_quotes(
    raw_game_odds: list[dict[str, Any]],
    start_dt: datetime,
    *,
    decision_dt: datetime | None = None,
    max_quote_age_hours: float | None = None,
    excluded_provider_markers: tuple[str, ...] = (),
    max_overround: float | None = None,
) -> list[dict[str, Any]]:
    """
    Extracts complete two-sided pre-tipoff observed pairs grouped by `(provider, market, canonical_line)`.

    For live decisions (`decision_dt` set) only quotes that existed at the decision time and are at most
    `max_quote_age_hours` old are used, and providers whose label contains an excluded marker (e.g.
    "(Best of" aggregates that pair the best price of one book with another book's counterpart) are
    skipped: those prices are not a quote any single book offered. Two-way markets whose overround
    exceeds `max_overround` are dropped: at a ~10% margin no realistic edge survives.
    """
    latest_by_key: dict[tuple[str, str, float | None, str], tuple[datetime, dict[str, Any]]] = {}
    for o in raw_game_odds:
        try:
            cap_dt = parse_iso_utc(str(o["captured_at"]))
            dec_val = float(o.get("decimal_odds") or 0.0)
        except Exception:
            continue
        if cap_dt >= start_dt or dec_val <= 1.0:
            continue
        if any(marker in str(o.get("provider") or "") for marker in excluded_provider_markers):
            continue
        if decision_dt is not None:
            if cap_dt > decision_dt:
                continue
            if max_quote_age_hours is not None and (decision_dt - cap_dt).total_seconds() > max_quote_age_hours * 3600.0:
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
    paired: list[dict[str, Any]] = []
    for mkt_name, (side_a, side_b) in sides_by_market.items():
        prov_lines = sorted({(k[0], k[2]) for k in latest_by_key if k[1] == mkt_name})
        for prov, lv_key in prov_lines:
            entry_a = latest_by_key.get((prov, mkt_name, lv_key, side_a))
            entry_b = latest_by_key.get((prov, mkt_name, lv_key, side_b))
            if not entry_a or not entry_b:
                continue
            row_a, row_b = entry_a[1], entry_b[1]
            if max_overround is not None:
                overround = 1.0 / float(row_a["decimal_odds"]) + 1.0 / float(row_b["decimal_odds"]) - 1.0
                if overround > max_overround:
                    continue
            paired.append({**row_a, "counterpart_decimal_odds": float(row_b["decimal_odds"])})
            paired.append({**row_b, "counterpart_decimal_odds": float(row_a["decimal_odds"])})
    return paired


def build_walk_forward_oos_comparisons_for_active_model(
    db: Any,
    all_final_games: list[dict[str, Any]],
    model_version_id: str,
    now_str: str,
    *,
    market_anchor_weight: float,
    moneyline_weight: float | None,
    retrain_every_matchdays: int = 12,
) -> list[dict[str, Any]]:
    """
    Reconstructs strictly out-of-sample expanding-window walk-forward comparisons for the
    frozen `model_version_id` vs `BaselineModel` vs observed `v_observed_odds_snapshots`
    market consensus when zero resolved post-m012 predictions exist in DB yet.
    """
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
        obs_summary_by_game[gid] = {
            "market_ml": float(ml_entry["p_market"]) if ml_entry else None,
            "tot_line": float(tot_choice[0]) if tot_choice else None,
            "market_tot": float(tot_choice[1]["p_market"]) if tot_choice else None,
            "sp_line": float(sp_choice[0]) if sp_choice else None,
            "market_sp": float(sp_choice[1]["p_market"]) if sp_choice else None,
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

    ml_w = float(moneyline_weight if moneyline_weight is not None else market_anchor_weight)
    tot_w = float(market_anchor_weight)
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
            raw_ml = float(ens_model.predict_moneyline(g, prior_games)["p_home"])
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
            anch_ml = (
                round(ml_w * cal_ml + (1.0 - ml_w) * mkt_ml, 6)
                if (cal_ml is not None and mkt_ml is not None)
                else None
            )

            pred_a_tot = raw_tot = cal_tot = anch_tot = None
            over_hit = 0
            has_obs_tot = False
            if tot_line is not None and abs(total_pts - tot_line) > 1e-9:
                has_obs_tot = True
                over_hit = 1 if total_pts > tot_line else 0
                pred_a_tot = float(base_model.predict_total_points(g, prior_games, tot_line)["p_over"])
                raw_tot = float(ens_model.predict_total_points(g, prior_games, tot_line)["p_over"])
                day_tot_updates.append(
                    {"game_start_time": g["game_start_time"], "raw_probability": raw_tot, "outcome": over_hit}
                )
                if tot_cal.is_fitted:
                    cal_tot = float(tot_cal.transform_single(raw_tot))
                    if mkt_tot is not None:
                        anch_tot = round(tot_w * cal_tot + (1.0 - tot_w) * mkt_tot, 6)

            raw_sp = cal_sp = anch_sp = None
            spread_hit: int | None = None
            if sp_line is not None and abs((home_pts - away_pts) + sp_line) > 1e-9:
                spread_hit = 1 if (home_pts - away_pts + sp_line) > 0.0 else 0
                raw_sp = float(ens_model.predict_spread(g, prior_games, sp_line)["p_cover_home"])
                day_sp_updates.append(
                    {"game_start_time": g["game_start_time"], "raw_probability": raw_sp, "outcome": spread_hit}
                )
                if sp_cal.is_fitted:
                    cal_sp = float(sp_cal.transform_single(raw_sp))
                    if mkt_sp is not None:
                        anch_sp = round(tot_w * cal_sp + (1.0 - tot_w) * mkt_sp, 6)

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
