"""
Temporal integrity of the stored audit trail (`src/validation/temporal_integrity.py`), shared by the audited
migration that records the legacy rows and by the independent auditor (`nba_auditor`).

Two contradictions are detected (AGENTS.md principle 3: what was known, and when):

1. A game row ingested at or after tip-off whose `features_available_at` precedes tip-off. A row written
   after tip-off cannot hold a pre-game snapshot: its pre-game row was replaced during the game, or the
   game was first seen after tip-off and stamped "tip-off − 2 h". Both writes were removed from ingestion.
2. A quote whose `captured_at` precedes the moment it was fetched: `fetched_at` when the writer recorded it
   and, for legacy rows without it, the "tip-off − 15 min" stamp the ESPN adapter gave to quotes it fetched
   after tip-off (its own rows: odds ids prefixed with the game id, including their closing-line copies).

Declared historical replays and synthetic fixtures are out of scope (see HISTORICAL_REPLAY_SOURCE_PROVIDERS).
Rows recorded through the audited repair mechanism (`audit_repairs`) are reported but do not fail the gate;
a backdated quote must also be quarantined, so no decision, closing line or CLV uses it.
"""

from __future__ import annotations

from datetime import datetime
import sqlite3
from typing import Any

# Historical imports whose `features_available_at` = tip-off − 2 h is the declared simulated decision time
# of walk-forward replays (their ratings are recomputed from earlier results only), not a capture claim.
HISTORICAL_REPLAY_SOURCE_PROVIDERS: tuple[str, ...] = ("espn_history_backfill",)

# The stamp the ESPN adapter used for quotes it fetched at or after tip-off (removed).
LEGACY_BACKDATED_ODDS_OFFSET_MINUTES = 15

REPAIR_ACTION_POST_TIPOFF_GAME = "RECORDED_POST_TIPOFF_INGESTION"
REPAIR_ACTION_BACKDATED_ODDS = "RECORDED_BACKDATED_ODDS_CAPTURE"
QUARANTINE_REASON_BACKDATED_ODDS = "BACKDATED_POST_TIPOFF_CAPTURE"

TEMPORAL_FREEZE_TRIGGERS: tuple[str, ...] = (
    "prevent_started_game_temporal_rewrite",
    "prevent_started_game_temporal_replace",
    "prevent_backdated_odds_capture",
)


def audited_games_predicate(alias: str = "g") -> str:
    """SQL predicate for the games the temporal checks apply to: real games ingested by live adapters."""
    providers = ", ".join(f"'{p}'" for p in HISTORICAL_REPLAY_SOURCE_PROVIDERS)
    return (
        f"{alias}.game_id NOT LIKE 'SYN%' AND {alias}.source_provider NOT LIKE 'synthetic%' "
        f"AND {alias}.source_provider NOT IN ({providers})"
    )


