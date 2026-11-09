"""
Temporal Walk-Forward Backtesting & Simulation Exit Gates (Sections 10 & 11):
- Reproduces strictly pre-game decisions in chronological order without lookahead
- Calculates ROI, Yield (documenting equivalence), Max Drawdown, Max Exposure, CLV
- Computes temporal Block Bootstrap (by matchday) 95% confidence intervals for ROI
- Evaluates the 9 pre-defined simulation exit gates (including >= 500 settled bets requirement)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from typing import Any
import numpy as np

from src.evaluation.clv import summarize_clv
from src.calibration.calibrator import (
    ProbabilityCalibrator,
    VennAbersConformalInterval,
    compute_brier_score,
    compute_log_loss,
    compute_reliability_curve,
)
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


def compute_drawdown_series(
    initial_bankroll: float,
    settled_bets: list[dict[str, Any]],
) -> dict[str, float]:
    """Calculates peak-to-trough maximum drawdown in PEN and percentage across chronological settlements."""
    balance = float(initial_bankroll)
    peak = balance
    max_dd_pen = 0.0
    max_dd_pct = 0.0

    for b in settled_bets:
        balance += float(b.get("net_profit_pen") or 0.0)
        if balance > peak:
            peak = balance
        dd_pen = peak - balance
        dd_pct = (dd_pen / peak) * 100.0 if peak > 0 else 0.0
        if dd_pen > max_dd_pen:
            max_dd_pen = dd_pen
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

    return {
        "max_drawdown_pen": round(max_dd_pen, 4),
        "max_drawdown_pct": round(max_dd_pct, 4),
        "peak_bankroll_pen": round(peak, 4),
        "ending_bankroll_pen": round(balance, 4),
    }


def compute_block_bootstrap_roi_ci(
    settled_bets: list[dict[str, Any]],
    n_boot: int = 1000,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Computes 95% confidence interval for ROI/Yield using temporal block bootstrap
    grouped by matchday_date to preserve intra-day correlation across NBA games.
    """
    if not settled_bets:
        return {
            "n_settled": 0,
            "n_matchday_blocks": 0,
            "roi_ci_lower_95_pct": 0.0,
            "roi_ci_upper_95_pct": 0.0,
            "compatible_with_zero_edge": True,
            "method": "temporal_matchday_block_bootstrap",
        }

    blocks: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for b in settled_bets:
        blocks[b["matchday_date"]].append((float(b["net_profit_pen"] or 0.0), float(b["stake_pen"])))

    block_keys = sorted(blocks.keys())
    n_blocks = len(block_keys)
    if n_blocks < 2:
        total_profit = sum(p for b in blocks.values() for p, _ in b)
        total_stake = sum(s for b in blocks.values() for _, s in b)
        pt = (total_profit / total_stake * 100.0) if total_stake > 0 else 0.0
        return {
            "n_settled": len(settled_bets),
            "n_matchday_blocks": n_blocks,
            "roi_ci_lower_95_pct": round(pt - 25.0, 4),
            "roi_ci_upper_95_pct": round(pt + 25.0, 4),
            "compatible_with_zero_edge": True,
            "method": "temporal_matchday_block_bootstrap_insufficient_blocks",
        }

    rng = np.random.default_rng(seed)
    boot_rois: list[float] = []
    for _ in range(n_boot):
        sampled_indices = rng.integers(0, n_blocks, size=n_blocks)
        prof_sum = 0.0
        stake_sum = 0.0
        for idx in sampled_indices:
            for p, s in blocks[block_keys[int(idx)]]:
                prof_sum += p
                stake_sum += s
        if stake_sum > 0:
            boot_rois.append((prof_sum / stake_sum) * 100.0)

    low_95 = float(np.percentile(boot_rois, 2.5))
    high_95 = float(np.percentile(boot_rois, 97.5))
    low_90 = float(np.percentile(boot_rois, 5.0))
    high_90 = float(np.percentile(boot_rois, 95.0))
    compatible_with_zero = bool(low_95 <= 0.0)

    return {
        "n_settled": len(settled_bets),
        "n_matchday_blocks": n_blocks,
        "roi_ci_lower_95_pct": round(low_95, 4),
        "roi_ci_upper_95_pct": round(high_95, 4),
        "roi_ci_lower_90_pct": round(low_90, 4),
        "roi_ci_upper_90_pct": round(high_90, 4),
        "compatible_with_zero_edge": compatible_with_zero,
        "method": "temporal_matchday_block_bootstrap",
    }


