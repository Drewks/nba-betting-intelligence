"""
Player Props Engine, SGP Copula and Tactical Matchups Tests (`tests/test_props_and_parlays.py`).
Modular test suite extracted from legacy test_nba_intelligence monolith.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest

from src.paper_trading.engine import DoubleSettlementError, PaperTradingEngine
from src.storage.db import DatabaseManager



def test_33_player_props_engine(tmp_path: Path) -> None:
    """
    V7.2 Player Props Engine Verification:
    Tests individual player statistical modeling (PTS, REB, AST, PRA),
    usage and minutes redistribution upon teammate absences, Poisson & Normal distributions,
    conformal Lower-Bound EV, and SQLite persistence.
    """
    from src.prediction.player_props import PlayerPropsEngine

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
    assert 1.00 <= top_pick["kelly_stake_pen"] <= 10.00

    # 4. Verify SQLite persistence in player_prop_picks
    persisted = db.fetch_all("SELECT * FROM player_prop_picks WHERE game_id = 'G_PROP_TEST'")
    assert len(persisted) >= 1
    row = persisted[0]
    assert row["player_name"] == "Kyrie Irving"
    assert row["prop_category"] == "PTS"
    assert row["selection"] == "OVER"
    assert row["line_value"] == 26.5


def test_38_v8_gaussian_copula_sgp_retabet_simulator() -> None:
    """
    Test 38 (V8 Phase 3 Verification):
    1. Bivariate Gaussian Copula modeling joint dependency between game selection and player prop.
    2. Zero-correlation baseline converges to independent product (p_joint ~ p_game * p_prop).
    3. Positive correlation (rho = +0.32) produces significant probability boost over independent pricing.
    4. EV calculation and fractional Kelly stake allocation for RETAbet Perú 'Crea tu Apuesta'.
    """
    from src.prediction.player_props import PlayerPropsEngine

    engine = PlayerPropsEngine()

    # 1. Independent case (rho = 0.0): p_joint should match independent product closely
    p_game = 0.60
    p_prop = 0.55
    res_indep = engine.simulate_same_game_parlay_copula(
        game_id="G_SGP_INDEP",
        matchday_date="2026-11-07",
        game_selection_label="Dallas Mavericks Gana",
        game_model_prob=p_game,
        player_name="Kyrie Irving",
        team="DAL",
        prop_category="PTS",
        prop_selection="OVER",
        prop_line=26.5,
        prop_model_prob=p_prop,
        offered_sgp_odds=3.00,
        correlation_rho=0.0,
        n_simulations=15000,
        random_seed=42,
    )
    expected_indep = p_game * p_prop
    assert res_indep["p_joint"] == pytest.approx(expected_indep, abs=0.015)
    assert abs(res_indep["correlation_boost_pct"]) < 5.0

    # 2. Correlated case (rho = +0.35): p_joint must significantly exceed independent product
    res_corr = engine.simulate_same_game_parlay_copula(
        game_id="G_SGP_CORR",
        matchday_date="2026-11-07",
        game_selection_label="Dallas Mavericks Gana",
        game_model_prob=p_game,
        player_name="Kyrie Irving",
        team="DAL",
        prop_category="PTS",
        prop_selection="OVER",
        prop_line=26.5,
        prop_model_prob=p_prop,
        offered_sgp_odds=3.30,
        correlation_rho=0.35,
        n_simulations=15000,
        random_seed=42,
    )
    assert res_corr["p_joint"] > expected_indep + 0.04
    assert res_corr["correlation_boost_pct"] > 12.0
    assert res_corr["fair_sgp_odds"] < (1.0 / expected_indep)
    assert res_corr["ev_pct"] > 10.0
    assert res_corr["is_value_sgp"] is True
    assert 1.00 <= res_corr["kelly_stake_pen"] <= 10.00
    assert "RETAbet Perú" in res_corr["bookmaker"]


def test_40_v8_expanded_player_props_and_tactical_matchup_engine(tmp_path: Path) -> None:
    """
    Test 40 (V8 Upgraded Player Props and Tactical Matchup Verification):
    1. Canonical coverage: > 100 players mapped across all 30 NBA teams.
    2. Defense vs Position (DvP): Opponent defensive rating splits modulate projections.
    3. Game Pace and Blowout Dampening: High pace accelerates scoring, heavy spreads dampen star minutes.
    4. Combo markets: Supports PR, PA, RA, and PRA.
    5. Automated Slate Generator: Produces qualified individual props and RETAbet SGPs.
    """
    from src.prediction.player_props import (
        PLAYER_PROP_BASELINES,
        TEAM_DEFENSIVE_MULTIPLIERS,
        PlayerPropsEngine,
    )

    # 1. Canonical coverage test
    assert len(PLAYER_PROP_BASELINES) >= 100
    assert len(TEAM_DEFENSIVE_MULTIPLIERS) == 30

    engine = PlayerPropsEngine(min_ev_threshold=0.03)

    # 2. Matchup defense impact test: Tatum vs WAS (TARGET) vs Tatum vs MIN (ELITE)
    proj_tatum_vs_was = engine.project_player_stats("Jayson Tatum", "BOS", opponent_team="WAS")
    proj_tatum_vs_min = engine.project_player_stats("Jayson Tatum", "BOS", opponent_team="MIN")

    assert proj_tatum_vs_was["projections"]["PTS"]["mean"] > proj_tatum_vs_min["projections"]["PTS"]["mean"]
    assert proj_tatum_vs_was["matchup_tier"] == "TARGET"
    assert proj_tatum_vs_min["matchup_tier"] == "ELITE"

    # 3. Pace factor impact test
    proj_fast_pace = engine.project_player_stats("Stephen Curry", "GSW", expected_game_pace=104.0)
    proj_slow_pace = engine.project_player_stats("Stephen Curry", "GSW", expected_game_pace=96.0)
    assert proj_fast_pace["projections"]["PTS"]["mean"] > proj_slow_pace["projections"]["PTS"]["mean"]

    # 4. Blowout spread dampening test
    proj_tight = engine.project_player_stats("Luka Doncic", "DAL", spread_blowout_risk=2.5)
    proj_blowout = engine.project_player_stats("Luka Doncic", "DAL", spread_blowout_risk=14.5)
    assert proj_tight["effective_minutes"] > proj_blowout["effective_minutes"]
    assert proj_blowout["blowout_min_discount"] > 0.0

    # 5. Combo markets test
    proj_combos = engine.project_player_stats("Nikola Jokic", "DEN")
    for combo in ["PRA", "PR", "PA", "RA"]:
        assert combo in proj_combos["projections"]
        assert proj_combos["projections"][combo]["mean"] > 0.0
        assert proj_combos["projections"][combo]["std"] > 0.0

    # 6. Automated Slate Generator test
    DatabaseManager(tmp_path / "test_slate.sqlite3")
    sample_slate = [
        {
            "game_id": "G_TEST_SLATE_1",
            "home_team": "IND",
            "away_team": "WAS",
            "matchday_date": "2026-11-08",
            "expected_margin": 4.5,
            "stats": {"expected_pace": 103.0},
            "model_p_home_pct": 65.0,
            "model_p_away_pct": 35.0,
        }
    ]
    # With props and parlays disabled explicitly, nothing is generated (no observed prop lines exist)
    assert engine.generate_slate_prop_opportunities(
        slate_games=sample_slate, bankroll_pen=100.0, min_ev_pct=3.0, allow_synthetic_lines=False, allow_parlays=False
    ) == []

    # Estimated lines: every pick is labelled as estimated, never presented as an observed price
    gen_results = engine.generate_slate_prop_opportunities(
        slate_games=sample_slate,
        bankroll_pen=100.0,
        min_ev_pct=3.0,
        allow_synthetic_lines=True,
        allow_parlays=False,
    )
    assert len(gen_results) >= 1
    types = {r.get("type") for r in gen_results}
    assert "INDIVIDUAL_PROP" in types
    assert "RETABET_SGP" not in types
    assert all(r["line_source"] == "ESTIMATED" and "LÍNEA ESTIMADA" in r["rationale"] for r in gen_results)
    assert all(0.0 <= r["kelly_stake_pen"] <= 10.0 for r in gen_results)


def test_41_player_props_paper_trading_and_settlement(tmp_path: Path) -> None:
    """
    Test 41: Dedicated Paper Trading for Player Props & RETAbet SGP:
    1. Bet placement & persistence in SQLite `player_prop_picks`.
    2. Accurate settlement of OVER, UNDER, and PUSH individual props.
    3. Accurate settlement of Same-Game Parlays (SGP) with joint copula probability.
    4. Anti-tampering immutability triggers (prevent update/delete on settled props).
    5. Double-settlement prevention.
    6. Performance metrics: Win Rate %, Net Profit PEN, ROI %, Brier Score calibration.
    7. Automated batch settlement with game boxscores.
    """
    import pytest
    from src.storage.db import DatabaseManager

    db = DatabaseManager(tmp_path / "props_pt_test.sqlite3")
    engine = PaperTradingEngine(db=db, initial_bankroll_pen=100.0)

    # Insert a test game
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, home_score, away_score, features_available_at, source_provider, ingested_at
        ) VALUES ('G_TEST_PROPS_1', '2026', '2026-11-08', '2026-11-08T20:00:00Z', 'LAL', 'DEN',
                  'FINAL', 112, 108, '2026-11-08T19:00:00Z', 'ESPN', '2026-11-08T19:00:00Z')
        """
    )

    # 1. Register Props:
    # Prop 1: LeBron James PTS OVER 25.5 @ 1.90, stake S/ 2.00
    prop1_id = engine.record_player_prop_pick({
        "prop_id": "PROP_LEBRON_PTS",
        "game_id": "G_TEST_PROPS_1",
        "matchday_date": "2026-11-08",
        "player_name": "LeBron James",
        "team": "LAL",
        "prop_category": "PTS",
        "line_value": 25.5,
        "selection": "OVER",
        "decimal_odds": 1.90,
        "projected_mean": 27.5,
        "projected_std": 6.0,
        "model_prob": 0.62,
        "conformal_p_low": 0.52,
        "conformal_p_high": 0.75,
        "ev_pct": 17.8,
        "stake_pen": 2.00,
        "kelly_stake_pen": 2.00,
    })

    # Prop 2: Nikola Jokic AST UNDER 9.5 @ 1.85, stake S/ 2.00
    prop2_id = engine.record_player_prop_pick({
        "prop_id": "PROP_JOKIC_AST",
        "game_id": "G_TEST_PROPS_1",
        "matchday_date": "2026-11-08",
        "player_name": "Nikola Jokic",
        "team": "DEN",
        "prop_category": "AST",
        "line_value": 9.5,
        "selection": "UNDER",
        "decimal_odds": 1.85,
        "projected_mean": 8.5,
        "projected_std": 3.0,
        "model_prob": 0.60,
        "conformal_p_low": 0.50,
        "conformal_p_high": 0.72,
        "ev_pct": 11.0,
        "stake_pen": 2.00,
        "kelly_stake_pen": 2.00,
    })

    # Prop 3: Anthony Davis REB OVER 12.0 @ 1.90 (PUSH scenario), stake S/ 1.00
    prop3_id = engine.record_player_prop_pick({
        "prop_id": "PROP_AD_REB",
        "game_id": "G_TEST_PROPS_1",
        "matchday_date": "2026-11-08",
        "player_name": "Anthony Davis",
        "team": "LAL",
        "prop_category": "REB",
        "line_value": 12.0,
        "selection": "OVER",
        "decimal_odds": 1.90,
        "projected_mean": 13.0,
        "projected_std": 3.5,
        "model_prob": 0.58,
        "conformal_p_low": 0.48,
        "conformal_p_high": 0.68,
        "ev_pct": 10.2,
        "stake_pen": 1.00,
        "kelly_stake_pen": 1.00,
    })

    # Prop 4: SGP Parlay: prohibited by AGENTS.md -> rejected by default
    sgp_payload = {
        "prop_id": "SGP_LAL_LEBRON_DEFAULT",
        "game_id": "G_TEST_PROPS_1",
        "matchday_date": "2026-11-08",
        "player_name": "LeBron James + LAL Gana",
        "team": "LAL",
        "prop_category": "SGP",
        "line_value": 25.5,
        "selection": "SGP",
        "decimal_odds": 3.50,
        "model_prob": 0.38,
        "stake_pen": 2.00,
    }
    from src.paper_trading.engine import RiskLimitError
    with pytest.raises(RiskLimitError):
        engine.record_player_prop_pick(sgp_payload, allow_parlay=False)

    # Research-only explicit opt-in still exercises the SGP settlement math
    sgp_id = engine.record_player_prop_pick(allow_parlay=True, prop_dict={
        "prop_id": "SGP_LAL_LEBRON",
        "game_id": "G_TEST_PROPS_1",
        "matchday_date": "2026-11-08",
        "player_name": "LeBron James + LAL Gana",
        "team": "LAL",
        "prop_category": "SGP",
        "line_value": 25.5,
        "selection": "SGP",
        "decimal_odds": 3.50,
        "projected_mean": 0.0,
        "projected_std": 0.0,
        "model_prob": 0.38,
        "conformal_p_low": 0.30,
        "conformal_p_high": 0.46,
        "ev_pct": 33.0,
        "stake_pen": 2.00,
        "kelly_stake_pen": 2.00,
    })

    # Verify initial metrics (all pending)
    init_metrics = engine.get_player_props_performance_metrics()
    assert init_metrics["total_picks"] == 4
    assert init_metrics["pending_picks"] == 4
    assert init_metrics["settled_picks"] == 0
    assert init_metrics["current_props_bankroll_pen"] == 100.00

    # 2. Settle Props:
    settle_time = "2026-11-08T23:00:00Z"

    # Prop 1: LeBron actual PTS = 28.0 > 25.5 -> WON! Net profit = 2.00 * (1.90 - 1) = +1.80
    res1 = engine.settle_player_prop(prop1_id, actual_stat=28.0, game_status="FINAL", settled_at=settle_time)
    assert res1["status"] == "WON"
    assert round(res1["net_profit_pen"], 2) == 1.80
    assert round(res1["bankroll_after_pen"], 2) == 101.80

    # Prop 2: Jokic actual AST = 11.0 > 9.5 -> UNDER LOST! Net profit = -2.00
    res2 = engine.settle_player_prop(prop2_id, actual_stat=11.0, game_status="FINAL", settled_at=settle_time)
    assert res2["status"] == "LOST"
    assert round(res2["net_profit_pen"], 2) == -2.00
    assert round(res2["bankroll_after_pen"], 2) == 99.80

    # Prop 3: Davis actual REB = 12.0 == 12.0 -> PUSH! Net profit = 0.00
    res3 = engine.settle_player_prop(prop3_id, actual_stat=12.0, game_status="FINAL", settled_at=settle_time)
    assert res3["status"] == "PUSH"
    assert round(res3["net_profit_pen"], 2) == 0.00
    assert round(res3["bankroll_after_pen"], 2) == 99.80

    # Prop 4: SGP Hit: actual_stat = 1.0 -> WON! Net profit = 2.00 * (3.50 - 1) = +5.00
    res4 = engine.settle_player_prop(sgp_id, actual_stat=1.0, game_status="FINAL", settled_at=settle_time)
    assert res4["status"] == "WON"
    assert round(res4["net_profit_pen"], 2) == 5.00
    assert round(res4["bankroll_after_pen"], 2) == 104.80

    # 3. Test Double Settlement Prevention
    with pytest.raises(DoubleSettlementError):
        engine.settle_player_prop(prop1_id, actual_stat=28.0, game_status="FINAL", settled_at=settle_time)

    # 4. Test Anti-Tampering SQLite Immutability Triggers
    with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_VIOLATION"):
        with db.connect() as conn:
            conn.execute("UPDATE player_prop_picks SET line_value = 99.0 WHERE prop_id = ?", (prop1_id,))

    with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_VIOLATION"):
        with db.connect() as conn:
            conn.execute("DELETE FROM player_prop_picks WHERE prop_id = ?", (prop1_id,))

    # 5. Test Performance Metrics post-settlement
    final_metrics = engine.get_player_props_performance_metrics()
    assert final_metrics["total_picks"] == 4
    assert final_metrics["pending_picks"] == 0
    assert final_metrics["settled_picks"] == 4
    assert final_metrics["won_picks"] == 2
    assert final_metrics["lost_picks"] == 1
    assert final_metrics["push_picks"] == 1
    assert 66.0 <= final_metrics["win_rate_pct"] <= 67.0
    assert final_metrics["total_staked_pen"] == 6.00
    assert round(final_metrics["total_net_profit_pen"], 2) == 4.80
    assert round(final_metrics["current_props_bankroll_pen"], 2) == 104.80
    assert final_metrics["roi_pct"] == 80.0
    assert final_metrics["brier_score"] > 0.0
    assert len(final_metrics["recent_settled"]) == 4

    # 6. Test Automated Batch Boxscore Settlement
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, home_score, away_score, features_available_at, source_provider, ingested_at
        ) VALUES ('G_TEST_PROPS_2', '2026', '2026-11-08', '2026-11-08T21:00:00Z', 'GSW', 'BOS',
                  'FINAL', 105, 102, '2026-11-08T20:00:00Z', 'ESPN', '2026-11-08T20:00:00Z')
        """
    )
    engine.record_player_prop_pick({
        "prop_id": "PROP_CURRY_3PM",
        "game_id": "G_TEST_PROPS_2",
        "matchday_date": "2026-11-08",
        "player_name": "Stephen Curry",
        "team": "GSW",
        "prop_category": "3PM",
        "line_value": 4.5,
        "selection": "OVER",
        "decimal_odds": 1.95,
        "model_prob": 0.55,
        "stake_pen": 1.00,
    })
    batch_boxscores = {
        "G_TEST_PROPS_2": {
            "Stephen Curry": {"PTS": 32.0, "3PM": 6.0, "AST": 7.0, "REB": 5.0}
        }
    }
    batch_res = engine.settle_pending_player_props(game_boxscores=batch_boxscores, settled_at="2026-11-08T23:59:00Z")
    assert len(batch_res) == 1
    assert batch_res[0]["status"] == "WON"
    assert batch_res[0]["actual_stat"] == 6.0
