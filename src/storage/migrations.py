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
import json
import logging
import sqlite3
from typing import Any

from src.validation.odds_integrity import find_copied_live_quotes
from src.storage.migrations_v1 import (
    RECOVERY_BUNDLE_PATH,
    RESTORE_PROBE_GAME_ID,
    _log_repair,
    _now,
    m001_add_odds_source_type,
    m002_drop_unique_prediction_dedup_index,
    m003_restore_history_from_93cfa87,
    m004_quarantine_unobserved_odds,
    m005_invalidate_pending_unobserved_props,
    m006_add_sub_bankroll_and_parlays,
    m007_invalidate_hardcoded_parlays,
    m008_quarantine_legacy_synthetic_bets,
    m009_enforce_observed_games_view,
)

__all__ = [
    "MIGRATIONS",
    "RECOVERY_BUNDLE_PATH",
    "RESTORE_PROBE_GAME_ID",
    "m001_add_odds_source_type",
    "m002_drop_unique_prediction_dedup_index",
    "m003_restore_history_from_93cfa87",
    "m004_quarantine_unobserved_odds",
    "m005_invalidate_pending_unobserved_props",
    "m006_add_sub_bankroll_and_parlays",
    "m007_invalidate_hardcoded_parlays",
    "m008_quarantine_legacy_synthetic_bets",
    "m009_enforce_observed_games_view",
    "m010_allow_player_prop_in_odds_snapshots",
    "m011_reconcile_observed_ledger_and_player_boxscores",
    "m012_separate_prob_semantics_spread_and_manifests",
    "m013_add_shadow_candidates_and_version_indexes",
    "run_migrations",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------------------------
# Migrations (010+)
# ---------------------------------------------------------------------------------------------


def m010_allow_player_prop_in_odds_snapshots(conn: sqlite3.Connection, migration_id: str) -> dict[str, Any]:
    """
    Upgrades legacy `odds_snapshots` tables whose CHECK constraint only permitted
    ('moneyline', 'total_points') so real observed 'player_prop' lines from Peruvian
    sportsbooks persist cleanly without changing any historical rows.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'odds_snapshots'"
    ).fetchone()
    if not row or "player_prop" in str(row[0]):
        return {"action": "noop", "reason": "player_prop already permitted"}

    before_cnt = int(conn.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0])

    # SQLite validates every view in the schema during ALTER TABLE ... RENAME TO; drop views
    # before renaming and recreate canonical VIEW_DDL right after (safe both with m008 & standalone).
    existing_views = [
        (str(r[0]), str(r[1]))
        for r in conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'view'").fetchall()
        if r[0] and r[1]
    ]
    for v_name, _ in existing_views:
        conn.execute(f'DROP VIEW IF EXISTS "{v_name}"')

    conn.execute("DROP TRIGGER IF EXISTS prevent_odds_update")
    conn.execute("DROP TRIGGER IF EXISTS prevent_odds_delete")
    conn.execute("DROP TABLE IF EXISTS odds_snapshots_v10")

    conn.execute(
        """
        CREATE TABLE odds_snapshots_v10 (
            odds_id TEXT PRIMARY KEY,
            game_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            market TEXT NOT NULL CHECK (market IN ('moneyline', 'total_points', 'player_prop')),
            selection TEXT NOT NULL CHECK (selection IN ('HOME', 'AWAY', 'OVER', 'UNDER')),
            line_value REAL,
            decimal_odds REAL NOT NULL CHECK (decimal_odds > 1.0),
            counterpart_decimal_odds REAL CHECK (counterpart_decimal_odds IS NULL OR counterpart_decimal_odds > 1.0),
            captured_at TEXT NOT NULL,
            is_closing_line INTEGER NOT NULL DEFAULT 0,
            source_type TEXT NOT NULL CHECK (source_type IN ('OBSERVED', 'DERIVED', 'SYNTHETIC')),
            FOREIGN KEY (game_id) REFERENCES games(game_id)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO odds_snapshots_v10 (
            odds_id, game_id, provider, market, selection, line_value,
            decimal_odds, counterpart_decimal_odds, captured_at, is_closing_line, source_type
        )
        SELECT
            odds_id, game_id, provider, market, selection, line_value,
            decimal_odds, counterpart_decimal_odds, captured_at, is_closing_line,
            COALESCE(source_type, 'OBSERVED')
        FROM odds_snapshots
        """
    )
    after_cnt = int(conn.execute("SELECT COUNT(*) FROM odds_snapshots_v10").fetchone()[0])
    if after_cnt != before_cnt:
        raise RuntimeError(f"m010 row count mismatch: before={before_cnt}, after={after_cnt}")

    conn.execute("DROP TABLE odds_snapshots")
    conn.execute("ALTER TABLE odds_snapshots_v10 RENAME TO odds_snapshots")

    from src.storage.schema import VIEW_DDL

    for ddl in VIEW_DDL.values():
        conn.execute(ddl)
    for v_name, v_sql in existing_views:
        if v_name not in VIEW_DDL:
            conn.execute(v_sql)
    conn.execute(
        """
        CREATE TRIGGER prevent_odds_update
        BEFORE UPDATE ON odds_snapshots
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Captured odds snapshots cannot be modified.');
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER prevent_odds_delete
        BEFORE DELETE ON odds_snapshots
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Captured odds snapshots cannot be deleted.');
        END
        """
    )

    _log_repair(
        conn,
        migration_id,
        "odds_snapshots",
        "SCHEMA_CHECK_UPGRADE",
        "ALLOW_PLAYER_PROP_MARKET",
        f"Upgraded odds_snapshots CHECK constraint to allow player_prop while preserving all {after_cnt} rows.",
    )
    return {"action": "upgraded", "rows_preserved": after_cnt}


def m011_reconcile_observed_ledger_and_player_boxscores(
    conn: sqlite3.Connection, migration_id: str
) -> dict[str, Any]:
    """
    1. Rebuilds `v_observed_bankroll_ledger` cleanly so non-observed derived bets (e.g. legacy
       `[T-6H Peru]`) are excluded and running settled balances match `v_observed_simulated_bets`.
    2. Populates the normalized `player_boxscores` table from all existing historical
       `game_boxscores` rows so player prop projections run without JSON scans or leakage.
    """
    from src.ingestion.boxscores import upsert_player_boxscores_rows
    from src.storage.schema import VIEW_DDL

    conn.execute("DROP VIEW IF EXISTS v_observed_bankroll_ledger")
    conn.execute(VIEW_DDL["v_observed_bankroll_ledger"])

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS player_boxscores (
            game_id TEXT NOT NULL,
            player_name TEXT NOT NULL,
            player_key TEXT NOT NULL,
            team TEXT NOT NULL,
            game_start_time TEXT NOT NULL,
            minutes REAL NOT NULL,
            pts REAL NOT NULL,
            reb REAL NOT NULL,
            ast REAL NOT NULL,
            threed REAL NOT NULL,
            starter INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (game_id, team, player_key),
            FOREIGN KEY (game_id) REFERENCES games(game_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_player_boxscores_lookup ON player_boxscores (player_key, game_start_time DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_player_boxscores_team ON player_boxscores (team, game_start_time DESC)"
    )

    rows = conn.execute(
        """
        SELECT gb.game_id, gb.players_json, g.game_start_time
        FROM game_boxscores gb
        JOIN games g ON gb.game_id = g.game_id
        WHERE g.game_id NOT LIKE 'SYN%'
          AND length(COALESCE(gb.players_json, '')) > 2
        """
    ).fetchall()

    games_processed = 0
    player_rows_upserted = 0
    for gid, players_raw, game_start_time in rows:
        try:
            parsed = json.loads(players_raw)
        except Exception:
            continue
        cnt = upsert_player_boxscores_rows(conn, str(gid), str(game_start_time), parsed)
        if cnt:
            games_processed += 1
            player_rows_upserted += cnt

    _log_repair(
        conn,
        migration_id,
        "player_boxscores",
        "SCHEMA_AND_VIEW_UPGRADE",
        "RECONCILE_OBSERVED_LEDGER_AND_POPULATE_PLAYER_BOXSCORES",
        f"Reconciled v_observed_bankroll_ledger and backfilled {player_rows_upserted} player boxscore rows across {games_processed} games.",
    )
    return {
        "status": "APPLIED",
        "games_processed": games_processed,
        "player_rows_upserted": player_rows_upserted,
    }


def m012_separate_prob_semantics_spread_and_manifests(
    conn: sqlite3.Connection, migration_id: str
) -> dict[str, Any]:
    """
    Audited Schema Migration m012 (F-008, F-010, F-017):
    1. Allows 'spread' market in `odds_snapshots`, `model_versions`, `predictions`, and `simulated_bets`.
    2. Adds explicit immutable probability semantics to `predictions`:
       - `raw_model_probability`
       - `calibrated_model_probability` (left NULL for pre-m012 legacy rows whose `calibrated_probability` mixed market anchoring)
       - `market_fair_probability`
       - `market_anchored_probability`
       - `run_manifest_id`
    3. Ensures `run_manifests` append-only table exists for full run reproducibility.
    Preserves 100% of historical rows and verifies exact row counts before & after.
    """
    from src.storage.schema import VIEW_DDL

    odds_sql = str((conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='odds_snapshots'").fetchone() or [""])[0])
    mv_sql = str((conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='model_versions'").fetchone() or [""])[0])
    pred_sql = str((conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='predictions'").fetchone() or [""])[0])
    bet_sql = str((conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='simulated_bets'").fetchone() or [""])[0])

    needs_upgrade = (
        "'spread'" not in odds_sql
        or "'spread'" not in mv_sql
        or "'spread'" not in pred_sql
        or "'spread'" not in bet_sql
        or "calibrated_model_probability" not in pred_sql
        or "run_manifest_id" not in pred_sql
    )
    if not needs_upgrade:
        return {"action": "noop", "reason": "m012 schema already up to date"}

    existing_views = [
        (str(r[0]), str(r[1]))
        for r in conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'view'").fetchall()
        if r[0] and r[1]
    ]
    for v_name, _ in existing_views:
        conn.execute(f'DROP VIEW IF EXISTS "{v_name}"')

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_manifests (
            run_id TEXT PRIMARY KEY,
            commit_sha TEXT NOT NULL,
            model_version_id TEXT NOT NULL,
            ensemble_version TEXT NOT NULL,
            submodel_versions_json TEXT NOT NULL,
            config_hash TEXT NOT NULL,
            config_version TEXT NOT NULL,
            calibrator_metadata_json TEXT NOT NULL,
            seeds_json TEXT NOT NULL,
            data_cutoff_utc TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS prevent_run_manifest_update
        BEFORE UPDATE ON run_manifests
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: run_manifests is append-only.');
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS prevent_run_manifest_delete
        BEFORE DELETE ON run_manifests
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: run_manifests cannot be deleted.');
        END
        """
    )

    bet_before = int(conn.execute("SELECT COUNT(*) FROM simulated_bets").fetchone()[0])
    pred_before = int(conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0])
    mv_before = int(conn.execute("SELECT COUNT(*) FROM model_versions").fetchone()[0])
    odds_before = int(conn.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0])

    # 1. Stage simulated_bets rows into flat table & drop child table before parent tables
    conn.execute("DROP TRIGGER IF EXISTS prevent_settled_bet_tampering")
    conn.execute("DROP TRIGGER IF EXISTS prevent_bet_delete")
    conn.execute("DROP TABLE IF EXISTS _m012_bets_stage")
    conn.execute("CREATE TABLE _m012_bets_stage AS SELECT * FROM simulated_bets")
    bet_staged = int(conn.execute("SELECT COUNT(*) FROM _m012_bets_stage").fetchone()[0])
    if bet_staged != bet_before:
        raise RuntimeError(f"m012 simulated_bets stage count mismatch: before={bet_before}, staged={bet_staged}")
    conn.execute("DROP TABLE simulated_bets")

    # 2. Stage predictions rows into flat table & drop predictions before upgrading model_versions
    conn.execute("DROP TRIGGER IF EXISTS prevent_prediction_update")
    conn.execute("DROP TRIGGER IF EXISTS prevent_prediction_delete")
    conn.execute("DROP INDEX IF EXISTS idx_predictions_lookup")
    conn.execute("DROP TABLE IF EXISTS _m012_preds_stage")
    existing_pred_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(predictions)").fetchall()}
    raw_m_expr = "raw_model_probability" if "raw_model_probability" in existing_pred_cols else "raw_probability"
    cal_m_expr = "calibrated_model_probability" if "calibrated_model_probability" in existing_pred_cols else "NULL"
    mkt_f_expr = "market_fair_probability" if "market_fair_probability" in existing_pred_cols else "implied_prob_fair"
    mkt_a_expr = "market_anchored_probability" if "market_anchored_probability" in existing_pred_cols else "calibrated_probability"
    run_m_expr = "run_manifest_id" if "run_manifest_id" in existing_pred_cols else "NULL"
    conn.execute(
        f"""
        CREATE TABLE _m012_preds_stage AS
        SELECT
            prediction_id, game_id, market, selection, line_value, model_version_id,
            raw_probability, calibrated_probability,
            {raw_m_expr} AS raw_model_probability,
            {cal_m_expr} AS calibrated_model_probability,
            {mkt_f_expr} AS market_fair_probability,
            {mkt_a_expr} AS market_anchored_probability,
            {run_m_expr} AS run_manifest_id,
            uncertainty_std, implied_prob_gross, implied_prob_fair, bookmaker_overround,
            decimal_odds_used, odds_provider, odds_captured_at, ev_unit, ev_pct,
            emitted_at, features_snapshot_json
        FROM predictions
        """
    )
    pred_staged = int(conn.execute("SELECT COUNT(*) FROM _m012_preds_stage").fetchone()[0])
    if pred_staged != pred_before:
        raise RuntimeError(f"m012 predictions stage count mismatch: before={pred_before}, staged={pred_staged}")
    conn.execute("DROP TABLE predictions")

    # 3. Upgrade model_versions ('spread' market permitted)
    conn.execute("DROP TABLE IF EXISTS model_versions_v12")
    conn.execute(
        """
        CREATE TABLE model_versions_v12 (
            model_version_id TEXT PRIMARY KEY,
            model_family TEXT NOT NULL,
            market TEXT NOT NULL CHECK (market IN ('moneyline', 'total_points', 'spread', 'player_prop')),
            train_start_date TEXT NOT NULL,
            train_end_date TEXT NOT NULL,
            trained_at TEXT NOT NULL,
            hyperparameters_json TEXT NOT NULL,
            oos_brier_score REAL,
            oos_log_loss REAL,
            is_active INTEGER NOT NULL DEFAULT 0,
            approved_by TEXT NOT NULL,
            parent_version_id TEXT
        )
        """
    )
    conn.execute("INSERT INTO model_versions_v12 SELECT * FROM model_versions")
    mv_after = int(conn.execute("SELECT COUNT(*) FROM model_versions_v12").fetchone()[0])
    if mv_after != mv_before:
        raise RuntimeError(f"m012 model_versions count mismatch: before={mv_before}, after={mv_after}")
    conn.execute("DROP TABLE model_versions")
    conn.execute("ALTER TABLE model_versions_v12 RENAME TO model_versions")

    # 4. Recreate predictions with FKs pointing at upgraded model_versions + restore triggers/index
    conn.execute(
        """
        CREATE TABLE predictions (
            prediction_id TEXT PRIMARY KEY,
            game_id TEXT NOT NULL,
            market TEXT NOT NULL CHECK (market IN ('moneyline', 'total_points', 'spread', 'player_prop')),
            selection TEXT NOT NULL CHECK (selection IN ('HOME', 'AWAY', 'OVER', 'UNDER')),
            line_value REAL,
            model_version_id TEXT NOT NULL,
            raw_probability REAL NOT NULL CHECK (raw_probability >= 0.0 AND raw_probability <= 1.0),
            calibrated_probability REAL NOT NULL CHECK (calibrated_probability >= 0.0 AND calibrated_probability <= 1.0),
            raw_model_probability REAL CHECK (raw_model_probability IS NULL OR (raw_model_probability >= 0.0 AND raw_model_probability <= 1.0)),
            calibrated_model_probability REAL CHECK (calibrated_model_probability IS NULL OR (calibrated_model_probability >= 0.0 AND calibrated_model_probability <= 1.0)),
            market_fair_probability REAL CHECK (market_fair_probability IS NULL OR (market_fair_probability >= 0.0 AND market_fair_probability <= 1.0)),
            market_anchored_probability REAL CHECK (market_anchored_probability IS NULL OR (market_anchored_probability >= 0.0 AND market_anchored_probability <= 1.0)),
            run_manifest_id TEXT,
            uncertainty_std REAL NOT NULL CHECK (uncertainty_std >= 0.0),
            implied_prob_gross REAL NOT NULL,
            implied_prob_fair REAL,
            bookmaker_overround REAL,
            decimal_odds_used REAL NOT NULL CHECK (decimal_odds_used > 1.0),
            odds_provider TEXT NOT NULL,
            odds_captured_at TEXT NOT NULL,
            ev_unit REAL NOT NULL,
            ev_pct REAL NOT NULL,
            emitted_at TEXT NOT NULL,
            features_snapshot_json TEXT NOT NULL,
            FOREIGN KEY (game_id) REFERENCES games(game_id),
            FOREIGN KEY (model_version_id) REFERENCES model_versions(model_version_id)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO predictions (
            prediction_id, game_id, market, selection, line_value, model_version_id,
            raw_probability, calibrated_probability,
            raw_model_probability, calibrated_model_probability,
            market_fair_probability, market_anchored_probability, run_manifest_id,
            uncertainty_std, implied_prob_gross, implied_prob_fair, bookmaker_overround,
            decimal_odds_used, odds_provider, odds_captured_at, ev_unit, ev_pct,
            emitted_at, features_snapshot_json
        )
        SELECT
            prediction_id, game_id, market, selection, line_value, model_version_id,
            raw_probability, calibrated_probability,
            raw_model_probability, calibrated_model_probability,
            market_fair_probability, market_anchored_probability, run_manifest_id,
            uncertainty_std, implied_prob_gross, implied_prob_fair, bookmaker_overround,
            decimal_odds_used, odds_provider, odds_captured_at, ev_unit, ev_pct,
            emitted_at, features_snapshot_json
        FROM _m012_preds_stage
        """
    )
    pred_after = int(conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0])
    if pred_after != pred_before:
        raise RuntimeError(f"m012 predictions count mismatch: before={pred_before}, after={pred_after}")
    conn.execute("DROP TABLE _m012_preds_stage")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_predictions_lookup ON predictions (game_id, market, selection, model_version_id, emitted_at)"
    )
    conn.execute(
        """
        CREATE TRIGGER prevent_prediction_update
        BEFORE UPDATE ON predictions
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Historical predictions cannot be modified.');
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER prevent_prediction_delete
        BEFORE DELETE ON predictions
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Historical predictions cannot be deleted.');
        END
        """
    )

    # 5. Recreate simulated_bets with FKs pointing at upgraded predictions + restore triggers
    conn.execute(
        """
        CREATE TABLE simulated_bets (
            bet_id TEXT PRIMARY KEY,
            prediction_id TEXT NOT NULL UNIQUE,
            game_id TEXT NOT NULL,
            matchday_date TEXT NOT NULL,
            market TEXT NOT NULL CHECK (market IN ('moneyline', 'total_points', 'spread', 'player_prop')),
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
        )
        """
    )
    conn.execute("INSERT INTO simulated_bets SELECT * FROM _m012_bets_stage")
    bet_after = int(conn.execute("SELECT COUNT(*) FROM simulated_bets").fetchone()[0])
    if bet_after != bet_before:
        raise RuntimeError(f"m012 simulated_bets count mismatch: before={bet_before}, after={bet_after}")
    conn.execute("DROP TABLE _m012_bets_stage")
    conn.execute(
        """
        CREATE TRIGGER prevent_settled_bet_tampering
        BEFORE UPDATE ON simulated_bets
        BEGIN
            SELECT CASE
                WHEN OLD.status != 'PENDING' THEN
                    RAISE(ABORT, 'DOUBLE_SETTLEMENT_OR_TAMPERING: Bet has already been settled and is immutable.')
                WHEN NEW.decimal_odds != OLD.decimal_odds
                  OR NEW.stake_pen != OLD.stake_pen
                  OR NEW.selection != OLD.selection
                  OR COALESCE(NEW.line_value, -9999) != COALESCE(OLD.line_value, -9999)
                  OR NEW.prediction_id != OLD.prediction_id
                  OR NEW.emitted_at != OLD.emitted_at
                  OR NEW.estimated_prob != OLD.estimated_prob
                  OR NEW.estimated_ev != OLD.estimated_ev THEN
                    RAISE(ABORT, 'IMMUTABLE_VIOLATION: Original bet parameters and odds cannot be modified.')
            END;
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER prevent_bet_delete
        BEFORE DELETE ON simulated_bets
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Simulated bets cannot be deleted from audit history.');
        END
        """
    )

    # 6. Upgrade odds_snapshots ('spread' market permitted)
    conn.execute("DROP TRIGGER IF EXISTS prevent_odds_update")
    conn.execute("DROP TRIGGER IF EXISTS prevent_odds_delete")
    conn.execute("DROP TABLE IF EXISTS odds_snapshots_v12")
    conn.execute(
        """
        CREATE TABLE odds_snapshots_v12 (
            odds_id TEXT PRIMARY KEY,
            game_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            market TEXT NOT NULL CHECK (market IN ('moneyline', 'total_points', 'spread', 'player_prop')),
            selection TEXT NOT NULL CHECK (selection IN ('HOME', 'AWAY', 'OVER', 'UNDER')),
            line_value REAL,
            decimal_odds REAL NOT NULL CHECK (decimal_odds > 1.0),
            counterpart_decimal_odds REAL CHECK (counterpart_decimal_odds IS NULL OR counterpart_decimal_odds > 1.0),
            captured_at TEXT NOT NULL,
            is_closing_line INTEGER NOT NULL DEFAULT 0,
            source_type TEXT NOT NULL CHECK (source_type IN ('OBSERVED', 'DERIVED', 'SYNTHETIC')),
            FOREIGN KEY (game_id) REFERENCES games(game_id)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO odds_snapshots_v12 (
            odds_id, game_id, provider, market, selection, line_value,
            decimal_odds, counterpart_decimal_odds, captured_at, is_closing_line, source_type
        )
        SELECT
            odds_id, game_id, provider, market, selection, line_value,
            decimal_odds, counterpart_decimal_odds, captured_at, is_closing_line,
            COALESCE(source_type, 'OBSERVED')
        FROM odds_snapshots
        """
    )
    odds_after = int(conn.execute("SELECT COUNT(*) FROM odds_snapshots_v12").fetchone()[0])
    if odds_after != odds_before:
        raise RuntimeError(f"m012 odds_snapshots count mismatch: before={odds_before}, after={odds_after}")
    conn.execute("DROP TABLE odds_snapshots")
    conn.execute("ALTER TABLE odds_snapshots_v12 RENAME TO odds_snapshots")
    conn.execute(
        """
        CREATE TRIGGER prevent_odds_update
        BEFORE UPDATE ON odds_snapshots
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Captured odds snapshots cannot be modified.');
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER prevent_odds_delete
        BEFORE DELETE ON odds_snapshots
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Captured odds snapshots cannot be deleted.');
        END
        """
    )

    # 7. Recreate views
    for ddl in VIEW_DDL.values():
        conn.execute(ddl)
    for v_name, v_sql in existing_views:
        if v_name not in VIEW_DDL:
            conn.execute(v_sql)

    _log_repair(
        conn,
        migration_id,
        "predictions",
        "SCHEMA_AND_PROB_SEMANTICS_UPGRADE",
        "SEPARATE_PROBS_ALLOW_SPREAD_ADD_RUN_MANIFESTS",
        (
            f"Upgraded CHECK constraints to allow 'spread', separated probability columns on "
            f"{pred_after} predictions, created run_manifests (odds={odds_after}, bets={bet_after}, mv={mv_after})."
        ),
    )
    return {
        "action": "upgraded",
        "odds_snapshots_rows": odds_after,
        "model_versions_rows": mv_after,
        "predictions_rows": pred_after,
        "simulated_bets_rows": bet_after,
    }


