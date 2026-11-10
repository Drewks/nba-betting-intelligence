"""
Real-Time Peruvian Sportsbook Scraping & Latency Arbitrage Engine (`src/ingestion/live_peru_scraper.py`).
Actively monitors live decimal odds across Peruvian sportsbooks:
  - RETAbet Perú (retabet.pe)
  - Betsson Perú (betsson.pe)
  - Doradobet Perú (doradobet.com)
  - Coolbet Perú (coolbet.pe)
  - Apuesta Total (apuestatotal.com)
  - Pinnacle / Sharp Market Maker (benchmark)

Detects:
  1. Stale Lines (retail odds lagging behind Pinnacle sharp line moves by >= 4.0% CLV).
  2. Risk-free Cross-Bookmaker Arbitrage (Surebets) in Soles (S/. PEN).
  3. Soft-book +EV mispricings across Peruvian retail books.
"""

from __future__ import annotations

import os

from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from src.ingestion.stale_line_hunter import StaleLineHunter
from src.reporting.telegram_bot import TelegramAlertBot
from src.storage.db import DatabaseManager
from src.utils.team_dictionary import format_matchup

logger = logging.getLogger("PeruOddsScraper")

PERU_OFFSET = timezone(timedelta(hours=-5))


@dataclass
class LiveGameOddsQuote:
    book_id: str
    book_name: str
    home_odds: float
    away_odds: float
    spread_home_line: float | None = None
    spread_home_odds: float | None = None
    total_points_line: float | None = None
    total_over_odds: float | None = None
    captured_at: str = ""
    source: str = "LIVE_EXTRACTOR"
    is_observed: bool = True
    source_type: str = "OBSERVED"


class LivePeruOddsScraper:
    """
    Automated real-time odds monitor for licensed and retail Peruvian sportsbooks.
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
    ) -> None:
        self.db = db
        self.min_clv_pct = min_clv_pct
        self.min_arb_margin_pct = min_arb_margin_pct
        self.bankroll_pen = bankroll_pen
        self.request_timeout = request_timeout
        self.hunter = StaleLineHunter(min_clv_pct=min_clv_pct, min_arb_margin_pct=min_arb_margin_pct)
        self.bot = TelegramAlertBot()

    def fetch_live_retabet_odds(self, home_team: str, away_team: str) -> LiveGameOddsQuote | None:
        """
        Extracts live odds from RETAbet Perú (retabet.pe).
        Uses direct sports API query with fallback to calibrated local market quote.
        """
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
        """Extracts live odds from Betsson Perú (betsson.pe)."""
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

        # 2. Genuine live quotes fetched from retail books (the only quotes that are persisted).
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
                  AND provider IN ('RETAbet Perú', 'Betano Perú', 'Betsson Perú', 'Inkabet', 'Te Apuesto')
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
                    else ("betsson_pe" if "Betsson" in prov else prov.lower().replace(" ", "_")))
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

        # 3. Stale lines: observed retail quotes vs observed sharp benchmark only.
        stale_opportunities: list[dict[str, Any]] = []
        if sharp_quote and quotes_by_book:
            retail_home_list = [
                {"bookmaker": q.book_name, "decimal_odds": q.home_odds, "selection": "HOME"}
                for q in quotes_by_book.values()
            ]
            retail_away_list = [
                {"bookmaker": q.book_name, "decimal_odds": q.away_odds, "selection": "AWAY"}
                for q in quotes_by_book.values()
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

        # 4. Surebets: only across observed quotes (live retail + stored sharp benchmark).
        observed_pool = list(quotes_by_book.values()) + ([sharp_quote] if sharp_quote else [])
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

        # 5. Persist only genuinely fetched quotes
        if self.db:
            self._persist_quotes_to_db(game_id, quotes_by_book, now_str)

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
            for selection, price, counter in (("HOME", q.home_odds, q.away_odds), ("AWAY", q.away_odds, q.home_odds)):
                self.db.insert_odds_snapshot(
                    {
                        "odds_id": f"ODDS_LIVEAPI_{game_id}_{bid}_{selection}_{now_str}",
                        "game_id": game_id,
                        "provider": provider,
                        "market": "moneyline",
                        "selection": selection,
                        "line_value": None,
                        "decimal_odds": float(price),
                        "counterpart_decimal_odds": float(counter),
                        "captured_at": q.captured_at or now_str,
                        "is_closing_line": 0,
                        "source_type": "OBSERVED",
                    }
                )

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
                logger.info("Skipping %s: no observed sharp (Pinnacle) moneyline quote stored.", gid)
                continue

            res = self.collect_slate_odds(
                game_id=gid,
                home_team=g["home_team"],
                away_team=g["away_team"],
                game_start_time=g["game_start_time"],
                sharp_home_odds=bench["home_odds"],
                sharp_away_odds=bench["away_odds"],
                as_of_utc=now_utc,
                sharp_book_name=bench["provider"],
                sharp_captured_at=bench["captured_at"],
            )
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
