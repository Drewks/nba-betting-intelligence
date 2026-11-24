"""
Regressions for the size of the live database in state-live (2026-11-24).

The main cycle's push printed GitHub's warning "GH001: Large files detected ... data/nba_intelligence.sqlite3
is 57.08 MB". The database grew ~14 MB a week (46.0 MB on 2026-11-17, 59.9 MB on 2026-11-24) and GitHub
rejects a push holding a file over 100 MB, which would have stopped every cycle around 2026-12-17.
state-live now stores it as data/nba_intelligence.sqlite3.gz (gzip -6 -n: 7.9 MB), and every workflow
restores it through src/storage/state_live.py, which falls back to the uncompressed file of commits from
before the change and fails closed unless PRAGMA integrity_check returns ok.
"""

from __future__ import annotations

from collections.abc import Callable
import gzip
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any

import pytest
import yaml

from src.storage.db import DatabaseManager
from src.storage.state_live import (
    LIVE_DB_GZ_PATH,
    LIVE_DB_PATH,
    StateLiveError,
    check_integrity,
    restore_live_db,
    stage_live_db,
)
from tests.helpers import PROJECT_ROOT

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
RESTORE = "python3 -m src.storage.state_live restore"
STAGE = "python3 -m src.storage.state_live stage"
needs_gzip = pytest.mark.skipif(shutil.which("gzip") is None, reason="the gzip command is not installed")


@pytest.fixture()
def git_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs git without the user's or system's config (hooks, signing) and with a fixed identity."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    empty_config = tmp_path / "empty.gitconfig"
    empty_config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "nba-intelligence-bot")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "nba-intelligence-bot@users.noreply.github.com")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _git_bytes(cwd: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True).stdout


