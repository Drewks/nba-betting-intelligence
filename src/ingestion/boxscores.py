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
import sqlite3
from typing import Any
import urllib.error
import urllib.request

from src.ingestion.normalizer import normalize_player_match_key, normalize_team_code
from src.storage.db import DatabaseManager
from src.validation.validator import parse_iso_utc

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


def upsert_player_boxscores_rows(
    conn: sqlite3.Connection,
    game_id: str,
    game_start_time: str,
    players_by_team: dict[str, Any] | None,
) -> int:
    """Flattens ESPN per-player boxscore JSON into the indexed `player_boxscores` table."""
    if not isinstance(players_by_team, dict) or not game_start_time:
        return 0
    upserted = 0
    for raw_team, p_list in players_by_team.items():
        if not isinstance(p_list, list):
            continue
        try:
            team_code = normalize_team_code(str(raw_team))
        except ValueError:
            team_code = str(raw_team or "").strip().upper()
        if not team_code:
            continue
        for p in p_list:
            if not isinstance(p, dict):
                continue
            p_name = str(p.get("name") or "").strip()
            p_key = normalize_player_match_key(p_name)
            if not p_key:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO player_boxscores (
                    game_id, player_name, player_key, team, game_start_time,
                    minutes, pts, reb, ast, threed, starter
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    p_name,
                    p_key,
                    team_code,
                    game_start_time,
                    float(p.get("min") or 0.0),
                    float(p.get("pts") or 0.0),
                    float(p.get("reb") or 0.0),
                    float(p.get("ast") or 0.0),
                    float(p.get("threed") or 0.0),
                    1 if p.get("starter") else 0,
                ),
            )
            upserted += 1
    return upserted


def backfill_boxscores(
    db: DatabaseManager,
    limit: int | None = None,
    workers: int = 8,
    *,
    max_404_attempts: int = 3,
    permanent_404_min_age_days: int = 7,
) -> dict[str, int]:
    """Fetches box scores for FINAL real games not yet stored and not marked permanently unavailable."""
    missing = db.fetch_all(
        """
        SELECT g.game_id, g.game_start_time FROM games g
        WHERE g.status = 'FINAL' AND g.game_id LIKE 'ESPN_%'
          AND g.game_id NOT IN (SELECT game_id FROM game_boxscores)
          AND g.game_id NOT IN (
              SELECT game_id FROM boxscore_fetch_failures WHERE permanently_unavailable = 1
          )
        ORDER BY g.game_start_time ASC
        """
    )
    start_by_id = {str(r["game_id"]): str(r["game_start_time"]) for r in missing}
    ids = [str(r["game_id"]) for r in missing if espn_event_id(str(r["game_id"]))]
    if limit is not None:
        ids = ids[:limit]

    prior_failures = {
        str(r["game_id"]): int(r["attempts"] or 0)
        for r in db.fetch_all("SELECT game_id, attempts FROM boxscore_fetch_failures")
    }

    def _one(game_id: str) -> tuple[str, dict[str, Any] | None, int | None, str | None]:
        try:
            return game_id, fetch_boxscore(str(espn_event_id(game_id))), None, None
        except urllib.error.HTTPError as exc:
            logger.warning("Box score fetch failed for %s: %s", game_id, exc)
            return game_id, None, int(exc.code), str(exc)[:300]
        except Exception as exc:
            logger.warning("Box score fetch failed for %s: %s", game_id, exc)
            return game_id, None, None, str(exc)[:300]

    stored = 0
    player_rows_stored = 0
    failed = 0
    marked_permanent = 0
    now_dt = datetime.now(timezone.utc)
    now = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_one, ids))
    with db.connect() as conn:
        for game_id, box, http_status, error_msg in results:
            if box is None:
                failed += 1
                new_attempts = prior_failures.get(game_id, 0) + 1
                game_age_days = 0.0
                start_raw = start_by_id.get(game_id, "")
                if start_raw:
                    try:
                        game_age_days = (now_dt - parse_iso_utc(start_raw)).total_seconds() / 86400.0
                    except Exception:
                        game_age_days = 0.0
                perm = (
                    1
                    if (
                        http_status == 404
                        and new_attempts >= max_404_attempts
                        and game_age_days >= permanent_404_min_age_days
                    )
                    else 0
                )
                conn.execute(
                    """
                    INSERT INTO boxscore_fetch_failures (
                        game_id, http_status, error_message, attempts,
                        first_failed_at, last_failed_at, permanently_unavailable
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(game_id) DO UPDATE SET
                        http_status = excluded.http_status,
                        error_message = excluded.error_message,
                        attempts = boxscore_fetch_failures.attempts + 1,
                        last_failed_at = excluded.last_failed_at,
                        permanently_unavailable = excluded.permanently_unavailable
                    """,
                    (game_id, http_status, error_msg, 1, now, now, perm),
                )
                if perm == 1:
                    marked_permanent += 1
                    logger.info(
                        "Marking %s boxscore permanently unavailable after %d HTTP 404 failures.",
                        game_id,
                        new_attempts,
                    )
                continue

            conn.execute("DELETE FROM boxscore_fetch_failures WHERE game_id = ?", (game_id,))
            conn.execute(
                "INSERT OR IGNORE INTO game_boxscores (game_id, team_stats_json, players_json, source, fetched_at) "
                "VALUES (?, ?, ?, 'espn_summary', ?)",
                (game_id, json.dumps(box["teams"]), json.dumps(box["players"], ensure_ascii=False), now),
            )
            player_rows_stored += upsert_player_boxscores_rows(
                conn,
                game_id,
                start_by_id.get(game_id, ""),
                box.get("players"),
            )
            stored += 1
    return {
        "requested": len(ids),
        "stored": stored,
        "player_rows_stored": player_rows_stored,
        "failed": failed,
        "marked_permanent": marked_permanent,
    }


def load_boxscores(db: DatabaseManager) -> dict[str, dict[str, Any]]:
    return {
        r["game_id"]: {"teams": json.loads(r["team_stats_json"]), "players": json.loads(r["players_json"])}
        for r in db.fetch_all("SELECT game_id, team_stats_json, players_json FROM game_boxscores")
    }
