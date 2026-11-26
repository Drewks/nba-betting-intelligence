"""Tests for the daily immutable database archive (`src/storage/state_archive.py`)."""

from __future__ import annotations

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
    """In-memory / directory-backed stand-in for GitHub Release `db-archive` (with rotation, never clobbers)."""

    def __init__(self, root: Path, *, max_assets: int = 900) -> None:
        self.base_root = root
        self.root = root / "release_assets"
        self.max_assets = max_assets
        self.created = False
        self.created_tags: set[str] = set()
        self.uploads: list[str] = []
        self.timestamps: dict[str, str] = {}

    def _dir_for(self, tag: str | None = None) -> Path:
        t = tag or RELEASE_TAG
        return self.root if t == RELEASE_TAG else self.base_root / f"release_assets_{t}"

    def ensure_release(self, tag: str | None = None) -> None:
        t = tag or RELEASE_TAG
        self._dir_for(t).mkdir(parents=True, exist_ok=True)
        self.created = True
        self.created_tags.add(t)

    def asset_timestamps(self, tag: str | None = None) -> dict[str, str]:
        d = self._dir_for(tag)
        if not d.exists():
            return {}
        return {
            p.name: self.timestamps.get(p.name, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            for p in d.iterdir()
            if p.is_file()
        }

    def asset_names(self, tag: str | None = None) -> set[str]:
        return set(self.asset_timestamps(tag))

    def select_upload_tag(self, name: str) -> tuple[str, dict[str, str]]:
        index = 1
        while True:
            t = RELEASE_TAG if index == 1 else f"{RELEASE_TAG}-{index}"
            if not self._dir_for(t).exists():
                return t, {}
            assets = self.asset_timestamps(t)
            if name in assets or len(assets) < self.max_assets:
                return t, assets
            index += 1

    def upload(self, path: Path, tag: str | None = None) -> None:
        t = tag or RELEASE_TAG
        self.ensure_release(t)
        dest = self._dir_for(t) / path.name
        if dest.exists():
            raise StateArchiveError(f"refusing to overwrite existing asset {path.name}")
        shutil.copyfile(path, dest)
        self.uploads.append(f"{t}/{path.name}")
        self.timestamps.setdefault(path.name, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def download(self, name: str, dest_dir: Path, tag: str | None = None) -> Path:
        src = self._dir_for(tag) / name
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
        conn.execute(
            """
            INSERT INTO injury_status_snapshots (
                snapshot_id, game_id, captured_at, team, player_name, status, source
            ) VALUES ('INJ_1', 'G_STARTED', '2026-11-23T21:00:00Z', 'BOS', 'Kristaps Porzingis', 'OUT', 'nba_official')
            """
        )
        conn.execute(
            """
            INSERT INTO calibration_logs (
                eval_id, evaluated_at, model_version_id, market, sample_size,
                brier_score, log_loss, ece, calibration_method, bins_json, promoted
            ) VALUES ('CAL_1', '2026-11-23T20:00:00Z', 'mv_test', 'moneyline', 200,
                      0.21, 0.61, 0.02, 'platt', '[]', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO game_boxscores (
                game_id, team_stats_json, players_json, source, fetched_at
            ) VALUES ('G_STARTED', '{}', '[]', 'espn', '2026-11-24T04:00:00Z')
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
        ("delete_injury_snapshot", "DELETE FROM injury_status_snapshots WHERE snapshot_id = 'INJ_1';", "injury_status_snapshots: row .* deleted"),
        ("edit_injury_snapshot", "UPDATE injury_status_snapshots SET status = 'AVAILABLE' WHERE snapshot_id = 'INJ_1';", "injury_status_snapshots: row .* modified"),
        ("edit_calibration_log", "UPDATE calibration_logs SET brier_score = 0.05 WHERE eval_id = 'CAL_1';", "calibration_logs: row .* modified"),
        ("delete_game_boxscore", "DELETE FROM game_boxscores WHERE game_id = 'G_STARTED';", "game_boxscores: row .* deleted"),
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
        ("drop_games_table", "DROP TABLE games;", "games: table missing from the newer snapshot"),
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

    # Corrupt asset bytes in store -> SHA-256 mismatch on BOTH reconstruct AND idempotent archive skip
    asset_file = store.root / asset_name("2026-11-24")
    original = asset_file.read_bytes()
    asset_file.write_bytes(original[:-10] + b"CORRUPTED!")
    out = tmp_path / "out.sqlite3"
    out.write_bytes(b"keep-me")
    with pytest.raises(StateArchiveError, match="SHA-256"):
        reconstruct("2026-11-24", out, store=store, history=history)
    assert out.read_bytes() == b"keep-me"
    with pytest.raises(StateArchiveError, match="SHA-256"):
        archive_snapshot(
            day1_gz,
            "2026-11-24",
            source_commit="1111111",
            committed_at="2026-11-24T12:00:00Z",
            store=store,
            history=history,
        )

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

    # Existing tampered/incompatible orphan asset without manifest -> fails closed (never overwrites)
    orphan = store.root / asset_name("2026-11-25")
    tampered_orphan = _tamper_db(day1_db, tmp_path / "orphan_bad.sqlite3", "UPDATE odds_snapshots SET decimal_odds = 9.99 WHERE odds_id = 'O_1';")
    orphan.write_bytes(gzip.compress(tampered_orphan.read_bytes(), mtime=0))
    asset_file.write_bytes(original)
    with pytest.raises(ContinuityViolationError, match="odds_snapshots: row .* modified"):
        archive_snapshot(
            day1_gz,
            "2026-11-25",
            source_commit="2222222",
            committed_at="2026-11-25T12:00:00Z",
            store=store,
            history=history,
        )


def test_archive_recovers_manifest_for_matching_and_superseded_same_day_orphan_assets(
    tmp_path: Path, git_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    work, _ = _init_repo_pair(tmp_path)
    store = FakeReleaseStore(tmp_path)
    history = HistoryBranch(repo_root=work)

    day1_db = _seed_day1_db(tmp_path / "d1.sqlite3")
    day1_gz = _gz(day1_db, tmp_path / "d1.sqlite3.gz")

    # Case 1: Release upload succeeds while history.append push fails, retry has byte-identical gz
    real_append = history.append

    def fail_once(*_args: Any, **_kwargs: Any) -> str:
        raise StateArchiveError("simulated transient push failure")

    monkeypatch.setattr(history, "append", fail_once)
    with pytest.raises(StateArchiveError, match="simulated transient push failure"):
        archive_snapshot(
            day1_gz,
            "2026-11-24",
            source_commit="1111111",
            committed_at="2026-11-24T12:00:00Z",
            store=store,
            history=history,
        )
    assert asset_name("2026-11-24") in store.asset_names()
    assert history.fetch() is None
    assert len(store.uploads) == 1

    monkeypatch.setattr(history, "append", real_append)
    m = archive_snapshot(
        day1_gz,
        "2026-11-24",
        source_commit="1111111",
        committed_at="2026-11-24T12:00:00Z",
        store=store,
        history=history,
    )
    assert m["asset_name"] == asset_name("2026-11-24")
    assert m["source_commit"] == "1111111"
    assert len(store.uploads) == 1
    out = tmp_path / "recovered_day1.sqlite3"
    reconstruct("2026-11-24", out, store=store, history=history)
    assert out.read_bytes() == day1_db.read_bytes()

    # Case 2: Day 2 cycle 1 uploads asset `day2_early` at 10:00Z, push fails; cycle 2 updates state-live lawfully
    # to `day2_late` and retries -> adopts `day2_early` without overwriting and records its manifest!
    day2_early_db = _evolve_to_day2(day1_db, tmp_path / "d2_early.sqlite3")
    day2_early_gz = _gz(day2_early_db, tmp_path / "d2_early.sqlite3.gz")
    store.timestamps[asset_name("2026-11-25")] = "2026-11-25T10:00:00Z"
    monkeypatch.setattr(history, "append", fail_once)
    with pytest.raises(StateArchiveError, match="simulated transient push failure"):
        archive_snapshot(
            day2_early_gz,
            "2026-11-25",
            source_commit="2222222",
            committed_at="2026-11-25T10:00:00Z",
            store=store,
            history=history,
        )
    assert asset_name("2026-11-25") in store.asset_names()
    assert len(store.uploads) == 2

    # Later same-day cycle adds another lawful odds snapshot
    day2_late_db = tmp_path / "d2_late.sqlite3"
    shutil.copyfile(day2_early_db, day2_late_db)
    mgr = DatabaseManager(day2_late_db)
    with mgr.connect() as conn:
        conn.execute(
            """
            INSERT INTO odds_snapshots (
                odds_id, game_id, provider, market, selection, line_value, decimal_odds,
                counterpart_decimal_odds, captured_at, is_closing_line, source_type, fetched_at
            ) VALUES ('O_3', 'G_FUTURE', 'pinnacle', 'moneyline', 'HOME', NULL, 1.74, 2.18,
                      '2026-11-25T16:00:00Z', 0, 'OBSERVED', '2026-11-25T16:00:00Z')
            """
        )
    mgr.checkpoint(truncate=True)
    day2_late_gz = _gz(day2_late_db, tmp_path / "d2_late.sqlite3.gz")

    monkeypatch.setattr(history, "append", real_append)
    m2 = archive_snapshot(
        day2_late_gz,
        "2026-11-25",
        source_commit="3333333",
        committed_at="2026-11-25T16:05:00Z",
        store=store,
        history=history,
    )
    assert m2["recovered_from_existing_asset"] is True
    assert m2["source_commit"].startswith("recovered-asset:")
    assert m2["gz_sha256"] == hashlib.sha256(day2_early_gz.read_bytes()).hexdigest()
    assert len(store.uploads) == 2  # existing immutable Release asset was NOT overwritten
    out2 = tmp_path / "recovered_day2.sqlite3"
    reconstruct("2026-11-25", out2, store=store, history=history)
    assert out2.read_bytes() == day2_early_db.read_bytes()

    # Subsequent verify_window passes across Day 1 -> recovered Day 2
    report = verify_window(30, store=store, history=history, today=date(2026, 11, 26))
    assert report["ok"] is True
    assert report["snapshots"] == ["2026-11-24", "2026-11-25"]


def test_orphan_recovery_uses_asset_upload_timestamp_and_fails_closed_when_missing(
    tmp_path: Path, git_env: None
) -> None:
    work, _ = _init_repo_pair(tmp_path)
    store = FakeReleaseStore(tmp_path)
    history = HistoryBranch(repo_root=work)

    # Orphan asset uploaded at 14:00Z from a reused state-live DB whose latest in-DB timestamp is 10:00Z,
    # while G_ORPHAN_TIP tipped off at 12:00Z (after in-DB max, BEFORE asset upload time!).
    orphan_db = _seed_day1_db(tmp_path / "orphan.sqlite3")
    mgr = DatabaseManager(orphan_db)
    with mgr.connect() as conn:
        conn.execute(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, features_available_at, source_provider, ingested_at
            ) VALUES ('G_ORPHAN_TIP', '2026-27', '2026-11-25', '2026-11-25T12:00:00Z', 'CLE', 'CHI', 'SCHEDULED',
                      '2026-11-25T09:00:00Z', 'espn', '2026-11-25T09:00:00Z')
            """
        )
    mgr.checkpoint(truncate=True)
    orphan_gz = _gz(orphan_db, tmp_path / "orphan.sqlite3.gz")
    store.ensure_release()
    shutil.copyfile(orphan_gz, store.root / asset_name("2026-11-25"))
    store.timestamps[asset_name("2026-11-25")] = "2026-11-25T14:00:00Z"

    # Later DB rewrites G_ORPHAN_TIP's ingested_at -> MUST fail closed because asset_ts (14:00Z) > tip-off (12:00Z)
    rewritten_db = _tamper_db(
        orphan_db,
        tmp_path / "rewritten.sqlite3",
        "UPDATE games SET ingested_at = '2026-11-25T15:00:00Z' WHERE game_id = 'G_ORPHAN_TIP';",
    )
    rewritten_gz = _gz(rewritten_db, tmp_path / "rewritten.sqlite3.gz")
    with pytest.raises(ContinuityViolationError, match="games: started game G_ORPHAN_TIP rewrote"):
        archive_snapshot(
            rewritten_gz,
            "2026-11-25",
            source_commit="late_sha",
            committed_at="2026-11-25T16:00:00Z",
            store=store,
            history=history,
        )

    # Missing upload timestamp on an orphan asset MUST fail closed
    store.timestamps[asset_name("2026-11-25")] = ""
    with pytest.raises(StateArchiveError, match="has no upload timestamp"):
        archive_snapshot(
            rewritten_gz,
            "2026-11-25",
            source_commit="late_sha",
            committed_at="2026-11-25T16:00:00Z",
            store=store,
            history=history,
        )

    # Matching orphan retried on a later UTC day with `--date` still preserves the upload timestamp cutoff
    store.timestamps[asset_name("2026-11-25")] = "2026-11-25T14:00:00Z"
    m_match = archive_snapshot(
        orphan_gz,
        "2026-11-25",
        source_commit="reused_sha",
        committed_at="2026-11-25T09:30:00Z",
        store=store,
        history=history,
    )
    assert m_match["source_committed_at"] == "2026-11-25T14:00:00Z"
    with pytest.raises(ContinuityViolationError, match="games: started game G_ORPHAN_TIP rewrote"):
        archive_snapshot(
            rewritten_gz,
            "2026-11-26",
            source_commit="next_day_sha",
            committed_at="2026-11-26T06:00:00Z",
            store=store,
            history=history,
        )


def test_freeze_cutoff_uses_archived_at_for_same_day_reused_state_live_commit(tmp_path: Path, git_env: None) -> None:
    work, _ = _init_repo_pair(tmp_path)
    store = FakeReleaseStore(tmp_path)
    history = HistoryBranch(repo_root=work)

    now = datetime.now(timezone.utc)
    today_str = now.date().isoformat()
    tomorrow_str = (now.date() + timedelta(days=1)).isoformat()
    # Commit happened 3h ago, game tipped off 1h ago (after commit, BEFORE archive time `now`)
    commit_before_tip = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tip_between_commit_and_archive = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ingested_before = (now - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")

    db1 = _seed_day1_db(tmp_path / "reuse1.sqlite3")
    mgr = DatabaseManager(db1)
    with mgr.connect() as conn:
        conn.execute(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, features_available_at, source_provider, ingested_at
            ) VALUES ('G_BETWEEN', '2026-27', ?, ?, 'NYK', 'MIL', 'SCHEDULED', ?, 'espn', ?)
            """,
            (today_str, tip_between_commit_and_archive, ingested_before, ingested_before),
        )
    mgr.checkpoint(truncate=True)
    gz1 = _gz(db1, tmp_path / "reuse1.sqlite3.gz")
    archive_snapshot(
        gz1,
        today_str,
        source_commit="reused_sha",
        committed_at=commit_before_tip,
        store=store,
        history=history,
    )

    # Rewriting G_BETWEEN's ingested_at on the next day MUST fail closed because archived_at > tip-off
    db2_bad = _tamper_db(
        db1,
        tmp_path / "reuse2_bad.sqlite3",
        f"UPDATE games SET ingested_at = '{now.strftime('%Y-%m-%dT%H:%M:%SZ')}' WHERE game_id = 'G_BETWEEN';",
    )
    gz2_bad = _gz(db2_bad, tmp_path / "reuse2_bad.sqlite3.gz")
    with pytest.raises(ContinuityViolationError, match="games: started game G_BETWEEN rewrote"):
        archive_snapshot(
            gz2_bad,
            tomorrow_str,
            source_commit="next_sha",
            committed_at=(now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    created_releases: set[str] = set()

    def fake_run(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[:3] == ["gh", "release", "view"] and "tagName" in cmd:
            tag = cmd[3]
            if tag in created_releases:
                return subprocess.CompletedProcess(cmd, 0, stdout=f'{{"tagName":"{tag}"}}\n', stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="release not found")
        if cmd[:3] == ["gh", "release", "create"]:
            created_releases.add(cmd[3])
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:3] == ["gh", "release", "view"] and "apiUrl" in cmd:
            tag = cmd[3]
            rid = "42" if tag == RELEASE_TAG else "43"
            return subprocess.CompletedProcess(
                cmd, 0, stdout=f"https://api.github.com/repos/Drewks/nba-betting-intelligence/releases/{rid}\n", stderr=""
            )
        if cmd[:3] == ["gh", "api", "--paginate"]:
            if "/releases/42/" in cmd[3]:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="nba_intelligence-2026-11-24.sqlite3.gz\t2026-11-24T23:55:00Z\n", stderr=""
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    store = GhReleaseStore(tag=RELEASE_TAG, repo_root=tmp_path, max_assets=1)
    store.ensure_release()
    create_cmd = next(c for c in calls if c[:3] == ["gh", "release", "create"])
    assert "--target" in create_cmd and create_cmd[create_cmd.index("--target") + 1] == "main"
    assert "--latest=false" in create_cmd

    timestamps = store.asset_timestamps()
    assert timestamps == {"nba_intelligence-2026-11-24.sqlite3.gz": "2026-11-24T23:55:00Z"}
    names = store.asset_names()
    assert names == {"nba_intelligence-2026-11-24.sqlite3.gz"}
    assert any("--paginate" in c for c in calls)

    # With max_assets=1 and db-archive already holding 1 asset, select_upload_tag rotates to db-archive-2
    next_tag, next_assets = store.select_upload_tag("nba_intelligence-2026-11-25.sqlite3.gz")
    assert next_tag == f"{RELEASE_TAG}-2" and next_assets == {}

    dummy = tmp_path / "nba_intelligence-2026-11-25.sqlite3.gz"
    dummy.write_bytes(b"gz")
    store.upload(dummy, tag=next_tag)
    upload_cmd = next(c for c in calls if c[:3] == ["gh", "release", "upload"])
    assert upload_cmd[3] == f"{RELEASE_TAG}-2"
    assert "--clobber" not in upload_cmd


def test_release_rotation_across_multiple_buckets_reconstruct_and_verify_window(
    tmp_path: Path, git_env: None
) -> None:
    work, _ = _init_repo_pair(tmp_path)
    store = FakeReleaseStore(tmp_path, max_assets=2)
    history = HistoryBranch(repo_root=work)

    current_db = _seed_day1_db(tmp_path / "rot_day0.sqlite3")
    expected_tags = {
        "2026-11-21": "db-archive",
        "2026-11-22": "db-archive",
        "2026-11-23": "db-archive-2",
        "2026-11-24": "db-archive-2",
        "2026-11-25": "db-archive-3",
    }
    saved_bytes: dict[str, bytes] = {}
    for idx, (snap_date, expected_tag) in enumerate(expected_tags.items(), start=1):
        day_db = tmp_path / f"rot_{snap_date}.sqlite3"
        shutil.copyfile(current_db, day_db)
        mgr = DatabaseManager(day_db)
        with mgr.connect() as conn:
            conn.execute(
                """
                INSERT INTO odds_snapshots (
                    odds_id, game_id, provider, market, selection, line_value, decimal_odds,
                    counterpart_decimal_odds, captured_at, is_closing_line, source_type, fetched_at
                ) VALUES (?, 'G_FUTURE', 'pinnacle', 'moneyline', 'HOME', NULL, 1.95, 1.95,
                          ?, 0, 'OBSERVED', ?)
                """,
                (f"O_ROT_{idx}", f"{snap_date}T12:00:00Z", f"{snap_date}T12:00:00Z"),
            )
        mgr.checkpoint(truncate=True)
        current_db = day_db
        saved_bytes[snap_date] = day_db.read_bytes()
        gz = _gz(day_db, tmp_path / f"rot_{snap_date}.sqlite3.gz")
        m = archive_snapshot(
            gz,
            snap_date,
            source_commit=f"sha_{idx}",
            committed_at=f"{snap_date}T12:05:00Z",
            store=store,
            history=history,
        )
        assert m["release_tag"] == expected_tag

    # Reconstruct every date across all 3 release buckets and verify full window continuity
    for snap_date, raw in saved_bytes.items():
        out = tmp_path / f"rebuilt_{snap_date}.sqlite3"
        reconstruct(snap_date, out, store=store, history=history)
        assert out.read_bytes() == raw

    report = verify_window(30, store=store, history=history, today=date(2026, 11, 26))
    assert report["ok"] is True
    assert report["snapshots"] == list(expected_tags)
    assert len(report["pairs"]) == 4


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