def _make_db(path: Path, *game_ids: str) -> bytes:
    """A database with the production schema and the given games; returns its bytes (WAL checkpointed)."""
    db = DatabaseManager(path)
    for game_id in game_ids:
        db.execute_insert(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, features_available_at, source_provider, ingested_at
            ) VALUES (?, '2026-27', '2026-11-24', '2026-11-25T00:30:00Z', 'MIN', 'POR', 'SCHEDULED',
                      '2026-11-24T12:00:00Z', 'espn', '2026-11-24T12:00:00Z')
            """,
            (game_id,),
        )
    db.checkpoint(truncate=True)
    assert not Path(f"{path}-wal").exists()
    return path.read_bytes()


def _game_ids(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {str(row[0]) for row in conn.execute("SELECT game_id FROM games")}
    finally:
        conn.close()


def _runner(tmp_path: Path, name: str, remote: Path) -> Path:
    """A fresh workflow checkout whose `origin` is the temporary bare repository."""
    work = tmp_path / name
    work.mkdir()
    _git(work, "init", "-q")
    _git(work, "remote", "add", "origin", remote.as_uri())
    return work


def _fetch_state_live(work: Path) -> str:
    _git(work, "fetch", "-q", "--depth=1", "origin", "state-live")
    return _git(work, "rev-parse", "origin/state-live")


def _push_state_live(work: Path, message: str, base: str | None) -> str:
    """write-tree, parentless commit-tree and the guarded push, as the workflows do."""
    tree = _git(work, "write-tree")
    commit = _git(work, "commit-tree", tree, "-m", message)
    lease = [f"--force-with-lease=refs/heads/state-live:{base}"] if base else []
    _git(work, "push", "-q", "--no-verify", *lease, "origin", f"{commit}:refs/heads/state-live")
    return commit


def _commit_files(work: Path, files: dict[str, bytes]) -> str:
    """A commit holding exactly `files` (any bytes), without touching the working tree."""
    _git(work, "read-tree", "--empty")
    for path, data in files.items():
        blob = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"], cwd=work, input=data, check=True, capture_output=True
        ).stdout.decode().strip()
        _git(work, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}")
    return _git(work, "commit-tree", _git(work, "write-tree"), "-m", "fixture")


# --- Save and restore through a temporary bare repository ------------------------------------------


@needs_gzip
def test_save_then_restore_round_trips_the_database_byte_for_byte(tmp_path: Path, git_env: None) -> None:
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))

    # state-live as it is before the change: only the uncompressed database
    old = _runner(tmp_path, "old_cycle", remote)
    old_bytes = _make_db(old / LIVE_DB_PATH, "G_OLD")
    (old / "SEGUIMIENTO_APUESTAS.md").write_text("# Seguimiento\n", encoding="utf-8")
    _git(old, "add", "-f", LIVE_DB_PATH, "SEGUIMIENTO_APUESTAS.md")
    old_commit = _push_state_live(old, "old-style state-live", None)

    # First run after the merge: the fallback restores the uncompressed file
    first = _runner(tmp_path, "first_cycle", remote)
    base = _fetch_state_live(first)
    assert base == old_commit
    info = restore_live_db(base, repo_root=first)
    assert info["source_path"] == LIVE_DB_PATH and info["compressed"] is False
    assert (first / LIVE_DB_PATH).read_bytes() == old_bytes

    # The run adds a game and saves onto state-live's own tree (as the closing loop does)
    saved = _make_db(first / LIVE_DB_PATH, "G_NEW")
    _git(first, "read-tree", base)
    staged = stage_live_db(repo_root=first)
    assert staged["sha256"] == hashlib.sha256(saved).hexdigest()
    new_commit = _push_state_live(first, "compressed state-live", base)
    # The same commit removes the uncompressed file from the tree and keeps the other state files
    assert _git(first, "ls-tree", "-r", "--name-only", new_commit).splitlines() == [
        "SEGUIMIENTO_APUESTAS.md",
        LIVE_DB_GZ_PATH,
    ]
    gz_blob = _git_bytes(first, "cat-file", "blob", f"{new_commit}:{LIVE_DB_GZ_PATH}")
    assert gz_blob[:2] == b"\x1f\x8b" and len(gz_blob) < len(saved)
    assert gz_blob[3] & 0x08 == 0 and gz_blob[4:8] == b"\0\0\0\0"  # -n: no file name, no timestamp

    # The next run decompresses the .gz and gets exactly the database that was saved
    nxt = _runner(tmp_path, "next_cycle", remote)
    assert _fetch_state_live(nxt) == new_commit
    info = restore_live_db(new_commit, repo_root=nxt)
    assert info["source_path"] == LIVE_DB_GZ_PATH and info["compressed"] is True
    assert (nxt / LIVE_DB_PATH).read_bytes() == saved
    assert info["sha256"] == hashlib.sha256(saved).hexdigest()
    assert check_integrity(nxt / LIVE_DB_PATH) == info["tables"] > 0
    assert _game_ids(nxt / LIVE_DB_PATH) == {"G_OLD", "G_NEW"}


@needs_gzip
def test_stage_is_deterministic_and_writes_what_gzip_6_n_writes(tmp_path: Path, git_env: None) -> None:
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    _make_db(work / LIVE_DB_PATH, "G_1")
    _git(work, "add", "-f", LIVE_DB_PATH)

    stage_live_db(repo_root=work)
    first_blob = _git(work, "rev-parse", f":{LIVE_DB_GZ_PATH}")
    # An unchanged database keeps its blob, so step 7's no-change check still sees no change
    stage_live_db(repo_root=work)
    assert _git(work, "rev-parse", f":{LIVE_DB_GZ_PATH}") == first_blob
    expected = subprocess.run(
        ["gzip", "-6", "-n", "-c", str(work / LIVE_DB_PATH)], check=True, capture_output=True
    ).stdout
    assert (work / LIVE_DB_GZ_PATH).read_bytes() == expected
    assert _git(work, "ls-files", "--", LIVE_DB_PATH) == ""
    assert _git(work, "ls-files", "--", LIVE_DB_GZ_PATH) == LIVE_DB_GZ_PATH


def test_stage_refuses_a_database_whose_wal_is_not_checkpointed(tmp_path: Path, git_env: None) -> None:
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    _make_db(work / LIVE_DB_PATH, "G_1")
    conn = sqlite3.connect(work / LIVE_DB_PATH)
    try:
        conn.execute("PRAGMA wal_autocheckpoint = 0")
        conn.execute("CREATE TABLE written_after_the_checkpoint (x)")
        conn.commit()
        with pytest.raises(StateLiveError, match="checkpoint"):
            stage_live_db(repo_root=work)
    finally:
        conn.close()
    assert not (work / LIVE_DB_GZ_PATH).exists()
    assert _git(work, "ls-files") == ""


# --- Restore fails closed ----------------------------------------------------------------------------


def _corrupt_pages(db_bytes: bytes) -> bytes:
    page_size = int.from_bytes(db_bytes[16:18], "big")
    broken = bytearray(db_bytes)
    broken[page_size : 3 * page_size] = b"\xa5" * (2 * page_size)
    return bytes(broken)


def _index_out_of_sync(path: Path) -> bytes:
    """A database that opens and reads fine but whose PRAGMA integrity_check lists missing index rows."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE t (a INTEGER, b INTEGER);
        CREATE INDEX t_a ON t (a);
        CREATE INDEX t_b ON t (b);
        INSERT INTO t VALUES (1, 30), (2, 20), (3, 10);
        """
    )
    roots = dict(conn.execute("SELECT name, rootpage FROM sqlite_master WHERE type = 'index'").fetchall())
    conn.execute("PRAGMA writable_schema = ON")
    try:
        conn.execute("UPDATE sqlite_master SET rootpage = ? WHERE name = 't_a'", (roots["t_b"],))
        conn.execute("UPDATE sqlite_master SET rootpage = ? WHERE name = 't_b'", (roots["t_a"],))
    except sqlite3.OperationalError:
        conn.close()
        pytest.skip("this SQLite build does not allow writable_schema (defensive mode)")
    conn.commit()
    conn.close()
    return path.read_bytes()


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("index_out_of_sync", "PRAGMA integrity_check of .* returned: row 1 missing from index"),
        ("corrupt_pages", "not a readable SQLite database: database disk image is malformed"),
        ("not_a_database", "not a readable SQLite database"),
        ("empty_database", "has no tables"),
        ("truncated_gz", "cannot decompress"),
        ("not_gzip", "cannot decompress"),
        ("bad_gz_next_to_good_raw", "cannot decompress"),
        ("no_database", "holds neither"),
    ],
)
def test_restore_fails_closed_and_leaves_the_target_as_it_was(
    tmp_path: Path, git_env: None, case: str, error: str
) -> None:
    good = _make_db(tmp_path / "good.sqlite3", "G_1")
    files: dict[str, Callable[[], dict[str, bytes]]] = {
        "index_out_of_sync": lambda: {LIVE_DB_GZ_PATH: gzip.compress(_index_out_of_sync(tmp_path / "bad.sqlite3"))},
        "corrupt_pages": lambda: {LIVE_DB_GZ_PATH: gzip.compress(_corrupt_pages(good))},
        "not_a_database": lambda: {LIVE_DB_GZ_PATH: gzip.compress(b"not a database " * 500)},
        "empty_database": lambda: {LIVE_DB_GZ_PATH: gzip.compress(b"")},
        "truncated_gz": lambda: {LIVE_DB_GZ_PATH: gzip.compress(good)[:-64]},
        "not_gzip": lambda: {LIVE_DB_GZ_PATH: b"plain text, not gzip"},
        # A .gz that exists is never skipped for an older uncompressed copy
        "bad_gz_next_to_good_raw": lambda: {LIVE_DB_GZ_PATH: gzip.compress(good)[:-64], LIVE_DB_PATH: good},
        "no_database": lambda: {"SEGUIMIENTO_APUESTAS.md": b"# Seguimiento\n"},
    }
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    commit = _commit_files(work, files[case]())
    target = work / LIVE_DB_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b"previous database")

    with pytest.raises(StateLiveError, match=error):
        restore_live_db(commit, repo_root=work)
    assert target.read_bytes() == b"previous database"
    assert sorted(p.name for p in target.parent.iterdir()) == ["nba_intelligence.sqlite3"]


def test_restore_names_a_commit_that_was_not_fetched(tmp_path: Path, git_env: None) -> None:
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    with pytest.raises(StateLiveError, match="is not a commit of this repository"):
        restore_live_db("0123456789abcdef0123456789abcdef01234567", repo_root=work)
    assert not (work / "data").exists()


def test_restore_drops_a_leftover_wal_that_would_be_replayed(tmp_path: Path, git_env: None) -> None:
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    db_bytes = _make_db(tmp_path / "live.sqlite3", "G_1")
    commit = _commit_files(work, {LIVE_DB_GZ_PATH: gzip.compress(db_bytes)})

    # A -wal left next to the target by an earlier run, holding a table the state-live database lacks
    target = work / LIVE_DB_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(db_bytes)
    conn = sqlite3.connect(target)
    conn.execute("PRAGMA wal_autocheckpoint = 0")
    conn.execute("CREATE TABLE stale_wal_table (x)")
    conn.commit()
    stale_wal = Path(f"{target}-wal").read_bytes()
    conn.close()
    target.write_bytes(db_bytes)
    Path(f"{target}-wal").write_bytes(stale_wal)
    # Left in place, the next connection would replay it onto the restored database
    probe = tmp_path / "probe.sqlite3"
    probe.write_bytes(db_bytes)
    Path(f"{probe}-wal").write_bytes(stale_wal)
    with sqlite3.connect(probe) as probe_conn:
        assert probe_conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'stale_wal_table'").fetchone()
    probe_conn.close()

    restore_live_db(commit, repo_root=work)
    assert not Path(f"{target}-wal").exists()
    assert target.read_bytes() == db_bytes
    with sqlite3.connect(target) as restored:
        assert restored.execute("SELECT 1 FROM sqlite_master WHERE name = 'stale_wal_table'").fetchone() is None
    restored.close()


# --- Command line used by the workflows --------------------------------------------------------------


def test_cli_runs_with_the_standard_library_only_and_fails_closed(tmp_path: Path, git_env: None) -> None:
    """The weekly backtest restores before `uv sync`, with the runner's system python3."""
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    db_bytes = _make_db(tmp_path / "live.sqlite3", "G_1")
    old_style = _commit_files(work, {LIVE_DB_PATH: db_bytes})
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}

    def cli(*args: str) -> subprocess.CompletedProcess[str]:
        # -S: no site-packages, so any third-party import would fail here
        return subprocess.run(
            [sys.executable, "-S", "-m", "src.storage.state_live", *args],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    out = cli("restore", old_style)
    assert out.returncode == 0, out.stdout + out.stderr
    assert out.stdout.startswith(f"::notice::{old_style} has no {LIVE_DB_GZ_PATH} yet")
    assert "integrity_check ok" in out.stdout
    assert (work / LIVE_DB_PATH).read_bytes() == db_bytes

    if shutil.which("gzip") is not None:
        out = cli("stage")
        assert out.returncode == 0, out.stdout + out.stderr
        assert "gzip -6 -n" in out.stdout
        assert _git(work, "ls-files") == LIVE_DB_GZ_PATH

    broken = _commit_files(work, {LIVE_DB_GZ_PATH: b"plain text, not gzip"})
    out = cli("restore", broken)
    assert out.returncode == 1
    assert out.stdout.startswith("::error::cannot decompress")
    assert (work / LIVE_DB_PATH).read_bytes() == db_bytes


def test_sync_state_live_extracts_the_compressed_database(tmp_path: Path, git_env: None) -> None:
    from scripts.sync_state_live import extract_state_live_db, inspect_sqlite_summary

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    db_bytes = _make_db(tmp_path / "live.sqlite3", "G_1")
    commit = _commit_files(repo, {LIVE_DB_GZ_PATH: gzip.compress(db_bytes)})
    _git(repo, "update-ref", "refs/remotes/origin/state-live", commit)

    out_path = tmp_path / "local" / "nba_state_live.sqlite3"
    info = extract_state_live_db(out_path, repo_root=repo, fetch=False)
    assert info["source_commit_sha"] == commit
    assert info["source_path"] == LIVE_DB_GZ_PATH
    assert info["sha256"] == hashlib.sha256(db_bytes).hexdigest()
    assert out_path.read_bytes() == db_bytes
    summary = inspect_sqlite_summary(out_path)
    assert summary["sqlite_integrity_check"] == "ok"
    assert summary["live_source_of_truth"] == "origin/state-live:data/nba_intelligence.sqlite3.gz"


# --- Workflows ---------------------------------------------------------------------------------------


def _steps(workflow: str) -> list[dict[str, Any]]:
    wf = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    steps: list[dict[str, Any]] = next(iter(wf["jobs"].values()))["steps"]
    return steps


def _step(steps: list[dict[str, Any]], name_prefix: str) -> dict[str, Any]:
    return next(s for s in steps if str(s.get("name", "")).startswith(name_prefix))


def test_every_workflow_restores_the_database_through_the_helper() -> None:
    for workflow, base in (
        ("nba_cloud_automation.yml", "STATE_BASE_SHA"),
        ("closing_capture.yml", "BASE"),
        ("weekly_backtest.yml", "STATE_BASE_SHA"),
    ):
        raw = (WORKFLOWS / workflow).read_text(encoding="utf-8")
        assert f'{RESTORE} "${{{base}}}"' in raw, workflow
        for line in raw.splitlines():
            if LIVE_DB_PATH in line and LIVE_DB_GZ_PATH not in line:
                # No workflow checks out, adds or reads the uncompressed file from git any more
                assert not any(cmd in line for cmd in ("git checkout", "git add", "git show", "cat-file")), line

    restore = str(_step(_steps("nba_cloud_automation.yml"), "4b.")["run"])
    loop_paths = restore.split("for state_path in", 1)[1].split("; do", 1)[0]
    assert "nba_intelligence.sqlite3" not in loop_paths
    assert restore.index('STATE_BASE_SHA="$(git rev-parse origin/state-live)"') < restore.index(RESTORE)


def test_main_cycle_stores_the_gz_after_the_checkpoint_with_the_same_guards() -> None:
    steps = _steps("nba_cloud_automation.yml")
    names = [str(s.get("name", "")) for s in steps]
    checkpoint = next(i for i, n in enumerate(names) if n.startswith("6b."))
    save_idx = next(i for i, n in enumerate(names) if n.startswith("7. Guardar estado runtime"))
    backup_idx = next(i for i, n in enumerate(names) if n.startswith("7c."))
    assert "checkpoint(truncate=True)" in str(steps[checkpoint]["run"])
    assert checkpoint < save_idx < backup_idx

    save = str(steps[save_idx]["run"])
    assert save.count(STAGE) == 1
    assert save.index(STAGE) < save.index('TREE_SHA="$(git write-tree)"')
    add_line = next(line for line in save.splitlines() if line.strip().startswith("git add -f"))
    assert "nba_intelligence.sqlite3" not in add_line
    no_change_paths = save.split('git diff --quiet "${STATE_BASE_SHA}" "${TREE_SHA}" --', 1)[1].split("; then", 1)[0]
    assert LIVE_DB_GZ_PATH in no_change_paths.split()
    assert LIVE_DB_PATH not in no_change_paths.split()
    # Concurrency guards unchanged
    assert 'if [ "$(git rev-parse origin/state-live)" != "${STATE_BASE_SHA}" ]; then' in save
    assert (
        'git push --force-with-lease="refs/heads/state-live:${STATE_BASE_SHA}" origin "${NEW_COMMIT}:refs/heads/state-live"'
        in save
    )

    backup = steps[backup_idx]["with"]
    assert backup["name"] == "nba-state-live-db-backup"
    assert backup["path"] == LIVE_DB_GZ_PATH
    assert backup["if-no-files-found"] == "error"


def test_closing_loop_stores_the_gz_only_after_a_data_change() -> None:
    loop = "\n".join(str(s.get("run", "")) for s in _steps("closing_capture.yml"))
    restore = loop.index(f'{RESTORE} "${{BASE}}"')
    fingerprint_check = loop.index('if [ "${FP_BEFORE}" != "${FP_AFTER}" ]; then')
    read_tree = loop.index('git read-tree "${BASE}"')
    stage = loop.index(STAGE)
    write_tree = loop.index('TREE_SHA="$(git write-tree)"')
    push = loop.index('git push --force-with-lease="refs/heads/state-live:${BASE}"')
    assert restore < fingerprint_check < read_tree < stage < write_tree < push
    assert loop.count(STAGE) == 1
    # Concurrency guards unchanged
    assert 'wait_for_main_cycle || {' in loop
    assert 'if [ "$(git rev-parse origin/state-live)" = "${BASE}" ] && [ "$(main_cycle_busy)" = "0" ]; then' in loop


def test_weekly_backtest_restores_the_gz_and_carries_the_stored_blob_over() -> None:
    steps = _steps("weekly_backtest.yml")
    prep = str(_step(steps, "1.")["run"])
    assert prep.index('STATE_BASE_SHA="$(git rev-parse origin/state-live)"') < prep.index(RESTORE)
    # The report is written onto state-live's own tree, so the database is carried over as stored
    save = str(_step(steps, "4.")["run"])
    assert 'git read-tree "${STATE_BASE_SHA}"' in save
    assert "nba_intelligence" not in save
