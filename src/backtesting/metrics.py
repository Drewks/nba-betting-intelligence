"""
Backtesting evaluation metrics, exit gates, and model-version audit summaries.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
import numpy as np

from src.storage.db import DatabaseManager


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
            "observed": {
                "model_brier": model_brier,
                "baseline_brier": base_brier,
                "model_log_loss": model_ll,
                "baseline_log_loss": base_ll,
            },
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


def summarize_model_versions_from_db(
    db: DatabaseManager,
    active_model_version_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Summarizes observed predictions and settled bets grouped by model_version_id,
    reporting post-m012 calibrated probability coverage explicitly.
    """
    pred_rows = db.fetch_all(
        """
        SELECT
            p.model_version_id,
            COUNT(*) AS predictions_count,
            SUM(CASE WHEN g.status = 'FINAL' AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL THEN 1 ELSE 0 END) AS final_game_predictions,
            SUM(CASE WHEN p.calibrated_model_probability IS NOT NULL THEN 1 ELSE 0 END) AS has_m012_cal_probs_count,
            SUM(CASE WHEN g.status = 'FINAL' AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL AND p.calibrated_model_probability IS NOT NULL THEN 1 ELSE 0 END) AS final_with_m012_cal_probs_count,
            MIN(p.emitted_at) AS first_emitted_at,
            MAX(p.emitted_at) AS last_emitted_at
        FROM v_observed_predictions p
        LEFT JOIN games g ON g.game_id = p.game_id
        GROUP BY p.model_version_id
        ORDER BY MAX(p.emitted_at) DESC
        """
    )
    bet_rows = db.fetch_all(
        """
        SELECT
            p.model_version_id,
            COUNT(*) AS settled_bets_count
        FROM v_observed_simulated_bets b
        JOIN predictions p ON p.prediction_id = b.prediction_id
        WHERE b.status IN ('WON', 'LOST', 'PUSH', 'VOID')
        GROUP BY p.model_version_id
        """
    )
    settled_by_ver = {str(r["model_version_id"]): int(r["settled_bets_count"] or 0) for r in bet_rows}

    summary: dict[str, dict[str, Any]] = {}
    for row in pred_rows:
        m_ver = str(row["model_version_id"])
        cal_cnt = int(row["has_m012_cal_probs_count"] or 0)
        final_cal_cnt = int(row["final_with_m012_cal_probs_count"] or 0)
        summary[m_ver] = {
            "model_version_id": m_ver,
            "is_active": bool(active_model_version_id and m_ver == active_model_version_id),
            "predictions_count": int(row["predictions_count"] or 0),
            "final_game_predictions": int(row["final_game_predictions"] or 0),
            "has_m012_cal_probs": cal_cnt > 0,
            "m012_cal_probs_count": cal_cnt,
            "final_with_m012_cal_probs_count": final_cal_cnt,
            "settled_bets_count": settled_by_ver.get(m_ver, 0),
            "first_emitted_at": row["first_emitted_at"],
            "last_emitted_at": row["last_emitted_at"],
        }
    return summary
