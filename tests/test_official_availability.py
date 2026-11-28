"""Official injury report replaces the availability proxy for the upcoming games it covers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.features.boxscore_features import compute_boxscore_features, player_name_key
from src.features.official_availability import build_official_availability_overrides
from src.storage.db import DatabaseManager

NOW = datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc)


def _seed(db: DatabaseManager, game_id: str, start: str, home: str, away: str) -> None:
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, features_available_at, source_provider, ingested_at
        ) VALUES (?, '2026-27', ?, ?, ?, ?, 'SCHEDULED', '2026-11-17T12:00:00Z', 'espn', '2026-11-17T12:00:00Z')
        """,
        (game_id, start[:10], start, home, away),
    )


def _report(entries: list[dict[str, Any]], pending: list[str] | None = None) -> dict[str, Any]:
    by_team: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        by_team.setdefault(e["team"], []).append(e)
    return {"fetch_ok": True, "by_team": by_team, "captured_at": "2026-11-17T17:30:00Z",
            "not_yet_submitted_teams": pending or []}


def test_report_entries_apply_only_to_the_same_eastern_date_and_matchup(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "avail.sqlite3")
    _seed(db, "G_TONIGHT", "2026-11-18T00:30:00Z", "MIN", "POR")   # 11/17 19:30 ET
    _seed(db, "G_TOMORROW", "2026-11-19T00:30:00Z", "MIN", "POR")  # 11/18 19:30 ET
    _seed(db, "G_OTHER", "2026-11-18T01:00:00Z", "BOS", "NYK")
    report = _report([
        {"team": "MIN", "name": "Anthony Edwards", "status": "Out", "game_date": "11/17/2026", "matchup": "POR@MIN"},
        {"team": "MIN", "name": "Rudy Gobert", "status": "Questionable", "game_date": "11/17/2026", "matchup": "POR@MIN"},
        {"team": "BOS", "name": "Jayson Tatum", "status": "Out", "game_date": "11/16/2026", "matchup": "BOS@NYK"},  # yesterday
    ])
    overrides = build_official_availability_overrides(db, report, NOW)
    assert set(overrides) == {"G_TONIGHT"}  # never tomorrow's game, never yesterday's report
    assert overrides["G_TONIGHT"]["MIN"] == frozenset({player_name_key("Anthony Edwards")})
    assert overrides["G_TONIGHT"]["POR"] == frozenset()  # covered game, nobody listed out
    rows = db.fetch_all("SELECT player_name, status FROM injury_status_snapshots WHERE game_id = 'G_TONIGHT'")
    assert {(r["player_name"], r["status"]) for r in rows} == {("Anthony Edwards", "Out"), ("Rudy Gobert", "Questionable")}


def test_pending_team_and_failed_report_keep_the_proxy(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "avail2.sqlite3")
    _seed(db, "G_TONIGHT", "2026-11-18T00:30:00Z", "MIN", "POR")
    report = _report(
        [{"team": "MIN", "name": "Anthony Edwards", "status": "Out", "game_date": "11/17/2026", "matchup": "POR@MIN"}],
        pending=["POR"],
    )
    overrides = build_official_availability_overrides(db, report, NOW, persist_snapshot=False)
    assert "POR" not in overrides["G_TONIGHT"]
    assert build_official_availability_overrides(db, {"fetch_ok": False}, NOW) == {}


def _box(team_players: dict[str, list[tuple[str, float, float]]]) -> dict[str, Any]:
    teams = {t: {"fga": 85, "fta": 20, "orb": 10, "drb": 33, "tov": 13, "pts": 112, "fgm": 41, "tpm": 12, "tpa": 35}
             for t in team_players}
    players = {t: [{"name": n, "min": m, "pts": p} for n, m, p in ps] for t, ps in team_players.items()}
    return {"teams": teams, "players": players}


def test_out_list_replaces_the_missed_last_game_proxy() -> None:
    roster = [("Star Player", 36.0, 28.0), ("Role Player", 24.0, 10.0), ("Bench Guy", 14.0, 5.0)]
    opp = [("Opp A", 34.0, 20.0), ("Opp B", 30.0, 15.0), ("Opp C", 20.0, 8.0)]
    games, boxes = [], {}
    for i in range(4):
        gid = f"H{i}"
        games.append({"game_id": gid, "game_start_time": f"2026-11-0{i + 1}T00:00:00Z", "status": "FINAL",
                      "home_team": "MIN", "away_team": "POR"})
        boxes[gid] = _box({"MIN": roster, "POR": opp})
    games.append({"game_id": "NEXT", "game_start_time": "2026-11-18T00:30:00Z", "status": "SCHEDULED",
                  "home_team": "MIN", "away_team": "POR"})
    proxy = compute_boxscore_features(games, boxes)["NEXT"]
    assert proxy["bx_missing_pts_diff"] == 0.0  # everyone played the last game
    out = {"NEXT": {"MIN": frozenset({player_name_key("Star Player")}), "POR": frozenset()}}
    official = compute_boxscore_features(games, boxes, availability_overrides=out)["NEXT"]
    # Home team missing its star: positive diff means away is missing more, so it turns negative
    assert official["bx_missing_pts_diff"] < -20.0
    assert official["bx_new_absence_pts_diff"] < -20.0
