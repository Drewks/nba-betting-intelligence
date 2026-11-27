"""
Temporal Walk-Forward Backtesting & Simulation Exit Gates (Sections 10 & 11):
- Reproduces strictly pre-game decisions in chronological order without lookahead
- Calculates ROI, Yield (documenting equivalence), Max Drawdown, Max Exposure, CLV
- Computes temporal Block Bootstrap (by matchday) 95% confidence intervals for ROI
- Evaluates the pre-defined simulation exit gates (including >= 500 settled bets requirement)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
import numpy as np

from src.backtesting.metrics import (
    compute_block_bootstrap_roi_ci,
    compute_drawdown_series,
    evaluate_simulation_exit_gates,
    summarize_model_versions_from_db,
)
from src.backtesting.walk_forward_helpers import (
    reconstruct_comparison_records_from_db,
    run_walk_forward_simulation,
)
from src.calibration.calibrator import (
    compute_brier_score,
    compute_log_loss,
    compute_reliability_curve,
)
from src.config import load_config
from src.evaluation.clv import summarize_clv
from src.paper_trading.engine import PaperTradingEngine
from src.storage.db import DatabaseManager

__all__ = [
    "WalkForwardBacktester",
    "compute_block_bootstrap_roi_ci",
    "compute_drawdown_series",
    "compute_financial_and_statistical_metrics",
    "evaluate_simulation_exit_gates",
    "summarize_model_versions_from_db",
]


class WalkForwardBacktester:
    """
    Executes a chronological walk-forward simulation across matchdays,
    comparing Models A-E/F, calibrating without leakage, and executing S/100 virtual paper trading.
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
        model_comparison_records, closing_rows, skipped_unpredictable_games = run_walk_forward_simulation(
            db=self.db,
            paper_engine=self.paper_engine,
            warmup_matchdays=self.warmup_matchdays,
            retrain_every_matchdays=self.retrain_every_matchdays,
            games=games,
            odds=odds,
        )
        metrics = self.compute_comprehensive_metrics(
            model_comparison_records=model_comparison_records,
            closing_rows=closing_rows,
            calibration_evaluation_source="WALK_FORWARD_SIMULATION",
        )
        metrics["skipped_unpredictable_games"] = skipped_unpredictable_games
        return metrics

    def _reconstruct_comparison_records_from_db(
        self,
        model_version_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fail-closed DB reconstruction (T-021): pre-m012 legacy rows leave
        calibrated_model_probability as None so market anchoring is never conflated
        with model calibration. When `model_version_id` is supplied, strictly isolates
        that model version from older versions in `v_observed_predictions`.
        """
        return reconstruct_comparison_records_from_db(self.db, model_version_id=model_version_id)

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
        calibration_evaluation_source: str | None = None,
        model_version_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Computes Section 10 & 11 metrics.
        - Bets: only bets placed on OBSERVED odds (`v_observed_simulated_bets`), within the engine scope.
        - Model quality: calibrated ensemble vs. naive baseline AND vs. de-vigged market on matched games.
        - Missing data yields None (never a default that would pass a gate).
        """
        used_db_reconstruction = not model_comparison_records
        if not model_comparison_records:
            model_comparison_records = self._reconstruct_comparison_records_from_db(
                model_version_id=model_version_id
            )

        production_scope = bool(getattr(self.paper_engine, "exclude_synthetic", False)) or not bool(
            getattr(self.paper_engine, "is_backtest", False)
        )
        if production_scope:
            model_comparison_records = [
                r for r in model_comparison_records if not str(r["game_id"]).startswith("SYN")
            ]

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
        for mkt in ("moneyline", "total_points", "spread"):
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
        for sdata in by_season.values():
            sdata["roi_pct"] = round((sdata["net_profit_pen"] / sdata["stakes_pen"]) * 100.0, 4) if sdata["stakes_pen"] > 0 else 0.0

        model_metrics: dict[str, Any] = {}
        overall_brier = baseline_brier = overall_ll = baseline_ll = overall_ece = None
        market_brier = market_ll = model_brier_mkt_subset = model_ll_mkt_subset = None
        market_subset_n = 0
        recs = model_comparison_records
        if recs:
            y_ml = [int(r["home_won"]) for r in recs]
            tot_base_recs = [
                r for r in recs
                if r.get("has_observed_tot_line", True) and r.get("model_a_tot") is not None
            ]
            cal_ml_recs = [r for r in recs if r.get("model_c_ml") is not None]
            cal_tot_recs = [r for r in tot_base_recs if r.get("model_d_tot") is not None]

            model_metrics["baseline_naive_ml"] = self._score([r["model_a_ml"] for r in recs], y_ml)
            if cal_ml_recs:
                model_metrics["ensemble_calibrated_ml"] = self._score(
                    [float(r["model_c_ml"]) for r in cal_ml_recs],
                    [int(r["home_won"]) for r in cal_ml_recs],
                    with_curve=True,
                )
            if tot_base_recs:
                model_metrics["baseline_naive_totals"] = self._score(
                    [r["model_a_tot"] for r in tot_base_recs],
                    [int(r["over_hit"]) for r in tot_base_recs],
                )
            if cal_tot_recs:
                model_metrics["ensemble_calibrated_totals"] = self._score(
                    [float(r["model_d_tot"]) for r in cal_tot_recs],
                    [int(r["over_hit"]) for r in cal_tot_recs],
                    with_curve=True,
                )
            for field, key, subset, y_key in (
                ("model_raw_ml", "ensemble_raw_ml", recs, "home_won"),
                ("model_cal_ml", "ensemble_calibrated_model_ml", recs, "home_won"),
                ("model_anchored_ml", "ensemble_market_anchored_ml", recs, "home_won"),
                ("model_b_ml", "elo_ml", recs, "home_won"),
                ("model_e_ml", "lightgbm_ml", recs, "home_won"),
                ("model_raw_tot", "ensemble_raw_totals", tot_base_recs, "over_hit"),
                ("model_cal_tot", "ensemble_calibrated_model_totals", tot_base_recs, "over_hit"),
                ("model_anchored_tot", "ensemble_market_anchored_totals", tot_base_recs, "over_hit"),
                ("model_e_tot", "lightgbm_totals", tot_base_recs, "over_hit"),
                ("model_raw_sp", "ensemble_raw_spread", recs, "spread_hit"),
                ("model_cal_sp", "ensemble_calibrated_model_spread", recs, "spread_hit"),
                ("market_sp", "market_devig_spread", recs, "spread_hit"),
                ("model_anchored_sp", "ensemble_market_anchored_spread", recs, "spread_hit"),
            ):
                valid = [r for r in subset if r.get(field) is not None and r.get(y_key) is not None]
                if valid:
                    model_metrics[key] = self._score(
                        [float(r[field]) for r in valid],
                        [int(r[y_key]) for r in valid],
                        with_curve=(key in (
                            "ensemble_raw_ml",
                            "ensemble_calibrated_model_ml",
                            "ensemble_market_anchored_ml",
                            "ensemble_raw_totals",
                            "ensemble_calibrated_model_totals",
                            "ensemble_market_anchored_totals",
                        )),
                    )

            sub_mkt = [
                r for r in recs
                if r.get("market_ml") is not None
                and r.get("market_tot") is not None
                and r.get("has_observed_tot_line", True)
            ]
            sub_cal = [
                r for r in sub_mkt
                if r.get("model_c_ml") is not None and r.get("model_d_tot") is not None
            ]
            sub = sub_cal if sub_cal else sub_mkt
            market_subset_n = len(sub)
            if sub:
                ys_ml = [int(r["home_won"]) for r in sub]
                ys_tot = [int(r["over_hit"]) for r in sub]
                m_ml = self._score([float(r["market_ml"]) for r in sub], ys_ml, with_curve=True)
                m_tot = self._score([float(r["market_tot"]) for r in sub], ys_tot, with_curve=True)
                model_metrics["market_devig_ml"] = m_ml
                model_metrics["market_devig_totals"] = m_tot
                if all(r.get("model_raw_ml") is not None and r.get("model_raw_tot") is not None for r in sub):
                    model_metrics["common_subset_raw_ml"] = self._score([float(r["model_raw_ml"]) for r in sub], ys_ml, with_curve=True)
                    model_metrics["common_subset_raw_totals"] = self._score([float(r["model_raw_tot"]) for r in sub], ys_tot, with_curve=True)
                if all(r.get("model_cal_ml") is not None and r.get("model_cal_tot") is not None for r in sub):
                    model_metrics["common_subset_calibrated_model_ml"] = self._score([float(r["model_cal_ml"]) for r in sub], ys_ml, with_curve=True)
                    model_metrics["common_subset_calibrated_model_totals"] = self._score([float(r["model_cal_tot"]) for r in sub], ys_tot, with_curve=True)
                if all(r.get("model_anchored_ml") is not None and r.get("model_anchored_tot") is not None for r in sub):
                    model_metrics["common_subset_market_anchored_ml"] = self._score([float(r["model_anchored_ml"]) for r in sub], ys_ml, with_curve=True)
                    model_metrics["common_subset_market_anchored_totals"] = self._score([float(r["model_anchored_tot"]) for r in sub], ys_tot, with_curve=True)
                market_brier = round(0.5 * (m_ml["brier_score"] + m_tot["brier_score"]), 6)
                market_ll = round(0.5 * (m_ml["log_loss"] + m_tot["log_loss"]), 6)
                if sub_cal:
                    e_ml = self._score([float(r["model_c_ml"]) for r in sub_cal], ys_ml, with_curve=True)
                    e_tot = self._score([float(r["model_d_tot"]) for r in sub_cal], ys_tot, with_curve=True)
                    model_metrics["common_subset_ensemble_ml"] = e_ml
                    model_metrics["common_subset_ensemble_totals"] = e_tot
                    model_brier_mkt_subset = round(0.5 * (e_ml["brier_score"] + e_tot["brier_score"]), 6)
                    model_ll_mkt_subset = round(0.5 * (e_ml["log_loss"] + e_tot["log_loss"]), 6)

            ens_ml = model_metrics.get("ensemble_calibrated_ml")
            ens_tot = model_metrics.get("ensemble_calibrated_totals")
            base_ml_m = model_metrics["baseline_naive_ml"]
            base_tot_m = model_metrics.get("baseline_naive_totals")
            if base_tot_m is not None:
                baseline_brier = round(0.5 * (base_ml_m["brier_score"] + base_tot_m["brier_score"]), 6)
                baseline_ll = round(0.5 * (base_ml_m["log_loss"] + base_tot_m["log_loss"]), 6)
            else:
                baseline_brier = round(base_ml_m["brier_score"], 6)
                baseline_ll = round(base_ml_m["log_loss"], 6)
            if ens_ml is not None and ens_tot is not None:
                overall_brier = round(0.5 * (ens_ml["brier_score"] + ens_tot["brier_score"]), 6)
                overall_ll = round(0.5 * (ens_ml["log_loss"] + ens_tot["log_loss"]), 6)
                overall_ece = round(0.5 * (ens_ml["ece"] + ens_tot["ece"]), 6)
            elif ens_ml is not None:
                overall_brier = round(ens_ml["brier_score"], 6)
                overall_ll = round(ens_ml["log_loss"], 6)
                overall_ece = round(ens_ml["ece"], 6)
        oos_seasons = len({r["season"] for r in recs}) if recs else 0

        try:
            active_model_version_id = load_config().model.version_id
        except Exception:
            active_model_version_id = "model_f_ensemble_v9"
        by_model_version = summarize_model_versions_from_db(
            self.db,
            active_model_version_id=active_model_version_id,
        )
        if calibration_evaluation_source is not None:
            resolved_eval_source = calibration_evaluation_source
        elif used_db_reconstruction:
            resolved_eval_source = (
                "DB_OBSERVED_PREDICTIONS_M012"
                if overall_brier is not None
                else "INSUFFICIENT_M012_OBSERVED_PREDICTIONS"
            )
        else:
            resolved_eval_source = (
                "PROVIDED_COMPARISON_RECORDS"
                if overall_brier is not None
                else "INSUFFICIENT_M012_COMPARISON_RECORDS"
            )

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
            "active_model_version_id": active_model_version_id,
            "by_model_version": by_model_version,
            "calibration_evaluation_source": resolved_eval_source,
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

    def compute_financial_and_statistical_metrics(
        self,
        model_comparison_records: list[dict[str, Any]] | None = None,
        closing_rows: list[dict[str, Any]] | None = None,
        calibration_evaluation_source: str | None = None,
        model_version_id: str | None = None,
    ) -> dict[str, Any]:
        """Alias for compute_comprehensive_metrics (observed financial and statistical evaluation)."""
        return self.compute_comprehensive_metrics(
            model_comparison_records=model_comparison_records,
            closing_rows=closing_rows,
            calibration_evaluation_source=calibration_evaluation_source,
            model_version_id=model_version_id,
        )


def compute_financial_and_statistical_metrics(
    db: DatabaseManager,
    paper_engine: PaperTradingEngine | None = None,
    model_version_id: str | None = None,
) -> dict[str, Any]:
    """
    Computes observed financial and statistical metrics from v_observed_simulated_bets,
    reconciled with PaperTradingEngine.get_bankroll_state().
    """
    engine = paper_engine or PaperTradingEngine(db, exclude_synthetic=True)
    bt = WalkForwardBacktester(db, engine)
    return bt.compute_comprehensive_metrics(model_version_id=model_version_id)
