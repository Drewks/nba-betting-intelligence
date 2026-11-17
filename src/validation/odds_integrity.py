"""
Odds integrity checks shared by migrations and the independent auditor (`src/validation/odds_integrity.py`).
"""

from __future__ import annotations

import sqlite3

# The decision timestamp became the real wall clock when this fix was deployed (PR #41). Predictions of
# runs created afterwards must never be stamped later than their own run; older rows keep the legacy
# "tip-off - 2 h" stamps and are reported separately (history is immutable).
DECISION_TIMESTAMP_FIX_DEPLOYED_AT = "2026-11-17T00:14:00Z"
MIN_COPIED_QUOTES = 3


def find_copied_live_quotes(conn: sqlite3.Connection, min_copied_quotes: int = MIN_COPIED_QUOTES) -> list[str]:
    """
    Odds ids of live-API quotes copied onto two games of the same teams (same provider, capture second,
    market, side, line and price), when a capture copied at least `min_copied_quotes` of them. These
    come from matching book events to games by team pair only; one game's quotes cannot be told apart
    from the other's afterwards.
    """
    # Only the affected feed path (live book APIs, provider label "[LIVE_API]") and only captures where a
    # whole slate entry was copied: at least MIN_COPIED_QUOTES identical quotes of the same capture on
    # both games. A single coincidental equal price between two real games is left untouched.
    pairs = conn.execute(
        """
        SELECT o1.game_id AS g1, o2.game_id AS g2, o1.provider AS provider, o1.captured_at AS captured_at,
               COUNT(*) AS n
        FROM odds_snapshots o1
        JOIN odds_snapshots o2
          ON o1.provider = o2.provider
         AND o1.captured_at = o2.captured_at
         AND o1.market = o2.market
         AND o1.selection = o2.selection
         AND COALESCE(o1.line_value, -9999) = COALESCE(o2.line_value, -9999)
         AND o1.decimal_odds = o2.decimal_odds
         AND o1.game_id < o2.game_id
        JOIN games g1 ON g1.game_id = o1.game_id
        JOIN games g2 ON g2.game_id = o2.game_id
        WHERE o1.provider LIKE '%[LIVE_API]%'
          AND (
            (g1.home_team = g2.home_team AND g1.away_team = g2.away_team)
            OR (g1.home_team = g2.away_team AND g1.away_team = g2.home_team)
          )
        GROUP BY o1.game_id, o2.game_id, o1.provider, o1.captured_at
        HAVING COUNT(*) >= ?
        """,
        (min_copied_quotes,),
    ).fetchall()
    copied: list[str] = []
    for g1, g2, provider, captured_at, _n in pairs:
        copied.extend(
            str(r[0])
            for r in conn.execute(
                """
                SELECT o.odds_id FROM odds_snapshots o
                WHERE o.game_id IN (?, ?) AND o.provider = ? AND o.captured_at = ?
                  AND EXISTS (
                    SELECT 1 FROM odds_snapshots c
                    WHERE c.game_id IN (?, ?) AND c.game_id <> o.game_id
                      AND c.provider = o.provider AND c.captured_at = o.captured_at
                      AND c.market = o.market AND c.selection = o.selection
                      AND COALESCE(c.line_value, -9999) = COALESCE(o.line_value, -9999)
                      AND c.decimal_odds = o.decimal_odds
                  )
                """,
                (g1, g2, provider, captured_at, g1, g2),
            ).fetchall()
        )
    return sorted(set(copied))


def count_decision_timestamp_violations(conn: sqlite3.Connection) -> dict[str, int]:
    """
    Predictions stamped later than the run that produced them (a decision cannot happen after its run).
    `post_fix` counts runs created after the fix was deployed and must be 0; `legacy` counts older runs.
    """
    rows = conn.execute(
        """
        SELECT m.created_at >= ? AS post_fix, COUNT(*) AS n
        FROM predictions p
        JOIN run_manifests m ON m.run_id = p.run_manifest_id
        WHERE p.emitted_at > m.created_at
        GROUP BY 1
        """,
        (DECISION_TIMESTAMP_FIX_DEPLOYED_AT,),
    ).fetchall()
    out = {"post_fix": 0, "legacy": 0}
    for post_fix, n in rows:
        out["post_fix" if post_fix else "legacy"] += int(n)
    return out


QUARANTINE_REASON_COPIED = "MISATTRIBUTED_SAME_TEAM_PAIR_GAME"


def quarantine_copied_live_quotes(conn: sqlite3.Connection, quarantined_at: str) -> int:
    """
    Quarantines copied cross-game live quotes not yet quarantined, so they never reach a decision.
    Run before candidate generation; quotes are never edited or deleted. Returns how many were added.
    """
    already = {str(r[0]) for r in conn.execute("SELECT odds_id FROM quarantined_odds").fetchall()}
    added = 0
    for odds_id in find_copied_live_quotes(conn):
        if odds_id in already:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO quarantined_odds (odds_id, reason, quarantined_at) VALUES (?, ?, ?)",
            (odds_id, QUARANTINE_REASON_COPIED, quarantined_at),
        )
        added += 1
    return added
