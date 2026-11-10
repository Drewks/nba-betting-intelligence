"""
Authorized Browser Inspection & DOM Table Extractor (`src/ingestion/authorized_scraper.py`).
Uses Browserbase (`browse` CLI / Cloud CDP) & Playwright Chromium with authorized HTTP fallback.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from typing import Any
import urllib.request

from src.ingestion.sportradar import SportradarAdapter

logger = logging.getLogger(__name__)


class PlaywrightAuthorizedScraper:
    """Authorized browser inspection & DOM table extractor using Browserbase (`browse` CLI / Cloud CDP) & Playwright."""

    def __init__(self, headless: bool = True) -> None:
        self.headless = headless

    def _find_browser_cache(self) -> bool:
        candidate_dirs = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright"),
            os.path.expanduser("~/.cache/ms-playwright"),
            os.path.expanduser("~/Library/Caches/ms-playwright"),
            os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""),
        ]
        for d in candidate_dirs:
            if d and os.path.isdir(d) and len(os.listdir(d)) > 0:
                return True
        return False

    def _find_browse_cli(self) -> str | None:
        import shutil
        return shutil.which("browse") or shutil.which("browse.cmd")

    def inspect_status(self) -> dict[str, Any]:
        """Checks Browserbase CLI/Cloud key, Playwright Python package, and browser binary availability."""
        import importlib.util
        extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        pw_installed = importlib.util.find_spec("playwright") is not None
        browsers_installed = self._find_browser_cache()
        browse_cli_path = self._find_browse_cli()
        bb_key_configured = bool(os.getenv("BROWSERBASE_API_KEY", "").strip())

        return {
            "playwright_python_installed": pw_installed,
            "browser_binaries_installed": browsers_installed,
            "browserbase_cli_installed": browse_cli_path is not None,
            "browserbase_api_key_configured": bb_key_configured,
            "browserbase_mode": (
                "REMOTE_CLOUD_CDP"
                if bb_key_configured
                else ("LOCAL_BROWSE_CLI" if browse_cli_path else "PLAYWRIGHT_FALLBACK")
            ),
            "extracted_at": extracted_at,
            "anti_bot_bypass_enabled": False,
            "status": "READY_FOR_BROWSER_INSTALL" if pw_installed and not browsers_installed else (
                "OPERATIONAL" if (pw_installed and browsers_installed) or bb_key_configured or browse_cli_path else "NOT_INSTALLED"
            ),
        }

    def extract_authorized_context_snapshot(self, timeout_ms: int = 8000) -> dict[str, Any]:
        """
        Extracts contextual NBA headlines and tabular injury/matchup notes from authorized public feeds.
        Prioritizes Browserbase Cloud CDP (when BROWSERBASE_API_KEY is set in GitHub Secrets/env) or
        Browserbase `browse` CLI, then local Playwright Chromium, with authorized HTTP fallback.
        """
        extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        documents: list[dict[str, str]] = []
        engine_used = "HTTP_AUTHORIZED_FALLBACK"

        # 1. Fetch ESPN public NBA news & injury context
        try:
            url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news?limit=15"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                news_payload = json.loads(resp.read().decode("utf-8"))
            for art in news_payload.get("articles", []):
                headline = str(art.get("headline", "")).strip()
                desc = str(art.get("description", "")).strip()
                published = str(art.get("published", extracted_at))
                if headline:
                    documents.append(
                        {
                            "source": "espn_nba_news_feed",
                            "title": headline,
                            "content": f"{headline}. {desc}",
                            "captured_at": published,
                        }
                    )
        except Exception as exc:
            logger.warning(f"Failed to fetch ESPN NBA RSS news: {exc}")

        # 1b. Merge official Sportradar NBA v8 injury documents & Synergy Basketball NBA profiles when configured
        try:
            sr_ctx = SportradarAdapter().fetch_league_intelligence_context()
            documents.extend(sr_ctx.get("injury_documents", [])[:90])
        except Exception as exc:
            logger.warning(f"Failed to fetch Sportradar injury docs: {exc}")

        bb_key = os.getenv("BROWSERBASE_API_KEY", "").strip()

        # 2. Priority A: Browserbase Cloud CDP session when BROWSERBASE_API_KEY is configured
        if bb_key:
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as p:
                    browser = p.chromium.connect_over_cdp(
                        f"wss://connect.browserbase.com?apiKey={bb_key}",
                        timeout=timeout_ms,
                    )
                    context = browser.contexts[0] if browser.contexts else browser.new_context()
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(
                        "https://www.espn.com/nba/injuries",
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    page_title = page.title()
                    rows = page.locator("table tr").all_inner_texts()
                    for row_text in rows[:25]:
                        clean_row = " ".join(row_text.split())
                        if len(clean_row) > 15 and "NAME" not in clean_row.upper():
                            documents.append(
                                {
                                    "source": "browserbase_cloud_espn_injuries_table",
                                    "title": page_title or "ESPN NBA Injuries Table (Browserbase Cloud)",
                                    "content": clean_row,
                                    "captured_at": extracted_at,
                                }
                            )
                    browser.close()
                    engine_used = "BROWSERBASE_CLOUD_CDP"
            except Exception:
                engine_used = "BROWSERBASE_KEY_PRESENT_FALLBACK"

        # 3. Priority B: Local Playwright Chromium or Browserbase Local Mode
        if engine_used not in ("BROWSERBASE_CLOUD_CDP",) and self._find_browser_cache():
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=self.headless)
                    page = browser.new_page()
                    page.goto(
                        "https://www.espn.com/nba/injuries",
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    page_title = page.title()
                    rows = page.locator("table tr").all_inner_texts()
                    for row_text in rows[:25]:
                        clean_row = " ".join(row_text.split())
                        if len(clean_row) > 15 and "NAME" not in clean_row.upper():
                            documents.append(
                                {
                                    "source": "playwright_espn_injuries_table",
                                    "title": page_title or "ESPN NBA Injuries Table",
                                    "content": clean_row,
                                    "captured_at": extracted_at,
                                }
                            )
                    browser.close()
                    engine_used = (
                        "BROWSERBASE_LOCAL_PLAYWRIGHT_HYBRID"
                        if self._find_browse_cli()
                        else "PLAYWRIGHT_CHROMIUM_HEADLESS"
                    )
            except Exception:
                engine_used = "PLAYWRIGHT_INSTALLED_HTTP_ASSISTED"

        return {
            "extracted_at": extracted_at,
            "engine_used": engine_used,
            "browserbase_cli_installed": self._find_browse_cli() is not None,
            "browserbase_cloud_configured": bool(bb_key),
            "documents_count": len(documents),
            "documents": documents,
        }
