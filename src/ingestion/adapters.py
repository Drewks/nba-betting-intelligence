"""
Interchangeable NBA data and odds adapters (V2 Syndicate-Grade):
Modular facade re-exporting specialized adapters:
- ESPNPublicAdapter (from src.ingestion.espn)
- TheOddsAPIAdapter (from src.ingestion.the_odds_api)
- SportradarAdapter (from src.ingestion.sportradar)
- NBAStatsAdapter (from src.ingestion.nba_stats)
- PlaywrightAuthorizedScraper (from src.ingestion.authorized_scraper)
- DataSourceRouter (from src.ingestion.router)
- BaseNBADataAdapter, AdapterUnavailableError (from src.ingestion.base)
"""

from __future__ import annotations

from src.ingestion.authorized_scraper import PlaywrightAuthorizedScraper
from src.ingestion.base import AdapterUnavailableError, BaseNBADataAdapter
from src.ingestion.context_constants import (
    HIGH_ALTITUDE_BONUS_PTS,
    LONG_TERM_INJURY_KEYWORDS,
    NBA_REFEREE_CREW_PROFILE,
    STAR_PLAYER_IMPACT_PTS,
)
from src.ingestion.espn import ESPNPublicAdapter
from src.ingestion.nba_stats import NBAStatsAdapter
from src.ingestion.router import DataSourceRouter
from src.ingestion.sportradar import SportradarAdapter
from src.ingestion.the_odds_api import TheOddsAPIAdapter

__all__ = [
    "BaseNBADataAdapter",
    "TheOddsAPIAdapter",
    "ESPNPublicAdapter",
    "SportradarAdapter",
    "NBAStatsAdapter",
    "PlaywrightAuthorizedScraper",
    "DataSourceRouter",
    "AdapterUnavailableError",
    "STAR_PLAYER_IMPACT_PTS",
    "HIGH_ALTITUDE_BONUS_PTS",
    "NBA_REFEREE_CREW_PROFILE",
    "LONG_TERM_INJURY_KEYWORDS",
]
