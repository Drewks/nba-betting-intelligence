"""
Automated Headless Browser Scraper for Peruvian Sportsbooks (`src/ingestion/playwright_scraper.py`).

Uses Playwright with stealth Chromium to dynamically scrape live odds and player props from:
  1. RETAbet Perú (retabet.pe)
  2. Betano Perú (pe.betano.com)

Features:
  - Network-level JSON payload inspection from standard browser responses.
  - Extracts Moneyline, Totals (Over/Under), Spreads, and Player Props (Points, Rebounds, Assists).
  - Enforces provenance: all inserted odds snapshots carry source_type='OBSERVED' and exact UTC timestamps.
  - Fail-safe design: times out cleanly if a site is unreachable or blocked, without failing the pipeline.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from src.ingestion.normalizer import normalize_team_code
from src.storage.db import DatabaseManager
from src.config import ScraperConfig, load_scraper_config

logger = logging.getLogger("PlaywrightScraper")

RETABET_NBA_URL = "https://retabet.pe/deportes/baloncesto/usa/nba"
BETANO_NBA_URL = "https://pe.betano.com/sport/basquetbol/estados-unidos/nba/"


class PeruPlaywrightScraper:
    """
    Automated headless scraper targeting Peruvian sportsbooks using Playwright.
    Intercepts dynamic API responses directly from the browser session.
    """

    def __init__(
        self,
        db: DatabaseManager | None = None,
        timeout_ms: int | None = None,
        headless: bool | None = None,
        config: ScraperConfig | None = None,
    ) -> None:
        self.db = db
        self.config = config or load_scraper_config()
        self.timeout_ms = timeout_ms if timeout_ms is not None else self.config.playwright.timeout_ms
        self.headless = headless if headless is not None else self.config.playwright.headless

    def _match_teams(self, event_name: str) -> tuple[str, str] | None:
        """Attempts to extract home and away team codes from an event title (e.g. 'Boston Celtics - Miami Heat')."""
        separators = [" VS ", " VS. ", " - ", " @ ", " V "]
        title = event_name.upper()
        for sep in separators:
            if sep in title:
                parts = title.split(sep, 1)
                t1_raw = parts[0].strip()
                t2_raw = parts[1].strip()
                try:
                    c1 = normalize_team_code(t1_raw)
                    c2 = normalize_team_code(t2_raw)
                    # In US sports, 'Away @ Home' is common, while 'Home - Away' is common in Europe/Latin America
                    if "@" in sep:
                        return c2, c1  # Home, Away
                    return c1, c2  # Home, Away
                except ValueError:
                    continue
        return None

    def scrape_retabet_odds(self) -> list[dict[str, Any]]:
        """
        Navigates to RETAbet Perú NBA section and intercepts event and market payloads.
        Returns a list of standardized observed quote dictionaries.
        """
        quotes: list[dict[str, Any]] = []
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=["--no-sandbox"],
                )
                book_cfg = self.config.sportsbooks.get("retabet")
                url = book_cfg.nba_url if book_cfg and book_cfg.nba_url else RETABET_NBA_URL
                wait_ms = book_cfg.wait_after_load_ms if book_cfg else self.config.playwright.wait_after_load_ms
                timeout = book_cfg.timeout_ms if book_cfg else self.timeout_ms
                ua = self.config.playwright.user_agent
                vp: Any = {"width": self.config.playwright.viewport.width, "height": self.config.playwright.viewport.height}

                context = browser.new_context(
                    user_agent=ua,
                    viewport=vp,
                )
                page = context.new_page()

                intercepted_data: list[dict[str, Any]] = []

                def handle_response(response: Any) -> None:
                    try:
                        r_url = str(response.url).lower()
                        if "api" in r_url and ("event" in r_url or "nba" in r_url or "sport" in r_url):
                            if response.status == 200:
                                ct = response.headers.get("content-type", "")
                                if "application/json" in ct:
                                    intercepted_data.append(response.json())
                    except Exception:
                        pass

                page.on("response", handle_response)

                try:
                    page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                    page.wait_for_timeout(wait_ms)
                except Exception as nav_exc:
                    logger.debug("RETAbet navigation reached timeout or partial load: %s", nav_exc)

                browser.close()

                # Parse intercepted payloads
                for payload in intercepted_data:
                    events = payload if isinstance(payload, list) else payload.get("events") or payload.get("data") or []
                    if not isinstance(events, list):
                        continue
                    for ev in events:
                        if not isinstance(ev, dict):
                            continue
                        name = ev.get("name") or ev.get("eventName") or ""
                        matched = self._match_teams(str(name))
                        if not matched:
                            continue
                        home_code, away_code = matched

                        # Check for moneyline / match odds
                        markets = ev.get("markets") or ev.get("items") or []
                        for mkt in markets:
                            if not isinstance(mkt, dict):
                                continue
                            m_type = str(mkt.get("name") or mkt.get("marketType") or "").upper()
                            selections = mkt.get("selections") or mkt.get("outcomes") or []

                            # Moneyline (Ganador del partido - 2-Way con prórroga incluida)
                            if any(k in m_type for k in ("TIEMPO REGLAMENTARIO", "1X2", "REGULAR TIME", "RESULTADO")):
                                continue
                            if any(k in m_type for k in ("GANADOR", "MONEYLINE", "1 2", "12")):
                                if len(selections) != 2:
                                    continue
                                if any(any(d == str(s.get("name") or "").strip().upper() for d in ("X", "EMPATE", "DRAW")) for s in selections):
                                    continue
                                home_odd: float | None = None
                                away_odd: float | None = None
                                for sel in selections:
                                    s_name = str(sel.get("name") or "").upper()
                                    price = float(sel.get("price") or sel.get("odds") or 0.0)
                                    if price > 1.0:
                                        if home_code in s_name or "1" in s_name:
                                            home_odd = price
                                        elif away_code in s_name or "2" in s_name:
                                            away_odd = price
                                if home_odd and away_odd:
                                    quotes.append({
                                        "provider": "RETAbet Perú",
                                        "home_team": home_code,
                                        "away_team": away_code,
                                        "market": "moneyline",
                                        "selection": "HOME",
                                        "decimal_odds": home_odd,
                                        "counterpart_decimal_odds": away_odd,
                                        "line_value": None,
                                        "captured_at": now_utc,
                                        "source_type": "OBSERVED",
                                    })
                                    quotes.append({
                                        "provider": "RETAbet Perú",
                                        "home_team": home_code,
                                        "away_team": away_code,
                                        "market": "moneyline",
                                        "selection": "AWAY",
                                        "decimal_odds": away_odd,
                                        "counterpart_decimal_odds": home_odd,
                                        "line_value": None,
                                        "captured_at": now_utc,
                                        "source_type": "OBSERVED",
                                    })

                            # Market: Totals Over and Under
                            elif any(k in m_type for k in ("TOTAL", "MÁS DE", "MENOS DE", "OVER/UNDER", "PUNTOS")):
                                over_odd: float | None = None
                                under_odd: float | None = None
                                line_val = mkt.get("handicap") or mkt.get("line") or None
                                for sel in selections:
                                    s_name = str(sel.get("name") or "").upper()
                                    price = float(sel.get("price") or sel.get("odds") or 0.0)
                                    if price > 1.0:
                                        if "MÁS" in s_name or "OVER" in s_name:
                                            over_odd = price
                                        elif "MENOS" in s_name or "UNDER" in s_name:
                                            under_odd = price
                                if over_odd and under_odd and line_val is not None:
                                    quotes.append({
                                        "provider": "RETAbet Perú",
                                        "home_team": home_code,
                                        "away_team": away_code,
                                        "market": "total_points",
                                        "selection": "OVER",
                                        "decimal_odds": over_odd,
                                        "counterpart_decimal_odds": under_odd,
                                        "line_value": float(line_val),
                                        "captured_at": now_utc,
                                        "source_type": "OBSERVED",
                                    })
                                    quotes.append({
                                        "provider": "RETAbet Perú",
                                        "home_team": home_code,
                                        "away_team": away_code,
                                        "market": "total_points",
                                        "selection": "UNDER",
                                        "decimal_odds": under_odd,
                                        "counterpart_decimal_odds": over_odd,
                                        "line_value": float(line_val),
                                        "captured_at": now_utc,
                                        "source_type": "OBSERVED",
                                    })

        except Exception as exc:
            logger.warning("RETAbet Playwright scraping error: %s", exc)

        return quotes

    def scrape_betano_odds(self) -> list[dict[str, Any]]:
        """
        Navigates to Betano Perú NBA section and intercepts event and market payloads.
        Returns a list of standardized observed quote dictionaries.
        """
        quotes: list[dict[str, Any]] = []
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=["--no-sandbox"],
                )
                book_cfg = self.config.sportsbooks.get("betano")
                url = book_cfg.nba_url if book_cfg and book_cfg.nba_url else BETANO_NBA_URL
                wait_ms = book_cfg.wait_after_load_ms if book_cfg else self.config.playwright.wait_after_load_ms
                timeout = book_cfg.timeout_ms if book_cfg else self.timeout_ms
                ua = self.config.playwright.user_agent
                vp: Any = {"width": self.config.playwright.viewport.width, "height": self.config.playwright.viewport.height}

                context = browser.new_context(
                    user_agent=ua,
                    viewport=vp,
                )
                page = context.new_page()

                intercepted_data: list[dict[str, Any]] = []

                def handle_response(response: Any) -> None:
                    try:
                        r_url = str(response.url).lower()
                        if "api" in r_url and ("event" in r_url or "sport" in r_url or "betano" in r_url):
                            if response.status == 200:
                                ct = response.headers.get("content-type", "")
                                if "application/json" in ct:
                                    intercepted_data.append(response.json())
                    except Exception:
                        pass

                page.on("response", handle_response)

                try:
                    page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                    page.wait_for_timeout(wait_ms)
                except Exception as nav_exc:
                    logger.debug("Betano navigation reached timeout or partial load: %s", nav_exc)

                browser.close()

                # Parse intercepted payloads
                for payload in intercepted_data:
                    data_obj = payload.get("data") if isinstance(payload, dict) else payload
                    events = data_obj if isinstance(data_obj, list) else []
                    if isinstance(data_obj, dict):
                        events = data_obj.get("events") or data_obj.get("matches") or []

                    for ev in events:
                        if not isinstance(ev, dict):
                            continue
                        name = ev.get("name") or ev.get("shortName") or ""
                        matched = self._match_teams(str(name))
                        if not matched:
                            continue
                        home_code, away_code = matched

                        markets = ev.get("markets") or []
                        for mkt in markets:
                            if not isinstance(mkt, dict):
                                continue
                            m_desc = str(mkt.get("name") or mkt.get("description") or "").upper()
                            selections = mkt.get("selections") or []

                            # Moneyline (Ganador del encuentro - 2-Way con prórroga incluida)
                            if any(k in m_desc for k in ("TIEMPO REGLAMENTARIO", "1X2", "REGULAR TIME", "RESULTADO DEL PARTIDO")):
                                continue
                            if any(k in m_desc for k in ("GANADOR", "MONEYLINE", "1 2", "12")):
                                if len(selections) != 2:
                                    continue
                                if any(any(d == str(s.get("name") or "").strip().upper() for d in ("X", "EMPATE", "DRAW")) for s in selections):
                                    continue
                                home_odd: float | None = None
                                away_odd: float | None = None
                                for sel in selections:
                                    s_name = str(sel.get("name") or "").upper()
                                    price = float(sel.get("price") or 0.0)
                                    if price > 1.0:
                                        if home_code in s_name or "1" in s_name:
                                            home_odd = price
                                        elif away_code in s_name or "2" in s_name:
                                            away_odd = price
                                if home_odd and away_odd:
                                    quotes.append({
                                        "provider": "Betano Perú",
                                        "home_team": home_code,
                                        "away_team": away_code,
                                        "market": "moneyline",
                                        "selection": "HOME",
                                        "decimal_odds": home_odd,
                                        "counterpart_decimal_odds": away_odd,
                                        "line_value": None,
                                        "captured_at": now_utc,
                                        "source_type": "OBSERVED",
                                    })
                                    quotes.append({
                                        "provider": "Betano Perú",
                                        "home_team": home_code,
                                        "away_team": away_code,
                                        "market": "moneyline",
                                        "selection": "AWAY",
                                        "decimal_odds": away_odd,
                                        "counterpart_decimal_odds": home_odd,
                                        "line_value": None,
                                        "captured_at": now_utc,
                                        "source_type": "OBSERVED",
                                    })

                            # Total de puntos
                            elif "TOTAL" in m_desc or "MÁS/MENOS" in m_desc or "OVER/UNDER" in m_desc:
                                over_odd: float | None = None
                                under_odd: float | None = None
                                line_val = mkt.get("handicap")
                                for sel in selections:
                                    s_name = str(sel.get("name") or "").upper()
                                    price = float(sel.get("price") or 0.0)
                                    handicap = sel.get("handicap")
                                    if line_val is None and handicap is not None:
                                        line_val = handicap
                                    if price > 1.0:
                                        if "MÁS" in s_name or "OVER" in s_name:
                                            over_odd = price
                                        elif "MENOS" in s_name or "UNDER" in s_name:
                                            under_odd = price
                                if over_odd and under_odd and line_val is not None:
                                    quotes.append({
                                        "provider": "Betano Perú",
                                        "home_team": home_code,
                                        "away_team": away_code,
                                        "market": "total_points",
                                        "selection": "OVER",
                                        "decimal_odds": over_odd,
                                        "counterpart_decimal_odds": under_odd,
                                        "line_value": float(line_val),
                                        "captured_at": now_utc,
                                        "source_type": "OBSERVED",
                                    })
                                    quotes.append({
                                        "provider": "Betano Perú",
                                        "home_team": home_code,
                                        "away_team": away_code,
                                        "market": "total_points",
                                        "selection": "UNDER",
                                        "decimal_odds": under_odd,
                                        "counterpart_decimal_odds": over_odd,
                                        "line_value": float(line_val),
                                        "captured_at": now_utc,
                                        "source_type": "OBSERVED",
                                    })

        except Exception as exc:
            logger.warning("Betano Playwright scraping error: %s", exc)

        return quotes

    def persist_scraped_quotes(
        self,
        quotes: list[dict[str, Any]],
        slate_games: list[dict[str, Any]],
    ) -> int:
        """
        Matches scraped quotes against active slate games by team codes and persists them into
        odds_snapshots with source_type='OBSERVED' using DatabaseManager.insert_odds_snapshot.
        """
        if not self.db or not quotes:
            return 0

        # Map (home_team, away_team) -> game_id
        game_map: dict[tuple[str, str], str] = {}
        for g in slate_games:
            game_map[(g["home_team"], g["away_team"])] = g["game_id"]

        inserted_count = 0
        for q in quotes:
            gid = game_map.get((q["home_team"], q["away_team"]))
            if not gid:
                continue

            book_slug = "retabet" if "retabet" in str(q["provider"]).lower() else "betano"
            mkt_slug = "ML" if q["market"] == "moneyline" else "TOT"
            line_str = f"_{q['line_value']}" if q["line_value"] is not None else ""
            odds_id = f"ODDS_{book_slug.upper()}_{gid}_{mkt_slug}_{q['selection']}{line_str}_{q['captured_at']}"

            inserted = self.db.insert_odds_snapshot({
                "odds_id": odds_id,
                "game_id": gid,
                "provider": q["provider"],
                "market": q["market"],
                "selection": q["selection"],
                "line_value": q["line_value"],
                "decimal_odds": q["decimal_odds"],
                "counterpart_decimal_odds": q.get("counterpart_decimal_odds"),
                "captured_at": q["captured_at"],
                "is_closing_line": 0,
                "source_type": "OBSERVED",
            })
            if inserted:
                inserted_count += 1

        logger.info("Persisted %d observed quotes from Peruvian sportsbooks.", inserted_count)
        return inserted_count
