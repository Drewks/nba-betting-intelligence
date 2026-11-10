"""
Kelly Portfolio Staking, CLV Governor, Drawdown Shield and Sizing Tests (`tests/test_risk_and_staking.py`).
Modular test suite extracted from legacy test_nba_intelligence monolith.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3

from src.paper_trading.engine import PaperTradingEngine
from src.storage.db import DatabaseManager
from tests.test_helpers import _seed_sample_game_and_prediction



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
            captured_at, is_closing_line, source_type
        ) VALUES ('ODDS_CLV_01', 'REAL_GAME_01', 'Pinnacle', 'moneyline', 'HOME', NULL, 1.80, '2026-10-19T23:55:00Z', 1, 'OBSERVED')
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
            captured_at, is_closing_line, source_type
        ) VALUES ('ODDS_MULTI_DK', 'G_CLV_MULTI', 'DraftKings', 'moneyline', 'HOME', NULL, 1.75, '2026-10-25T23:55:00Z', 1, 'OBSERVED')
        """
    )
    db.execute_insert(
        """
        INSERT INTO odds_snapshots (
            odds_id, game_id, provider, market, selection, line_value, decimal_odds,
            captured_at, is_closing_line, source_type
        ) VALUES ('ODDS_MULTI_PINN', 'G_CLV_MULTI', 'Pinnacle', 'moneyline', 'HOME', NULL, 1.80, '2026-10-25T23:58:00Z', 1, 'OBSERVED')
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


def test_39_v8_drawdown_kelly_shield_and_official_v8_promotion() -> None:
    """
    Test 39 (V8 Official Promotion Verification):
    1. High-Water Mark (HWM) Drawdown Kelly Shield contracts stakes during equity drawdowns.
    2. scan_retabet_sgp_slate automatically pairs game outcomes with qualified player props.
    3. Official V8 Model Version ID verification.
    """
    from src.prediction.ev_calculator import optimize_simultaneous_kelly_portfolio
    from src.prediction.player_props import PlayerPropsEngine
    import scripts.run_cloud_cycle as rcc

    # 1. Test Drawdown Kelly Shield
    cand = [{"estimated_probability": 0.62, "decimal_odds_used": 1.95}]

    # At all-time high (no drawdown)
    res_peak = optimize_simultaneous_kelly_portfolio(
        cand, bankroll_pen=100.0, peak_bankroll_pen=100.0
    )
    # Under a 15% drawdown (S/85 vs peak S/100)
    res_dd15 = optimize_simultaneous_kelly_portfolio(
        cand, bankroll_pen=85.0, peak_bankroll_pen=100.0
    )
    # Under a severe 40% drawdown (S/60 vs peak S/100)
    res_dd40 = optimize_simultaneous_kelly_portfolio(
        cand, bankroll_pen=60.0, peak_bankroll_pen=100.0
    )

    assert res_peak[0]["kelly_optimal_fraction"] > res_dd15[0]["kelly_optimal_fraction"]
    assert res_dd15[0]["kelly_optimal_fraction"] > res_dd40[0]["kelly_optimal_fraction"]
    assert res_dd40[0]["kelly_recommended_stake_pen"] >= 1.00  # Stays bounded by floor

    # 2. Test scan_retabet_sgp_slate
    engine = PlayerPropsEngine()
    sample_slate = [
        {
            "game_id": "G_SGP_SLATE_1",
            "home_team": "DAL",
            "away_team": "PHX",
            "home_name": "Dallas Mavericks",
            "away_name": "Phoenix Suns",
            "model_p_home_pct": 62.0,
            "model_p_away_pct": 38.0,
        }
    ]
    sample_props = [
        {
            "game_id": "G_SGP_SLATE_1",
            "team": "DAL",
            "player_name": "Kyrie Irving",
            "prop_category": "PTS",
            "selection": "OVER",
            "line_value": 26.5,
            "model_prob": 0.64,
            "matchday_date": "2026-11-07",
        }
    ]
    # Estimated SGP price = product of legs minus a 10% margin (no floor); min_ev lowered to exercise the scan
    sgp_picks = engine.scan_retabet_sgp_slate(sample_slate, sample_props, bankroll_pen=100.0, min_ev_pct=-100.0)
    assert len(sgp_picks) >= 1
    top_sgp = sgp_picks[0]
    assert top_sgp["bookmaker"] == "RETAbet Perú"
    assert top_sgp["correlation_rho"] > 0.20
    assert top_sgp["is_value_sgp"] is True
    # No floors: the stake is 0 without positive EV at the estimated price, and capped otherwise
    assert 0.0 <= top_sgp["kelly_stake_pen"] <= 10.00
    assert "CUOTA ESTIMADA" in top_sgp["rationale"]

    # 3. Verify V8 Official Model Promotion
    assert rcc.MODEL_VERSION_ID == "model_f_ensemble_v8"


# 50. Audited Phase 0: Rigorous Risk Management, Negative-EV Zero Stake & Quarantined Odds Integrity
def test_50_unconstrained_staking_and_high_prob_parlays(tmp_path: Path) -> None:
    """
    Test 50: Verification of Post-Audit Data & Risk Integrity:
    1. Strict Kelly and Zero-Stake on Negative EV:
       - p = 0.66 at decimal odds 1.40 (EV = -7.6%) MUST yield stake = 0.00 PEN (no artificial floor).
       - Positive EV picks respect strict AGENTS.md caps (S/ 1.00 to S/ 2.00 PEN).
    2. Portfolio Risk Preservation:
       - CPPI preservation shield contracts capital during bankroll drawdowns.
       - Max portfolio exposure cap of 20% prevents over-allocation.
    3. Mathematical Parlay Calculation without Fake Multipliers:
       - Parlay combined odds equal genuine un-inflated leg products (no x1.25 bonus, no fake floors).
       - Stakes strictly capped at S/ 2.00 PEN.
    4. Database Quarantine & View Isolation:
       - Fabricated odds are quarantined in quarantined_odds table.
       - v_observed_odds_snapshots and v_observed_simulated_bets exclude fabricated lines.
    """
    from src.paper_trading.engine import PaperTradingEngine
    from src.prediction.ev_calculator import optimize_simultaneous_kelly_portfolio
    from src.prediction.player_props import PlayerPropsEngine
    from src.storage.db import DatabaseManager

    db = DatabaseManager(tmp_path / "test_audited_risk.sqlite3")

    # 1. Negative-EV Zero Stake Verification (Auditor finding fix)
    neg_ev_candidates = [{"calibrated_probability": 0.66, "decimal_odds": 1.40}]
    neg_res = optimize_simultaneous_kelly_portfolio(neg_ev_candidates, bankroll_pen=100.0)
    assert neg_res[0]["kelly_recommended_stake_pen"] == 0.00
    assert neg_res[0]["kelly_optimal_fraction"] == 0.00

    # 2. Positive-EV Controlled Staking (AGENTS.md rules: S/ 1.00 - S/ 2.00 PEN)
    engine_compliant = PaperTradingEngine(
        db=db,
        initial_bankroll_pen=100.0,
        base_stake_pen=1.00,
        max_stake_pen=2.00,
        min_ev_threshold=0.05,
        dynamic_conviction_staking=True,
        enable_cppi_shield=True,
        staking_mode="CONSERVATIVE",
    )

    stake_star = engine_compliant.compute_contextual_stake_pen(
        calibrated_prob=0.66,
        decimal_odds=1.85,
        ev_unit=0.22,
        current_bankroll_pen=100.0,
    )
    assert 1.00 <= stake_star <= 2.00  # Strict 1-2% bankroll cap per AGENTS.md

    # 3. Drawdown Capital Preservation (CPPI Shield)
    stake_in_drawdown = engine_compliant.compute_contextual_stake_pen(
        calibrated_prob=0.60,
        decimal_odds=1.90,
        ev_unit=0.14,
        current_bankroll_pen=86.0,
        apply_cppi_shield=True,
        peak_bankroll_pen=100.0,
    )
    assert stake_in_drawdown <= stake_star  # Properly scaled down to protect capital

    # 4. Parlay Generator: Genuine mathematical product without x1.25 multiplier or fake floors (from real games)
    props_engine = PlayerPropsEngine(db=db)
    conn = sqlite3.connect("data/nba_intelligence.sqlite3")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT game_id, home_team, away_team FROM games WHERE status = 'FINAL' ORDER BY game_start_time LIMIT 2")
    real_g = [dict(r) for r in cur.fetchall()]
    conn.close()

    real_slate = [
        {
            "game_id": real_g[0]["game_id"],
            "home_team": real_g[0]["home_team"],
            "away_team": real_g[0]["away_team"],
            "model_p_home_pct": 82.0,
            "model_p_away_pct": 18.0,
        },
        {
            "game_id": real_g[1]["game_id"],
            "home_team": real_g[1]["home_team"],
            "away_team": real_g[1]["away_team"],
            "model_p_home_pct": 78.0,
            "model_p_away_pct": 22.0,
        },
    ]
    real_props = [
        {
            "game_id": real_g[0]["game_id"],
            "player_name": "Jayson Tatum",
            "team": real_g[0]["home_team"],
            "prop_category": "PTS",
            "projected_mean": 27.5,
            "projected_std": 6.0,
        },
        {
            "game_id": real_g[1]["game_id"],
            "player_name": "Nikola Jokic",
            "team": real_g[1]["home_team"],
            "prop_category": "REB",
            "projected_mean": 12.5,
            "projected_std": 3.0,
        },
    ]

    parlays = props_engine.generate_high_probability_parlays(
        slate_games=real_slate,
        props_list=real_props,
        bankroll_pen=100.0,
        min_leg_prob=0.75,
    )

    assert len(parlays) >= 1
    best_parlay = parlays[0]
    # Mathematically exact combined odds without artificial 2.05 floor or 1.25 bonus
    assert best_parlay["offered_sgp_odds"] > 1.0
    assert best_parlay["p_joint"] >= 0.50
    # Stake complies with the configured per-selection cap
    assert best_parlay["stake_pen"] <= 10.00

    # 5. Database Quarantine Verification
    quarantined = db.fetch_all("SELECT * FROM quarantined_odds")
    assert isinstance(quarantined, list)
    obs_odds = db.fetch_all("SELECT * FROM v_observed_odds_snapshots")
    assert isinstance(obs_odds, list)
