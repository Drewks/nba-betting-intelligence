"""
Shared test helper fixtures and utilities (`tests/helpers.py`).
"""

from __future__ import annotations

import atexit
from pathlib import Path
import shutil
import sqlite3
import tempfile

from src.storage.db import DatabaseManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PROD_DB_SOURCE = PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"
_SESSION_SNAPSHOT_DIR: Path | None = None
_SESSION_SNAPSHOT_DB: Path | None = None


def get_isolated_prod_db_snapshot() -> Path:
    """
    Returns a process-scoped temporary copy of `data/nba_intelligence.sqlite3`
    created via raw file copy (`shutil.copy2`) so SQLite never opens or checkpoints
    the repository's tracked `data/nba_intelligence.sqlite3` during tests.
    """
    global _SESSION_SNAPSHOT_DIR, _SESSION_SNAPSHOT_DB
    if _SESSION_SNAPSHOT_DB is not None and _SESSION_SNAPSHOT_DB.exists():
        return _SESSION_SNAPSHOT_DB

    if not _PROD_DB_SOURCE.exists():
        raise FileNotFoundError(f"Production SQLite database not found at {_PROD_DB_SOURCE}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="nba_pytest_hermetic_db_"))
    atexit.register(lambda: shutil.rmtree(tmp_dir, ignore_errors=True))
    dst = tmp_dir / "nba_intelligence.sqlite3"
    shutil.copy2(_PROD_DB_SOURCE, dst)
    _SESSION_SNAPSHOT_DIR = tmp_dir
    _SESSION_SNAPSHOT_DB = dst
    return dst


def copy_prod_db(tmp_path: Path, filename: str = "nba_intelligence_copy.sqlite3") -> Path:
    """Copies the isolated production DB snapshot into `tmp_path / filename` for writable test isolation."""
    src = get_isolated_prod_db_snapshot()
    dst = tmp_path / filename
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def connect_readonly_prod_db() -> sqlite3.Connection:
    """Opens a SQLite connection against the isolated snapshot copy (never the tracked repo file)."""
    snap = get_isolated_prod_db_snapshot()
    conn = sqlite3.connect(f"file:{snap.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


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
