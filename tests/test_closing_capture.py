"""Closing-line capture: only games about to start are captured, and their latest quote becomes the close."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.ingestion.closing_capture import capture_closing_window, games_in_closing_window
from src.storage.db import DatabaseManager
from tests.helpers import PROJECT_ROOT

NOW = datetime(2026, 11, 17, 0, 30, tzinfo=timezone.utc)


def _seed_game(db: DatabaseManager, game_id: str, start: str) -> None:
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, features_available_at, source_provider, ingested_at
        ) VALUES (?, '2026-27', ?, ?, 'MIN', 'POR', 'SCHEDULED', '2026-11-16T12:00:00Z', 'espn', '2026-11-16T12:00:00Z')
        """,
        (game_id, start[:10], start),
    )


class _FakeCollector:
    """Stores one Pinnacle total pair per call, like LivePeruOddsScraper.collect_slate_odds does."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self.calls: list[str] = []

    def collect_slate_odds(self, game_id: str, home_team: str, away_team: str, game_start_time: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(game_id)
        cap = kwargs["as_of_utc"].strftime("%Y-%m-%dT%H:%M:%SZ")
        for sel, odds, counter in (("OVER", 1.95, 1.93), ("UNDER", 1.93, 1.95)):
            self.db.insert_odds_snapshot({
                "odds_id": f"T_{game_id}_{sel}_{cap}",
                "game_id": game_id,
                "provider": "Pinnacle [LIVE_API]",
                "market": "total_points",
                "selection": sel,
                "line_value": 229.5,
                "decimal_odds": odds,
                "counterpart_decimal_odds": counter,
                "captured_at": cap,
                "source_type": "OBSERVED",
            })
        return {"observed_quotes_count": 1}


def test_only_games_in_window_are_captured_and_closed(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "close.sqlite3")
    _seed_game(db, "G_SOON", "2026-11-17T01:00:00Z")   # 30 min ahead: in window
    _seed_game(db, "G_LATER", "2026-11-17T03:00:00Z")  # 2.5 h ahead: not yet
    _seed_game(db, "G_PAST", "2026-11-17T00:00:00Z")   # already started
    assert [g["game_id"] for g in games_in_closing_window(db, NOW, 45)] == ["G_SOON"]

    collector = _FakeCollector(db)
    summary = capture_closing_window(db, collector=collector, now=NOW, window_minutes=45)
    assert collector.calls == ["G_SOON"]
    assert summary["games_in_window"] == 1
    assert summary["closing_lines_promoted"] == 2
    closes = db.fetch_all("SELECT game_id, captured_at FROM v_observed_odds_snapshots WHERE is_closing_line = 1")
    assert {r["game_id"] for r in closes} == {"G_SOON"}
    assert {r["captured_at"] for r in closes} == {"2026-11-17T00:30:00Z"}


def test_later_capture_produces_a_newer_close(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "close2.sqlite3")
    _seed_game(db, "G_SOON", "2026-11-17T01:00:00Z")
    collector = _FakeCollector(db)
    capture_closing_window(db, collector=collector, now=NOW, window_minutes=45)
    later = datetime(2026, 11, 17, 0, 50, tzinfo=timezone.utc)
    capture_closing_window(db, collector=collector, now=later, window_minutes=45)
    latest = db.fetch_one(
        "SELECT MAX(captured_at) AS c FROM v_observed_odds_snapshots WHERE is_closing_line = 1 AND game_id = 'G_SOON'"
    )
    assert latest["c"] == "2026-11-17T00:50:00Z"


def test_no_games_means_no_network_and_no_writes(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "close3.sqlite3")
    collector = _FakeCollector(db)
    summary = capture_closing_window(db, collector=collector, now=NOW, window_minutes=45)
    assert summary["games_in_window"] == 0 and collector.calls == []


def test_closing_workflow_is_event_driven_and_never_pushes_over_a_main_cycle() -> None:
    wf = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "closing_capture.yml").read_text(encoding="utf-8"))
    main = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "nba_cloud_automation.yml").read_text(encoding="utf-8"))
    triggers = wf.get("on") or wf.get(True)
    # Started when a main cycle finishes (GitHub's high-frequency cron proved unreliable)
    assert main["name"] in triggers["workflow_run"]["workflows"]
    minutes = {c["cron"].split()[0] for c in triggers["schedule"]}
    main_minutes = {c["cron"].split()[0] for c in (main.get("on") or main.get(True))["schedule"]}
    assert not any(m in mm.split(",") for mm in minutes for m in main_minutes)
    # A multi-hour loop must not hold up the main cycle: own concurrency group, explicit waiting instead
    assert wf["concurrency"]["group"] != main["concurrency"]["group"]
    steps_text = "\n".join(str(s.get("run", "")) for s in next(iter(wf["jobs"].values()))["steps"])
    assert "wait_for_main_cycle" in steps_text
    job_env = next(iter(wf["jobs"].values()))["env"]
    # every workflow that writes state-live is waited for, not only the main cycle
    for writer in ("nba_cloud_automation.yml", "weekly_backtest.yml"):
        assert writer in job_env["STATE_WRITER_WORKFLOWS"]
    assert '[ "$(main_cycle_busy)" = "0" ]' in steps_text  # re-checked right before pushing
    assert 'git read-tree "${BASE}"' in steps_text
    assert "checkpoint(truncate=True)" in steps_text
    assert "--count-upcoming" in steps_text


def test_count_upcoming_cli(tmp_path: Path) -> None:
    import subprocess
    import sys

    db = DatabaseManager(tmp_path / "count.sqlite3")
    _seed_game(db, "G_FAR", "2099-01-01T00:00:00Z")
    out = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "capture_closing_odds.py"), "--db", str(tmp_path / "count.sqlite3"),
         "--count-upcoming", "240"],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip().splitlines()[-1] == "0"


def test_weekly_backtest_report_survives_the_main_cycle() -> None:
    weekly = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "weekly_backtest.yml").read_text(encoding="utf-8"))
    main_raw = (PROJECT_ROOT / ".github" / "workflows" / "nba_cloud_automation.yml").read_text(encoding="utf-8")
    weekly_steps = "\n".join(str(s.get("run", "")) for s in next(iter(weekly["jobs"].values()))["steps"])
    assert "--refresh-season" in weekly_steps
    assert '--db "$RUNNER_TEMP/backtest.sqlite3"' in weekly_steps  # never writes the audit database
    assert 'git read-tree "${STATE_BASE_SHA}"' in weekly_steps
    # The main cycle restores the weekly report from state-live before rebuilding the state tree
    assert "reports/real_odds_backtest.md" in main_raw.split("4b. Restaurar estado vivo")[1].split("- name: 5.")[0]
    assert weekly["concurrency"]["group"] == yaml.safe_load(main_raw)["concurrency"]["group"]
