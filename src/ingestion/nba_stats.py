"""
NBAStatsAdapter (`src/ingestion/nba_stats.py`):
Interchangeable adapter for NBA.com/stats (stats.nba.com).
"""

from __future__ import annotations

import json
from typing import Any
import urllib.request

from src.ingestion.base import AdapterUnavailableError, BaseNBADataAdapter


class NBAStatsAdapter(BaseNBADataAdapter):
    """Interchangeable adapter for NBA.com/stats (stats.nba.com)."""

    provider_name = "nba_com_stats"

    def __init__(self, timeout_seconds: int = 8) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_games_and_odds(
        self,
        date_str: str | None = None,
        as_of_utc: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        url = (
            "https://stats.nba.com/stats/leaguegamelog?"
            "Counter=100&DateFrom=&DateTo=&Direction=DESC&LeagueID=00&"
            "PlayerOrTeam=T&Season=2025-26&SeasonType=Regular%20Season&Sorter=DATE"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://www.nba.com/",
            "Origin": "https://www.nba.com",
            "Accept": "application/json",
            "x-nba-stats-origin": "stats",
            "x-nba-stats-token": "true",
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                _ = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise AdapterUnavailableError(
                f"NBAStatsAdapter unreachable or blocked by Akamai TLS filter ({exc}). "
                "Note: stats.nba.com does not provide historical bookmaker odds."
            ) from exc
        return {"games": [], "odds": []}
