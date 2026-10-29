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
