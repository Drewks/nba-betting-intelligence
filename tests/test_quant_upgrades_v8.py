"""Regression tests covering V8 ledger reconciliation, player boxscores & props OOS,
EWMA config/defense-sign wiring, cross-book line shopping, and Moneyline max-odds risk gating.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from src.backtesting.hyperparameter_optimizer import _simulate_parametric_pass
from src.config import load_config
from src.features.builder import build_pregame_features
from src.ingestion.normalizer import normalize_player_match_key
from src.paper_trading.engine import PaperTradingEngine
from src.prediction.ev_calculator import (
    canonical_bookmaker_name,
    select_best_line_shopping_candidates,
)
from src.prediction.player_props import PlayerPropsEngine
from src.storage.db import DatabaseManager
from tests.helpers import _seed_sample_game_and_prediction


def test_m011_reconciles_observed_ledger_and_backfills_player_boxscores(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "test_m011.sqlite3")
    for tid, name in [("BOS", "Boston Celtics"), ("MIA", "Miami Heat")]:
        db.execute_insert(
            "INSERT OR IGNORE INTO teams (team_id, full_name, conference, division, updated_at) "
            "VALUES (?, ?, 'East', 'Atlantic', '2026-10-01T00:00:00Z')",
            (tid, name),
        )
    db.execute_insert(
        """
        INSERT OR IGNORE INTO model_versions (
            model_version_id, model_family, market, train_start_date, train_end_date,
            trained_at, hyperparameters_json, is_active, approved_by
        ) VALUES (
            'model_c_test_v1', 'model_f_ensemble', 'moneyline',
            '2026-01-01', '2026-10-19', '2026-10-19T23:00:00Z', '{}', 1, 'test'
        )
        """
    )

    for gid, dt, pred_id, provider, odds, prob in [
        ("G_PERU_LEDGER", "2026-10-20", "PRED_PERU_L", "Betano [T-6H Peru]", 2.10, 0.54),
        ("G_OBS_LEDGER", "2026-10-21", "PRED_OBS_L", "Pinnacle", 1.90, 0.56),
    ]:
        db.execute_insert(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, home_score, away_score, features_available_at, source_provider, ingested_at
            ) VALUES (?, '2026-27', ?, ?, 'BOS', 'MIA', 'SCHEDULED', NULL, NULL, ?, 'espn', ?)
            """,
            (gid, dt, f"{dt}T23:00:00Z", f"{dt}T18:00:00Z", f"{dt}T18:00:00Z"),
        )
        db.execute_insert(
            """
            INSERT INTO predictions (
                prediction_id, game_id, market, selection, line_value, model_version_id,
                raw_probability, calibrated_probability, uncertainty_std, implied_prob_gross,
                implied_prob_fair, bookmaker_overround, decimal_odds_used, odds_provider,
                odds_captured_at, ev_unit, ev_pct, emitted_at, features_snapshot_json
            ) VALUES (
                ?, ?, 'moneyline', 'HOME', NULL, 'model_c_test_v1',
                ?, ?, 0.04, ?, ?, 0.04, ?, ?, ?, ?, ?, ?, '{}'
            )
            """,
            (
                pred_id,
                gid,
                prob,
                prob,
                round(1.0 / odds, 5),
                round(1.0 / odds, 5),
                odds,
                provider,
                f"{dt}T19:00:00Z",
                round(prob * odds - 1.0, 5),
                round((prob * odds - 1.0) * 100.0, 3),
                f"{dt}T20:00:00Z",
            ),
        )

    engine = PaperTradingEngine(db, initial_bankroll_pen=100.0, exclude_synthetic=False, min_ev_threshold=0.02)
    res_peru = engine.evaluate_and_record_matchday_selections(
        matchday_date="2026-10-20",
        candidate_predictions=[
            {
                "prediction_id": "PRED_PERU_L",
                "game_id": "G_PERU_LEDGER",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 2.10,
                "calibrated_probability": 0.54,
                "ev_unit": 0.134,
                "ev_pct": 13.4,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-20T20:00:00Z",
            }
        ],
    )
    peru_bet_id = res_peru["placed_bets"][0]["bet_id"]
    engine.settle_bet(peru_bet_id, "FINAL", 118, 100, "2026-10-21T02:00:00Z")

    res_obs = engine.evaluate_and_record_matchday_selections(
        matchday_date="2026-10-21",
        candidate_predictions=[
            {
                "prediction_id": "PRED_OBS_L",
                "game_id": "G_OBS_LEDGER",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 1.90,
                "calibrated_probability": 0.56,
                "ev_unit": 0.064,
                "ev_pct": 6.4,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-21T20:00:00Z",
            }
        ],
    )
    obs_bet_id = res_obs["placed_bets"][0]["bet_id"]
    engine.settle_bet(obs_bet_id, "FINAL", 115, 102, "2026-10-22T02:00:00Z")

    db.execute_insert(
        """
        INSERT INTO game_boxscores (game_id, team_stats_json, players_json, source, fetched_at)
        VALUES (?, '{}', ?, 'espn', '2026-10-21T03:00:00Z')
        """,
        (
            "G_OBS_LEDGER",
            json.dumps(
                {
                    "BOS": [
                        {
                            "name": "Nikola Jokić",
                            "min": 35.0,
                            "pts": 29.0,
                            "reb": 13.0,
                            "ast": 10.0,
                            "threed": 2.0,
                            "starter": True,
                        },
                        {
                            "name": "Jayson Tatum",
                            "min": 36.0,
                            "pts": 27.0,
                            "reb": 8.0,
                            "ast": 5.0,
                            "threed": 3.0,
                            "starter": True,
                        },
                    ]
                }
            ),
        ),
    )

    with db.connect() as conn:
        conn.execute("DELETE FROM player_boxscores")
        conn.execute("DROP VIEW IF EXISTS v_observed_bankroll_ledger")
        conn.execute(
            "CREATE VIEW v_observed_bankroll_ledger AS "
            "SELECT *, settled_bankroll_pen AS raw_settled_bankroll_pen FROM bankroll_ledger"
        )
        conn.execute(
            "DELETE FROM schema_migrations WHERE migration_id = ?",
            ("2026_11_14_011_reconcile_observed_ledger_and_player_boxscores",),
        )

    db.initialize_schema()

    mig_row = db.fetch_one(
        "SELECT migration_id FROM schema_migrations WHERE migration_id = ?",
        ("2026_11_14_011_reconcile_observed_ledger_and_player_boxscores",),
    )
    assert mig_row is not None

    jokic_row = db.fetch_one(
        "SELECT * FROM player_boxscores WHERE game_id = ? AND player_key = ?",
        ("G_OBS_LEDGER", normalize_player_match_key("Nikola Jokic")),
    )
    assert jokic_row is not None
    assert jokic_row["pts"] == pytest.approx(29.0)
    assert jokic_row["threed"] == pytest.approx(2.0)
    assert jokic_row["starter"] == 1

    obs_ledger_rows = db.fetch_all("SELECT * FROM v_observed_bankroll_ledger ORDER BY entry_id ASC")
    obs_ref_ids = {r["reference_bet_id"] for r in obs_ledger_rows if r["reference_bet_id"]}
    assert obs_bet_id in obs_ref_ids
    assert peru_bet_id not in obs_ref_ids

    obs_state = PaperTradingEngine(db, exclude_synthetic=True).get_bankroll_state()
    raw_peru_row = db.fetch_one(
        "SELECT settled_bankroll_pen FROM bankroll_ledger WHERE reference_bet_id = ? AND event_type = 'BET_SETTLED'",
        (peru_bet_id,),
    )
    assert raw_peru_row is not None
    assert raw_peru_row["settled_bankroll_pen"] == pytest.approx(101.10, abs=1e-4)
    assert obs_ledger_rows[-1]["settled_bankroll_pen"] == pytest.approx(obs_state["settled_bankroll_pen"], abs=1e-4)
    assert obs_state["settled_bankroll_pen"] == pytest.approx(100.90, abs=1e-4)


