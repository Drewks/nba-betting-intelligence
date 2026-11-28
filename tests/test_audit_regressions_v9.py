"""
Regression test suite verifying remediation of all 18 audit findings (F-001..F-018 / T-001..T-020).
Every test runs hermetically without external network calls or mutations to `data/nba_intelligence.sqlite3`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Any

import numpy as np
import pytest
import yaml

from src.agents.specialized_agents import NBAAuditorAgent
from src.backtesting.backtester import WalkForwardBacktester
from src.calibration.calibrator import VennAbersConformalInterval
from src.config import load_config
from src.ingestion.playwright_scraper import PeruPlaywrightScraper
from src.models.deep_monte_carlo import DeepMonteCarloHybridModel
from src.models.ensemble import EnsembleStackingModel
from src.models.gbm_model import AdvancedGBMModel
from src.models.point_margin import PointMarginModel
from src.models.total_points import TotalPointsModel
from src.paper_trading.engine import (
    PaperTradingEngine,
    RiskLimitError,
    compute_props_calibration_summary,
)
from src.paper_trading.parlay_engine import ParlayRiskLimitError, ParlayTradingEngine
from src.paper_trading.settlement import calculate_settlement_outcome
from src.prediction.ev_calculator import calculate_ev
from src.prediction.multivariate_copula import MultivariateStudentTCopula
from src.prediction.player_props import PlayerPropsEngine
from src.storage.db import DatabaseManager
from src.validation.validator import DataValidationError, TemporalLeakageError, validate_odds_record

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_TEAMS_ROTATION: tuple[str, ...] = ("BOS", "NYK", "DEN", "OKC", "DAL", "MIN", "LAL", "GSW")


def _build_chronological_games(n_games: int = 80) -> list[dict[str, Any]]:
    """Constructs a deterministic chronological FINAL game stream for model fitting tests."""
    games: list[dict[str, Any]] = []
    start_base = datetime(2025, 11, 1, 20, 0, tzinfo=timezone.utc)
    rng = np.random.default_rng(12345)
    for idx in range(n_games):
        tipoff = start_base + timedelta(hours=12 * idx)
        avail = tipoff - timedelta(hours=2)
        home_t = _TEAMS_ROTATION[idx % len(_TEAMS_ROTATION)]
        away_t = _TEAMS_ROTATION[(idx + 3) % len(_TEAMS_ROTATION)]
        home_off = 114.0 + float(rng.normal(0.0, 4.0))
        home_def = 111.0 + float(rng.normal(0.0, 3.5))
        away_off = 113.0 + float(rng.normal(0.0, 4.0))
        away_def = 112.0 + float(rng.normal(0.0, 3.5))
        pace = 99.0 + float(rng.normal(0.0, 2.5))
        expected_margin = 2.0 + 0.45 * ((home_off - home_def) - (away_off - away_def))
        expected_total = 224.0 + 0.55 * (pace - 99.0) * 2.0
        actual_margin = int(round(expected_margin + float(rng.normal(0.0, 12.5))))
        actual_total = int(max(185, round(expected_total + float(rng.normal(0.0, 17.0)))))
        home_score = max(80, (actual_total + actual_margin) // 2)
        away_score = max(80, actual_total - home_score)
        if home_score == away_score:
            home_score += 2
        games.append(
            {
                "game_id": f"G_HIST_{idx:03d}",
                "season": "2025-26",
                "matchday_date": tipoff.strftime("%Y-%m-%d"),
                "game_start_time": tipoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "features_available_at": avail.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "home_team": home_t,
                "away_team": away_t,
                "status": "FINAL",
                "home_score": home_score,
                "away_score": away_score,
                "home_off_rtg": round(home_off, 2),
                "home_def_rtg": round(home_def, 2),
                "away_off_rtg": round(away_off, 2),
                "away_def_rtg": round(away_def, 2),
                "home_pace": round(pace, 2),
                "away_pace": round(pace + float(rng.normal(0.0, 1.0)), 2),
                "home_rest_days": 2,
                "away_rest_days": 1 if idx % 3 == 0 else 2,
                "source_provider": "test_chronological",
                "ingested_at": avail.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    return games


def test_t001_oof_sigma_never_uses_insample_residuals() -> None:
    """T-001 (F-001): Ridge and GBM sigma must derive strictly from expanding temporal OOF residuals."""
    games = _build_chronological_games(90)
    cutoff = "2026-02-01T00:00:00Z"

    ridge_m = PointMarginModel()
    ridge_m.fit(games, cutoff)
    assert ridge_m.is_fitted is True
    assert ridge_m.sigma_metadata["uses_insample_for_sigma"] is False
    assert ridge_m.sigma_metadata["method"] == "temporal_expanding_oof"
    assert ridge_m.sigma_metadata["oof_sample_size"] >= 10
    assert ridge_m.sigma_metadata["n_folds"] >= 1
    assert ridge_m.sigma_metadata["oof_residual_std_raw"] is not None

    ridge_t = TotalPointsModel()
    ridge_t.fit(games, cutoff)
    assert ridge_t.is_fitted is True
    assert ridge_t.sigma_metadata["uses_insample_for_sigma"] is False
    assert ridge_t.sigma_metadata["method"] == "temporal_expanding_oof"
    assert ridge_t.sigma_metadata["oof_sample_size"] >= 10

    gbm = AdvancedGBMModel()
    gbm.fit(games, cutoff)
    assert gbm.is_fitted is True
    for branch in ("margin", "total"):
        meta = gbm.sigma_metadata[branch]
        assert meta["uses_insample_for_sigma"] is False
        assert meta["method"] == "temporal_expanding_oof"
        assert meta["oof_sample_size"] >= 10


def test_t002_mc_quantiles_labeled_simulation_not_conformal() -> None:
    """T-002 (F-002): Monte Carlo Q10/Q90 intervals must be labeled simulation_q* with is_conformal=0.0."""
    games = _build_chronological_games(70)
    target = {
        **games[-1],
        "game_id": "G_TARGET_MC",
        "matchday_date": "2026-02-10",
        "game_start_time": "2026-02-11T00:00:00Z",
        "features_available_at": "2026-02-10T22:00:00Z",
        "status": "SCHEDULED",
        "home_score": None,
        "away_score": None,
    }
    hist = games[:-1]

    mc = DeepMonteCarloHybridModel(n_simulations=3000)
    mc.fit(hist, target["features_available_at"])
    mc_out = mc.simulate_matchup(target, hist, line_value=224.5)
    assert "simulation_q10_total" in mc_out
    assert "simulation_q90_total" in mc_out
    assert "simulation_q10_margin" in mc_out
    assert "simulation_q90_margin" in mc_out
    assert mc_out["is_conformal"] == 0.0
    assert not any(k.startswith("conformal_q") for k in mc_out)

    ens = EnsembleStackingModel()
    ens.fit(hist, target["features_available_at"])
    ml_out = ens.predict_moneyline(target, hist)
    tot_out = ens.predict_total_points(target, hist, line_value=224.5)
    assert "simulation_q10_margin" in ml_out
    assert "simulation_q90_margin" in ml_out
    assert "simulation_q10_total" in tot_out
    assert "simulation_q90_total" in tot_out
    assert not any(k.startswith("conformal_q") for k in ml_out)
    assert not any(k.startswith("conformal_q") for k in tot_out)


def test_t003_double_plus_overtime_iterative_resolution() -> None:
    """T-003 (F-003): DeepMonteCarloHybridModel iterates overtime until winner (2+ OT possible, unbiased)."""
    games = _build_chronological_games(60)
    even_game = {
        "game_id": "G_EVEN_OT_TEST",
        "season": "2025-26",
        "matchday_date": "2026-02-15",
        "game_start_time": "2026-02-16T00:00:00Z",
        "features_available_at": "2026-02-15T22:00:00Z",
        "home_team": "BOS",
        "away_team": "DEN",
        "status": "SCHEDULED",
        "home_off_rtg": 114.0,
        "home_def_rtg": 114.0,
        "away_off_rtg": 114.0,
        "away_def_rtg": 114.0,
        "home_pace": 99.0,
        "away_pace": 99.0,
        "home_rest_days": 2,
        "away_rest_days": 2,
    }
    mc = DeepMonteCarloHybridModel(n_simulations=20000)
    mc.fit(games, even_game["features_available_at"])
    out = mc.simulate_matchup(even_game, games, line_value=225.0)
    assert out["overtime_prob"] > 0.02
    assert out["multi_overtime_prob"] > 0.0
    assert out["max_ot_periods_simulated"] >= 2.0
    assert out["expected_ot_periods_given_ot"] > 1.0
    assert 0.40 <= out["p_home_mc"] <= 0.62


def test_t004_integer_line_push_probabilities_sum_to_one() -> None:
    """T-004 (F-004): Integer prop and game lines preserve positive push probability and exact sum=1."""
    engine = PlayerPropsEngine()
    p_over_p, p_under_p, p_push_p = engine.compute_exceedance_probabilities("PTS", 24.0, 24.0, 5.5, "poisson")
    assert p_push_p > 0.0
    assert p_over_p > 0.0 and p_under_p > 0.0
    assert p_over_p + p_under_p + p_push_p == pytest.approx(1.0, abs=1e-5)

    p_over_n, p_under_n, p_push_n = engine.compute_exceedance_probabilities("PTS", 24.0, 24.0, 5.5, "normal")
    assert p_push_n > 0.0
    assert p_over_n + p_under_n + p_push_n == pytest.approx(1.0, abs=1e-5)

    games = _build_chronological_games(60)
    mc = DeepMonteCarloHybridModel(n_simulations=5000)
    mc.fit(games[:-1], games[-1]["features_available_at"])
    mc_out = mc.simulate_matchup({**games[-1], "status": "SCHEDULED"}, games[:-1], line_value=224.0)
    assert mc_out["p_push_mc"] > 0.0
    assert mc_out["p_over_mc"] + mc_out["p_under_mc"] + mc_out["p_push_mc"] == pytest.approx(1.0, abs=1e-5)


def test_t005_ev_with_push_refunds_stake() -> None:
    """T-005 (F-004): EV formula refunds push stake (`EV = p_win * (O - 1) - p_loss`) cleanly."""
    res = calculate_ev(0.50, 1.90, p_push=0.10, p_loss=0.40)
    # Without push refund naive 0.50*1.90 - 1.0 = -0.05; with push refund 0.50*0.90 - 0.40 = +0.05
    assert res["ev_unit"] == pytest.approx(0.05, abs=1e-5)
    assert res["ev_pct"] == pytest.approx(5.0, abs=1e-3)
    assert res["p_push"] == pytest.approx(0.10, abs=1e-6)

    with pytest.raises(DataValidationError):
        calculate_ev(0.60, 1.90, p_push=0.20, p_loss=0.30)


def test_t006_sgp_zero_hits_never_clamped_and_rejected() -> None:
    """T-006 (F-005): Zero joint simulation hits must yield p_joint=0.0 and INSUFFICIENT_SIMULATION_PRECISION."""
    engine = PlayerPropsEngine()
    res_bi = engine.simulate_same_game_parlay_copula(
        game_id="G_SGP_ZERO",
        matchday_date="2026-11-10",
        game_selection_label="DAL Gana",
        game_model_prob=0.0005,
        player_name="Kyrie Irving",
        team="DAL",
        prop_category="PTS",
        prop_selection="OVER",
        prop_line=35.5,
        prop_model_prob=0.0005,
        offered_sgp_odds=25.0,
        correlation_rho=-0.8,
        n_simulations=100,
        random_seed=42,
    )
    assert res_bi["p_joint"] == 0.0
    assert res_bi["is_value_sgp"] is False
    assert res_bi["kelly_stake_pen"] == 0.0
    assert res_bi["decision"] == "NO_BET"
    assert res_bi["decision_reason"] == "INSUFFICIENT_SIMULATION_PRECISION"

    cop = MultivariateStudentTCopula()
    res_multi = cop.simulate_multivariate_copula(
        legs=[
            {"label": "LEG_A", "player_name": "P1", "prop_category": "PTS", "model_prob": 0.0005},
            {"label": "LEG_B", "player_name": "P2", "prop_category": "REB", "model_prob": 0.0005},
        ],
        offered_sgp_odds=40.0,
        n_simulations=100,
        random_seed=42,
    )
    assert res_multi["p_joint"] == 0.0
    assert res_multi["hits"] == 0
    assert res_multi["sufficient_precision"] is False
    assert res_multi["decision"] == "NO_BET"
    assert res_multi["decision_reason"] == "INSUFFICIENT_SIMULATION_PRECISION"


def test_t007_props_calibrator_fitted_sets_valid_cutoff_and_enables_staking() -> None:
    """T-007 (F-006): Props calibrator with sufficient prior OOS data fits with valid cutoff_utc."""
    engine = PlayerPropsEngine(min_ev_threshold=0.01, global_min_samples=60)
    rng = np.random.default_rng(77)
    records = []
    for i in range(250):
        p_i = float(rng.uniform(0.30, 0.85))
        records.append(
            {
                "game_start_time": f"2026-10-{1 + (i % 25):02d}T18:00:00Z",
                "raw_probability": p_i,
                "outcome": int(rng.random() < p_i),
            }
        )
    assert engine.calibrator.fit(records, "2026-11-01T00:00:00Z") is True
    assert engine.calibrator.is_fitted is True
    assert engine.calibrator.cutoff_time_str == "2026-11-01T00:00:00Z"

    interval = engine.calibrator.predict_interval(0.70)
    assert interval["is_fitted"] is True
    assert interval["is_conformal"] is True
    assert interval["cutoff_utc"] == "2026-11-01T00:00:00Z"
    assert 0.0 < interval["p0"] <= interval["p_va"] <= interval["p1"] < 1.0

    picks = engine.evaluate_prop_opportunity(
        player_name="Kyrie Irving",
        team="DAL",
        game_id="G_PROP_CAL_OK",
        matchday_date="2026-11-06",
        prop_category="PTS",
        line_value=24.5,
        over_odds=1.95,
        under_odds=1.85,
        absent_teammates=["Luka Doncic"],
        bankroll_pen=100.0,
        as_of_utc="2026-11-06T20:00:00Z",
        persist=False,
    )
    assert picks
    top = picks[0]
    assert top["calibration_is_conformal"] is True
    assert top["lower_bound_ev_blocked"] is False


def test_t008_unfitted_props_calibrator_blocks_live_kelly_staking() -> None:
    """T-008 (F-006): Unfitted or under-sampled calibrator marks fallback and blocks Kelly staking."""
    va = VennAbersConformalInterval(window=500, min_samples=60)
    too_few = [
        {"game_start_time": "2026-10-10T00:00:00Z", "raw_probability": 0.6, "outcome": i % 2}
        for i in range(15)
    ]
    assert va.fit(too_few, "2026-11-01T00:00:00Z") is False
    fallback = va.predict_interval(0.72)
    assert fallback["is_fitted"] is False
    assert fallback["is_conformal"] is False
    assert fallback["calibration_method"] == "unfitted_heuristic_fallback"

    engine = PlayerPropsEngine(min_ev_threshold=0.00)
    picks = engine.evaluate_prop_opportunity(
        player_name="Kyrie Irving",
        team="DAL",
        game_id="G_PROP_UNFIT",
        matchday_date="2026-11-06",
        prop_category="PTS",
        line_value=24.5,
        over_odds=2.05,
        under_odds=1.80,
        absent_teammates=["Luka Doncic"],
        bankroll_pen=100.0,
        as_of_utc="2026-11-06T20:00:00Z",
        persist=False,
    )
    assert picks
    assert all(p["lower_bound_ev_blocked"] is True for p in picks)
    assert all(p["kelly_stake_pen"] == 0.0 for p in picks)
    assert all(p["decision_reason"] == "UNFITTED_CALIBRATOR_FALLBACK" for p in picks)


def test_t009_default_config_blocks_props_and_parlays_in_all_engines(tmp_path: Path) -> None:
    """T-009 (F-008): With config flags false, no code path inserts player_prop_picks or parlay_bets."""
    cfg = load_config()
    assert cfg.risk.allow_player_props_betting is False
    assert cfg.risk.allow_parlays is False

    db = DatabaseManager(tmp_path / "gate_default.sqlite3")
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, features_available_at, source_provider, ingested_at
        ) VALUES ('G_BLOCK', '2026-27', '2026-11-10', '2026-11-11T00:00:00Z', 'DAL', 'BOS',
                  'SCHEDULED', '2026-11-10T20:00:00Z', 'espn', '2026-11-10T20:00:00Z')
        """
    )

    pt = PaperTradingEngine(db=db, initial_bankroll_pen=100.0)
    with pytest.raises(RiskLimitError, match="allow_player_props_betting"):
        pt.record_player_prop_pick(
            {
                "prop_id": "PROP_BLOCK_1",
                "game_id": "G_BLOCK",
                "matchday_date": "2026-11-10",
                "player_name": "Kyrie Irving",
                "team": "DAL",
                "prop_category": "PTS",
                "line_value": 24.5,
                "selection": "OVER",
                "decimal_odds": 1.95,
                "model_prob": 0.65,
                "stake_pen": 2.0,
            }
        )

    props_eng = PlayerPropsEngine(db=db)
    persisted_prop = props_eng._persist_prop_pick(
        {
            "prop_id": "PROP_BLOCK_2",
            "game_id": "G_BLOCK",
            "matchday_date": "2026-11-10",
            "player_name": "Kyrie Irving",
            "team": "DAL",
            "prop_category": "PTS",
            "line_value": 24.5,
            "selection": "OVER",
            "decimal_odds": 1.95,
            "projected_mean": 27.0,
            "projected_std": 6.0,
            "model_prob": 0.65,
            "conformal_p_low": 0.58,
            "conformal_p_high": 0.72,
            "ev_pct": 15.0,
            "ev_lower_bound_pct": 5.0,
            "kelly_stake_pen": 2.0,
            "usage_bump_pct": 0.0,
            "rationale": "test",
            "emitted_at": "2026-11-10T20:00:00Z",
            "lower_bound_ev_blocked": False,
        },
        bankroll_pen=100.0,
    )
    assert persisted_prop is False

    parlay_eng = ParlayTradingEngine(db=db, initial_bankroll_pen=50.0)
    with pytest.raises(ParlayRiskLimitError, match="DISABLED_BY_CONFIG"):
        parlay_eng.record_parlay_bet(
            {
                "parlay_id": "PARLAY_BLOCK_1",
                "matchday_date": "2026-11-10",
                "legs": [
                    {"game_id": "G_BLOCK", "market": "moneyline", "selection": "HOME", "decimal_odds": 1.8, "prob": 0.6},
                    {"game_id": "G_BLOCK2", "market": "moneyline", "selection": "AWAY", "decimal_odds": 1.9, "prob": 0.58},
                ],
                "combined_odds": 3.42,
                "joint_prob": 0.348,
                "ev_pct": 19.0,
                "stake_pen": 1.5,
            }
        )
    assert (
        parlay_eng.record_candidate_parlays(
            "2026-11-10",
            [{"parlay_id": "CAND_1", "legs": [], "combined_odds": 3.0, "joint_prob": 0.4, "ev_pct": 20.0, "stake_pen": 1.0}],
        )
        == []
    )
    assert db.fetch_one("SELECT COUNT(*) AS n FROM player_prop_picks")["n"] == 0
    assert db.fetch_one("SELECT COUNT(*) AS n FROM parlay_bets")["n"] == 0