def _rows(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    cols = [str(d[0]) for d in cur.description]
    return [dict(zip(cols, tuple(r), strict=True)) for r in cur.fetchall()]


def _minutes_between(start: str, later: str) -> float | None:
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(later.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return round((b - a).total_seconds() / 60.0, 1)


def find_post_tipoff_ingested_games(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Games ingested at or after tip-off whose `features_available_at` precedes tip-off."""
    rows = _rows(
        conn.execute(
            f"""
            SELECT g.game_id, g.status, g.source_provider, g.game_start_time, g.features_available_at, g.ingested_at,
                   (SELECT COUNT(*) FROM predictions p WHERE p.game_id = g.game_id) AS predictions,
                   (SELECT COUNT(*) FROM simulated_bets b WHERE b.game_id = g.game_id) AS bets
            FROM games g
            WHERE datetime(g.ingested_at) >= datetime(g.game_start_time)
              AND datetime(g.features_available_at) < datetime(g.game_start_time)
              AND {audited_games_predicate("g")}
            ORDER BY g.game_start_time, g.game_id
            """
        )
    )
    for r in rows:
        r["ingested_minutes_after_tipoff"] = _minutes_between(str(r["game_start_time"]), str(r["ingested_at"]))
    return rows


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(str(r[1]) == column for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def find_backdated_odds(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Quotes whose `captured_at` precedes the moment they were fetched (recorded or legacy-stamped)."""
    if _has_column(conn, "odds_snapshots", "fetched_at"):
        fetched_col = "o.fetched_at"
        recorded = "(o.fetched_at IS NOT NULL AND datetime(o.captured_at) < datetime(o.fetched_at))"
        legacy_guard = "o.fetched_at IS NULL AND "
    else:
        fetched_col = "NULL"
        recorded = "0"
        legacy_guard = ""
    legacy = (
        f"({legacy_guard}datetime(o.captured_at) = "
        f"datetime(g.game_start_time, '-{LEGACY_BACKDATED_ODDS_OFFSET_MINUTES} minutes') "
        "AND substr(o.odds_id, 1, length(o.game_id) + 1) = o.game_id || '_')"
    )
    return _rows(
        conn.execute(
            f"""
            SELECT o.odds_id, o.game_id, o.provider, o.market, o.selection, o.line_value, o.decimal_odds,
                   o.captured_at, {fetched_col} AS fetched_at, o.is_closing_line, g.game_start_time,
                   CASE WHEN {recorded} THEN 'CAPTURED_BEFORE_RECORDED_FETCH'
                        ELSE 'LEGACY_TIPOFF_MINUS_{LEGACY_BACKDATED_ODDS_OFFSET_MINUTES}_MIN_STAMP' END AS signature,
                   EXISTS (SELECT 1 FROM quarantined_odds q WHERE q.odds_id = o.odds_id) AS quarantined,
                   (SELECT r.registered_at FROM audit_row_registry r
                     WHERE r.table_name = 'odds_snapshots' AND r.row_pk = o.odds_id) AS first_registered_at
            FROM odds_snapshots o
            JOIN games g ON g.game_id = o.game_id
            WHERE ({recorded} OR {legacy})
              AND {audited_games_predicate("g")}
            ORDER BY g.game_start_time, o.odds_id
            """
        )
    )


def _recorded_pks(conn: sqlite3.Connection, table: str, action: str) -> set[str]:
    return {
        str(r[0])
        for r in conn.execute(
            "SELECT row_pk FROM audit_repairs WHERE table_name = ? AND action = ?", (table, action)
        ).fetchall()
    }


def summarize_temporal_integrity(conn: sqlite3.Connection) -> dict[str, Any]:
    """
    Auditor gate: passes only if every post-tip-off ingested game is recorded in `audit_repairs`, every
    backdated quote is both recorded and quarantined, and the temporal-freeze triggers are installed.
    """
    games = find_post_tipoff_ingested_games(conn)
    odds = find_backdated_odds(conn)
    recorded_games = _recorded_pks(conn, "games", REPAIR_ACTION_POST_TIPOFF_GAME)
    recorded_odds = _recorded_pks(conn, "odds_snapshots", REPAIR_ACTION_BACKDATED_ODDS)
    unrecorded_games = [g for g in games if str(g["game_id"]) not in recorded_games]
    unresolved_odds = [o for o in odds if str(o["odds_id"]) not in recorded_odds or not o["quarantined"]]
    installed = {
        str(r[0])
        for r in conn.execute(
            f"SELECT name FROM sqlite_master WHERE type = 'trigger' AND name IN ({', '.join('?' for _ in TEMPORAL_FREEZE_TRIGGERS)})",
            TEMPORAL_FREEZE_TRIGGERS,
        ).fetchall()
    }
    missing_triggers = [t for t in TEMPORAL_FREEZE_TRIGGERS if t not in installed]
    return {
        "passed": not unrecorded_games and not unresolved_odds and not missing_triggers,
        "post_tipoff_ingested_games": len(games),
        "recorded_post_tipoff_games": len(games) - len(unrecorded_games),
        "unrecorded_post_tipoff_games": len(unrecorded_games),
        "unrecorded_game_examples": [str(g["game_id"]) for g in unrecorded_games[:10]],
        "backdated_odds": len(odds),
        "backdated_closing_lines": sum(1 for o in odds if int(o["is_closing_line"] or 0) == 1),
        "unresolved_backdated_odds": len(unresolved_odds),
        "unresolved_odds_examples": [str(o["odds_id"]) for o in unresolved_odds[:10]],
        "temporal_freeze_triggers_active": not missing_triggers,
        "missing_triggers": missing_triggers,
    }
