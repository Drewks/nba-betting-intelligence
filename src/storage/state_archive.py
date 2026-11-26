"""
Daily immutable archive of the live audit database (`src/storage/state_archive.py`).

state-live keeps only the latest database: its commits are rewritten (`--force-with-lease`) and the workflow
backups expire after 7 days, so yesterday's database cannot be recovered from it. This module keeps one
snapshot per UTC day for as long as the repository exists:

- the compressed database (`nba_intelligence-YYYY-MM-DD.sqlite3.gz`, byte-identical to the
  `data/nba_intelligence.sqlite3.gz` blob committed on state-live) is an asset of the GitHub Release
  `db-archive` (needs only `contents: write`);
- `snapshots/YYYY-MM-DD.json` (sizes, SHA-256 of the .gz and of the database, row count and content digest of
  every table, and the continuity check against the previous snapshot) plus one line in `ledger.jsonl` are
  committed on the branch `state-history`, always as a child of its current tip and pushed without force,
  so its history is append-only.

Continuity (`verify_immutable_continuity`) compares two snapshots row by row: no row of an append-only table
may disappear or change, a settled bet/pick/parlay/shadow candidate is frozen, a pending one may only change
its settlement columns, and a game that had started keeps its tip-off and ingestion timestamps. Archiving
fails closed on any continuity violation before uploading an asset or advancing `state-history`.

Standard library only (the workflow runs it with python3). Requires `git` and `gh`.

  python3 -m src.storage.state_archive archive [--date YYYY-MM-DD] [--ref origin/state-live]
  python3 -m src.storage.state_archive archive --date YYYY-MM-DD --gz path.sqlite3.gz [--source-commit SHA] [--committed-at ISO]
  python3 -m src.storage.state_archive reconstruct YYYY-MM-DD --out /tmp/db.sqlite3
  python3 -m src.storage.state_archive verify-window --days 30
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any, Protocol
import zlib

from src.storage.state_live import LIVE_DB_GZ_PATH, StateLiveError, check_integrity

RELEASE_TAG = "db-archive"
RELEASE_TARGET = "main"
HISTORY_BRANCH = "state-history"
MANIFEST_SCHEMA = 1
_MAX_REPORTED = 20
_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


class StateArchiveError(RuntimeError):
    """The archive could not be written, read or verified safely."""


class ContinuityViolationError(StateArchiveError):
    """Immutable history continuity check failed between two snapshots."""

    def __init__(self, previous_snapshot: str, violations: list[str]) -> None:
        self.previous_snapshot = previous_snapshot
        self.violations = list(violations)
        detail = "; ".join(self.violations[:_MAX_REPORTED])
        super().__init__(
            f"Immutable continuity violated vs {previous_snapshot} ({len(self.violations)} violation(s)): {detail}"
        )


@dataclass(frozen=True)
class TableRule:
    """How a table's rows may evolve between two snapshots."""

    pk: tuple[str, ...]
    # Settle-once tables: only `settlement_columns` may change while `status = 'PENDING'`; every other column
    # (recorded selection, odds, stake, probabilities, timestamps) is frozen immediately, and once a row is
    # settled every column is frozen. Empty `status_column` means every column is always frozen.
    settlement_columns: tuple[str, ...] = ()
    status_column: str = ""


_BET_SETTLEMENT_COLS = ("status", "net_profit_pen", "bankroll_after_pen", "actual_result_summary", "settled_at")

IMMUTABLE_TABLES: dict[str, TableRule] = {
    "odds_snapshots": TableRule(("odds_id",)),
    "quarantined_odds": TableRule(("odds_id",)),
    "predictions": TableRule(("prediction_id",)),
    "decision_log": TableRule(("decision_id",)),
    "bankroll_ledger": TableRule(("entry_id",)),
    "run_manifests": TableRule(("run_id",)),
    "schema_migrations": TableRule(("migration_id",)),
    "audit_repairs": TableRule(("repair_id",)),
    "audit_row_registry": TableRule(("table_name", "row_pk")),
    "parlay_bankroll_ledger": TableRule(("entry_id",)),
    "simulated_bets": TableRule(("bet_id",), _BET_SETTLEMENT_COLS, "status"),
    "parlay_bets": TableRule(("parlay_id",), _BET_SETTLEMENT_COLS, "status"),
    "player_prop_picks": TableRule(("prop_id",), ("actual_stat", *_BET_SETTLEMENT_COLS), "status"),
    "shadow_candidates": TableRule(
        ("shadow_id",),
        ("closing_decimal_odds", "closing_fair_prob", "clv_pct", "status", "hypothetical_unit_profit", "settled_at"),
        "status",
    ),
}
# Games: once tip-off has passed, the row is history (src/storage/schema.py temporal-freeze triggers).
GAME_FROZEN_AFTER_START = ("game_start_time", "features_available_at", "ingested_at")


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _ro_uri(path: str | Path) -> str:
    return f"{Path(path).resolve().as_uri()}?mode=ro&immutable=1"


