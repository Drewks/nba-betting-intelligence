"""
Synchronizes and verifies the live production SQLite database from `origin/state-live`
into an isolated runtime path without mutating the tracked frozen CI baseline on `main`.

state-live stores the database gzip-compressed as `data/nba_intelligence.sqlite3.gz`; it is
decompressed with the same code the workflows use (`src/storage/state_live.py`).

Usage:
  uv run python scripts/sync_state_live.py
  uv run python scripts/sync_state_live.py --out C:/Temp/state_live.sqlite3 --apply-migrations
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.db import DatabaseManager
from src.storage.state_live import LIVE_DB_PATH, LIVE_SOURCE_OF_TRUTH, restore_live_db


def extract_state_live_db(
    out_path: Path,
    *,
    remote_ref: str = "origin/state-live",
    repo_root: Path = PROJECT_ROOT,
    fetch: bool = True,
    allow_tracked_overwrite: bool = False,
) -> dict[str, Any]:
    """
    Writes the live database of `origin/state-live` to `out_path`: `data/nba_intelligence.sqlite3.gz`
    decompressed (or the uncompressed file of a commit from before the compression). Raises unless the
    result passes `PRAGMA integrity_check`.
    """
    resolved_out = Path(out_path).resolve()
    tracked_main_db = (repo_root / LIVE_DB_PATH).resolve()
    if resolved_out == tracked_main_db and not allow_tracked_overwrite:
        raise RuntimeError(
            "Refusing to overwrite tracked `data/nba_intelligence.sqlite3` on `main`; "
            "pass a temporary/runtime `--out` path (`.github/workflows/ci.yml` enforces immutability on `main`)."
        )

    if fetch:
        remote_name, _, branch_name = remote_ref.partition("/")
        proc_fetch = subprocess.run(
            ["git", "fetch", "--depth=1", remote_name or "origin", branch_name or "state-live"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc_fetch.returncode != 0:
            raise RuntimeError(f"git fetch {remote_ref} failed: {proc_fetch.stderr.strip()}")

    proc_sha = subprocess.run(
        ["git", "rev-parse", remote_ref],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc_sha.returncode != 0:
        raise RuntimeError(f"Unable to resolve {remote_ref}: {proc_sha.stderr.strip()}")
    commit_sha = proc_sha.stdout.strip()

    restored = restore_live_db(commit_sha, resolved_out, repo_root=repo_root)
    return {
        "source_ref": remote_ref,
        "source_commit_sha": commit_sha,
        "source_path": restored["source_path"],
        "output_path": str(resolved_out),
        "size_bytes": restored["size_bytes"],
        "sha256": restored["sha256"],
    }


def inspect_sqlite_summary(db_path: Path, *, apply_migrations: bool = False) -> dict[str, Any]:
    """Checks SQLite integrity, optionally runs pending migrations, and reports table counts."""
    resolved = Path(db_path).resolve()
    if apply_migrations:
        db = DatabaseManager(resolved)
        db.checkpoint(truncate=True)

    uri = f"file:{resolved.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        has_shadow = bool(
            conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='shadow_candidates'").fetchone()
        )
        final_games = int(
            conn.execute("SELECT COUNT(*) FROM games WHERE status='FINAL' AND game_id NOT LIKE 'SYN%'").fetchone()[0]
        )
        obs_preds = int(conn.execute("SELECT COUNT(*) FROM v_observed_predictions").fetchone()[0])
        settled_bets = int(
            conn.execute(
                "SELECT COUNT(*) FROM v_observed_simulated_bets WHERE status IN ('WON', 'LOST', 'PUSH', 'VOID')"
            ).fetchone()[0]
        )
        shadow_count = int(conn.execute("SELECT COUNT(*) FROM shadow_candidates").fetchone()[0]) if has_shadow else 0
        latest_mig = conn.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    return {
        "db_path": str(resolved),
        "sqlite_integrity_check": integrity,
        "final_games_observed": final_games,
        "observed_predictions_count": obs_preds,
        "observed_settled_bets_count": settled_bets,
        "shadow_candidates_count": shadow_count,
        "latest_migration_id": str(latest_mig[0]) if latest_mig else None,
        "live_source_of_truth": LIVE_SOURCE_OF_TRUTH,
        "main_branch_db_policy": "FROZEN_CI_BASELINE",
    }


def main() -> None:
    default_out = Path(os.environ.get("TEMP") or tempfile.gettempdir()) / "nba_state_live.sqlite3"
    parser = argparse.ArgumentParser(description="Sync & inspect live SQLite state from origin/state-live.")
    parser.add_argument("--out", default=str(default_out), help="Target isolated runtime SQLite path.")
    parser.add_argument("--remote-ref", default="origin/state-live", help="Git ref holding live SQLite DB.")
    parser.add_argument("--no-fetch", action="store_true", help="Skip `git fetch` and read local remote-tracking ref.")
    parser.add_argument("--verify-only", action="store_true", help="Inspect `--out` without re-extracting from Git.")
    parser.add_argument("--apply-migrations", action="store_true", help="Run pending migrations on extracted copy.")
    args = parser.parse_args()

    out_path = Path(args.out)
    payload: dict[str, Any] = {}
    if not args.verify_only:
        payload["extract"] = extract_state_live_db(
            out_path,
            remote_ref=args.remote_ref,
            fetch=not args.no_fetch,
        )
    payload["summary"] = inspect_sqlite_summary(out_path, apply_migrations=args.apply_migrations)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