def test_t010_props_queries_enforce_cutoff_and_exclude_future_boxscores(tmp_path: Path) -> None:
    """T-010 (F-007): Props baseline/DvP queries require cutoff and ignore post-cutoff boxscores."""
    db = DatabaseManager(tmp_path / "props_temporal.sqlite3")
    with db.connect() as conn:
        for gid, mdate, start_ts, avail_ts in [
            ("G_PAST", "2026-11-05", "2026-11-06T00:00:00Z", "2026-11-05T20:00:00Z"),
            ("G_FUTURE", "2026-11-12", "2026-11-13T00:00:00Z", "2026-11-12T20:00:00Z"),
        ]:
            conn.execute(
                """
                INSERT INTO games (
                    game_id, season, matchday_date, game_start_time, home_team, away_team,
                    status, home_score, away_score, features_available_at, source_provider, ingested_at
                ) VALUES (?, '2026-27', ?, ?, 'DAL', 'WAS', 'FINAL', 110, 105, ?, 'espn', ?)
                """,
                (gid, mdate, start_ts, avail_ts, avail_ts),
            )
        for gid, pts in [("G_PAST", 18.0), ("G_FUTURE", 65.0)]:
            for idx in range(1 if gid == "G_FUTURE" else 8):
                if idx > 0:
                    pre_dt = datetime(2026, 10, 20 + idx, 0, 0, tzinfo=timezone.utc)
                    target_gid = f"G_PRE_{idx}"
                    target_start = pre_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    avail = (pre_dt - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO games (
                            game_id, season, matchday_date, game_start_time, home_team, away_team,
                            status, home_score, away_score, features_available_at, source_provider, ingested_at
                        ) VALUES (?, '2026-27', ?, ?, 'DAL', 'WAS', 'FINAL', 108, 100, ?, 'espn', ?)
                        """,
                        (target_gid, pre_dt.strftime("%Y-%m-%d"), target_start, avail, avail),
                    )
                else:
                    target_gid = gid
                    target_start = "2026-11-06T00:00:00Z" if gid == "G_PAST" else "2026-11-13T00:00:00Z"
                conn.execute(
                    """
                    INSERT INTO player_boxscores (
                        game_id, player_name, player_key, team, game_start_time,
                        minutes, pts, reb, ast, threed, starter
                    ) VALUES (?, 'Kyrie Irving', 'kyrie irving', 'DAL', ?, 34.0, ?, 5.0, 6.0, 2.0, 1)
                    """,
                    (target_gid, target_start, pts),
                )

    engine = PlayerPropsEngine(db=db)
    with pytest.raises(TemporalLeakageError):
        engine.get_player_baseline("Kyrie Irving")
    with pytest.raises(TemporalLeakageError):
        engine.get_team_defensive_multipliers("WAS")
    with pytest.raises(TemporalLeakageError):
        engine.project_player_stats("Kyrie Irving", "DAL")

    mins_b, _usg, ppm_b, _rpm, _apm, _tpm = engine.get_player_baseline(
        "Kyrie Irving", as_of_utc="2026-11-10T00:00:00Z"
    )
    mins_a, _usg_a, ppm_a, _rpm_a, _apm_a, _tpm_a = engine.get_player_baseline(
        "Kyrie Irving", as_of_utc="2026-11-15T00:00:00Z"
    )
    assert ppm_b < ppm_a
    # Compare against a clean DB without the future game to prove exact zero leakage before cutoff
    db_clean = DatabaseManager(tmp_path / "props_temporal_clean.sqlite3")
    with db_clean.connect() as conn_c:
        rows_g = db.fetch_all("SELECT * FROM games WHERE game_id != 'G_FUTURE'")
        for rg in rows_g:
            conn_c.execute(
                """
                INSERT INTO games (
                    game_id, season, matchday_date, game_start_time, home_team, away_team,
                    status, home_score, away_score, features_available_at, source_provider, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rg["game_id"], rg["season"], rg["matchday_date"], rg["game_start_time"],
                    rg["home_team"], rg["away_team"], rg["status"], rg["home_score"], rg["away_score"],
                    rg["features_available_at"], rg["source_provider"], rg["ingested_at"],
                ),
            )
        rows_b = db.fetch_all("SELECT * FROM player_boxscores WHERE game_id != 'G_FUTURE'")
        for rb in rows_b:
            conn_c.execute(
                """
                INSERT INTO player_boxscores (
                    game_id, player_name, player_key, team, game_start_time,
                    minutes, pts, reb, ast, threed, starter
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rb["game_id"], rb["player_name"], rb["player_key"], rb["team"], rb["game_start_time"],
                    rb["minutes"], rb["pts"], rb["reb"], rb["ast"], rb["threed"], rb["starter"],
                ),
            )
    clean_base = PlayerPropsEngine(db=db_clean).get_player_baseline(
        "Kyrie Irving", as_of_utc="2026-11-10T00:00:00Z"
    )
    assert mins_b == pytest.approx(clean_base[0], abs=1e-9)
    assert ppm_b == pytest.approx(clean_base[2], abs=1e-9)


def test_t011_predictions_separate_four_probability_columns(tmp_path: Path) -> None:
    """T-011 (F-009): Schema and persistence separate raw, calibrated, market_fair, and anchored probs."""
    db = DatabaseManager(tmp_path / "preds_sep.sqlite3")
    cols = {r["name"] for r in db.fetch_all("PRAGMA table_info(predictions)")}
    assert {
        "raw_model_probability",
        "calibrated_model_probability",
        "market_fair_probability",
        "market_anchored_probability",
        "run_manifest_id",
    }.issubset(cols)

    db.execute_insert(
        "INSERT INTO games (game_id, season, matchday_date, game_start_time, home_team, away_team, "
        "status, features_available_at, source_provider, ingested_at) "
        "VALUES ('G_P4', '2026-27', '2026-11-10', '2026-11-11T00:00:00Z', 'BOS', 'NYK', "
        "'SCHEDULED', '2026-11-10T20:00:00Z', 'espn', '2026-11-10T20:00:00Z')"
    )
    db.execute_insert(
        "INSERT INTO model_versions (model_version_id, model_family, market, train_start_date, train_end_date, "
        "trained_at, hyperparameters_json, approved_by) VALUES ('model_f_ensemble_v8', 'ensemble', 'moneyline', "
        "'2025-10-01', '2026-11-01', '2026-11-01T00:00:00Z', '{}', 'test')"
    )
    db.execute_insert(
        """
        INSERT INTO predictions (
            prediction_id, game_id, market, selection, model_version_id,
            raw_probability, calibrated_probability,
            raw_model_probability, calibrated_model_probability,
            market_fair_probability, market_anchored_probability,
            uncertainty_std, implied_prob_gross, decimal_odds_used,
            odds_provider, odds_captured_at, ev_unit, ev_pct, emitted_at, features_snapshot_json
        ) VALUES (
            'PRED_4P', 'G_P4', 'moneyline', 'HOME', 'model_f_ensemble_v8',
            0.66, 0.59,
            0.66, 0.62,
            0.55, 0.59,
            0.04, 0.56, 1.85,
            'pinnacle', '2026-11-10T21:00:00Z', 0.0915, 9.15, '2026-11-10T21:05:00Z', '{}'
        )
        """
    )
    row = db.fetch_one("SELECT * FROM predictions WHERE prediction_id = 'PRED_4P'")
    assert row["raw_model_probability"] == pytest.approx(0.66)
    assert row["calibrated_model_probability"] == pytest.approx(0.62)
    assert row["market_fair_probability"] == pytest.approx(0.55)
    assert row["market_anchored_probability"] == pytest.approx(0.59)


def test_t012_backtester_compares_model_vs_market_on_exact_matched_subset(tmp_path: Path) -> None:
    """T-012 (F-009/F-011): Backtester matches subsets strictly and omits Totals without real market lines."""
    db = DatabaseManager(tmp_path / "bt_subset.sqlite3")
    bt = WalkForwardBacktester(db, PaperTradingEngine(db))
    recs = [
        # 2 games with full observed ML + Totals lines
        {
            "game_id": "G1", "season": "2025-26", "matchday_date": "2026-01-01",
            "home_won": 1, "over_hit": 1, "has_observed_tot_line": True,
            "model_a_ml": 0.55, "model_c_ml": 0.62, "model_raw_ml": 0.64, "model_cal_ml": 0.62, "model_anchored_ml": 0.60, "market_ml": 0.58,
            "model_a_tot": 0.50, "model_d_tot": 0.58, "model_raw_tot": 0.60, "model_cal_tot": 0.58, "model_anchored_tot": 0.57, "market_tot": 0.54,
        },
        {
            "game_id": "G2", "season": "2025-26", "matchday_date": "2026-01-02",
            "home_won": 0, "over_hit": 0, "has_observed_tot_line": True,
            "model_a_ml": 0.50, "model_c_ml": 0.41, "model_raw_ml": 0.40, "model_cal_ml": 0.41, "model_anchored_ml": 0.42, "market_ml": 0.45,
            "model_a_tot": 0.50, "model_d_tot": 0.43, "model_raw_tot": 0.42, "model_cal_tot": 0.43, "model_anchored_tot": 0.44, "market_tot": 0.46,
        },
        # 1 game missing real Totals line -> excluded from matched comparison & Totals evaluation
        {
            "game_id": "G3", "season": "2025-26", "matchday_date": "2026-01-03",
            "home_won": 1, "over_hit": 1, "has_observed_tot_line": False,
            "model_a_ml": 0.50, "model_c_ml": 0.70, "model_raw_ml": 0.70, "model_cal_ml": 0.70, "model_anchored_ml": 0.70, "market_ml": 0.60,
            "model_a_tot": 0.50, "model_d_tot": 0.90, "model_raw_tot": 0.90, "model_cal_tot": 0.90, "model_anchored_tot": 0.90, "market_tot": None,
        },
    ]
    summary = bt.compute_comprehensive_metrics(model_comparison_records=recs, closing_rows=[])
    assert summary["model_comparison_sample_size"] == 3
    assert summary["market_comparison_sample_size"] == 2
    mc = summary["model_comparison"]
    assert mc["market_devig_totals"]["sample_size"] == 2
    assert mc["ensemble_calibrated_totals"]["sample_size"] == 2
    assert mc["common_subset_raw_ml"]["sample_size"] == 2
    assert mc["common_subset_calibrated_model_ml"]["sample_size"] == 2
    assert mc["common_subset_market_anchored_ml"]["sample_size"] == 2
    assert mc["common_subset_ensemble_ml"]["brier_score"] == mc["common_subset_calibrated_model_ml"]["brier_score"]
    assert mc["common_subset_ensemble_ml"]["brier_score"] != mc["common_subset_market_anchored_ml"]["brier_score"]


def test_t013_spread_validation_scraping_and_settlement() -> None:
    """T-013 (F-010): Spread market works across validator, scraper quotes, and settlement (WIN/LOSS/PUSH)."""
    valid_spread = {
        "game_id": "G_SP",
        "provider": "Pinnacle",
        "market": "spread",
        "selection": "HOME",
        "line_value": -4.5,
        "decimal_odds": 1.92,
        "counterpart_decimal_odds": 1.92,
        "captured_at": "2026-11-10T18:00:00Z",
    }
    assert validate_odds_record(valid_spread, "2026-11-11T00:00:00Z")["market"] == "spread"

    with pytest.raises(DataValidationError):
        validate_odds_record({**valid_spread, "line_value": None}, "2026-11-11T00:00:00Z")
    with pytest.raises(DataValidationError):
        validate_odds_record({**valid_spread, "line_value": 55.0}, "2026-11-11T00:00:00Z")
    with pytest.raises(DataValidationError):
        validate_odds_record({**valid_spread, "selection": "OVER"}, "2026-11-11T00:00:00Z")

    quotes = PeruPlaywrightScraper._slate_rows_to_quote_dicts(
        [
            {
                "book_name": "RETAbet",
                "home_team": "BOS",
                "away_team": "NYK",
                "captured_at": "2026-11-10T18:00:00Z",
                "home_odds": 1.60,
                "away_odds": 2.40,
                "spread_home_line": -4.5,
                "spread_home_odds": 1.90,
                "spread_away_odds": 1.90,
            }
        ]
    )
    spread_quotes = [q for q in quotes if q["market"] == "spread"]
    assert len(spread_quotes) == 2
    by_sel = {q["selection"]: q for q in spread_quotes}
    assert by_sel["HOME"]["line_value"] == -4.5
    assert by_sel["AWAY"]["line_value"] == 4.5

    st_win, prof_win, _ = calculate_settlement_outcome("spread", "HOME", -4.5, 1.90, 2.0, "FINAL", 112, 105)
    assert st_win == "WON" and prof_win == pytest.approx(1.80)
    st_lost, prof_lost, _ = calculate_settlement_outcome("spread", "HOME", -4.5, 1.90, 2.0, "FINAL", 110, 107)
    assert st_lost == "LOST" and prof_lost == pytest.approx(-2.0)
    st_push, prof_push, _ = calculate_settlement_outcome("spread", "AWAY", 5.0, 1.90, 2.0, "FINAL", 110, 105)
    assert st_push == "PUSH" and prof_push == pytest.approx(0.0)


def test_t014_props_interval_coverage_never_inflated_by_binary_accuracy() -> None:
    """T-014 (F-011): Uncalibrated bounds report None coverage (not accuracy); bad intervals fail validity."""
    uncalibrated_rows = [
        {"status": "WON", "model_prob": 0.72, "conformal_p_low": 0.0, "conformal_p_high": 1.0}
        for _ in range(10)
    ]
    summary_uncal = compute_props_calibration_summary(uncalibrated_rows)
    assert summary_uncal["accuracy_pct"] == 100.0
    assert summary_uncal["venn_abers_calibrated_count"] == 0
    assert summary_uncal["conformal_coverage_pct"] is None
    assert summary_uncal["venn_abers_empirical_coverage_valid"] is None

    miscalibrated_rows = [
        {"status": "WON" if i == 0 else "LOST", "model_prob": 0.82, "conformal_p_low": 0.78, "conformal_p_high": 0.86}
        for i in range(10)
    ]
    summary_bad = compute_props_calibration_summary(miscalibrated_rows)
    assert summary_bad["venn_abers_calibrated_count"] == 10
    assert summary_bad["venn_abers_empirical_coverage_valid"] is False
    assert summary_bad["conformal_coverage_pct"] == 0.0


def test_t015_totals_calibration_uses_observed_lines_and_band_telemetry() -> None:
    """T-015 (F-012): Totals calibration uses observed lines (no hardcoded 228.5) and reports line bands."""
    import scripts.run_cloud_cycle as cycle

    cloud_src = (PROJECT_ROOT / "scripts" / "run_cloud_cycle.py").read_text(encoding="utf-8")
    assert "line_value=228.5" not in cloud_src
    assert "line_val = 228.5" not in cloud_src

    rows = [
        {"line_value": 212.5, "raw_probability": 0.54, "outcome": 1},
        {"line_value": 220.5, "raw_probability": 0.51, "outcome": 0},
        {"line_value": 230.5, "raw_probability": 0.58, "outcome": 1},
        {"line_value": 239.5, "raw_probability": 0.49, "outcome": 0},
    ]
    bands = cycle._compute_totals_line_band_telemetry(rows)
    assert set(bands.keys()) == {"<=215.0", "215.5-225.0", "225.5-235.0", ">235.0"}
    assert all(bands[b]["sample_size"] == 1 for b in bands)
    assert bands["<=215.0"]["mean_raw_prob"] == pytest.approx(0.54)
    assert bands[">235.0"]["empirical_over_rate"] == pytest.approx(0.0)


def test_t016_multivariate_student_t_copula_replaces_vine_copula() -> None:
    """T-016 (F-013): vine_copula.py must not exist; MultivariateStudentTCopula provides Student-t copula."""
    assert not (PROJECT_ROOT / "src" / "prediction" / "vine_copula.py").exists()
    cop = MultivariateStudentTCopula()
    corr_res = cop.simulate_multivariate_copula(
        legs=[
            {"label": "PTS", "player_name": "Luka Doncic", "prop_category": "PTS", "model_prob": 0.55},
            {"label": "AST", "player_name": "Kyrie Irving", "prop_category": "AST", "model_prob": 0.55},
        ],
        offered_sgp_odds=3.40,
        copula_family="student_t",
        df=5,
        n_simulations=10000,
        random_seed=42,
    )
    assert 0.25 <= corr_res["p_joint"] <= 0.50
    assert corr_res["copula_method"] == "multivariate_student_t_copula"
    assert corr_res["copula_family"] == "student_t"


def test_t017_scheduler_reports_exact_executed_and_skipped_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-017 (F-014): Scheduler accurately logs executed vs skipped sources and observed quote deltas."""
    import scripts.run_automated_scheduler as sched_mod

    db_file = tmp_path / "sched.sqlite3"
    state_file = tmp_path / "alert_state.json"
    scheduler = sched_mod.NBADailyScheduler(db_path=db_file, alert_state_path=state_file)

    monkeypatch.setattr(
        sched_mod,
        "run_incremental_cloud_cycle",
        lambda mode="pregame", **_kw: {"mode": mode, "sources_info": {"sportradar_api": {"available": False}}},
    )
    monkeypatch.setattr(scheduler, "run_peru_playwright_odds_harvest", lambda: 0)
    monkeypatch.setattr(scheduler, "bot", type("OfflineBot", (), {"is_live": False})())

    morning = scheduler.execute_morning_cycle()
    assert "espn_public_adapter" in morning["sources_executed"]
    assert "live_peru_odds_scraper" in morning["sources_executed"]
    assert "peru_playwright_scraper" not in morning["sources_executed"]
    assert "peru_playwright_scraper" in morning["sources_skipped"]
    assert "player_props_betting" in morning["sources_skipped"]
    assert "parlays_sub_bankroll" in morning["sources_skipped"]
    assert "telegram_bot" in morning["sources_skipped"]
    assert isinstance(morning["new_quotes_persisted_by_source"], dict)


def test_t018_workflows_least_privilege_and_ci_branch_gate() -> None:
    """T-018 (F-015/F-016): Minimal GITHUB_TOKEN permissions in automation workflow and strict CI PR gates."""
    auto_wf = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "nba_cloud_automation.yml").read_text(encoding="utf-8")
    )
    assert auto_wf["permissions"] == {"contents": "read"}
    jobs = auto_wf["jobs"]
    cycle_perms = jobs["run-nba-intelligence-cycle"]["permissions"]
    assert cycle_perms == {"contents": "write"}
    assert "issues" not in cycle_perms
    pages_perms = jobs["deploy-pages"]["permissions"]
    # actions: read (read-only) lets the job confirm the run lists the Pages artifact before deploying
    # (2026-11-24: deploy-pages failed when the artifact list lagged behind the upload).
    assert pages_perms == {"contents": "read", "pages": "write", "id-token": "write", "actions": "read"}

    auto_raw = (PROJECT_ROOT / ".github" / "workflows" / "nba_cloud_automation.yml").read_text(encoding="utf-8")
    assert "git push origin main" not in auto_raw
    assert "state-live" in auto_raw
    assert "nba-pages-docs" in auto_raw

    ci_wf = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    on_cfg = ci_wf.get("on", ci_wf.get(True, {}))
    assert "main" in on_cfg["pull_request"]["branches"]
    assert "main" in on_cfg["push"]["branches"]
    ci_job = next(iter(ci_wf["jobs"].values()))
    assert ci_job["name"] == "Lint, Type Check & Pytest Suite"
    run_scripts = "\n".join(str(s.get("run", "")) for s in ci_job["steps"])
    assert "ruff check" in run_scripts
    assert "mypy src/" in run_scripts
    assert "pytest" in run_scripts
    assert "data/nba_intelligence.sqlite3" in run_scripts


