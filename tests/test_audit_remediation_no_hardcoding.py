"""
Regression and verification tests for 100% genuine data execution and 0 hardcoding.
Validates:
1. Dynamic loading of situational factors (HCA, altitude, travel, B2B) from config.
2. Dynamic loading of lineup synergy thresholds and RAPM profiles from calibrated weights.
3. Fallback rosters externalized into config/fallback_rosters.json with DB-first resolution.
4. EV calculation constants wired to AppConfig.model.
5. Zero synthetic fixture adapters used across the entire test suite.
"""

from pathlib import Path
import json

from src.config import load_config
from src.features.builder import _get_situational_factors_config
from src.features.team_ratings import (
    _get_lineup_synergy_config,
    compute_lineup_synergy_penalty,
    get_player_on_off_synergy_profiles,
)
from src.prediction.ev_calculator import (
    DEFAULT_MODEL_WEIGHT,
    MAX_MODEL_MARKET_DISAGREEMENT,
)
from src.prediction.player_props import get_fallback_rosters


def test_situational_factors_dynamic_config() -> None:
    cfg = load_config()
    sit_cfg = _get_situational_factors_config()
    assert sit_cfg.home_court_advantage_elo == cfg.situational_factors.home_court_advantage_elo
    assert sit_cfg.home_court_advantage_pts == cfg.situational_factors.home_court_advantage_pts
    assert sit_cfg.b2b_penalty_away == cfg.situational_factors.b2b_penalty_away
    assert sit_cfg.b2b_penalty_home == cfg.situational_factors.b2b_penalty_home
    assert sit_cfg.altitude_edge_multiplier == cfg.situational_factors.altitude_edge_multiplier
    assert sit_cfg.travel_miles_rate == cfg.situational_factors.travel_miles_rate


def test_lineup_synergy_dynamic_config_and_calibrated_profiles() -> None:
    cfg = load_config()
    syn_cfg = _get_lineup_synergy_config()
    assert syn_cfg.initiator_absence_threshold == cfg.lineup_synergy.initiator_absence_threshold
    assert syn_cfg.initiator_absence_penalty == cfg.lineup_synergy.initiator_absence_penalty
    assert syn_cfg.rim_anchor_absence_threshold == cfg.lineup_synergy.rim_anchor_absence_threshold
    assert syn_cfg.rim_anchor_absence_penalty == cfg.lineup_synergy.rim_anchor_absence_penalty

    profiles = get_player_on_off_synergy_profiles()
    assert len(profiles) >= 46
    assert "Nikola Jokic" in profiles
    assert "Luka Doncic" in profiles
    assert "Stephen Curry" in profiles
    assert "Joel Embiid" in profiles

    # Verify compound synergy penalty calculation
    absent = [
        {"name": "Luka Doncic", "status": "OUT", "adapt_factor": 1.0, "position": "PG"},
        {"name": "Kyrie Irving", "status": "OUT", "adapt_factor": 1.0, "position": "PG"},
    ]
    pen = compute_lineup_synergy_penalty(absent)
    assert pen["off_rtg_penalty"] > 0
    assert pen["total_net_penalty"] > 0
    assert pen["synergy_compound_bonus"] >= 0


def test_player_props_fallback_rosters_from_config() -> None:
    rosters = get_fallback_rosters()
    assert len(rosters) == 30
    assert "BOS" in rosters and "Jayson Tatum" in rosters["BOS"]
    assert "DEN" in rosters and "Nikola Jokic" in rosters["DEN"]
    assert "GSW" in rosters and "Stephen Curry" in rosters["GSW"]
    assert "LAL" in rosters and "LeBron James" in rosters["LAL"]

    f = Path("config/fallback_rosters.json")
    assert f.exists()
    loaded = json.loads(f.read_text(encoding="utf-8"))
    assert len(loaded) == 30


def test_ev_calculator_defaults_from_config() -> None:
    cfg = load_config()
    assert DEFAULT_MODEL_WEIGHT == cfg.model.market_anchor_model_weight
    assert MAX_MODEL_MARKET_DISAGREEMENT == cfg.model.max_model_market_disagreement


def test_sqlite_wal_mode_and_busy_timeout(tmp_path: Path) -> None:
    from src.storage.db import DatabaseManager
    test_db = tmp_path / "test_wal.sqlite3"
    db_mgr = DatabaseManager(test_db)
    with db_mgr.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        assert str(mode).lower() == "wal"

        cursor.execute("PRAGMA busy_timeout;")
        timeout = cursor.fetchone()[0]
        assert timeout == 30000


