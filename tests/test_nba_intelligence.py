"""
Comprehensive Unit, Integration, and Reproducibility Test Suite (Section 14):
Covers all 15 required test categories plus end-to-end sequential orchestrator verification.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest

from src.backtesting.backtester import WalkForwardBacktester
from src.calibration.calibrator import ProbabilityCalibrator
from src.ingestion.adapters import (
    AdapterUnavailableError,
    BaseNBADataAdapter,
    DataSourceRouter,
    SyntheticFixtureAdapter,
)
from src.orchestrator import HumanInterventionRequiredError, Orchestrator
from src.paper_trading.engine import DoubleSettlementError, PaperTradingEngine
from src.prediction.ev_calculator import (
    calculate_ev,
    calculate_implied_prob_gross,
    devig_multiplicative,
)
from src.storage.db import DatabaseManager
from src.validation.validator import (
    DataValidationError,
    TemporalLeakageError,
    detect_duplicates,
    validate_game_record,
    validate_odds_record,
    validate_temporal_split,
)


def _seed_sample_game_and_prediction(db: DatabaseManager, game_id: str = "G_TEST_01") -> str:
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
            away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
            features_available_at, source_provider, ingested_at, result_recorded_at
        ) VALUES (
            ?, '2026-27', '2026-10-20', '2026-10-20T23:00:00Z', 'BOS', 'MIA',
            'SCHEDULED', NULL, NULL, 118.5, 110.2, 99.0, 113.5, 112.0, 97.5, 2, 2,
            '2026-10-20T18:00:00Z', 'synthetic_fixture', '2026-10-20T18:00:00Z', NULL
        )
        """,
        (game_id,),
    )
    db.execute_insert(
        """
        INSERT OR IGNORE INTO model_versions (
            model_version_id, model_family, market, train_start_date, train_end_date,
            trained_at, hyperparameters_json, is_active, approved_by
        ) VALUES (
            'model_c_test_v1', 'model_c_point_margin', 'moneyline',
            '2026-01-01', '2026-10-19', '2026-10-19T23:00:00Z', '{}', 1, 'test'
        )
        """
    )
    pred_id = f"PRED_{game_id}"
    db.execute_insert(
        """
        INSERT INTO predictions (
            prediction_id, game_id, market, selection, line_value, model_version_id,
            raw_probability, calibrated_probability, uncertainty_std, implied_prob_gross,
            implied_prob_fair, bookmaker_overround, decimal_odds_used, odds_provider,
            odds_captured_at, ev_unit, ev_pct, emitted_at, features_snapshot_json
        ) VALUES (
            ?, ?, 'moneyline', 'HOME', NULL, 'model_c_test_v1',
            0.52, 0.52, 0.05, 0.47619, 0.455, 0.045, 2.10, 'TestBook',
            '2026-10-20T19:00:00Z', 0.092, 9.2, '2026-10-20T20:00:00Z', '{}'
        )
        """,
        (pred_id, game_id),
    )
    return pred_id


# 1. Cálculo de probabilidad implícita
def test_01_implied_probability_calculation() -> None:
    assert calculate_implied_prob_gross(2.00) == pytest.approx(0.50, abs=1e-6)
    assert calculate_implied_prob_gross(2.10) == pytest.approx(1.0 / 2.10, abs=1e-5)
    p_fair_a, p_fair_b, overround = devig_multiplicative(1.9091, 1.9091)
    assert p_fair_a == pytest.approx(0.50, abs=1e-4)
    assert p_fair_b == pytest.approx(0.50, abs=1e-4)
    assert overround > 0.04


# 2. Cálculo de EV
def test_02_expected_value_calculation() -> None:
    res = calculate_ev(estimated_prob=0.52, decimal_odds=2.10)
    assert res["ev_unit"] == pytest.approx(0.092, abs=1e-6)
    assert res["ev_pct"] == pytest.approx(9.2, abs=1e-4)


# 3. Liquidación de una apuesta ganada
def test_03_settlement_won_bet(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "test_won.sqlite3")
    engine = PaperTradingEngine(db, initial_bankroll_pen=100.00)
    pred_id = _seed_sample_game_and_prediction(db, "G_WON")

    engine.evaluate_and_record_matchday_selections(
        matchday_date="2026-10-20",
        candidate_predictions=[
            {
                "prediction_id": pred_id,
                "game_id": "G_WON",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 2.10,
                "calibrated_probability": 0.52,
                "ev_unit": 0.092,
                "ev_pct": 9.2,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-20T20:00:00Z",
            }
        ],
    )
    bet_row = db.fetch_one("SELECT bet_id FROM simulated_bets WHERE game_id = 'G_WON'")
    assert bet_row is not None

    settled = engine.settle_bet(
        bet_id=bet_row["bet_id"],
        game_status="FINAL",
        home_score=112,
        away_score=104,
        settled_at="2026-10-21T02:00:00Z",
    )
    assert settled["status"] == "WON"
    assert settled["net_profit_pen"] == pytest.approx(1.10, abs=1e-4)
    assert settled["bankroll_after_pen"] == pytest.approx(101.10, abs=1e-4)


# 4. Liquidación de una apuesta perdida
def test_04_settlement_lost_bet(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "test_lost.sqlite3")
    engine = PaperTradingEngine(db, initial_bankroll_pen=100.00)
    pred_id = _seed_sample_game_and_prediction(db, "G_LOST")

    engine.evaluate_and_record_matchday_selections(
        matchday_date="2026-10-20",
        candidate_predictions=[
            {
                "prediction_id": pred_id,
                "game_id": "G_LOST",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 2.10,
                "calibrated_probability": 0.52,
                "ev_unit": 0.092,
                "ev_pct": 9.2,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-20T20:00:00Z",
            }
        ],
    )
    bet_row = db.fetch_one("SELECT bet_id FROM simulated_bets WHERE game_id = 'G_LOST'")
    assert bet_row is not None

    settled = engine.settle_bet(
        bet_id=bet_row["bet_id"],
        game_status="FINAL",
        home_score=98,
        away_score=105,
        settled_at="2026-10-21T02:00:00Z",
    )
    assert settled["status"] == "LOST"
    assert settled["net_profit_pen"] == pytest.approx(-1.00, abs=1e-4)
    assert settled["bankroll_after_pen"] == pytest.approx(99.00, abs=1e-4)


# 5. Liquidación de un push
def test_05_settlement_push_bet() -> None:
    status, net_profit, _ = PaperTradingEngine.calculate_settlement_outcome(
        market="total_points",
        selection="OVER",
        line_value=225.0,
        decimal_odds=1.91,
        stake_pen=1.00,
        game_status="FINAL",
        home_score=115,
        away_score=110,
    )
    assert status == "PUSH"
    assert net_profit == pytest.approx(0.0, abs=1e-6)


# 6. Actualización del bankroll
def test_06_bankroll_update_and_reconciliation(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "test_bankroll.sqlite3")
    engine = PaperTradingEngine(db, initial_bankroll_pen=100.00)
    p1 = _seed_sample_game_and_prediction(db, "G_B1")
    p2 = _seed_sample_game_and_prediction(db, "G_B2")

    engine.evaluate_and_record_matchday_selections(
        matchday_date="2026-10-20",
        candidate_predictions=[
            {
                "prediction_id": p1,
                "game_id": "G_B1",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 2.10,
                "calibrated_probability": 0.52,
                "ev_unit": 0.092,
                "ev_pct": 9.2,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-20T20:00:00Z",
            },
            {
                "prediction_id": p2,
                "game_id": "G_B2",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 2.00,
                "calibrated_probability": 0.55,
                "ev_unit": 0.10,
                "ev_pct": 10.0,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-20T20:00:00Z",
            },
        ],
    )
    mid_state = engine.get_bankroll_state()
    assert mid_state["settled_bankroll_pen"] == pytest.approx(100.00)
    assert mid_state["pending_exposure_pen"] == pytest.approx(2.00)
    assert mid_state["available_balance_pen"] == pytest.approx(98.00)

    b1 = db.fetch_one("SELECT bet_id FROM simulated_bets WHERE game_id = 'G_B1'")["bet_id"]
    b2 = db.fetch_one("SELECT bet_id FROM simulated_bets WHERE game_id = 'G_B2'")["bet_id"]
    engine.settle_bet(b1, "FINAL", 110, 100, "2026-10-21T02:00:00Z")  # +1.10
    engine.settle_bet(b2, "FINAL", 95, 102, "2026-10-21T02:05:00Z")   # -1.00

    final_state = engine.get_bankroll_state()
    assert final_state["settled_bankroll_pen"] == pytest.approx(100.10)
    assert final_state["cumulative_net_profit_pen"] == pytest.approx(0.10)
    assert final_state["pending_exposure_pen"] == pytest.approx(0.00)
    assert final_state["available_balance_pen"] == pytest.approx(100.10)


