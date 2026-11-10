"""
ESPN box score ingestion (team totals + per-player minutes) for FINAL games.

Box scores are post-game facts: they may only feed features of games that start LATER
(see src/features/boxscore_features.py, which enforces this in a single chronological pass).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
from typing import Any
import urllib.request

from src.ingestion.normalizer import normalize_team_code
from src.storage.db import DatabaseManager

logger = logging.getLogger(__name__)

SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}"


def espn_event_id(game_id: str) -> str | None:
    parts = str(game_id).split("_")
    return parts[1] if len(parts) > 2 and parts[0] == "ESPN" and parts[1].isdigit() else None


def _pair(value: str) -> tuple[float, float]:
    made, _, att = str(value).partition("-")
    return float(made), float(att)


def parse_boxscore(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Returns {'teams': {CODE: {...}}, 'players': {CODE: [{name, min, pts, starter}]}} or None if incomplete."""
    box = payload.get("boxscore") or {}
    teams: dict[str, dict[str, float]] = {}
    for t in box.get("teams") or []:
        try:
            code = normalize_team_code((t.get("team") or {}).get("abbreviation", ""))
        except ValueError:
            return None
        raw = {s.get("name"): s.get("displayValue") for s in t.get("statistics") or []}
        try:
            fgm, fga = _pair(raw["fieldGoalsMade-fieldGoalsAttempted"])
            tpm, tpa = _pair(raw["threePointFieldGoalsMade-threePointFieldGoalsAttempted"])
            ftm, fta = _pair(raw["freeThrowsMade-freeThrowsAttempted"])
            teams[code] = {
                "fgm": fgm, "fga": fga, "tpm": tpm, "tpa": tpa, "ftm": ftm, "fta": fta,
                "orb": float(raw["offensiveRebounds"]), "drb": float(raw["defensiveRebounds"]),
                "tov": float(raw.get("totalTurnovers") or raw["turnovers"]),
                "pts": 2.0 * fgm + tpm + ftm,
            }
        except (KeyError, ValueError, TypeError):
            return None
    players: dict[str, list[dict[str, Any]]] = {}
    for p in box.get("players") or []:
        try:
            code = normalize_team_code((p.get("team") or {}).get("abbreviation", ""))
        except ValueError:
            continue
        rows: list[dict[str, Any]] = []
        for cat in p.get("statistics") or []:
            labels = [str(x).upper() for x in cat.get("labels") or []]
            for ath in cat.get("athletes") or []:
                name = (ath.get("athlete") or {}).get("displayName")
                stats = dict(zip(labels, ath.get("stats") or [], strict=False))
                try:
                    minutes = float(stats.get("MIN") or 0.0)
                    pts = float(stats.get("PTS") or 0.0)
                    reb = float(stats.get("REB") or 0.0)
                    ast = float(stats.get("AST") or 0.0)
                    raw_3pt = stats.get("3PT") or stats.get("3PM") or "0-0"
                    threed = float(str(raw_3pt).split("-")[0]) if "-" in str(raw_3pt) else float(raw_3pt or 0.0)
                except (ValueError, TypeError):
                    minutes, pts, reb, ast, threed = 0.0, 0.0, 0.0, 0.0, 0.0
                if name:
                    rows.append({
                        "name": name,
                        "min": minutes,
                        "pts": pts,
                        "reb": reb,
                        "ast": ast,
                        "threed": threed,
                        "starter": bool(ath.get("starter")),
                    })
        players[code] = rows
    if len(teams) != 2 or any(v["fga"] <= 0 for v in teams.values()):
        return None
    return {"teams": teams, "players": players}


def fetch_boxscore(event_id: str, timeout: int = 15) -> dict[str, Any] | None:
    req = urllib.request.Request(SUMMARY_URL.format(event_id=event_id), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse_boxscore(json.loads(resp.read().decode("utf-8")))


def backfill_boxscores(db: DatabaseManager, limit: int | None = None, workers: int = 8) -> dict[str, int]:
    """Fetches box scores for FINAL real games that do not have one yet (oldest first)."""
    missing = db.fetch_all(
        """
        SELECT g.game_id FROM games g
        WHERE g.status = 'FINAL' AND g.game_id LIKE 'ESPN_%'
          AND g.game_id NOT IN (SELECT game_id FROM game_boxscores)
        ORDER BY g.game_start_time ASC
        """
    )
    ids = [r["game_id"] for r in missing if espn_event_id(r["game_id"])]
    if limit is not None:
        ids = ids[:limit]

    def _one(game_id: str) -> tuple[str, dict[str, Any] | None]:
        try:
            return game_id, fetch_boxscore(str(espn_event_id(game_id)))
        except Exception as exc:
            logger.warning("Box score fetch failed for %s: %s", game_id, exc)
            return game_id, None

    stored = 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_one, ids))
    with db.connect() as conn:
        for game_id, box in results:
            if box is None:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO game_boxscores (game_id, team_stats_json, players_json, source, fetched_at) "
                "VALUES (?, ?, ?, 'espn_summary', ?)",
                (game_id, json.dumps(box["teams"]), json.dumps(box["players"], ensure_ascii=False), now),
            )
            stored += 1
    return {"requested": len(ids), "stored": stored}


def load_boxscores(db: DatabaseManager) -> dict[str, dict[str, Any]]:
    return {
        r["game_id"]: {"teams": json.loads(r["team_stats_json"]), "players": json.loads(r["players_json"])}
        for r in db.fetch_all("SELECT game_id, team_stats_json, players_json FROM game_boxscores")
    }
