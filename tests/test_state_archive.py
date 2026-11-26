"""Tests for the daily immutable database archive (`src/storage/state_archive.py`)."""

from __future__ import annotations

from datetime import date
import gzip
import hashlib
import json
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
from src.storage.state_archive import (
    IMMUTABLE_TABLES,
    RELEASE_TAG,
    ContinuityViolationError,
    GhReleaseStore,
    HistoryBranch,
    StateArchiveError,
    archive_snapshot,
    asset_name,
    main,
    reconstruct,
    table_fingerprints,
    verify_immutable_continuity,
    verify_window,
)
from src.storage.state_live import LIVE_DB_GZ_PATH
from tests.helpers import PROJECT_ROOT


class FakeReleaseStore:
    """In-memory / directory-backed stand-in for GitHub Release `db-archive` (never clobbers)."""

    def __init__(self, root: Path) -> None:
        self.root = root / "release_assets"
        self.created = False
        self.uploads: list[str] = []

    def ensure_release(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.created = True

    def asset_names(self) -> set[str]:
        if not self.root.exists():
            return set()
        return {p.name for p in self.root.iterdir() if p.is_file()}

    def upload(self, path: Path) -> None:
        self.ensure_release()
        dest = self.root / path.name
        if dest.exists():
            raise StateArchiveError(f"refusing to overwrite existing asset {path.name}")
        shutil.copyfile(path, dest)
        self.uploads.append(path.name)

    def download(self, name: str, dest_dir: Path) -> Path:
        src = self.root / name
        if not src.is_file():
            raise StateArchiveError(f"missing asset {name}")
        dest = dest_dir / name
        shutil.copyfile(src, dest)
        return dest


@pytest.fixture()
def git_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    empty_cfg = tmp_path / "empty.gitconfig"
    empty_cfg.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_cfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "nba-intelligence-bot")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "nba-intelligence-bot@users.noreply.github.com")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _init_repo_pair(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    work.mkdir()
    _git(work, "init", "-q")
    _git(work, "remote", "add", "origin", remote.as_uri())
    return work, remote


def _seed_day1_db(path: Path) -> Path:
    db = DatabaseManager(path)
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO model_versions (
                model_version_id, model_family, market, train_start_date, train_end_date,
                trained_at, hyperparameters_json, is_active, approved_by
            ) VALUES ('mv_test', 'ensemble', 'moneyline', '2025-10-01', '2026-10-01', '2026-11-01T00:00:00Z', '{}', 1, 'test')
            """
        )
        conn.execute(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, features_available_at, source_provider, ingested_at
            ) VALUES
            ('G_STARTED', '2026-27', '2026-11-24', '2026-11-24T01:00:00Z', 'BOS', 'LAL', 'SCHEDULED',
             '2026-11-23T20:00:00Z', 'espn', '2026-11-23T20:00:00Z'),
            ('G_FUTURE', '2026-27', '2035-11-25', '2035-11-25T23:00:00Z', 'DEN', 'MIA', 'SCHEDULED',
             '2026-11-24T10:00:00Z', 'espn', '2026-11-24T10:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO odds_snapshots (
                odds_id, game_id, provider, market, selection, line_value, decimal_odds,
                counterpart_decimal_odds, captured_at, is_closing_line, source_type, fetched_at
            ) VALUES ('O_1', 'G_STARTED', 'pinnacle', 'moneyline', 'HOME', NULL, 2.05, 1.85,
                      '2026-11-23T22:00:00Z', 0, 'OBSERVED', '2026-11-23T22:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO quarantined_odds (odds_id, reason, quarantined_at)
            VALUES ('O_Q1', 'SYNTHETIC', '2026-11-23T22:05:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO predictions (
                prediction_id, game_id, market, selection, model_version_id,
                raw_probability, calibrated_probability, uncertainty_std, implied_prob_gross,
                implied_prob_fair, decimal_odds_used, odds_provider, odds_captured_at,
                ev_unit, ev_pct, emitted_at, features_snapshot_json
            ) VALUES ('P_1', 'G_STARTED', 'moneyline', 'HOME', 'mv_test', 0.55, 0.54, 0.04, 0.49,
                      0.48, 2.05, 'pinnacle', '2026-11-23T22:00:00Z', 0.107, 10.7, '2026-11-23T22:01:00Z', '{}')
            """
        )
        conn.execute(
            """
            INSERT INTO simulated_bets (
                bet_id, prediction_id, game_id, matchday_date, market, selection, line_value,
                decimal_odds, estimated_prob, estimated_ev, stake_pen, emitted_at, model_version_id, status
            ) VALUES ('B_1', 'P_1', 'G_STARTED', '2026-11-24', 'moneyline', 'HOME', NULL,
                      2.05, 0.54, 0.107, 2.0, '2026-11-23T22:01:00Z', 'mv_test', 'PENDING')
            """
        )
        conn.execute(
            """
            INSERT INTO decision_log (
                decision_id, game_id, matchday_date, market, selection, decision_type,
                reason_code, reason_detail, ev_pct, emitted_at, model_version_id
            ) VALUES ('D_1', 'G_STARTED', '2026-11-24', 'moneyline', 'HOME', 'BET_PLACED',
                      'QUALIFIED', 'ok', 10.7, '2026-11-23T22:01:00Z', 'mv_test')
            """
        )
        conn.execute(
            """
            INSERT INTO bankroll_ledger (
                timestamp, event_type, reference_bet_id, amount_delta_pen,
                settled_bankroll_pen, pending_exposure_pen, available_balance_pen
            ) VALUES ('2026-11-23T22:01:00Z', 'BET_RESERVED', 'B_1', 0.0, 100.0, 2.0, 98.0)
            """
        )
        conn.execute(
            """
            INSERT INTO shadow_candidates (
                shadow_id, prediction_id, game_id, matchday_date, market, selection, line_value,
                model_version_id, odds_provider, decimal_odds, raw_probability, calibrated_probability,
                ev_unit, ev_pct, hypothetical_kelly_stake_pen, decision_status, rejection_reason,
                status, emitted_at, source_type
            ) VALUES ('SH_1', 'P_1', 'G_STARTED', '2026-11-24', 'moneyline', 'HOME', NULL,
                      'mv_test', 'pinnacle', 2.05, 0.55, 0.54, 0.107, 10.7, 2.0, 'PLACED',
                      'QUALIFIED', 'PENDING', '2026-11-23T22:01:00Z', 'OBSERVED')
            """
        )
        conn.execute(
            """
            INSERT INTO run_manifests (
                run_id, commit_sha, model_version_id, ensemble_version, submodel_versions_json,
                config_hash, config_version, calibrator_metadata_json, seeds_json, data_cutoff_utc, created_at
            ) VALUES ('R_1', 'abc123', 'mv_test', 'v8', '{}', 'cfg1', '8.0', '{}', '{}',
                      '2026-11-24T00:00:00Z', '2026-11-24T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO player_prop_picks (
                prop_id, game_id, matchday_date, player_name, team, prop_category, line_value,
                selection, decimal_odds, projected_mean, projected_std, model_prob,
                conformal_p_low, conformal_p_high, ev_pct, ev_lower_bound_pct, stake_pen,
                kelly_stake_pen, usage_bump_pct, rationale, emitted_at, status
            ) VALUES ('PP_1', 'G_STARTED', '2026-11-24', 'Jayson Tatum', 'BOS', 'PTS', 26.5,
                      'OVER', 1.91, 29.0, 5.2, 0.58, 0.52, 0.64, 10.8, 3.0, 1.5, 1.5, 0.0,
                      'test prop', '2026-11-23T22:01:00Z', 'PENDING')
            """
        )
    db.checkpoint(truncate=True)
    return path