# 7. Prevención de doble liquidación
def test_07_prevent_double_settlement(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "test_double.sqlite3")
    engine = PaperTradingEngine(db, initial_bankroll_pen=100.00)
    pred_id = _seed_sample_game_and_prediction(db, "G_DBL")

    engine.evaluate_and_record_matchday_selections(
        matchday_date="2026-10-20",
        candidate_predictions=[
            {
                "prediction_id": pred_id,
                "game_id": "G_DBL",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 2.10,
                "calibrated_probability": 0.52,
                "ev_unit": 0.092,
                "ev_pct": 9.2,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-20T20:00:00Z",
            }
        ],
    )
    bet_id = db.fetch_one("SELECT bet_id FROM simulated_bets WHERE game_id = 'G_DBL'")["bet_id"]
    engine.settle_bet(bet_id, "FINAL", 110, 100, "2026-10-21T02:00:00Z")

    with pytest.raises(DoubleSettlementError):
        engine.settle_bet(bet_id, "FINAL", 110, 100, "2026-10-21T03:00:00Z")


# 8. Rechazo de cuotas ausentes o inválidas
def test_08_reject_missing_or_invalid_odds() -> None:
    with pytest.raises(DataValidationError):
        calculate_implied_prob_gross(1.0)
    with pytest.raises(DataValidationError):
        calculate_implied_prob_gross(-1.5)
    with pytest.raises(DataValidationError):
        validate_odds_record(
            {
                "game_id": "G1",
                "provider": "TestBook",
                "market": "moneyline",
                "selection": "HOME",
                "decimal_odds": None,
                "captured_at": "2026-10-20T18:00:00Z",
            },
            game_start_time="2026-10-20T23:00:00Z",
        )


# 9. Detección de datos futuros
def test_09_detect_future_data_leakage() -> None:
    with pytest.raises(TemporalLeakageError):
        validate_game_record(
            {
                "game_id": "G_LEAK",
                "season": "2026-27",
                "matchday_date": "2026-10-20",
                "game_start_time": "2026-10-20T23:00:00Z",
                "home_team": "BOS",
                "away_team": "MIA",
                "status": "SCHEDULED",
                "features_available_at": "2026-10-20T23:30:00Z",  # After tipoff!
                "source_provider": "test",
            }
        )
    with pytest.raises(TemporalLeakageError):
        validate_odds_record(
            {
                "game_id": "G_LEAK",
                "provider": "TestBook",
                "market": "moneyline",
                "selection": "HOME",
                "decimal_odds": 1.95,
                "captured_at": "2026-10-20T23:05:00Z",  # Post-tipoff odds!
            },
            game_start_time="2026-10-20T23:00:00Z",
        )


# 10. Separación temporal de entrenamiento y evaluación
def test_10_temporal_train_eval_separation() -> None:
    train_games = [{"game_id": "G1", "game_start_time": "2026-10-10T23:00:00Z"}]
    eval_games_valid = [{"game_id": "G2", "game_start_time": "2026-10-11T23:00:00Z"}]
    validate_temporal_split(train_games, eval_games_valid)

    eval_games_overlapping = [{"game_id": "G3", "game_start_time": "2026-10-09T23:00:00Z"}]
    with pytest.raises(TemporalLeakageError):
        validate_temporal_split(train_games, eval_games_overlapping)


# 11. Reproducción de resultados históricos
def test_11_historical_reproducibility(tmp_path: Path) -> None:
    adapter = SyntheticFixtureAdapter(seed=99, num_matchdays=20, games_per_day=4)
    bundle_1 = adapter.fetch_games_and_odds()
    bundle_2 = adapter.fetch_games_and_odds()
    assert bundle_1 == bundle_2

    db1 = DatabaseManager(tmp_path / "repro1.sqlite3")
    bt1 = WalkForwardBacktester(db1, PaperTradingEngine(db1), warmup_matchdays=8, retrain_every_matchdays=5)
    res1 = bt1.run_walk_forward(bundle_1["games"], bundle_1["odds"])

    db2 = DatabaseManager(tmp_path / "repro2.sqlite3")
    bt2 = WalkForwardBacktester(db2, PaperTradingEngine(db2), warmup_matchdays=8, retrain_every_matchdays=5)
    res2 = bt2.run_walk_forward(bundle_2["games"], bundle_2["odds"])

    assert res1["net_profit_pen"] == res2["net_profit_pen"]
    assert res1["roi_pct"] == res2["roi_pct"]
    assert res1["overall_brier_score"] == res2["overall_brier_score"]


# 12. Registro inmutable de predicciones
def test_12_immutable_prediction_and_bet_records(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "test_immut.sqlite3")
    pred_id = _seed_sample_game_and_prediction(db, "G_IMMUT")

    with pytest.raises(sqlite3.IntegrityError):
        with db.connect() as conn:
            conn.execute("UPDATE predictions SET calibrated_probability = 0.99 WHERE prediction_id = ?", (pred_id,))

    with pytest.raises(sqlite3.IntegrityError):
        with db.connect() as conn:
            conn.execute("DELETE FROM predictions WHERE prediction_id = ?", (pred_id,))


# 13. Recalibración sin fuga de información
def test_13_recalibration_without_data_leakage() -> None:
    cal = ProbabilityCalibrator(method="logistic", min_samples_logistic=5)
    leaked_records = [
        {
            "game_start_time": "2026-10-25T23:00:00Z",
            "raw_probability": 0.60,
            "outcome": 1,
        }
    ]
    with pytest.raises(TemporalLeakageError):
        cal.fit(leaked_records, calibration_cutoff_time="2026-10-20T00:00:00Z")

    valid_records = [
        {
            "game_start_time": f"2026-10-{day:02d}T23:00:00Z",
            "raw_probability": 0.35 if day % 2 == 0 else 0.70,
            "outcome": 0 if day % 2 == 0 else 1,
        }
        for day in range(1, 15)
    ]
    method_used = cal.fit(valid_records, calibration_cutoff_time="2026-10-20T00:00:00Z")
    assert method_used == "logistic"
    transformed = cal.transform_single(0.65)
    assert 0.03 <= transformed <= 0.97


# 14. Recuperación ante fallos de una fuente
def test_14_source_failover_recovery() -> None:
    class FailingAdapter(BaseNBADataAdapter):
        provider_name = "failing_primary_source"

        def fetch_games_and_odds(self, date_str=None, as_of_utc=None):
            raise AdapterUnavailableError("Simulated timeout on primary source")

    fallback_adapter = SyntheticFixtureAdapter(seed=42, num_matchdays=5, games_per_day=2)
    router = DataSourceRouter([FailingAdapter(), fallback_adapter])
    res = router.fetch_with_failover()
    assert res["active_provider"] == fallback_adapter.provider_name
    assert len(res["failover_events"]) == 1
    assert len(res["games"]) == 10


# 15. Detección de duplicados
def test_15_duplicate_detection_in_data_and_bets(tmp_path: Path) -> None:
    records = [
        {"game_id": "G1", "market": "moneyline"},
        {"game_id": "G2", "market": "moneyline"},
        {"game_id": "G1", "market": "moneyline"},
    ]
    dups = detect_duplicates(records, ("game_id", "market"))
    assert dups == [("G1", "moneyline")]

    db = DatabaseManager(tmp_path / "test_dup_bets.sqlite3")
    engine = PaperTradingEngine(db, initial_bankroll_pen=100.00)
    pred_id = _seed_sample_game_and_prediction(db, "G_DUP")
    cand = {
        "prediction_id": pred_id,
        "game_id": "G_DUP",
        "market": "moneyline",
        "selection": "HOME",
        "line_value": None,
        "decimal_odds_used": 2.10,
        "calibrated_probability": 0.52,
        "ev_unit": 0.092,
        "ev_pct": 9.2,
        "model_version_id": "model_c_test_v1",
        "emitted_at": "2026-10-20T20:00:00Z",
    }
    first_run = engine.evaluate_and_record_matchday_selections("2026-10-20", [cand])
    second_run = engine.evaluate_and_record_matchday_selections("2026-10-20", [cand])
    assert len(first_run["placed_bets"]) == 1
    assert len(second_run["placed_bets"]) == 0
    assert second_run["no_bet_decisions"][0]["reason_code"] == "DUPLICATE_SELECTION"


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
                "gate_4_zero_information_leakage": {"passed": True},
            }
        },
    }
    res_t2 = evaluate_and_notify_readiness(tier2_metrics, status_file)
    assert res_t2["is_ready_for_real_money"] is True
    assert res_t2["is_tier2_full_bankroll_ready"] is True
    assert res_t2["graduation_level"] == "NIVEL_2_BANCA_COMPLETA"
    assert res_t2["tier2_passed_gates_count"] == 8


