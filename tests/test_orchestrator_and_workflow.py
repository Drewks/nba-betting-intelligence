"""
Pipeline Orchestrator, Retry Control and Notification System Tests (`tests/test_orchestrator_and_workflow.py`).
Modular test suite extracted from legacy test_nba_intelligence monolith.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from src.orchestrator import HumanInterventionRequiredError, Orchestrator



# 16. Integración completa del Coordinador (Orchestrator) y control de reintentos
def test_16_end_to_end_orchestrator_and_retry_control(tmp_path: Path) -> None:
    orch = Orchestrator(
        db_path=tmp_path / "e2e.sqlite3",
        reports_dir=tmp_path / "reports",
        obsidian_vault_dir=tmp_path / "NBA",
        max_retries=2,
    )
    # Test retry limit on persistent error
    attempts = {"count": 0}

    def _always_fail():
        attempts["count"] += 1
        raise RuntimeError("Persistent agent failure")

    with pytest.raises(HumanInterventionRequiredError):
        orch.execute_step_sequentially(99, "test_failing_agent", _always_fail)
    assert attempts["count"] == 3  # 1 initial + 2 controlled retries

    # Run full pipeline end-to-end
    summary = orch.run_full_pipeline(include_live_espn=False)
    assert summary["audit_result"]["leakage_violations_count"] == 0
    assert summary["audit_result"]["bankroll_reconciled"] is True
    assert summary["audit_result"]["immutability_triggers_verified"] is True
    assert summary["audit_result"]["exit_gates_evaluation"]["recommendation"] == "REMAIN_IN_PAPER_TRADING"
    assert (tmp_path / "reports" / "daily_report.md").exists()
    assert (tmp_path / "reports" / "weekly_report.md").exists()
    assert (tmp_path / "reports" / "audit_report.md").exists()


# 17. Prueba del Sistema de Alerta de Madurez para Entorno Real (8 Criterios y 2 Niveles de Graduación)
def test_17_readiness_notification_system(tmp_path: Path) -> None:
    from src.reporting.notifier import evaluate_and_notify_readiness

    status_file = tmp_path / "readiness_status.json"
    calibrating_metrics = {
        "settled_bets_count": 98,
        "live_espn_settled_bets_count": 0,
        "pending_bets_count": 6,
        "current_settled_bankroll_pen": 103.03,
        "roi_pct": 3.10,
        "yield_pct": 2.92,
        "max_drawdown_pct": 6.47,
        "overall_brier_score": 0.2455,
        "baseline_brier_score": 0.2503,
        "overall_ece": 0.028,
        "bootstrap_uncertainty": {
            "roi_ci_lower_90_pct": -15.20,
            "roi_ci_upper_90_pct": 22.10,
            "roi_ci_lower_95_pct": -21.81,
            "roi_ci_upper_95_pct": 27.73,
        },
        "exit_gates_evaluation": {
            "gates": {
                "gate_1_min_500_settled_selections": {"passed": False},
                "gate_3_calibration_non_inferior_to_baseline": {"passed": True},
                "gate_10_non_inferior_to_devigged_market": {"passed": True},
                "gate_4_zero_information_leakage": {"passed": True},
                "gate_5_positive_roi_and_yield": {"passed": True},
                "gate_6_statistical_uncertainty_excludes_zero_edge": {"passed": False},
            }
        },
    }
    res_cal = evaluate_and_notify_readiness(calibrating_metrics, status_file)
    assert res_cal["is_ready_for_real_money"] is False
    assert res_cal["graduation_level"] == "FASE_0_SIMULACION_Y_CALIBRACION"
    assert res_cal["passed_gates_count"] == 5
    assert res_cal["total_gates_count"] == 8
    assert res_cal["missing_settled_bets"] == 402
    assert res_cal["missing_live_bets_tier1"] == 200

    tier1_metrics = {
        "settled_bets_count": 512,
        "live_espn_settled_bets_count": 215,
        "pending_bets_count": 2,
        "current_settled_bankroll_pen": 124.50,
        "roi_pct": 4.80,
        "yield_pct": 4.50,
        "max_drawdown_pct": 9.20,
        "overall_brier_score": 0.2410,
        "baseline_brier_score": 0.2503,
        "overall_ece": 0.032,
        "bootstrap_uncertainty": {
            "roi_ci_lower_90_pct": 0.85,
            "roi_ci_upper_90_pct": 8.90,
            "roi_ci_lower_95_pct": -0.40,
            "roi_ci_upper_95_pct": 10.10,
        },
        "exit_gates_evaluation": {
            "gates": {
                "gate_1_min_500_settled_selections": {"passed": True},
                "gate_3_calibration_non_inferior_to_baseline": {"passed": True},
                "gate_10_non_inferior_to_devigged_market": {"passed": True},
                "gate_4_zero_information_leakage": {"passed": True},
            }
        },
    }
    res_t1 = evaluate_and_notify_readiness(tier1_metrics, status_file)
    assert res_t1["is_ready_for_real_money"] is True
    assert res_t1["is_tier1_micro_bankroll_ready"] is True
    assert res_t1["is_tier2_full_bankroll_ready"] is False
    assert res_t1["graduation_level"] == "NIVEL_1_MICRO_BANCA"
    assert res_t1["passed_gates_count"] == 8

    tier2_metrics = {
        "settled_bets_count": 1050,
        "live_espn_settled_bets_count": 540,
        "pending_bets_count": 2,
        "current_settled_bankroll_pen": 168.00,
        "roi_pct": 6.40,
        "yield_pct": 6.10,
        "max_drawdown_pct": 10.50,
        "overall_brier_score": 0.2385,
        "baseline_brier_score": 0.2503,
        "overall_ece": 0.024,
        "performance_by_market": {
            "moneyline": {"roi_pct": 5.80},
            "total_points": {"roi_pct": 7.10},
        },
        "bootstrap_uncertainty": {
            "roi_ci_lower_90_pct": 2.90,
            "roi_ci_upper_90_pct": 9.80,
            "roi_ci_lower_95_pct": 1.85,
            "roi_ci_upper_95_pct": 10.90,
        },
        "exit_gates_evaluation": {
            "gates": {
                "gate_1_min_500_settled_selections": {"passed": True},
                "gate_3_calibration_non_inferior_to_baseline": {"passed": True},
                "gate_10_non_inferior_to_devigged_market": {"passed": True},
                "gate_4_zero_information_leakage": {"passed": True},
            }
        },
    }
    res_t2 = evaluate_and_notify_readiness(tier2_metrics, status_file)
    assert res_t2["is_ready_for_real_money"] is True
    assert res_t2["is_tier2_full_bankroll_ready"] is True
    assert res_t2["graduation_level"] == "NIVEL_2_BANCA_COMPLETA"
    assert res_t2["tier2_passed_gates_count"] == 8


def test_24_external_workflow_dispatcher() -> None:
    """Validates zero-latency external workflow dispatcher (Improvement #4)."""
    from scripts.dispatch_cycle import resolve_repository, dispatch_workflow

    repo = resolve_repository()
    assert "nba-betting-intelligence" in repo

    # Dry run execution for each supported cycle mode
    for mode in ("auto", "pregame", "settle_and_calibrate"):
        success = dispatch_workflow(
            repo="Drewks/nba-betting-intelligence",
            token="ghp_test_token_1234567890",
            mode=mode,
            ref="main",
            dry_run=True,
        )
        assert success is True
