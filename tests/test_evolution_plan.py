"""
Unit and integration tests for the Evolution Plan (`tests/test_evolution_plan.py`):
  1. Sub-Bankroll (S/50 PEN) and ParlayTradingEngine (isolation, staking, settlement, immutability).
  2. Hybrid Market Allocation in PaperTradingEngine (70% Totals / 30% Moneyline cap).
  3. Peru Playwright Scraper team matching and quote normalization.
  4. Dual-bankroll Telegram listener status & balance reporting.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from src.config import load_config
from src.ingestion.playwright_scraper import PeruPlaywrightScraper
from src.paper_trading.engine import PaperTradingEngine
from src.paper_trading.parlay_engine import ParlayTradingEngine
from src.reporting.telegram_interactive import TelegramInteractiveListener
from src.storage.db import DatabaseManager


def _seed_game(db: DatabaseManager, game_id: str, matchday_date: str = "2026-11-10") -> None:
    db.execute_insert(
        """
        INSERT OR IGNORE INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
            away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
            features_available_at, source_provider, ingested_at
        ) VALUES (?, '2026-27', ?, '2026-11-10T23:00:00Z', 'TOR', 'MEM', 'SCHEDULED',
                 NULL, NULL, 112.5, 110.2, 98.5, 114.1, 111.0, 100.2, 2, 1,
                 '2026-11-10T12:00:00Z', 'ESPN', '2026-11-10T12:00:00Z')
        """,
        (game_id, matchday_date),
    )


def _seed_prediction(db: DatabaseManager, pred_id: str, game_id: str, market: str, selection: str, line_val: float | None = None) -> None:
    db.execute_insert(
        """
        INSERT OR IGNORE INTO model_versions (
            model_version_id, model_family, market, train_start_date, train_end_date,
            trained_at, hyperparameters_json, is_active, approved_by
        ) VALUES (
            'v8', 'ensemble', 'moneyline',
            '2026-01-01', '2026-11-09', '2026-11-09T12:00:00Z', '{}', 1, 'test'
        )
        """
    )
    db.execute_insert(
        """
        INSERT OR IGNORE INTO predictions (
            prediction_id, game_id, market, selection, line_value, model_version_id,
            raw_probability, calibrated_probability, uncertainty_std, implied_prob_gross,
            implied_prob_fair, bookmaker_overround, decimal_odds_used, odds_provider,
            odds_captured_at, ev_unit, ev_pct, emitted_at, features_snapshot_json
        ) VALUES (
            ?, ?, ?, ?, ?, 'v8',
            0.60, 0.60, 0.05, 0.512, 0.50, 0.045, 1.95, 'TheOddsAPI',
            '2026-11-10T12:00:00Z', 0.10, 10.0, '2026-11-10T12:00:00Z', '{}'
        )
        """,
        (pred_id, game_id, market, selection, line_val),
    )


# -------------------------------------------------------------------------------------------------
# 1. Sub-Bankroll and ParlayTradingEngine Tests
# -------------------------------------------------------------------------------------------------

def test_parlay_engine_initialization_and_isolation(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "dual_bankroll.sqlite3")
    engine = ParlayTradingEngine(db, initial_bankroll_pen=50.00)

    state = engine.get_bankroll_state()
    assert state["initial_bankroll_pen"] == 50.00
    assert state["settled_bankroll_pen"] == 50.00
    assert state["pending_exposure_pen"] == 0.00
    assert state["available_balance_pen"] == 50.00

    # Verify initial ledger event
    ledger_rows = db.fetch_all("SELECT * FROM parlay_bankroll_ledger")
    assert len(ledger_rows) == 1
    assert ledger_rows[0]["event_type"] == "INITIAL_VIRTUAL_BANKROLL"
    assert ledger_rows[0]["settled_bankroll_pen"] == 50.00


def test_parlay_engine_record_and_settlement(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "parlay_test.sqlite3")
    engine = ParlayTradingEngine(
        db=db,
        initial_bankroll_pen=50.00,
        max_stake_pen=5.00,
        min_stake_pen=0.50,
        kelly_fraction=0.40,
    )

    parlay_payload = {
        "parlay_id": "PARLAY_TEST_01",
        "matchday_date": "2026-11-10",
        "strategy_type": "SGP_COPULA",
        "legs": [
            {"game_id": "G1", "market": "moneyline", "selection": "HOME", "decimal_odds": 1.60},
            {"game_id": "G1", "market": "player_prop", "selection": "OVER", "player_name": "Player A", "line": 22.5, "decimal_odds": 1.70},
        ],
        "compound_odds": 2.72,
        "joint_prob": 0.45,
        "compound_ev_pct": 22.4,
        "stake_pen": 2.50,
    }

    placed = engine.record_parlay_bet(parlay_payload)
    assert placed["status"] == "PLACED"
    assert placed["stake_pen"] == 2.50

    state_after_place = engine.get_bankroll_state()
    assert state_after_place["settled_bankroll_pen"] == 50.00
    assert state_after_place["pending_exposure_pen"] == 2.50
    assert state_after_place["available_balance_pen"] == 47.50

    # Settle WON
    settle_res = engine.settle_parlay_bet(
        parlay_id="PARLAY_TEST_01",
        leg_results=[
            {"status": "WON", "summary": "Home Won 108-102"},
            {"status": "WON", "summary": "Player A scored 26"},
        ],
    )
    assert settle_res["status"] == "WON"
    expected_profit = round(2.50 * (2.72 - 1.0), 2)
    assert settle_res["net_profit_pen"] == expected_profit

    state_after_win = engine.get_bankroll_state()
    assert state_after_win["settled_bankroll_pen"] == 50.00 + expected_profit
    assert state_after_win["pending_exposure_pen"] == 0.00


def test_parlay_engine_loss_settlement(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "parlay_loss.sqlite3")
    engine = ParlayTradingEngine(db, initial_bankroll_pen=50.00)

    parlay_payload = {
        "parlay_id": "PARLAY_TEST_LOSS",
        "matchday_date": "2026-11-10",
        "strategy_type": "HIGH_PROB_PARLAY",
        "legs": [
            {"desc": "Leg 1", "decimal_odds": 1.30},
            {"desc": "Leg 2", "decimal_odds": 1.40},
        ],
        "compound_odds": 1.82,
        "joint_prob": 0.65,
        "compound_ev_pct": 18.3,
        "stake_pen": 3.00,
    }
    engine.record_parlay_bet(parlay_payload)

    settle_res = engine.settle_parlay_bet(
        parlay_id="PARLAY_TEST_LOSS",
        leg_results=[
            {"status": "WON", "summary": "Leg 1 hit"},
            {"status": "LOST", "summary": "Leg 2 missed"},
        ],
    )
    assert settle_res["status"] == "LOST"
    assert settle_res["net_profit_pen"] == -3.00

    state = engine.get_bankroll_state()
    assert state["settled_bankroll_pen"] == 47.00
    assert state["available_balance_pen"] == 47.00


def test_parlay_bets_immutability_triggers(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "immutability.sqlite3")
    engine = ParlayTradingEngine(db, initial_bankroll_pen=50.00)

    parlay_payload = {
        "parlay_id": "PARLAY_IMMUTABLE",
        "matchday_date": "2026-11-10",
        "strategy_type": "SGP_COPULA",
        "legs": [{"desc": "L1", "decimal_odds": 1.50}, {"desc": "L2", "decimal_odds": 1.50}],
        "compound_odds": 2.25,
        "joint_prob": 0.50,
        "compound_ev_pct": 12.5,
        "stake_pen": 2.00,
    }
    engine.record_parlay_bet(parlay_payload)
    engine.settle_parlay_bet(
        "PARLAY_IMMUTABLE",
        [{"status": "WON"}, {"status": "WON"}],
    )

    # Attempting to delete or update settled parlay must abort
    with pytest.raises(Exception, match="IMMUTABLE_VIOLATION|DOUBLE_SETTLEMENT"):
        db.execute_insert("DELETE FROM parlay_bets WHERE parlay_id = 'PARLAY_IMMUTABLE'")

    with pytest.raises(Exception, match="DOUBLE_SETTLEMENT_OR_TAMPERING"):
        db.execute_insert(
            "UPDATE parlay_bets SET status = 'LOST' WHERE parlay_id = 'PARLAY_IMMUTABLE'"
        )


# -------------------------------------------------------------------------------------------------
# 2. Hybrid Allocation in PaperTradingEngine Tests (70% Totals / 30% Moneyline)
# -------------------------------------------------------------------------------------------------

def test_hybrid_market_allocation_enforces_caps(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "hybrid_test.sqlite3")
    engine = PaperTradingEngine(
        db=db,
        initial_bankroll_pen=100.00,
        base_stake_pen=1.00,
        max_stake_pen=3.00,
        max_selections_per_matchday=3,
        hybrid_allocation_enabled=True,
        max_totals_per_matchday=2,
        max_moneyline_per_matchday=1,
        staking_mode="FRACTIONAL_KELLY",
    )

    # Seed 4 games
    for i in range(1, 5):
        _seed_game(db, f"G_{i}")

    # Seed predictions: 2 Totals and 2 Moneylines, all positive EV
    candidates = [
        {
            "prediction_id": "P_TOT_1", "game_id": "G_1", "market": "total_points", "selection": "OVER",
            "line_value": 220.5, "decimal_odds_used": 1.95, "calibrated_probability": 0.60, "ev_unit": 0.170,
            "ev_pct": 17.0, "model_version_id": "v8", "emitted_at": "2026-11-10T12:00:00Z",
        },
        {
            "prediction_id": "P_ML_1", "game_id": "G_2", "market": "moneyline", "selection": "HOME",
            "line_value": None, "decimal_odds_used": 1.85, "calibrated_probability": 0.62, "ev_unit": 0.147,
            "ev_pct": 14.7, "model_version_id": "v8", "emitted_at": "2026-11-10T12:00:00Z",
        },
        {
            "prediction_id": "P_ML_2", "game_id": "G_3", "market": "moneyline", "selection": "AWAY",
            "line_value": None, "decimal_odds_used": 1.85, "calibrated_probability": 0.61, "ev_unit": 0.128,
            "ev_pct": 12.8, "model_version_id": "v8", "emitted_at": "2026-11-10T12:00:00Z",
        },
        {
            "prediction_id": "P_TOT_2", "game_id": "G_4", "market": "total_points", "selection": "UNDER",
            "line_value": 215.0, "decimal_odds_used": 1.95, "calibrated_probability": 0.57, "ev_unit": 0.111,
            "ev_pct": 11.1, "model_version_id": "v8", "emitted_at": "2026-11-10T12:00:00Z",
        },
    ]

    for c in candidates:
        _seed_prediction(db, c["prediction_id"], c["game_id"], c["market"], c["selection"], c.get("line_value"))

    res = engine.evaluate_and_record_matchday_selections("2026-11-10", candidates)
    placed = res["placed_bets"]
    assert len(placed) == 3

    markets_placed = [b["market"] for b in placed]
    assert markets_placed.count("total_points") == 2
    assert markets_placed.count("moneyline") == 1

    # Check that the 2nd moneyline was rejected due to MARKET_CAP_REACHED (only 1 ML allowed)
    no_bets = res["no_bet_decisions"]
    rej_ml = next(nb for nb in no_bets if nb["game_id"] == "G_3")
    assert rej_ml["reason_code"] == "MARKET_CAP_REACHED"


# -------------------------------------------------------------------------------------------------
# 3. Peru Playwright Scraper Team Matching and Logic
# -------------------------------------------------------------------------------------------------

def test_playwright_scraper_team_matching() -> None:
    scraper = PeruPlaywrightScraper()
    assert scraper._match_teams("Boston Celtics vs Miami Heat") == ("BOS", "MIA")
    assert scraper._match_teams("Lakers @ Warriors") == ("GSW", "LAL")
    assert scraper._match_teams("Denver Nuggets - Houston Rockets") == ("DEN", "HOU")
    assert scraper._match_teams("Invalid Team vs Another Invalid") is None


def test_playwright_scraper_persists_observed_quotes(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "scraper_db.sqlite3")
    scraper = PeruPlaywrightScraper(db=db)

    _seed_game(db, "ESPN_TOR_MEM", matchday_date="2026-11-10")

    mock_quotes = [
        {
            "provider": "RETAbet Perú",
            "home_team": "TOR",
            "away_team": "MEM",
            "market": "moneyline",
            "selection": "HOME",
            "decimal_odds": 1.65,
            "counterpart_decimal_odds": 2.30,
            "line_value": None,
            "captured_at": "2026-11-10T14:00:00Z",
            "source_type": "OBSERVED",
        },
        {
            "provider": "RETAbet Perú",
            "home_team": "TOR",
            "away_team": "MEM",
            "market": "total_points",
            "selection": "OVER",
            "decimal_odds": 1.91,
            "counterpart_decimal_odds": 1.91,
            "line_value": 224.5,
            "captured_at": "2026-11-10T14:00:00Z",
            "source_type": "OBSERVED",
        },
    ]

    slate_games = [{"game_id": "ESPN_TOR_MEM", "home_team": "TOR", "away_team": "MEM"}]
    inserted = scraper.persist_scraped_quotes(mock_quotes, slate_games)
    assert inserted == 2

    # Verify rows in v_observed_odds_snapshots
    observed = db.fetch_all("SELECT * FROM v_observed_odds_snapshots WHERE game_id = 'ESPN_TOR_MEM'")
    assert len(observed) == 2
    assert all(r["source_type"] == "OBSERVED" for r in observed)


# -------------------------------------------------------------------------------------------------
# 4. Config & Telegram Dual Balance Verification
# -------------------------------------------------------------------------------------------------

def test_config_loader_includes_sub_bankroll_and_hybrid() -> None:
    cfg = load_config()
    assert cfg.sub_bankroll.enabled is True
    assert cfg.sub_bankroll.virtual_bankroll_initial_pen == 50.00
    assert cfg.sub_bankroll.max_stake_pen == 5.00
    assert cfg.hybrid_allocation.enabled is True
    assert cfg.hybrid_allocation.max_totals_per_matchday == 2
    assert cfg.hybrid_allocation.max_moneyline_per_matchday == 1


def test_telegram_listener_dual_banca(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "tg.sqlite3")
    listener = TelegramInteractiveListener(
        bot_token="TEST_TOKEN",
        allowed_chat_ids=["12345"],
        db=db,
    )
    reply = listener.process_message(
        chat_id="12345",
        text="/banca",
        from_user={"first_name": "Andre", "username": "andbo"},
    )
    assert "CENTRO FINANCIERO DUAL" in reply
    assert "BANKROLL PRINCIPAL (S/ 100.00 PEN" in reply
    assert "SUB-BANKROLL COMBINADAS (S/ 50.00 PEN" in reply


def test_parlay_engine_record_candidate_parlays(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "cand_parlays.sqlite3")
    engine = ParlayTradingEngine(db, initial_bankroll_pen=50.00, max_parlays_per_matchday=2)

    candidates = [
        {
            "parlay_id": "HP_TEST_01",
            "strategy": "SAME_GAME_ANCHOR",
            "type": "RETABET_SGP",
            "legs": [
                {"game_id": "G1", "market": "moneyline", "selection": "HOME", "odds": 1.75},
                {"game_id": "G1", "market": "player_points", "selection": "OVER", "line_value": 24.5, "player_name": "J. Tatum", "odds": 1.85},
            ],
            "decimal_odds": 3.20,
            "p_joint": 0.38,
            "ev_pct": 21.6,
            "stake_pen": 2.50,
            "emitted_at": "2026-11-10T12:00:00Z",
        },
        {
            "sgp_id": "SGP_TEST_02",
            "game_id": "G2",
            "game_selection": "AWAY",
            "team": "LAL",
            "player_name": "A. Davis",
            "prop_category": "rebounds",
            "prop_selection": "OVER",
            "prop_line": 12.5,
            "offered_sgp_odds": 2.90,
            "p_joint": 0.40,
            "ev_pct": 16.0,
            "kelly_stake_pen": 2.00,
            "emitted_at": "2026-11-10T12:00:00Z",
        },
        {
            "parlay_id": "HP_TEST_03_EXCESS",
            "strategy": "SAME_GAME_ANCHOR",
            "legs": [
                {"game_id": "G3", "market": "moneyline", "selection": "HOME", "odds": 1.50},
                {"game_id": "G3", "market": "total_points", "selection": "OVER", "line_value": 220.5, "odds": 1.90},
            ],
            "decimal_odds": 2.85,
            "p_joint": 0.42,
            "ev_pct": 19.7,
            "stake_pen": 2.00,
        },
    ]

    placed = engine.record_candidate_parlays(candidates, matchday_date="2026-11-10")
    # Only 2 placed because max_parlays_per_matchday == 2
    assert len(placed) == 2
    assert placed[0]["parlay_id"] == "HP_TEST_01"
    assert placed[1]["parlay_id"] == "SGP_TEST_02"

    state = engine.get_bankroll_state()
    assert state["pending_exposure_pen"] == 4.50
    assert state["available_balance_pen"] == 45.50

    # Idempotency check: recording again should place 0 new bets
    placed_again = engine.record_candidate_parlays(candidates, matchday_date="2026-11-10")
    assert len(placed_again) == 0


def test_parlay_engine_settle_pending_parlays_end_to_end(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "settle_parlays.sqlite3")
    engine = ParlayTradingEngine(db, initial_bankroll_pen=50.00)

    # 1. Seed two games
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
            away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
            features_available_at, source_provider, ingested_at
        ) VALUES
        ('GAME_A', '2026-27', '2026-11-10', '2026-11-10T20:00:00Z', 'BOS', 'NYK', 'FINAL', 115, 105, 115.0, 110.0, 100.0, 112.0, 111.0, 99.0, 2, 1, '2026-11-10T12:00:00Z', 'ESPN', '2026-11-10T12:00:00Z'),
        ('GAME_B', '2026-27', '2026-11-10', '2026-11-10T22:30:00Z', 'GSW', 'LAC', 'FINAL', 120, 110, 116.0, 112.0, 102.0, 114.0, 113.0, 100.0, 1, 2, '2026-11-10T12:00:00Z', 'ESPN', '2026-11-10T12:00:00Z')
        """
    )

    # 2. Record a winning parlay (Game A ML Home + Game B Total Over 215.5)
    p1 = {
        "parlay_id": "PARLAY_WIN_01",
        "matchday_date": "2026-11-10",
        "strategy_type": "HIGH_PROB_PARLAY",
        "legs": [
            {"game_id": "GAME_A", "market": "moneyline", "selection": "HOME", "decimal_odds": 1.50},
            {"game_id": "GAME_B", "market": "total_points", "selection": "OVER", "line_value": 215.5, "decimal_odds": 1.90},
        ],
        "compound_odds": 2.85,
        "joint_prob": 0.45,
        "compound_ev_pct": 28.25,
        "stake_pen": 4.00,
        "emitted_at": "2026-11-10T12:00:00Z",
    }
    engine.record_parlay_bet(p1)

    # 3. Record a losing parlay (Game A ML Away + Player Prop)
    p2 = {
        "parlay_id": "PARLAY_LOSS_02",
        "matchday_date": "2026-11-10",
        "strategy_type": "SGP_COPULA",
        "legs": [
            {"game_id": "GAME_A", "market": "moneyline", "selection": "AWAY", "decimal_odds": 2.60},
            {"game_id": "GAME_A", "market": "player_points", "selection": "OVER", "line_value": 25.5, "player_name": "J. Brown", "decimal_odds": 1.85},
        ],
        "compound_odds": 4.81,
        "joint_prob": 0.25,
        "compound_ev_pct": 20.25,
        "stake_pen": 2.00,
        "emitted_at": "2026-11-10T12:00:00Z",
    }
    engine.record_parlay_bet(p2)

    boxscores = {
        "GAME_A": {
            "J. Brown": {"minutes": 34.0, "pts": 28.0, "reb": 6.0, "ast": 4.0},
        }
    }

    settled = engine.settle_pending_parlays(game_boxscores=boxscores, settled_at="2026-11-11T03:00:00Z")
    assert len(settled) == 2

    res_map = {r["parlay_id"]: r for r in settled}
    # P1 won: 4.00 * (2.85 - 1.0) = 7.40 net profit
    assert res_map["PARLAY_WIN_01"]["status"] == "WON"
    assert res_map["PARLAY_WIN_01"]["net_profit_pen"] == 7.40

    # P2 lost: -2.00 net profit
    assert res_map["PARLAY_LOSS_02"]["status"] == "LOST"
    assert res_map["PARLAY_LOSS_02"]["net_profit_pen"] == -2.00

    state = engine.get_bankroll_state()
    # 50.00 + 7.40 - 2.00 = 55.40
    assert state["settled_bankroll_pen"] == 55.40
    assert state["pending_exposure_pen"] == 0.00
    assert state["cumulative_net_profit_pen"] == 5.40