def m013_add_shadow_candidates_and_version_indexes(
    conn: sqlite3.Connection,
    migration_id: str,
) -> dict[str, Any]:
    """
    Creates the immutable `shadow_candidates` ledger (for recording +EV signals blocked only by
    Kelly floor / daily bet cap / EV threshold without contaminating the official S/100 ledger)
    and adds model_version_id / shadow lookup indexes.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shadow_candidates (
            shadow_id TEXT PRIMARY KEY,
            prediction_id TEXT,
            game_id TEXT NOT NULL,
            matchday_date TEXT NOT NULL,
            market TEXT NOT NULL CHECK (market IN ('moneyline', 'total_points', 'spread')),
            selection TEXT NOT NULL,
            line_value REAL,
            model_version_id TEXT NOT NULL,
            odds_provider TEXT NOT NULL,
            decimal_odds REAL NOT NULL CHECK (decimal_odds > 1.0),
            raw_probability REAL NOT NULL,
            calibrated_probability REAL NOT NULL,
            ev_unit REAL NOT NULL,
            ev_pct REAL NOT NULL,
            hypothetical_kelly_stake_pen REAL NOT NULL CHECK (hypothetical_kelly_stake_pen >= 0.0),
            decision_status TEXT NOT NULL,
            rejection_reason TEXT NOT NULL,
            closing_decimal_odds REAL,
            closing_fair_prob REAL,
            clv_pct REAL,
            status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'WON', 'LOST', 'PUSH', 'VOID')),
            hypothetical_unit_profit REAL,
            emitted_at TEXT NOT NULL,
            settled_at TEXT,
            source_type TEXT NOT NULL DEFAULT 'OBSERVED' CHECK (source_type = 'OBSERVED'),
            FOREIGN KEY (game_id) REFERENCES games(game_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS prevent_settled_shadow_tampering
        BEFORE UPDATE ON shadow_candidates
        BEGIN
            SELECT CASE
                WHEN OLD.status != 'PENDING' THEN
                    RAISE(ABORT, 'DOUBLE_SETTLEMENT_OR_TAMPERING: Shadow candidate has already been settled and is immutable.')
                WHEN NEW.decimal_odds != OLD.decimal_odds
                  OR NEW.calibrated_probability != OLD.calibrated_probability
                  OR NEW.ev_unit != OLD.ev_unit
                  OR NEW.emitted_at != OLD.emitted_at
                  OR NEW.market != OLD.market
                  OR NEW.selection != OLD.selection THEN
                    RAISE(ABORT, 'IMMUTABLE_VIOLATION: Original shadow candidate parameters cannot be modified.')
            END;
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS prevent_shadow_delete
        BEFORE DELETE ON shadow_candidates
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Shadow candidates cannot be deleted from audit history.');
        END
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_predictions_version_market ON predictions (model_version_id, market, game_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shadow_candidates_game_status ON shadow_candidates (game_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shadow_candidates_matchday ON shadow_candidates (matchday_date, model_version_id)"
    )
    _log_repair(
        conn,
        migration_id,
        "shadow_candidates",
        "SHADOW_LEDGER_INIT",
        "CREATE_SHADOW_CANDIDATES_LEDGER",
        "Created immutable shadow_candidates table and model_version_id/shadow query indexes.",
    )
    return {"action": "shadow_candidates_created", "indexes_created": 3}


def m014_quarantine_misattributed_same_pair_quotes(
    conn: sqlite3.Connection,
    migration_id: str,
) -> dict[str, Any]:
    """
    Quarantines live-API quotes that were attached to two different games of the same two teams.

    Until 2026-11-16 the live book feeds were matched to games by team pair only, so when the same
    teams met on consecutive days (e.g. POR@MIN on 11-17 and 11-18) one game's quotes were stored on
    both games. The copies are identical (provider, capture second, market, side, line, price), and it
    cannot be told afterwards which game a quote really belonged to, so every copy is quarantined.
    Quotes are never deleted or edited; predictions that used them stay in history and are counted.
    """
    rows = [(odds_id,) for odds_id in find_copied_live_quotes(conn)]
    already = {str(r[0]) for r in conn.execute("SELECT odds_id FROM quarantined_odds").fetchall()}
    now = _now()
    quarantined = 0
    for (odds_id,) in rows:
        if str(odds_id) in already:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO quarantined_odds (odds_id, reason, quarantined_at) VALUES (?, ?, ?)",
            (odds_id, "MISATTRIBUTED_SAME_TEAM_PAIR_GAME", now),
        )
        quarantined += 1
    affected_predictions = 0
    if rows:
        affected_predictions = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM predictions p
                WHERE EXISTS (
                    SELECT 1 FROM odds_snapshots o
                    JOIN quarantined_odds q ON q.odds_id = o.odds_id
                    WHERE q.reason = 'MISATTRIBUTED_SAME_TEAM_PAIR_GAME'
                      AND o.game_id = p.game_id
                      AND o.provider = p.odds_provider
                      AND o.captured_at = p.odds_captured_at
                      AND o.decimal_odds = p.decimal_odds_used
                )
                """
            ).fetchone()[0]
        )
    _log_repair(
        conn,
        migration_id,
        "odds_snapshots",
        "SAME_TEAM_PAIR_MISATTRIBUTION",
        "QUARANTINE_MISATTRIBUTED_QUOTES",
        f"Quarantined {quarantined} live-API quotes copied onto both games of a same-team mini-series; "
        f"{affected_predictions} historical predictions used one of them (kept unchanged).",
    )
    return {"quarantined_quotes": quarantined, "affected_predictions": affected_predictions}


