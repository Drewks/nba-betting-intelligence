"""Database manager for SQLite persistence with immutable audit guarantees."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from src.storage.migrations import run_migrations
from src.storage.schema import DDL_STATEMENTS, VIEW_DDL

VALID_SOURCE_TYPES: frozenset[str] = frozenset({"OBSERVED", "DERIVED", "SYNTHETIC"})


class DatabaseManager:
    """Manages SQLite connections, schema initialization, and immutable audit queries."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        if str(self.db_path) != ":memory:" and not str(self.db_path).startswith(":memory:"):
            try:
                conn.execute("PRAGMA journal_mode = WAL;")
            except Exception:
                pass
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

            # Auto-migrate legacy player_prop_picks table if it lacks net_profit_pen or has old CHECK constraint
            p_row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='player_prop_picks'"
            ).fetchone()
            if p_row and "net_profit_pen" not in str(p_row["sql"]):
                conn.execute("PRAGMA foreign_keys = OFF;")
                conn.executescript(
                    """
                    DROP TRIGGER IF EXISTS prevent_settled_prop_tampering;
                    DROP TRIGGER IF EXISTS prevent_prop_delete;
                    CREATE TABLE player_prop_picks_v2 (
                        prop_id TEXT PRIMARY KEY,
                        game_id TEXT NOT NULL,
                        matchday_date TEXT NOT NULL,
                        player_name TEXT NOT NULL,
                        team TEXT NOT NULL,
                        prop_category TEXT NOT NULL CHECK (prop_category IN ('PTS', 'REB', 'AST', 'PRA', '3PM', 'PR', 'PA', 'RA', 'SGP')),
                        line_value REAL NOT NULL,
                        selection TEXT NOT NULL CHECK (selection IN ('OVER', 'UNDER', 'SGP', 'HOME', 'AWAY')),
                        decimal_odds REAL NOT NULL CHECK (decimal_odds > 1.0),
                        projected_mean REAL NOT NULL,
                        projected_std REAL NOT NULL,
                        model_prob REAL NOT NULL,
                        conformal_p_low REAL NOT NULL,
                        conformal_p_high REAL NOT NULL,
                        ev_pct REAL NOT NULL,
                        ev_lower_bound_pct REAL NOT NULL,
                        stake_pen REAL NOT NULL DEFAULT 1.00 CHECK (stake_pen > 0.0),
                        kelly_stake_pen REAL NOT NULL,
                        usage_bump_pct REAL NOT NULL DEFAULT 0.0,
                        rationale TEXT NOT NULL,
                        emitted_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'WON', 'LOST', 'PUSH', 'VOID')),
                        actual_stat REAL,
                        net_profit_pen REAL,
                        bankroll_after_pen REAL,
                        actual_result_summary TEXT,
                        settled_at TEXT,
                        FOREIGN KEY (game_id) REFERENCES games(game_id)
                    );
                    INSERT INTO player_prop_picks_v2 (
                        prop_id, game_id, matchday_date, player_name, team, prop_category,
                        line_value, selection, decimal_odds, projected_mean, projected_std,
                        model_prob, conformal_p_low, conformal_p_high, ev_pct, ev_lower_bound_pct,
                        stake_pen, kelly_stake_pen, usage_bump_pct, rationale, emitted_at,
                        status, actual_stat, settled_at
                    )
                    SELECT
                        prop_id, game_id, matchday_date, player_name, team, prop_category,
                        line_value, selection, decimal_odds, projected_mean, projected_std,
                        model_prob, conformal_p_low, conformal_p_high, ev_pct, ev_lower_bound_pct,
                        COALESCE(kelly_stake_pen, 1.00), kelly_stake_pen, usage_bump_pct, rationale, emitted_at,
                        status, actual_stat, settled_at
                    FROM player_prop_picks;
                    DROP TABLE player_prop_picks;
                    ALTER TABLE player_prop_picks_v2 RENAME TO player_prop_picks;
                    """
                )
                for ddl in DDL_STATEMENTS:
                    if "prevent_settled_prop_tampering" in ddl or "prevent_prop_delete" in ddl:
                        conn.executescript(ddl)
                conn.execute("PRAGMA foreign_keys = ON;")

            # Numbered, audited migrations (history restoration, quarantine sweep, ...)
            run_migrations(conn)

            # Derived views are always recreated so existing databases get the latest definitions.
            for view_name in reversed(list(VIEW_DDL)):
                conn.execute(f"DROP VIEW IF EXISTS {view_name}")
            for ddl in VIEW_DDL.values():
                conn.execute(ddl)

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

    def insert_odds_snapshot(self, odds: dict[str, Any], conn: sqlite3.Connection | None = None) -> bool:
        """
        Single write path for odds_snapshots. Provenance is mandatory: callers MUST declare
        `source_type` explicitly (OBSERVED / DERIVED / SYNTHETIC). The column has a legacy
        DEFAULT 'OBSERVED' in old databases, so relying on the default is forbidden here.
        Returns True if a new row was inserted (False if the odds_id already existed).
        """
        source_type = odds.get("source_type")
        if source_type not in VALID_SOURCE_TYPES:
            raise ValueError(
                f"insert_odds_snapshot requires explicit source_type in {sorted(VALID_SOURCE_TYPES)}; "
                f"got {source_type!r} for odds_id={odds.get('odds_id')!r}"
            )
        params = (
            odds["odds_id"],
            odds["game_id"],
            odds["provider"],
            odds["market"],
            odds["selection"],
            odds.get("line_value"),
            odds["decimal_odds"],
            odds.get("counterpart_decimal_odds"),
            odds["captured_at"],
            int(odds.get("is_closing_line", 0)),
            source_type,
        )
        sql = """
            INSERT OR IGNORE INTO odds_snapshots (
                odds_id, game_id, provider, market, selection, line_value,
                decimal_odds, counterpart_decimal_odds, captured_at, is_closing_line, source_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        if conn is not None:
            return conn.execute(sql, params).rowcount > 0
        with self.connect() as own_conn:
            return own_conn.execute(sql, params).rowcount > 0

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
