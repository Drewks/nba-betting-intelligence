"""
Walk-forward simulation loop and observed-DB comparison reconstruction helpers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from typing import Any

from src.calibration.calibrator import (
    ProbabilityCalibrator,
    VennAbersConformalInterval,
    calibrate_binary_with_push,
)
from src.config import load_config
from src.features.builder import build_pregame_features
from src.models.statistical_models import (
    AdvancedGBMModel,
    BaselineModel,
    EloModel,
    EnsembleStackingModel,
    PointMarginModel,
    TotalPointsModel,
)
from src.paper_trading.engine import PaperTradingEngine
from src.prediction.ev_calculator import evaluate_market_opportunity
from src.storage.db import DatabaseManager
from src.validation.validator import (
    parse_iso_utc,
    validate_game_record,
    validate_odds_record,
)


def _flip_conformal_interval(va_interval: dict[str, Any]) -> dict[str, Any]:
    """Complements a Venn-Abers conformal interval onto the opposite binary selection."""
    return {
        "p0": round(1.0 - va_interval["p1"], 6),
        "p1": round(1.0 - va_interval["p0"], 6),
        "p_va": round(1.0 - va_interval["p_va"], 6),
        "width": va_interval["width"],
    }


def _extract_market_probs(row: dict[str, Any] | None) -> tuple[float | None, float | None, float | None, float | None]:
    """Returns `(raw_model_prob, cal_model_prob, fair_market_prob, anchored_prob)` preserving pre-m012 None semantics."""
    if not row:
        return (None, None, None, None)
    raw = float(row["raw_model_probability"] if row.get("raw_model_probability") is not None else row["raw_probability"])
    cal = float(row["calibrated_model_probability"]) if row.get("calibrated_model_probability") is not None else None
    mkt = (
        float(row["market_fair_probability"] if row.get("market_fair_probability") is not None else row["implied_prob_fair"])
        if (row.get("market_fair_probability") is not None or row.get("implied_prob_fair") is not None)
        else None
    )
    anch = float(row["market_anchored_probability"] if row.get("market_anchored_probability") is not None else row["calibrated_probability"])
    return (raw, cal, mkt, anch)


def reconstruct_comparison_records_from_db(db: DatabaseManager) -> list[dict[str, Any]]:
    """
    One record per real FINAL game using the LATEST observed pre-tip prediction of each market.
    Explicitly separates raw model probability, calibrated model probability, fair de-vigged market
    probability, and market-anchored probability (F-008). Pre-m012 legacy rows leave
    calibrated_model_probability as None so market anchoring is never conflated with model calibration.
    """
    rows = db.fetch_all(
        """
        WITH latest AS (
            SELECT p.*, ROW_NUMBER() OVER (
                PARTITION BY p.game_id, p.market ORDER BY p.emitted_at DESC, p.prediction_id DESC
            ) AS rn
            FROM v_observed_predictions p
            WHERE (p.market = 'moneyline' AND p.selection = 'HOME')
               OR (p.market = 'total_points' AND p.selection = 'OVER')
               OR (p.market = 'spread' AND p.selection = 'HOME')
        )
        SELECT l.game_id, l.market, l.raw_probability, l.calibrated_probability,
               l.raw_model_probability, l.calibrated_model_probability,
               l.market_fair_probability, l.market_anchored_probability,
               l.implied_prob_fair, l.line_value,
               g.season, g.matchday_date, g.game_start_time, g.home_score, g.away_score
        FROM latest l JOIN games g ON g.game_id = l.game_id
        WHERE l.rn = 1 AND g.status = 'FINAL' AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
          AND l.game_id NOT LIKE 'SYN%'
        """
    )
    by_game: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in rows:
        by_game[r["game_id"]][r["market"]] = r
    all_final_games = db.fetch_all(
        "SELECT * FROM v_observed_games WHERE status = 'FINAL' AND home_score IS NOT NULL ORDER BY game_start_time ASC"
    )
    games_idx = {g["game_id"]: g for g in all_final_games}
    base_model = BaselineModel("model_a_baseline_v1")
    out: list[dict[str, Any]] = []
    for gid, mk in sorted(by_game.items(), key=lambda kv: str(next(iter(kv[1].values()))["game_start_time"])):
        ml = mk.get("moneyline")
        tot = mk.get("total_points")
        sp = mk.get("spread")
        if not ml or not tot or tot.get("line_value") is None:
            continue
        g_full = games_idx.get(gid)
        if not g_full:
            continue
        prior_g = [x for x in all_final_games if x["game_start_time"] < g_full["game_start_time"]]
        if prior_g:
            base_model.fit(prior_g, g_full["game_start_time"])
        line_v = float(tot["line_value"])
        total_pts = int(g_full["home_score"]) + int(g_full["away_score"])
        if abs(total_pts - line_v) < 1e-9:
            continue  # pushes carry no binary outcome

        spread_hit: int | None = None
        sp_raw = sp_cal = sp_mkt = sp_anch = None
        if sp and sp.get("line_value") is not None:
            sp_line = float(sp["line_value"])
            adj_sp = (int(g_full["home_score"]) - int(g_full["away_score"])) + sp_line
            if abs(adj_sp) > 1e-9:
                spread_hit = 1 if adj_sp > 0.0 else 0
                sp_raw, sp_cal, sp_mkt, sp_anch = _extract_market_probs(sp)

        ml_raw, ml_cal, ml_mkt, ml_anch = _extract_market_probs(ml)
        tot_raw, tot_cal, tot_mkt, tot_anch = _extract_market_probs(tot)

        out.append(
            {
                "game_id": gid,
                "season": ml["season"],
                "matchday_date": ml["matchday_date"],
                "home_won": 1 if int(g_full["home_score"]) > int(g_full["away_score"]) else 0,
                "over_hit": 1 if total_pts > line_v else 0,
                "has_observed_tot_line": True,
                "spread_hit": spread_hit,
                "model_a_ml": base_model.predict_moneyline(g_full, prior_g)["p_home"],
                "model_raw_ml": ml_raw,
                "model_cal_ml": ml_cal,
                # F-008: Never conflate missing calibrated_model_probability (pre-m012) with market_anchored_probability
                "model_c_ml": ml_cal,
                "model_anchored_ml": ml_anch,
                "market_ml": ml_mkt,
                "model_a_tot": base_model.predict_total_points(g_full, prior_g, line_v)["p_over"],
                "model_raw_tot": tot_raw,
                "model_cal_tot": tot_cal,
                "model_d_tot": tot_cal,
                "model_anchored_tot": tot_anch,
                "market_tot": tot_mkt,
                "model_raw_sp": sp_raw,
                "model_cal_sp": sp_cal,
                "market_sp": sp_mkt,
                "model_anchored_sp": sp_anch,
            }
        )
    return out


def run_walk_forward_simulation(
    db: DatabaseManager,
    paper_engine: PaperTradingEngine,
    warmup_matchdays: int,
    retrain_every_matchdays: int,
    games: list[dict[str, Any]],
    odds: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Executes chronological walk-forward training, calibration, prediction, and settlement."""
    sorted_games = sorted(games, key=lambda g: g["game_start_time"])
    skipped_unpredictable_games = 0

    with db.connect() as conn:
        for g in sorted_games:
            # Only games not stored yet are inserted: a stored row is never re-inserted or replaced
            # (the games temporal-freeze triggers reject a different copy of a started game).
            conn.execute(
                """
                INSERT OR IGNORE INTO games (
                    game_id, season, matchday_date, game_start_time, home_team, away_team,
                    status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
                    away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
                    features_available_at, source_provider, ingested_at, result_recorded_at
                )
                SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                WHERE NOT EXISTS (SELECT 1 FROM games WHERE game_id = ?)
                """,
                (
                    g["game_id"],
                    g["season"],
                    g["matchday_date"],
                    g["game_start_time"],
                    g["home_team"],
                    g["away_team"],
                    g["status"],
                    g["home_score"],
                    g["away_score"],
                    g["home_off_rtg"],
                    g["home_def_rtg"],
                    g["home_pace"],
                    g["away_off_rtg"],
                    g["away_def_rtg"],
                    g["away_pace"],
                    g["home_rest_days"],
                    g["away_rest_days"],
                    g["features_available_at"],
                    g["source_provider"],
                    g["ingested_at"],
                    g.get("result_recorded_at"),
                    g["game_id"],
                ),
            )

    odds_by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    closing_rows: list[dict[str, Any]] = []
    for o in odds:
        if int(o.get("is_closing_line", 0)) == 1:
            closing_rows.append(o)
        else:
            odds_by_game[o["game_id"]].append(o)

    matchdays = sorted({g["matchday_date"] for g in sorted_games})

    model_a = BaselineModel("model_a_baseline_v1")
    model_b = EloModel("model_b_elo_v1")
    model_c = PointMarginModel("model_c_point_margin_v1")
    model_d = TotalPointsModel("model_d_total_points_v1")
    model_e = AdvancedGBMModel("model_e_lightgbm_v1")
    try:
        active_ensemble_id = load_config().model.version_id
    except Exception:
        active_ensemble_id = "model_f_ensemble_v8"
    model_f = EnsembleStackingModel(active_ensemble_id)

    ml_calibrator = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    tot_calibrator = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    sp_calibrator = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    ml_va = VennAbersConformalInterval(window=1200, min_samples=25)
    tot_va = VennAbersConformalInterval(window=1200, min_samples=25)
    sp_va = VennAbersConformalInterval(window=1200, min_samples=25)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for m_id, m_fam, mkt in [
        (model_a.version_id, model_a.model_family, "moneyline"),
        (model_b.version_id, model_b.model_family, "moneyline"),
        (model_c.version_id, model_c.model_family, "moneyline"),
        (model_d.version_id, model_d.model_family, "total_points"),
        (model_e.version_id, model_e.model_family, "moneyline"),
        (model_f.version_id, model_f.model_family, "moneyline"),
    ]:
        db.execute_insert(
            """
            INSERT OR IGNORE INTO model_versions (
                model_version_id, model_family, market, train_start_date, train_end_date,
                trained_at, hyperparameters_json, oos_brier_score, oos_log_loss,
                is_active, approved_by, parent_version_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, 'orchestrator_walk_forward', NULL)
            """,
            (
                m_id,
                m_fam,
                mkt,
                matchdays[0] if matchdays else "2026-01-01",
                matchdays[min(len(matchdays) - 1, warmup_matchdays)] if matchdays else "2026-01-12",
                now_utc,
                json.dumps({"walk_forward": True}),
                1 if m_id in (model_c.version_id, model_d.version_id) else 0,
            ),
        )

    resolved_ml_cal_records: list[dict[str, Any]] = []
    resolved_tot_cal_records: list[dict[str, Any]] = []
    resolved_sp_cal_records: list[dict[str, Any]] = []
    model_comparison_records: list[dict[str, Any]] = []

    for day_idx, m_date in enumerate(matchdays):
        day_games = [g for g in sorted_games if g["matchday_date"] == m_date]
        if not day_games:
            continue

        cutoff_ts = min(g["game_start_time"] for g in day_games)
        prior_final_games = [
            g for g in sorted_games
            if g["status"] == "FINAL"
            and parse_iso_utc(g["game_start_time"]) < parse_iso_utc(cutoff_ts)
        ]

        if day_idx < warmup_matchdays:
            continue

        if (day_idx - warmup_matchdays) % retrain_every_matchdays == 0:
            model_a.fit(prior_final_games, cutoff_ts)
            model_c.fit(prior_final_games, cutoff_ts)
            model_d.fit(prior_final_games, cutoff_ts)
            model_e.fit(prior_final_games, cutoff_ts)
            model_f.fit(prior_final_games, cutoff_ts)
            if len(resolved_ml_cal_records) >= 25:
                ml_calibrator.fit(resolved_ml_cal_records, cutoff_ts)
                ml_va.fit(resolved_ml_cal_records, cutoff_ts)
            if len(resolved_tot_cal_records) >= 25:
                tot_calibrator.fit(resolved_tot_cal_records, cutoff_ts)
                tot_va.fit(resolved_tot_cal_records, cutoff_ts)
            if len(resolved_sp_cal_records) >= 25:
                sp_calibrator.fit(resolved_sp_cal_records, cutoff_ts)
                sp_va.fit(resolved_sp_cal_records, cutoff_ts)

        matchday_candidates: list[dict[str, Any]] = []

        for g in day_games:
            game_odds = odds_by_game.get(g["game_id"], [])
            start_dt = parse_iso_utc(g["game_start_time"])
            default_pred_dt = start_dt - (parse_iso_utc("2026-01-01T02:00:00Z") - parse_iso_utc("2026-01-01T00:00:00Z"))
            if game_odds:
                latest_odds_dt = max(parse_iso_utc(o["captured_at"]) for o in game_odds)
                pred_dt = max(default_pred_dt, latest_odds_dt)
            else:
                pred_dt = default_pred_dt
            feat_dt = parse_iso_utc(g["features_available_at"])
            pred_dt = max(pred_dt, feat_dt)
            if pred_dt >= start_dt:
                skipped_unpredictable_games += 1
                continue
            pred_ts = pred_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            validate_game_record(g, simulated_prediction_time=pred_ts)

            feats = build_pregame_features(g, prior_final_games, market="total_points")
            pred_a_ml = model_a.predict_moneyline(g, prior_final_games)
            pred_b_ml = model_b.predict_moneyline(g, prior_final_games)
            pred_e_ml = model_e.predict_moneyline(g, prior_final_games)
            pred_f_ml = model_f.predict_moneyline(g, prior_final_games)

            raw_p_home = pred_f_ml["p_home"]
            cal_p_home = ml_calibrator.transform_single(raw_p_home)
            cal_p_away = round(1.0 - cal_p_home, 6)
            va_home_int = ml_va.predict_interval(raw_p_home)

            tot_line_odds = [o for o in game_odds if o["market"] == "total_points" and o.get("line_value") is not None]
            has_obs_total = len(tot_line_odds) > 0
            line_val = float(tot_line_odds[0]["line_value"]) if has_obs_total else None

            pred_a_tot = model_a.predict_total_points(g, prior_final_games, line_val) if line_val is not None else None
            pred_e_tot = model_e.predict_total_points(g, prior_final_games, line_val) if line_val is not None else None
            pred_f_tot = model_f.predict_total_points(g, prior_final_games, line_val) if line_val is not None else None

            raw_p_over = float(pred_f_tot["p_over"]) if pred_f_tot is not None else None
            cal_p_over = float(tot_calibrator.transform_single(raw_p_over)) if raw_p_over is not None else None

            tot_eval_cache: dict[float, dict[str, Any]] = {}
            for o in tot_line_odds:
                lv_k = round(float(o["line_value"]), 2)
                if lv_k not in tot_eval_cache:
                    p_tot_k = model_f.predict_total_points(g, prior_final_games, lv_k)
                    r_over_k = float(p_tot_k["p_over"])
                    p_push_k = float(p_tot_k.get("p_push", 0.0))
                    cal_tot_res = calibrate_binary_with_push(
                        r_over_k, p_push=p_push_k, calibrator=tot_calibrator, va_calibrator=tot_va,
                    )
                    tot_eval_cache[lv_k] = {
                        "pred": p_tot_k,
                        "raw_over": r_over_k,
                        "cal_over": float(cal_tot_res["cal_prob"]),
                        "p_push": p_push_k,
                        "va": cal_tot_res["va_interval"],
                    }

            sp_odds = [o for o in game_odds if o["market"] == "spread" and o.get("line_value") is not None]
            sp_eval_cache: dict[float, dict[str, Any]] = {}
            for o in sp_odds:
                h_line_k = round(float(o["line_value"]) if o["selection"] == "HOME" else -float(o["line_value"]), 2)
                if h_line_k not in sp_eval_cache:
                    p_sp_k = model_f.predict_spread(g, prior_final_games, h_line_k)
                    r_sp_home = float(p_sp_k["p_cover_home"])
                    p_push_sp = float(p_sp_k.get("p_push", 0.0))
                    cal_sp_res = calibrate_binary_with_push(
                        r_sp_home, p_push=p_push_sp, calibrator=sp_calibrator, va_calibrator=sp_va,
                    )
                    sp_eval_cache[h_line_k] = {
                        "pred": p_sp_k,
                        "raw_home": r_sp_home,
                        "cal_home": float(cal_sp_res["cal_prob"]),
                        "p_push": p_push_sp,
                        "va": cal_sp_res["va_interval"],
                    }

            market_p_home = anchored_p_home = None
            market_p_over = anchored_p_over = None
            market_p_sp_home = anchored_p_sp_home = None
            first_sp_line: float | None = (
                round(float(sp_odds[0]["line_value"]) if sp_odds[0]["selection"] == "HOME" else -float(sp_odds[0]["line_value"]), 2)
                if sp_odds
                else None
            )
            for o in game_odds:
                validate_odds_record(o, g["game_start_time"], simulated_prediction_time=pred_ts)
                mkt = o["market"]
                sel = o["selection"]
                row_p_push = 0.0

                if mkt == "moneyline":
                    raw_p = raw_p_home if sel == "HOME" else round(1.0 - raw_p_home, 6)
                    cal_p = cal_p_home if sel == "HOME" else cal_p_away
                    unc = pred_f_ml["uncertainty_std"]
                    conf_int = va_home_int if sel == "HOME" else _flip_conformal_interval(va_home_int)
                elif mkt == "total_points":
                    te = tot_eval_cache[round(float(o["line_value"]), 2)]
                    row_p_push = float(te["p_push"])
                    raw_p = float(te["raw_over"]) if sel == "OVER" else round(max(0.0, 1.0 - float(te["raw_over"]) - row_p_push), 6)
                    cal_p = float(te["cal_over"]) if sel == "OVER" else round(max(0.0, 1.0 - float(te["cal_over"]) - row_p_push), 6)
                    unc = te["pred"]["uncertainty_std"]
                    conf_int = te["va"] if sel == "OVER" else _flip_conformal_interval(te["va"])
                else:
                    se = sp_eval_cache[round(float(o["line_value"]) if sel == "HOME" else -float(o["line_value"]), 2)]
                    row_p_push = float(se["p_push"])
                    raw_p = float(se["raw_home"]) if sel == "HOME" else round(max(0.0, 1.0 - float(se["raw_home"]) - row_p_push), 6)
                    cal_p = float(se["cal_home"]) if sel == "HOME" else round(max(0.0, 1.0 - float(se["cal_home"]) - row_p_push), 6)
                    unc = se["pred"]["uncertainty_std"]
                    conf_int = se["va"] if sel == "HOME" else _flip_conformal_interval(se["va"])

                opp = evaluate_market_opportunity(
                    estimated_prob=cal_p,
                    raw_model_prob=raw_p,
                    uncertainty_std=unc,
                    odds_record=o,
                    game_start_time=g["game_start_time"],
                    model_version_id=model_f.version_id,
                    simulated_prediction_time=pred_ts,
                    conformal_interval=conf_int,
                    p_push=row_p_push,
                )

                pred_id = f"PRED_{model_f.version_id}_{o['odds_id']}"
                db.execute_insert(
                    """
                    INSERT OR IGNORE INTO predictions (
                        prediction_id, game_id, market, selection, line_value,
                        model_version_id, raw_probability, calibrated_probability,
                        raw_model_probability, calibrated_model_probability,
                        market_fair_probability, market_anchored_probability,
                        uncertainty_std, implied_prob_gross, implied_prob_fair,
                        bookmaker_overround, decimal_odds_used, odds_provider,
                        odds_captured_at, ev_unit, ev_pct, emitted_at, features_snapshot_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pred_id,
                        g["game_id"],
                        mkt,
                        sel,
                        o.get("line_value"),
                        model_f.version_id,
                        raw_p,
                        opp["market_anchored_probability"],
                        opp["raw_model_probability"],
                        opp["calibrated_model_probability"],
                        opp["market_fair_probability"],
                        opp["market_anchored_probability"],
                        unc,
                        opp["implied_prob_gross"],
                        opp["implied_prob_fair"],
                        opp["bookmaker_overround"],
                        opp["decimal_odds_used"],
                        opp["odds_provider"],
                        opp["odds_captured_at"],
                        opp["ev_unit"],
                        opp["ev_pct"],
                        pred_ts,
                        json.dumps(feats),
                    ),
                )

                opp["prediction_id"] = pred_id
                opp["raw_probability"] = raw_p
                opp["calibrated_probability"] = opp["market_anchored_probability"]
                opp["emitted_at"] = pred_ts
                matchday_candidates.append(opp)
                if mkt == "moneyline" and sel == "HOME" and opp.get("implied_prob_fair") is not None:
                    market_p_home = float(opp["implied_prob_fair"])
                    anchored_p_home = float(opp["market_anchored_probability"])
                elif mkt == "total_points" and sel == "OVER" and opp.get("implied_prob_fair") is not None:
                    market_p_over = float(opp["implied_prob_fair"])
                    anchored_p_over = float(opp["market_anchored_probability"])
                elif mkt == "spread" and sel == "HOME" and opp.get("implied_prob_fair") is not None:
                    market_p_sp_home = float(opp["implied_prob_fair"])
                    anchored_p_sp_home = float(opp["market_anchored_probability"])

            if g["status"] == "FINAL" and g["home_score"] is not None and g["away_score"] is not None:
                home_won = 1 if g["home_score"] > g["away_score"] else 0
                total_pts = int(g["home_score"]) + int(g["away_score"])
                over_hit: int | None = None
                if line_val is not None and abs(total_pts - line_val) > 1e-9:
                    over_hit = 1 if total_pts > line_val else 0

                resolved_ml_cal_records.append(
                    {
                        "game_id": g["game_id"],
                        "game_start_time": g["game_start_time"],
                        "result_recorded_at": g.get("result_recorded_at"),
                        "raw_probability": raw_p_home,
                        "calibrated_probability": cal_p_home,
                        "baseline_probability": pred_a_ml["p_home"],
                        "outcome": home_won,
                    }
                )
                if over_hit is not None and raw_p_over is not None and cal_p_over is not None and pred_a_tot is not None:
                    resolved_tot_cal_records.append(
                        {
                            "game_id": g["game_id"],
                            "game_start_time": g["game_start_time"],
                            "result_recorded_at": g.get("result_recorded_at"),
                            "raw_probability": raw_p_over,
                            "calibrated_probability": cal_p_over,
                            "baseline_probability": pred_a_tot["p_over"],
                            "line_value": line_val,
                            "outcome": over_hit,
                        }
                    )
                spread_hit: int | None = None
                sp_raw_rec = sp_cal_rec = None
                if first_sp_line is not None:
                    adj_sp = (int(g["home_score"]) - int(g["away_score"])) + first_sp_line
                    se_first = sp_eval_cache[first_sp_line]
                    sp_raw_rec = se_first["raw_home"]
                    sp_cal_rec = se_first["cal_home"]
                    if abs(adj_sp) > 1e-9:
                        spread_hit = 1 if adj_sp > 0.0 else 0
                        resolved_sp_cal_records.append(
                            {
                                "game_id": g["game_id"],
                                "game_start_time": g["game_start_time"],
                                "result_recorded_at": g.get("result_recorded_at"),
                                "raw_probability": sp_raw_rec,
                                "calibrated_probability": sp_cal_rec,
                                "line_value": first_sp_line,
                                "outcome": spread_hit,
                            }
                        )
                model_comparison_records.append(
                    {
                        "game_id": g["game_id"],
                        "season": g["season"],
                        "matchday_date": g["matchday_date"],
                        "home_won": home_won,
                        "over_hit": over_hit if over_hit is not None else (1 if total_pts > (line_val or 228.5) else 0),
                        "has_observed_tot_line": over_hit is not None,
                        "spread_hit": spread_hit,
                        "model_a_ml": pred_a_ml["p_home"],
                        "model_b_ml": pred_b_ml["p_home"],
                        "model_raw_ml": raw_p_home,
                        "model_cal_ml": cal_p_home,
                        "model_c_ml": cal_p_home,
                        "model_anchored_ml": anchored_p_home,
                        "model_e_ml": pred_e_ml["p_home"],
                        "model_a_tot": pred_a_tot["p_over"] if pred_a_tot else None,
                        "model_raw_tot": raw_p_over,
                        "model_cal_tot": cal_p_over,
                        "model_d_tot": cal_p_over,
                        "model_anchored_tot": anchored_p_over,
                        "model_e_tot": pred_e_tot["p_over"] if pred_e_tot else None,
                        "market_ml": market_p_home,
                        "market_tot": market_p_over,
                        "model_raw_sp": sp_raw_rec,
                        "model_cal_sp": sp_cal_rec,
                        "market_sp": market_p_sp_home,
                        "model_anchored_sp": anchored_p_sp_home,
                    }
                )

        day_result = paper_engine.evaluate_and_record_matchday_selections(
            matchday_date=m_date,
            candidate_predictions=matchday_candidates,
        )

        games_lookup = {g["game_id"]: g for g in day_games}
        for placed in day_result["placed_bets"]:
            gm = games_lookup[placed["game_id"]]
            if gm["status"] in ("FINAL", "POSTPONED", "CANCELLED"):
                settle_ts = gm.get("result_recorded_at") or now_utc
                paper_engine.settle_bet(
                    bet_id=placed["bet_id"],
                    game_status=gm["status"],
                    home_score=gm["home_score"],
                    away_score=gm["away_score"],
                    settled_at=settle_ts,
                )

    return model_comparison_records, closing_rows, skipped_unpredictable_games
