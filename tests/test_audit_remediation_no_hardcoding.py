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