def _evolve_to_day2(day1_db: Path, day2_db: Path) -> Path:
    shutil.copyfile(day1_db, day2_db)
    db = DatabaseManager(day2_db)
    with db.connect() as conn:
        # Lawful updates: started game gets FINAL score (timestamps unchanged), unstarted game updates timestamp,
        # pending bet & shadow candidate settle, append-only tables gain new rows.
        conn.execute(
            "UPDATE games SET status = 'FINAL', home_score = 112, away_score = 104, result_recorded_at = '2026-11-24T04:00:00Z' "
            "WHERE game_id = 'G_STARTED'"
        )
        conn.execute(
            "UPDATE games SET features_available_at = '2026-11-25T12:00:00Z', ingested_at = '2026-11-25T12:00:00Z' "
            "WHERE game_id = 'G_FUTURE'"
        )
        conn.execute(
            "UPDATE simulated_bets SET status = 'WON', net_profit_pen = 2.10, bankroll_after_pen = 102.10, "
            "actual_result_summary = '112-104', settled_at = '2026-11-24T04:05:00Z' WHERE bet_id = 'B_1'"
        )
        conn.execute(
            "UPDATE shadow_candidates SET status = 'WON', hypothetical_unit_profit = 1.05, "
            "settled_at = '2026-11-24T04:05:00Z' WHERE shadow_id = 'SH_1'"
        )
        conn.execute(
            "UPDATE player_prop_picks SET status = 'WON', actual_stat = 31.0, net_profit_pen = 1.365, "
            "bankroll_after_pen = 101.365, actual_result_summary = '31 PTS', settled_at = '2026-11-24T04:05:00Z' "
            "WHERE prop_id = 'PP_1'"
        )
        conn.execute(
            """
            INSERT INTO bankroll_ledger (
                timestamp, event_type, reference_bet_id, amount_delta_pen,
                settled_bankroll_pen, pending_exposure_pen, available_balance_pen
            ) VALUES ('2026-11-24T04:05:00Z', 'BET_SETTLED', 'B_1', 2.10, 102.10, 0.0, 102.10)
            """
        )
        conn.execute(
            """
            INSERT INTO odds_snapshots (
                odds_id, game_id, provider, market, selection, line_value, decimal_odds,
                counterpart_decimal_odds, captured_at, is_closing_line, source_type, fetched_at
            ) VALUES ('O_2', 'G_FUTURE', 'pinnacle', 'moneyline', 'AWAY', NULL, 2.20, 1.72,
                      '2026-11-25T12:00:00Z', 0, 'OBSERVED', '2026-11-25T12:00:00Z')
            """
        )
    db.checkpoint(truncate=True)
    return day2_db


