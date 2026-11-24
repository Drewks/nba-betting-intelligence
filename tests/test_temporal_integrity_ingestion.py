"""
Regression tests for the 2026-11-24 temporal-integrity fix (AGENTS.md principle 3, what was known and when):

- a stored game is never re-inserted with values computed during the game (ESPN in-progress statuses);
- ESPN in-progress / halftime / end-of-period statuses never look SCHEDULED (feed-only IN_PROGRESS);
- a quote fetched after tip-off is dropped, never stored with a backdated `captured_at`;
- `features_available_at` / `ingested_at` of a started game are frozen by triggers (UPDATE and REPLACE);
- the auditor gate fails until legacy rows are recorded through `audit_repairs` (migration 016).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any
import urllib.request

import pytest

from src.agents.specialized_agents import NBAAuditorAgent, NBADataScoutAgent
from src.features.team_ratings import apply_pregame_team_ratings
from src.ingestion.base import BaseNBADataAdapter
from src.ingestion.espn import ESPNPublicAdapter, map_espn_status
from src.ingestion.router import DataSourceRouter
from src.paper_trading.engine import build_production_engine
from src.reporting.audit_report import _temporal_integrity_line, generate_audit_report
from src.storage.db import DatabaseManager
from src.validation.temporal_integrity import (
    QUARANTINE_REASON_BACKDATED_ODDS,
    REPAIR_ACTION_BACKDATED_ODDS,
    REPAIR_ACTION_POST_TIPOFF_GAME,
    summarize_temporal_integrity,
)
from src.validation.validator import DataValidationError, validate_game_record
from tests.helpers import copy_prod_db

M016_ID = "2026_11_24_016_freeze_pregame_timestamps_and_record_backdated_rows"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# Anchored to the wall clock: the freeze triggers compare tip-off with SQLite's datetime('now').
NOW = datetime.now(timezone.utc).replace(microsecond=0)
TIP = NOW - timedelta(hours=1)  # a game under way right now
EV_ID = "401999001"
GAME_ID = f"ESPN_{EV_ID}_{_iso(TIP)[:10]}_BOS_AT_NYK"


def _event(
    ev_id: str,
    status_name: str,
    state: str,
    start: datetime,
    *,
    home: str = "NYK",
    away: str = "BOS",
    ml: tuple[int, int] = (-150, 130),
    total: float = 221.5,
    scores: tuple[int, int] = (0, 0),
) -> dict[str, Any]:
    return {
        "id": ev_id,
        "date": _iso(start),
        "competitions": [
            {
                "status": {"type": {"name": status_name, "state": state}},
                "competitors": [
                    {"homeAway": "home", "team": {"abbreviation": home}, "score": str(scores[0])},
                    {"homeAway": "away", "team": {"abbreviation": away}, "score": str(scores[1])},
                ],
                "odds": [
                    {
                        "provider": {"name": "DraftKings"},
                        "homeTeamOdds": {"moneyLine": ml[0]},
                        "awayTeamOdds": {"moneyLine": ml[1]},
                        "overUnder": total,
                        "overOdds": -110,
                        "underOdds": -110,
                    }
                ],
            }
        ],
    }


def _scoreboard(*events: dict[str, Any]) -> dict[str, Any]:
    return {"season": {"year": 2027}, "events": list(events)}


def _espn_adapter(
    monkeypatch: pytest.MonkeyPatch,
    state: dict[str, Any],
    multi_book: dict[tuple[str, str, str], list[dict[str, Any]]] | None = None,
) -> ESPNPublicAdapter:
    """Real ESPN adapter over a mutable fake feed (`state['payload']` scoreboard, `state['box']` team stats)."""

    class _Resp:
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *args: Any) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps(state["payload"]).encode("utf-8")

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
    monkeypatch.setattr("src.ingestion.espn.SportradarAdapter.fetch_league_intelligence_context", lambda _self: {})
    adapter = ESPNPublicAdapter(timeout_seconds=1, enrich_with_the_odds_api=multi_book is not None)
    monkeypatch.setattr(
        adapter,
        "_fetch_event_summary_context",
        lambda _ev_id: {
            "injury_penalties": {},
            "referee_total_adj": 0.0,
            "referee_hca_adj": 0.0,
            "team_box_stats": state.get("box") or {},
            "lineup_synergy_details": {},
        },
    )
    monkeypatch.setattr(adapter, "_compute_team_rest_days", lambda _code, _date: 2)
    if multi_book is not None:
        monkeypatch.setattr(adapter.odds_api_helper, "is_configured", lambda: True)
        monkeypatch.setattr(adapter.odds_api_helper, "fetch_multi_book_odds_by_matchup", lambda _now: multi_book)
    return adapter


LIVE_BOX = {
    "NYK": {"avgPoints": 131.0, "avgPointsAgainst": 99.0, "fieldGoalPct": 61.0},
    "BOS": {"avgPoints": 97.0, "avgPointsAgainst": 128.0, "fieldGoalPct": 36.0},
}


def _ingest_pregame(db: DatabaseManager, router: DataSourceRouter) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pre_tip = _iso(TIP - timedelta(hours=3))
    res = NBADataScoutAgent(db).ingest_and_validate_dataset(router, as_of_utc=pre_tip)
    assert [g["game_id"] for g in res["validated_games"]] == [GAME_ID]
    assert len(res["validated_odds"]) == 4 and res["rejected_odds"] == []
    stored = db.fetch_one("SELECT * FROM games WHERE game_id = ?", (GAME_ID,))
    assert stored is not None
    assert stored["features_available_at"] == stored["ingested_at"] == pre_tip
    odds = db.fetch_all("SELECT * FROM odds_snapshots ORDER BY odds_id")
    assert {(o["captured_at"], o["fetched_at"]) for o in odds} == {(pre_tip, pre_tip)}
    return stored, odds


# --- Done when 1: re-ingesting an in-progress game leaves the stored row unchanged ----------------------


@pytest.mark.parametrize("status_name", ["STATUS_IN_PROGRESS", "STATUS_HALFTIME", "STATUS_END_PERIOD"])
def test_reingesting_in_progress_game_leaves_stored_row_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status_name: str
) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    state: dict[str, Any] = {"payload": _scoreboard(_event(EV_ID, "STATUS_SCHEDULED", "pre", TIP)), "box": {}}
    router = DataSourceRouter([_espn_adapter(monkeypatch, state)])
    stored_before, odds_before = _ingest_pregame(db, router)

    # During the game the feed carries live box scores (different features) and live prices.
    state["payload"] = _scoreboard(_event(EV_ID, status_name, "in", TIP, ml=(-900, 600), total=238.5))
    state["box"] = LIVE_BOX
    res = NBADataScoutAgent(db).ingest_and_validate_dataset(router, as_of_utc=_iso(TIP + timedelta(minutes=50)))

    assert [g["game_id"] for g in res["in_progress_games"]] == [GAME_ID]
    assert res["validated_games"] == [] and res["discarded_games"] == []
    assert res["validated_odds"] == [] and res["pregame_live_profiles"] == {}
    assert db.fetch_one("SELECT * FROM games WHERE game_id = ?", (GAME_ID,)) == stored_before
    assert db.fetch_all("SELECT * FROM odds_snapshots ORDER BY odds_id") == odds_before


def test_lagging_scheduled_feed_after_tipoff_and_final_result_keep_pregame_trail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    state: dict[str, Any] = {"payload": _scoreboard(_event(EV_ID, "STATUS_SCHEDULED", "pre", TIP)), "box": {}}
    router = DataSourceRouter([_espn_adapter(monkeypatch, state)])
    stored_before, odds_before = _ingest_pregame(db, router)

    # ESPN still says "scheduled" minutes after tip-off: nothing of the row changes and no quote is stored.
    state["payload"] = _scoreboard(_event(EV_ID, "STATUS_SCHEDULED", "pre", TIP, ml=(-900, 600)))
    state["box"] = LIVE_BOX
    res = NBADataScoutAgent(db).ingest_and_validate_dataset(router, as_of_utc=_iso(TIP + timedelta(minutes=5)))
    assert res["frozen_existing_games"] == 1 and res["pregame_live_profiles"] == {}
    assert res["validated_odds"] == [] and res["rejected_odds"] == []
    assert db.fetch_one("SELECT * FROM games WHERE game_id = ?", (GAME_ID,)) == stored_before
    assert db.fetch_all("SELECT * FROM odds_snapshots ORDER BY odds_id") == odds_before

    # The result only moves status, scores and result_recorded_at.
    state["payload"] = _scoreboard(_event(EV_ID, "STATUS_FINAL", "post", TIP, scores=(112, 104)))
    res = NBADataScoutAgent(db).ingest_and_validate_dataset(router)
    assert res["results_applied"] == 1
    after = db.fetch_one("SELECT * FROM games WHERE game_id = ?", (GAME_ID,))
    assert after is not None
    assert (after["status"], after["home_score"], after["away_score"]) == ("FINAL", 112, 104)
    moved = {"status", "home_score", "away_score", "result_recorded_at"}
    assert {k: v for k, v in after.items() if k not in moved} == {k: v for k, v in stored_before.items() if k not in moved}


def test_pretip_reingestion_keeps_first_snapshot_and_feeds_fresh_estimate_to_ratings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tip = NOW + timedelta(hours=6)
    gid = f"ESPN_{EV_ID}_{_iso(tip)[:10]}_BOS_AT_NYK"
    db = DatabaseManager(tmp_path / "t.sqlite3")
    state: dict[str, Any] = {"payload": _scoreboard(_event(EV_ID, "STATUS_SCHEDULED", "pre", tip)), "box": {}}
    router = DataSourceRouter([_espn_adapter(monkeypatch, state)])
    NBADataScoutAgent(db).ingest_and_validate_dataset(router, as_of_utc=_iso(NOW - timedelta(hours=2)))
    first = db.fetch_one("SELECT * FROM games WHERE game_id = ?", (gid,))
    assert first is not None

    state["box"] = LIVE_BOX  # injury/box-score news before tip-off changes the feed's estimate
    res = NBADataScoutAgent(db).ingest_and_validate_dataset(router, as_of_utc=_iso(NOW - timedelta(hours=1)))
    assert db.fetch_one("SELECT * FROM games WHERE game_id = ?", (gid,)) == first  # first snapshot kept
    fresh = res["pregame_live_profiles"][gid]
    assert fresh["home_off_rtg"] != first["home_off_rtg"]

    # The ratings step blends the fresh estimate exactly as when the row itself was replaced by it.
    old_behaviour = DatabaseManager(tmp_path / "replaced.sqlite3")
    old_behaviour.execute_insert(
        f"INSERT INTO games ({', '.join(first)}) VALUES ({', '.join('?' for _ in first)})",
        tuple({**first, **fresh}[c] for c in first),
    )
    apply_pregame_team_ratings(db, live_profiles=res["pregame_live_profiles"])
    apply_pregame_team_ratings(old_behaviour)
    cols = "home_off_rtg, home_def_rtg, home_pace, away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days"
    blended = db.fetch_one(f"SELECT {cols} FROM games WHERE game_id = ?", (gid,))
    assert blended == old_behaviour.fetch_one(f"SELECT {cols} FROM games WHERE game_id = ?", (gid,))
    timestamps = db.fetch_one("SELECT features_available_at, ingested_at FROM games WHERE game_id = ?", (gid,))
    assert timestamps == {"features_available_at": first["features_available_at"], "ingested_at": first["ingested_at"]}


# --- Done when 2: quotes fetched after tip-off are never stored with a backdated captured_at ------------


@pytest.mark.parametrize(("status_name", "state_name"), [("STATUS_SCHEDULED", "pre"), ("STATUS_IN_PROGRESS", "in")])
def test_quotes_fetched_after_tipoff_are_dropped_not_backdated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status_name: str, state_name: str
) -> None:
    upcoming_tip = NOW + timedelta(hours=3)
    upcoming_id = f"ESPN_401999002_{_iso(upcoming_tip)[:10]}_GSW_AT_LAL"

    def _line_shop(price_home: float, price_away: float) -> list[dict[str, Any]]:
        return [
            {"provider": "Pinnacle (Best of 9 books)", "market": "moneyline", "selection": "HOME", "line_value": None,
             "decimal_odds": price_home, "counterpart_decimal_odds": price_away, "source_type": "OBSERVED"},
            {"provider": "Pinnacle (Best of 9 books)", "market": "moneyline", "selection": "AWAY", "line_value": None,
             "decimal_odds": price_away, "counterpart_decimal_odds": price_home, "source_type": "OBSERVED"},
        ]

    state: dict[str, Any] = {
        "payload": _scoreboard(
            _event(EV_ID, status_name, state_name, TIP, ml=(-900, 600)),
            _event("401999002", "STATUS_SCHEDULED", "pre", upcoming_tip, home="LAL", away="GSW"),
        ),
        "box": LIVE_BOX,
    }
    multi_book = {
        (_iso(TIP)[:10], "BOS", "NYK"): _line_shop(1.08, 8.5),  # in-game prices of the started game
        (_iso(upcoming_tip)[:10], "GSW", "LAL"): _line_shop(1.95, 1.95),
    }
    adapter = _espn_adapter(monkeypatch, state, multi_book=multi_book)
    fetched = _iso(NOW)

    raw = adapter.fetch_games_and_odds(as_of_utc=fetched)
    assert raw["odds"], "the upcoming game keeps its quotes"
    assert all(o["game_id"] == upcoming_id for o in raw["odds"])  # started game: dropped, not stamped tip - 15 min
    assert {(o["captured_at"], o["fetched_at"]) for o in raw["odds"]} == {(fetched, fetched)}

    db = DatabaseManager(tmp_path / "t.sqlite3")
    res = NBADataScoutAgent(db).ingest_and_validate_dataset(DataSourceRouter([adapter]), as_of_utc=fetched)
    stored = db.fetch_all("SELECT game_id, captured_at, fetched_at FROM odds_snapshots")
    assert stored and {r["game_id"] for r in stored} == {upcoming_id}
    assert all(r["captured_at"] == r["fetched_at"] == fetched for r in stored)
    tip_minus_15 = _iso(TIP - timedelta(minutes=15))
    assert db.fetch_one("SELECT COUNT(*) AS n FROM odds_snapshots WHERE captured_at = ?", (tip_minus_15,)) == {"n": 0}
    # First seen after tip-off: no pre-game row is stored for the started game.
    assert db.fetch_one("SELECT 1 FROM games WHERE game_id = ?", (GAME_ID,)) is None
    assert GAME_ID in {d["game_id"] for d in res["discarded_games"]} | {g["game_id"] for g in res["in_progress_games"]}


class _StaticAdapter(BaseNBADataAdapter):
    provider_name = "static_test"

    def __init__(self, games: list[dict[str, Any]], odds: list[dict[str, Any]] | None = None) -> None:
        self.games = games
        self.odds = odds or []

    def fetch_games_and_odds(self, date_str: str | None = None, as_of_utc: str | None = None) -> dict[str, Any]:
        return {"games": [dict(g) for g in self.games], "odds": [dict(o) for o in self.odds]}


def _game(game_id: str, start: datetime, ingested: datetime, **kw: Any) -> dict[str, Any]:
    g = {
        "game_id": game_id,
        "season": "2026-27",
        "matchday_date": _iso(start)[:10],
        "game_start_time": _iso(start),
        "home_team": "NYK",
        "away_team": "BOS",
        "status": "SCHEDULED",
        "home_score": None,
        "away_score": None,
        "home_off_rtg": 115.0,
        "home_def_rtg": 112.0,
        "home_pace": 99.0,
        "away_off_rtg": 116.0,
        "away_def_rtg": 111.0,
        "away_pace": 98.0,
        "home_rest_days": 2,
        "away_rest_days": 2,
        "features_available_at": _iso(ingested),
        "source_provider": "espn_v2_syndicate_enriched",
        "ingested_at": _iso(ingested),
        "result_recorded_at": None,
    }
    g.update(kw)
    return g


def _quote(odds_id: str, game_id: str, captured: str, fetched: str | None, closing: int = 0) -> dict[str, Any]:
    q: dict[str, Any] = {
        "odds_id": odds_id, "game_id": game_id, "provider": "DraftKings", "market": "moneyline", "selection": "HOME",
        "line_value": None, "decimal_odds": 1.8, "counterpart_decimal_odds": 2.05, "captured_at": captured,
        "is_closing_line": closing, "source_type": "OBSERVED",
    }
    if fetched is not None:
        q["fetched_at"] = fetched
    return q


def test_backdated_quotes_are_rejected_by_scout_write_path_and_trigger(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    tip = NOW + timedelta(hours=4)
    fetched = _iso(NOW)
    backdated = _iso(NOW - timedelta(minutes=15))
    adapter = _StaticAdapter(
        [_game("G_FUT", tip, NOW)],
        [
            _quote("Q_OK", "G_FUT", fetched, fetched),
            _quote("Q_BACKDATED", "G_FUT", backdated, fetched),
            _quote("Q_FETCH_BEFORE_CALL", "G_FUT", backdated, backdated),
        ],
    )
    res = NBADataScoutAgent(db).ingest_and_validate_dataset(DataSourceRouter([adapter]), as_of_utc=fetched)
    assert [o["odds_id"] for o in res["validated_odds"]] == ["Q_OK"]
    reasons = {r["odds_id"]: r["reason"] for r in res["rejected_odds"]}
    assert "BACKDATED_CAPTURE" in reasons["Q_BACKDATED"]
    assert "before the fetch started" in reasons["Q_FETCH_BEFORE_CALL"]
    assert [r["odds_id"] for r in db.fetch_all("SELECT odds_id FROM odds_snapshots")] == ["Q_OK"]

    with pytest.raises(ValueError, match="BACKDATED_CAPTURE"):
        db.insert_odds_snapshot(_quote("Q_DIRECT", "G_FUT", backdated, fetched))
    with pytest.raises(sqlite3.IntegrityError, match="TEMPORAL_INTEGRITY_VIOLATION"):
        db.execute_insert(
            "INSERT INTO odds_snapshots (odds_id, game_id, provider, market, selection, decimal_odds, captured_at, "
            "is_closing_line, source_type, fetched_at) VALUES ('Q_RAW', 'G_FUT', 'X', 'moneyline', 'HOME', 1.9, ?, 0, "
            "'OBSERVED', ?)",
            (backdated, fetched),
        )


# --- Triggers: started games are frozen, rating columns stay writable ------------------------------------


def test_started_game_timestamps_are_frozen_but_ratings_and_results_stay_writable(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    started = _game("G_STARTED", NOW - timedelta(hours=2), NOW - timedelta(hours=5))
    upcoming = _game("G_UPCOMING", NOW + timedelta(hours=2), NOW - timedelta(hours=1))
    cols = list(started)
    insert = f"INSERT INTO games ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})"
    for g in (started, upcoming):
        db.execute_insert(insert, tuple(g[c] for c in cols))

    for col in ("features_available_at", "ingested_at"):
        with pytest.raises(sqlite3.IntegrityError, match="TEMPORAL_INTEGRITY_VIOLATION"):
            db.execute_insert(f"UPDATE games SET {col} = ? WHERE game_id = 'G_STARTED'", (_iso(TIP),))
    with pytest.raises(sqlite3.IntegrityError, match="TEMPORAL_INTEGRITY_VIOLATION"):  # the incident path
        db.execute_insert(insert.replace("INSERT", "INSERT OR REPLACE"), tuple({**started, "ingested_at": _iso(NOW)}[c] for c in cols))

    # Legitimate writes: recomputed ratings, the result, an identical re-insert, and an upcoming game.
    db.execute_insert("UPDATE games SET home_off_rtg = 120.5, home_rest_days = 1 WHERE game_id = 'G_STARTED'")
    db.execute_insert("UPDATE games SET status = 'FINAL', home_score = 101, away_score = 99 WHERE game_id = 'G_STARTED'")
    db.execute_insert(insert.replace("INSERT", "INSERT OR IGNORE"), tuple(started[c] for c in cols))
    db.execute_insert("UPDATE games SET features_available_at = ? WHERE game_id = 'G_UPCOMING'", (_iso(NOW),))
    row = db.fetch_one("SELECT * FROM games WHERE game_id = 'G_STARTED'")
    assert row is not None and row["home_off_rtg"] == 120.5 and row["status"] == "FINAL"
    assert (row["features_available_at"], row["ingested_at"]) == (started["features_available_at"], started["ingested_at"])


def test_rescheduled_tipoff_is_followed_only_while_the_stored_tipoff_is_ahead(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    ahead = _game("G_AHEAD", NOW + timedelta(hours=5), NOW - timedelta(hours=1))
    passed = _game("G_PASSED", NOW - timedelta(hours=1), NOW - timedelta(hours=4))
    scout = NBADataScoutAgent(db)
    scout.ingest_and_validate_dataset(DataSourceRouter([_StaticAdapter([ahead, passed])]), as_of_utc=_iso(NOW - timedelta(hours=6)))
    stored = {g["game_id"]: g for g in db.fetch_all("SELECT * FROM games")}

    moved_ahead = {**ahead, "game_start_time": _iso(NOW + timedelta(hours=3)), "ingested_at": _iso(NOW), "home_off_rtg": 99.0}
    moved_passed = {**passed, "game_start_time": _iso(NOW - timedelta(minutes=30)), "ingested_at": _iso(NOW)}
    res = scout.ingest_and_validate_dataset(DataSourceRouter([_StaticAdapter([moved_ahead, moved_passed])]), as_of_utc=_iso(NOW))
    assert res["schedule_corrections"] == 1
    after = {g["game_id"]: g for g in db.fetch_all("SELECT * FROM games")}
    assert after["G_AHEAD"] == {**stored["G_AHEAD"], "game_start_time": moved_ahead["game_start_time"]}
    assert after["G_PASSED"] == stored["G_PASSED"]


# --- ESPN status mapping -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "state", "expected"),
    [
        ("STATUS_SCHEDULED", "pre", "SCHEDULED"),
        ("STATUS_IN_PROGRESS", "in", "IN_PROGRESS"),
        ("STATUS_HALFTIME", "in", "IN_PROGRESS"),
        ("STATUS_END_PERIOD", "in", "IN_PROGRESS"),
        ("STATUS_SOMETHING_NEW", "in", "IN_PROGRESS"),
        ("STATUS_FORFEIT", "post", "IN_PROGRESS"),
        ("STATUS_FINAL", "post", "FINAL"),
        ("STATUS_POSTPONED", "post", "POSTPONED"),
        ("STATUS_CANCELED", "post", "CANCELLED"),
        ("", "", "SCHEDULED"),
    ],
)
def test_espn_status_mapping_never_reports_a_live_game_as_scheduled(name: str, state: str, expected: str) -> None:
    assert map_espn_status({"type": {"name": name, "state": state}}) == expected


def test_in_progress_status_is_never_a_pregame_record() -> None:
    with pytest.raises(DataValidationError, match="in progress"):
        validate_game_record(_game("G_LIVE", NOW + timedelta(hours=1), NOW, status="IN_PROGRESS"))


def test_final_result_first_seen_after_tipoff_is_stamped_with_real_ingestion_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    state: dict[str, Any] = {"payload": _scoreboard(_event(EV_ID, "STATUS_FINAL", "post", TIP, scores=(101, 97))), "box": LIVE_BOX}
    res = NBADataScoutAgent(db).ingest_and_validate_dataset(DataSourceRouter([_espn_adapter(monkeypatch, state)]))
    assert res["discarded_games"] == []
    row = db.fetch_one("SELECT * FROM games WHERE game_id = ?", (GAME_ID,))
    assert row is not None and row["status"] == "FINAL"
    assert row["features_available_at"] == row["ingested_at"] > row["game_start_time"]  # not tip-off - 2 h
    with db.connect() as conn:
        assert summarize_temporal_integrity(conn)["post_tipoff_ingested_games"] == 0


# --- Done when 3: the auditor gate fails until legacy rows are recorded as audited repairs -----------------


def test_auditor_gate_fails_until_legacy_rows_are_recorded_by_migration_016(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    db = DatabaseManager(path)
    tip = datetime(2026, 11, 18, 0, 30, tzinfo=timezone.utc)
    legacy = [
        # replaced during the game (the incident): ingested 85 min after tip-off, availability tip-off - 2 h
        _game("ESPN_1_2026-11-18_NYK_AT_TOR", tip, tip + timedelta(minutes=85), status="FINAL", home_score=1, away_score=0,
              features_available_at=_iso(tip - timedelta(hours=2))),
        _game("ESPN_2_2026-11-18_BOS_AT_MIA", tip, tip - timedelta(hours=3), status="FINAL", home_score=1, away_score=0),
        _game("ESPN_3_2025-01-02_BOS_AT_MIA", tip, tip + timedelta(days=5), status="FINAL", home_score=1, away_score=0,
              features_available_at=_iso(tip - timedelta(hours=2)), source_provider="espn_history_backfill"),
        _game("SYN_4_BOS_AT_MIA", tip, tip + timedelta(days=5), status="FINAL", home_score=1, away_score=0,
              features_available_at=_iso(tip - timedelta(hours=2)), source_provider="synthetic_fixture_verified"),
    ]
    cols = list(legacy[0])
    for g in legacy:
        db.execute_insert(f"INSERT INTO games ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", tuple(g[c] for c in cols))
    gid = legacy[0]["game_id"]
    stamp = _iso(tip - timedelta(minutes=15))
    for q in (
        _quote(f"{gid}_ML_HOME_DraftKings_m150", gid, stamp, None),  # legacy ESPN-adapter stamp, no fetch record
        _quote(f"{gid}_ML_HOME_DraftKings_m150_CLOSE", gid, stamp, None, closing=1),
        _quote(f"ODDS_LIVEAPI_{gid}_teapuesto_HOME_{stamp}", gid, stamp, None),  # real Peru capture at :15 sharp
        _quote("ESPN_2_2026-11-18_BOS_AT_MIA_ML_HOME_DraftKings_m120", "ESPN_2_2026-11-18_BOS_AT_MIA", _iso(tip - timedelta(hours=3)), None),
    ):
        db.insert_odds_snapshot(q)
    rows_before = db.fetch_all("SELECT * FROM games ORDER BY game_id"), db.fetch_all("SELECT * FROM odds_snapshots ORDER BY odds_id")

    gate = NBAAuditorAgent(db, build_production_engine(db))._verify_temporal_ingestion_integrity()
    assert not gate["passed"]
    assert (gate["unrecorded_post_tipoff_games"], gate["unrecorded_game_examples"]) == (1, [gid])
    assert (gate["unresolved_backdated_odds"], gate["backdated_closing_lines"]) == (2, 1)
    audit = NBAAuditorAgent(db, build_production_engine(db)).run_independent_audit({})
    assert audit["temporal_ingestion_integrity"]["passed"] is False
    assert audit["exit_gates_evaluation"]["gates"]["gate_8_data_and_odds_integrity"]["passed"] is False
    assert "VIOLACIÓN" in _temporal_integrity_line(audit["temporal_ingestion_integrity"])

    # Re-run migration 016 through the normal initialisation path (as on the live database).
    with db.connect() as conn:
        conn.execute("DELETE FROM schema_migrations WHERE migration_id = ?", (M016_ID,))
    db = DatabaseManager(path)
    gate = NBAAuditorAgent(db, build_production_engine(db))._verify_temporal_ingestion_integrity()
    assert gate["passed"] and gate["recorded_post_tipoff_games"] == 1 and gate["backdated_odds"] == 2
    repairs = db.fetch_all("SELECT table_name, row_pk, action FROM audit_repairs WHERE migration_id = ? ORDER BY row_pk", (M016_ID,))
    assert {(r["table_name"], r["row_pk"]) for r in repairs if r["action"] == REPAIR_ACTION_POST_TIPOFF_GAME} == {("games", gid)}
    assert {r["row_pk"] for r in repairs if r["action"] == REPAIR_ACTION_BACKDATED_ODDS} == {
        f"{gid}_ML_HOME_DraftKings_m150",
        f"{gid}_ML_HOME_DraftKings_m150_CLOSE",
    }
    quarantined = db.fetch_all("SELECT odds_id FROM quarantined_odds WHERE reason = ?", (QUARANTINE_REASON_BACKDATED_ODDS,))
    assert len(quarantined) == 2
    assert db.fetch_all("SELECT odds_id FROM v_observed_odds_snapshots WHERE is_closing_line = 1") == []  # out of CLV
    # Nothing was deleted or rewritten.
    assert (db.fetch_all("SELECT * FROM games ORDER BY game_id"), db.fetch_all("SELECT * FROM odds_snapshots ORDER BY odds_id")) == rows_before
    audit = NBAAuditorAgent(db, build_production_engine(db)).run_independent_audit({})
    assert audit["temporal_ingestion_integrity"]["passed"] is True
    assert "ÍNTEGRO" in _temporal_integrity_line(audit["temporal_ingestion_integrity"])


def _assert_gate_fails_then_passes_after_migration(path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(str(path))
    try:
        before = summarize_temporal_integrity(conn)
    finally:
        conn.close()
    assert not before["passed"]
    db = DatabaseManager(path)  # applies migration 016
    after = NBAAuditorAgent(db, build_production_engine(db))._verify_temporal_ingestion_integrity()
    assert after["passed"], after
    assert after["recorded_post_tipoff_games"] == before["post_tipoff_ingested_games"]
    assert after["backdated_odds"] == before["backdated_odds"] and after["unresolved_backdated_odds"] == 0
    return {"before": before, "after": after}


def test_auditor_gate_on_repository_fixture_db_passes_once_rows_are_recorded(tmp_path: Path) -> None:
    result = _assert_gate_fails_then_passes_after_migration(copy_prod_db(tmp_path, "fixture_copy.sqlite3"))
    assert result["before"]["unrecorded_post_tipoff_games"] > 0


@pytest.mark.skipif(
    not os.environ.get("NBA_LIVE_DB_COPY"),
    reason="set NBA_LIVE_DB_COPY to a copy of origin/state-live:data/nba_intelligence.sqlite3",
)
def test_auditor_gate_on_live_state_db_copy(tmp_path: Path) -> None:
    dst = tmp_path / "live_copy.sqlite3"
    shutil.copy2(os.environ["NBA_LIVE_DB_COPY"], dst)
    result = _assert_gate_fails_then_passes_after_migration(dst)
    assert result["before"]["backdated_closing_lines"] <= result["before"]["backdated_odds"]


def test_audit_report_shows_temporal_integrity_line() -> None:
    gates = {"gate_8_data_and_odds_integrity": {"passed": True, "observed": 0, "required": 0}}
    md = generate_audit_report(
        {
            "leakage_violations_count": 0,
            "bankroll_reconciled": True,
            "immutability_triggers_verified": True,
            "history_integrity": {"missing_rows_total": 0, "missing_rows_by_table": {}},
            "temporal_ingestion_integrity": {
                "passed": True,
                "recorded_post_tipoff_games": 123,
                "unrecorded_post_tipoff_games": 0,
                "backdated_odds": 12,
                "backdated_closing_lines": 6,
                "unresolved_backdated_odds": 0,
                "temporal_freeze_triggers_active": True,
            },
            "exit_gates_evaluation": {"auto_transition_to_real_money": False, "recommendation": "REMAIN_IN_PAPER_TRADING", "gates": gates},
        },
        {},
    )
    line = next(ln for ln in md.splitlines() if "Integridad temporal de ingestión" in ln)
    assert "ÍNTEGRO" in line and "`123`" in line and "cierres `6`" in line and "ACTIVOS" in line


def test_quotes_are_stamped_after_the_feed_responds_not_at_call_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """A request that starts just before tip-off and returns after it must not emit pre-tip-stamped quotes."""
    tip = datetime(2026, 11, 25, 0, 30, tzinfo=timezone.utc)
    clock = iter([tip - timedelta(seconds=2), tip + timedelta(seconds=3)])  # call entry, then response arrival

    class _Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
            return next(clock)

    state: dict[str, Any] = {"payload": _scoreboard(_event(EV_ID, "STATUS_SCHEDULED", "pre", tip)), "box": {}}
    adapter = _espn_adapter(monkeypatch, state)
    monkeypatch.setattr("src.ingestion.espn.datetime", _Clock)
    raw = adapter.fetch_games_and_odds()
    assert raw["odds"] == []
    assert raw["games"][0]["features_available_at"] == _iso(tip + timedelta(seconds=3))