def _connect_ro(path: str | Path) -> sqlite3.Connection:
    return sqlite3.connect(_ro_uri(path), uri=True)


def _workflow_message(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _validate_snapshot_date(snapshot_date: str) -> str:
    if len(snapshot_date) != 10:
        raise StateArchiveError(f"invalid snapshot date {snapshot_date!r}: expected YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(snapshot_date)
    except ValueError as exc:
        raise StateArchiveError(f"invalid snapshot date {snapshot_date!r}: expected YYYY-MM-DD") from exc
    if parsed.isoformat() != snapshot_date:
        raise StateArchiveError(f"invalid snapshot date {snapshot_date!r}: expected YYYY-MM-DD")
    return snapshot_date


def _parse_iso_timestamp(ts: str) -> datetime:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StateArchiveError(f"invalid ISO-8601 timestamp {ts!r}") from exc
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _validate_iso_timestamp(ts: str) -> str:
    _parse_iso_timestamp(ts)
    return ts


def _freeze_cutoff(manifest: dict[str, Any]) -> str | None:
    """
    Timestamp at which started games in `manifest` were already frozen.

    For a live same-day archive (including no-change workflow runs that reuse an older state-live SHA),
    any game that tipped off by `archived_at` was already started when the snapshot was observed.
    For a historical backfill (`archived_at` on a later UTC date than `snapshot_date`) or a manifest
    recovered from an earlier same-day Release asset, `source_committed_at` reflects when that snapshot
    was actually taken.
    """
    committed_at = manifest.get("source_committed_at")
    archived_at = manifest.get("archived_at")
    snap_date = str(manifest.get("snapshot_date") or "")
    if not archived_at:
        return str(committed_at) if committed_at else None
    if manifest.get("recovered_from_existing_asset") and committed_at:
        return str(committed_at)
    if snap_date and str(archived_at)[:10] > snap_date and committed_at:
        return str(committed_at)
    if not committed_at:
        return str(archived_at)
    return str(archived_at) if _parse_iso_timestamp(str(archived_at)) >= _parse_iso_timestamp(str(committed_at)) else str(committed_at)


def _db_latest_timestamp(db_path: Path) -> str | None:
    """Best-effort latest ISO-8601 UTC write timestamp recorded inside `db_path` (for orphan asset recovery)."""
    candidates: list[tuple[datetime, str]] = []
    conn = _connect_ro(db_path)
    try:
        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table, col in (
            ("run_manifests", "created_at"),
            ("odds_snapshots", "captured_at"),
            ("predictions", "emitted_at"),
            ("simulated_bets", "settled_at"),
            ("games", "ingested_at"),
        ):
            if table not in tables or col not in _columns(conn, "main", table):
                continue
            row = conn.execute(
                f"SELECT MAX(datetime({_q(col)})) FROM {_q(table)} WHERE {_q(col)} IS NOT NULL"
            ).fetchone()
            if row and row[0]:
                raw = str(row[0]).replace(" ", "T") + "Z"
                try:
                    candidates.append((_parse_iso_timestamp(raw), raw))
                except StateArchiveError:
                    continue
    finally:
        conn.close()
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _sha256_file(path: Path) -> tuple[int, str]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _columns(conn: sqlite3.Connection, schema: str, table: str) -> list[str]:
    return [str(r[1]) for r in conn.execute(f"PRAGMA {schema}.table_info({_q(table)})")]


def _pk_columns(conn: sqlite3.Connection, schema: str, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA {schema}.table_info({_q(table)})").fetchall()
    return [name for _, name in sorted((int(r[5]), str(r[1])) for r in rows if int(r[5]) > 0)]


def _differs_sql(cols: list[str]) -> str:
    return " OR ".join(f"n.{_q(c)} IS NOT o.{_q(c)}" for c in cols) or "0"


def table_fingerprints(db_path: str | Path) -> dict[str, dict[str, Any]]:
    """Row count and SHA-256 of canonical JSON rows (PK order, falling back to all columns) of every table."""
    conn = _connect_ro(db_path)
    try:
        out: dict[str, dict[str, Any]] = {}
        names = [str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        for name in names:
            cols = _columns(conn, "main", name)
            pks = _pk_columns(conn, "main", name)
            select_expr = ", ".join(_q(c) for c in cols)
            order_expr = ", ".join(_q(c) for c in (pks or cols))
            digest = hashlib.sha256()
            count = 0
            for row in conn.execute(f"SELECT {select_expr} FROM {_q(name)} ORDER BY {order_expr}"):
                digest.update(json.dumps(list(row), separators=(",", ":"), default=str).encode("utf-8") + b"\n")
                count += 1
            out[name] = {
                "row_count": count,
                "content_sha256": digest.hexdigest(),
                "immutable": name in IMMUTABLE_TABLES,
            }
        return out
    finally:
        conn.close()


def verify_immutable_continuity(
    older_db: str | Path, newer_db: str | Path, *, older_taken_at: str | None = None
) -> list[str]:
    """
    Row-by-row check that `newer_db` is a lawful continuation of `older_db`. Returns the violations (empty when
    continuous). `older_taken_at` (ISO UTC) is when the older snapshot was stored: games that had started by
    then must keep their tip-off and ingestion timestamps.
    """
    conn = _connect_ro(newer_db)
    violations: list[str] = []
    try:
        conn.execute("ATTACH DATABASE ? AS old", (_ro_uri(older_db),))
        old_tables = {str(r[0]) for r in conn.execute("SELECT name FROM old.sqlite_master WHERE type = 'table'")}
        new_tables = {str(r[0]) for r in conn.execute("SELECT name FROM main.sqlite_master WHERE type = 'table'")}
        for table, rule in IMMUTABLE_TABLES.items():
            if table not in old_tables:
                continue
            if table not in new_tables:
                violations.append(f"{table}: table missing from the newer snapshot")
                continue
            old_cols, new_cols = _columns(conn, "old", table), set(_columns(conn, "main", table))
            dropped = [c for c in old_cols if c not in new_cols]
            if dropped:
                violations.append(f"{table}: columns dropped {dropped}")
            common = [c for c in old_cols if c in new_cols]
            if not all(k in common for k in rule.pk):
                violations.append(f"{table}: primary key columns missing {list(rule.pk)}")
                continue
            violations += _table_violations(conn, table, rule, common)
        if "games" in old_tables:
            if "games" not in new_tables:
                violations.append("games: table missing from the newer snapshot")
            elif older_taken_at:
                violations += _game_violations(conn, older_taken_at)
    finally:
        conn.close()
    return violations


def _table_violations(conn: sqlite3.Connection, table: str, rule: TableRule, common: list[str]) -> list[str]:
    join = " AND ".join(f"n.{_q(k)} IS o.{_q(k)}" for k in rule.pk)
    pk_sel = ", ".join(f"o.{_q(k)}" for k in rule.pk)
    out: list[str] = []
    missing = conn.execute(
        f"SELECT {pk_sel} FROM old.{_q(table)} o WHERE NOT EXISTS (SELECT 1 FROM main.{_q(table)} n WHERE {join}) "
        f"LIMIT {_MAX_REPORTED}"
    ).fetchall()
    out += [f"{table}: row {list(r)} deleted" for r in missing]
    if rule.status_column and rule.status_column in common:
        settlement = set(rule.settlement_columns)
        pending_cols = [c for c in common if c not in settlement]
        cond = f"(o.{_q(rule.status_column)} IS NOT 'PENDING' AND ({_differs_sql(common)})) OR ({_differs_sql(pending_cols)})"
    else:
        cond = _differs_sql(common)
    changed = conn.execute(
        f"SELECT {pk_sel} FROM old.{_q(table)} o JOIN main.{_q(table)} n ON {join} WHERE {cond} LIMIT {_MAX_REPORTED}"
    ).fetchall()
    out += [f"{table}: row {list(r)} modified" for r in changed]
    return out


def _game_violations(conn: sqlite3.Connection, older_taken_at: str) -> list[str]:
    old_cols = _columns(conn, "old", "games")
    new_cols = set(_columns(conn, "main", "games"))
    if "game_id" not in old_cols or "game_start_time" not in old_cols:
        return []
    if "game_id" not in new_cols:
        return ["games: primary key column missing ['game_id']"]
    started = "datetime(o.game_start_time) <= datetime(?)"
    rows = conn.execute(
        f"SELECT o.game_id FROM old.games o WHERE {started} "
        f"AND NOT EXISTS (SELECT 1 FROM main.games n WHERE n.game_id = o.game_id) LIMIT {_MAX_REPORTED}",
        (older_taken_at,),
    ).fetchall()
    out = [f"games: started game {r[0]} deleted" for r in rows]
    dropped = [c for c in GAME_FROZEN_AFTER_START if c in old_cols and c not in new_cols]
    if dropped:
        out.append(f"games: frozen columns dropped {dropped}")
    cols = [c for c in GAME_FROZEN_AFTER_START if c in old_cols and c in new_cols]
    rows = conn.execute(
        f"SELECT o.game_id FROM old.games o JOIN main.games n ON n.game_id = o.game_id "
        f"WHERE {started} AND ({_differs_sql(cols)}) LIMIT {_MAX_REPORTED}",
        (older_taken_at,),
    ).fetchall()
    return out + [f"games: started game {r[0]} rewrote {list(cols)}" for r in rows]


def decompress(gz_path: Path, out_path: Path) -> tuple[int, str]:
    """Decompresses `gz_path` into `out_path`; returns the database size and SHA-256."""
    digest, size = hashlib.sha256(), 0
    try:
        with gzip.open(gz_path, "rb") as src, out_path.open("wb") as dst:
            while chunk := src.read(1 << 20):
                digest.update(chunk)
                size += len(chunk)
                dst.write(chunk)
    except (EOFError, OSError, zlib.error) as exc:
        raise StateArchiveError(f"cannot decompress {gz_path}: {exc}") from exc
    return size, digest.hexdigest()


# ------------------------------------------------------------------------------------------------ release store
class ReleaseStore(Protocol):
    def ensure_release(self) -> None: ...
    def asset_names(self) -> set[str]: ...
    def asset_timestamps(self) -> dict[str, str]: ...
    def upload(self, path: Path) -> None: ...
    def download(self, name: str, dest_dir: Path) -> Path: ...


class GhReleaseStore:
    """GitHub Release `db-archive` through the `gh` CLI (GH_TOKEN with `contents: write`)."""

    def __init__(self, tag: str = RELEASE_TAG, repo_root: Path = Path("."), target: str = RELEASE_TARGET) -> None:
        self.tag, self.root, self.target = tag, repo_root, target

    def _gh(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(["gh", *args], cwd=self.root, capture_output=True, text=True, check=False)
        if check and proc.returncode != 0:
            raise StateArchiveError(f"gh {' '.join(args)} failed: {proc.stderr.strip()}")
        return proc

    def ensure_release(self) -> None:
        if self._gh("release", "view", self.tag, "--json", "tagName", check=False).returncode == 0:
            return
        notes = (
            "Daily immutable snapshots of the live paper-trading audit database (state-live). "
            f"The SHA-256 of every asset and its continuity check are committed on the `{HISTORY_BRANCH}` branch."
        )
        self._gh(
            "release",
            "create",
            self.tag,
            "--target",
            self.target,
            "--title",
            "NBA state-live daily database archive",
            "--notes",
            notes,
            "--latest=false",
        )

    def asset_timestamps(self) -> dict[str, str]:
        api_url = self._gh("release", "view", self.tag, "--json", "apiUrl", "--jq", ".apiUrl").stdout.strip()
        if not api_url:
            return {}
        out = self._gh(
            "api",
            "--paginate",
            f"{api_url}/assets?per_page=100",
            "--jq",
            r'.[] | "\(.name)\t\(.created_at // "")"',
        ).stdout
        timestamps: dict[str, str] = {}
        for line in out.splitlines():
            if "\t" in line:
                name, created_at = line.split("\t", 1)
                if name.strip():
                    timestamps[name.strip()] = created_at.strip()
        return timestamps

    def asset_names(self) -> set[str]:
        return set(self.asset_timestamps())

    def upload(self, path: Path) -> None:
        self._gh("release", "upload", self.tag, str(path))  # never --clobber: an asset is written once

    def download(self, name: str, dest_dir: Path) -> Path:
        self._gh("release", "download", self.tag, "--pattern", name, "--dir", str(dest_dir))
        downloaded = dest_dir / name
        if not downloaded.is_file():
            raise StateArchiveError(f"release asset {name} was not downloaded into {dest_dir}")
        return downloaded


# ------------------------------------------------------------------------------------------------ history branch
def _git(
    root: Path,
    *args: str,
    env: dict[str, str] | None = None,
    check: bool = True,
    data: bytes | None = None,
    strip: bool = True,
) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, check=False, input=data, env={**os.environ, **(env or {})}
    )
    if check and proc.returncode != 0:
        raise StateArchiveError(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
    text = proc.stdout.decode("utf-8", "replace")
    return text.strip() if strip else text


class HistoryBranch:
    """The append-only `state-history` branch on `origin` (plumbing only: the working tree is never touched)."""

    def __init__(self, repo_root: Path = Path("."), remote: str = "origin", branch: str = HISTORY_BRANCH) -> None:
        self.root, self.remote, self.branch = repo_root, remote, branch
        self.ref = f"refs/remotes/{remote}/{branch}"

    def fetch(self) -> str | None:
        """Fetches the branch; returns its tip, or None when it does not exist yet."""
        if not _git(self.root, "ls-remote", "--heads", self.remote, self.branch):
            return None
        _git(self.root, "fetch", "--quiet", self.remote, f"+refs/heads/{self.branch}:{self.ref}")
        return _git(self.root, "rev-parse", self.ref)

    def read(self, tip: str | None, path: str) -> str | None:
        if tip is None or not self._exists(tip, path):
            return None
        return _git(self.root, "show", f"{tip}:{path}", strip=False)

    def _exists(self, tip: str, path: str) -> bool:
        return subprocess.run(["git", "cat-file", "-e", f"{tip}:{path}"], cwd=self.root, capture_output=True).returncode == 0

    def snapshot_dates(self, tip: str | None) -> list[str]:
        if tip is None or not self._exists(tip, "snapshots"):
            return []
        names = _git(self.root, "ls-tree", "--name-only", f"{tip}:snapshots", check=False).splitlines()
        return sorted(n[:-5] for n in names if n.endswith(".json"))

    def append(self, tip: str | None, files: dict[str, str], message: str) -> str:
        """Commits `files` as a child of `tip` and pushes it without force (fast-forward only)."""
        with tempfile.TemporaryDirectory() as tmp:
            env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
            if tip is not None:
                _git(self.root, "read-tree", tip, env=env)
            for path, content in files.items():
                blob = _git(self.root, "hash-object", "-w", "--stdin", data=content.encode("utf-8"))
                _git(self.root, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
            tree = _git(self.root, "write-tree", env=env)
        parent = ["-p", tip] if tip is not None else []
        commit = _git(self.root, "commit-tree", tree, *parent, "-m", message)
        _git(self.root, "push", self.remote, f"{commit}:refs/heads/{self.branch}")
        return commit


# ------------------------------------------------------------------------------------------------ operations
def asset_name(snapshot_date: str) -> str:
    _validate_snapshot_date(snapshot_date)
    return f"nba_intelligence-{snapshot_date}.sqlite3.gz"


def build_manifest(
    gz_path: Path, db_path: Path, snapshot_date: str, *, source_commit: str, committed_at: str
) -> dict[str, Any]:
    _validate_snapshot_date(snapshot_date)
    _validate_iso_timestamp(committed_at)
    gz_size, gz_sha = _sha256_file(gz_path)
    db_size, db_sha = _sha256_file(db_path)
    return {
        "schema": MANIFEST_SCHEMA,
        "snapshot_date": snapshot_date,
        "archived_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_commit": source_commit,
        "source_committed_at": committed_at,
        "release_tag": RELEASE_TAG,
        "asset_name": asset_name(snapshot_date),
        "gz_size_bytes": gz_size,
        "gz_sha256": gz_sha,
        "sqlite_size_bytes": db_size,
        "sqlite_sha256": db_sha,
        "tables": table_fingerprints(db_path),
    }


def _fetch_asset(store: ReleaseStore, manifest: dict[str, Any], workdir: Path) -> Path:
    """Downloads and fully verifies a snapshot; returns the decompressed database path."""
    gz = store.download(str(manifest["asset_name"]), workdir)
    gz_size, gz_sha = _sha256_file(gz)
    if gz_sha != manifest["gz_sha256"] or gz_size != manifest["gz_size_bytes"]:
        raise StateArchiveError(f"{gz.name}: SHA-256 or size differs from the manifest")
    db = workdir / f"{manifest['snapshot_date']}.sqlite3"
    db_size, db_sha = decompress(gz, db)
    if db_sha != manifest["sqlite_sha256"] or db_size != manifest["sqlite_size_bytes"]:
        raise StateArchiveError(f"{db.name}: decompressed SHA-256 or size differs from the manifest")
    try:
        check_integrity(db)
    except StateLiveError as exc:
        raise StateArchiveError(str(exc)) from exc
    tables = table_fingerprints(db)
    expected_tables: dict[str, Any] = manifest["tables"]
    if set(tables) != set(expected_tables):
        raise StateArchiveError(f"{db.name}: table set differs from the manifest")
    for name, fp in expected_tables.items():
        actual = tables[name]
        if actual["content_sha256"] != fp["content_sha256"] or actual["row_count"] != fp["row_count"]:
            raise StateArchiveError(f"{db.name}: table {name} differs from the manifest")
    return db


def archive_snapshot(
    gz_path: Path,
    snapshot_date: str,
    *,
    source_commit: str,
    committed_at: str,
    store: ReleaseStore,
    history: HistoryBranch,
    allow_violations: bool = False,
) -> dict[str, Any]:
    """Archives one day's database (idempotent per day). Fails closed on continuity violations."""
    _validate_snapshot_date(snapshot_date)
    _validate_iso_timestamp(committed_at)
    tip = history.fetch()
    path = f"snapshots/{snapshot_date}.json"
    existing = history.read(tip, path)
    store.ensure_release()
    if existing is not None:
        manifest = json.loads(existing)
        if manifest["asset_name"] not in store.asset_names():
            raise StateArchiveError(f"{path} exists but its asset {manifest['asset_name']} is missing from {RELEASE_TAG}")
        with tempfile.TemporaryDirectory() as tmp:
            _fetch_asset(store, manifest, Path(tmp))
        return {**manifest, "skipped": True}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        db = work / "current.sqlite3"
        decompress(gz_path, db)
        try:
            check_integrity(db)
        except StateLiveError as exc:
            raise StateArchiveError(str(exc)) from exc
        all_dates = history.snapshot_dates(tip)
        previous = [d for d in all_dates if d < snapshot_date]
        later = [d for d in all_dates if d > snapshot_date]
        name = asset_name(snapshot_date)
        existing_assets = store.asset_timestamps()
        asset_exists = name in existing_assets

        target_gz = gz_path
        target_db = db
        target_commit = source_commit
        target_committed_at = committed_at
        recovered_superseded = False

        if asset_exists:
            # Recovery path: a previous run uploaded the immutable asset but failed before pushing `state-history`.
            # Always require a trustworthy upload timestamp on the existing asset so the started-game freeze cutoff
            # is never weakened on a later retry (including cross-midnight retries with `--date`).
            asset_ts = existing_assets.get(name, "").strip()
            if not asset_ts:
                raise StateArchiveError(
                    f"existing asset {name} in {RELEASE_TAG} has no upload timestamp; "
                    "cannot verify started-game freeze cutoff safely"
                )
            _validate_iso_timestamp(asset_ts)
            existing_dir = work / "existing_asset"
            existing_dir.mkdir()
            existing_gz = store.download(name, existing_dir)
            existing_size, existing_sha = _sha256_file(existing_gz)
            cur_size, cur_sha = _sha256_file(gz_path)
            if existing_sha != cur_sha or existing_size != cur_size:
                existing_db = existing_dir / "existing.sqlite3"
                decompress(existing_gz, existing_db)
                try:
                    check_integrity(existing_db)
                except StateLiveError as exc:
                    raise StateArchiveError(f"existing asset {name} failed integrity check: {exc}") from exc
                db_latest = _db_latest_timestamp(existing_db)
                if db_latest and _parse_iso_timestamp(db_latest) > _parse_iso_timestamp(asset_ts):
                    recovered_at = db_latest
                else:
                    recovered_at = asset_ts
                ancestor_violations = verify_immutable_continuity(existing_db, db, older_taken_at=recovered_at)
                if ancestor_violations and not allow_violations:
                    raise ContinuityViolationError(f"{snapshot_date} (existing asset {name})", ancestor_violations)
                target_gz = existing_gz
                target_db = existing_db
                target_commit = f"recovered-asset:{existing_sha[:12]}"
                target_committed_at = recovered_at
                recovered_superseded = True
            elif asset_ts[:10] <= snapshot_date and _parse_iso_timestamp(asset_ts) > _parse_iso_timestamp(committed_at):
                target_committed_at = asset_ts

        manifest = build_manifest(
            target_gz, target_db, snapshot_date, source_commit=target_commit, committed_at=target_committed_at
        )
        if recovered_superseded:
            manifest["recovered_from_existing_asset"] = True
        continuity: dict[str, Any] = {"previous_snapshot": None, "ok": True, "violations": []}
        if previous:
            prev_manifest = json.loads(history.read(tip, f"snapshots/{previous[-1]}.json") or "{}")
            prev_dir = work / "previous"
            prev_dir.mkdir()
            prev_db = _fetch_asset(store, prev_manifest, prev_dir)
            found = verify_immutable_continuity(prev_db, target_db, older_taken_at=_freeze_cutoff(prev_manifest))
            continuity = {"previous_snapshot": previous[-1], "ok": not found, "violations": found}
            if found and not allow_violations:
                raise ContinuityViolationError(previous[-1], found)
        if later:
            next_manifest = json.loads(history.read(tip, f"snapshots/{later[0]}.json") or "{}")
            next_dir = work / "next"
            next_dir.mkdir()
            next_db = _fetch_asset(store, next_manifest, next_dir)
            later_found = verify_immutable_continuity(target_db, next_db, older_taken_at=_freeze_cutoff(manifest))
            if later_found and not allow_violations:
                raise ContinuityViolationError(later[0], later_found)
        manifest["continuity"] = continuity
        if not asset_exists:
            upload = work / name
            shutil.copyfile(gz_path, upload)
            store.upload(upload)
    ledger = (history.read(tip, "ledger.jsonl") or "").rstrip("\n")
    line = json.dumps(
        {k: manifest[k] for k in ("snapshot_date", "asset_name", "gz_sha256", "sqlite_sha256", "source_commit")}
        | {"continuity_ok": continuity["ok"]},
        sort_keys=True,
    )
    history.append(
        tip,
        {
            path: json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            "ledger.jsonl": (ledger + "\n" if ledger else "") + line + "\n",
        },
        f"archive: database snapshot {snapshot_date} ({manifest['gz_sha256'][:12]})",
    )
    return manifest


def reconstruct(snapshot_date: str, out_path: Path, *, store: ReleaseStore, history: HistoryBranch) -> dict[str, Any]:
    """Rebuilds the database of `snapshot_date` from the archive into `out_path`, fully verified."""
    _validate_snapshot_date(snapshot_date)
    tip = history.fetch()
    raw = history.read(tip, f"snapshots/{snapshot_date}.json")
    if raw is None:
        raise StateArchiveError(f"no archived snapshot for {snapshot_date}")
    manifest = json.loads(raw)
    with tempfile.TemporaryDirectory() as tmp:
        db = _fetch_asset(store, manifest, Path(tmp))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_out = out_path.with_name(f"{out_path.name}.reconstruct-tmp")
        try:
            shutil.copyfile(db, tmp_out)
            for suffix in _SIDECAR_SUFFIXES:
                Path(f"{out_path}{suffix}").unlink(missing_ok=True)
            os.replace(tmp_out, out_path)
        finally:
            tmp_out.unlink(missing_ok=True)
    return manifest


def verify_window(days: int, *, store: ReleaseStore, history: HistoryBranch, today: date | None = None) -> dict[str, Any]:
    """Reconstructs every snapshot of the last `days` days and checks continuity between consecutive ones."""
    if days < 1:
        raise StateArchiveError(f"days must be >= 1, got {days}")
    tip = history.fetch()
    since = ((today or datetime.now(timezone.utc).date()) - timedelta(days=days)).isoformat()
    dates = [d for d in history.snapshot_dates(tip) if d >= since]
    if not dates:
        raise StateArchiveError(f"no archived snapshots found on {history.branch} since {since}")
    report: dict[str, Any] = {"snapshots": dates, "pairs": [], "ok": True}
    with tempfile.TemporaryDirectory() as tmp:
        prev: tuple[str, Path, Path, dict[str, Any]] | None = None
        for d in dates:
            manifest = json.loads(history.read(tip, f"snapshots/{d}.json") or "{}")
            workdir = Path(tmp) / d
            workdir.mkdir()
            db = _fetch_asset(store, manifest, workdir)
            if prev is not None:
                found = verify_immutable_continuity(prev[2], db, older_taken_at=_freeze_cutoff(prev[3]))
                report["pairs"].append({"older": prev[0], "newer": d, "violations": found})
                report["ok"] = report["ok"] and not found
                shutil.rmtree(prev[1], ignore_errors=True)
            prev = (d, workdir, db, manifest)
    return report


def _source_from_ref(ref: str, dest: Path, repo_root: Path) -> tuple[str, str]:
    commit = _git(repo_root, "rev-parse", f"{ref}^{{commit}}")
    committed_at = datetime.fromtimestamp(int(_git(repo_root, "show", "-s", "--format=%ct", commit)), tz=timezone.utc)
    blob = subprocess.run(["git", "cat-file", "blob", f"{commit}:{LIVE_DB_GZ_PATH}"], cwd=repo_root, capture_output=True, check=False)
    if blob.returncode != 0:
        raise StateArchiveError(f"{commit} holds no {LIVE_DB_GZ_PATH}")
    dest.write_bytes(blob.stdout)
    return commit, committed_at.strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m src.storage.state_archive", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    arc = sub.add_parser("archive", help="Archive one UTC day's database snapshot (idempotent per day).")
    arc.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    arc.add_argument("--ref", default="origin/state-live", help="state-live commit holding the .gz to archive")
    arc.add_argument("--gz", type=Path, default=None, help="Local .sqlite3.gz file to archive instead of --ref")
    arc.add_argument("--source-commit", default=None, help="Source commit SHA or provenance label (for --gz backfill)")
    arc.add_argument("--committed-at", default=None, help="ISO-8601 UTC timestamp when the source snapshot was taken")
    rec = sub.add_parser("reconstruct", help="Rebuild an archived day's database.")
    rec.add_argument("date")
    rec.add_argument("--out", required=True, type=Path)
    win = sub.add_parser("verify-window", help="Reconstruct the last N days and verify continuity.")
    win.add_argument("--days", type=int, default=30)
    args = parser.parse_args(argv)
    root, store, history = Path("."), GhReleaseStore(), HistoryBranch()
    try:
        if args.command == "archive":
            if args.gz is not None:
                if not args.gz.is_file():
                    raise StateArchiveError(f"source file not found: {args.gz}")
                commit = args.source_commit or "local-backfill"
                committed_at = args.committed_at or datetime.fromtimestamp(
                    args.gz.stat().st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
                m = archive_snapshot(
                    args.gz, args.date, source_commit=commit, committed_at=committed_at, store=store, history=history
                )
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    gz = Path(tmp) / "source.sqlite3.gz"
                    ref_commit, ref_committed_at = _source_from_ref(args.ref, gz, root)
                    m = archive_snapshot(
                        gz,
                        args.date,
                        source_commit=args.source_commit or ref_commit,
                        committed_at=args.committed_at or ref_committed_at,
                        store=store,
                        history=history,
                    )
            if m.get("skipped"):
                print(f"Snapshot {args.date} already archived ({m['gz_sha256'][:12]}); nothing to do.")
                return 0
            cont = m["continuity"]
            print(
                f"Archived {m['asset_name']} (sha256 {m['gz_sha256']}); continuity vs {cont['previous_snapshot']}: ok"
            )
        elif args.command == "reconstruct":
            m = reconstruct(args.date, args.out, store=store, history=history)
            print(
                f"Reconstructed {args.date} into {args.out}: sha256 {m['sqlite_sha256']}, integrity ok, "
                f"{len(m['tables'])} tables match the manifest."
            )
        else:
            report = verify_window(args.days, store=store, history=history)
            print(json.dumps(report, indent=2))
            return 0 if report["ok"] else 2
    except ContinuityViolationError as exc:
        print(f"::error::{_workflow_message(str(exc))}")
        return 2
    except (StateArchiveError, OSError) as exc:
        print(f"::error::{_workflow_message(str(exc))}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
