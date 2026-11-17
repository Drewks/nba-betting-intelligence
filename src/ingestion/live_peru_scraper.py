"""
Real-Time Peruvian Sportsbook Scraping & Latency Arbitrage Engine (`src/ingestion/live_peru_scraper.py`).
Actively monitors live decimal odds across accessible Peruvian & sharp sportsbook feeds:
  - Te Apuesto Perú (api-latam.core-ix.com public NBA market feed — Moneyline, Totals, Spread, PTS/3PM Player Props)
  - Betano Perú (www.betano.pe public NBA JSON feed — Moneyline, Totals, Spread)
  - Pinnacle / Sharp Market Maker (guest.api.arcadia.pinnacle.com — Benchmark Moneyline, Totals, Spread)
  - Optional observed DB snapshots imported via Playwright/Ingestion (RETAbet, Betano, Betsson, Inkabet)

Policy: `PUBLIC_READONLY_JSON_API_NO_ANTIBOT_BYPASS` (honors `config/model_config.yaml` -> `sources`).

Detects:
  1. Stale Lines (retail odds lagging behind Pinnacle sharp line moves by >= 4.0% CLV).
  2. Risk-free Cross-Bookmaker Arbitrage (Surebets) in Soles (S/. PEN).
  3. Soft-book +EV mispricings persisted strictly with source_type='OBSERVED'.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import json
import logging
from pathlib import Path
import re
from typing import Any

import httpx

from src.config import SourcesConfig, load_config, load_scraper_config
from src.ingestion.peru_book_parsers import (
    TEAPUESTO_NBA_TOURNAMENT_ID,
    LiveGameOddsQuote,
    _resolve_team_code,
    parse_betano_nba_events,
    parse_pinnacle_nba_events,
    parse_teapuesto_nba_events,
    select_slate_row_by_start_time,
)
from src.ingestion.stale_line_hunter import StaleLineHunter
from src.reporting.telegram_bot import TelegramAlertBot
from src.storage.db import DatabaseManager
from src.utils.team_dictionary import format_matchup

logger = logging.getLogger("PeruOddsScraper")

PERU_OFFSET = timezone(timedelta(hours=-5))

TEAPUESTO_TOURNAMENT_EVENTS_URL = "https://api-latam.core-ix.com/api/v1/tournament-events"
BETANO_NBA_API_URL = "https://www.betano.pe/api/sport/basquetbol/norteamerica/nba/441g/"
PINNACLE_NBA_MATCHUPS_URL = "https://guest.api.arcadia.pinnacle.com/0.1/leagues/487/matchups"
PINNACLE_NBA_MARKETS_URL = "https://guest.api.arcadia.pinnacle.com/0.1/leagues/487/markets/straight"


class LivePeruOddsScraper:
    """
    Automated real-time odds monitor for accessible Peruvian & sharp sportsbook feeds.
    Performs live extraction, stale line tracking, and instant arbitrage alerts.
    """

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        db: DatabaseManager | None = None,
        min_clv_pct: float = 4.0,
        min_arb_margin_pct: float = 0.8,
        bankroll_pen: float = 100.0,
        request_timeout: float = 8.0,
        enable_live_network: bool | None = None,
    ) -> None:
        self.db = db
        self.min_clv_pct = min_clv_pct
        self.min_arb_margin_pct = min_arb_margin_pct
        self.bankroll_pen = bankroll_pen
        self.request_timeout = request_timeout
        self._sources_cfg: SourcesConfig | None = None
        try:
            self._sources_cfg = load_config().sources
        except Exception:
            self._sources_cfg = None
        default_net = self._sources_cfg.peru_scrapers_enabled if self._sources_cfg is not None else True
        self.enable_live_network = (
            bool(default_net) if enable_live_network is None else bool(enable_live_network)
        )
        self.hunter = StaleLineHunter(min_clv_pct=min_clv_pct, min_arb_margin_pct=min_arb_margin_pct)
        self.bot = TelegramAlertBot()
        self._scraper_cfg = load_scraper_config()
        self._teapuesto_cache: tuple[datetime, list[dict[str, Any]]] | None = None
        self._betano_cache: tuple[datetime, list[dict[str, Any]]] | None = None
        self._pinnacle_cache: tuple[datetime, list[dict[str, Any]]] | None = None
        self._retabet_probe_at: datetime | None = None
        self._betsson_probe_at: datetime | None = None
        self._source_status: dict[str, dict[str, Any]] = {}

    def _resolve_api_url(self, key: str, default: str) -> str:
        """Resolves a sportsbook API URL from scraper_config.yaml with a safe default."""
        sb = self._scraper_cfg.sportsbooks.get(key)
        if sb and sb.api_url:
            return sb.api_url
        return default

    def _is_source_enabled(self, key: str) -> bool:
        """Checks whether a configured source is enabled in both model_config.yaml and scraper_config.yaml."""
        if self._sources_cfg is not None:
            if not self._sources_cfg.peru_scrapers_enabled:
                return False
            if key in ("te_apuesto", "pinnacle", "betano") and key not in self._sources_cfg.allowed_live_api_books:
                return False
        sb = self._scraper_cfg.sportsbooks.get(key)
        return True if sb is None else bool(sb.enabled)

    def _set_source_status(self, key: str, status: str, detail: str = "", events_count: int = 0) -> None:
        self._source_status[key] = {
            "status": status,
            "detail": detail,
            "events_count": events_count,
            "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def get_source_diagnostics(self) -> dict[str, dict[str, Any]]:
        """Returns latest real status for every sportsbook feed checked by this instance."""
        return dict(self._source_status)

    def _fetch_teapuesto_slate(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Fetches pre-game NBA slate odds from Te Apuesto Perú public API with 60s instance cache."""
        if not self.enable_live_network:
            return []
        if not self._is_source_enabled("te_apuesto"):
            self._set_source_status("teapuesto_pe", "DISABLED_IN_CONFIG")
            return []
        now = datetime.now(timezone.utc)
        if not force_refresh and self._teapuesto_cache is not None:
            cached_at, rows = self._teapuesto_cache
            if (now - cached_at).total_seconds() < 60.0:
                return rows
        payload = {
            "platform": "desktop",
            "language_id": 3,
            "code": "es-ES",
            "language_code": "spa",
            "version": "v3",
            "site_code": "ta",
            "time_range": "all",
            "auth": None,
            "tournament_ids": [TEAPUESTO_NBA_TOURNAMENT_ID],
            "event_card_type": 1,
        }
        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}
        url = self._resolve_api_url("te_apuesto", TEAPUESTO_TOURNAMENT_EVENTS_URL)
        try:
            with httpx.Client(timeout=self.request_timeout, headers=headers) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    rows = parse_teapuesto_nba_events(
                        resp.json(),
                        captured_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    )
                    self._teapuesto_cache = (now, rows)
                    self._set_source_status("teapuesto_pe", "ACTIVE_JSON_API", "HTTP 200", len(rows))
                    return rows
                self._set_source_status("teapuesto_pe", f"HTTP_{resp.status_code}", url)
                logger.warning("Te Apuesto API returned status %s", resp.status_code)
        except Exception as exc:
            self._set_source_status("teapuesto_pe", "NETWORK_ERROR", str(exc))
            logger.debug("Te Apuesto live fetch failed: %s", exc)
        self._teapuesto_cache = (now, [])
        return []

    def _fetch_betano_slate(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Fetches pre-game NBA slate odds from Betano Perú public JSON API with 60s instance cache."""
        if not self.enable_live_network:
            return []
        if not self._is_source_enabled("betano"):
            self._set_source_status("betano_pe", "DISABLED_IN_CONFIG")
            return []
        now = datetime.now(timezone.utc)
        if not force_refresh and self._betano_cache is not None:
            cached_at, rows = self._betano_cache
            if (now - cached_at).total_seconds() < 60.0:
                return rows
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json",
            "Referer": "https://www.betano.pe/",
        }
        url = self._resolve_api_url("betano", BETANO_NBA_API_URL)
        try:
            with httpx.Client(timeout=self.request_timeout, headers=headers, follow_redirects=True) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        rows = parse_betano_nba_events(
                            data,
                            captured_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        )
                        self._betano_cache = (now, rows)
                        self._set_source_status("betano_pe", "ACTIVE_JSON_API", "HTTP 200", len(rows))
                        return rows
                status_tag = "BOT_PROTECTED_HTTP_403" if resp.status_code == 403 else f"HTTP_{resp.status_code}"
                self._set_source_status("betano_pe", status_tag, url)
                logger.warning("Betano Perú API returned status %s", resp.status_code)
        except Exception as exc:
            self._set_source_status("betano_pe", "NETWORK_ERROR", str(exc))
            logger.debug("Betano Perú live fetch failed: %s", exc)
        self._betano_cache = (now, [])
        return []

    def _fetch_pinnacle_slate(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Fetches pre-game NBA sharp odds from Pinnacle Arcadia guest API with 60s cache."""
        if not self.enable_live_network:
            return []
        if not self._is_source_enabled("pinnacle"):
            self._set_source_status("pinnacle", "DISABLED_IN_CONFIG")
            return []
        now = datetime.now(timezone.utc)
        if not force_refresh and self._pinnacle_cache is not None:
            cached_at, rows = self._pinnacle_cache
            if (now - cached_at).total_seconds() < 60.0:
                return rows
        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}
        base_url = self._resolve_api_url("pinnacle", "https://guest.api.arcadia.pinnacle.com/0.1/leagues/487").rstrip("/")
        matchups_url = f"{base_url}/matchups"
        markets_url = f"{base_url}/markets/straight"
        try:
            with httpx.Client(timeout=self.request_timeout, headers=headers) as client:
                rm = client.get(matchups_url)
                rk = client.get(markets_url)
                if rm.status_code == 200 and rk.status_code == 200:
                    rows = parse_pinnacle_nba_events(
                        rm.json(),
                        rk.json(),
                        captured_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    )
                    self._pinnacle_cache = (now, rows)
                    self._set_source_status("pinnacle", "ACTIVE_JSON_API", "HTTP 200", len(rows))
                    return rows
                self._set_source_status("pinnacle", f"HTTP_{rm.status_code}_{rk.status_code}", matchups_url)
                logger.warning("Pinnacle Arcadia API returned %s / %s", rm.status_code, rk.status_code)
        except Exception as exc:
            self._set_source_status("pinnacle", "NETWORK_ERROR", str(exc))
            logger.debug("Pinnacle Arcadia live fetch failed: %s", exc)
        self._pinnacle_cache = (now, [])
        return []

    def _match_slate_row(
        self,
        rows: list[dict[str, Any]],
        home_team: str,
        away_team: str,
        game_start_time: str | None = None,
    ) -> LiveGameOddsQuote | None:
        h_code = _resolve_team_code(home_team) or home_team.upper()
        a_code = _resolve_team_code(away_team) or away_team.upper()
        target_pair = frozenset({h_code, a_code})
        candidates = [row for row in rows if row.get("team_pair") == target_pair]
        # The same two teams often meet on consecutive days (NBA mini-series). Matching on the team
        # pair alone attached one game's quotes to both games, so the event start time must agree.
        row = select_slate_row_by_start_time(candidates, game_start_time)
        if row is not None:
            team_odds = row.get("team_odds") or {}
            h_odds = float(team_odds.get(h_code) or 0.0)
            a_odds = float(team_odds.get(a_code) or 0.0)
            spread_by_team = row.get("spread_line_by_team") or {}
            s_home_line = row.get("spread_home_line")
            s_home_odds = row.get("spread_home_odds")
            s_away_odds = row.get("spread_away_odds")
            if spread_by_team:
                s_home_line, s_home_odds = spread_by_team.get(h_code, (None, None))
                _, s_away_odds = spread_by_team.get(a_code, (None, None))
            elif row.get("home_team") != h_code and s_home_line is not None:
                s_home_line = -float(s_home_line)
                s_home_odds, s_away_odds = s_away_odds, s_home_odds
            return LiveGameOddsQuote(
                book_id=str(row["book_id"]),
                book_name=str(row["book_name"]),
                home_odds=h_odds,
                away_odds=a_odds,
                spread_home_line=s_home_line,
                spread_home_odds=s_home_odds,
                spread_away_odds=s_away_odds,
                total_points_line=row.get("total_points_line"),
                total_over_odds=row.get("total_over_odds"),
                total_under_odds=row.get("total_under_odds"),
                player_props=row.get("player_props"),
                captured_at=str(row.get("captured_at") or ""),
                source=str(row.get("source") or "LIVE_EXTRACTOR"),
                is_observed=True,
                source_type="OBSERVED",
            )
        return None

    def fetch_live_teapuesto_odds(
        self, home_team: str, away_team: str, game_start_time: str | None = None
    ) -> LiveGameOddsQuote | None:
        """Extracts live pre-game NBA odds from Te Apuesto Perú (public API)."""
        return self._match_slate_row(self._fetch_teapuesto_slate(), home_team, away_team, game_start_time)

    def fetch_live_betano_odds(
        self, home_team: str, away_team: str, game_start_time: str | None = None
    ) -> LiveGameOddsQuote | None:
        """Extracts live pre-game NBA odds from Betano Perú (public JSON API)."""
        return self._match_slate_row(self._fetch_betano_slate(), home_team, away_team, game_start_time)

    def fetch_live_pinnacle_odds(
        self, home_team: str, away_team: str, game_start_time: str | None = None
    ) -> LiveGameOddsQuote | None:
        """Extracts live pre-game NBA sharp odds from Pinnacle Arcadia guest API."""
        return self._match_slate_row(self._fetch_pinnacle_slate(), home_team, away_team, game_start_time)

    def fetch_live_retabet_odds(self, home_team: str, away_team: str) -> LiveGameOddsQuote | None:
        """
        Queries RETAbet Perú only when explicitly accessible without WAF evasion.
        Caches unreachable/WAF blocks for 60s so per-game scans avoid redundant retries.
        """
        if not self.enable_live_network:
            return None
        now = datetime.now(timezone.utc)
        if self._retabet_probe_at is not None and (now - self._retabet_probe_at).total_seconds() < 60.0:
            return None
        self._retabet_probe_at = now
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        url = "https://api.retabet.pe/sports/v2/events/nba"
        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}

        try:
            with httpx.Client(timeout=self.request_timeout, headers=headers) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    events = data.get("events", [])
                    self._set_source_status("retabet_pe", "ACTIVE_JSON_API", "HTTP 200", len(events))
                    for ev in events:
                        ev_name = ev.get("name", "").upper()
                        if home_team in ev_name or away_team in ev_name:
                            h_raw = ev.get("home_odds")
                            a_raw = ev.get("away_odds")
                            if h_raw is not None and a_raw is not None and float(h_raw) > 1.0 and float(a_raw) > 1.0:
                                return LiveGameOddsQuote(
                                    book_id="retabet_pe",
                                    book_name="RETAbet Perú",
                                    home_odds=float(h_raw),
                                    away_odds=float(a_raw),
                                    captured_at=now_str,
                                    source="RETAbet API Direct",
                                    is_observed=True,
                                    source_type="OBSERVED",
                                )
                else:
                    self._set_source_status("retabet_pe", f"HTTP_{resp.status_code}", url)
        except Exception as exc:
            self._set_source_status("retabet_pe", "UNREACHABLE_F5_PROTECTED", str(exc))
            logger.debug(f"RETAbet live fetch failed: {exc}")
        return None

    def fetch_live_betsson_odds(self, home_team: str, away_team: str) -> LiveGameOddsQuote | None:
        """
        Queries Betsson/Altenar feed when accessible without Kasada/WAF challenge.
        Caches blocked responses for 60s so slate scans stay fast and honest.
        """
        if not self.enable_live_network:
            return None
        now = datetime.now(timezone.utc)
        if self._betsson_probe_at is not None and (now - self._betsson_probe_at).total_seconds() < 60.0:
            return None
        self._betsson_probe_at = now
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        url = "https://sb2frontend-altenar2.biahosted.com/api/Sportsbook/GetEvents"
        params = {"sportId": "66", "timezoneOffset": "-300"}  # Basketball / PET
        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}

        try:
            with httpx.Client(timeout=self.request_timeout, headers=headers) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    events = data.get("events", [])
                    self._set_source_status("betsson_pe", "ACTIVE_JSON_API", "HTTP 200", len(events))
                    for ev in events:
                        ev_name = ev.get("name", "").upper()
                        if home_team in ev_name or away_team in ev_name:
                            prices = ev.get("prices")
                            if prices and len(prices) >= 2 and float(prices[0]) > 1.0 and float(prices[1]) > 1.0:
                                return LiveGameOddsQuote(
                                    book_id="betsson_pe",
                                    book_name="Betsson Perú",
                                    home_odds=float(prices[0]),
                                    away_odds=float(prices[1]),
                                    captured_at=now_str,
                                    source="Betsson API Direct",
                                    is_observed=True,
                                    source_type="OBSERVED",
                                )
                else:
                    self._set_source_status("betsson_pe", f"BOT_PROTECTED_HTTP_{resp.status_code}", url)
        except Exception as exc:
            self._set_source_status("betsson_pe", "NETWORK_ERROR", str(exc))
            logger.debug(f"Betsson live fetch failed: {exc}")
        return None

    def collect_slate_odds(
        self,
        game_id: str,
        home_team: str,
        away_team: str,
        game_start_time: str,
        sharp_home_odds: float | None = None,
        sharp_away_odds: float | None = None,
        as_of_utc: datetime | None = None,
        sharp_book_name: str | None = None,
        sharp_captured_at: str | None = None,
    ) -> dict[str, Any]:
        """
        Consolidates odds for a matchup. Only quotes genuinely fetched from a bookmaker are persisted
        or used for stale-line/surebet detection; benchmark-derived retail estimates are display-only.
        There is no fallback price: without an observed sharp benchmark nothing is compared.
        """
        now = as_of_utc or datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        peru_time_str = (now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M PET")

        # 1. Reference comparison (DISPLAY ONLY). Retail quotes derived from the benchmark are estimates:
        #    they are never persisted and never used for stale-line or surebet detection, because a quote
        #    computed from the benchmark can, by construction, never be "stale" against it.
        from src.ingestion.peru_sportsbooks import calculate_peru_odds_comparison
        quotes_by_book: dict[str, LiveGameOddsQuote] = {}
        derived_quotes: dict[str, LiveGameOddsQuote] = {}
        h_bench = float(sharp_home_odds) if sharp_home_odds and sharp_home_odds > 1.0 else None
        a_bench = float(sharp_away_odds) if sharp_away_odds and sharp_away_odds > 1.0 else None
        sharp_quote: LiveGameOddsQuote | None = None

        if h_bench is not None and a_bench is not None:
            comp = calculate_peru_odds_comparison(
                p_home_fair=0.50,
                p_away_fair=0.50,
                benchmark_home_odds=h_bench,
                benchmark_away_odds=a_bench,
            )
            for b_info in comp.get("books", []):
                bid = b_info["id"]
                if bid == "pinnacle_pe":
                    continue
                derived_quotes[bid] = LiveGameOddsQuote(
                    book_id=bid,
                    book_name=b_info["name"],
                    home_odds=float(b_info["home_odds"]),
                    away_odds=float(b_info["away_odds"]),
                    captured_at=now_str,
                    source="ESTIMATE (derived from benchmark, not observed)",
                    is_observed=False,
                    source_type="DERIVED",
                )
            # The benchmark is a copy of an already-stored observed sharp quote: it is used for comparison
            # but never re-persisted (re-persisting would duplicate and relabel provenance).
            sharp_quote = LiveGameOddsQuote(
                book_id="sharp_benchmark",
                book_name=sharp_book_name or "Sharp benchmark",
                home_odds=h_bench,
                away_odds=a_bench,
                captured_at=sharp_captured_at or now_str,
                source="Stored observed sharp quote",
                is_observed=False,
                source_type="OBSERVED",
            )

        # 2. Genuine live quotes fetched from accessible retail & sharp feeds.
        live_ta = self.fetch_live_teapuesto_odds(home_team, away_team, game_start_time)
        if live_ta:
            quotes_by_book["teapuesto_pe"] = live_ta

        live_betano = self.fetch_live_betano_odds(home_team, away_team, game_start_time)
        if live_betano:
            quotes_by_book["betano_pe"] = live_betano

        live_pin = self.fetch_live_pinnacle_odds(home_team, away_team, game_start_time)
        if live_pin and sharp_quote is None and live_pin.home_odds > 1.0 and live_pin.away_odds > 1.0:
            sharp_quote = LiveGameOddsQuote(
                book_id="sharp_benchmark",
                book_name=live_pin.book_name,
                home_odds=live_pin.home_odds,
                away_odds=live_pin.away_odds,
                spread_home_line=live_pin.spread_home_line,
                spread_home_odds=live_pin.spread_home_odds,
                spread_away_odds=live_pin.spread_away_odds,
                total_points_line=live_pin.total_points_line,
                total_over_odds=live_pin.total_over_odds,
                total_under_odds=live_pin.total_under_odds,
                captured_at=live_pin.captured_at or now_str,
                source=live_pin.source,
                is_observed=False,
                source_type="OBSERVED",
            )

        live_ret = self.fetch_live_retabet_odds(home_team, away_team)
        if live_ret:
            quotes_by_book["retabet_pe"] = live_ret

        live_bet = self.fetch_live_betsson_odds(home_team, away_team)
        if live_bet:
            quotes_by_book["betsson_pe"] = live_bet

        # 2b. Include quotes genuinely observed and stored in DB (e.g. via Playwright scraper)
        if self.db is not None:
            observed_rows = self.db.fetch_all(
                """
                SELECT provider, selection, decimal_odds, captured_at
                FROM v_observed_odds_snapshots
                WHERE game_id = ? AND market = 'moneyline'
                  AND (
                    provider IN ('RETAbet Perú', 'Betano Perú', 'Betsson Perú', 'Inkabet', 'Te Apuesto', 'Te Apuesto Perú', 'Apuesta Total')
                    OR provider LIKE 'Te Apuesto%'
                  )
                ORDER BY captured_at DESC
                """,
                (game_id,),
            )
            by_prov: dict[str, dict[str, Any]] = {}
            for r in observed_rows:
                prov = str(r["provider"])
                sel = str(r["selection"]).upper()
                if prov not in by_prov:
                    by_prov[prov] = {}
                if sel not in by_prov[prov]:
                    by_prov[prov][sel] = r

            for prov, sels in by_prov.items():
                slug = (
                    "retabet_pe" if "RETAbet" in prov
                    else ("betano_pe" if "Betano" in prov
                    else ("betsson_pe" if "Betsson" in prov
                    else ("teapuesto_pe" if "Te Apuesto" in prov else prov.lower().replace(" ", "_"))))
                )
                if slug not in quotes_by_book and "HOME" in sels and "AWAY" in sels:
                    quotes_by_book[slug] = LiveGameOddsQuote(
                        book_id=slug,
                        book_name=prov,
                        home_odds=float(sels["HOME"]["decimal_odds"]),
                        away_odds=float(sels["AWAY"]["decimal_odds"]),
                        captured_at=str(sels["HOME"]["captured_at"]),
                        source=f"{prov} (Observed via Playwright / Ingestion)",
                        is_observed=True,
                        source_type="OBSERVED",
                    )

        # 3. Stale lines: observed retail quotes (having valid moneyline prices) vs observed sharp benchmark only.
        stale_opportunities: list[dict[str, Any]] = []
        ml_retail_quotes = [q for q in quotes_by_book.values() if q.home_odds > 1.0 and q.away_odds > 1.0]
        if sharp_quote and ml_retail_quotes:
            retail_home_list = [
                {"bookmaker": q.book_name, "decimal_odds": q.home_odds, "selection": "HOME"}
                for q in ml_retail_quotes
            ]
            retail_away_list = [
                {"bookmaker": q.book_name, "decimal_odds": q.away_odds, "selection": "AWAY"}
                for q in ml_retail_quotes
            ]
            for sel, sharp_odds, retail in (
                ("HOME", sharp_quote.home_odds, retail_home_list),
                ("AWAY", sharp_quote.away_odds, retail_away_list),
            ):
                stale_opportunities.extend(
                    self.hunter.identify_stale_lines(
                        game_id=game_id,
                        matchday_date=now.strftime("%Y-%m-%d"),
                        sharp_line={
                            "bookmaker": sharp_quote.book_name,
                            "market": "moneyline",
                            "selection": sel,
                            "decimal_odds": sharp_odds,
                        },
                        retail_lines=retail,
                        bankroll_pen=self.bankroll_pen,
                    )
                )

        # 4. Surebets: only across observed quotes with valid moneyline prices.
        observed_pool = ml_retail_quotes + ([sharp_quote] if sharp_quote and sharp_quote.home_odds > 1.0 and sharp_quote.away_odds > 1.0 else [])
        best_h: LiveGameOddsQuote | None = None
        best_a: LiveGameOddsQuote | None = None
        surebet_info: dict[str, Any] | None = None
        inv_sum = 1.0
        if len(observed_pool) >= 2:
            best_h = max(observed_pool, key=lambda q: q.home_odds)
            best_a = max(observed_pool, key=lambda q: q.away_odds)
            inv_sum = (1.0 / best_h.home_odds) + (1.0 / best_a.away_odds)
            if inv_sum < 0.999 and best_h.book_name != best_a.book_name:
                surebet_info = self.hunter.compute_surebet_arbitrage(
                    game_id=game_id,
                    matchday_date=now.strftime("%Y-%m-%d"),
                    book_a=best_h.book_name,
                    selection_a=f"{home_team} (Local)",
                    odds_a=best_h.home_odds,
                    book_b=best_a.book_name,
                    selection_b=f"{away_team} (Visita)",
                    odds_b=best_a.away_odds,
                    total_investment_pen=min(self.bankroll_pen, 1.00),
                )

        # 5. Persist only genuinely fetched quotes (retail + live Pinnacle sharp feed if newly fetched)
        if self.db:
            to_persist = dict(quotes_by_book)
            if live_pin and live_pin.is_observed:
                to_persist["pinnacle_live"] = live_pin
            self._persist_quotes_to_db(game_id, to_persist, now_str)

        all_quotes = {**{k: asdict(v) for k, v in derived_quotes.items()}, **{k: asdict(v) for k, v in quotes_by_book.items()}}
        if sharp_quote:
            all_quotes["sharp_benchmark"] = asdict(sharp_quote)

        return {
            "game_id": game_id,
            "matchup": format_matchup(away_team, home_team),
            "game_start_time": game_start_time,
            "captured_at_utc": now_str,
            "hora_captura_peru": peru_time_str,
            "best_home": {"book": best_h.book_name, "odds": best_h.home_odds} if best_h else None,
            "best_away": {"book": best_a.book_name, "odds": best_a.away_odds} if best_a else None,
            "synthetic_margin_pct": round((inv_sum - 1.0) * 100.0, 2) if (best_h and best_a) else 0.0,
            "quotes": all_quotes,
            "observed_quotes_count": len(quotes_by_book),
            "player_props_count": sum(len(q.player_props or []) for q in quotes_by_book.values()),
            "stale_lines": stale_opportunities,
            "surebet": surebet_info,
        }

    def _persist_quotes_to_db(
        self,
        game_id: str,
        quotes: dict[str, LiveGameOddsQuote],
        now_str: str,
    ) -> None:
        """Persists live scraped odds into the SQLite database."""
        if not self.db:
            return
        g_exists = self.db.fetch_one("SELECT 1 FROM games WHERE game_id = ?", (game_id,))
        if not g_exists:
            return

        for bid, q in quotes.items():
            if not getattr(q, "is_observed", False) or getattr(q, "source_type", "") != "OBSERVED":
                continue
            provider = f"{q.book_name} [LIVE_API]"
            cap_ts = q.captured_at or now_str
            if q.home_odds > 1.0 and q.away_odds > 1.0:
                for selection, price, counter in (("HOME", q.home_odds, q.away_odds), ("AWAY", q.away_odds, q.home_odds)):
                    self.db.insert_odds_snapshot(
                        {
                            "odds_id": f"ODDS_LIVEAPI_{game_id}_{bid}_{selection}_{cap_ts}",
                            "game_id": game_id,
                            "provider": provider,
                            "market": "moneyline",
                            "selection": selection,
                            "line_value": None,
                            "decimal_odds": float(price),
                            "counterpart_decimal_odds": float(counter),
                            "captured_at": cap_ts,
                            "is_closing_line": 0,
                            "source_type": "OBSERVED",
                        }
                    )
            if (
                q.total_points_line is not None
                and q.total_over_odds is not None
                and q.total_under_odds is not None
                and q.total_over_odds > 1.0
                and q.total_under_odds > 1.0
            ):
                for selection, price, counter in (
                    ("OVER", q.total_over_odds, q.total_under_odds),
                    ("UNDER", q.total_under_odds, q.total_over_odds),
                ):
                    self.db.insert_odds_snapshot(
                        {
                            "odds_id": f"ODDS_LIVEAPI_{game_id}_{bid}_TOT_{selection}_{q.total_points_line}_{cap_ts}",
                            "game_id": game_id,
                            "provider": provider,
                            "market": "total_points",
                            "selection": selection,
                            "line_value": float(q.total_points_line),
                            "decimal_odds": float(price),
                            "counterpart_decimal_odds": float(counter),
                            "captured_at": cap_ts,
                            "is_closing_line": 0,
                            "source_type": "OBSERVED",
                        }
                    )
            if (
                q.spread_home_line is not None
                and q.spread_home_odds is not None
                and q.spread_away_odds is not None
                and q.spread_home_odds > 1.0
                and q.spread_away_odds > 1.0
            ):
                h_line = float(q.spread_home_line)
                a_line = -h_line if h_line != 0.0 else 0.0
                for selection, s_line, price, counter in (
                    ("HOME", h_line, q.spread_home_odds, q.spread_away_odds),
                    ("AWAY", a_line, q.spread_away_odds, q.spread_home_odds),
                ):
                    self.db.insert_odds_snapshot(
                        {
                            "odds_id": f"ODDS_LIVEAPI_{game_id}_{bid}_SPR_{selection}_{s_line}_{cap_ts}",
                            "game_id": game_id,
                            "provider": provider,
                            "market": "spread",
                            "selection": selection,
                            "line_value": s_line,
                            "decimal_odds": float(price),
                            "counterpart_decimal_odds": float(counter),
                            "captured_at": cap_ts,
                            "is_closing_line": 0,
                            "source_type": "OBSERVED",
                        }
                    )
            for pp in q.player_props or []:
                p_name = str(pp.get("player_name") or "").strip()
                raw_cat = str(pp.get("prop_category") or "PTS").strip().upper()
                cat_code = "PTS" if raw_cat in ("PTS", "POINTS", "PUNTOS") else raw_cat
                p_line = pp.get("line_value")
                p_over = pp.get("over_odds")
                p_under = pp.get("under_odds")
                if (
                    p_name
                    and cat_code
                    and p_line is not None
                    and float(p_line) > 0.0
                    and p_over is not None
                    and p_under is not None
                    and float(p_over) > 1.0
                    and float(p_under) > 1.0
                ):
                    p_slug = re.sub(r"[^a-zA-Z0-9]+", "_", p_name).strip("_")
                    prop_provider = f"{provider}|{p_name}|{cat_code}"
                    for selection, price, counter in (
                        ("OVER", float(p_over), float(p_under)),
                        ("UNDER", float(p_under), float(p_over)),
                    ):
                        self.db.insert_odds_snapshot(
                            {
                                "odds_id": f"ODDS_LIVEAPI_{game_id}_{bid}_PROP_{p_slug}_{cat_code}_{selection}_{float(p_line)}_{cap_ts}",
                                "game_id": game_id,
                                "provider": prop_provider,
                                "market": "player_prop",
                                "selection": selection,
                                "line_value": float(p_line),
                                "decimal_odds": price,
                                "counterpart_decimal_odds": counter,
                                "captured_at": cap_ts,
                                "is_closing_line": 0,
                                "source_type": "OBSERVED",
                            }
                        )
            # Spread, moneyline, total_points, and player_prop snapshots are all persisted.

    def _latest_observed_sharp_benchmark(self, game_id: str) -> dict[str, Any] | None:
        """Latest observed Pinnacle moneyline pair (HOME and AWAY from the same capture)."""
        if not self.db:
            return None
        row = self.db.fetch_one(
            """
            SELECT h.provider, h.captured_at, h.decimal_odds AS home_odds, a.decimal_odds AS away_odds
            FROM v_observed_odds_snapshots h
            JOIN v_observed_odds_snapshots a
              ON a.game_id = h.game_id AND a.provider = h.provider AND a.captured_at = h.captured_at
             AND a.market = 'moneyline' AND a.selection = 'AWAY' AND a.is_closing_line = 0
            WHERE h.game_id = ? AND h.market = 'moneyline' AND h.selection = 'HOME' AND h.is_closing_line = 0
              AND h.provider LIKE '%Pinnacle%'
            ORDER BY h.captured_at DESC
            LIMIT 1
            """,
            (game_id,),
        )
        return row

    def scan_and_alert_entire_slate(
        self,
        notify_telegram: bool = True,
        force_all: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Scans all scheduled slate games, performs live comparison across Peruvian sportsbooks,
        and dispatches instant Telegram alerts for Stale Lines (+CLV) and Surebets.
        """
        if not self.db:
            return []

        now_utc = datetime.now(timezone.utc)
        now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Fetch scheduled games
        filter_clause = "" if force_all else "AND game_start_time > ?"
        query = f"""
            SELECT game_id, home_team, away_team, game_start_time
            FROM games
            WHERE status = 'SCHEDULED' AND game_id NOT LIKE 'SYN%' {filter_clause}
            ORDER BY game_start_time ASC
            LIMIT 15
        """
        params = () if force_all else (now_str,)
        games = self.db.fetch_all(query, params)

        results: list[dict[str, Any]] = []
        alerts_sent = 0

        for g in games:
            gid = g["game_id"]
            # Look up existing benchmark
            bench = self._latest_observed_sharp_benchmark(gid)
            if bench is None:
                bench_h = None
                bench_a = None
                bench_prov = None
                bench_ts = None
            else:
                bench_h = bench["home_odds"]
                bench_a = bench["away_odds"]
                bench_prov = bench["provider"]
                bench_ts = bench["captured_at"]

            res = self.collect_slate_odds(
                game_id=gid,
                home_team=g["home_team"],
                away_team=g["away_team"],
                game_start_time=g["game_start_time"],
                sharp_home_odds=bench_h,
                sharp_away_odds=bench_a,
                as_of_utc=now_utc,
                sharp_book_name=bench_prov,
                sharp_captured_at=bench_ts,
            )
            if res.get("observed_quotes_count", 0) > 0 or "sharp_benchmark" in res.get("quotes", {}):
                results.append(res)

            # Telegram Dispatch for Stale Lines
            if notify_telegram and self.bot.is_live:
                for stale in res.get("stale_lines", []):
                    if float(stale.get("expected_clv_pct") or 0.0) >= self.min_clv_pct:
                        msg = self.bot.format_stale_line_alert(stale)
                        self.bot.send_raw_message(msg)
                        alerts_sent += 1

                # Telegram Dispatch for Surebets
                sb = res.get("surebet")
                if sb and sb.get("is_arbitrage"):
                    msg = self.bot.format_surebet_alert(sb)
                    self.bot.send_raw_message(msg)
                    alerts_sent += 1

        out_file = Path("data/evaluation/latest_peru_odds_scan.json")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info(f"Escaneo de cuotas peruanas completado para {len(results)} partidos. Alertas despachadas: {alerts_sent}.")
        return results
