"""
Phase 4 Verification Tests (`tests/test_phase4_scraper_config.py`):
1. Validation of ScraperConfig, PlaywrightBrowserConfig, and SportsbookEndpointConfig from YAML.
2. Reactivity of PeruPlaywrightScraper to custom endpoints and headless browser parameters.
3. Dynamic team slug mappings in roster_manager via get_espn_team_url_map().
"""

from __future__ import annotations


from src.config import (
    ScraperConfig,
    PlaywrightBrowserConfig,
    SportsbookEndpointConfig,
    ESPNConfig,
    ViewportConfig,
    load_scraper_config,
)
from src.ingestion.playwright_scraper import PeruPlaywrightScraper
from src.ingestion.roster_manager import get_espn_team_url_map


def test_phase4_load_scraper_config_from_yaml() -> None:
    """Verifies that scraper_config.yaml is loaded with correct typing and properties."""
    cfg = load_scraper_config()
    assert isinstance(cfg, ScraperConfig)
    assert isinstance(cfg.playwright, PlaywrightBrowserConfig)
    assert cfg.playwright.headless is True
    assert cfg.playwright.timeout_ms == 15000
    assert cfg.playwright.wait_after_load_ms == 2000
    assert cfg.playwright.viewport.width == 1280
    assert cfg.playwright.viewport.height == 800
    assert "Chrome" in cfg.playwright.user_agent

    # Sportsbooks
    assert "retabet" in cfg.sportsbooks
    assert "betano" in cfg.sportsbooks
    retabet = cfg.sportsbooks["retabet"]
    assert retabet.name == "RETAbet Perú"
    assert "retabet.pe" in retabet.nba_url
    assert retabet.enabled is True

    betano = cfg.sportsbooks["betano"]
    assert betano.name == "Betano Perú"
    assert "betano.com" in betano.nba_url

    # ESPN team map
    assert cfg.espn.team_url_map.get("NOP") == "no"
    assert cfg.espn.team_url_map.get("UTA") == "utah"


def test_phase4_custom_scraper_config_injection() -> None:
    """Verifies that PeruPlaywrightScraper respects custom configuration."""
    custom_cfg = ScraperConfig(
        playwright=PlaywrightBrowserConfig(
            headless=False,
            timeout_ms=30000,
            wait_after_load_ms=5000,
            viewport=ViewportConfig(width=1920, height=1080),
        ),
        sportsbooks={
            "retabet": SportsbookEndpointConfig(
                name="RETAbet Custom",
                nba_url="https://custom.retabet.pe/nba",
                timeout_ms=25000,
                wait_after_load_ms=4000,
            ),
        },
        espn=ESPNConfig(
            team_url_map={"BOS": "celtics", "LAL": "lakers"},
        ),
    )

    scraper = PeruPlaywrightScraper(config=custom_cfg)
    assert scraper.headless is False
    assert scraper.timeout_ms == 30000
    assert scraper.config.playwright.viewport.width == 1920
    assert scraper.config.sportsbooks["retabet"].nba_url == "https://custom.retabet.pe/nba"
    assert scraper.config.sportsbooks["retabet"].timeout_ms == 25000


def test_phase4_roster_manager_slug_mapping() -> None:
    """Verifies that roster_manager utilizes dynamic slug mappings."""
    slug_map = get_espn_team_url_map()
    assert isinstance(slug_map, dict)
    assert slug_map["NOP"] == "no"
    assert slug_map["UTA"] == "utah"