# 18. Staking contextual Kelly-Convicción según probabilidad de acierto (S/1.00 a S/6.00 PEN)
def test_18_dynamic_contextual_kelly_staking(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "test_dynamic_stake.sqlite3")
    engine = PaperTradingEngine(
        db=db,
        initial_bankroll_pen=100.00,
        base_stake_pen=1.00,
        max_stake_pen=6.00,
        dynamic_conviction_staking=True,
    )
    p_low = _seed_sample_game_and_prediction(db, "G_LOW_PROB")
    p_med = _seed_sample_game_and_prediction(db, "G_MED_PROB")
    p_high = _seed_sample_game_and_prediction(db, "G_HIGH_PROB")

    res = engine.evaluate_and_record_matchday_selections(
        matchday_date="2026-10-20",
        candidate_predictions=[
            {
                "prediction_id": p_low,
                "game_id": "G_LOW_PROB",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 2.75,
                "calibrated_probability": 0.42,
                "ev_unit": 0.155,
                "ev_pct": 15.5,
                "uncertainty_std": 0.06,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-20T20:00:00Z",
            },
            {
                "prediction_id": p_med,
                "game_id": "G_MED_PROB",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 2.00,
                "calibrated_probability": 0.54,
                "ev_unit": 0.08,
                "ev_pct": 8.0,
                "uncertainty_std": 0.05,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-20T20:00:00Z",
            },
            {
                "prediction_id": p_high,
                "game_id": "G_HIGH_PROB",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 1.91,
                "calibrated_probability": 0.68,
                "ev_unit": 0.2988,
                "ev_pct": 29.88,
                "uncertainty_std": 0.04,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-20T20:00:00Z",
            },
        ],
    )
    placed = {b["game_id"]: b["stake_pen"] for b in res["placed_bets"]}
    assert 1.00 <= placed["G_LOW_PROB"] <= 1.75
    assert 2.00 <= placed["G_MED_PROB"] <= 3.35
    assert 4.80 <= placed["G_HIGH_PROB"] <= 6.00
    assert placed["G_HIGH_PROB"] > placed["G_MED_PROB"] > placed["G_LOW_PROB"]
    # High-probability pick is prioritized first in placement order
    assert res["placed_bets"][0]["game_id"] == "G_HIGH_PROB"


# 19. Motor Híbrido Modelo G (ML + 10,000 Simulaciones Monte Carlo con Overtime/Blowout + Conformal)
def test_19_deep_montecarlo_hybrid_model() -> None:
    from src.models.statistical_models import DeepMonteCarloHybridModel, EnsembleStackingModel

    adapter = SyntheticFixtureAdapter(seed=101, num_matchdays=12, games_per_day=4)
    bundle = adapter.fetch_games_and_odds()
    games = bundle["games"]
    hist = [g for g in games[:35] if g["status"] == "FINAL"]
    target_game = games[36]

    mc_model = DeepMonteCarloHybridModel("model_g_test", n_simulations=10000)
    mc_model.fit(hist, target_game["game_start_time"])
    sim_1 = mc_model.simulate_matchup(target_game, hist, line_value=228.5)
    sim_2 = mc_model.simulate_matchup(target_game, hist, line_value=228.5)

    # Deterministic 10,000-simulation reproducibility
    assert sim_1["p_home_mc"] == sim_2["p_home_mc"]
    assert sim_1["p_over_mc"] == sim_2["p_over_mc"]
    assert sim_1["n_simulations"] == 10000
    assert 0.01 <= sim_1["overtime_prob"] <= 0.18
    assert 0.01 <= sim_1["blowout_prob"] <= 0.65
    assert sim_1["conformal_q10_total"] < sim_1["mc_expected_total"] < sim_1["conformal_q90_total"]

    ens = EnsembleStackingModel("model_f_test")
    ens.fit(hist, target_game["game_start_time"])
    ml_out = ens.predict_moneyline(target_game, hist)
    tot_out = ens.predict_total_points(target_game, hist, 228.5)
    assert "p_montecarlo" in ml_out
    assert "overtime_prob" in tot_out
    assert "conformal_q10_total" in tot_out


# 20. Prioridad 0: Anclaje al Mercado Eficiente, Ratings Anti-Fuga y Filtro de Datos Reales
def test_20_prioridad_0_market_anchoring_and_team_ratings(tmp_path: Path) -> None:
    from src.features.team_ratings import compute_pregame_team_ratings, is_synthetic_game_id
    from src.paper_trading.engine import PaperTradingEngine
    from src.prediction.ev_calculator import (
        DEFAULT_MODEL_WEIGHT,
        compute_market_consensus,
        evaluate_market_opportunity,
        market_anchored_probability,
    )
    from src.storage.db import DatabaseManager

    # 1. Anclaje de Probabilidad al Mercado
    odds_sample = [
        {"provider": "Pinnacle (LineShop)", "market": "moneyline", "selection": "HOME", "decimal_odds": 1.95, "counterpart_decimal_odds": 1.95},
        {"provider": "DraftKings", "market": "moneyline", "selection": "HOME", "decimal_odds": 1.91, "counterpart_decimal_odds": 1.91},
    ]
    cons = compute_market_consensus(odds_sample)
    assert ("moneyline", "HOME", None) in cons
    # Pinnacle devigged fair prob is exactly 0.50
    assert abs(cons[("moneyline", "HOME", None)]["p_market"] - 0.50) < 1e-4

    # Blending test: model says 65% (0.65), market consensus is 50% (0.50)
    anchored = market_anchored_probability(0.65, 0.50, model_weight=DEFAULT_MODEL_WEIGHT)
    # 0.30 * 0.65 + 0.70 * 0.50 = 0.545
    assert abs(anchored - 0.545) < 1e-4

    # 2. evaluate_market_opportunity anchors probability and computes disagreement
    eval_res = evaluate_market_opportunity(
        estimated_prob=0.65,
        uncertainty_std=0.05,
        odds_record={"game_id": "G_REAL", "provider": "Pinnacle", "market": "moneyline", "selection": "HOME", "decimal_odds": 1.95, "counterpart_decimal_odds": 1.95, "captured_at": "2026-10-30T18:00:00Z"},
        game_start_time="2026-10-30T23:00:00Z",
        model_version_id="model_f_v3",
        simulated_prediction_time="2026-10-30T19:00:00Z",
        market_consensus_prob=0.50,
    )
    assert abs(eval_res["estimated_probability"] - 0.545) < 1e-4
    assert abs(eval_res["model_market_disagreement"] - 0.15) < 1e-4

    # 3. Model-Market Disagreement Gate in PaperTradingEngine
    db = DatabaseManager(tmp_path / "test_p0.sqlite3")
    engine = PaperTradingEngine(db=db, min_ev_threshold=0.02, dynamic_conviction_staking=True, exclude_synthetic=True)
    res_gate = engine.evaluate_and_record_matchday_selections(
        "2026-10-30",
        [
            {
                "prediction_id": "PRED_HUGE_GAP",
                "game_id": "G_REAL_1",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 1.95,
                "calibrated_probability": 0.56,
                "ev_unit": 0.09,
                "ev_pct": 9.0,
                "uncertainty_std": 0.05,
                "model_version_id": "model_f_v3",
                "model_market_disagreement": 0.22,  # 22 points > 15 max gap
                "max_model_market_disagreement": 0.15,
                "emitted_at": "2026-10-30T20:00:00Z",
            }
        ],
    )
    assert len(res_gate["placed_bets"]) == 0
    assert res_gate["no_bet_decisions"][0]["reason_code"] == "MODEL_MARKET_DISAGREEMENT"

    # 4. Anti-leakage rest days & rating engine
    chron_games = [
        {"game_id": "ESPN_1", "game_start_time": "2026-10-25T00:00:00Z", "home_team": "BOS", "away_team": "NYK", "status": "FINAL", "home_score": 110, "away_score": 105},
        {"game_id": "ESPN_2", "game_start_time": "2026-10-26T00:00:00Z", "home_team": "BOS", "away_team": "MIA", "status": "SCHEDULED", "home_score": None, "away_score": None},
    ]
    ratings = compute_pregame_team_ratings(chron_games)
    # BOS played on Oct 25 and Oct 26 -> 1 day rest (Back-to-Back)
    assert ratings["ESPN_2"]["home_rest_days"] == 1
    assert is_synthetic_game_id("SYN_20260101_BOS_AT_MIA")
    assert not is_synthetic_game_id("ESPN_401909891")

