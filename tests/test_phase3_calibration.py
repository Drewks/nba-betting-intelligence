"""
Phase 3 Verification Tests (`tests/test_phase3_calibration.py`):
1. Validation of CLVMetaLabelingConfig and CopulaCorrelationsConfig in src/config.py.
2. End-to-end execution and metric validation of scripts/calibrate_parameters.py.
3. Reactivity and empirical probability computation in predict_clv_meta_label.
4. Dynamic loading and mathematical consistency of VineCopulaSGP with calibrated weights.
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np

from scripts.calibrate_parameters import calibrate_all_and_save
from src.config import load_config, CLVMetaLabelingConfig, CopulaCorrelationsConfig
from src.prediction.ev_calculator import predict_clv_meta_label
from src.prediction.vine_copula import VineCopulaSGP


def test_phase3_config_loading_and_dataclasses() -> None:
    """Verifies that Phase 3 configs load and have correct typing."""
    cfg = load_config()
    assert isinstance(cfg.clv_meta_labeling, CLVMetaLabelingConfig)
    assert isinstance(cfg.copula_correlations, CopulaCorrelationsConfig)
    assert cfg.clv_meta_labeling.enabled is True
    assert cfg.clv_meta_labeling.time_decay_rate == 0.04
    assert cfg.clv_meta_labeling.adverse_steam_threshold == -0.040
    assert cfg.copula_correlations.enabled is True


def test_phase3_calibrate_parameters_script_execution(tmp_path: Path) -> None:
    """Verifies that calibrate_parameters runs end-to-end and outputs valid empirical metrics."""
    db_path = Path("data/nba_intelligence.sqlite3")
    assert db_path.exists(), "Production SQLite database required for calibration test"

    out_json = tmp_path / "test_calibrated_weights.json"
    payload = calibrate_all_and_save(db_path, out_json)

    assert out_json.exists()
    assert "clv_meta_labeling" in payload
    assert "sgp_copula_correlations" in payload

    clv = payload["clv_meta_labeling"]
    assert clv["sample_size"] > 100
    assert clv["accuracy"] >= 0.80
    assert clv["roc_auc"] >= 0.85
    assert clv["brier_score"] <= 0.25
    assert "coef_steam_delta" in clv
    assert clv["coef_steam_delta"] > 0.0  # Steam must positively predict beating close

    corrs = payload["sgp_copula_correlations"]
    assert "PTS,3PM" in corrs
    assert "PTS,REB" in corrs
    assert 0.10 <= corrs["PTS,3PM"] <= 0.70
    assert 0.05 <= corrs["PTS,REB"] <= 0.40


def test_phase3_predict_clv_meta_label_with_calibrated_weights() -> None:
    """Tests that predict_clv_meta_label properly consumes calibrated parameters."""
    # 1. Adverse steam triggers guard
    res_adv = predict_clv_meta_label(
        odds_record={"decimal_odds": 1.95, "captured_at": "2026-11-10T12:00:00Z"},
        game_start_time="2026-11-10T18:00:00Z",
        steam_delta=-0.045,
    )
    assert res_adv["meta_label_pass"] is False
    assert res_adv["reason_code"] == "ADVERSE_STEAM_DECAY"

    # 2. Strong positive steam + low overround predicts high positive CLV
    res_fav = predict_clv_meta_label(
        odds_record={"decimal_odds": 1.95, "captured_at": "2026-11-10T16:00:00Z"},
        game_start_time="2026-11-10T18:00:00Z",
        steam_delta=0.035,
        conformal_width=0.04,
        overround=0.025,
    )
    assert res_fav["meta_label_pass"] is True
    assert res_fav["p_positive_clv"] > 0.55
    assert res_fav["reason_code"] == "PASS"

    # 3. Custom weights injection test
    custom_w = {
        "intercept": 0.0,
        "coef_steam_delta": 50.0,
        "coef_conformal_width_excess": -2.0,
        "coef_disagreement_excess": -1.0,
        "coef_overround_excess": -1.0,
        "time_decay_rate": 0.05,
        "max_hours_to_tipoff": 10.0,
        "adverse_steam_threshold": -0.050,
        "min_p_clv_threshold": 0.50,
        "exp_clv_multiplier": 8.0,
    }
    res_custom = predict_clv_meta_label(
        odds_record={"decimal_odds": 2.00, "captured_at": "2026-11-10T17:00:00Z"},
        game_start_time="2026-11-10T18:00:00Z",
        steam_delta=0.020,
        custom_weights=custom_w,
    )
    assert res_custom["meta_label_pass"] is True
    assert res_custom["p_positive_clv"] > 0.50


def test_phase3_vine_copula_dynamic_correlations(tmp_path: Path) -> None:
    """Tests VineCopulaSGP with calibrated correlations file."""
    # Create custom weights JSON
    custom_json = tmp_path / "custom_weights.json"
    custom_data = {
        "metadata": {"version": "test"},
        "sgp_copula_correlations": {
            "PTS,3PM": 0.52,
            "PTS,REB": 0.18,
            "GAME_WIN,PTS": 0.38,
        },
    }
    custom_json.write_text(json.dumps(custom_data), encoding="utf-8")

    copula = VineCopulaSGP(weights_path=custom_json)
    assert copula.correlations[("PTS", "3PM")] == 0.52
    assert copula.correlations[("GAME_WIN", "PTS")] == 0.38

    # Matrix building test
    legs = [
        {"player_name": "Luka Doncic", "team": "DAL", "category": "PTS", "selection": "OVER"},
        {"player_name": "Luka Doncic", "team": "DAL", "category": "3PM", "selection": "OVER"},
    ]
    mat = copula.build_sgp_correlation_matrix(legs)
    assert mat.shape == (2, 2)
    assert np.isclose(mat[0, 1], 0.52)
    assert np.all(np.linalg.eigvalsh(mat) >= -1e-6)
