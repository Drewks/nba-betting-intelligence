"""
The Odds API v4 Adapter (`src/ingestion/the_odds_api.py`).
Performs multi-bookmaker Line Shopping across 20+ sportsbooks and extracts Pinnacle's sharp
counterpart odds for accurate de-vigging and EV calculation.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from typing import Any
import urllib.error
import urllib.request
import numpy as np

from src.config import load_config
from src.ingestion.normalizer import normalize_team_code

logger = logging.getLogger(__name__)


def _load_dotenv_if_present() -> None:
    """Loads local .env file into os.environ if present without overwriting existing env vars."""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                cleaned = line.strip()
                if cleaned and not cleaned.startswith("#") and "=" in cleaned:
                    k, v = cleaned.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'").strip('"')
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception as exc:
            logger.warning(f"Handled exception loading .env: {exc}")


_load_dotenv_if_present()


class TheOddsAPIAdapter:
    """
    Phase V2.4 Adapter for The Odds API v4 (https://api.the-odds-api.com/v4/sports/basketball_nba/odds).
    Performs multi-bookmaker Line Shopping across 20+ sportsbooks and extracts Pinnacle's sharp
    counterpart odds for accurate de-vigging and EV calculation.
    """

    provider_name = "the_odds_api_v4_lineshopper"
    _DISABLED_KEY_FINGERPRINTS: set[str] = set()
    _LAST_REMAINING_REQUESTS: int | None = None
    _RESPONSE_CACHE: dict[tuple[str, str, str], tuple[float, dict[tuple[str, str, str], list[dict[str, Any]]]]] = {}

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: int = 10,
        *,
        regions: str | None = None,
        markets: str | None = None,
        cache_ttl_seconds: int | None = None,
    ) -> None:
        _load_dotenv_if_present()
        self.api_key = (api_key or os.getenv("THE_ODDS_API_KEY") or "").strip()
        self.timeout_seconds = timeout_seconds
        try:
            src_cfg = load_config().sources
            default_regions = src_cfg.the_odds_api_regions
            default_markets = src_cfg.the_odds_api_markets
            default_ttl = src_cfg.the_odds_api_cache_ttl_seconds
        except Exception:
            default_regions, default_markets, default_ttl = "eu", "h2h,totals", 300
        self.regions = (regions if regions is not None else default_regions).strip() or "eu"
        self.markets = (markets if markets is not None else default_markets).strip() or "h2h,totals"
        self.cache_ttl_seconds = max(0, int(default_ttl if cache_ttl_seconds is None else cache_ttl_seconds))

    @classmethod
    def clear_cache(cls) -> None:
        """Clears the in-process HTTP response TTL cache."""
        cls._RESPONSE_CACHE.clear()

    @classmethod
    def reset_circuit_breaker(cls) -> None:
        """Clears per-process circuit-breaker and cache state (primarily for tests or key rotation)."""
        cls._DISABLED_KEY_FINGERPRINTS.clear()
        cls._LAST_REMAINING_REQUESTS = None
        cls._RESPONSE_CACHE.clear()

    def _key_fingerprint(self) -> str:
        return hashlib.sha256(self.api_key.encode("utf-8")).hexdigest()[:12]

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def fetch_multi_book_odds_by_matchup(self, now_utc: str) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
        """
        Fetches live decimal odds across configured bookmaker regions/markets
        and returns a mapping keyed by (matchday_date, away_team_code, home_team_code).
        """
        if not self.api_key:
            return {}

        key_fp = self._key_fingerprint()
        if key_fp in self._DISABLED_KEY_FINGERPRINTS:
            logger.debug("TheOddsAPI circuit breaker open for key %s; skipping call.", key_fp)
            return {}

        cache_key = (key_fp, self.regions, self.markets)
        if self.cache_ttl_seconds > 0:
            cached_entry = self._RESPONSE_CACHE.get(cache_key)
            if cached_entry is not None:
                cached_ts, cached_map = cached_entry
                age_sec = time.monotonic() - cached_ts
                if age_sec <= self.cache_ttl_seconds:
                    logger.debug("TheOddsAPI cache hit (age=%.1fs); saved API quota.", age_sec)
                    return {k: [dict(item) for item in v] for k, v in cached_map.items()}

        url = (
            f"https://api.the-odds-api.com/v4/sports/basketball_nba/odds/"
            f"?apiKey={self.api_key}&regions={self.regions}&markets={self.markets}&oddsFormat=decimal"
        )
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                },
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                events = json.loads(resp.read().decode("utf-8"))
                headers = getattr(resp, "headers", None)
                if headers is not None:
                    rem_raw = headers.get("x-requests-remaining")
                    used_raw = headers.get("x-requests-used")
                    if isinstance(rem_raw, (int, str)):
                        remaining: int | None = None
                        try:
                            remaining = int(rem_raw)
                        except (TypeError, ValueError):
                            remaining = None
                        if remaining is not None:
                            type(self)._LAST_REMAINING_REQUESTS = remaining
                            logger.info("TheOddsAPI quota: used=%s remaining=%s", used_raw, remaining)
                            if remaining <= 0:
                                type(self)._DISABLED_KEY_FINGERPRINTS.add(key_fp)
                                logger.warning(
                                    "TheOddsAPI quota exhausted (remaining=%d); circuit breaker tripped for this run.",
                                    remaining,
                                )
        except Exception as exc:
            sanitized = str(exc)
            if self.api_key:
                sanitized = sanitized.replace(self.api_key, "***")
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 402, 429):
                type(self)._DISABLED_KEY_FINGERPRINTS.add(key_fp)
                logger.warning(
                    "TheOddsAPI request failed: %s — circuit breaker tripped for this run (HTTP %d; check THE_ODDS_API_KEY / quota).",
                    sanitized,
                    exc.code,
                )
            else:
                logger.warning("TheOddsAPI request failed: %s", sanitized)
            return {}

        by_matchup: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)

        for ev in events:
            commence = ev.get("commence_time", "")
            if not commence or commence <= now_utc:
                continue
            try:
                home_code = normalize_team_code(ev.get("home_team", ""))
                away_code = normalize_team_code(ev.get("away_team", ""))
            except ValueError:
                continue

            matchday_date = commence[:10]
            bookmakers = ev.get("bookmakers") or []
            if not bookmakers:
                continue

            best_home_odds = 0.0
            best_home_book = ""
            best_home_counterpart = 0.0

            best_away_odds = 0.0
            best_away_book = ""
            best_away_counterpart = 0.0

            pinnacle_home_odds: float | None = None
            pinnacle_away_odds: float | None = None
            all_home_prices: list[float] = []
            all_away_prices: list[float] = []

            totals_by_line: dict[float, dict[str, Any]] = defaultdict(
                lambda: {
                    "best_over": 0.0,
                    "best_over_book": "",
                    "over_counterpart": 0.0,
                    "best_under": 0.0,
                    "best_under_book": "",
                    "under_counterpart": 0.0,
                    "pinnacle_over": None,
                    "pinnacle_under": None,
                    "over_prices": [],
                    "under_prices": [],
                    "has_pinnacle": False,
                    "book_count": 0,
                }
            )

            for book in bookmakers:
                b_key = book.get("key", "book")
                b_title = book.get("title", b_key)
                for mkt in book.get("markets") or []:
                    m_key = mkt.get("key")
                    outcomes = mkt.get("outcomes") or []
                    if m_key == "h2h" and len(outcomes) == 2:
                        h_price = None
                        a_price = None
                        for out in outcomes:
                            try:
                                code = normalize_team_code(out.get("name", ""))
                                price = float(out.get("price", 0.0))
                            except Exception:
                                continue
                            if code == home_code:
                                h_price = price
                            elif code == away_code:
                                a_price = price
                        if h_price and a_price and h_price > 1.0 and a_price > 1.0:
                            all_home_prices.append(h_price)
                            all_away_prices.append(a_price)
                            if b_key == "pinnacle":
                                pinnacle_home_odds = h_price
                                pinnacle_away_odds = a_price
                            if h_price > best_home_odds:
                                best_home_odds = h_price
                                best_home_book = f"{b_title} (Best of {len(bookmakers)} books)"
                                best_home_counterpart = a_price
                            if a_price > best_away_odds:
                                best_away_odds = a_price
                                best_away_book = f"{b_title} (Best of {len(bookmakers)} books)"
                                best_away_counterpart = h_price

                    elif m_key == "totals" and len(outcomes) == 2:
                        over_p = None
                        under_p = None
                        line_pt = None
                        for out in outcomes:
                            nm = str(out.get("name", "")).upper()
                            pt = out.get("point")
                            pr = out.get("price")
                            if pt is not None and pr is not None:
                                line_pt = float(pt)
                                if nm == "OVER":
                                    over_p = float(pr)
                                elif nm == "UNDER":
                                    under_p = float(pr)
                        if line_pt is not None and over_p and under_p and over_p > 1.0 and under_p > 1.0:
                            entry = totals_by_line[line_pt]
                            entry["book_count"] += 1
                            entry["over_prices"].append(over_p)
                            entry["under_prices"].append(under_p)
                            if b_key == "pinnacle":
                                entry["has_pinnacle"] = True
                                entry["pinnacle_over"] = over_p
                                entry["pinnacle_under"] = under_p
                            if over_p > entry["best_over"]:
                                entry["best_over"] = over_p
                                entry["best_over_book"] = f"{b_title} (LineShop)"
                                entry["over_counterpart"] = under_p
                            if under_p > entry["best_under"]:
                                entry["best_under"] = under_p
                                entry["best_under_book"] = f"{b_title} (LineShop)"
                                entry["under_counterpart"] = over_p

            if best_home_odds > 1.0 and best_away_odds > 1.0:
                med_away = float(np.median(all_away_prices)) if len(all_away_prices) >= 2 else best_home_counterpart
                med_home = float(np.median(all_home_prices)) if len(all_home_prices) >= 2 else best_away_counterpart
                h_counter = pinnacle_away_odds if pinnacle_away_odds else med_away
                a_counter = pinnacle_home_odds if pinnacle_home_odds else med_home
                by_matchup[(matchday_date, away_code, home_code)].extend(
                    [
                        {
                            "provider": best_home_book,
                            "market": "moneyline",
                            "selection": "HOME",
                            "line_value": None,
                            "decimal_odds": round(best_home_odds, 4),
                            "counterpart_decimal_odds": round(h_counter, 4),
                            "captured_at": now_utc,
                            "is_closing_line": 0,
                            "source_type": "OBSERVED",
                        },
                        {
                            "provider": best_away_book,
                            "market": "moneyline",
                            "selection": "AWAY",
                            "line_value": None,
                            "decimal_odds": round(best_away_odds, 4),
                            "counterpart_decimal_odds": round(a_counter, 4),
                            "captured_at": now_utc,
                            "is_closing_line": 0,
                            "source_type": "OBSERVED",
                        },
                    ]
                )

            if totals_by_line:
                chosen_line = sorted(
                    totals_by_line.keys(),
                    key=lambda ln: (1 if totals_by_line[ln]["has_pinnacle"] else 0, totals_by_line[ln]["book_count"]),
                    reverse=True,
                )[0]
                t_info = totals_by_line[chosen_line]
                if t_info["best_over"] > 1.0 and t_info["best_under"] > 1.0:
                    over_cnt = t_info["pinnacle_under"] or (
                        float(np.median(t_info["under_prices"])) if len(t_info["under_prices"]) >= 2 else t_info["over_counterpart"]
                    )
                    under_cnt = t_info["pinnacle_over"] or (
                        float(np.median(t_info["over_prices"])) if len(t_info["over_prices"]) >= 2 else t_info["under_counterpart"]
                    )
                    by_matchup[(matchday_date, away_code, home_code)].extend(
                        [
                            {
                                "provider": t_info["best_over_book"],
                                "market": "total_points",
                                "selection": "OVER",
                                "line_value": float(chosen_line),
                                "decimal_odds": round(float(t_info["best_over"]), 4),
                                "counterpart_decimal_odds": round(float(over_cnt), 4),
                                "captured_at": now_utc,
                                "is_closing_line": 0,
                                "source_type": "OBSERVED",
                            },
                            {
                                "provider": t_info["best_under_book"],
                                "market": "total_points",
                                "selection": "UNDER",
                                "line_value": float(chosen_line),
                                "decimal_odds": round(float(t_info["best_under"]), 4),
                                "counterpart_decimal_odds": round(float(under_cnt), 4),
                                "captured_at": now_utc,
                                "is_closing_line": 0,
                                "source_type": "OBSERVED",
                            },
                        ]
                    )

        if self.cache_ttl_seconds > 0:
            type(self)._RESPONSE_CACHE[cache_key] = (
                time.monotonic(),
                {k: [dict(item) for item in v] for k, v in by_matchup.items()},
            )

        return by_matchup
