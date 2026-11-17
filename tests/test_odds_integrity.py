"""Permanent auditor checks: copied cross-game live quotes and decisions stamped after their run."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from src.agents.specialized_agents import NBAAuditorAgent
from src.paper_trading.engine import build_production_engine
from src.storage.db import DatabaseManager
from src.validation.odds_integrity import count_decision_timestamp_violations, find_copied_live_quotes


def _seed_game(db: DatabaseManager, game_id: str, start: str) -> None:
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, features_available_at, source_provider, ingested_at
        ) VALUES (?, '2026-27', ?, ?, 'MIN', 'POR', 'SCHEDULED', '2026-11-16T12:00:00Z', 'espn', '2026-11-16T12:00:00Z')
        """,
        (game_id, start[:10], start),
    )


def _quote(db: DatabaseManager, odds_id: str, game_id: str, odds: float, line: float) -> None:
    db.insert_odds_snapshot({
        "odds_id": odds_id, "game_id": game_id, "provider": "Pinnacle [LIVE_API]", "market": "total_points",
        "selection": "UNDER", "line_value": line, "decimal_odds": odds, "counterpart_decimal_odds": 1.91,
        "captured_at": "2026-11-17T00:30:00Z", "source_type": "OBSERVED",
    })


def test_auditor_flags_unquarantined_copied_quotes(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "oi.sqlite3")
    _seed_game(db, "G1", "2026-11-17T01:00:00Z")
    _seed_game(db, "G2", "2026-11-18T01:00:00Z")
    for i, odds in enumerate((1.98, 1.91, 2.05)):
        _quote(db, f"A{i}", "G1", odds, 227.5 + i)
        _quote(db, f"B{i}", "G2", odds, 227.5 + i)
    with db.connect() as conn:
        assert len(find_copied_live_quotes(conn)) == 6
    auditor = NBAAuditorAgent(db, build_production_engine(db))
    oi = auditor._verify_odds_and_decision_integrity()
    assert oi["unquarantined_copied_quotes"] == 6

    with db.connect() as conn:
        for i in range(3):
            for g in "AB":
                conn.execute(
                    "INSERT INTO quarantined_odds (odds_id, reason, quarantined_at) VALUES (?, 'TEST', '2026-11-17T01:00:00Z')",
                    (f"{g}{i}",),
                )
    assert auditor._verify_odds_and_decision_integrity()["unquarantined_copied_quotes"] == 0


def test_decision_timestamp_violations_split_post_fix_and_legacy() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE run_manifests (run_id TEXT PRIMARY KEY, created_at TEXT);
        CREATE TABLE predictions (prediction_id TEXT PRIMARY KEY, run_manifest_id TEXT, emitted_at TEXT);
        INSERT INTO run_manifests VALUES ('OLD', '2026-11-16T02:00:00Z'), ('NEW', '2026-11-17T03:00:00Z');
        INSERT INTO predictions VALUES
            ('p1', 'OLD', '2026-11-16T22:00:00Z'),  -- legacy tip-off - 2 h stamp
            ('p2', 'NEW', '2026-11-17T03:00:00Z'),  -- real decision time
            ('p3', 'NEW', '2026-11-17T05:00:00Z');  -- would be a regression
        """
    )
    assert count_decision_timestamp_violations(conn) == {"post_fix": 1, "legacy": 1}
