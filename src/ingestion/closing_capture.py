"""
Closing-line capture (`src/ingestion/closing_capture.py`).

CLV is only as good as the closing line it is measured against. The regular cycles run at fixed times
(the last pre-game run is 23:35 UTC), so for a 02:30 UTC tip-off the "closing" quote was captured three
hours before the game while the line was still moving. This module is run by a light workflow every
15 minutes during the tip-off window: it captures the observed live quotes (Pinnacle, Te Apuesto,
Betano) of the games that start within the next `window_minutes` and promotes the latest pre-tip
capture to the closing line, so the close is taken minutes before tip-off.

Nothing is inferred: only quotes the books actually served are stored, with their capture time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from src.paper_trading.settlement import persist_closing_lines_for_games
from src.validation.validator import parse_iso_utc

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_MINUTES = 45


# Tables a closing capture can add rows to. Opening the database rewrites its bytes even when nothing
# changes, so "did the capture add data" is decided on row counts, never on the file.
CAPTURE_TABLES: tuple[str, ...] = ("odds_snapshots", "quarantined_odds", "audit_row_registry")


def capture_fingerprint(db: Any) -> str:
    """Row counts of the tables a capture writes, as a comparable string."""
    parts = []
    for table in CAPTURE_TABLES:
        row = db.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")
        parts.append(f"{table}={int(row['n']) if row else 0}")
    return ";".join(parts)


def games_in_closing_window(db: Any, now: datetime, window_minutes: int = DEFAULT_WINDOW_MINUTES) -> list[dict[str, Any]]:
    """Scheduled real games that have not started and start within the next `window_minutes`."""
    now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = (now + timedelta(minutes=window_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = db.fetch_all(
        """
        SELECT game_id, home_team, away_team, game_start_time
        FROM v_observed_games
        WHERE status = 'SCHEDULED'
          AND datetime(game_start_time) > datetime(?)
          AND datetime(game_start_time) <= datetime(?)
        ORDER BY game_start_time ASC
        """,
        (now_str, end_str),
    )
    return [dict(r) for r in rows]


def capture_closing_window(
    db: Any,
    collector: Any = None,
    now: datetime | None = None,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
) -> dict[str, Any]:
    """
    Captures observed quotes for games about to start and promotes the latest pre-tip capture of every
    (book, market, side, line) to a closing line. Returns a summary; never raises on a single book error.
    `collector` is any object with LivePeruOddsScraper.collect_slate_odds' signature (tests pass a fake).
    """
    now_dt = now or datetime.now(timezone.utc)
    games = games_in_closing_window(db, now_dt, window_minutes)
    summary: dict[str, Any] = {
        "captured_at": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_minutes": window_minutes,
        "games_in_window": len(games),
        "games": [],
        "closing_lines_promoted": 0,
    }
    if not games:
        return summary

    active: Any
    if collector is None:
        from src.ingestion.live_peru_scraper import LivePeruOddsScraper

        active = LivePeruOddsScraper(db=db)
    else:
        active = collector

    for g in games:
        entry: dict[str, Any] = {"game_id": g["game_id"], "game_start_time": g["game_start_time"]}
        if parse_iso_utc(g["game_start_time"]) <= now_dt:
            entry["skipped"] = "already_started"
            summary["games"].append(entry)
            continue
        try:
            res = active.collect_slate_odds(
                game_id=g["game_id"],
                home_team=g["home_team"],
                away_team=g["away_team"],
                game_start_time=g["game_start_time"],
                as_of_utc=now_dt,
                include_player_props=False,
            )
            entry["observed_quotes"] = int(res.get("observed_quotes_count") or 0)
        except Exception as exc:  # one failing book must not lose the other books' closes
            logger.warning("Closing capture failed for %s: %s", g["game_id"], exc)
            entry["error"] = str(exc)
        summary["games"].append(entry)

    summary["closing_lines_promoted"] = persist_closing_lines_for_games(
        db,
        as_of_utc=now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        include_player_props=False,
    )
    return summary