def evaluate_simulation_exit_gates(
    metrics: dict[str, Any],
    leakage_violations: int = 0,
    integrity_errors: int = 0,
    reproducibility_verified: bool = False,
    auditor_approved: bool = False,
    min_settled_required: int = 500,
) -> dict[str, Any]:
    """
    Evaluates the pre-defined validation gates from Section 11 plus a market benchmark gate.
    Fail-closed: a missing metric FAILS its gate (it is never replaced by a passing default).
    Never modifies acceptance criteria retroactively and never automates transition to real money.
    """

    def _f(key: str) -> float | None:
        val = metrics.get(key)
        return None if val is None else float(val)

    settled_count = int(metrics.get("settled_bets_count") or 0)
    oos_periods = int(metrics.get("oos_seasons_evaluated") or 0)
    model_brier = _f("overall_brier_score")
    base_brier = _f("baseline_brier_score")
    model_ll = _f("overall_log_loss")
    base_ll = _f("baseline_log_loss")
    mkt_brier = _f("market_brier_score")
    mkt_ll = _f("market_log_loss")
    model_brier_sub = _f("model_brier_on_market_subset")
    model_ll_sub = _f("model_log_loss_on_market_subset")
    roi_pct = float(metrics.get("roi_pct") or 0.0)
    yield_pct = float(metrics.get("yield_pct", 0.0))
    ci_info = metrics.get("bootstrap_uncertainty", {})
    ci_excludes_zero = not bool(ci_info.get("compatible_with_zero_edge", True))

    gates: dict[str, dict[str, Any]] = {
        "gate_1_min_500_settled_selections": {
            "passed": settled_count >= min_settled_required,
            "observed": settled_count,
            "required": f">= {min_settled_required}",
        },
        "gate_2_multi_period_oos_evaluation": {
            "passed": oos_periods >= 2,
            "observed": oos_periods,
            "required": ">= 2 temporal periods/seasons",
        },
        "gate_3_calibration_non_inferior_to_baseline": {
            "passed": (
                None not in (model_brier, base_brier, model_ll, base_ll)
                and model_brier <= base_brier  # type: ignore[operator]
                and model_ll <= base_ll  # type: ignore[operator]
            ),
            "observed": {"model_brier": model_brier, "baseline_brier": base_brier, "model_log_loss": model_ll, "baseline_log_loss": base_ll},
            "required": "model Brier <= baseline Brier AND model LogLoss <= baseline LogLoss",
        },
        "gate_4_zero_information_leakage": {
            "passed": leakage_violations == 0,
            "observed": leakage_violations,
            "required": 0,
        },
        "gate_5_positive_roi_and_yield": {
            "passed": roi_pct > 0.0 and yield_pct > 0.0,
            "observed": {"roi_pct": roi_pct, "yield_pct": yield_pct},
            "required": "ROI > 0% and Yield > 0%",
        },
        "gate_6_statistical_uncertainty_excludes_zero_edge": {
            "passed": ci_excludes_zero,
            "observed": {
                "ci_95_lower_pct": ci_info.get("roi_ci_lower_95_pct"),
                "ci_95_upper_pct": ci_info.get("roi_ci_upper_95_pct"),
                "compatible_with_zero_edge": ci_info.get("compatible_with_zero_edge"),
            },
            "required": "95% block bootstrap CI lower bound > 0%",
        },
        "gate_7_reproducible_results": {
            "passed": bool(reproducibility_verified),
            "observed": bool(reproducibility_verified),
            "required": True,
        },
        "gate_8_data_and_odds_integrity": {
            "passed": integrity_errors == 0,
            "observed": integrity_errors,
            "required": 0,
        },
        "gate_9_independent_audit_approved": {
            "passed": bool(auditor_approved),
            "observed": bool(auditor_approved),
            "required": True,
        },
        "gate_10_non_inferior_to_devigged_market": {
            "passed": (
                None not in (mkt_brier, mkt_ll, model_brier_sub, model_ll_sub)
                and model_brier_sub <= mkt_brier  # type: ignore[operator]
                and model_ll_sub <= mkt_ll  # type: ignore[operator]
            ),
            "observed": {
                "model_brier": model_brier_sub,
                "market_brier": mkt_brier,
                "model_log_loss": model_ll_sub,
                "market_log_loss": mkt_ll,
                "sample_size": metrics.get("market_comparison_sample_size"),
            },
            "required": "model Brier/LogLoss <= de-vigged market Brier/LogLoss on the same games",
        },
    }

    all_passed = all(g["passed"] for g in gates.values())
    failed_gates = [name for name, g in gates.items() if not g["passed"]]

    return {
        "all_gates_passed": all_passed,
        "failed_gates": failed_gates,
        "recommendation": (
            "ELIGIBLE_FOR_HUMAN_COMMITTEE_REVIEW_ONLY"
            if all_passed
            else "REMAIN_IN_PAPER_TRADING"
        ),
        "auto_transition_to_real_money": False,
        "gates": gates,
    }