def test_t019_run_manifest_immutability_and_dynamic_reproducibility(tmp_path: Path) -> None:
    """T-019 (F-017/F-018): run_manifests are append-only, linked from predictions, and repro uses active config."""
    db = DatabaseManager(tmp_path / "manifests.sqlite3")
    db.execute_insert(
        """
        INSERT INTO run_manifests (
            run_id, commit_sha, model_version_id, ensemble_version, submodel_versions_json,
            config_hash, config_version, calibrator_metadata_json, seeds_json, data_cutoff_utc,
            notes, created_at
        ) VALUES (
            'RUN_TEST_001', 'abc1234', 'model_f_ensemble_v8', 'orchestrator_v8', '{}',
            'hash_xyz', '8.0', '{}', '{"mc":42}', '2026-11-10T00:00:00Z',
            'audit test', '2026-11-10T00:00:00Z'
        )
        """
    )
    with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_VIOLATION"):
        with db.connect() as conn:
            conn.execute("UPDATE run_manifests SET commit_sha = 'tampered' WHERE run_id = 'RUN_TEST_001'")
    with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_VIOLATION"):
        with db.connect() as conn:
            conn.execute("DELETE FROM run_manifests WHERE run_id = 'RUN_TEST_001'")

    auditor = NBAAuditorAgent(db=db, paper_engine=PaperTradingEngine(db))
    repro = auditor._verify_reproducibility()
    assert repro["verified"] is True
    agents_src = (PROJECT_ROOT / "src" / "agents" / "specialized_agents.py").read_text(encoding="utf-8")
    assert "model_f_ensemble_v2" not in agents_src


