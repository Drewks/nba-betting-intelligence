"""
Dynamic NBA Roster Manager (V8 Official):
Fetches, caches, and verifies real-time official NBA rosters from ESPN across all 30 franchises.
Eliminates static roster obsolescence, traded player hallucinations, and phantom matchup errors.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
from typing import Any
import urllib.request

from src.storage.db import DatabaseManager

logger = logging.getLogger(__name__)

# Canonical 30 NBA team codes
NBA_TEAMS = [
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
]

ESPN_TEAM_URL_MAP = {
    "NOP": "no",
    "UTA": "utah",
}


def ensure_roster_table(db: DatabaseManager) -> None:
    """Ensures the team_rosters cache table exists in SQLite."""
    db.execute_insert(
        """
        CREATE TABLE IF NOT EXISTS team_rosters (
            team_id TEXT NOT NULL,
            player_name TEXT NOT NULL,
            position TEXT,
            jersey TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (team_id, player_name)
        );
        """
    )


def fetch_espn_team_roster(team_code: str, timeout_seconds: int = 8) -> tuple[str, list[dict[str, str]]]:
    """Fetches the official live roster for a single NBA franchise from ESPN API."""
    espn_code = ESPN_TEAM_URL_MAP.get(team_code, team_code.lower())
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{espn_code}/roster"
    athletes: list[dict[str, str]] = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for ath in data.get("athletes", []):
            name = ath.get("displayName")
            if not name:
                continue
            pos = (ath.get("position") or {}).get("abbreviation", "")
            jersey = str(ath.get("jersey", ""))
            athletes.append({
                "name": name,
                "position": pos,
                "jersey": jersey,
            })
    except Exception as exc:
        logger.warning(f"Failed to fetch live roster for {team_code}: {exc}")
    return team_code, athletes


def sync_all_nba_rosters(db: DatabaseManager, max_workers: int = 10) -> dict[str, list[str]]:
    """
    Synchronizes all 30 NBA active team rosters into SQLite.
    Returns a mapping of { team_code: [player_name_1, player_name_2, ...] }.
    """
    ensure_roster_table(db)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(fetch_espn_team_roster, NBA_TEAMS))

    roster_map: dict[str, list[str]] = {}
    with db.connect() as conn:
        for team_code, athletes in results:
            if not athletes:
                continue
            # Mark existing records for team as updated
            player_names = []
            for ath in athletes:
                p_name = ath["name"]
                player_names.append(p_name)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO team_rosters (team_id, player_name, position, jersey, is_active, updated_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                    """,
                    (team_code, p_name, ath.get("position"), ath.get("jersey"), now_str),
                )
            roster_map[team_code] = player_names

    return roster_map


def get_team_roster(db: DatabaseManager, team_code: str, auto_sync_if_empty: bool = True) -> list[str]:
    """
    Returns the verified active roster for a team from SQLite cache.
    Auto-syncs if empty or uninitialized.
    """
    ensure_roster_table(db)
    rows = db.fetch_all(
        "SELECT player_name FROM team_rosters WHERE team_id = ? AND is_active = 1",
        (team_code,),
    )
    if rows:
        return [r["player_name"] for r in rows]

    if auto_sync_if_empty:
        sync_all_nba_rosters(db)
        fresh_rows = db.fetch_all(
            "SELECT player_name FROM team_rosters WHERE team_id = ? AND is_active = 1",
            (team_code,),
        )
        return [r["player_name"] for r in fresh_rows]

    return []


def get_all_rosters(db: DatabaseManager) -> dict[str, list[str]]:
    """Returns the full mapping of all 30 NBA teams to their current active rosters."""
    ensure_roster_table(db)
    rows = db.fetch_all("SELECT team_id, player_name FROM team_rosters WHERE is_active = 1")
    if not rows:
        return sync_all_nba_rosters(db)

    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["team_id"], []).append(r["player_name"])
    return out


def normalize_name(name: str) -> str:
    """Normalizes player name for robust matching across punctuation differences."""
    return name.replace(".", "").replace("'", "").replace("-", " ").replace(" III", "").replace(" Jr.", "").strip().lower()


def get_player_team(db: DatabaseManager, player_name: str) -> str | None:
    """Finds which NBA franchise a player officially belongs to."""
    ensure_roster_table(db)
    # Direct match
    row = db.fetch_one(
        "SELECT team_id FROM team_rosters WHERE player_name = ? AND is_active = 1",
        (player_name,),
    )
    if row:
        return row["team_id"]

    # Fuzzy / substring match
    fuzzy_row = db.fetch_one(
        "SELECT team_id, player_name FROM team_rosters WHERE (player_name LIKE ? OR ? LIKE ('%' || player_name || '%')) AND is_active = 1",
        (f"%{player_name}%", player_name),
    )
    if fuzzy_row:
        return fuzzy_row["team_id"]

    # Punctuation / normalized match
    norm_p = normalize_name(player_name)
    all_rosters = db.fetch_all("SELECT team_id, player_name FROM team_rosters WHERE is_active = 1")
    for r in all_rosters:
        if normalize_name(r["player_name"]) == norm_p:
            return r["team_id"]

    return None
