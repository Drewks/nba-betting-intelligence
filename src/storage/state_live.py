"""
Storage of the live audit database in the `state-live` branch (`src/storage/state_live.py`).

state-live keeps the database gzip-compressed as `data/nba_intelligence.sqlite3.gz`. Uncompressed it grew
~14 MB a week (46.0 MB on 2026-11-17, 59.9 MB on 2026-11-24) and GitHub rejects a push holding a file over
100 MB, which would stop every cycle; `gzip -6 -n` stores the 59.9 MB database in 7.9 MB.

- `stage`, after the WAL checkpoint and before `git write-tree`: writes the `.gz` with `gzip -6 -n` (no
  name or timestamp, so an unchanged database keeps the same blob and the no-change checks still work),
  checks that it decompresses to the same bytes, `git add -f`s it and drops the uncompressed file from the
  index, so the commit removes it from state-live.
- `restore <commit>`: decompresses `<commit>:data/nba_intelligence.sqlite3.gz` into
  `data/nba_intelligence.sqlite3`. A commit written before the compression only holds the uncompressed
  file, which is restored as is. Fails closed unless `PRAGMA integrity_check` returns `ok`.

Standard library only: the weekly backtest restores the database before `uv sync`. The workflows run it
from the top of their checkout, where it overwrites main's frozen fixture on purpose; for a local copy use
`scripts/sync_state_live.py`, which refuses to.

  python3 -m src.storage.state_live restore "${STATE_BASE_SHA}"
  python3 -m src.storage.state_live stage
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any, Protocol
import zlib

LIVE_DB_PATH = "data/nba_intelligence.sqlite3"
LIVE_DB_GZ_PATH = f"{LIVE_DB_PATH}.gz"
LIVE_SOURCE_OF_TRUTH = f"origin/state-live:{LIVE_DB_GZ_PATH}"
GZIP_COMMAND = ("gzip", "-6", "-n")

_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
_CHUNK_BYTES = 1 << 20


class StateLiveError(RuntimeError):
    """The live database could not be stored in, or restored from, state-live safely."""


class _Reader(Protocol):
    def read(self, size: int = ..., /) -> bytes: ...


class _Writer(Protocol):
    def write(self, data: bytes, /) -> int: ...


def _git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    proc = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, check=False)
    if check and proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise StateLiveError(f"git {' '.join(args)} failed: {detail}")
    return proc


def _in_commit(repo_root: Path, commit: str, path: str) -> bool:
    return _git(repo_root, "cat-file", "-e", f"{commit}:{path}", check=False).returncode == 0


def _copy(src: _Reader, dst: _Writer | None = None) -> tuple[int, str]:
    """Reads `src` to the end (writing it to `dst` if given) and returns its size and sha256."""
    digest = hashlib.sha256()
    size = 0
    while chunk := src.read(_CHUNK_BYTES):
        digest.update(chunk)
        size += len(chunk)
        if dst is not None:
            dst.write(chunk)
    return size, digest.hexdigest()


def check_integrity(db_path: str | Path) -> int:
    """Returns the number of tables; raises StateLiveError unless `PRAGMA integrity_check` returns `ok`."""
    path = Path(db_path).resolve()
    # immutable=1 reads the main file only: a leftover -wal is not applied and no -wal/-shm is created.
    uri = f"{path.as_uri()}?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            result = [str(row[0]) for row in conn.execute("PRAGMA integrity_check")]
            tables = int(conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise StateLiveError(f"{path} is not a readable SQLite database: {exc}") from exc
    if result != ["ok"]:
        raise StateLiveError(f"PRAGMA integrity_check of {path} returned: {'; '.join(result[:5])}")
    if tables == 0:
        # An empty file passes integrity_check.
        raise StateLiveError(f"{path} has no tables")
    return tables


def restore_live_db(
    commit: str,
    out_path: str | Path = LIVE_DB_PATH,
    *,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    """
    Writes the database of the state-live commit `commit` to `out_path` (relative to `repo_root`, the top
    of the working tree): the `.gz` decompressed or, in a commit from before the compression, the
    uncompressed file. Raises StateLiveError, leaving `out_path` as it was, unless the restored database
    passes `PRAGMA integrity_check`.
    """
    root = Path(repo_root)
    if _git(root, "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}", check=False).returncode != 0:
        raise StateLiveError(f"{commit} is not a commit of this repository (fetch state-live first)")
    if _in_commit(root, commit, LIVE_DB_GZ_PATH):
        source = LIVE_DB_GZ_PATH
    elif _in_commit(root, commit, LIVE_DB_PATH):
        source = LIVE_DB_PATH
    else:
        raise StateLiveError(f"state-live commit {commit} holds neither {LIVE_DB_GZ_PATH} nor {LIVE_DB_PATH}")
    blob = _git(root, "cat-file", "blob", f"{commit}:{source}").stdout

    out = root / out_path
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.name}.restore-tmp")
    try:
        try:
            with tmp.open("wb") as dst:
                if source == LIVE_DB_GZ_PATH:
                    with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as unzipped:
                        size, sha256 = _copy(unzipped, dst)
                else:
                    size, sha256 = _copy(io.BytesIO(blob), dst)
        except (EOFError, OSError, zlib.error) as exc:
            raise StateLiveError(f"cannot decompress {commit}:{source}: {exc}") from exc
        tables = check_integrity(tmp)
        # The next connection would replay a -wal left next to the target onto the restored database.
        for suffix in _SIDECAR_SUFFIXES:
            Path(f"{out}{suffix}").unlink(missing_ok=True)
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return {
        "commit": commit,
        "source_path": source,
        "compressed": source == LIVE_DB_GZ_PATH,
        "output_path": str(out),
        "size_bytes": size,
        "sha256": sha256,
        "tables": tables,
    }


def stage_live_db(*, repo_root: str | Path = ".") -> dict[str, Any]:
    """
    Puts the checkpointed `data/nba_intelligence.sqlite3` of `repo_root` (the top of the working tree) in
    the index as `data/nba_intelligence.sqlite3.gz` and drops the uncompressed file from the index, so the
    next `git write-tree` holds only the `.gz`. Raises StateLiveError, leaving the index as it was, unless
    the database passes `PRAGMA integrity_check` and the `.gz` decompresses to the same bytes.
    """
    root = Path(repo_root)
    db = root / LIVE_DB_PATH
    gz = root / LIVE_DB_GZ_PATH
    wal = Path(f"{db}-wal")
    if wal.exists() and wal.stat().st_size > 0:
        raise StateLiveError(f"{wal} is not empty: checkpoint the database before storing it")
    tables = check_integrity(db)

    tmp = gz.with_name(f"{gz.name}.tmp")
    try:
        with tmp.open("wb") as dst:
            proc = subprocess.run([*GZIP_COMMAND, "-c", "--", str(db)], stdout=dst, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", errors="replace").strip()
            raise StateLiveError(f"{' '.join(GZIP_COMMAND)} failed on {db}: {detail}")
        with db.open("rb") as raw:
            db_size, db_sha256 = _copy(raw)
        try:
            with gzip.open(tmp, "rb") as unzipped:
                round_trip = _copy(unzipped)
        except (EOFError, OSError, zlib.error) as exc:
            raise StateLiveError(f"the new {gz.name} does not decompress: {exc}") from exc
        if round_trip != (db_size, db_sha256):
            raise StateLiveError(f"the new {gz.name} does not decompress to {db}")
        os.replace(tmp, gz)
    finally:
        tmp.unlink(missing_ok=True)

    _git(root, "add", "-f", "--", LIVE_DB_GZ_PATH)
    # Not `git rm --cached`: after `git read-tree` of a commit from before the compression, the staged
    # database matches neither HEAD nor the working tree, and `git rm --cached` refuses to drop it.
    _git(root, "update-index", "--force-remove", "--", LIVE_DB_PATH)
    return {
        "db_path": str(db),
        "gz_path": str(gz),
        "size_bytes": db_size,
        "gz_size_bytes": gz.stat().st_size,
        "sha256": db_sha256,
        "tables": tables,
    }


def _workflow_message(text: str) -> str:
    """Escapes a GitHub Actions workflow-command message so a multi-line error stays one annotation."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.storage.state_live",
        description=f"Store or restore the live audit database as {LIVE_DB_GZ_PATH} in state-live.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    restore_cmd = commands.add_parser("restore", help=f"Restore {LIVE_DB_PATH} from a state-live commit.")
    restore_cmd.add_argument("commit", help="state-live commit (SHA or ref) to restore from")
    commands.add_parser("stage", help=f"Compress {LIVE_DB_PATH} into the index as {LIVE_DB_GZ_PATH}.")
    args = parser.parse_args(argv)

    try:
        if args.command == "restore":
            info = restore_live_db(args.commit)
            if not info["compressed"]:
                print(
                    f"::notice::{args.commit} has no {LIVE_DB_GZ_PATH} yet (written before the compression); "
                    f"restored the uncompressed {LIVE_DB_PATH}."
                )
            print(
                f"Restored {LIVE_DB_PATH} from {args.commit}:{info['source_path']}: {info['size_bytes']} bytes, "
                f"sha256 {info['sha256']}, integrity_check ok ({info['tables']} tables)."
            )
        else:
            info = stage_live_db()
            print(
                f"Staged {LIVE_DB_GZ_PATH} ({' '.join(GZIP_COMMAND)}): {info['size_bytes']} -> "
                f"{info['gz_size_bytes']} bytes, sha256 {info['sha256']}, integrity_check ok "
                f"({info['tables']} tables); {LIVE_DB_PATH} dropped from the index."
            )
    except (StateLiveError, OSError) as exc:
        print(f"::error::{_workflow_message(str(exc))}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