def test_telegram_daily_settlement_report_dual_bankroll() -> None:
    from src.reporting.telegram_bot import TelegramAlertBot
    bot = TelegramAlertBot(bot_token=None)

    settled_bets = [
        {"status": "WON", "net_profit_pen": 2.85, "stake_pen": 3.00, "game_id": "G1", "market": "total_points", "selection": "OVER"},
    ]
    parlay_state = {
        "settled_bankroll_pen": 54.50,
        "cumulative_net_profit_pen": 4.50,
        "roi_pct": 9.0,
    }
    settled_parlays = [
        {"parlay_id": "HP_01", "status": "WON", "summary": "WON: odds 2.50", "net_profit_pen": 4.50},
    ]

    msg = bot.format_daily_settlement_report(
        matchday_date="2026-11-10",
        settled_bets=settled_bets,
        settled_props=[],
        current_bankroll_pen=102.85,
        initial_bankroll_pen=100.0,
        parlay_bankroll_state=parlay_state,
        settled_parlays=settled_parlays,
    )

    assert "Bankroll Principal:*" in msg
    assert "102.85 PEN" in msg
    assert "Sub-Bankroll Combinadas (S/ 50.00 PEN — Alpha Lab)" in msg
    assert "S/ 54.50 PEN" in msg
    assert "HP_01" in msg
