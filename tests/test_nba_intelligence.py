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

