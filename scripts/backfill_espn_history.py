"""
Backfills REAL historical NBA results (scores + tip-off times) from ESPN's public scoreboard
so the models train on real basketball instead of synthetic fixtures.

Only final scores and start times are stored. Pre-game ratings / rest days are NOT taken from
ESPN; they are recomputed leakage-free by `src.features.team_ratings.apply_pregame_team_ratings`.

Usage:
    uv run python scripts/backfill_espn_history.py --start 2024-10-22 --end 2026-10-29
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features.team_ratings import apply_pregame_team_ratings
from src.ingestion.normalizer import normalize_season, normalize_team_code
from src.storage.db import DatabaseManager

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d}&limit=50"
VALID_SEASON_TYPES = {2, 3, 5}  # regular season, playoffs, play-in
OFFSEASON_MONTHS = {7, 8, 9}


def _fetch_day(day: date) -> list[dict]:
    url = SCOREBOARD_URL.format(d=day.strftime("%Y%m%d"))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except Exception:
            if attempt == 2:
                return []
    rows: list[dict] = []
    for ev in payload.get("events", []):
        season = ev.get("season", {}) or {}
        if int(season.get("type", 0) or 0) not in VALID_SEASON_TYPES:
            continue
        comp = (ev.get("competitions") or [{}])[0]
        if "FINAL" not in str(comp.get("status", {}).get("type", {}).get("name", "")):
            continue
        cs = comp.get("competitors", [])
        home = next((c for c in cs if c.get("homeAway") == "home"), None)
        away = next((c for c in cs if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        try:
            h_code = normalize_team_code(home["team"]["abbreviation"])
            a_code = normalize_team_code(away["team"]["abbreviation"])
            h_score, a_score = int(home["score"]), int(away["score"])
        except (ValueError, KeyError, TypeError):
            continue  # All-Star / exhibition teams, missing scores
        raw = ev.get("date", "")
        start = raw[:-1] + ":00Z" if len(raw) == 17 and raw.endswith("Z") else raw
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        matchday = start[:10]
        rows.append(
            {
                "game_id": f"ESPN_{ev.get('id')}_{matchday}_{a_code}_AT_{h_code}",
                "season": normalize_season(int(season.get("year", start_dt.year)) - 1),
                "matchday_date": matchday,
                "game_start_time": start,
                "home_team": h_code,
                "away_team": a_code,
                "home_score": h_score,
                "away_score": a_score,
                "features_available_at": (start_dt - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "result_recorded_at": (start_dt + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    return rows


def backfill(db: DatabaseManager, start: date, end: date, workers: int = 8) -> dict:
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    days = [d for d in days if d.month not in OFFSEASON_MONTHS]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_fetch_day, days))
    games = {r["game_id"]: r for day_rows in results for r in day_rows}
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    before = db.fetch_one("SELECT COUNT(*) AS c FROM games")["c"]
    with db.connect() as conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
                away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
                features_available_at, source_provider, ingested_at, result_recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'FINAL', ?, ?, 114.5, 114.5, 99.5, 114.5, 114.5, 99.5, 3, 3,
                      ?, 'espn_history_backfill', ?, ?)
            """,
            [
                (
                    g["game_id"], g["season"], g["matchday_date"], g["game_start_time"],
                    g["home_team"], g["away_team"], g["home_score"], g["away_score"],
                    g["features_available_at"], now_str, g["result_recorded_at"],
                )
                for g in games.values()
            ],
        )
    after = db.fetch_one("SELECT COUNT(*) AS c FROM games")["c"]
    rated = apply_pregame_team_ratings(db)
    return {"days_queried": len(days), "games_found": len(games), "games_inserted": after - before, "games_rated": rated}


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill real NBA history from ESPN scoreboard.")
    parser.add_argument("--start", default="2024-10-22")
    parser.add_argument("--end", default=(datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d"))
    parser.add_argument("--db", default=str(PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"))
    args = parser.parse_args()
    db = DatabaseManager(args.db)
    out = backfill(db, date.fromisoformat(args.start), date.fromisoformat(args.end))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