def _gz(db_path: Path, out_gz: Path) -> Path:
    out_gz.write_bytes(gzip.compress(db_path.read_bytes(), compresslevel=6, mtime=0))
    return out_gz


def _tamper_db(src_db: Path, dst_db: Path, sql: str) -> Path:
    """Copies `src_db` to `dst_db`, drops triggers, and applies tampering SQL directly."""
    shutil.copyfile(src_db, dst_db)
    conn = sqlite3.connect(dst_db)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        for (trig,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall():
            conn.execute(f'DROP TRIGGER IF EXISTS "{trig}"')
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()
    return dst_db


# --- End-to-end archive, idempotency, reconstruct, verify-window ------------------------------------


def test_archive_reconstruct_and_verify_window_end_to_end(tmp_path: Path, git_env: None) -> None:
    work, _ = _init_repo_pair(tmp_path)
    store = FakeReleaseStore(tmp_path)
    history = HistoryBranch(repo_root=work)

    day1_db = _seed_day1_db(tmp_path / "d1.sqlite3")
    day1_gz = _gz(day1_db, tmp_path / "d1.sqlite3.gz")
    m1 = archive_snapshot(
        day1_gz,
        "2026-11-24",
        source_commit="1111111",
        committed_at="2026-11-24T12:00:00Z",
        store=store,
        history=history,
    )
    assert store.created is True
    assert m1["asset_name"] == asset_name("2026-11-24")
    assert m1["continuity"] == {"previous_snapshot": None, "ok": True, "violations": []}
    assert m1["tables"]["decision_log"]["immutable"] is True
    assert m1["tables"]["bankroll_ledger"]["immutable"] is True
    assert m1["tables"]["quarantined_odds"]["immutable"] is True
    tip1 = history.fetch()
    assert tip1 is not None

    # Idempotent: archiving the same UTC day again does not upload or advance state-history
    m1_again = archive_snapshot(
        day1_gz,
        "2026-11-24",
        source_commit="2222222",
        committed_at="2026-11-24T18:00:00Z",
        store=store,
        history=history,
    )
    assert m1_again["skipped"] is True
    assert history.fetch() == tip1
    assert len(store.uploads) == 1

    # Day 2: lawful evolution appends child commit on state-history (linear parented chain)
    day2_db = _evolve_to_day2(day1_db, tmp_path / "d2.sqlite3")
    day2_gz = _gz(day2_db, tmp_path / "d2.sqlite3.gz")
    m2 = archive_snapshot(
        day2_gz,
        "2026-11-25",
        source_commit="3333333",
        committed_at="2026-11-25T15:00:00Z",
        store=store,
        history=history,
    )
    assert m2["continuity"] == {"previous_snapshot": "2026-11-24", "ok": True, "violations": []}
    tip2 = history.fetch()
    assert tip2 is not None and tip2 != tip1
    assert _git(work, "rev-parse", f"{tip2}^") == tip1  # append-only child of tip1

    ledger_raw = history.read(tip2, "ledger.jsonl")
    assert ledger_raw is not None and ledger_raw.endswith("\n")
    ledger_lines = [json.loads(line) for line in ledger_raw.splitlines()]
    assert [entry["snapshot_date"] for entry in ledger_lines] == ["2026-11-24", "2026-11-25"]
    assert all(entry["continuity_ok"] is True for entry in ledger_lines)

    # Reconstruct both days and verify exact bytes (and stale -wal cleanup)
    out1 = tmp_path / "out" / "2026-11-24.sqlite3"
    out1.parent.mkdir(parents=True)
    Path(f"{out1}-wal").write_bytes(b"stale wal bytes")
    reconstruct("2026-11-24", out1, store=store, history=history)
    assert out1.read_bytes() == day1_db.read_bytes()
    assert not Path(f"{out1}-wal").exists()

    out2 = tmp_path / "out" / "2026-11-25.sqlite3"
    reconstruct("2026-11-25", out2, store=store, history=history)
    assert out2.read_bytes() == day2_db.read_bytes()

    # verify_window across 30 days passes
    report = verify_window(30, store=store, history=history, today=date(2026, 11, 26))
    assert report == {
        "snapshots": ["2026-11-24", "2026-11-25"],
        "pairs": [{"older": "2026-11-24", "newer": "2026-11-25", "violations": []}],
        "ok": True,
    }


# --- Tampering, deletion, corruption & fail-closed guards -------------------------------------------


@pytest.mark.parametrize(
    ("label", "tamper_sql", "expected_match"),
    [
        ("delete_odds", "DELETE FROM odds_snapshots WHERE odds_id = 'O_1';", "odds_snapshots: row .* deleted"),
        ("edit_odds", "UPDATE odds_snapshots SET decimal_odds = 3.50 WHERE odds_id = 'O_1';", "odds_snapshots: row .* modified"),
        ("delete_decision", "DELETE FROM decision_log WHERE decision_id = 'D_1';", "decision_log: row .* deleted"),
        ("edit_bankroll", "UPDATE bankroll_ledger SET settled_bankroll_pen = 500.0 WHERE entry_id = 1;", "bankroll_ledger: row .* modified"),
        ("delete_quarantine", "DELETE FROM quarantined_odds WHERE odds_id = 'O_Q1';", "quarantined_odds: row .* deleted"),
        ("edit_pending_bet_odds", "UPDATE simulated_bets SET decimal_odds = 4.0 WHERE bet_id = 'B_1';", "simulated_bets: row .* modified"),
        ("edit_pending_prop_odds", "UPDATE player_prop_picks SET decimal_odds = 2.50 WHERE prop_id = 'PP_1';", "player_prop_picks: row .* modified"),
        ("edit_pending_prop_selection", "UPDATE player_prop_picks SET selection = 'UNDER' WHERE prop_id = 'PP_1';", "player_prop_picks: row .* modified"),
        ("edit_pending_prop_stake", "UPDATE player_prop_picks SET stake_pen = 5.0 WHERE prop_id = 'PP_1';", "player_prop_picks: row .* modified"),
        ("delete_started_game", "DELETE FROM games WHERE game_id = 'G_STARTED';", "games: started game G_STARTED deleted"),
        (
            "rewrite_started_game_ts",
            "UPDATE games SET ingested_at = '2026-11-24T03:00:00Z' WHERE game_id = 'G_STARTED';",
            "games: started game G_STARTED rewrote",
        ),
        ("drop_immutable_table", "DROP TABLE predictions;", "predictions: table missing"),
    ],
)
def test_archive_fails_closed_on_immutable_tampering_without_uploading_or_advancing(
    tmp_path: Path, git_env: None, label: str, tamper_sql: str, expected_match: str
) -> None:
    work, _ = _init_repo_pair(tmp_path)
    store = FakeReleaseStore(tmp_path)
    history = HistoryBranch(repo_root=work)

    day1_db = _seed_day1_db(tmp_path / "d1.sqlite3")
    archive_snapshot(
        _gz(day1_db, tmp_path / "d1.sqlite3.gz"),
        "2026-11-24",
        source_commit="1111111",
        committed_at="2026-11-24T12:00:00Z",
        store=store,
        history=history,
    )
    tip_before = history.fetch()
    assets_before = store.asset_names()

    tampered_db = _tamper_db(day1_db, tmp_path / f"tampered_{label}.sqlite3", tamper_sql)
    tampered_gz = _gz(tampered_db, tmp_path / f"tampered_{label}.sqlite3.gz")
    with pytest.raises(ContinuityViolationError, match=expected_match):
        archive_snapshot(
            tampered_gz,
            "2026-11-25",
            source_commit="badsha",
            committed_at="2026-11-25T12:00:00Z",
            store=store,
            history=history,
        )
    # Fail-closed: neither Release asset nor state-history changed!
    assert store.asset_names() == assets_before
    assert history.fetch() == tip_before


def test_settled_bet_tampering_detected_between_day2_and_day3(tmp_path: Path) -> None:
    day1 = _seed_day1_db(tmp_path / "d1.sqlite3")
    day2 = _evolve_to_day2(day1, tmp_path / "d2.sqlite3")
    day3_tampered = _tamper_db(
        day2,
        tmp_path / "d3_bad.sqlite3",
        "UPDATE simulated_bets SET net_profit_pen = 99.0 WHERE bet_id = 'B_1';",
    )
    violations = verify_immutable_continuity(day2, day3_tampered, older_taken_at="2026-11-25T15:00:00Z")
    assert any("simulated_bets: row ['B_1'] modified" in v for v in violations)


def test_corrupt_release_asset_or_missing_asset_fails_closed(tmp_path: Path, git_env: None) -> None:
    work, _ = _init_repo_pair(tmp_path)
    store = FakeReleaseStore(tmp_path)
    history = HistoryBranch(repo_root=work)

    day1_db = _seed_day1_db(tmp_path / "d1.sqlite3")
    day1_gz = _gz(day1_db, tmp_path / "d1.sqlite3.gz")
    archive_snapshot(
        day1_gz,
        "2026-11-24",
        source_commit="1111111",
        committed_at="2026-11-24T12:00:00Z",
        store=store,
        history=history,
    )

    # Corrupt asset bytes in store -> SHA-256 mismatch on reconstruct
    asset_file = store.root / asset_name("2026-11-24")
    original = asset_file.read_bytes()
    asset_file.write_bytes(original[:-10] + b"CORRUPTED!")
    out = tmp_path / "out.sqlite3"
    out.write_bytes(b"keep-me")
    with pytest.raises(StateArchiveError, match="SHA-256"):
        reconstruct("2026-11-24", out, store=store, history=history)
    assert out.read_bytes() == b"keep-me"

    # Missing asset when manifest exists -> idempotency check fails closed
    asset_file.unlink()
    with pytest.raises(StateArchiveError, match="missing from db-archive"):
        archive_snapshot(
            day1_gz,
            "2026-11-24",
            source_commit="1111111",
            committed_at="2026-11-24T12:00:00Z",
            store=store,
            history=history,
        )

    # Existing asset without manifest -> refuses to overwrite
    orphan = store.root / asset_name("2026-11-25")
    orphan.write_bytes(day1_gz.read_bytes())
    asset_file.write_bytes(original)
    with pytest.raises(StateArchiveError, match="refusing to overwrite"):
        archive_snapshot(
            day1_gz,
            "2026-11-25",
            source_commit="2222222",
            committed_at="2026-11-25T12:00:00Z",
            store=store,
            history=history,
        )


def test_history_branch_preserves_whitespace_and_rejects_non_ff_push(tmp_path: Path, git_env: None) -> None:
    work, _ = _init_repo_pair(tmp_path)
    history = HistoryBranch(repo_root=work)
    assert history.fetch() is None
    assert history.read(None, "ledger.jsonl") is None

    content = "  leading and trailing whitespace\nsecond line\n\n"
    c1 = history.append(None, {"notes.txt": content}, "init")
    assert history.read(c1, "notes.txt") == content
    assert history.read(c1, "does-not-exist.txt") is None

    # Advance remote to c2, then try to push a sibling commit with parent=c1 -> must fail (no --force!)
    c2 = history.append(c1, {"notes.txt": "v2\n"}, "advance")
    assert history.fetch() == c2
    with pytest.raises(StateArchiveError, match="git push"):
        history.append(c1, {"notes.txt": "diverged\n"}, "non-ff attempt")
    assert history.fetch() == c2


def test_verify_window_fails_closed_when_empty_or_invalid_days(tmp_path: Path, git_env: None) -> None:
    work, _ = _init_repo_pair(tmp_path)
    store = FakeReleaseStore(tmp_path)
    history = HistoryBranch(repo_root=work)
    with pytest.raises(StateArchiveError, match="days must be >= 1"):
        verify_window(0, store=store, history=history)
    with pytest.raises(StateArchiveError, match="no archived snapshots found"):
        verify_window(30, store=store, history=history)


def test_gh_release_store_uses_target_main_never_clobbers_and_paginates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[:3] == ["gh", "release", "view"] and "tagName" in cmd:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="release not found")
        if cmd[:3] == ["gh", "release", "view"] and "apiUrl" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="https://api.github.com/repos/Drewks/nba-betting-intelligence/releases/42\n", stderr=""
            )
        if cmd[:3] == ["gh", "api", "--paginate"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="nba_intelligence-2026-11-24.sqlite3.gz\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    store = GhReleaseStore(tag=RELEASE_TAG, repo_root=tmp_path)
    store.ensure_release()
    create_cmd = next(c for c in calls if c[:3] == ["gh", "release", "create"])
    assert "--target" in create_cmd and create_cmd[create_cmd.index("--target") + 1] == "main"
    assert "--latest=false" in create_cmd

    names = store.asset_names()
    assert names == {"nba_intelligence-2026-11-24.sqlite3.gz"}
    assert any("--paginate" in c for c in calls)

    dummy = tmp_path / "nba_intelligence-2026-11-25.sqlite3.gz"
    dummy.write_bytes(b"gz")
    store.upload(dummy)
    upload_cmd = next(c for c in calls if c[:3] == ["gh", "release", "upload"])
    assert "--clobber" not in upload_cmd


def test_cli_stdlib_only_and_date_validation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # -S disables site-packages: proves src/storage/state_archive.py is strictly stdlib-only
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}
    proc = subprocess.run(
        [sys.executable, "-S", "-m", "src.storage.state_archive", "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "reconstruct" in proc.stdout and "verify-window" in proc.stdout

    # Invalid date fails closed
    rc = main(["reconstruct", "../bad", "--out", str(tmp_path / "x.sqlite3")])
    assert rc == 1
    assert "::error::invalid snapshot date" in capsys.readouterr().out


def test_cli_archive_gz_backfill_and_ref_modes(
    tmp_path: Path, git_env: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    work, _ = _init_repo_pair(tmp_path)
    store = FakeReleaseStore(tmp_path)
    history = HistoryBranch(repo_root=work)
    monkeypatch.chdir(work)
    monkeypatch.setattr("src.storage.state_archive.GhReleaseStore", lambda: store)
    monkeypatch.setattr("src.storage.state_archive.HistoryBranch", lambda: history)

    # 1. Backfill Day 1 via --gz + --source-commit + --committed-at
    day1_db = _seed_day1_db(tmp_path / "d1.sqlite3")
    day1_gz = _gz(day1_db, tmp_path / "d1.sqlite3.gz")
    rc = main(
        [
            "archive",
            "--date",
            "2026-11-24",
            "--gz",
            str(day1_gz),
            "--source-commit",
            "run-45513493079",
            "--committed-at",
            "2026-11-24T23:53:43Z",
        ]
    )
    assert rc == 0
    assert "Archived nba_intelligence-2026-11-24.sqlite3.gz" in capsys.readouterr().out

    # 2. Archive Day 2 via --ref pointing at a real commit holding data/nba_intelligence.sqlite3.gz
    day2_db = _evolve_to_day2(day1_db, tmp_path / "d2.sqlite3")
    day2_gz = _gz(day2_db, tmp_path / "d2.sqlite3.gz")
    blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"], cwd=work, input=day2_gz.read_bytes(), check=True, capture_output=True
    ).stdout.decode().strip()
    _git(work, "read-tree", "--empty")
    _git(work, "update-index", "--add", "--cacheinfo", f"100644,{blob},{LIVE_DB_GZ_PATH}")
    ref_commit = _git(work, "commit-tree", _git(work, "write-tree"), "-m", "state-live day2")
    _git(work, "update-ref", "refs/remotes/origin/state-live", ref_commit)

    rc = main(["archive", "--date", "2026-11-25", "--ref", ref_commit])
    assert rc == 0
    assert "continuity vs 2026-11-24: ok" in capsys.readouterr().out

    # 3. CLI reconstruct & verify-window
    out_db = tmp_path / "rebuilt.sqlite3"
    assert main(["reconstruct", "2026-11-25", "--out", str(out_db)]) == 0
    assert out_db.read_bytes() == day2_db.read_bytes()
    capsys.readouterr()

    # 4. Tampered Day 3 via --gz returns exit code 2 without uploading
    bad_db = _tamper_db(day2_db, tmp_path / "d3_bad.sqlite3", "DELETE FROM decision_log WHERE decision_id = 'D_1';")
    bad_gz = _gz(bad_db, tmp_path / "d3_bad.sqlite3.gz")
    rc = main(["archive", "--date", "2026-11-26", "--gz", str(bad_gz), "--committed-at", "2026-11-26T12:00:00Z"])
    assert rc == 2
    assert "::error::Immutable continuity violated" in capsys.readouterr().out
    assert asset_name("2026-11-26") not in store.asset_names()


def test_table_fingerprints_are_deterministic_and_cover_audit_tables(tmp_path: Path) -> None:
    db = _seed_day1_db(tmp_path / "fp.sqlite3")
    fp1 = table_fingerprints(db)
    fp2 = table_fingerprints(db)
    assert fp1 == fp2
    for required in ("odds_snapshots", "quarantined_odds", "predictions", "decision_log", "bankroll_ledger", "simulated_bets"):
        assert required in IMMUTABLE_TABLES
        assert fp1[required]["immutable"] is True
        assert fp1[required]["row_count"] >= 1
        assert len(fp1[required]["content_sha256"]) == 64


def test_cloud_workflow_wires_step_7d_preserving_t018_permissions() -> None:
    wf_path = PROJECT_ROOT / ".github" / "workflows" / "nba_cloud_automation.yml"
    wf = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    job = wf["jobs"]["run-nba-intelligence-cycle"]
    # T-018 invariant: exact permissions dict equality
    assert job["permissions"] == {"contents": "write"}

    steps = job["steps"]
    names = [str(s.get("name", "")) for s in steps]
    idx_7 = next(i for i, n in enumerate(names) if n.startswith("7. Guardar estado runtime"))
    idx_7c = next(i for i, n in enumerate(names) if n.startswith("7c."))
    idx_7d = next(i for i, n in enumerate(names) if n.startswith("7d."))
    idx_7b = next(i for i, n in enumerate(names) if n.startswith("7b."))
    assert idx_7 < idx_7c < idx_7d < idx_7b

    step_7_run = str(steps[idx_7]["run"])
    assert 'echo "STATE_LIVE_HEAD_SHA=${STATE_LIVE_HEAD_SHA}" >> "$GITHUB_ENV"' in step_7_run
    assert 'STATE_LIVE_HEAD_SHA="${STATE_BASE_SHA}"' in step_7_run
    assert 'STATE_LIVE_HEAD_SHA="${NEW_COMMIT}"' in step_7_run

    step_7d = steps[idx_7d]
    assert step_7d.get("continue-on-error") is not True
    assert step_7d["env"]["GH_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"
    assert 'python3 -m src.storage.state_archive archive --ref "${STATE_LIVE_HEAD_SHA:-origin/state-live}"' in str(
        step_7d["run"]
    )
    assert hashlib.sha256(LIVE_DB_GZ_PATH.encode()).hexdigest()  # sanity import check
