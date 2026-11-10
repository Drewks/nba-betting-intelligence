"""
Numbered, idempotent schema/data migrations for the audit database.

Rules:
- Each migration runs at most once per database and is recorded in `schema_migrations`.
- Every row-level data repair is written to the append-only `audit_repairs` table, so the
  repair itself is auditable (what changed, when, and why).
- Migrations never DELETE or UPDATE immutable history. The only UPDATEs allowed are the ones the
  immutability triggers already permit (PENDING -> settled transitions restoring a lost settlement,
  and SCHEDULED -> FINAL result restoration on `games`).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any

from src.storage.schema import UNOBSERVED_PROVIDER_SQL_PREDICATE

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RECOVERY_BUNDLE_PATH = PROJECT_ROOT / "data" / "recovery" / "restore_2026-11-09_from_93cfa87.json"

# The bundle is only applicable to the production database (it references real ESPN game ids).
RESTORE_PROBE_GAME_ID = "ESPN_401909955_2026-11-10_MEM_AT_TOR"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_repair(conn: sqlite3.Connection, migration_id: str, table: str, pk: Any, action: str, details: str) -> None:
    conn.execute(
        """
        INSERT INTO audit_repairs (applied_at, migration_id, table_name, row_pk, action, details)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (_now(), migration_id, table, str(pk), action, details),
    )


def _column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


# ---------------------------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------------------------

def m001_add_odds_source_type(conn: sqlite3.Connection, migration_id: str) -> dict[str, Any]:
    """Legacy databases lack `source_type`. SQLite requires a DEFAULT to add a NOT NULL column, so
    legacy rows get 'OBSERVED' here and fabricated ones are quarantined by m004. New writes must go
    through DatabaseManager.insert_odds_snapshot, which refuses to rely on the default."""
    if "source_type" in _column_names(conn, "odds_snapshots"):
        return {"action": "noop", "reason": "column already present"}
    conn.execute(
        "ALTER TABLE odds_snapshots ADD COLUMN source_type TEXT NOT NULL DEFAULT 'OBSERVED' "
        "CHECK (source_type IN ('OBSERVED', 'DERIVED', 'SYNTHETIC'))"
    )
    return {"action": "column_added"}


def m002_drop_unique_prediction_dedup_index(conn: sqlite3.Connection, migration_id: str) -> dict[str, Any]:
    """The unique index forced the deletion of 164 immutable predictions. Predictions are append-only:
    de-duplication is a query-time concern (latest prediction per game), never a storage constraint."""
    existed = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'idx_predictions_dedup'"
    ).fetchone()
    conn.execute("DROP INDEX IF EXISTS idx_predictions_dedup")
    return {"action": "dropped" if existed else "noop"}


