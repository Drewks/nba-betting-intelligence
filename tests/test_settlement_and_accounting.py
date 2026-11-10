"""
Settlement, Bankroll Accounting, CPPI Shield and PnL Tests (`tests/test_settlement_and_accounting.py`).
Modular test suite extracted from legacy test_nba_intelligence monolith.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest

from src.paper_trading.engine import DoubleSettlementError, PaperTradingEngine
from src.prediction.ev_calculator import (
    calculate_ev,
    calculate_implied_prob_gross,
    devig_multiplicative,
)
from src.storage.db import DatabaseManager
from src.validation.validator import (
    DataValidationError,
    validate_odds_record,
)
from tests.helpers import _seed_sample_game_and_prediction



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


# 46. V9 Fase 5: CPPI Capital Preservation Shield (Constant Proportion Portfolio Insurance)
def test_46_cppi_capital_preservation_shield(tmp_path: Path) -> None:
    """
    Test 46 (V9 Phase 5 Verification):
    1. Constant Proportion Portfolio Insurance (CPPI) capital preservation shield.
    2. Multiplier is 1.0 when bankroll is at peak equity.
    3. Multiplier scales down as bankroll drops towards the 85% floor.
    4. Strict lower clamp (0.15) prevents ruin while maintaining fractional skin in the game.
    5. Integration into PaperTradingEngine.compute_contextual_stake_pen.
    """
    from src.paper_trading.engine import PaperTradingEngine, compute_cppi_multiplier
    from src.storage.db import DatabaseManager

    # 1. Multiplier behavior across drawdown regimes
    m_peak = compute_cppi_multiplier(current_bankroll=100.0, peak_bankroll=100.0, floor_fraction=0.85)
    assert m_peak == 1.0

    # Mild drawdown: 95.0 -> Cushion = 10.0 / Max Cushion = 15.0 -> 0.67
    m_mild = compute_cppi_multiplier(current_bankroll=95.0, peak_bankroll=100.0, floor_fraction=0.85)
    assert 0.60 <= m_mild <= 0.75

    # Severe distress near floor: 86.0 -> Cushion = 1.0 / Max Cushion = 15.0 -> small
    m_distress = compute_cppi_multiplier(current_bankroll=86.0, peak_bankroll=100.0, floor_fraction=0.85)
    assert 0.15 <= m_distress <= 0.25

    # Breach of floor: 83.0 -> Floor clamped to 0.15
    m_breach = compute_cppi_multiplier(current_bankroll=83.0, peak_bankroll=100.0, floor_fraction=0.85)
    assert m_breach == 0.15

    # 2. Integration into PaperTradingEngine contextual staking
    db = DatabaseManager(tmp_path / "test_cppi.sqlite3")
    engine = PaperTradingEngine(db=db, initial_bankroll_pen=100.0, dynamic_conviction_staking=True, max_stake_pen=6.00)

    # Healthy bankroll stake
    stake_healthy = engine.compute_contextual_stake_pen(
        calibrated_prob=0.60,
        decimal_odds=1.95,
        ev_unit=0.17,
        current_bankroll_pen=100.0,
        apply_cppi_shield=True,
        peak_bankroll_pen=100.0,
    )

    # Distressed bankroll stake (in drawdown to 87.0 PEN from peak 100.0 PEN)
    stake_distressed = engine.compute_contextual_stake_pen(
        calibrated_prob=0.60,
        decimal_odds=1.95,
        ev_unit=0.17,
        current_bankroll_pen=87.0,
        apply_cppi_shield=True,
        peak_bankroll_pen=100.0,
    )

    assert stake_healthy > stake_distressed
    assert stake_distressed >= 1.00  # Never below minimum bet S/ 1.00 PEN


# 47. V9 Automatización: Automated Daily Settlement & Telegram Summary Dispatcher
def test_47_automated_daily_settlement_and_telegram_report(tmp_path: Path) -> None:
    """
    Test 47: Verification of Automated Daily Settlement & Telegram Reporting:
    1. Peru Timezone alignment (UTC-5 / America/Lima).
    2. Accurate formatting of format_daily_settlement_report:
       - Won, Lost, PUSH counts
       - Win Rate %, Net PnL in Soles (S/. PEN), ROI %
       - Bankroll update and CPPI 85% floor display
    3. Graceful handling of empty slates (no pending bets).
    4. End-to-end integration with NBADailyScheduler.
    """
    from scripts.run_automated_scheduler import NBADailyScheduler, get_peru_time, PERU_OFFSET
    from src.reporting.telegram_bot import TelegramAlertBot
    from src.storage.db import DatabaseManager

    # 1. Timezone verification
    t_pet = get_peru_time()
    assert t_pet.tzinfo == PERU_OFFSET

    # 2. Daily Settlement Report Formatter
    bot = TelegramAlertBot()
    sample_bets = [
        {"game_id": "G_SETTLE_1", "market": "moneyline", "selection": "HOME", "status": "WON", "net_profit_pen": 1.85, "stake_pen": 2.0},
        {"game_id": "G_SETTLE_2", "market": "total_points", "selection": "OVER", "status": "LOST", "net_profit_pen": -2.00, "stake_pen": 2.0},
    ]
    sample_props = [
        {"player_name": "Luka Doncic", "prop_category": "PTS", "selection": "OVER", "line_value": 28.5, "status": "WON", "net_profit_pen": 1.80, "stake_pen": 2.0},
        {"player_name": "LeBron + LAL", "prop_category": "SGP", "selection": "SGP", "line_value": 25.5, "status": "WON", "net_profit_pen": 5.00, "stake_pen": 2.0},
    ]

    report = bot.format_daily_settlement_report(
        matchday_date="2026-11-08",
        settled_bets=sample_bets,
        settled_props=sample_props,
        current_bankroll_pen=106.65,
        initial_bankroll_pen=100.00,
        peak_bankroll_pen=106.65,
        cppi_multiplier=1.0,
    )

    assert "RESUMEN DIARIO DE LIQUIDACIÓN" in report
    assert "2026-11-08" in report
    assert "S/ 106.65 PEN" in report
    assert "3 Ganadas ✅ | 1 Perdidas ❌" in report
    assert "Win Rate:* `75.0%`" in report
    assert "+S/ 6.65 PEN" in report
    assert "Luka Doncic" in report

    # 3. Empty slate handling
    empty_report = bot.format_daily_settlement_report(
        matchday_date="2026-11-08",
        settled_bets=[],
        settled_props=[],
        current_bankroll_pen=100.0,
    )
    assert "No hubo apuestas ni props" in empty_report
    assert "S/ 100.00 PEN" in empty_report

    # 4. Scheduler instantiation with test DB
    DatabaseManager(tmp_path / "sched_test.sqlite3")
    sched = NBADailyScheduler(db_path=tmp_path / "sched_test.sqlite3")
    assert sched.paper_engine.initial_bankroll_pen == 100.00