MIGRATIONS: list[tuple[str, Callable[[sqlite3.Connection, str], dict[str, Any]]]] = [
    ("2026_11_09_001_add_odds_source_type", m001_add_odds_source_type),
    ("2026_11_09_002_drop_unique_prediction_dedup_index", m002_drop_unique_prediction_dedup_index),
    ("2026_11_09_003_restore_history_from_93cfa87", m003_restore_history_from_93cfa87),
    ("2026_11_09_004_quarantine_unobserved_odds", m004_quarantine_unobserved_odds),
    ("2026_11_09_005_invalidate_pending_unobserved_props", m005_invalidate_pending_unobserved_props),
    ("2026_11_09_006_add_sub_bankroll_and_parlays", m006_add_sub_bankroll_and_parlays),
    ("2026_11_09_007_invalidate_hardcoded_parlays", m007_invalidate_hardcoded_parlays),
    ("2026_11_10_008_quarantine_legacy_synthetic_bets", m008_quarantine_legacy_synthetic_bets),
    ("2026_11_10_009_enforce_observed_games_view", m009_enforce_observed_games_view),
    ("2026_11_14_010_allow_player_prop_in_odds_snapshots", m010_allow_player_prop_in_odds_snapshots),
    ("2026_11_14_011_reconcile_observed_ledger_and_player_boxscores", m011_reconcile_observed_ledger_and_player_boxscores),
    ("2026_11_14_012_separate_prob_semantics_spread_and_manifests", m012_separate_prob_semantics_spread_and_manifests),
    ("2026_11_15_013_add_shadow_candidates_and_version_indexes", m013_add_shadow_candidates_and_version_indexes),
    ("2026_11_16_014_quarantine_misattributed_same_pair_quotes", m014_quarantine_misattributed_same_pair_quotes),
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