# 21. Prioridad 1: Kelly Proporcional a la Ventaja, Guardi?n de Riesgo CLV y Anti-Correlaci?n por Partido
def test_21_prioridad_1_edge_proportional_kelly_clv_governor_anticorrelation(tmp_path: Path) -> None:
    from src.paper_trading.engine import PaperTradingEngine
    from src.storage.db import DatabaseManager

    db = DatabaseManager(tmp_path / "test_p1.sqlite3")
    engine = PaperTradingEngine(
        db=db,
        initial_bankroll_pen=100.00,
        base_stake_pen=1.00,
        max_stake_pen=6.00,
        dynamic_conviction_staking=True,
        single_bet_per_game=True,
    )

    # 1. Edge-Proportional Staking: High prob (68%) with high EV (29.9%) vs tiny EV (1.5%)
    stake_high_edge = engine.compute_contextual_stake_pen(
        calibrated_prob=0.68,
        decimal_odds=1.91,
        ev_unit=0.2988,
        current_bankroll_pen=100.0,
        apply_clv_governor=False,
    )
    stake_tiny_edge = engine.compute_contextual_stake_pen(
        calibrated_prob=0.68,
        decimal_odds=1.49,
        ev_unit=0.015,
        current_bankroll_pen=100.0,
        apply_clv_governor=False,
    )
    # High edge unlocks high stake (S/5.50), while tiny edge protects bankroll (S/1.76 - S/2.10)
    assert 4.80 <= stake_high_edge <= 6.00
    assert 1.00 <= stake_tiny_edge <= 2.20
    assert stake_high_edge > 2.0 * stake_tiny_edge

    # 2. Anti-Correlation: Only 1 bet allowed per game across all markets
    p_ml = _seed_sample_game_and_prediction(db, "G_MATCHUP_ALPHA")
    # Add a second prediction for the same game
    p_tot = "PRED_TEST_TOT_ALPHA"
    db.execute_insert(
        """
        INSERT INTO predictions (
            prediction_id, game_id, market, selection, line_value,
            model_version_id, raw_probability, calibrated_probability,
            uncertainty_std, implied_prob_gross, implied_prob_fair,
            bookmaker_overround, decimal_odds_used, odds_provider,
            odds_captured_at, ev_unit, ev_pct, emitted_at, features_snapshot_json
        ) VALUES (
            ?, 'G_MATCHUP_ALPHA', 'total_points', 'UNDER', 228.5,
            'model_c_test_v1', 0.55, 0.55,
            0.05, 0.5235, 0.50,
            0.047, 1.91, 'DraftKings',
            '2026-10-20T18:00:00Z', 0.0505, 5.05, '2026-10-20T18:00:00Z', '{}'
        )
        """,
        (p_tot,),
    )

    res_anticorr = engine.evaluate_and_record_matchday_selections(
        "2026-10-20",
        [
            {
                "prediction_id": p_ml,
                "game_id": "G_MATCHUP_ALPHA",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 1.95,
                "calibrated_probability": 0.58,
                "ev_unit": 0.131,
                "ev_pct": 13.1,
                "uncertainty_std": 0.04,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-20T20:00:00Z",
            },
            {
                "prediction_id": p_tot,
                "game_id": "G_MATCHUP_ALPHA",
                "market": "total_points",
                "selection": "UNDER",
                "line_value": 228.5,
                "decimal_odds_used": 1.91,
                "calibrated_probability": 0.55,
                "ev_unit": 0.0505,
                "ev_pct": 5.05,
                "uncertainty_std": 0.05,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-20T20:00:00Z",
            },
        ],
    )
    # Exactly one bet placed on G_MATCHUP_ALPHA; second market is blocked to prevent double-dipping risk
    assert len(res_anticorr["placed_bets"]) == 1
    assert res_anticorr["placed_bets"][0]["market"] == "moneyline"
    assert len(res_anticorr["no_bet_decisions"]) == 1
    assert res_anticorr["no_bet_decisions"][0]["reason_code"] == "CORRELATED_GAME_EXPOSURE"

    # 3. CLV Risk Governor with synthetic isolation (exclude_synthetic=True) - tests ambiguous column fix
    engine_real = PaperTradingEngine(
        db=db,
        initial_bankroll_pen=100.00,
        base_stake_pen=1.00,
        max_stake_pen=6.00,
        dynamic_conviction_staking=True,
        exclude_synthetic=True,
    )
    pred_real = _seed_sample_game_and_prediction(db, "REAL_GAME_01")
    db.execute_insert(
        """
        INSERT INTO odds_snapshots (
            odds_id, game_id, provider, market, selection, line_value, decimal_odds,
            captured_at, is_closing_line
        ) VALUES ('ODDS_CLV_01', 'REAL_GAME_01', 'Pinnacle', 'moneyline', 'HOME', NULL, 1.80, '2026-10-19T23:55:00Z', 1)
        """
    )
    db.execute_insert(
        """
        INSERT INTO simulated_bets (
            bet_id, prediction_id, game_id, matchday_date, market, selection,
            line_value, decimal_odds, estimated_prob, estimated_ev, stake_pen, status, net_profit_pen,
            emitted_at, settled_at, model_version_id
        ) VALUES ('BET_TEST_CLV_1', ?, 'REAL_GAME_01', '2026-10-19', 'moneyline', 'HOME',
                  NULL, 1.95, 0.55, 0.07, 2.50, 'WON', 2.375, '2026-10-19T18:00:00Z', '2026-10-20T03:00:00Z', 'model_c_test_v1')
        """,
        (pred_real,),
    )
    factor, mean_clv = engine_real.get_recent_clv_governor_factor()
    assert isinstance(factor, float)
    stake_with_clv = engine_real.compute_contextual_stake_pen(
        calibrated_prob=0.60,
        decimal_odds=1.90,
        ev_unit=0.08,
        current_bankroll_pen=100.0,
        apply_clv_governor=True,
    )
    assert 1.00 <= stake_with_clv <= 6.00

# 22. Deduplicación de CLV, Filtro de Sesgo Longshot y Calidad del Pick Diario (>= 50% Prob)
def test_22_clv_deduplication_longshot_guard_and_daily_pick_quality(tmp_path: Path) -> None:
    from src.paper_trading.engine import PaperTradingEngine
    from src.storage.db import DatabaseManager
    from src.reporting.notifier import select_and_dispatch_daily_top_pick

    db = DatabaseManager(tmp_path / "test_p22.sqlite3")
    engine = PaperTradingEngine(
        db=db,
        initial_bankroll_pen=100.00,
        base_stake_pen=1.00,
        max_stake_pen=6.00,
        dynamic_conviction_staking=True,
        exclude_synthetic=True,
    )

    # 1. Test Longshot Bias Guard (odds > 3.50 with EV < 15% must be skipped)
    p_longshot = _seed_sample_game_and_prediction(db, "G_LONGSHOT")
    res_longshot = engine.evaluate_and_record_matchday_selections(
        "2026-10-25",
        [
            {
                "prediction_id": p_longshot,
                "game_id": "G_LONGSHOT",
                "market": "moneyline",
                "selection": "AWAY",
                "line_value": None,
                "decimal_odds_used": 4.50,
                "calibrated_probability": 0.24,
                "ev_unit": 0.08,
                "ev_pct": 8.0,
                "uncertainty_std": 0.05,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-25T18:00:00Z",
            }
        ],
    )
    assert len(res_longshot["placed_bets"]) == 0
    assert len(res_longshot["no_bet_decisions"]) == 1
    assert res_longshot["no_bet_decisions"][0]["reason_code"] == "EXCESSIVE_LONGSHOT_VARIANCE"

    # 2. Test CLV Deduplication with multiple closing lines per bet
    pred_clv = _seed_sample_game_and_prediction(db, "G_CLV_MULTI")
    db.execute_insert(
        """
        INSERT INTO odds_snapshots (
            odds_id, game_id, provider, market, selection, line_value, decimal_odds,
            captured_at, is_closing_line
        ) VALUES ('ODDS_MULTI_DK', 'G_CLV_MULTI', 'DraftKings', 'moneyline', 'HOME', NULL, 1.75, '2026-10-25T23:55:00Z', 1)
        """
    )
    db.execute_insert(
        """
        INSERT INTO odds_snapshots (
            odds_id, game_id, provider, market, selection, line_value, decimal_odds,
            captured_at, is_closing_line
        ) VALUES ('ODDS_MULTI_PINN', 'G_CLV_MULTI', 'Pinnacle', 'moneyline', 'HOME', NULL, 1.80, '2026-10-25T23:58:00Z', 1)
        """
    )
    db.execute_insert(
        """
        INSERT INTO simulated_bets (
            bet_id, prediction_id, game_id, matchday_date, market, selection,
            line_value, decimal_odds, estimated_prob, estimated_ev, stake_pen, status, net_profit_pen,
            emitted_at, settled_at, model_version_id
        ) VALUES ('BET_MULTI_1', ?, 'G_CLV_MULTI', '2026-10-25', 'moneyline', 'HOME',
                  NULL, 1.95, 0.55, 0.07, 2.50, 'WON', 2.375, '2026-10-25T18:00:00Z', '2026-10-26T03:00:00Z', 'model_c_test_v1')
        """,
        (pred_clv,),
    )
    factor, mean_clv = engine.get_recent_clv_governor_factor(lookback=10)
    assert isinstance(factor, float)

    # 3. Test Daily Top Pick Quality Filter (Requires prob >= 50% and odds <= 2.60)
    status_file = tmp_path / "readiness.json"
    status_file.write_text("{}", encoding="utf-8")

    low_prob_bets = [
        {
            "bet_id": "BET_LOW",
            "partido": "SAC @ MEM",
            "mercado": "moneyline",
            "seleccion": "AWAY",
            "cuota_decimal": 4.40,
            "prob_estimada": 24.1,
            "ev_porcentaje": 6.1,
            "estado": "PENDING",
            "fecha_jornada": "2026-10-25",
            "hora_partido_peru": "2026-10-25 19:00",
            "stake_pen": 1.04,
        }
    ]
    res_low = select_and_dispatch_daily_top_pick(low_prob_bets, status_file)
    assert res_low is not None
    assert res_low["top_pick"] is None
    assert res_low["reason"] == "NO_HIGH_PROBABILITY_PICK_MEETS_50PCT_THRESHOLD"

    high_prob_bets = [
        {
            "bet_id": "BET_HIGH",
            "partido": "BOS @ MIA",
            "mercado": "moneyline",
            "seleccion": "HOME",
            "cuota_decimal": 1.65,
            "prob_estimada": 67.5,
            "ev_porcentaje": 11.4,
            "estado": "PENDING",
            "fecha_jornada": "2026-10-25",
            "hora_partido_peru": "2026-10-25 19:00",
            "stake_pen": 4.50,
        }
    ]
    res_high = select_and_dispatch_daily_top_pick(high_prob_bets, status_file)
    assert res_high is not None
    assert res_high["top_pick"] is not None
    assert res_high["top_pick"]["bet_id"] == "BET_HIGH"
    assert res_high["top_pick"]["prob_estimada"] == 67.5

