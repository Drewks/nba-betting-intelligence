"""
Real-Time Peruvian Sportsbook Scraping & Latency Arbitrage Engine (`src/ingestion/live_peru_scraper.py`).
Actively monitors live decimal odds across accessible Peruvian & sharp sportsbook feeds:
  - Te Apuesto Perú (api-latam.core-ix.com public NBA market feed — Moneyline, Totals, Spread, Player Props)
  - Pinnacle / Sharp Market Maker (guest.api.arcadia.pinnacle.com — Benchmark Moneyline, Totals, Spread)
  - Optional observed DB snapshots imported via Playwright/Ingestion (RETAbet, Betano, Betsson, Inkabet)

Detects:
  1. Stale Lines (retail odds lagging behind Pinnacle sharp line moves by >= 4.0% CLV).
  2. Risk-free Cross-Bookmaker Arbitrage (Surebets) in Soles (S/. PEN).
  3. Soft-book +EV mispricings persisted strictly with source_type='OBSERVED'.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

import httpx

from src.ingestion.normalizer import american_to_decimal_odds
from src.ingestion.stale_line_hunter import StaleLineHunter
from src.reporting.telegram_bot import TelegramAlertBot
from src.storage.db import DatabaseManager
from src.utils.team_dictionary import format_matchup, get_team

logger = logging.getLogger("PeruOddsScraper")

PERU_OFFSET = timezone(timedelta(hours=-5))

TEAPUESTO_TOURNAMENT_EVENTS_URL = "https://api-latam.core-ix.com/api/v1/tournament-events"
TEAPUESTO_NBA_TOURNAMENT_ID = "46"
PINNACLE_NBA_MATCHUPS_URL = "https://guest.api.arcadia.pinnacle.com/0.1/leagues/487/matchups"
PINNACLE_NBA_MARKETS_URL = "https://guest.api.arcadia.pinnacle.com/0.1/leagues/487/markets/straight"

_PAREN_LINE_RE = re.compile(r"\(([-+]?\d+(?:\.\d+)?)\)")
_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


@dataclass
class LiveGameOddsQuote:
    book_id: str
    book_name: str
    home_odds: float
    away_odds: float
    spread_home_line: float | None = None
    spread_home_odds: float | None = None
    spread_away_odds: float | None = None
    total_points_line: float | None = None
    total_over_odds: float | None = None
    total_under_odds: float | None = None
    captured_at: str = ""
    source: str = "LIVE_EXTRACTOR"
    is_observed: bool = True
    source_type: str = "OBSERVED"


def _normalize_teapuesto_player_name(raw_name: str) -> str:
    """Converts 'Lastname, Firstname' into 'Firstname Lastname' cleanly."""
    cleaned = raw_name.strip()
    if "," in cleaned:
        last, first = cleaned.split(",", 1)
        joined = f"{first.strip()} {last.strip()}".strip()
        if joined:
            return joined
    return cleaned


def _resolve_team_code(raw_team: str) -> str | None:
    """Resolves team names across variations to canonical 3-letter NBA code."""
    team = get_team(raw_team)
    return team.code if team is not None else None


def parse_teapuesto_nba_events(
    payload: dict[str, Any],
    *,
    captured_at: str | None = None,
    include_live: bool = False,
) -> list[dict[str, Any]]:
    """
    Parses Te Apuesto public tournament-events JSON into standardized NBA pre-game odds rows.
    Extracts Moneyline (219), Totals (225), Spread/Handicap (223), and Player Points Props (921).
    """
    now_str = captured_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data_node = payload.get("data") if isinstance(payload, dict) else None
    tournaments = (data_node or {}).get("tournaments") if isinstance(data_node, dict) else None
    nba_node = (tournaments or {}).get(TEAPUESTO_NBA_TOURNAMENT_ID) if isinstance(tournaments, dict) else None
    events = (nba_node or {}).get("events") if isinstance(nba_node, dict) else None
    if not isinstance(events, list):
        return []

    parsed_rows: list[dict[str, Any]] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if not include_live and int(ev.get("status") or 0) != 0:
            continue

        ev_name = str(ev.get("name") or "")
        parts = [p.strip() for p in re.split(r"\s+-\s+|\s+vs\.?\s+|\s+@\s+", ev_name, maxsplit=1, flags=re.IGNORECASE)]
        if len(parts) != 2:
            continue
        c1 = _resolve_team_code(parts[0])
        c2 = _resolve_team_code(parts[1])
        if not c1 or not c2 or c1 == c2:
            continue

        home_code, away_code = (c2, c1) if " @ " in ev_name else (c1, c2)
        markets = ev.get("markets") or []

        ml_odds_by_team: dict[str, float] = {}
        total_line: float | None = None
        over_odds: float | None = None
        under_odds: float | None = None
        spread_line_by_team: dict[str, tuple[float, float]] = {}
        player_props: list[dict[str, Any]] = []

        for m in markets:
            if not isinstance(m, dict):
                continue
            pmid = str(m.get("provider_market_id") or "")
            buckets = m.get("market_odds") or []

            if pmid == "219" and buckets:
                for odd in (buckets[0].get("odds") or []):
                    tcode = _resolve_team_code(str(odd.get("name") or ""))
                    val = float(odd.get("value") or 0.0)
                    if tcode and val > 1.0:
                        ml_odds_by_team[tcode] = val

            elif pmid == "225" and buckets:
                fav_buckets = [b for b in buckets if isinstance(b, dict) and b.get("is_favorite")]
                ordered_buckets = fav_buckets + [b for b in buckets if b not in fav_buckets]
                for bucket in ordered_buckets:
                    b_over: float | None = None
                    b_under: float | None = None
                    b_line: float | None = None
                    for odd in (bucket.get("odds") or []):
                        oid = str(odd.get("provider_odd_id") or "")
                        oname = str(odd.get("name") or "").lower()
                        val = float(odd.get("value") or 0.0)
                        if val <= 1.0:
                            continue
                        sv = odd.get("special_value")
                        if sv is not None:
                            try:
                                b_line = float(sv)
                            except (TypeError, ValueError):
                                pass
                        if b_line is None:
                            m_num = _NUM_RE.search(oname)
                            if m_num:
                                b_line = float(m_num.group(0))
                        if oid == "12" or "más" in oname or "mas" in oname or "over" in oname:
                            b_over = val
                        elif oid == "13" or "menos" in oname or "under" in oname:
                            b_under = val
                    if b_line is not None and b_over and b_under:
                        total_line, over_odds, under_odds = b_line, b_over, b_under
                        break

            elif pmid == "223" and buckets:
                fav_buckets = [b for b in buckets if isinstance(b, dict) and b.get("is_favorite")]
                ordered_buckets = fav_buckets + [b for b in buckets if b not in fav_buckets]
                for bucket in ordered_buckets:
                    parsed_sides: dict[str, tuple[float, float]] = {}
                    for odd in (bucket.get("odds") or []):
                        oname = str(odd.get("name") or "")
                        val = float(odd.get("value") or 0.0)
                        if val <= 1.0:
                            continue
                        line_match = _PAREN_LINE_RE.search(oname)
                        if not line_match:
                            continue
                        hcp = float(line_match.group(1))
                        clean_team_name = _PAREN_LINE_RE.sub("", oname).strip()
                        tcode = _resolve_team_code(clean_team_name)
                        if tcode:
                            parsed_sides[tcode] = (hcp, val)
                    if c1 in parsed_sides and c2 in parsed_sides:
                        spread_line_by_team = parsed_sides
                        break

            elif pmid == "921" and buckets:
                for bucket in buckets:
                    bname = str(bucket.get("name") or "")
                    raw_player = re.sub(r"\s+total\s+puntos.*$", "", bname, flags=re.IGNORECASE).strip()
                    player_name = _normalize_teapuesto_player_name(raw_player)
                    if not player_name:
                        continue
                    p_over: float | None = None
                    p_under: float | None = None
                    p_line: float | None = None
                    for odd in (bucket.get("odds") or []):
                        oid = str(odd.get("provider_odd_id") or "")
                        oname = str(odd.get("name") or "").lower()
                        val = float(odd.get("value") or 0.0)
                        if val <= 1.0:
                            continue
                        if p_line is None:
                            m_num = _NUM_RE.search(oname)
                            if m_num:
                                p_line = float(m_num.group(0))
                        if oid == "12" or "más" in oname or "mas" in oname or "over" in oname:
                            p_over = val
                        elif oid == "13" or "menos" in oname or "under" in oname:
                            p_under = val
                    if p_line is not None and p_over and p_under:
                        player_props.append(
                            {
                                "player_name": player_name,
                                "prop_category": "POINTS",
                                "line_value": p_line,
                                "over_odds": p_over,
                                "under_odds": p_under,
                                "book_name": "Te Apuesto Perú",
                            }
                        )

        home_odds = ml_odds_by_team.get(home_code)
        away_odds = ml_odds_by_team.get(away_code)
        if not (home_odds and away_odds) and not (total_line and over_odds and under_odds):
            continue

        spread_home_line = spread_line_by_team.get(home_code, (None, None))[0]
        spread_home_odds = spread_line_by_team.get(home_code, (None, None))[1]
        spread_away_odds = spread_line_by_team.get(away_code, (None, None))[1]

        parsed_rows.append(
            {
                "event_id": ev.get("id"),
                "start_time": ev.get("start_time"),
                "home_team": home_code,
                "away_team": away_code,
                "team_pair": frozenset({home_code, away_code}),
                "team_odds": ml_odds_by_team,
                "home_odds": float(home_odds or 0.0),
                "away_odds": float(away_odds or 0.0),
                "total_points_line": total_line,
                "total_over_odds": over_odds,
                "total_under_odds": under_odds,
                "spread_line_by_team": spread_line_by_team,
                "spread_home_line": spread_home_line,
                "spread_home_odds": spread_home_odds,
                "spread_away_odds": spread_away_odds,
                "player_props": player_props,
                "captured_at": now_str,
                "book_id": "teapuesto_pe",
                "book_name": "Te Apuesto Perú",
                "source": "Te Apuesto API Direct",
                "is_observed": True,
                "source_type": "OBSERVED",
            }
        )
    return parsed_rows


def parse_pinnacle_nba_events(
    matchups: list[dict[str, Any]],
    markets: list[dict[str, Any]],
    *,
    captured_at: str | None = None,
    include_live: bool = False,
) -> list[dict[str, Any]]:
    """
    Parses Pinnacle Arcadia matchups + period-0 straight markets into standardized NBA pre-game odds rows.
    """
    now_str = captured_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    main_games: dict[int, tuple[str, str, str]] = {}
    for m in matchups:
        if not isinstance(m, dict):
            continue
        if m.get("type") != "matchup" or m.get("special") is not None or not m.get("hasMarkets"):
            continue
        if not include_live and m.get("isLive"):
            continue
        align_map: dict[str, str] = {}
        for part in (m.get("participants") or []):
            align = str(part.get("alignment") or "").lower()
            tcode = _resolve_team_code(str(part.get("name") or ""))
            if align in ("home", "away") and tcode:
                align_map[align] = tcode
        if "home" in align_map and "away" in align_map and align_map["home"] != align_map["away"]:
            main_games[int(m["id"])] = (
                align_map["home"],
                align_map["away"],
                str(m.get("startTime") or ""),
            )

    by_mid: dict[int, list[dict[str, Any]]] = {}
    for mk in markets:
        if not isinstance(mk, dict):
            continue
        mid = mk.get("matchupId")
        if mid is None or int(mid) not in main_games:
            continue
        if mk.get("period") != 0 or mk.get("isAlternate") or mk.get("status") != "open":
            continue
        by_mid.setdefault(int(mid), []).append(mk)

    parsed_rows: list[dict[str, Any]] = []
    for mid, (home_code, away_code, start_time) in main_games.items():
        mks = by_mid.get(mid, [])
        if not mks:
            continue

        home_odds: float | None = None
        away_odds: float | None = None
        total_line: float | None = None
        over_odds: float | None = None
        under_odds: float | None = None
        spread_home_line: float | None = None
        spread_home_odds: float | None = None
        spread_away_odds: float | None = None

        for mk in mks:
            mtype = mk.get("type")
            prices = mk.get("prices") or []
            if mtype == "moneyline" and home_odds is None:
                p_map = {str(p.get("designation") or "").lower(): p for p in prices}
                if "home" in p_map and "away" in p_map:
                    try:
                        h_dec = american_to_decimal_odds(p_map["home"]["price"])
                        a_dec = american_to_decimal_odds(p_map["away"]["price"])
                        if h_dec > 1.0 and a_dec > 1.0:
                            home_odds, away_odds = h_dec, a_dec
                    except Exception:
                        pass
            elif mtype == "total" and total_line is None:
                p_map = {str(p.get("designation") or "").lower(): p for p in prices}
                if "over" in p_map and "under" in p_map and p_map["over"].get("points") is not None:
                    try:
                        ov = american_to_decimal_odds(p_map["over"]["price"])
                        un = american_to_decimal_odds(p_map["under"]["price"])
                        if ov > 1.0 and un > 1.0:
                            total_line = float(p_map["over"]["points"])
                            over_odds, under_odds = ov, un
                    except Exception:
                        pass
            elif mtype == "spread" and spread_home_line is None:
                p_map = {str(p.get("designation") or "").lower(): p for p in prices}
                if "home" in p_map and "away" in p_map and p_map["home"].get("points") is not None:
                    try:
                        sh = american_to_decimal_odds(p_map["home"]["price"])
                        sa = american_to_decimal_odds(p_map["away"]["price"])
                        if sh > 1.0 and sa > 1.0:
                            spread_home_line = float(p_map["home"]["points"])
                            spread_home_odds, spread_away_odds = sh, sa
                    except Exception:
                        pass

        if not (home_odds and away_odds) and not (total_line and over_odds and under_odds):
            continue

        parsed_rows.append(
            {
                "event_id": mid,
                "start_time": start_time,
                "home_team": home_code,
                "away_team": away_code,
                "team_pair": frozenset({home_code, away_code}),
                "team_odds": {home_code: home_odds or 0.0, away_code: away_odds or 0.0},
                "home_odds": float(home_odds or 0.0),
                "away_odds": float(away_odds or 0.0),
                "total_points_line": total_line,
                "total_over_odds": over_odds,
                "total_under_odds": under_odds,
                "spread_home_line": spread_home_line,
                "spread_home_odds": spread_home_odds,
                "spread_away_odds": spread_away_odds,
                "captured_at": now_str,
                "book_id": "pinnacle",
                "book_name": "Pinnacle",
                "source": "Pinnacle Arcadia Public API",
                "is_observed": True,
                "source_type": "OBSERVED",
            }
        )
    return parsed_rows


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
        self.enable_live_network = (
            (not bool(os.environ.get("PYTEST_CURRENT_TEST")))
            if enable_live_network is None
            else bool(enable_live_network)
        )
        self.hunter = StaleLineHunter(min_clv_pct=min_clv_pct, min_arb_margin_pct=min_arb_margin_pct)
        self.bot = TelegramAlertBot()
        self._teapuesto_cache: tuple[datetime, list[dict[str, Any]]] | None = None
        self._pinnacle_cache: tuple[datetime, list[dict[str, Any]]] | None = None

    def _fetch_teapuesto_slate(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Fetches pre-game NBA slate odds from Te Apuesto Perú public API with 60s instance cache."""
        if not self.enable_live_network:
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
        try:
            with httpx.Client(timeout=self.request_timeout, headers=headers) as client:
                resp = client.post(TEAPUESTO_TOURNAMENT_EVENTS_URL, json=payload)
                if resp.status_code == 200:
                    rows = parse_teapuesto_nba_events(
                        resp.json(),
                        captured_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    )
                    self._teapuesto_cache = (now, rows)
                    return rows
                logger.warning("Te Apuesto API returned status %s", resp.status_code)
        except Exception as exc:
            logger.debug("Te Apuesto live fetch failed: %s", exc)
        return []

    def _fetch_pinnacle_slate(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Fetches pre-game NBA sharp odds from Pinnacle Arcadia guest API with 60s cache."""
        if not self.enable_live_network:
            return []
        now = datetime.now(timezone.utc)
        if not force_refresh and self._pinnacle_cache is not None:
            cached_at, rows = self._pinnacle_cache
            if (now - cached_at).total_seconds() < 60.0:
                return rows
        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}
        try:
            with httpx.Client(timeout=self.request_timeout, headers=headers) as client:
                rm = client.get(PINNACLE_NBA_MATCHUPS_URL)
                rk = client.get(PINNACLE_NBA_MARKETS_URL)
                if rm.status_code == 200 and rk.status_code == 200:
                    rows = parse_pinnacle_nba_events(
                        rm.json(),
                        rk.json(),
                        captured_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    )
                    self._pinnacle_cache = (now, rows)
                    return rows
                logger.warning("Pinnacle Arcadia API returned %s / %s", rm.status_code, rk.status_code)
        except Exception as exc:
            logger.debug("Pinnacle Arcadia live fetch failed: %s", exc)
        return []

    def _match_slate_row(
        self,
        rows: list[dict[str, Any]],
        home_team: str,
        away_team: str,
    ) -> LiveGameOddsQuote | None:
        h_code = _resolve_team_code(home_team) or home_team.upper()
        a_code = _resolve_team_code(away_team) or away_team.upper()
        target_pair = frozenset({h_code, a_code})
        for row in rows:
            if row.get("team_pair") != target_pair:
                continue
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
                captured_at=str(row.get("captured_at") or ""),
                source=str(row.get("source") or "LIVE_EXTRACTOR"),
                is_observed=True,
                source_type="OBSERVED",
            )
        return None

    def fetch_live_teapuesto_odds(self, home_team: str, away_team: str) -> LiveGameOddsQuote | None:
        """Extracts live pre-game NBA odds from Te Apuesto Perú (public API)."""
        return self._match_slate_row(self._fetch_teapuesto_slate(), home_team, away_team)

    def fetch_live_pinnacle_odds(self, home_team: str, away_team: str) -> LiveGameOddsQuote | None:
        """Extracts live pre-game NBA sharp odds from Pinnacle Arcadia guest API."""
        return self._match_slate_row(self._fetch_pinnacle_slate(), home_team, away_team)

    def fetch_live_retabet_odds(self, home_team: str, away_team: str) -> LiveGameOddsQuote | None:
        """
        Queries RETAbet Perú only when explicitly accessible without WAF evasion.
        Returns None cleanly on network errors or WAF blocks (zero synthetic fallback).
        """
        if not self.enable_live_network:
            return None
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = "https://api.retabet.pe/sports/v2/events/nba"
        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}

        try:
            with httpx.Client(timeout=self.request_timeout, headers=headers) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for ev in data.get("events", []):
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
        except Exception as exc:
            logger.debug(f"RETAbet live fetch failed: {exc}")
        return None

    def fetch_live_betsson_odds(self, home_team: str, away_team: str) -> LiveGameOddsQuote | None:
        """Queries Betsson/Altenar feed when accessible without WAF challenge."""
        if not self.enable_live_network:
            return None
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = "https://sb2frontend-altenar2.biahosted.com/api/Sportsbook/GetEvents"
        params = {"sportId": "66", "timezoneOffset": "-300"}  # Basketball / PET
        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}

        try:
            with httpx.Client(timeout=self.request_timeout, headers=headers) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    for ev in data.get("events", []):
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
        except Exception as exc:
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
        live_ta = self.fetch_live_teapuesto_odds(home_team, away_team)
        if live_ta:
            quotes_by_book["teapuesto_pe"] = live_ta

        live_pin = self.fetch_live_pinnacle_odds(home_team, away_team)
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
            # Note: odds_snapshots CHECK constraint accepts ('moneyline', 'total_points', 'player_prop');
            # spread lines remain exposed on LiveGameOddsQuote & scan JSON outputs.

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
            if res.get("observed_quotes_count", 0) > 0 or bench is not None:
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

        # Persist results summary to data/evaluation only during live runs (not during tests)
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            out_file = Path("data/evaluation/latest_peru_odds_scan.json")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info(f"Escaneo de cuotas peruanas completado para {len(results)} partidos. Alertas despachadas: {alerts_sent}.")
        return results