def test_t020_readme_matches_active_model_config() -> None:
    """T-020 (F-018): README operational rules and version identifiers match config/model_config.yaml."""
    load_config.cache_clear()
    cfg = load_config()
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    kelly_pct = f"{cfg.risk.kelly_fraction * 100:.0f}%"
    min_ev_pct = f"{cfg.risk.min_ev_threshold * 100:.1f}%"
    max_stake = f"{cfg.risk.max_stake_pen:.2f}"
    max_picks = str(cfg.risk.max_selections_per_matchday)

    assert kelly_pct in readme
    assert min_ev_pct in readme
    assert max_stake in readme
    assert max_picks in readme
    assert cfg.model.version_id in readme
    assert f"`allow_parlays: {str(cfg.risk.allow_parlays).lower()}`" in readme
    assert f"`allow_player_props_betting: {str(cfg.risk.allow_player_props_betting).lower()}`" in readme
    assert f"trials_evaluated_count: {cfg.evaluation.trials_evaluated_count}" in readme
    assert "50% Kelly" not in readme
    assert "EV <= 5%" not in readme


def test_t021_pre_m012_db_rows_never_conflate_calibrated_with_market_anchored(tmp_path: Path) -> None:
    """T-021 (F-008): Legacy pre-m012 rows with NULL calibrated_model_probability fail closed and never masquerade as market_anchored."""
    db = DatabaseManager(tmp_path / "pre_m012.sqlite3")
    db.execute_insert(
        "INSERT INTO model_versions (model_version_id, model_family, market, train_start_date, train_end_date, trained_at, hyperparameters_json, approved_by) "
        "VALUES ('model_f_ensemble_v8', 'f', 'moneyline', '2026-01-01', '2026-02-01', '2026-02-01T00:00:00Z', '{}', 'test')"
    )
    games_data = [
        ("G_PRE_1", "2026-02-10", "2026-02-11T00:00:00Z", "BOS", "NYK", 112, 102, 2.15, 220.5),
        ("G_PRE_2", "2026-02-11", "2026-02-12T00:00:00Z", "DEN", "DAL", 104, 111, 1.85, 224.5),
    ]
    for idx, (gid, mdate, gtime, ht, at, hs, as_, line_tot_odds, tot_line) in enumerate(games_data):
        db.execute_insert(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
                away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
                features_available_at, source_provider, ingested_at
            ) VALUES (?, '2025-26', ?, ?, ?, ?, 'FINAL', ?, ?, 115.0, 111.0, 99.0, 113.0, 112.0, 98.5, 2, 2, '2026-02-09T12:00:00Z', 'espn', '2026-02-09T12:00:00Z')
            """,
            (gid, mdate, gtime, ht, at, hs, as_),
        )
        db.execute_insert(
            """
            INSERT INTO predictions (
                prediction_id, game_id, market, selection, model_version_id, raw_probability,
                calibrated_probability, uncertainty_std, implied_prob_gross, implied_prob_fair,
                decimal_odds_used, odds_provider, odds_captured_at, ev_unit, ev_pct, emitted_at,
                features_snapshot_json, raw_model_probability, calibrated_model_probability,
                market_fair_probability, market_anchored_probability
            ) VALUES (?, ?, 'moneyline', 'HOME', 'model_f_ensemble_v8', ?, ?, 0.05, 0.52, 0.50, 1.95, 'DraftKings', '2026-02-09T20:00:00Z', 0.02, 2.0, '2026-02-09T20:00:00Z', '{}', ?, NULL, 0.50, ?)
            """,
            (f"PM_{idx}", gid, 0.64 if idx == 0 else 0.40, 0.54 if idx == 0 else 0.45, 0.64 if idx == 0 else 0.40, 0.54 if idx == 0 else 0.45),
        )
        db.execute_insert(
            """
            INSERT INTO predictions (
                prediction_id, game_id, market, selection, line_value, model_version_id, raw_probability,
                calibrated_probability, uncertainty_std, implied_prob_gross, implied_prob_fair,
                decimal_odds_used, odds_provider, odds_captured_at, ev_unit, ev_pct, emitted_at,
                features_snapshot_json, raw_model_probability, calibrated_model_probability,
                market_fair_probability, market_anchored_probability
            ) VALUES (?, ?, 'total_points', 'OVER', ?, 'model_f_ensemble_v8', ?, ?, 0.05, 0.52, 0.50, ?, 'DraftKings', '2026-02-09T20:00:00Z', 0.02, 2.0, '2026-02-09T20:00:00Z', '{}', ?, NULL, 0.50, ?)
            """,
            (f"PT_{idx}", gid, tot_line, 0.58 if idx == 0 else 0.42, 0.52 if idx == 0 else 0.47, line_tot_odds, 0.58 if idx == 0 else 0.42, 0.52 if idx == 0 else 0.47),
        )

    bt = WalkForwardBacktester(db, PaperTradingEngine(db))
    recs = bt._reconstruct_comparison_records_from_db()
    assert len(recs) == 2
    assert all(r["model_c_ml"] is None for r in recs)
    assert all(r["model_d_tot"] is None for r in recs)

    metrics = bt.compute_comprehensive_metrics(model_comparison_records=recs, closing_rows=[])
    mc = metrics["model_comparison"]
    assert "ensemble_calibrated_ml" not in mc
    assert "ensemble_calibrated_totals" not in mc
    assert "common_subset_market_anchored_ml" in mc
    assert metrics["overall_brier_score"] is None
    assert metrics["model_brier_on_market_subset"] is None
    assert metrics["exit_gates_evaluation"]["gates"]["gate_3_calibration_non_inferior_to_baseline"]["passed"] is False
    assert metrics["exit_gates_evaluation"]["gates"]["gate_10_non_inferior_to_devigged_market"]["passed"] is False


def test_t022_calibrate_binary_with_push_preserves_push_budget() -> None:
    """T-022: Conditional push calibration maps into decisive space and scales intervals coherently by (1 - p_push)."""
    from src.calibration.calibrator import ProbabilityCalibrator, calibrate_binary_with_push

    cal = ProbabilityCalibrator(method="logistic", min_samples_logistic=10)
    va = VennAbersConformalInterval(window=200, min_samples=10)
    rng = np.random.default_rng(99)
    hist = [
        {"game_start_time": f"2026-01-{1 + (i % 25):02d}T12:00:00Z", "raw_probability": float(p), "outcome": int(rng.random() < p)}
        for i, p in enumerate(rng.uniform(0.35, 0.70, size=40))
    ]
    cal.fit(hist, "2026-02-01T00:00:00Z")
    va.fit(hist, "2026-02-01T00:00:00Z")

    no_push = calibrate_binary_with_push(0.58, p_push=0.0, calibrator=cal, va_calibrator=va)
    assert no_push["cal_prob"] == pytest.approx(cal.transform_single(0.58), abs=1e-9)

    p_push = 0.08
    with_push = calibrate_binary_with_push(0.54, p_push=p_push, calibrator=cal, va_calibrator=va)
    assert with_push["cal_prob"] <= 1.0 - p_push + 1e-9
    va_int = with_push["va_interval"]
    assert va_int is not None and va_int["is_conformal"] is True
    assert 0.0 <= va_int["p0"] <= va_int["p_va"] <= va_int["p1"] <= 1.0 - p_push + 1e-6


def test_t023_reporting_and_orchestrator_config_and_copula_honesty(tmp_path: Path) -> None:
    """T-023: Orchestrator uses build_production_engine and reporting labels match Student-t copula & runtime config."""
    from src.orchestrator import Orchestrator
    from src.reporting.audit_report import generate_audit_report
    from src.reporting.dashboard_generator import generate_interactive_html_dashboard
    from src.reporting.obsidian_sync import sync_obsidian_vault

    cfg = load_config()
    orch = Orchestrator(db_path=tmp_path / "orch.sqlite3", reports_dir=tmp_path / "r", obsidian_vault_dir=tmp_path / "n")
    assert orch.paper_engine.kelly_fraction == cfg.risk.kelly_fraction
    assert orch.paper_engine.max_stake_pen == cfg.risk.max_stake_pen
    assert orch.paper_engine.min_ev_threshold == cfg.risk.min_ev_threshold

    audit_md = generate_audit_report(
        {
            "leakage_violations_count": 0,
            "bankroll_reconciled": True,
            "immutability_triggers_verified": True,
            "history_integrity": {"missing_rows_total": 0, "missing_rows_by_table": {}},
            "auditor_approved": False,
            "exit_gates_evaluation": {
                "auto_transition_to_real_money": False,
                "recommendation": "REMAIN_IN_PAPER_TRADING",
                "passed_count": 3,
                "total_gates": 10,
                "gates": {
                    "gate_3_calibration_non_inferior_to_baseline": {"passed": False, "observed": "n/d", "required": "<= baseline"},
                    "gate_10_non_inferior_to_devigged_market": {"passed": False, "observed": "n/d", "required": "<= market"},
                },
            },
        },
        {"playwright_status": "Playwright runtime verificado dinámicamente"},
    )
    assert "Gemini Argon" not in audit_md
    assert "Playwright runtime verificado dinámicamente" in audit_md
    assert "aún no supera simultáneamente las puertas estadísticas" in audit_md
    assert cfg.model.version_id in audit_md

    vault = sync_obsidian_vault(
        tmp_path / "vault",
        daily_report_md="# Daily",
        weekly_report_md="# Weekly",
        audit_report_md=audit_md,
        metrics={
            "current_settled_bankroll_pen": 100.0,
            "net_profit_pen": 0.0,
            "roi_pct": 0.0,
            "settled_bets_count": 0,
            "exit_gates_evaluation": {"recommendation": "REMAIN_IN_PAPER_TRADING"},
        },
        environment_status={},
        target_date="2026-11-14",
    )
    sgp_note = (tmp_path / "vault" / "00-Inbox/02-SGP-Correlated-Parlays.md").read_text(encoding="utf-8")
    models_note = (tmp_path / "vault" / "06-Models/Model-Catalog-and-Versions.md").read_text(encoding="utf-8")
    sources_note = (tmp_path / "vault" / "01-Sources/Data-Sources-and-Limitations.md").read_text(encoding="utf-8")
    assert "00-Inbox/02-SGP-Correlated-Parlays.md" in vault
    assert "Gaussiana" not in sgp_note
    assert "Student-t" in sgp_note
    assert "model_b_elo_v2" not in models_note
    assert cfg.model.version_id in models_note
    assert "OPERATIONAL_LIVE_NBA_V8_AND_SYNERGY" not in sources_note

    out_html = tmp_path / "dashboard.html"
    generate_interactive_html_dashboard(
        {
            "current_settled_bankroll_pen": 100.0,
            "net_profit_pen": 0.0,
            "roi_pct": 0.0,
            "settled_bets_count": 0,
            "exit_gates_evaluation": {"gates": {}, "recommendation": "REMAIN_IN_PAPER_TRADING"},
        },
        [],
        [],
        out_html,
        "2026-11-14 15:00 PET",
        player_props=[],
    )
    html = out_html.read_text(encoding="utf-8")
    assert "Cópulas Gaussianas" not in html
    assert "Edge Sintético" not in html
    assert "Cópula Student-t" in html