class WalkForwardBacktester:
    """
    Executes a chronological walk-forward simulation across matchdays,
    comparing Models A-E, calibrating without leakage, and executing S/100 virtual paper trading.
    """

    def __init__(
        self,
        db: DatabaseManager,
        paper_engine: PaperTradingEngine,
        warmup_matchdays: int = 12,
        retrain_every_matchdays: int = 10,
    ) -> None:
        self.db = db
        self.paper_engine = paper_engine
        self.warmup_matchdays = warmup_matchdays
        self.retrain_every_matchdays = retrain_every_matchdays

    def run_walk_forward(
        self,
        games: list[dict[str, Any]],
        odds: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Runs chronological walk-forward evaluation and populates SQLite audit tables.

        The paper engine is switched to backtest mode (historical FINAL games are bettable) only for
        the duration of this call, so a shared production engine is never left in backtest mode.
        """
        previous_mode = bool(getattr(self.paper_engine, "is_backtest", False))
        self.paper_engine.is_backtest = True
        try:
            return self._run_walk_forward_impl(games, odds)
        finally:
            self.paper_engine.is_backtest = previous_mode

    def _run_walk_forward_impl(
        self,
        games: list[dict[str, Any]],
        odds: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sorted_games = sorted(games, key=lambda g: g["game_start_time"])
        skipped_unpredictable_games = 0

        # Ensure all games are persisted in SQLite so foreign key constraints on predictions/bets hold
        with self.db.connect() as conn:
            for g in sorted_games:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO games (
                        game_id, season, matchday_date, game_start_time, home_team, away_team,
                        status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
                        away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
                        features_available_at, source_provider, ingested_at, result_recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        model_f = EnsembleStackingModel("model_f_ensemble_v2")

        ml_calibrator = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
        tot_calibrator = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
        ml_va = VennAbersConformalInterval(window=1200, min_samples=25)
        tot_va = VennAbersConformalInterval(window=1200, min_samples=25)

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for m_id, m_fam, mkt in [
            (model_a.version_id, model_a.model_family, "moneyline"),
            (model_b.version_id, model_b.model_family, "moneyline"),
            (model_c.version_id, model_c.model_family, "moneyline"),
            (model_d.version_id, model_d.model_family, "total_points"),
            (model_e.version_id, model_e.model_family, "moneyline"),
            (model_f.version_id, model_f.model_family, "moneyline"),
        ]:
            self.db.execute_insert(
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
                    matchdays[min(len(matchdays) - 1, self.warmup_matchdays)] if matchdays else "2026-01-12",
                    now_utc,
                    json.dumps({"walk_forward": True}),
                    1 if m_id in (model_c.version_id, model_d.version_id) else 0,
                ),
            )

        resolved_ml_cal_records: list[dict[str, Any]] = []
        resolved_tot_cal_records: list[dict[str, Any]] = []
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

            if day_idx < self.warmup_matchdays:
                continue

            # Periodic batch retraining & calibration update (Process B & C)
            if (day_idx - self.warmup_matchdays) % self.retrain_every_matchdays == 0:
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
                # A prediction can only be made once the game's pre-game features exist. Games first seen
                # as post-game results (features_available_at >= tip-off) are history only: never predicted.
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

                tot_line_odds = [o for o in game_odds if o["market"] == "total_points"]
                line_val = float(tot_line_odds[0]["line_value"]) if tot_line_odds else 228.5

                pred_a_tot = model_a.predict_total_points(g, prior_final_games, line_val)
                pred_e_tot = model_e.predict_total_points(g, prior_final_games, line_val)
                pred_f_tot = model_f.predict_total_points(g, prior_final_games, line_val)

                raw_p_over = pred_f_tot["p_over"]
                cal_p_over = tot_calibrator.transform_single(raw_p_over)
                cal_p_under = round(1.0 - cal_p_over, 6)
                va_over_int = tot_va.predict_interval(raw_p_over)

                market_p_home: float | None = None
                market_p_over: float | None = None
                for o in game_odds:
                    validate_odds_record(o, g["game_start_time"], simulated_prediction_time=pred_ts)
                    mkt = o["market"]
                    sel = o["selection"]

                    if mkt == "moneyline":
                        raw_p = raw_p_home if sel == "HOME" else round(1.0 - raw_p_home, 6)
                        cal_p = cal_p_home if sel == "HOME" else cal_p_away
                        unc = pred_f_ml["uncertainty_std"]
                        m_ver = model_f.version_id
                        conf_int = va_home_int if sel == "HOME" else {
                            "p0": round(1.0 - va_home_int["p1"], 6),
                            "p1": round(1.0 - va_home_int["p0"], 6),
                            "p_va": round(1.0 - va_home_int["p_va"], 6),
                            "width": va_home_int["width"],
                        }
                    else:
                        raw_p = raw_p_over if sel == "OVER" else round(1.0 - raw_p_over, 6)
                        cal_p = cal_p_over if sel == "OVER" else cal_p_under
                        unc = pred_f_tot["uncertainty_std"]
                        m_ver = model_f.version_id
                        conf_int = va_over_int if sel == "OVER" else {
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
                        conformal_interval=conf_int,
                    )

                    pred_id = f"PRED_{m_ver}_{o['odds_id']}"
                    self.db.execute_insert(
                        """
                        INSERT OR IGNORE INTO predictions (
                            prediction_id, game_id, market, selection, line_value,
                            model_version_id, raw_probability, calibrated_probability,
                            uncertainty_std, implied_prob_gross, implied_prob_fair,
                            bookmaker_overround, decimal_odds_used, odds_provider,
                            odds_captured_at, ev_unit, ev_pct, emitted_at, features_snapshot_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            pred_id,
                            g["game_id"],
                            mkt,
                            sel,
                            o.get("line_value"),
                            m_ver,
                            raw_p,
                            cal_p,
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
                    opp["calibrated_probability"] = cal_p
                    opp["emitted_at"] = pred_ts
                    matchday_candidates.append(opp)
                    if mkt == "moneyline" and sel == "HOME" and opp.get("implied_prob_fair") is not None:
                        market_p_home = float(opp["implied_prob_fair"])
                    elif mkt == "total_points" and sel == "OVER" and opp.get("implied_prob_fair") is not None:
                        market_p_over = float(opp["implied_prob_fair"])

                # If game finished, record outcome for subsequent matchday training/calibration
                if g["status"] == "FINAL" and g["home_score"] is not None and g["away_score"] is not None:
                    home_won = 1 if g["home_score"] > g["away_score"] else 0
                    over_hit = 1 if (g["home_score"] + g["away_score"]) > line_val else 0

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
                    resolved_tot_cal_records.append(
                        {
                            "game_id": g["game_id"],
                            "game_start_time": g["game_start_time"],
                            "result_recorded_at": g.get("result_recorded_at"),
                            "raw_probability": raw_p_over,
                            "calibrated_probability": cal_p_over,
                            "baseline_probability": pred_a_tot["p_over"],
                            "outcome": over_hit,
                        }
                    )
                    model_comparison_records.append(
                        {
                            "game_id": g["game_id"],
                            "season": g["season"],
                            "matchday_date": g["matchday_date"],
                            "home_won": home_won,
                            "over_hit": over_hit,
                            "model_a_ml": pred_a_ml["p_home"],
                            "model_b_ml": pred_b_ml["p_home"],
                            "model_c_ml": cal_p_home,
                            "model_e_ml": pred_e_ml["p_home"],
                            "model_a_tot": pred_a_tot["p_over"],
                            "model_d_tot": cal_p_over,
                            "model_e_tot": pred_e_tot["p_over"],
                            "market_ml": market_p_home,
                            "market_tot": market_p_over,
                        }
                    )

            # Paper trading selection for this matchday
            day_result = self.paper_engine.evaluate_and_record_matchday_selections(
                matchday_date=m_date,
                candidate_predictions=matchday_candidates,
            )

            # Settle placed bets if the matchday's games are FINAL
            games_lookup = {g["game_id"]: g for g in day_games}
            for placed in day_result["placed_bets"]:
                gm = games_lookup[placed["game_id"]]
                if gm["status"] in ("FINAL", "POSTPONED", "CANCELLED"):
                    settle_ts = gm.get("result_recorded_at") or now_utc
                    self.paper_engine.settle_bet(
                        bet_id=placed["bet_id"],
                        game_status=gm["status"],
                        home_score=gm["home_score"],
                        away_score=gm["away_score"],
                        settled_at=settle_ts,
                    )

        metrics = self.compute_comprehensive_metrics(
            model_comparison_records=model_comparison_records,
            closing_rows=closing_rows,
        )
        metrics["skipped_unpredictable_games"] = skipped_unpredictable_games
        return metrics

    def _reconstruct_comparison_records_from_db(self) -> list[dict[str, Any]]:
        """
        One record per real FINAL game using the LATEST observed pre-tip prediction of each market.
        Fields: naive baseline, calibrated ensemble probability (as stored), raw ensemble probability and
        the de-vigged market probability of the same odds snapshot. Nothing is synthesized: when a value
        is missing it stays None and the corresponding metric is not computed.
        """
        rows = self.db.fetch_all(
            """
            WITH latest AS (
                SELECT p.*, ROW_NUMBER() OVER (
                    PARTITION BY p.game_id, p.market ORDER BY p.emitted_at DESC, p.prediction_id DESC
                ) AS rn
                FROM v_observed_predictions p
                WHERE (p.market = 'moneyline' AND p.selection = 'HOME')
                   OR (p.market = 'total_points' AND p.selection = 'OVER')
            )
            SELECT l.game_id, l.market, l.raw_probability, l.calibrated_probability, l.implied_prob_fair,
                   l.line_value, g.season, g.matchday_date, g.game_start_time, g.home_score, g.away_score
            FROM latest l JOIN games g ON g.game_id = l.game_id
            WHERE l.rn = 1 AND g.status = 'FINAL' AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
              AND l.game_id NOT LIKE 'SYN%'
            """
        )
        by_game: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for r in rows:
            by_game[r["game_id"]][r["market"]] = r
        all_final_games = self.db.fetch_all(
            "SELECT * FROM games WHERE status = 'FINAL' AND home_score IS NOT NULL ORDER BY game_start_time ASC"
        )
        games_idx = {g["game_id"]: g for g in all_final_games}
        base_model = BaselineModel("model_a_baseline_v1")
        out: list[dict[str, Any]] = []
        for gid, mk in sorted(by_game.items(), key=lambda kv: str(next(iter(kv[1].values()))["game_start_time"])):
            ml = mk.get("moneyline")
            tot = mk.get("total_points")
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
            out.append(
                {
                    "game_id": gid,
                    "season": ml["season"],
                    "matchday_date": ml["matchday_date"],
                    "home_won": 1 if int(g_full["home_score"]) > int(g_full["away_score"]) else 0,
                    "over_hit": 1 if total_pts > line_v else 0,
                    "model_a_ml": base_model.predict_moneyline(g_full, prior_g)["p_home"],
                    "model_raw_ml": float(ml["raw_probability"]),
                    "model_c_ml": float(ml["calibrated_probability"]),
                    "market_ml": float(ml["implied_prob_fair"]) if ml.get("implied_prob_fair") is not None else None,
                    "model_a_tot": base_model.predict_total_points(g_full, prior_g, line_v)["p_over"],
                    "model_d_tot": float(tot["calibrated_probability"]),
                    "market_tot": float(tot["implied_prob_fair"]) if tot.get("implied_prob_fair") is not None else None,
                }
            )
        return out

    @staticmethod
    def _score(probs: list[float], outcomes: list[int], with_curve: bool = False) -> dict[str, Any]:
        if with_curve:
            return compute_reliability_curve(probs, outcomes)
        return {
            "sample_size": len(probs),
            "brier_score": compute_brier_score(probs, outcomes),
            "log_loss": compute_log_loss(probs, outcomes),
        }

    def compute_comprehensive_metrics(
        self,
        model_comparison_records: list[dict[str, Any]] | None = None,
        closing_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Computes Section 10 & 11 metrics.
        - Bets: only bets placed on OBSERVED odds (`v_observed_simulated_bets`), within the engine scope.
        - Model quality: the calibrated ensemble vs. the naive baseline AND vs. the de-vigged market on the
          same games. Beating the naive baseline is necessary but meaningless on its own; the market is
          the benchmark that matters.
        - Missing data yields None (never a default that would pass a gate).
        """
        if not model_comparison_records:
            model_comparison_records = self._reconstruct_comparison_records_from_db()
        if getattr(self.paper_engine, "exclude_synthetic", False):
            model_comparison_records = [
                r for r in model_comparison_records if not str(r["game_id"]).startswith("SYN")
            ]

        # Production scope (exclude_synthetic=True): only bets placed on OBSERVED odds count.
        # Simulation scope (synthetic walk-forward): every bet is synthetic by construction.
        production_scope = bool(getattr(self.paper_engine, "exclude_synthetic", False))
        bets_source = "v_observed_simulated_bets" if production_scope else "simulated_bets"
        all_bets = self.db.fetch_all(
            f"SELECT * FROM {bets_source} WHERE {getattr(self.paper_engine, 'scope_sql', '1 = 1')} "
            "ORDER BY emitted_at ASC"
        )
        settled_bets = [b for b in all_bets if b["status"] in ("WON", "LOST", "PUSH", "VOID")]
        pending_bets = [b for b in all_bets if b["status"] == "PENDING"]

        won_count = sum(1 for b in settled_bets if b["status"] == "WON")
        lost_count = sum(1 for b in settled_bets if b["status"] == "LOST")
        push_count = sum(1 for b in settled_bets if b["status"] == "PUSH")
        void_count = sum(1 for b in settled_bets if b["status"] == "VOID")

        net_profit = round(sum(float(b["net_profit_pen"] or 0.0) for b in settled_bets), 4)
        # VOID stakes are returned, so they are not "risked" capital for ROI purposes.
        settled_stakes = round(sum(float(b["stake_pen"]) for b in settled_bets if b["status"] != "VOID"), 4)
        total_wagered = round(sum(float(b["stake_pen"]) for b in all_bets if b["status"] != "VOID"), 4)

        roi_pct = round((net_profit / settled_stakes) * 100.0, 4) if settled_stakes > 0 else 0.0
        yield_pct = round((net_profit / total_wagered) * 100.0, 4) if total_wagered > 0 else 0.0
        avg_odds = round(float(np.mean([float(b["decimal_odds"]) for b in settled_bets])), 4) if settled_bets else 0.0

        settled_chrono = sorted(settled_bets, key=lambda b: str(b.get("settled_at") or b.get("emitted_at") or ""))
        dd_info = compute_drawdown_series(self.paper_engine.initial_bankroll_pen, settled_chrono)
        boot_ci = compute_block_bootstrap_roi_ci([b for b in settled_bets if b["status"] != "VOID"])

        ledger_rows = self.db.fetch_all("SELECT MAX(pending_exposure_pen) AS max_exp FROM bankroll_ledger")
        max_exposure = float(ledger_rows[0]["max_exp"] or 0.0) if ledger_rows else 0.0

        # Closing Line Value in probability space against the de-vigged observed close.
        if closing_rows is None:
            odds_source = "v_observed_odds_snapshots" if production_scope else "odds_snapshots"
            closing_rows = self.db.fetch_all(
                f"""
                SELECT game_id, market, selection, line_value, decimal_odds, counterpart_decimal_odds, provider, captured_at
                FROM {odds_source} WHERE is_closing_line = 1
                """
            )
        bet_providers = {
            r["prediction_id"]: r["odds_provider"]
            for r in self.db.fetch_all("SELECT prediction_id, odds_provider FROM predictions")
        }
        clv = summarize_clv([b for b in settled_bets if b["status"] != "VOID"], closing_rows, bet_providers)

        by_market: dict[str, dict[str, Any]] = {}
        for mkt in ("moneyline", "total_points"):
            m_bets = [b for b in settled_bets if b["market"] == mkt]
            m_prof = round(sum(float(b["net_profit_pen"] or 0.0) for b in m_bets), 4)
            m_stakes = round(sum(float(b["stake_pen"]) for b in m_bets if b["status"] != "VOID"), 4)
            by_market[mkt] = {
                "settled_count": len(m_bets),
                "won": sum(1 for b in m_bets if b["status"] == "WON"),
                "lost": sum(1 for b in m_bets if b["status"] == "LOST"),
                "push": sum(1 for b in m_bets if b["status"] == "PUSH"),
                "net_profit_pen": m_prof,
                "roi_pct": round((m_prof / m_stakes) * 100.0, 4) if m_stakes > 0 else 0.0,
            }

        games_map = {g["game_id"]: g for g in self.db.fetch_all("SELECT game_id, season FROM games")}
        by_season: dict[str, dict[str, Any]] = defaultdict(lambda: {"settled_count": 0, "net_profit_pen": 0.0, "stakes_pen": 0.0})
        for b in settled_bets:
            seas = games_map.get(b["game_id"], {}).get("season", "unknown")
            by_season[seas]["settled_count"] += 1
            by_season[seas]["net_profit_pen"] = round(by_season[seas]["net_profit_pen"] + float(b["net_profit_pen"] or 0.0), 4)
            if b["status"] != "VOID":
                by_season[seas]["stakes_pen"] = round(by_season[seas]["stakes_pen"] + float(b["stake_pen"]), 4)
        for _seas, sdata in by_season.items():
            sdata["roi_pct"] = round((sdata["net_profit_pen"] / sdata["stakes_pen"]) * 100.0, 4) if sdata["stakes_pen"] > 0 else 0.0

        model_metrics: dict[str, Any] = {}
        overall_brier = baseline_brier = overall_ll = baseline_ll = overall_ece = None
        market_brier = market_ll = model_brier_mkt_subset = model_ll_mkt_subset = None
        market_subset_n = 0
        recs = model_comparison_records
        if recs:
            y_ml = [int(r["home_won"]) for r in recs]
            y_tot = [int(r["over_hit"]) for r in recs]
            model_metrics["baseline_naive_ml"] = self._score([r["model_a_ml"] for r in recs], y_ml)
            model_metrics["ensemble_calibrated_ml"] = self._score([r["model_c_ml"] for r in recs], y_ml, with_curve=True)
            model_metrics["baseline_naive_totals"] = self._score([r["model_a_tot"] for r in recs], y_tot)
            model_metrics["ensemble_calibrated_totals"] = self._score([r["model_d_tot"] for r in recs], y_tot, with_curve=True)
            for field, key, ys in (
                ("model_raw_ml", "ensemble_raw_ml", y_ml),
                ("model_b_ml", "elo_ml", y_ml),
                ("model_e_ml", "lightgbm_ml", y_ml),
                ("model_e_tot", "lightgbm_totals", y_tot),
            ):
                if all(r.get(field) is not None for r in recs):
                    model_metrics[key] = self._score([float(r[field]) for r in recs], ys)

            sub = [r for r in recs if r.get("market_ml") is not None and r.get("market_tot") is not None]
            market_subset_n = len(sub)
            if sub:
                ys_ml = [int(r["home_won"]) for r in sub]
                ys_tot = [int(r["over_hit"]) for r in sub]
                m_ml = self._score([float(r["market_ml"]) for r in sub], ys_ml)
                m_tot = self._score([float(r["market_tot"]) for r in sub], ys_tot)
                e_ml = self._score([float(r["model_c_ml"]) for r in sub], ys_ml)
                e_tot = self._score([float(r["model_d_tot"]) for r in sub], ys_tot)
                model_metrics["market_devig_ml"] = m_ml
                model_metrics["market_devig_totals"] = m_tot
                market_brier = round(0.5 * (m_ml["brier_score"] + m_tot["brier_score"]), 6)
                market_ll = round(0.5 * (m_ml["log_loss"] + m_tot["log_loss"]), 6)
                model_brier_mkt_subset = round(0.5 * (e_ml["brier_score"] + e_tot["brier_score"]), 6)
                model_ll_mkt_subset = round(0.5 * (e_ml["log_loss"] + e_tot["log_loss"]), 6)

            ens_ml = model_metrics["ensemble_calibrated_ml"]
            ens_tot = model_metrics["ensemble_calibrated_totals"]
            overall_brier = round(0.5 * (ens_ml["brier_score"] + ens_tot["brier_score"]), 6)
            baseline_brier = round(
                0.5 * (model_metrics["baseline_naive_ml"]["brier_score"] + model_metrics["baseline_naive_totals"]["brier_score"]), 6
            )
            overall_ll = round(0.5 * (ens_ml["log_loss"] + ens_tot["log_loss"]), 6)
            baseline_ll = round(
                0.5 * (model_metrics["baseline_naive_ml"]["log_loss"] + model_metrics["baseline_naive_totals"]["log_loss"]), 6
            )
            overall_ece = round(0.5 * (ens_ml["ece"] + ens_tot["ece"]), 6)
        oos_seasons = len({r["season"] for r in recs}) if recs else 0

        live_settled_list = [b for b in settled_chrono if str(b["game_id"]).startswith("ESPN_")]
        live_espn_settled = len(live_settled_list)
        live_espn_pending = sum(1 for b in pending_bets if str(b["game_id"]).startswith("ESPN_"))
        live_dd_info = compute_drawdown_series(self.paper_engine.initial_bankroll_pen, live_settled_list)

        summary = {
            "initial_bankroll_pen": self.paper_engine.initial_bankroll_pen,
            "current_settled_bankroll_pen": dd_info["ending_bankroll_pen"],
            "net_profit_pen": net_profit,
            "settled_stakes_pen": settled_stakes,
            "total_wagered_pen": total_wagered,
            "roi_pct": roi_pct,
            "yield_pct": yield_pct,
            "roi_yield_equivalence_note": (
                "ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) "
                "are equivalent when all wagered bets are settled; they differ only while pending bets exist. "
                "VOID stakes are excluded (returned capital)."
            ),
            "bets_scope": (
                "v_observed_simulated_bets (bets placed on observed odds only)"
                if production_scope
                else "simulated_bets (synthetic simulation scope)"
            ),
            "settled_bets_count": len(settled_bets),
            "pending_bets_count": len(pending_bets),
            "live_espn_settled_bets_count": live_espn_settled,
            "live_espn_pending_bets_count": live_espn_pending,
            "won_count": won_count,
            "lost_count": lost_count,
            "push_count": push_count,
            "void_count": void_count,
            "average_decimal_odds": avg_odds,
            "max_drawdown_pen": dd_info["max_drawdown_pen"],
            "max_drawdown_pct": dd_info["max_drawdown_pct"],
            "live_max_drawdown_pct": live_dd_info["max_drawdown_pct"],
            "max_exposure_pen": round(max_exposure, 4),
            "mean_clv_pct": clv["mean_clv_pct"],
            "clv_beat_close_rate": clv["clv_beat_close_rate"],
            "clv_sample_size": clv["clv_sample_size"],
            "clv_outliers_excluded": clv["clv_outliers_excluded"],
            "clv_definition": clv["clv_definition"],
            "overall_brier_score": overall_brier,
            "baseline_brier_score": baseline_brier,
            "overall_log_loss": overall_ll,
            "baseline_log_loss": baseline_ll,
            "market_brier_score": market_brier,
            "market_log_loss": market_ll,
            "model_brier_on_market_subset": model_brier_mkt_subset,
            "model_log_loss_on_market_subset": model_ll_mkt_subset,
            "market_comparison_sample_size": market_subset_n,
            "overall_ece": overall_ece,
            "model_comparison_sample_size": len(recs) if recs else 0,
            "oos_seasons_evaluated": oos_seasons,
            "bootstrap_uncertainty": boot_ci,
            "performance_by_market": by_market,
            "performance_by_season": dict(by_season),
            "model_comparison": model_metrics,
        }

        summary["exit_gates_evaluation"] = evaluate_simulation_exit_gates(summary)
        return summary