def test_player_props_half_line_unicode_zero_lookahead_and_oos_calibration(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "test_props_v8.sqlite3")
    for tid, name in [("DEN", "Denver Nuggets"), ("DAL", "Dallas Mavericks")]:
        db.execute_insert(
            "INSERT OR IGNORE INTO teams (team_id, full_name, conference, division, updated_at) "
            "VALUES (?, ?, 'West', 'Northwest', '2026-10-01T00:00:00Z')",
            (tid, name),
        )

    now_utc = datetime.now(timezone.utc)
    hist_dates = [
        (f"G_P_HIST_{i}", (now_utc - timedelta(days=10 - 2 * i)).strftime("%Y-%m-%d"))
        for i in range(4)
    ]
    for gid, dt in hist_dates:
        start = f"{dt}T01:00:00Z"
        db.execute_insert(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
                away_off_rtg, away_def_rtg, away_pace,
                features_available_at, source_provider, ingested_at, result_recorded_at
            ) VALUES (?, '2026-27', ?, ?, 'DEN', 'DAL', 'FINAL', 114, 108, 118.0, 110.0, 99.0, 112.0, 114.0, 98.5, ?, 'espn', ?, ?)
            """,
            (gid, dt, start, start, start, start),
        )
        db.execute_insert(
            """
            INSERT INTO player_boxscores (
                game_id, player_name, player_key, team, game_start_time,
                minutes, pts, reb, ast, threed, starter
            ) VALUES (?, 'Nikola Jokić', ?, 'DEN', ?, 34.0, 26.0, 12.0, 9.0, 2.0, 1)
            """,
            (gid, normalize_player_match_key("Nikola Jokić"), start),
        )

    # Future decoy game that MUST NEVER leak into pre-tipoff projections for slate game
    fut_dt = now_utc + timedelta(days=20)
    fut_date_str = fut_dt.strftime("%Y-%m-%d")
    fut_start = fut_dt.strftime("%Y-%m-%dT01:00:00Z")
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, home_score, away_score, features_available_at, source_provider, ingested_at
        ) VALUES ('G_P_FUTURE_LEAK', '2026-27', ?, ?, 'DEN', 'DAL', 'FINAL', 140, 100, ?, 'espn', ?)
        """,
        (fut_date_str, fut_start, fut_start, fut_start),
    )
    db.execute_insert(
        """
        INSERT INTO player_boxscores (
            game_id, player_name, player_key, team, game_start_time,
            minutes, pts, reb, ast, threed, starter
        ) VALUES ('G_P_FUTURE_LEAK', 'Nikola Jokić', ?, 'DEN', ?, 40.0, 75.0, 30.0, 25.0, 14.0, 1)
        """,
        (normalize_player_match_key("Nikola Jokić"), fut_start),
    )

    slate_dt = now_utc + timedelta(days=2)
    slate_date_str = slate_dt.strftime("%Y-%m-%d")
    slate_start = slate_dt.strftime("%Y-%m-%dT23:00:00Z")
    cap_ts = (now_utc + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, features_available_at, source_provider, ingested_at
        ) VALUES ('G_P_SLATE', '2026-27', ?, ?, 'DEN', 'DAL', 'SCHEDULED', ?, 'espn', ?)
        """,
        (slate_date_str, slate_start, cap_ts, cap_ts),
    )
    db.execute_insert(
        """
        INSERT INTO odds_snapshots (
            odds_id, game_id, provider, market, selection, line_value,
            decimal_odds, counterpart_decimal_odds, captured_at, is_closing_line, source_type
        ) VALUES (
            'ODDS_3PM_HALF', 'G_P_SLATE', 'Te Apuesto Perú|Nikola Jokic|3PM',
            'player_prop', 'OVER', 0.5, 1.55, 2.30, ?, 0, 'OBSERVED'
        )
        """,
        (cap_ts,),
    )

    props_engine = PlayerPropsEngine(db=db, min_ev_threshold=0.03)
    proj = props_engine.project_player_stats(
        player_name="Nikola Jokic",
        team="DEN",
        opponent_team="DAL",
        as_of_utc=slate_start,
    )
    assert proj["projections"]["PTS"]["mean"] < 35.0
    assert proj["projections"]["3PM"]["mean"] < 4.0

    opps = props_engine.generate_slate_prop_opportunities(
        slate_games=[
            {
                "game_id": "G_P_SLATE",
                "matchday_date": slate_date_str,
                "game_start_time": slate_start,
                "home_team": "DEN",
                "away_team": "DAL",
            }
        ],
        bankroll_pen=100.0,
        min_ev_pct=3.0,
        output_file=tmp_path / "props_out.json",
    )
    three_pm_half = [
        o for o in opps if o["prop_category"] == "3PM" and float(o["line_value"]) == pytest.approx(0.5)
    ]
    assert three_pm_half, "Expected 0.5 3PM line to remain eligible with Unicode accent matching"

    oos = props_engine.evaluate_historical_oos_calibration(
        min_date=(now_utc - timedelta(days=15)).strftime("%Y-%m-%dT00:00:00Z"),
        min_minutes=12.0,
        max_samples=20,
    )
    assert oos["evaluated_samples"] >= 1
    assert "PTS>15.5" in oos["benchmarks"]
    assert "3PM>0.5" in oos["benchmarks"]
    assert 0.0 <= oos["benchmarks"]["3PM>0.5"]["brier"] <= 1.0


def test_ewma_config_wiring_and_defense_sign_consistency() -> None:
    base_dt = datetime(2025, 11, 1, 1, 0, tzinfo=timezone.utc)
    matchups = [("BOS", "WAS"), ("CLE", "CHA"), ("OKC", "POR")]
    hist_games: list[dict[str, object]] = []
    for i in range(96):
        strong, weak = matchups[i % len(matchups)]
        start_str = (base_dt + timedelta(hours=12 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        home, away = (strong, weak) if i % 2 == 0 else (weak, strong)
        win_pts, lose_pts = (114, 106) if i < 64 else (126, 92)
        home_score, away_score = (win_pts, lose_pts) if home == strong else (lose_pts, win_pts)
        hist_games.append(
            {
                "game_id": f"G_DET_{i:03d}",
                "status": "FINAL",
                "game_start_time": start_str,
                "matchday_date": start_str[:10],
                "home_team": home,
                "away_team": away,
                "home_score": home_score,
                "away_score": away_score,
            }
        )

    target_game = {
        "game_id": "G_DET_TARGET",
        "game_start_time": (base_dt + timedelta(hours=12 * 100)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "home_team": "BOS",
        "away_team": "WAS",
        "home_off_rtg": 118.0,
        "home_def_rtg": 100.0,
        "home_pace": 99.0,
        "away_off_rtg": 100.0,
        "away_def_rtg": 118.0,
        "away_pace": 99.0,
        "home_rest_days": 2,
        "away_rest_days": 2,
    }

    feats_default = build_pregame_features(target_game, hist_games, market="moneyline")
    assert feats_default["matchup_mismatch"] > 5.0

    base_cfg = load_config()
    cfg_a = replace(
        deepcopy(base_cfg),
        model=replace(
            base_cfg.model,
            ewma_alpha_slow=0.02,
            ewma_alpha_fast=0.09,
            tempo_alpha_slow=0.02,
            tempo_alpha_fast=0.09,
        ),
    )
    cfg_b = replace(
        deepcopy(base_cfg),
        model=replace(
            base_cfg.model,
            ewma_alpha_slow=0.09,
            ewma_alpha_fast=0.21,
            tempo_alpha_slow=0.07,
            tempo_alpha_fast=0.18,
        ),
    )

    with patch("src.config.load_config", return_value=cfg_a):
        feats_a = build_pregame_features(target_game, hist_games, market="moneyline")
    with patch("src.config.load_config", return_value=cfg_b):
        feats_b = build_pregame_features(target_game, hist_games, market="moneyline")
    assert feats_a["form_surge_diff"] != pytest.approx(feats_b["form_surge_diff"], abs=1e-4)
    assert feats_a["structural_margin"] != pytest.approx(feats_b["structural_margin"], abs=1e-4)
    assert feats_a["tempo_sum"] != pytest.approx(feats_b["tempo_sum"], abs=1e-4)
    assert feats_a["structural_total"] != pytest.approx(feats_b["structural_total"], abs=1e-4)

    raw_p, _anch_p, outcomes, pred_tot, act_tot = _simulate_parametric_pass(
        hist_games,
        alpha_slow=0.0375,
        alpha_fast=0.13,
        tempo_alpha_slow=0.055,
        tempo_alpha_fast=0.13,
        blowout_cap=28.0,
        market_model_weight=0.30,
        spread_sigma=11.6,
        momentum_blend_weight=0.88,
        eval_slice_size=24,
        holdout_size=0,
    )
    assert len(raw_p) == 24
    brier = float(np.mean((np.asarray(raw_p) - np.asarray(outcomes)) ** 2))
    assert brier < 0.15
    assert len(pred_tot) == len(act_tot) == 24


def test_line_shopping_canonical_aliases_and_moneyline_odds_cap(tmp_path: Path) -> None:
    assert canonical_bookmaker_name("Te Apuesto Perú [LIVE_API]") == "te_apuesto"
    assert canonical_bookmaker_name("Betsson (LineShop)") == "betsson"
    assert canonical_bookmaker_name("Coolbet") == "coolbet"
    assert canonical_bookmaker_name("Apuesta Total") == "apuesta_total"
    assert canonical_bookmaker_name("Betano Perú [LIVE_API]") == "betano"

    candidates = [
        {
            "game_id": "G_LS_1",
            "market": "moneyline",
            "selection": "HOME",
            "line_value": None,
            "odds_provider": "Pinnacle",
            "decimal_odds_used": 2.04,
            "ev_pct": 4.2,
        },
        {
            "game_id": "G_LS_1",
            "market": "moneyline",
            "selection": "HOME",
            "line_value": None,
            "odds_provider": "Betano Perú [LIVE_API]",
            "decimal_odds_used": 2.10,
            "ev_pct": 6.5,
        },
        {
            "game_id": "G_LS_1",
            "market": "moneyline",
            "selection": "HOME",
            "line_value": None,
            "odds_provider": "Te Apuesto Perú [LIVE_API]",
            "decimal_odds_used": 2.18,
            "ev_pct": 9.8,
        },
    ]
    best_all = select_best_line_shopping_candidates(candidates)
    assert len(best_all) == 1
    winner = best_all[0]
    assert winner["decimal_odds_used"] == pytest.approx(2.18)
    assert winner["line_shop_books"] == 3
    assert canonical_bookmaker_name(str(winner["runner_up_provider"])) == "betano"
    assert winner["line_shop_gain_pct"] == pytest.approx(((2.18 - 2.10) / 2.10) * 100.0, abs=0.05)

    best_filtered = select_best_line_shopping_candidates(candidates, accessible_books=["pinnacle", "betano"])
    assert len(best_filtered) == 1
    assert best_filtered[0]["decimal_odds_used"] == pytest.approx(2.10)
    assert best_filtered[0]["line_shop_books"] == 3
    assert canonical_bookmaker_name(str(best_filtered[0]["runner_up_provider"])) == "te_apuesto"
    assert best_filtered[0]["line_shop_gain_pct"] == pytest.approx(((2.10 / 2.18) - 1.0) * 100.0, abs=0.05)

    db = DatabaseManager(tmp_path / "test_ml_cap.sqlite3")
    pred_high = _seed_sample_game_and_prediction(db, "G_ML_CAP_HIGH")
    pred_ok = _seed_sample_game_and_prediction(db, "G_ML_CAP_OK")

    engine = PaperTradingEngine(db, initial_bankroll_pen=100.0, min_ev_threshold=0.02)
    res = engine.evaluate_and_record_matchday_selections(
        matchday_date="2026-10-20",
        candidate_predictions=[
            {
                "prediction_id": pred_high,
                "game_id": "G_ML_CAP_HIGH",
                "market": "moneyline",
                "selection": "AWAY",
                "line_value": None,
                "decimal_odds_used": 2.95,
                "calibrated_probability": 0.41,
                "model_market_disagreement": 0.04,
                "ev_unit": 0.2095,
                "ev_pct": 20.95,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-20T20:00:00Z",
                "moneyline_max_odds": 2.80,
            },
            {
                "prediction_id": pred_ok,
                "game_id": "G_ML_CAP_OK",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 2.45,
                "calibrated_probability": 0.45,
                "model_market_disagreement": 0.04,
                "ev_unit": 0.1025,
                "ev_pct": 10.25,
                "model_version_id": "model_c_test_v1",
                "emitted_at": "2026-10-20T20:00:00Z",
                "moneyline_max_odds": 2.80,
            },
        ],
    )
    assert any(
        d["game_id"] == "G_ML_CAP_HIGH" and d["reason_code"] == "EXCESSIVE_LONGSHOT_VARIANCE"
        for d in res["no_bet_decisions"]
    )
    assert len(res["placed_bets"]) == 1
    assert res["placed_bets"][0]["game_id"] == "G_ML_CAP_OK"
