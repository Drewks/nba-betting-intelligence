"""Database manager for SQLite persistence with immutable audit guarantees."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from src.storage.schema import DDL_STATEMENTS


class DatabaseManager:
    """Manages SQLite connections, schema initialization, and immutable audit queries."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize_schema(self) -> None:
        with self.connect() as conn:
            for ddl in DDL_STATEMENTS:
                conn.executescript(ddl)
            # Auto-migrate legacy simulated_bets table if it still has CHECK (stake_pen <= 1.0)
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='simulated_bets'"
            ).fetchone()
            if row and "stake_pen <= 1.0" in str(row["sql"]):
                conn.execute("PRAGMA foreign_keys = OFF;")
                conn.executescript(
                    """
                    DROP TRIGGER IF EXISTS prevent_settled_bet_tampering;
                    DROP TRIGGER IF EXISTS prevent_bet_delete;
                    CREATE TABLE simulated_bets_v2 (
                        bet_id TEXT PRIMARY KEY,
                        prediction_id TEXT NOT NULL UNIQUE,
                        game_id TEXT NOT NULL,
                        matchday_date TEXT NOT NULL,
                        market TEXT NOT NULL CHECK (market IN ('moneyline', 'total_points')),
                        selection TEXT NOT NULL CHECK (selection IN ('HOME', 'AWAY', 'OVER', 'UNDER')),
                        line_value REAL,
                        decimal_odds REAL NOT NULL CHECK (decimal_odds > 1.0),
                        estimated_prob REAL NOT NULL,
                        estimated_ev REAL NOT NULL,
                        stake_pen REAL NOT NULL CHECK (stake_pen > 0.0 AND stake_pen <= 25.0),
                        emitted_at TEXT NOT NULL,
                        model_version_id TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('PENDING', 'WON', 'LOST', 'PUSH', 'VOID')),
                        net_profit_pen REAL,
                        bankroll_after_pen REAL,
                        actual_result_summary TEXT,
                        settled_at TEXT,
                        UNIQUE(game_id, market, selection, line_value),
                        FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id),
                        FOREIGN KEY (game_id) REFERENCES games(game_id)
                    );
                    INSERT INTO simulated_bets_v2 SELECT * FROM simulated_bets;
                    DROP TABLE simulated_bets;
                    ALTER TABLE simulated_bets_v2 RENAME TO simulated_bets;
                    """
                )
                for ddl in DDL_STATEMENTS:
                    if "prevent_settled_bet_tampering" in ddl or "prevent_bet_delete" in ddl:
                        conn.executescript(ddl)
                conn.execute("PRAGMA foreign_keys = ON;")

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as conn:
            cur = conn.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row is not None else None

    def execute_insert(self, query: str, params: tuple[Any, ...] = ()) -> None:
        with self.connect() as conn:
            conn.execute(query, params)

    def log_agent_execution(
        self,
        exec_id: str,
        run_id: str,
        phase_number: int,
        agent_name: str,
        status: str,
        retry_count: int,
        started_at: str,
        completed_at: str | None,
        details: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_execution_log (
                    exec_id, run_id, phase_number, agent_name, status,
                    retry_count, started_at, completed_at, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exec_id,
                    run_id,
                    phase_number,
                    agent_name,
                    status,
                    retry_count,
                    started_at,
                    completed_at,
                    json.dumps(details, ensure_ascii=False),
                ),
            )