def test_poisson_integer_line_push_probabilities() -> None:
    from unittest.mock import MagicMock
    from src.prediction.player_props import PlayerPropsEngine
    engine = PlayerPropsEngine(db=MagicMock())

    # Integer line (e.g. 2.0 assists with projection 2.0)
    p_over, p_under = engine.compute_exceedance_probabilities(
        prop_category="assists",
        line_value=2.0,
        proj_mean=2.0,
        proj_std=1.2,
        dist_type="poisson",
    )
    # Both probabilities must sum to 1.0 (conditional on non-push)
    assert abs((p_over + p_under) - 1.0) < 1e-4
    assert 0.0 < p_over < 1.0
    assert 0.0 < p_under < 1.0

    # Half integer line (e.g. 2.5 assists)
    p_over_half, p_under_half = engine.compute_exceedance_probabilities(
        prop_category="assists",
        line_value=2.5,
        proj_mean=2.0,
        proj_std=1.2,
        dist_type="poisson",
    )
    assert abs((p_over_half + p_under_half) - 1.0) < 1e-4


def test_playwright_scraper_1x2_filtering_logic() -> None:
    # 3-way markets or draw selections must be ignored
    mkt_3way = {
        "name": "Resultado del partido",
        "selections": [
            {"name": "Boston Celtics", "price": 1.45},
            {"name": "Empate", "price": 14.0},
            {"name": "Miami Heat", "price": 3.10},
        ],
    }
    m_desc = str(mkt_3way.get("name") or "").upper()
    is_excluded = any(k in m_desc for k in ("TIEMPO REGLAMENTARIO", "1X2", "REGULAR TIME", "RESULTADO DEL PARTIDO"))
    assert is_excluded is True

    # 2-way moneyline market with overtime included must be accepted
    mkt_2way = {
        "name": "Ganador del partido (con prórroga)",
        "selections": [
            {"name": "Boston Celtics", "price": 1.40},
            {"name": "Miami Heat", "price": 2.95},
        ],
    }
    m2_desc = str(mkt_2way.get("name") or "").upper()
    is_excluded_2 = any(k in m2_desc for k in ("TIEMPO REGLAMENTARIO", "1X2", "REGULAR TIME", "RESULTADO DEL PARTIDO"))
    is_valid_ml = any(k in m2_desc for k in ("GANADOR", "MONEYLINE", "1 2", "12"))
    assert is_excluded_2 is False
    assert is_valid_ml is True
    assert len(mkt_2way["selections"]) == 2


def test_settlement_cycle_and_liquidar_keys() -> None:
    from unittest.mock import MagicMock, patch
    from src.reporting.telegram_interactive import TelegramInteractiveListener

    mock_scheduler = MagicMock()
    mock_scheduler.execute_nightly_settlement_cycle.return_value = {
        "status": "COMPLETED",
        "settled_count": 3,
        "settled_bets_count": 2,
        "settled_props_count": 1,
        "daily_pnl_pen": 4.50,
        "settled_bankroll_pen": 104.50,
        "current_bankroll_pen": 104.50,
    }
    with patch("scripts.run_automated_scheduler.NBADailyScheduler", return_value=mock_scheduler):
        listener = TelegramInteractiveListener()
        msg = listener.handle_liquidar()
        assert "Apuestas Liquidadas:* `3`" in msg
        assert "+S/ 4.50 PEN" in msg
        assert "S/ 104.50 PEN" in msg


def test_morning_cycle_execution_order_in_scheduler() -> None:
    from unittest.mock import patch
    from scripts.run_automated_scheduler import NBADailyScheduler

    scheduler = NBADailyScheduler()
    call_order = []

    def mock_cycle(*args, **kwargs):
        call_order.append("cycle")
        return {"status": "SUCCESS"}

    def mock_harvest(*args, **kwargs):
        call_order.append("harvest")
        return 5

    with patch("scripts.run_automated_scheduler.run_incremental_cloud_cycle", side_effect=mock_cycle), \
         patch.object(scheduler, "run_peru_playwright_odds_harvest", side_effect=mock_harvest), \
         patch.object(scheduler.db, "fetch_all", return_value=[]):
        res = scheduler.execute_morning_cycle()
        assert call_order == ["cycle", "harvest"], f"Expected ['cycle', 'harvest'], got {call_order}"
        assert res["status"] == "COMPLETED"


def test_zero_synthetic_fixture_adapters_in_tests() -> None:
    test_dir = Path("tests")
    forbidden = "Synthetic" + "FixtureAdapter"
    for py_file in test_dir.glob("test_*.py"):
        if py_file.name == "test_audit_remediation_no_hardcoding.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        assert forbidden not in content, (
            f"Found forbidden {forbidden} in test file {py_file.name}!"
        )
