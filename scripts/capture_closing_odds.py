"""
Captures closing lines for games that start within the next minutes (`scripts/capture_closing_odds.py`).

Run every 15 minutes during the tip-off window by `.github/workflows/closing_capture.yml`, so CLV is
measured against a line taken minutes before tip-off instead of the last regular cycle (23:35 UTC).

Usage:
  uv run python scripts/capture_closing_odds.py               # default 45-minute window
  uv run python scripts/capture_closing_odds.py --window 30
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datetime import datetime, timezone

from src.ingestion.closing_capture import (
    DEFAULT_WINDOW_MINUTES,
    capture_closing_window,
    capture_fingerprint,
    games_in_closing_window,
)
from src.storage.db import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture closing lines for games about to start.")
    parser.add_argument("--db", default=str(PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"))
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW_MINUTES, help="Minutes ahead of now")
    parser.add_argument(
        "--count-upcoming",
        type=int,
        metavar="MINUTES",
        help="Only print how many scheduled games start within MINUTES (used by the capture loop)",
    )
    parser.add_argument(
        "--fingerprint",
        action="store_true",
        help="Only print the row-count fingerprint of the tables a capture writes (used by the loop)",
    )
    args = parser.parse_args()

    db = DatabaseManager(args.db)
    if args.fingerprint:
        print(capture_fingerprint(db))
        return
    if args.count_upcoming is not None:
        print(len(games_in_closing_window(db, datetime.now(timezone.utc), args.count_upcoming)))
        return
    summary = capture_closing_window(db, window_minutes=args.window)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