# 23. Persistencia Automática de Cuotas de Cierre (Closing Lines) Pre-Tipoff y Modos de Ciclo
def test_23_persist_closing_lines_and_cycle_modes(tmp_path: Path) -> None:
    from src.paper_trading.engine import PaperTradingEngine
    from src.storage.db import DatabaseManager

    db = DatabaseManager(tmp_path / "test_p23.sqlite3")
    engine = PaperTradingEngine(
        db=db,
        initial_bankroll_pen=100.00,
        base_stake_pen=1.00,
        max_stake_pen=6.00,
        dynamic_conviction_staking=True,
        exclude_synthetic=True,
    )

    # 1. Seed a scheduled real game starting in 20 minutes
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
            away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
            features_available_at, source_provider, ingested_at
        ) VALUES (
            'REAL_GAME_TIPOFF', '2026-27', '2026-10-25', '2026-10-25T20:00:00Z', 'GSW', 'LAL',
            'SCHEDULED', NULL, NULL, 115.0, 112.0, 100.0, 114.0, 113.0, 99.0, 2, 2,
            '2026-10-25T18:00:00Z', 'espn_real', '2026-10-25T18:00:00Z'
        )
        """
    )
    # Insert open odds captured pre-tipoff
    db.execute_insert(
        """
        INSERT INTO odds_snapshots (
            odds_id, game_id, provider, market, selection, line_value, decimal_odds,
            captured_at, is_closing_line
        ) VALUES ('ODDS_TIPOFF_HOME', 'REAL_GAME_TIPOFF', 'Pinnacle', 'moneyline', 'HOME', NULL, 1.95, '2026-10-25T19:40:00Z', 0)
        """
    )

    # Run persist_closing_lines_for_games as of 19:45 UTC (15 min before tipoff)
    promoted = engine.persist_closing_lines_for_games(as_of_utc="2026-10-25T19:45:00Z")
    assert promoted == 1

    # Verify that a closing line row now exists with is_closing_line = 1
    closing_row = db.fetch_one(
        "SELECT * FROM odds_snapshots WHERE game_id = 'REAL_GAME_TIPOFF' AND is_closing_line = 1"
    )
    assert closing_row is not None
    assert closing_row["odds_id"] == "ODDS_TIPOFF_HOME_CLOSE"
    assert float(closing_row["decimal_odds"]) == 1.95
    assert closing_row["captured_at"] == "2026-10-25T19:40:00Z"

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


def test_25_v4_model_breakthrough_and_calibration_guards() -> None:
    """Validates V4 pace-decoupled ratings, enriched feature vector, OOS ensemble weights, and small-sample calibration intercept guard."""
    from src.calibration.calibrator import ProbabilityCalibrator
    from src.features.builder import build_pregame_features
    from src.features.team_ratings import compute_pregame_team_ratings
    from src.models.statistical_models import EnsembleStackingModel

    # 1. Pace-decoupled rating verification: high-scoring offense increases home_off_rtg without artificially lowering home_def_rtg
    sample_games = [
        {"game_id": "ESPN_T1", "game_start_time": "2026-10-20T00:00:00Z", "home_team": "IND", "away_team": "ATL", "status": "FINAL", "home_score": 132, "away_score": 114},
        {"game_id": "ESPN_T2", "game_start_time": "2026-10-22T00:00:00Z", "home_team": "IND", "away_team": "DET", "status": "FINAL", "home_score": 128, "away_score": 114},
        {"game_id": "ESPN_T3", "game_start_time": "2026-10-25T00:00:00Z", "home_team": "IND", "away_team": "MIA", "status": "SCHEDULED", "home_score": None, "away_score": None},
    ]
    rtgs = compute_pregame_team_ratings(sample_games)
    assert rtgs["ESPN_T3"]["home_off_rtg"] > 115.5
    assert rtgs["ESPN_T3"]["home_off_rtg"] > rtgs["ESPN_T3"]["home_def_rtg"]

    # 2. Enriched pre-game features & altitude/fatigue signals
    target_den = {
        "game_id": "ESPN_DEN_1",
        "game_start_time": "2026-10-26T01:00:00Z",
        "home_team": "DEN",
        "away_team": "ATL",
        "status": "SCHEDULED",
        "home_off_rtg": 118.0,
        "home_def_rtg": 112.0,
        "home_pace": 99.5,
        "away_off_rtg": 114.0,
        "away_def_rtg": 116.0,
        "away_pace": 100.5,
        "home_rest_days": 3,
        "away_rest_days": 1,
        "features_available_at": "2026-10-25T20:00:00Z",
    }
    feats = build_pregame_features(target_den, sample_games[:2], market="moneyline")
    assert feats["altitude_advantage"] > 1.5
    assert feats["fatigue_diff"] > 2.0
    assert feats["structural_margin"] > 8.0
    assert "elo_spread" in feats and "structural_total" in feats

    # 3. Small-sample intercept regularization in ProbabilityCalibrator (prevents directional Home/Away bias on N=35)
    cal = ProbabilityCalibrator(method="logistic", min_samples_logistic=25)
    skewed_small_sample = [
        {
            "game_start_time": f"2026-10-{(i % 20) + 1:02d}T12:00:00Z",
            "raw_probability": 0.50,
            "outcome": 0 if i < 23 else 1,  # 12 wins, 23 losses at p=0.50 on small N=35
        }
        for i in range(35)
    ]
    cal.fit(skewed_small_sample, "2026-10-28T00:00:00Z")
    # At N=35 (<= 50), intercept is regularized to 0.0 so p=0.50 stays centered at 0.50
    assert abs(cal.transform_single(0.50) - 0.50) < 0.01



def test_26_v5_geodesic_travel_altitude_acclimation_and_moment_matched_mc() -> None:
    """Validates V5 geodesic Haversine travel miles, road-return penalty, altitude acclimation, and MC moment-matching."""
    from src.features.builder import _compute_travel_leg, build_pregame_features
    from src.models.statistical_models import DeepMonteCarloHybridModel

    # 1. Geodesic Haversine travel & altitude acclimation: MIA -> DEN climbs >5,200 ft; UTA -> DEN climbs ~1,054 ft
    dist_mia_den, tz_mia_den, climb_mia_den = _compute_travel_leg("MIA", "DEN", "MIA")
    dist_uta_den, tz_uta_den, climb_uta_den = _compute_travel_leg("UTA", "DEN", "UTA")
    assert dist_mia_den > 1650.0
    assert tz_mia_den == 2.0
    assert climb_mia_den > 5200.0
    assert climb_uta_den < 1100.0

    # 2. First game home after long road trip (>700 miles, rest <= 2 days) triggers first_home_from_road == 1.0
    hist_road_return = [
        {
            "game_id": "ESPN_RR_1",
            "game_start_time": "2026-10-20T02:00:00Z",
            "home_team": "LAL",
            "away_team": "BOS",
            "status": "FINAL",
            "home_score": 110,
            "away_score": 115,
        },
        {
            "game_id": "ESPN_RR_2",
            "game_start_time": "2026-10-21T00:00:00Z",
            "home_team": "NYK",
            "away_team": "PHI",
            "status": "FINAL",
            "home_score": 108,
            "away_score": 104,
        },
    ]
    target_bos_home = {
        "game_id": "ESPN_RR_TARGET",
        "game_start_time": "2026-10-22T23:30:00Z",
        "home_team": "BOS",
        "away_team": "NYK",
        "status": "SCHEDULED",
        "home_off_rtg": 118.0,
        "home_def_rtg": 111.0,
        "home_pace": 99.5,
        "away_off_rtg": 115.0,
        "away_def_rtg": 112.0,
        "away_pace": 98.5,
        "home_rest_days": 2,
        "away_rest_days": 2,
        "features_available_at": "2026-10-22T18:00:00Z",
    }
    feats_rr = build_pregame_features(target_bos_home, hist_road_return, market="moneyline")
    assert feats_rr["first_home_from_road"] == 1.0
    assert feats_rr["travel_miles_diff"] < -2000.0  # BOS traveled ~2,590 mi from LAL vs NYK ~190 mi from NYK

    # 3. Moment-matched Monte Carlo simulator preserves exact analytical expectations
    mc_model = DeepMonteCarloHybridModel(n_simulations=5000)
    sim_out = mc_model.simulate_matchup(target_bos_home, hist_road_return, line_value=226.5)
    assert 0.05 <= sim_out["p_home_mc"] <= 0.95
    assert 0.05 <= sim_out["p_over_mc"] <= 0.95
    assert sim_out["conformal_q10_total"] < sim_out["mc_expected_total"] < sim_out["conformal_q90_total"]



def test_27_v6_steam_moves_spread_predictions_referees_and_injury_decay(tmp_path: Path) -> None:
    """Validates V6 Steam Move detection, adverse steam guard, Point Spread prediction/settlement, Referee Crew & 3PT mean-reversion."""
    from src.ingestion.adapters import ESPNPublicAdapter
    from src.models.statistical_models import EnsembleStackingModel
    from src.paper_trading.engine import PaperTradingEngine
    from src.prediction.ev_calculator import compute_line_steam, evaluate_market_opportunity
    from src.storage.db import DatabaseManager

    # 1. Steam Move velocity calculation across chronological snapshots
    snapshots = [
        {
            "game_id": "ESPN_STEAM_1",
            "market": "moneyline",
            "selection": "HOME",
            "decimal_odds": 1.95,
            "counterpart_decimal_odds": 1.95,
            "captured_at": "2026-11-05T14:00:00Z",
        },
        {
            "game_id": "ESPN_STEAM_1",
            "market": "moneyline",
            "selection": "HOME",
            "decimal_odds": 1.72,
            "counterpart_decimal_odds": 2.22,
            "captured_at": "2026-11-05T21:00:00Z",
        },
    ]
    steam_map = compute_line_steam(snapshots)
    ml_home_steam = steam_map[("moneyline", "HOME")]
    assert ml_home_steam["steam_delta"] > 0.05  # Implied fair prob rose from 50.0% to ~56.3% (+6.3% sharp steam)

    # Confirming vs adverse steam modulation in evaluate_market_opportunity
    opp_confirm = evaluate_market_opportunity(
        estimated_prob=0.62,
        uncertainty_std=0.04,
        odds_record={
            "odds_id": "O_ST_1",
            "game_id": "ESPN_STEAM_1",
            "provider": "Pinnacle",
            "market": "moneyline",
            "selection": "HOME",
            "line_value": None,
            "decimal_odds": 1.85,
            "counterpart_decimal_odds": 2.05,
            "captured_at": "2026-11-05T21:00:00Z",
        },
        game_start_time="2026-11-05T23:30:00Z",
        model_version_id="model_f_ensemble_v5",
        steam_delta=0.035,
    )
    opp_adverse = evaluate_market_opportunity(
        estimated_prob=0.62,
        uncertainty_std=0.04,
        odds_record={
            "odds_id": "O_ST_2",
            "game_id": "ESPN_STEAM_1",
            "provider": "Pinnacle",
            "market": "moneyline",
            "selection": "HOME",
            "line_value": None,
            "decimal_odds": 1.85,
            "counterpart_decimal_odds": 2.05,
            "captured_at": "2026-11-05T21:00:00Z",
        },
        game_start_time="2026-11-05T23:30:00Z",
        model_version_id="model_f_ensemble_v5",
        steam_delta=-0.035,
    )
    assert opp_confirm["estimated_probability"] > opp_adverse["estimated_probability"]

    # 2. Adverse Sharp Steam Guard in PaperTradingEngine (blocks bets with steam_delta <= -0.045)
    db = DatabaseManager(tmp_path / "test_v6.sqlite3")
    engine = PaperTradingEngine(db=db, initial_bankroll_pen=100.0, max_stake_pen=6.0, dynamic_conviction_staking=True)
    res_steam = engine.evaluate_and_record_matchday_selections(
        "2026-11-05",
        [
            {
                "prediction_id": "PRED_STEAM_ADV",
                "game_id": "ESPN_STEAM_1",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 1.95,
                "calibrated_probability": 0.56,
                "ev_unit": 0.092,
                "ev_pct": 9.2,
                "uncertainty_std": 0.04,
                "steam_delta": -0.052,
                "model_version_id": "model_f_ensemble_v5",
                "emitted_at": "2026-11-05T21:00:00Z",
            }
        ],
    )
    assert len(res_steam["placed_bets"]) == 0
    assert res_steam["no_bet_decisions"][0]["reason_code"] == "ADVERSE_SHARP_STEAM_MOVE"

    # 3. Point Spread prediction (predict_spread) and settlement (WON, LOST, PUSH)
    hist = [
        {"game_id": "G1", "game_start_time": "2026-10-20T00:00:00Z", "home_team": "BOS", "away_team": "NYK", "status": "FINAL", "home_score": 118, "away_score": 106},
        {"game_id": "G2", "game_start_time": "2026-10-22T00:00:00Z", "home_team": "BOS", "away_team": "MIA", "status": "FINAL", "home_score": 114, "away_score": 102},
    ]
    target = {
        "game_id": "G3",
        "game_start_time": "2026-10-25T00:00:00Z",
        "home_team": "BOS",
        "away_team": "NYK",
        "status": "SCHEDULED",
        "home_off_rtg": 119.0,
        "home_def_rtg": 110.5,
        "home_pace": 99.0,
        "away_off_rtg": 114.5,
        "away_def_rtg": 113.5,
        "away_pace": 98.0,
        "home_rest_days": 2,
        "away_rest_days": 2,
        "features_available_at": "2026-10-24T18:00:00Z",
    }
    ens = EnsembleStackingModel("model_f_v6_test")
    sp_half = ens.predict_spread(target, hist, spread_line_home=-5.5)
    sp_int = ens.predict_spread(target, hist, spread_line_home=-5.0)
    assert 0.05 <= sp_half["p_cover_home"] <= 0.95
    assert sp_half["p_push_estimate"] == 0.0
    assert sp_int["p_push_estimate"] > 0.01

    st_win, prof_win, _ = PaperTradingEngine.calculate_settlement_outcome("spread", "HOME", -5.5, 1.91, 2.0, "FINAL", 112, 105)
    st_push, prof_push, _ = PaperTradingEngine.calculate_settlement_outcome("spread", "HOME", -7.0, 1.91, 2.0, "FINAL", 112, 105)
    st_away, prof_away, _ = PaperTradingEngine.calculate_settlement_outcome("spread", "AWAY", 5.5, 1.91, 2.0, "FINAL", 110, 106)
    assert st_win == "WON" and prof_win == 1.82
    assert st_push == "PUSH" and prof_push == 0.0
    assert st_away == "WON" and prof_away == 1.82

    # 4. Referee Crew Tendency & 3PT Shooting Luck Mean-Reversion in _estimate_pregame_team_profile
    off_high_ref, _, pace_high_ref = ESPNPublicAdapter._estimate_pregame_team_profile(
        "BOS", {}, is_home=True, box_stats={"threePointFieldGoalPct": 44.0}, referee_total_adj=2.5, referee_hca_adj=0.6
    )
    off_low_ref, _, pace_low_ref = ESPNPublicAdapter._estimate_pregame_team_profile(
        "BOS", {}, is_home=True, box_stats={"threePointFieldGoalPct": 44.0}, referee_total_adj=-2.0, referee_hca_adj=-0.4
    )
    assert off_high_ref > off_low_ref
    assert pace_high_ref > pace_low_ref


# 28. V7 Fase 2: Sinergia de Quintetos (LineupSynergyEngine On/Off RAPM) y Penalización No Lineal por Rol
def test_28_lineup_synergy_nonlinear_role_penalties() -> None:
    from src.features.team_ratings import compute_lineup_synergy_penalty
    from src.ingestion.adapters import ESPNPublicAdapter

    # 1. Single primary initiator out: offense-heavy penalty
    single_init = compute_lineup_synergy_penalty(
        [{"name": "Tyrese Haliburton", "status": "out", "position": "PG", "baseline_deduction": 0.0}]
    )
    assert single_init["off_rtg_penalty"] > single_init["def_rtg_penalty"] * 2.5
    assert single_init["pace_delta"] < -1.0
    assert single_init["synergy_compound_bonus"] == 0.0

    # 2. Two primary initiators out simultaneously -> non-linear compound playmaking collapse (> sum of parts)
    second_init = compute_lineup_synergy_penalty(
        [{"name": "Darius Garland", "status": "out", "position": "PG", "baseline_deduction": 0.0}]
    )
    double_init = compute_lineup_synergy_penalty(
        [
            {"name": "Tyrese Haliburton", "status": "out", "position": "PG", "baseline_deduction": 0.0},
            {"name": "Darius Garland", "status": "out", "position": "PG", "baseline_deduction": 0.0},
        ]
    )
    assert double_init["synergy_compound_bonus"] > 1.5
    assert double_init["total_net_penalty"] > round(
        single_init["total_net_penalty"] + second_init["total_net_penalty"] + 1.5, 2
    )

    # 3. Rim anchor out: defense-heavy penalty
    rim_out = compute_lineup_synergy_penalty(
        [
            {"name": "Rudy Gobert", "status": "out", "position": "C", "baseline_deduction": 0.0},
            {"name": "Evan Mobley", "status": "out", "position": "C", "baseline_deduction": 0.0},
        ]
    )
    assert rim_out["def_rtg_penalty"] > rim_out["off_rtg_penalty"] * 2.0
    assert rim_out["synergy_compound_bonus"] > 1.0

    # 4. Integration with _estimate_pregame_team_profile asymmetric Off/Def/Pace adjustment
    off_healthy, def_healthy, pace_healthy = ESPNPublicAdapter._estimate_pregame_team_profile("IND", {}, is_home=True)
    off_syn, def_syn, pace_syn = ESPNPublicAdapter._estimate_pregame_team_profile(
        "IND",
        {},
        is_home=True,
        injury_penalty=double_init["total_net_penalty"],
        synergy_detail=double_init,
    )
    assert (off_healthy - off_syn) > (def_syn - def_healthy) * 2.0
    assert pace_syn < pace_healthy


# 29. V7 Fase 3: Predicción Conformal Adaptativa (Venn-Abers Predictor & Conformal Lower-Bound EV)
def test_29_conformal_venn_abers_intervals_and_lower_bound_ev(tmp_path: Path) -> None:
    import pytest
    from src.calibration.calibrator import (
        VennAbersConformalInterval,
        conformal_lower_bound_ev,
    )
    from src.paper_trading.engine import PaperTradingEngine
    from src.prediction.ev_calculator import evaluate_market_opportunity
    from src.storage.db import DatabaseManager
    from src.validation.validator import TemporalLeakageError

    va = VennAbersConformalInterval(window=500, min_samples=20)

    # 1. Anti-leakage enforcement
    with pytest.raises(TemporalLeakageError):
        va.fit(
            [{"raw_probability": 0.65, "game_start_time": "2026-11-06T00:00:00Z", "outcome": 1}],
            "2026-11-05T00:00:00Z",
        )

    # 2. Multi-probabilistic validity & monotonicity
    records = []
    for i in range(50):
        p_raw = 0.30 + (i / 100.0)
        y = 1 if p_raw > 0.52 else 0
        records.append({
            "raw_probability": p_raw,
            "game_start_time": f"2026-10-{i % 25 + 1:02d}T00:00:00Z",
            "outcome": y,
        })
    fitted = va.fit(records, "2026-10-31T00:00:00Z")
    assert fitted is True
    res = va.predict_interval(0.60)
    assert 0.0 <= res["p0"] <= res["p_va"] <= res["p1"] <= 1.0
    assert res["width"] == round(res["p1"] - res["p0"], 6)

    # 3. Conformal lower-bound EV
    lb = conformal_lower_bound_ev(
        point_prob=0.60,
        interval_low=res["p0"],
        market_prob=0.55,
        model_weight=0.30,
        decimal_odds=2.00,
    )
    assert lb["ev_lower_bound"] <= (0.60 * 2.00 - 1.0)
    assert lb["p_low_final"] <= 0.60

    # 4. evaluate_market_opportunity integration
    odds_sample = {
        "odds_id": "O_TEST_CONF_1",
        "game_id": "G_TEST_CONF_1",
        "market": "moneyline",
        "selection": "HOME",
        "line_value": None,
        "decimal_odds": 2.10,
        "counterpart_decimal_odds": 1.85,
        "provider": "Pinnacle",
        "captured_at": "2026-11-04T12:00:00Z",
    }
    opp = evaluate_market_opportunity(
        estimated_prob=0.60,
        uncertainty_std=0.045,
        odds_record=odds_sample,
        game_start_time="2026-11-04T18:00:00Z",
        model_version_id="model_f_v7",
        conformal_interval=res,
    )
    assert opp["conformal_p_low"] == res["p0"]
    assert opp["conformal_p_high"] == res["p1"]
    assert opp["conformal_width"] == res["width"]
    assert "ev_lower_bound" in opp
    assert "ev_lower_bound_pct" in opp

    # 5. PaperTradingEngine width guard blocks excessively wide intervals (> 0.22)
    db = DatabaseManager(tmp_path / "test_p29.sqlite3")
    engine = PaperTradingEngine(db=db, initial_bankroll_pen=100.0, dynamic_conviction_staking=True)
    wide_candidate = {
        "prediction_id": "P_WIDE",
        "game_id": "G_WIDE",
        "market": "moneyline",
        "selection": "HOME",
        "decimal_odds_used": 2.05,
        "calibrated_probability": 0.58,
        "ev_unit": 0.08,
        "ev_pct": 8.0,
        "model_version_id": "model_f_v7",
        "conformal_width": 0.28,  # > 0.22 guard
        "emitted_at": "2026-11-04T12:00:00Z",
    }
    decisions = engine.evaluate_and_record_matchday_selections("2026-11-04", [wide_candidate])
    assert len(decisions["no_bet_decisions"]) == 1
    assert decisions["no_bet_decisions"][0]["reason_code"] == "CONFORMAL_UNCERTAINTY_TOO_WIDE"


# 30. V7 Fase 4: Optimización Bayesiana Walk-Forward de Hiperparámetros (Optuna TPE)
def test_30_optuna_walk_forward_hyperparameter_optimization(tmp_path: Path) -> None:
    import json
    import pytest
    from src.backtesting.hyperparameter_optimizer import OptunaWalkForwardOptimizer
    from src.ingestion.adapters import SyntheticFixtureAdapter

    optimizer = OptunaWalkForwardOptimizer(seed=42)

    # 1. Reject insufficient games
    with pytest.raises(ValueError, match="Insufficient games"):
        optimizer.optimize(games=[], n_trials=2)

    # 2. Run optimization over deterministic walk-forward schedule
    adapter = SyntheticFixtureAdapter(seed=42, num_matchdays=30, games_per_day=4)
    bundle = adapter.fetch_games_and_odds()
    games = bundle["games"]

    out_json = tmp_path / "optimal_hyperparameters.json"
    summary = optimizer.optimize(
        games=games,
        n_trials=6,
        eval_slice_size=35,
        output_json_path=out_json,
    )

    assert summary["n_trials"] == 6
    assert summary["eval_sample_size"] == 35
    assert "best_hyperparameters" in summary
    assert "best_score" in summary
    assert "baseline_score" in summary
    assert out_json.exists()

    loaded = json.loads(out_json.read_text(encoding="utf-8"))
    assert loaded["best_score"] == summary["best_score"]
    best_p = summary["best_hyperparameters"]
    assert 0.025 <= best_p["alpha_slow"] <= 0.075
    assert 0.080 <= best_p["alpha_fast"] <= 0.170
    assert 0.20 <= best_p["market_model_weight"] <= 0.45


# 31. V7 Fase 5: Optimización de Portafolio Kelly Simultáneo Multi-Partido (scipy.optimize)
def test_31_simultaneous_kelly_portfolio_optimization(tmp_path: Path) -> None:
    from src.paper_trading.engine import PaperTradingEngine
    from src.prediction.ev_calculator import optimize_simultaneous_kelly_portfolio
    from src.storage.db import DatabaseManager

    # 1. Single bet returns exact fractional Kelly stake
    single_cand = [{"estimated_probability": 0.60, "decimal_odds_used": 1.95}]
    single_res = optimize_simultaneous_kelly_portfolio(single_cand, bankroll_pen=100.0)
    assert len(single_res) == 1
    assert "kelly_optimal_fraction" in single_res[0]
    assert 1.00 <= single_res[0]["kelly_recommended_stake_pen"] <= 6.00

    # 2. Multi-bet simultaneous optimization across 3 games
    slate_candidates = [
        {"game_id": "G1", "selection": "HOME", "estimated_probability": 0.64, "decimal_odds_used": 1.88},  # Strong edge
        {"game_id": "G2", "selection": "HOME", "estimated_probability": 0.58, "decimal_odds_used": 1.95},  # Medium edge
        {"game_id": "G3", "selection": "AWAY", "estimated_probability": 0.53, "decimal_odds_used": 2.15},  # Lean edge
    ]
    opt_slate = optimize_simultaneous_kelly_portfolio(
        slate_candidates,
        bankroll_pen=100.0,
        max_total_exposure_fraction=0.15,
        max_individual_fraction=0.06,
        fractional_multiplier=0.50,
    )
    assert len(opt_slate) == 3
    total_frac = sum(c["kelly_optimal_fraction"] for c in opt_slate)
    assert total_frac <= 0.150001
    for c in opt_slate:
        assert c["kelly_optimal_fraction"] <= 0.060001
        assert 1.00 <= c["kelly_recommended_stake_pen"] <= 6.00

    # Stronger edge receives more capital than lean edge
    assert opt_slate[0]["kelly_recommended_stake_pen"] >= opt_slate[2]["kelly_recommended_stake_pen"]

    # 3. Integration with PaperTradingEngine matchday batch allocation
    db = DatabaseManager(tmp_path / "test_p31.sqlite3")
    engine = PaperTradingEngine(db=db, initial_bankroll_pen=100.0, dynamic_conviction_staking=True)
    p1 = _seed_sample_game_and_prediction(db, "G_BAT_1")
    p2 = _seed_sample_game_and_prediction(db, "G_BAT_2")
    batch_candidates = [
        {
            "prediction_id": p1,
            "game_id": "G_BAT_1",
            "market": "moneyline",
            "selection": "HOME",
            "decimal_odds_used": 1.92,
            "calibrated_probability": 0.62,
            "ev_unit": 0.09,
            "ev_pct": 9.0,
            "model_version_id": "model_c_test_v1",
            "emitted_at": "2026-10-20T20:00:00Z",
        },
        {
            "prediction_id": p2,
            "game_id": "G_BAT_2",
            "market": "moneyline",
            "selection": "AWAY",
            "decimal_odds_used": 2.10,
            "calibrated_probability": 0.56,
            "ev_unit": 0.08,
            "ev_pct": 8.0,
            "model_version_id": "model_c_test_v1",
            "emitted_at": "2026-10-20T20:00:00Z",
        },
    ]
    decisions = engine.evaluate_and_record_matchday_selections("2026-10-20", batch_candidates)
    assert len(decisions["placed_bets"]) == 2
    for b in decisions["placed_bets"]:
        assert 1.00 <= b["stake_pen"] <= 6.00


def test_32_injury_sniper_pregame_dual_window(tmp_path: Path) -> None:
    """
    V7.1 Fase 6 Verification:
    Tests the automated Injury Sniper Dual-Window Monitor at T-2h and T-30m:
      1) Temporal classification into WINDOW_2H (90-150m) and WINDOW_30M (15-45m).
      2) Transition detection for star players (Questionable -> OUT, late scratches).
      3) Lineup synergy penalty recalculation and Venn-Abers conformal Lower-Bound EV.
      4) Emission of actionable Sniper Alerts with simultaneous Kelly portfolio stakes.
      5) Immutable audit logging into the SQLite `sniper_alerts` table.
    """
    from datetime import datetime, timezone
    from src.prediction.injury_sniper import (
        classify_game_window,
        detect_injury_status_transitions,
        InjurySniperMonitor,
    )
    from src.storage.db import DatabaseManager

    ref_utc = datetime(2026, 11, 7, 22, 0, 0, tzinfo=timezone.utc)

    # 1. Test Window Classification
    w_2h, d_2h = classify_game_window("2026-11-08T00:00:00Z", ref_utc)  # 120m
    assert w_2h == "WINDOW_2H"
    assert d_2h == 120.0

    w_30m, d_30m = classify_game_window("2026-11-07T22:30:00Z", ref_utc)  # 30m
    assert w_30m == "WINDOW_30M"
    assert d_30m == 30.0

    w_imm, d_imm = classify_game_window("2026-11-07T22:10:00Z", ref_utc)  # 10m
    assert w_imm == "TIPOFF_IMMINENT"

    w_fut, d_fut = classify_game_window("2026-11-08T03:00:00Z", ref_utc)  # 300m
    assert w_fut == "UPCOMING_FUTURE"

    # 2. Test Injury Transition Detection
    cached_inj = [
        {"name": "Luka Doncic", "status": "QUESTIONABLE", "team": "DAL"},
        {"name": "Rudy Gobert", "status": "DOUBTFUL", "team": "MIN"},
    ]
    live_inj = [
        {"name": "Luka Doncic", "status": "OUT", "team": "DAL", "notes": "Left ankle sprain"},
        {"name": "Rudy Gobert", "status": "AVAILABLE", "team": "MIN", "notes": "Cleared to play"},
    ]
    transitions = detect_injury_status_transitions(cached_inj, live_inj)
    assert len(transitions) == 2

    luka_t = next(t for t in transitions if t["player_name"] == "Luka Doncic")
    assert luka_t["old_status"] == "QUESTIONABLE"
    assert luka_t["new_status"] == "OUT"
    assert luka_t["tactical_role"] == "PRIMARY_INITIATOR"
    assert luka_t["severity"] == "CRITICAL"
    assert luka_t["is_synergy_star"] is True

    rudy_t = next(t for t in transitions if t["player_name"] == "Rudy Gobert")
    assert rudy_t["old_status"] == "DOUBTFUL"
    assert rudy_t["new_status"] == "AVAILABLE"
    assert rudy_t["tactical_role"] == "RIM_ANCHOR"
    assert rudy_t["severity"] == "HIGH"

    # 3. Test Sniper Opportunity Evaluation & Conformal Lower-Bound EV
    db_file = tmp_path / "test_sniper.sqlite3"
    db = DatabaseManager(db_file)
    # Seed teams & game to satisfy foreign keys
    db.execute_insert(
        "INSERT INTO teams (team_id, full_name, conference, division, updated_at) VALUES ('PHX', 'Phoenix Suns', 'West', 'Pacific', '2026-10-01T00:00:00Z');"
    )
    db.execute_insert(
        "INSERT INTO teams (team_id, full_name, conference, division, updated_at) VALUES ('DAL', 'Dallas Mavericks', 'West', 'Southwest', '2026-10-01T00:00:00Z');"
    )
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team, status,
            features_available_at, source_provider, ingested_at
        ) VALUES ('G_SNIPER_TEST', '2026-27', '2026-11-07', '2026-11-08T00:00:00Z', 'PHX', 'DAL', 'SCHEDULED', '2026-11-07T20:00:00Z', 'espn', '2026-11-07T20:00:00Z');
        """
    )

    odds_list = [
        {
            "odds_id": "O_PHX",
            "game_id": "G_SNIPER_TEST",
            "provider": "draftkings",
            "market": "moneyline",
            "selection": "HOME",
            "line_value": None,
            "decimal_odds": 1.88,
            "counterpart_decimal_odds": 1.95,
            "captured_at": "2026-11-07T22:00:00Z",
        },
        {
            "odds_id": "O_DAL",
            "game_id": "G_SNIPER_TEST",
            "provider": "draftkings",
            "market": "moneyline",
            "selection": "AWAY",
            "line_value": None,
            "decimal_odds": 1.95,
            "counterpart_decimal_odds": 1.88,
            "captured_at": "2026-11-07T22:00:00Z",
        },
    ]

    monitor = InjurySniperMonitor(db=db, min_ev_threshold=0.04)
    alerts = monitor.evaluate_game_sniper_opportunity(
        game_id="G_SNIPER_TEST",
        matchday_date="2026-11-07",
        game_start_time="2026-11-08T00:00:00Z",
        home_team="PHX",
        away_team="DAL",
        live_injuries=[{"name": "Luka Doncic", "status": "OUT", "team": "DAL", "position": "PG"}],
        market_odds=odds_list,
        window_type="WINDOW_2H",
        minutes_to_tipoff=120.0,
        cached_injuries=[{"name": "Luka Doncic", "status": "QUESTIONABLE", "team": "DAL"}],
        bankroll_pen=100.0,
    )

    # 4. Verify Alert Generation on PHX ML
    assert len(alerts) >= 1
    phx_alert = next(a for a in alerts if a["selection"] == "HOME")
    assert phx_alert["target_team"] == "PHX"
    assert phx_alert["synergy_shift"] > 3.0  # Away loss of Luka adds >3 pts advantage to Home
    assert phx_alert["ev_lower_bound_pct"] > 4.0
    assert 1.00 <= phx_alert["kelly_stake_pen"] <= 6.00
    assert phx_alert["window_type"] == "WINDOW_2H"

    # 5. Verify SQLite persistence in sniper_alerts
    persisted = db.fetch_all("SELECT * FROM sniper_alerts WHERE game_id = 'G_SNIPER_TEST'")
    assert len(persisted) >= 1
    row = persisted[0]
    assert row["selection"] == "HOME"
    assert row["window_type"] == "WINDOW_2H"
    assert row["ev_lower_bound_pct"] > 4.0

