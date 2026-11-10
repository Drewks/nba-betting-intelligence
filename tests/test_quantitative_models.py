"""
Statistical Models, Monte Carlo, Conformal Prediction and Ensemble Tests (`tests/test_quantitative_models.py`).
Modular test suite extracted from legacy test_nba_intelligence monolith.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import numpy as np
import pytest

from src.calibration.calibrator import ProbabilityCalibrator
from src.paper_trading.engine import PaperTradingEngine
from src.storage.db import DatabaseManager
from src.validation.validator import (
    TemporalLeakageError,
)
from tests.helpers import _seed_sample_game_and_prediction



# 19. Motor Híbrido Modelo G (ML + 10,000 Simulaciones Monte Carlo con Overtime/Blowout + Conformal sobre Datos Históricos Reales)
def test_19_deep_montecarlo_hybrid_model() -> None:
    from src.models.statistical_models import DeepMonteCarloHybridModel, EnsembleStackingModel

    conn = sqlite3.connect("data/nba_intelligence.sqlite3")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM games WHERE status = 'FINAL' ORDER BY game_start_time LIMIT 50")
    games = [dict(r) for r in cur.fetchall()]
    conn.close()

    hist = games[:35]
    target_game = games[36]

    mc_model = DeepMonteCarloHybridModel("model_g_test", n_simulations=10000)
    mc_model.fit(hist, target_game["game_start_time"])
    sim_1 = mc_model.simulate_matchup(target_game, hist, line_value=228.5)
    sim_2 = mc_model.simulate_matchup(target_game, hist, line_value=228.5)

    # Deterministic 10,000-simulation reproducibility
    assert sim_1["p_home_mc"] == sim_2["p_home_mc"]
    assert sim_1["p_over_mc"] == sim_2["p_over_mc"]
    assert sim_1["n_simulations"] == 10000
    assert 0.00 <= sim_1["overtime_prob"] <= 0.25
    assert 0.00 <= sim_1["blowout_prob"] <= 0.65
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
    from src.prediction.ev_calculator import (
        DEFAULT_MODEL_WEIGHT,
        compute_market_consensus,
        evaluate_market_opportunity,
        market_anchored_probability,
    )

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


def test_25_v4_model_breakthrough_and_calibration_guards() -> None:
    """Validates V4 pace-decoupled ratings, enriched feature vector, OOS ensemble weights, and small-sample calibration intercept guard."""
    from src.features.builder import build_pregame_features
    from src.features.team_ratings import compute_pregame_team_ratings

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
    from src.prediction.ev_calculator import compute_line_steam, evaluate_market_opportunity

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
    from src.calibration.calibrator import (
        VennAbersConformalInterval,
        conformal_lower_bound_ev,
    )
    from src.paper_trading.engine import PaperTradingEngine
    from src.prediction.ev_calculator import evaluate_market_opportunity

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
    import pytest
    from src.backtesting.hyperparameter_optimizer import OptunaWalkForwardOptimizer

    optimizer = OptunaWalkForwardOptimizer(seed=42)

    # 1. Reject insufficient games
    with pytest.raises(ValueError, match="Insufficient games"):
        optimizer.optimize(games=[], n_trials=2)

    # 2. Run optimization over deterministic walk-forward schedule with genuine historical games
    conn = sqlite3.connect("data/nba_intelligence.sqlite3")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM games WHERE status = 'FINAL' ORDER BY game_start_time LIMIT 120")
    games = [dict(r) for r in cur.fetchall()]
    conn.close()

    out_json = tmp_path / "optimal_hyperparameters.json"
    summary = optimizer.optimize(
        games=games,
        n_trials=4,
        eval_slice_size=25,
        output_json_path=out_json,
    )

    assert summary["n_trials"] == 4
    assert summary["eval_sample_size"] == 25
    assert "best_hyperparameters" in summary
    assert "best_score" in summary
    assert "baseline_score" in summary
    assert out_json.exists()

    loaded = json.loads(out_json.read_text(encoding="utf-8"))
    assert loaded["best_score"] == summary["best_score"]
    best_p = summary["best_hyperparameters"]
    assert 0.010 <= best_p["alpha_slow"] <= 0.080
    assert 0.080 <= best_p["alpha_fast"] <= 0.200
    assert "spread_sigma" in best_p
    assert "momentum_blend_weight" in best_p
    # No fake market anchor is tuned (historical games carry no observed market probability)
    assert "market_model_weight" not in best_p
    # Adoption is decided on an untouched holdout window, never on the tuning window
    assert summary["holdout_sample_size"] > 0
    assert set(summary["holdout"]) >= {"baseline_score", "best_score"}
    assert summary["adoption_decision"] in ("ADOPT_ON_HOLDOUT_IMPROVEMENT", "REJECT_NO_HOLDOUT_IMPROVEMENT")


def test_36_v8_clean_four_factors_and_garbage_time_filtering() -> None:
    """
    Test 36 (V8 Phase 1 Verification):
    1. Dean Oliver Four Factors tracking in compute_pregame_team_ratings (eFG%, TOV%, ORB%, FTR).
    2. Garbage-Time possession dampening (clean_possession_weight) when blowout margin > 18.
    3. Integration into build_pregame_features (four_factors_diff, shot_quality_xeFG_diff).
    4. End-to-end model compatibility with PointMarginModel and AdvancedGBMModel.
    """
    from src.features.team_ratings import compute_pregame_team_ratings
    from src.features.builder import build_pregame_features
    from src.models.statistical_models import PointMarginModel

    sample_games = [
        {
            "game_id": "G_FF_1",
            "game_start_time": "2026-10-20T00:00:00Z",
            "home_team": "BOS",
            "away_team": "NYK",
            "status": "FINAL",
            "home_score": 126,
            "away_score": 98,
            "home_box_stats": {
                "fieldGoalsMade": 46,
                "fieldGoalsAttempted": 86,
                "threePointFieldGoalsMade": 18,
                "threePointFieldGoalsAttempted": 38,
                "freeThrowsAttempted": 20,
                "turnovers": 10,
                "offensiveRebounds": 11,
            },
            "away_box_stats": {
                "fieldGoalsMade": 36,
                "fieldGoalsAttempted": 90,
                "threePointFieldGoalsMade": 9,
                "threePointFieldGoalsAttempted": 32,
                "freeThrowsAttempted": 22,
                "turnovers": 16,
                "defensiveRebounds": 30,
            },
        },
        {
            "game_id": "G_FF_2",
            "game_start_time": "2026-10-22T00:00:00Z",
            "home_team": "BOS",
            "away_team": "MIA",
            "status": "FINAL",
            "home_score": 118,
            "away_score": 112,
        },
        {
            "game_id": "G_FF_TARGET",
            "game_start_time": "2026-10-25T00:00:00Z",
            "home_team": "BOS",
            "away_team": "LAL",
            "status": "SCHEDULED",
            "home_score": None,
            "away_score": None,
        },
    ]

    ratings = compute_pregame_team_ratings(sample_games)
    assert "G_FF_TARGET" in ratings
    target_r = ratings["G_FF_TARGET"]
    assert "four_factors_diff" in target_r
    assert "shot_quality_xeFG_diff" in target_r
    assert "home_efg" in target_r
    assert "away_efg" in target_r
    assert target_r["home_efg"] > 0.50
    assert -0.20 <= target_r["four_factors_diff"] <= 0.20

    # Test build_pregame_features integration
    target_game_dict = {
        "game_id": "G_FF_TARGET",
        "game_start_time": "2026-10-25T00:00:00Z",
        "home_team": "BOS",
        "away_team": "LAL",
        "status": "SCHEDULED",
        "home_off_rtg": target_r["home_off_rtg"],
        "home_def_rtg": target_r["home_def_rtg"],
        "home_pace": target_r["home_pace"],
        "away_off_rtg": target_r["away_off_rtg"],
        "away_def_rtg": target_r["away_def_rtg"],
        "away_pace": target_r["away_pace"],
        "home_rest_days": 3,
        "away_rest_days": 2,
        "four_factors_diff": target_r["four_factors_diff"],
        "shot_quality_xeFG_diff": target_r["shot_quality_xeFG_diff"],
        "features_available_at": "2026-10-24T18:00:00Z",
    }
    feats = build_pregame_features(target_game_dict, sample_games[:2], market="moneyline")
    assert "four_factors_diff" in feats
    assert "shot_quality_xeFG_diff" in feats
    assert isinstance(feats["four_factors_diff"], float)

    # Test model training and prediction with enriched Four Factors features
    pm = PointMarginModel("model_c_v8_test")
    pm.fit(sample_games[:2], "2026-10-24T00:00:00Z")
    pred_c = pm.predict_moneyline(target_game_dict, sample_games[:2])
    assert 0.05 <= pred_c["p_home"] <= 0.95


def test_37_v8_market_residual_model_and_clv_meta_labeling(tmp_path: Path) -> None:
    """
    Test 37 (V8 Phase 2 Verification):
    1. MarketResidualModel (logit-space micro-edge Delta_z on Shin sharp base).
    2. predict_clv_meta_label likelihood scoring and reason codes.
    3. PaperTradingEngine integration blocking candidates that fail CLV meta-labeling.
    """
    from src.models.statistical_models import MarketResidualModel
    from src.prediction.ev_calculator import predict_clv_meta_label

    # 1. Test MarketResidualModel in logit space
    mrm = MarketResidualModel("test_res_v8")
    sharp_p = 0.55
    res_pos = mrm.predict_residual(
        features={
            "four_factors_diff": 0.04,
            "shot_quality_xeFG_diff": 0.02,
            "fatigue_diff": 1.5,
            "altitude_advantage": 1.2,
            "travel_miles_diff": 800.0,
            "rest_diff": 1.0,
        },
        sharp_home_prob=sharp_p,
    )
    assert res_pos["p_home"] > sharp_p
    assert res_pos["delta_logit"] > 0.0
    assert abs(res_pos["delta_logit"]) <= 0.45

    # 2. Test predict_clv_meta_label
    # Adverse steam move triggers guard
    res_adverse = predict_clv_meta_label(
        odds_record={"decimal_odds": 1.95, "captured_at": "2026-11-07T12:00:00Z"},
        game_start_time="2026-11-07T18:00:00Z",
        steam_delta=-0.045,
    )
    assert res_adverse["meta_label_pass"] is False
    assert res_adverse["reason_code"] == "ADVERSE_STEAM_DECAY"

    # Positive steam + tight interval produces high probability of positive CLV
    res_favorable = predict_clv_meta_label(
        odds_record={"decimal_odds": 1.95, "captured_at": "2026-11-07T16:00:00Z"},
        game_start_time="2026-11-07T18:00:00Z",
        steam_delta=0.035,
        conformal_width=0.04,
        overround=0.025,
    )
    assert res_favorable["meta_label_pass"] is True
    assert res_favorable["p_positive_clv"] > 0.55

    # 3. Test PaperTradingEngine blocking candidates that fail CLV meta-labeling
    db = DatabaseManager(tmp_path / "test_p37.sqlite3")
    engine = PaperTradingEngine(db=db, initial_bankroll_pen=100.0, dynamic_conviction_staking=True, max_stake_pen=6.00)
    p_fail = _seed_sample_game_and_prediction(db, "G_CLV_FAIL")

    decisions = engine.evaluate_and_record_matchday_selections(
        "2026-11-07",
        [
            {
                "prediction_id": p_fail,
                "game_id": "G_CLV_FAIL",
                "market": "moneyline",
                "selection": "HOME",
                "decimal_odds_used": 1.95,
                "calibrated_probability": 0.58,
                "ev_unit": 0.09,
                "ev_pct": 9.0,
                "model_version_id": "model_c_test_v1",
                "meta_label_pass": False,
                "meta_label_reason": "NEGATIVE_EXPECTED_CLV",
                "p_positive_clv": 0.38,
                "emitted_at": "2026-11-07T12:00:00Z",
            }
        ],
    )
    assert len(decisions["placed_bets"]) == 0
    assert len(decisions["no_bet_decisions"]) == 1
    assert decisions["no_bet_decisions"][0]["reason_code"] == "NEGATIVE_EXPECTED_CLV"


# 43. V9 Fase 1: Hurdle Model for Player Minutes, Blowout Hazard & Referee Foul Trouble
def test_43_hurdle_minutes_model() -> None:
    """
    Test 43 (V9 Phase 1 Verification):
    1. Hurdle model stage 1: P(Minutes > 0) classification (ACTIVE vs QUESTIONABLE vs OUT).
    2. Quantile regression stage 2: P10 floor, P50 median, P90 ceiling.
    3. Logistic blowout hazard: Starters in blowouts (|spread| >= 12.5) lose minutes.
    4. Referee crew chief foul trouble hazard model.
    5. Integration into PlayerPropsEngine.project_player_stats.
    """
    from src.prediction.minutes_model import MinutesProjectionEngine
    from src.prediction.player_props import PlayerPropsEngine

    engine = MinutesProjectionEngine()

    # 1. Participation hurdle probability
    p_act = engine.predict_participation_probability("ACTIVE", days_rest=2)
    p_q = engine.predict_participation_probability("QUESTIONABLE", days_rest=1)
    p_out = engine.predict_participation_probability("OUT", days_rest=0)
    assert p_act >= 0.95
    assert 0.40 <= p_q <= 0.60
    assert p_out == 0.0

    # 2. Quantile ordering and validity
    proj = engine.predict_minutes_quantiles(base_minutes=35.0, spread=3.0, is_starter=True)
    assert proj["p10_floor"] < proj["p50_median"] < proj["p90_ceiling"]
    assert 30.0 <= proj["p50_median"] <= 36.0

    # 3. Logistic Blowout Risk: Close game vs blowout game
    proj_close = engine.predict_minutes_quantiles(base_minutes=35.0, spread=2.0, is_starter=True)
    proj_blowout = engine.predict_minutes_quantiles(base_minutes=35.0, spread=15.0, is_starter=True)
    assert proj_blowout["blowout_risk"] > proj_close["blowout_risk"]
    assert proj_blowout["p50_median"] < proj_close["p50_median"]
    assert proj_blowout["blowout_delta_minutes"] < -1.5

    # 4. Referee foul trouble hazard
    proj_lenient_ref = engine.predict_minutes_quantiles(
        base_minutes=32.0, spread=3.0, is_starter=True, referee_foul_rate=0.85, foul_trouble_prone=False
    )
    proj_strict_ref = engine.predict_minutes_quantiles(
        base_minutes=32.0, spread=3.0, is_starter=True, referee_foul_rate=1.40, foul_trouble_prone=True
    )
    assert proj_strict_ref["foul_trouble_hazard"] > proj_lenient_ref["foul_trouble_hazard"]
    assert proj_strict_ref["p10_floor"] < proj_lenient_ref["p10_floor"]

    # 5. Integration with PlayerPropsEngine
    props_engine = PlayerPropsEngine()
    player_proj = props_engine.project_player_stats(
        player_name="Nikola Jokic",
        team="DEN",
        spread_blowout_risk=14.0,
        referee_foul_rate=1.25,
        foul_trouble_prone=True,
    )
    assert "hurdle_minutes" in player_proj
    assert "p10_floor" in player_proj["hurdle_minutes"]
    assert "p50_median" in player_proj["hurdle_minutes"]
    assert "p90_ceiling" in player_proj["hurdle_minutes"]
    assert player_proj["hurdle_minutes"]["blowout_risk"] > 0.40


# 44. V9 Fase 2: Multivariate Vine Copula Engine for 3 to 5-Leg Same Game Parlays (SGP)
def test_44_vine_copula_multivariate_sgp() -> None:
    """
    Test 44 (V9 Phase 2 Verification):
    1. Multi-dimensional Vine Copula Simulator for 3-leg and 4-leg Same Game Parlays (SGP).
    2. Student-t heavy tail dependence vs Gaussian copula.
    3. Positive correlation matrix ensures joint probability exceeds independent product.
    4. Fractional Kelly staking and EV pricing for Peruvian retail books (RETAbet, Betsson).
    5. Integration into PlayerPropsEngine.simulate_multi_leg_sgp_vine_copula.
    """
    from src.prediction.vine_copula import VineCopulaSGP, nearest_positive_definite
    from src.prediction.player_props import PlayerPropsEngine

    copula = VineCopulaSGP()

    # 1. 3-Leg SGP definition
    legs = [
        {"player_name": "Jayson Tatum", "team": "BOS", "category": "PTS", "selection": "OVER", "line": 26.5, "model_prob": 0.58},
        {"player_name": "Jaylen Brown", "team": "BOS", "category": "REB", "selection": "OVER", "line": 6.5, "model_prob": 0.55},
        {"team": "BOS", "category": "GAME_WIN", "selection": "OVER", "line": 0.0, "model_prob": 0.65},
    ]

    res_student = copula.simulate_multivariate_copula(
        legs=legs,
        offered_sgp_odds=5.50,
        copula_family="student_t",
        df=5,
        bankroll_pen=100.0,
        n_simulations=15000,
        random_seed=42,
    )

    assert res_student["num_legs"] == 3
    assert res_student["p_joint"] > res_student["p_independent"]
    assert res_student["correlation_boost_pct"] > 10.0
    assert res_student["ev_pct"] > 0.0
    assert 1.0 <= res_student["kelly_stake_pen"] <= 3.50

    # 2. Gaussian Copula comparison
    res_gauss = copula.simulate_multivariate_copula(
        legs=legs,
        offered_sgp_odds=5.50,
        copula_family="gaussian",
        bankroll_pen=100.0,
        n_simulations=15000,
        random_seed=42,
    )
    assert res_gauss["p_joint"] > 0.0

    # 3. Higham nearest positive definite repair
    invalid_corr = np.array([
        [1.0, 0.95, 0.95],
        [0.95, 1.0, -0.90],
        [0.95, -0.90, 1.0],
    ])
    repaired_corr = nearest_positive_definite(invalid_corr)
    eigvals = np.linalg.eigvalsh(repaired_corr)
    assert np.all(eigvals >= -1e-7)
    assert np.allclose(np.diag(repaired_corr), 1.0)

    # 4. Integration with PlayerPropsEngine
    props_engine = PlayerPropsEngine()
    sgp_res = props_engine.simulate_multi_leg_sgp_vine_copula(
        legs=legs,
        offered_sgp_odds=5.80,
        bankroll_pen=100.0,
    )
    assert sgp_res["num_legs"] == 3
    assert sgp_res["p_joint"] > 0.15
    assert "rationale" in sgp_res
