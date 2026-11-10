"""
Shared test helper fixtures and utilities (`tests/helpers.py`).
"""

from __future__ import annotations

from src.storage.db import DatabaseManager


def _seed_sample_game_and_prediction(db: DatabaseManager, game_id: str = "G_TEST_01") -> str:
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
            away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
            features_available_at, source_provider, ingested_at, result_recorded_at
        ) VALUES (
            ?, '2026-27', '2026-10-20', '2026-10-20T23:00:00Z', 'BOS', 'MIA',
            'SCHEDULED', NULL, NULL, 118.5, 110.2, 99.0, 113.5, 112.0, 97.5, 2, 2,
            '2026-10-20T18:00:00Z', 'test_fixture', '2026-10-20T18:00:00Z', NULL
        )
        """,
        (game_id,),
    )
    db.execute_insert(
        """
        INSERT OR IGNORE INTO model_versions (
            model_version_id, model_family, market, train_start_date, train_end_date,
            trained_at, hyperparameters_json, is_active, approved_by
        ) VALUES (
            'model_c_test_v1', 'model_c_point_margin', 'moneyline',
            '2026-01-01', '2026-10-19', '2026-10-19T23:00:00Z', '{}', 1, 'test'
        )
        """
    )
    pred_id = f"PRED_{game_id}"
    db.execute_insert(
        """
        INSERT INTO predictions (
            prediction_id, game_id, market, selection, line_value, model_version_id,
            raw_probability, calibrated_probability, uncertainty_std, implied_prob_gross,
            implied_prob_fair, bookmaker_overround, decimal_odds_used, odds_provider,
            odds_captured_at, ev_unit, ev_pct, emitted_at, features_snapshot_json
        ) VALUES (
            ?, ?, 'moneyline', 'HOME', NULL, 'model_c_test_v1',
            0.52, 0.52, 0.05, 0.47619, 0.455, 0.045, 2.10, 'TestBook',
            '2026-10-20T19:00:00Z', 0.092, 9.2, '2026-10-20T20:00:00Z', '{}'
        )
        """,
        (pred_id, game_id),
    )
    return pred_id