def _insert_row(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> bool:
    cols = [c for c in row.keys() if c in _column_names(conn, table)]
    placeholders = ", ".join("?" for _ in cols)
    sql = f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    return conn.execute(sql, tuple(row[c] for c in cols)).rowcount > 0


def m003_restore_history_from_93cfa87(conn: sqlite3.Connection, migration_id: str) -> dict[str, Any]:
    """
    Restores the audit history lost on 2026-11-09 (commits 75da20e and 61541df replaced the bot's
    database with an older snapshot and deleted 164 predictions). The recovery bundle was generated
    from the bot's last database (commit 93cfa87) by scripts/build_recovery_bundle.py.
    """
    if not conn.execute("SELECT 1 FROM games WHERE game_id = ?", (RESTORE_PROBE_GAME_ID,)).fetchone():
        return {"action": "skipped", "reason": "not the production database (probe game absent)"}
    if not RECOVERY_BUNDLE_PATH.exists():
        raise FileNotFoundError(f"Recovery bundle missing: {RECOVERY_BUNDLE_PATH}")

    raw = RECOVERY_BUNDLE_PATH.read_text(encoding="utf-8")
    bundle = json.loads(raw)
    payload_json = json.dumps(bundle["payload"], sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    if digest != bundle["payload_sha256"]:
        raise ValueError("Recovery bundle checksum mismatch: refusing to restore from a modified bundle")
    payload = bundle["payload"]

    summary: dict[str, Any] = {"bundle_sha256": digest}

    # 1. Re-insert deleted rows (parents first so foreign keys hold).
    pk_by_table = {
        "odds_snapshots": "odds_id",
        "predictions": "prediction_id",
        "simulated_bets": "bet_id",
        "decision_log": "decision_id",
        "player_prop_picks": "prop_id",
        "bankroll_ledger": "entry_id",
    }
    for table in ("odds_snapshots", "predictions", "simulated_bets", "decision_log", "player_prop_picks", "bankroll_ledger"):
        restored = skipped = 0
        pk_col = pk_by_table[table]
        for row in payload["missing_rows"].get(table, []):
            pk = row.get(pk_col)
            try:
                ok = _insert_row(conn, table, row)
                if not ok and table == "bankroll_ledger":
                    # entry_id already reused by a newer entry: keep the historical entry with a new id.
                    clone = {k: v for k, v in row.items() if k != "entry_id"}
                    ok = _insert_row(conn, table, clone)
                    if ok:
                        _log_repair(conn, migration_id, table, pk, "RESTORED_WITH_NEW_ENTRY_ID",
                                    "original entry_id was reused after the deletion")
                        restored += 1
                        continue
            except sqlite3.IntegrityError as exc:
                ok = False
                _log_repair(conn, migration_id, table, pk, "RESTORE_SKIPPED", f"integrity error: {exc}")
            if ok:
                restored += 1
                _log_repair(conn, migration_id, table, pk, "RESTORED_DELETED_ROW",
                            "row deleted on 2026-11-09 restored from bot database 93cfa87")
            else:
                skipped += 1
        summary[f"{table}_restored"] = restored
        summary[f"{table}_skipped"] = skipped

    # 2. Restore results that were rolled back (FINAL -> SCHEDULED).
    games_restored = 0
    for gr in payload.get("game_result_restores", []):
        cur = conn.execute(
            """
            UPDATE games SET status = ?, home_score = ?, away_score = ?, result_recorded_at = ?
            WHERE game_id = ? AND status != 'FINAL'
            """,
            (gr["status"], gr["home_score"], gr["away_score"], gr["result_recorded_at"], gr["game_id"]),
        )
        if cur.rowcount:
            games_restored += 1
            _log_repair(conn, migration_id, "games", gr["game_id"], "RESTORED_FINAL_RESULT",
                        f"result {gr['home_score']}-{gr['away_score']} had been rolled back to SCHEDULED")
    summary["games_results_restored"] = games_restored

    # 3. Restore bet settlements that were rolled back (settled -> PENDING). Allowed by the trigger
    #    because the stored row is PENDING and the original bet parameters are unchanged.
    bets_restored = 0
    for br in payload.get("bet_settlement_restores", []):
        cur = conn.execute(
            """
            UPDATE simulated_bets
            SET status = ?, net_profit_pen = ?, bankroll_after_pen = ?, actual_result_summary = ?, settled_at = ?
            WHERE bet_id = ? AND status = 'PENDING'
            """,
            (br["status"], br["net_profit_pen"], br["bankroll_after_pen"], br["actual_result_summary"],
             br["settled_at"], br["bet_id"]),
        )
        if cur.rowcount:
            bets_restored += 1
            _log_repair(conn, migration_id, "simulated_bets", br["bet_id"], "RESTORED_SETTLEMENT",
                        f"{br['status']} {br['net_profit_pen']:+.4f} PEN had been rolled back to PENDING")
    summary["bet_settlements_restored"] = bets_restored

    # 4. Settled props that were overwritten to VOID cannot be reverted (VOID rows are immutable).
    #    They are documented so reports can exclude them explicitly.
    for pc in payload.get("prop_settlements_overwritten", []):
        _log_repair(conn, migration_id, "player_prop_picks", pc["prop_id"], "DOCUMENTED_OVERWRITTEN_SETTLEMENT",
                    f"original status {pc['original_status']} ({pc['original_net_profit_pen']}) was overwritten "
                    "to VOID on 2026-11-09; unrecoverable under immutability rules (line was never observed)")
    summary["prop_overwrites_documented"] = len(payload.get("prop_settlements_overwritten", []))
    return summary


def m004_quarantine_unobserved_odds(conn: sqlite3.Connection, migration_id: str) -> dict[str, Any]:
    """Quarantines every odds row generated by the system itself (and closing copies of them)."""
    now = _now()
    predicate = UNOBSERVED_PROVIDER_SQL_PREDICATE.format(col="provider")
    candidates = conn.execute(
        f"""
        SELECT odds_id, provider, decimal_odds, counterpart_decimal_odds FROM odds_snapshots
        WHERE odds_id NOT IN (SELECT odds_id FROM quarantined_odds)
          AND (
                {predicate}
             OR source_type != 'OBSERVED'
             OR (provider = 'draftkings' AND decimal_odds = 1.90 AND counterpart_decimal_odds = 1.90)
             OR (provider LIKE 'Pinnacle (Per%' AND decimal_odds = 1.908)
             OR game_id LIKE 'SYN%'
          )
        """
    ).fetchall()
    for r in candidates:
        conn.execute(
            "INSERT OR IGNORE INTO quarantined_odds (odds_id, reason, quarantined_at) VALUES (?, ?, ?)",
            (r[0], f"{migration_id}: unobserved/system-generated quote ({r[1]}, {r[2]}/{r[3]})", now),
        )
    # Closing-line copies inherit the quarantine of their source row.
    copies = conn.execute(
        """
        SELECT c.odds_id, q.odds_id FROM odds_snapshots c
        JOIN quarantined_odds q ON c.odds_id LIKE q.odds_id || '_CLOSE%'
        WHERE c.is_closing_line = 1 AND c.odds_id NOT IN (SELECT odds_id FROM quarantined_odds)
        """
    ).fetchall()
    for c_id, src_id in copies:
        conn.execute(
            "INSERT OR IGNORE INTO quarantined_odds (odds_id, reason, quarantined_at) VALUES (?, ?, ?)",
            (c_id, f"{migration_id}: closing copy of quarantined quote {src_id}", now),
        )
    return {"quarantined_quotes": len(candidates), "quarantined_closing_copies": len(copies)}


def m005_invalidate_pending_unobserved_props(conn: sqlite3.Connection, migration_id: str) -> dict[str, Any]:
    """
    Player props were always priced against system-generated lines (the odds schema cannot even store
    a 'player_prop' market). Pending props are invalidated (VOID, zero P&L) so they are never settled
    against invented prices. Settled props are left untouched (immutable) and excluded from metrics.
    """
    rows = conn.execute("SELECT prop_id FROM player_prop_picks WHERE status = 'PENDING'").fetchall()
    for (prop_id,) in rows:
        conn.execute(
            """
            UPDATE player_prop_picks
            SET status = 'VOID', net_profit_pen = 0.0, actual_result_summary = ?, settled_at = ?
            WHERE prop_id = ? AND status = 'PENDING'
            """,
            ("INVALIDATED_UNOBSERVED_LINE: line/price was never observed in a real market", _now(), prop_id),
        )
        _log_repair(conn, migration_id, "player_prop_picks", prop_id, "INVALIDATED_PENDING_PROP",
                    "pending prop priced on a system-generated line")
    return {"props_invalidated": len(rows)}




def m006_add_sub_bankroll_and_parlays(conn: sqlite3.Connection, migration_id: str) -> dict[str, Any]:
    """
    Creates isolated sub-bankroll tables for combined bets (SGP & high-probability parlays).
    Initializes a dedicated S/50.00 PEN virtual sub-bankroll with its own append-only ledger,
    keeping multi-leg parlay testing completely isolated from the audited Phase 0 main bankroll.
    """
    now = _now()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS parlay_bets (
            parlay_id TEXT PRIMARY KEY,
            matchday_date TEXT NOT NULL,
            strategy_type TEXT NOT NULL CHECK (strategy_type IN ('SGP_COPULA', 'HIGH_PROB_PARLAY', 'CROSS_GAME_PARLAY')),
            legs_json TEXT NOT NULL,
            num_legs INTEGER NOT NULL CHECK (num_legs >= 2),
            compound_odds REAL NOT NULL CHECK (compound_odds > 1.0),
            joint_prob REAL NOT NULL CHECK (joint_prob > 0.0 AND joint_prob <= 1.0),
            compound_ev_pct REAL NOT NULL,
            stake_pen REAL NOT NULL CHECK (stake_pen > 0.0 AND stake_pen <= 25.0),
            emitted_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'WON', 'LOST', 'PUSH', 'VOID')),
            net_profit_pen REAL,
            bankroll_after_pen REAL,
            actual_result_summary TEXT,
            settled_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS prevent_settled_parlay_tampering
        BEFORE UPDATE ON parlay_bets
        BEGIN
            SELECT CASE
                WHEN OLD.status != 'PENDING' THEN
                    RAISE(ABORT, 'DOUBLE_SETTLEMENT_OR_TAMPERING: Parlay bet has already been settled and is immutable.')
                WHEN NEW.compound_odds != OLD.compound_odds
                  OR NEW.stake_pen != OLD.stake_pen
                  OR NEW.legs_json != OLD.legs_json
                  OR NEW.emitted_at != OLD.emitted_at
                  OR NEW.strategy_type != OLD.strategy_type THEN
                    RAISE(ABORT, 'IMMUTABLE_VIOLATION: Original parlay parameters cannot be modified.')
            END;
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS prevent_parlay_delete
        BEFORE DELETE ON parlay_bets
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Parlay bets cannot be deleted from audit history.');
        END
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS parlay_bankroll_ledger (
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN ('INITIAL_VIRTUAL_BANKROLL', 'BET_RESERVED', 'BET_SETTLED')),
            reference_parlay_id TEXT,
            amount_delta_pen REAL NOT NULL,
            settled_bankroll_pen REAL NOT NULL CHECK (settled_bankroll_pen >= 0.0),
            pending_exposure_pen REAL NOT NULL CHECK (pending_exposure_pen >= 0.0),
            available_balance_pen REAL NOT NULL CHECK (available_balance_pen >= 0.0)
        )
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS prevent_parlay_ledger_update
        BEFORE UPDATE ON parlay_bankroll_ledger
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: parlay_bankroll_ledger entries cannot be updated.');
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS prevent_parlay_ledger_delete
        BEFORE DELETE ON parlay_bankroll_ledger
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: parlay_bankroll_ledger entries cannot be deleted.');
        END
        """
    )

    seeded = False
    existing = conn.execute("SELECT COUNT(*) FROM parlay_bankroll_ledger").fetchone()
    if not existing or existing[0] == 0:
        conn.execute(
            """
            INSERT INTO parlay_bankroll_ledger (
                timestamp, event_type, reference_parlay_id, amount_delta_pen,
                settled_bankroll_pen, pending_exposure_pen, available_balance_pen
            ) VALUES (?, 'INITIAL_VIRTUAL_BANKROLL', NULL, 50.0, 50.0, 0.0, 50.0)
            """,
            (now,),
        )
        seeded = True

    return {"action": "tables_created", "initial_bankroll_seeded": seeded, "initial_amount_pen": 50.0}




def m007_invalidate_hardcoded_parlays(conn: sqlite3.Connection, migration_id: str) -> dict[str, Any]:
    """
    Invalidates pending parlay bets created with hardcoded placeholder odds (1.70/1.85).
    Marks them VOID (0.0 net profit), refunds their exposure in the parlay ledger, and logs
    the repair in audit_repairs.
    """
    now = _now()
    if "parlay_bets" not in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
        return {"action": "skipped", "reason": "parlay_bets table does not exist"}

    rows = conn.execute(
        """
        SELECT parlay_id, stake_pen, legs_json
        FROM parlay_bets
        WHERE status = 'PENDING'
          AND (legs_json LIKE '%"odds": 1.7%' OR legs_json LIKE '%"odds": 1.85%')
        """
    ).fetchall()

    if not rows:
        return {"action": "noop", "invalidated_count": 0}

    last_ledger = conn.execute(
        "SELECT settled_bankroll_pen, pending_exposure_pen FROM parlay_bankroll_ledger ORDER BY entry_id DESC LIMIT 1"
    ).fetchone()
    curr_settled = float(last_ledger[0]) if last_ledger else 50.0
    curr_exposure = float(last_ledger[1]) if last_ledger else 0.0

    invalidated = 0
    for parlay_id, stake_pen, _ in rows:
        stake = float(stake_pen)
        curr_exposure = max(0.0, round(curr_exposure - stake, 2))
        curr_avail = round(curr_settled - curr_exposure, 2)

        conn.execute(
            """
            UPDATE parlay_bets
            SET status = 'VOID', net_profit_pen = 0.0, bankroll_after_pen = ?,
                actual_result_summary = ?, settled_at = ?
            WHERE parlay_id = ? AND status = 'PENDING'
            """,
            (
                curr_settled,
                "INVALIDATED_HARDCODED_ODDS: Parlay candidate created with fabricated placeholder leg odds (1.70/1.85)",
                now,
                parlay_id,
            ),
        )

        conn.execute(
            """
            INSERT INTO parlay_bankroll_ledger (
                timestamp, event_type, reference_parlay_id, amount_delta_pen,
                settled_bankroll_pen, pending_exposure_pen, available_balance_pen
            ) VALUES (?, 'BET_SETTLED', ?, 0.0, ?, ?, ?)
            """,
            (now, parlay_id, curr_settled, curr_exposure, curr_avail),
        )

        _log_repair(
            conn,
            migration_id,
            "parlay_bets",
            parlay_id,
            "INVALIDATED_HARDCODED_PARLAY",
            f"pending parlay with hardcoded leg odds (1.70/1.85) staked {stake:.2f} PEN refunded to available balance",
        )
        invalidated += 1

    return {
        "invalidated_count": invalidated,
        "final_exposure_pen": curr_exposure,
        "final_available_pen": curr_settled - curr_exposure,
    }

MIGRATIONS: list[tuple[str, Callable[[sqlite3.Connection, str], dict[str, Any]]]] = [
    ("2026_11_09_001_add_odds_source_type", m001_add_odds_source_type),
    ("2026_11_09_002_drop_unique_prediction_dedup_index", m002_drop_unique_prediction_dedup_index),
    ("2026_11_09_003_restore_history_from_93cfa87", m003_restore_history_from_93cfa87),
    ("2026_11_09_004_quarantine_unobserved_odds", m004_quarantine_unobserved_odds),
    ("2026_11_09_005_invalidate_pending_unobserved_props", m005_invalidate_pending_unobserved_props),
    ("2026_11_09_006_add_sub_bankroll_and_parlays", m006_add_sub_bankroll_and_parlays),
    ("2026_11_09_007_invalidate_hardcoded_parlays", m007_invalidate_hardcoded_parlays),
]


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Applies pending migrations in order inside the caller's transaction. Returns applied ids."""
    applied_now: list[str] = []
    done = {r[0] for r in conn.execute("SELECT migration_id FROM schema_migrations").fetchall()}
    for migration_id, fn in MIGRATIONS:
        if migration_id in done:
            continue
        details = fn(conn, migration_id)
        conn.execute(
            "INSERT INTO schema_migrations (migration_id, applied_at, details_json) VALUES (?, ?, ?)",
            (migration_id, _now(), json.dumps(details, ensure_ascii=False, sort_keys=True)),
        )
        logger.info("Applied migration %s: %s", migration_id, details)
        applied_now.append(migration_id)
    return applied_now
