"""
Unit and regression tests for Phase 2 Dynamic Player Props & DvP Engine:
Validates rolling EWMA baseline extraction from game_boxscores and dynamic team DvP multipliers.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.prediction.player_props import PlayerPropsEngine
from src.storage.db import DatabaseManager


def _seed_dynamic_test_environment(db: DatabaseManager) -> None:
    """Seeds games and boxscores for testing dynamic baseline and DvP computation."""
    # Seed 10 final games for TEST_OPP team where they allowed 130.0 PPG (very vulnerable defense)
    for i in range(10):
        gid = f"G_DYN_{i}"
        mdate = f"2026-11-{i+1:02d}"
        db.execute_insert(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, home_score, away_score, home_pace, away_pace, features_available_at, source_provider, ingested_at
            ) VALUES (?, '2025-2026', ?, ?, 'TEST_OPP', 'RIVAL', 'FINAL', 105.0, 130.0, 102.5, 102.5, ?, 'test', ?)
            """,
            (gid, mdate, f"{mdate}T20:00:00Z", f"{mdate}T18:00:00Z", f"{mdate}T18:00:00Z"),
        )
        # In each game, "Dynamic Star" scored 35 pts with 10 reb, 8 ast, 4 3pm in 36 minutes
        box_players = {
            "RIVAL": [
                {
                    "name": "Dynamic Star",
                    "min": 36.0,
                    "pts": 35.0,
                    "reb": 10.0,
                    "ast": 8.0,
                    "threed": 4.0,
                    "starter": True,
                }
            ],
            "TEST_OPP": [
                {
                    "name": "Opp Player",
                    "min": 30.0,
                    "pts": 20.0,
                    "reb": 5.0,
                    "ast": 3.0,
                    "threed": 2.0,
                    "starter": True,
                }
            ],
        }
        team_stats = {
            "RIVAL": {"pts": 130.0, "tpm": 16.0},
            "TEST_OPP": {"pts": 105.0, "tpm": 10.0},
        }
        db.execute_insert(
            """
            INSERT INTO game_boxscores (game_id, team_stats_json, players_json, source, fetched_at)
            VALUES (?, ?, ?, 'test_feed', ?)
            """,
            (gid, json.dumps(team_stats), json.dumps(box_players), f"{mdate}T23:00:00Z"),
        )


def test_phase2_dynamic_player_baseline_from_boxscores(tmp_path: Path) -> None:
    """Verifies that player baseline is computed dynamically from recent boxscores via EWMA."""
    db = DatabaseManager(tmp_path / "test_p2_player.sqlite3")
    _seed_dynamic_test_environment(db)

    engine = PlayerPropsEngine(db=db)
    baseline = engine.get_player_baseline("Dynamic Star")

    dyn_min, dyn_usg, dyn_ppm, dyn_rpm, dyn_apm, dyn_tpm = baseline
    assert dyn_min == 36.0
    # 35 pts in 36 mins -> ~0.972 pts/min
    assert 0.96 <= dyn_ppm <= 0.98
    # 10 reb in 36 mins -> ~0.278 reb/min
    assert 0.26 <= dyn_rpm <= 0.29
    # 8 ast in 36 mins -> ~0.222 ast/min
    assert 0.21 <= dyn_apm <= 0.23
    # 4 3pm in 36 mins -> ~0.111 3pm/min
    assert 0.10 <= dyn_tpm <= 0.12


def test_phase2_dynamic_team_defensive_multipliers(tmp_path: Path) -> None:
    """Verifies that opponent DvP multipliers adapt dynamically to points/3PM allowed in SQLite."""
    db = DatabaseManager(tmp_path / "test_p2_team.sqlite3")
    _seed_dynamic_test_environment(db)

    engine = PlayerPropsEngine(db=db)
    dvp = engine.get_team_defensive_multipliers("TEST_OPP")

    # TEST_OPP allowed 130 PPG (league benchmark ~114.2) -> multiplier >= 1.08 -> TARGET tier
    assert dvp["PTS"] >= 1.08
    assert dvp["tier"] == "TARGET"
    assert dvp["pace"] >= 100.0


def test_phase2_graceful_fallback_for_unlisted_player(tmp_path: Path) -> None:
    """Verifies that an unlisted rookie player falls back safely to default prior without exceptions."""
    db = DatabaseManager(tmp_path / "test_p2_fallback.sqlite3")
    engine = PlayerPropsEngine(db=db)

    baseline = engine.get_player_baseline("Unknown Rookie")
    dyn_min, dyn_usg, dyn_ppm, dyn_rpm, dyn_apm, dyn_tpm = baseline

    # Generic rotation defaults
    assert dyn_min == 26.0
    assert dyn_usg == 17.5
    assert dyn_ppm == 0.45
