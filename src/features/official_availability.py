"""
Official NBA injury report -> availability overrides for upcoming games (`src/features/official_availability.py`).

The box-score availability features (`bx_missing_*`) were computed with a proxy: rotation players who
did not play the team's last game. For upcoming games the league's official injury report says who is
ruled OUT, which is a better measurement of the same quantity. Each team appears in the report for its
game, and each entry carries that game's date (US Eastern) and matchup ("TOR@PHI"): an entry is applied
only to the scheduled game with the same Eastern date and teams, so a report about yesterday's game is
never applied to tomorrow's.

Only the report fetched at decision time is used (no lookahead), and every list applied is stored in
`injury_status_snapshots` so the audit trail shows what the model saw.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any
from zoneinfo import ZoneInfo

from src.features.boxscore_features import player_name_key
from src.ingestion.normalizer import normalize_team_code
from src.validation.validator import parse_iso_utc

EASTERN = ZoneInfo("America/New_York")

logger = logging.getLogger(__name__)

OUT_STATUSES = frozenset({"out"})
DEFAULT_HORIZON_HOURS = 36


def build_official_availability_overrides(
    db: Any,
    report: dict[str, Any],
    now: datetime,
    horizon_hours: int = DEFAULT_HORIZON_HOURS,
    persist_snapshot: bool = True,
) -> dict[str, dict[str, frozenset[str]]]:
    """
    Returns {game_id: {team: player name keys ruled OUT}} for scheduled games within `horizon_hours`
    that the report covers (a team listed with nobody OUT gets an empty set: nobody is missing).
    A failed or empty report returns {} (the proxy stays in use).
    """
    if not report.get("fetch_ok") or not report.get("by_team"):
        return {}
    now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = (now + timedelta(hours=horizon_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    upcoming = db.fetch_all(
        """
        SELECT game_id, home_team, away_team, game_start_time FROM v_observed_games
        WHERE status = 'SCHEDULED'
          AND datetime(game_start_time) > datetime(?)
          AND datetime(game_start_time) <= datetime(?)
        ORDER BY game_start_time ASC
        """,
        (now_str, end_str),
    )
    # (Eastern game date "MM/DD/YYYY", frozenset of the two teams) -> game_id
    games_by_key: dict[tuple[str, frozenset[str]], str] = {}
    for g in upcoming:
        et_date = parse_iso_utc(str(g["game_start_time"])).astimezone(EASTERN).strftime("%m/%d/%Y")
        games_by_key[(et_date, frozenset({str(g["home_team"]), str(g["away_team"])}))] = str(g["game_id"])

    def _game_for(entry: dict[str, Any]) -> str | None:
        matchup = str(entry.get("matchup") or "")
        date_txt = str(entry.get("game_date") or "").strip()
        if "@" not in matchup or not date_txt:
            return None
        try:
            teams = frozenset(normalize_team_code(t.strip()) for t in matchup.split("@", 1))
            et_date = datetime.strptime(date_txt, "%m/%d/%Y").strftime("%m/%d/%Y")
        except Exception:
            return None
        return games_by_key.get((et_date, teams))

    captured_at = str(report.get("captured_at") or now_str)
    overrides: dict[str, dict[str, frozenset[str]]] = {}
    snapshot_rows: list[tuple[str, str, str, str, str, str, str]] = []
    for team, entries in (report.get("by_team") or {}).items():
        for e in entries:
            name = str(e.get("name") or "")
            game_id = _game_for(e)
            if game_id is None or not name:
                continue
            team_out = overrides.setdefault(game_id, {}).setdefault(str(team), frozenset())
            if str(e.get("status") or "").strip().lower() in OUT_STATUSES:
                overrides[game_id][str(team)] = team_out | {player_name_key(name)}
            snapshot_rows.append((
                f"INJ_{game_id}_{captured_at}_{team}_{name}",
                game_id,
                captured_at,
                str(team),
                name,
                str(e.get("status") or ""),
                "nba_official_injury_report",
            ))

    # A game the report covers: the other team, if not listed, has nobody ruled out, unless it has not
    # submitted its report yet (then its proxy stays in use).
    pending = {str(t) for t in (report.get("not_yet_submitted_teams") or [])}
    teams_by_game = {gid: teams for (_d, teams), gid in games_by_key.items()}
    for game_id, by_team in overrides.items():
        for team in teams_by_game.get(game_id, frozenset()):
            if team not in pending:
                by_team.setdefault(team, frozenset())

    if persist_snapshot and snapshot_rows:
        with db.connect() as conn:
            conn.executemany("INSERT OR IGNORE INTO injury_status_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)", snapshot_rows)
    logger.info(
        "Official injury report applied to %d upcoming games (%d team lists)",
        len(overrides),
        sum(len(v) for v in overrides.values()),
    )
    return overrides