def test_33_player_props_engine(tmp_path: Path) -> None:
    """
    V7.2 Player Props Engine Verification:
    Tests individual player statistical modeling (PTS, REB, AST, PRA),
    usage and minutes redistribution upon teammate absences, Poisson & Normal distributions,
    conformal Lower-Bound EV, and SQLite persistence.
    """
    from src.prediction.player_props import PlayerPropsEngine
    from src.storage.db import DatabaseManager

    db_file = tmp_path / "test_props.sqlite3"
    db = DatabaseManager(db_file)
    db.execute_insert(
        "INSERT INTO teams (team_id, full_name, conference, division, updated_at) VALUES ('DAL', 'Dallas Mavericks', 'West', 'Southwest', '2026-10-01T00:00:00Z');"
    )
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team, status,
            features_available_at, source_provider, ingested_at
        ) VALUES ('G_PROP_TEST', '2026-27', '2026-11-06', '2026-11-07T00:00:00Z', 'DAL', 'PHX', 'SCHEDULED', '2026-11-06T20:00:00Z', 'espn', '2026-11-06T20:00:00Z');
        """
    )

    engine = PlayerPropsEngine(db=db, min_ev_threshold=0.00)

    # 1. Test baseline vs usage bump projection
    base_proj = engine.project_player_stats("Kyrie Irving", "DAL", absent_teammates=[])
    bump_proj = engine.project_player_stats("Kyrie Irving", "DAL", absent_teammates=["Luka Doncic"])

    assert bump_proj["usage_bump_pct"] > 5.0
    assert bump_proj["effective_minutes"] > base_proj["effective_minutes"]
    assert bump_proj["projections"]["PTS"]["mean"] > base_proj["projections"]["PTS"]["mean"]

    # 2. Test exceedance probabilities (Normal for PTS, Poisson for AST)
    p_over_pts, p_under_pts = engine.compute_exceedance_probabilities("PTS", 26.5, 30.1, 7.46, "normal")
    assert 0.60 <= p_over_pts <= 0.85
    assert abs((p_over_pts + p_under_pts) - 1.0) < 0.01

    p_over_ast, p_under_ast = engine.compute_exceedance_probabilities("AST", 5.5, 7.0, 2.65, "poisson")
    assert 0.60 <= p_over_ast <= 0.85

    # 3. Test prop opportunity evaluation & Kelly stake
    picks = engine.evaluate_prop_opportunity(
        player_name="Kyrie Irving",
        team="DAL",
        game_id="G_PROP_TEST",
        matchday_date="2026-11-06",
        prop_category="PTS",
        line_value=26.5,
        over_odds=1.90,
        under_odds=1.90,
        absent_teammates=["Luka Doncic"],
        bankroll_pen=100.0,
    )
    assert len(picks) >= 1
    top_pick = picks[0]
    assert top_pick["player_name"] == "Kyrie Irving"
    assert top_pick["selection"] == "OVER"
    assert top_pick["ev_pct"] > 10.0
    assert 1.00 <= top_pick["kelly_stake_pen"] <= 5.00

    # 4. Verify SQLite persistence in player_prop_picks
    persisted = db.fetch_all("SELECT * FROM player_prop_picks WHERE game_id = 'G_PROP_TEST'")
    assert len(persisted) >= 1
    row = persisted[0]
    assert row["player_name"] == "Kyrie Irving"
    assert row["prop_category"] == "PTS"
    assert row["selection"] == "OVER"
    assert row["line_value"] == 26.5

