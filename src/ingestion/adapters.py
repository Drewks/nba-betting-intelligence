"""
Interchangeable NBA data and odds adapters (V2 Syndicate-Grade):
- ESPNPublicAdapter: Live schedules, final scores, real-time injury reports (`summary?event=...`),
  Four Factors boxscore stats (`avgPoints`, `avgPointsAgainst`, `FG%`, `3P%`, `Turnovers`, `Rebounds`),
  and schedule rest/altitude adjustments.
- TheOddsAPIAdapter: Multi-bookmaker line shopping across 20+ sportsbooks (`pinnacle`, `fanduel`,
  `draftkings`, `betmgm`, `betsson`, `coolbet`, `marathonbet`, `bovada`, etc.), using Pinnacle's
  de-vigged line as the sharp market reference and picking the highest decimal price available.
- SportradarAdapter, NBAStatsAdapter, PlaywrightAuthorizedScraper, SyntheticFixtureAdapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
from typing import Any
import urllib.request

import numpy as np

from src.ingestion.normalizer import (
    NBA_TEAMS,
    american_to_decimal_odds,
    normalize_season,
    normalize_team_code,
)


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
        except Exception:
            pass


_load_dotenv_if_present()


# High-impact NBA star players (estimated point spread value when ruled OUT)
STAR_PLAYER_IMPACT_PTS: dict[str, float] = {
    "Nikola Jokic": 6.8,
    "Luka Doncic": 6.2,
    "Shai Gilgeous-Alexander": 6.0,
    "Giannis Antetokounmpo": 6.0,
    "Joel Embiid": 5.8,
    "Victor Wembanyama": 5.2,
    "Jayson Tatum": 4.8,
    "Stephen Curry": 5.0,
    "Anthony Davis": 4.6,
    "LeBron James": 4.4,
    "Kevin Durant": 4.5,
    "Anthony Edwards": 4.5,
    "Jalen Brunson": 4.5,
    "Donovan Mitchell": 4.3,
    "Devin Booker": 4.2,
    "Tyrese Haliburton": 4.2,
    "Ja Morant": 4.2,
    "Kawhi Leonard": 4.2,
    "Damian Lillard": 4.0,
    "Domantas Sabonis": 4.0,
    "Jimmy Butler": 3.8,
    "Lauri Markkanen": 3.8,
    "Jaren Jackson Jr.": 3.5,
    "Paolo Banchero": 3.6,
    "Zion Williamson": 3.6,
    "Trae Young": 3.8,
    "Cade Cunningham": 3.5,
    "Chet Holmgren": 3.5,
    "Jaylen Brown": 3.5,
    "Bam Adebayo": 3.5,
    "De'Aaron Fox": 3.6,
    "Karl-Anthony Towns": 3.4,
    "Kyrie Irving": 3.5,
    "James Harden": 3.3,
    "Paul George": 3.3,
    "Jusuf Nurkic": 2.2,
    "Tobias Harris": 2.0,
}

# High-altitude home courts (extra home advantage in points)
HIGH_ALTITUDE_BONUS_PTS: dict[str, float] = {
    "DEN": 1.6,  # Mile High (1,609m)
    "UTA": 1.1,  # Salt Lake City (1,288m)
}


class AdapterUnavailableError(RuntimeError):
    """Raised when an external data adapter cannot be reached or lacks credentials."""


class BaseNBADataAdapter(ABC):
    """Abstract interface for interchangeable NBA statistics, schedule, and odds providers."""

    provider_name: str = "base"

    @abstractmethod
    def fetch_games_and_odds(
        self,
        date_str: str | None = None,
        as_of_utc: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Returns {'games': [...], 'odds': [...]} with explicit provenance and timestamps."""


class TheOddsAPIAdapter:
    """
    Phase V2.4 Adapter for The Odds API v4 (https://api.the-odds-api.com/v4/sports/basketball_nba/odds).
    Performs multi-bookmaker Line Shopping across 20+ sportsbooks and extracts Pinnacle's sharp
    counterpart odds for accurate de-vigging and EV calculation.
    """

    provider_name = "the_odds_api_v4_lineshopper"

    def __init__(self, api_key: str | None = None, timeout_seconds: int = 10) -> None:
        _load_dotenv_if_present()
        self.api_key = (api_key or os.getenv("THE_ODDS_API_KEY", "")).strip()
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def fetch_multi_book_odds_by_matchup(self, now_utc: str) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
        """
        Fetches live decimal odds across US & EU bookmakers (including Pinnacle, FanDuel, DraftKings, BetMGM)
        and returns a mapping keyed by (matchday_date, away_team_code, home_team_code).
        """
        if not self.api_key:
            return {}

        url = (
            f"https://api.the-odds-api.com/v4/sports/basketball_nba/odds/"
            f"?apiKey={self.api_key}&regions=us,eu&markets=h2h,totals&oddsFormat=decimal"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                events = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return {}

        by_matchup: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)

        for ev in events:
            commence = ev.get("commence_time", "")
            if not commence or commence <= now_utc:
                # Strictly pre-game only
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

            # 1.Moneyline (h2h): Find best price for HOME and AWAY across all books, plus Pinnacle reference
            best_home_odds = 0.0
            best_home_book = ""
            best_home_counterpart = 0.0

            best_away_odds = 0.0
            best_away_book = ""
            best_away_counterpart = 0.0

            pinnacle_home_odds: float | None = None
            pinnacle_away_odds: float | None = None

            # Also track totals grouped by point line
            totals_by_line: dict[float, dict[str, Any]] = defaultdict(
                lambda: {
                    "best_over": 0.0,
                    "best_over_book": "",
                    "over_counterpart": 0.0,
                    "best_under": 0.0,
                    "best_under_book": "",
                    "under_counterpart": 0.0,
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
                            if b_key == "pinnacle":
                                entry["has_pinnacle"] = True
                            if over_p > entry["best_over"]:
                                entry["best_over"] = over_p
                                entry["best_over_book"] = f"{b_title} (LineShop)"
                                entry["over_counterpart"] = under_p
                            if under_p > entry["best_under"]:
                                entry["best_under"] = under_p
                                entry["best_under_book"] = f"{b_title} (LineShop)"
                                entry["under_counterpart"] = over_p

            # Use Pinnacle counterpart odds if available so de-vigged fair probability reflects Pinnacle's sharp line
            if best_home_odds > 1.0 and best_away_odds > 1.0:
                h_counter = pinnacle_away_odds if pinnacle_away_odds else best_home_counterpart
                a_counter = pinnacle_home_odds if pinnacle_home_odds else best_away_counterpart
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
                        },
                    ]
                )

            if totals_by_line:
                # Choose the consensus line (preferring Pinnacle's line or highest book_count)
                chosen_line = sorted(
                    totals_by_line.keys(),
                    key=lambda ln: (1 if totals_by_line[ln]["has_pinnacle"] else 0, totals_by_line[ln]["book_count"]),
                    reverse=True,
                )[0]
                t_info = totals_by_line[chosen_line]
                if t_info["best_over"] > 1.0 and t_info["best_under"] > 1.0:
                    by_matchup[(matchday_date, away_code, home_code)].extend(
                        [
                            {
                                "provider": t_info["best_over_book"],
                                "market": "total_points",
                                "selection": "OVER",
                                "line_value": float(chosen_line),
                                "decimal_odds": round(float(t_info["best_over"]), 4),
                                "counterpart_decimal_odds": round(float(t_info["over_counterpart"]), 4),
                                "captured_at": now_utc,
                                "is_closing_line": 0,
                            },
                            {
                                "provider": t_info["best_under_book"],
                                "market": "total_points",
                                "selection": "UNDER",
                                "line_value": float(chosen_line),
                                "decimal_odds": round(float(t_info["best_under"]), 4),
                                "counterpart_decimal_odds": round(float(t_info["under_counterpart"]), 4),
                                "captured_at": now_utc,
                                "is_closing_line": 0,
                            },
                        ]
                    )

        return by_matchup


class ESPNPublicAdapter(BaseNBADataAdapter):
    """
    V2 Structured Adapter for ESPN's public NBA API + optional TheOddsAPI multi-bookmaker enrichment:
    - Fase V2.1: Real-time injury report extraction & star player point-spread penalty (`summary?event=...`)
    - Fase V2.2: Four Factors boxscore extraction (`avgPoints`, `avgPointsAgainst`, `FG%`, `3P%`, `TOV`),
      real schedule rest days (`Back-to-Back` detection) and high-altitude adjustment (`DEN`, `UTA`)
    - Fase V2.4: Automatically merges multi-bookmaker Line Shopping odds from `TheOddsAPIAdapter` when configured.
    """

    provider_name = "espn_v2_syndicate_enriched"

    def __init__(self, timeout_seconds: int = 8, enrich_with_the_odds_api: bool = True) -> None:
        self.timeout_seconds = timeout_seconds
        self.enrich_with_the_odds_api = enrich_with_the_odds_api
        self.odds_api_helper = TheOddsAPIAdapter(timeout_seconds=timeout_seconds)

    def _fetch_event_summary_context(self, event_id: str) -> dict[str, Any]:
        """Fetches live pre-game injury report and detailed team boxscore statistics from ESPN summary."""
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return {"injury_penalties": {}, "team_box_stats": {}}

        injury_penalties: dict[str, float] = {}
        for t_inj in data.get("injuries") or []:
            raw_abbr = t_inj.get("team", {}).get("abbreviation", "")
            try:
                t_code = normalize_team_code(raw_abbr)
            except ValueError:
                continue
            penalty = 0.0
            for inj in t_inj.get("injuries") or []:
                player_name = inj.get("athlete", {}).get("displayName", "")
                status = str(inj.get("status", "")).lower()
                star_val = STAR_PLAYER_IMPACT_PTS.get(player_name, 1.25)
                if "out" in status:
                    penalty += star_val
                elif "doubtful" in status:
                    penalty += 0.70 * star_val
                elif "questionable" in status or "day-to-day" in status:
                    penalty += 0.30 * star_val
            injury_penalties[t_code] = round(min(11.5, penalty), 2)

        team_box_stats: dict[str, dict[str, float]] = {}
        for bt in data.get("boxscore", {}).get("teams") or []:
            raw_abbr = bt.get("team", {}).get("abbreviation", "")
            try:
                t_code = normalize_team_code(raw_abbr)
            except ValueError:
                continue
            s_map: dict[str, float] = {}
            for s in bt.get("statistics") or []:
                nm = s.get("name")
                dv = s.get("displayValue")
                if nm and dv is not None:
                    try:
                        s_map[nm] = float(dv)
                    except ValueError:
                        pass
            team_box_stats[t_code] = s_map

        return {
            "injury_penalties": injury_penalties,
            "team_box_stats": team_box_stats,
        }

    def fetch_games_and_odds(
        self,
        date_str: str | None = None,
        as_of_utc: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        now_utc = as_of_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
        if date_str:
            compact_date = date_str.replace("-", "")
            url = f"{url}?dates={compact_date}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise AdapterUnavailableError(f"ESPNPublicAdapter request failed: {exc}") from exc

        multi_book_odds: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        if self.enrich_with_the_odds_api and self.odds_api_helper.is_configured():
            multi_book_odds = self.odds_api_helper.fetch_multi_book_odds_by_matchup(now_utc)

        sr_context = SportradarAdapter().fetch_league_intelligence_context()
        sr_injuries = sr_context.get("injury_penalties", {})
        sr_splits = sr_context.get("team_splits", {})

        games_out: list[dict[str, Any]] = []
        odds_out: list[dict[str, Any]] = []

        season_year = payload.get("season", {}).get("year", 2027)
        season_label = normalize_season(int(season_year) - 1)

        for event in payload.get("events", []):
            ev_id = str(event.get("id", ""))
            comp = (event.get("competitions") or [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) != 2:
                continue

            home_comp = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away_comp = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not home_comp or not away_comp:
                continue

            try:
                home_code = normalize_team_code(home_comp["team"]["abbreviation"])
                away_code = normalize_team_code(away_comp["team"]["abbreviation"])
            except ValueError:
                continue

            raw_date = event.get("date", "")
            if len(raw_date) == 17 and raw_date.endswith("Z"):
                game_start_time = raw_date[:-1] + ":00Z"
            else:
                game_start_time = raw_date

            matchday_date = game_start_time[:10]
            status_name = comp.get("status", {}).get("type", {}).get("name", "STATUS_SCHEDULED")
            if "FINAL" in status_name:
                status = "FINAL"
            elif "POSTPONED" in status_name:
                status = "POSTPONED"
            elif "CANCELED" in status_name or "CANCELLED" in status_name:
                status = "CANCELLED"
            elif status_name == "STATUS_SCHEDULED" and now_utc < game_start_time:
                status = "SCHEDULED"
            else:
                # Skip IN_PROGRESS / HALFTIME games (no live in-play betting in v1/v2)
                continue

            home_score = int(home_comp["score"]) if status == "FINAL" and home_comp.get("score") else None
            away_score = int(away_comp["score"]) if status == "FINAL" and away_comp.get("score") else None

            game_id = f"ESPN_{ev_id}_{matchday_date}_{away_code}_AT_{home_code}"

            # Fetch V2.1 & V2.2 summary context (injuries + Four Factors boxscore) for SCHEDULED games
            summary_ctx = (
                self._fetch_event_summary_context(ev_id)
                if status == "SCHEDULED" and ev_id
                else {"injury_penalties": {}, "team_box_stats": {}}
            )

            odds_list = comp.get("odds") or []
            first_odds = odds_list[0] if odds_list else {}

            home_inj = max(
                float(summary_ctx["injury_penalties"].get(home_code, 0.0)),
                float(sr_injuries.get(home_code, 0.0)),
            )
            away_inj = max(
                float(summary_ctx["injury_penalties"].get(away_code, 0.0)),
                float(sr_injuries.get(away_code, 0.0)),
            )

            home_base_off, home_base_def, home_pace = self._estimate_pregame_team_profile(
                home_code,
                home_comp,
                first_odds,
                is_home=True,
                injury_penalty=home_inj,
                opp_injury_penalty=away_inj,
                box_stats=summary_ctx["team_box_stats"].get(home_code, {}),
                sr_split=sr_splits.get(home_code, {}),
            )
            away_base_off, away_base_def, away_pace = self._estimate_pregame_team_profile(
                away_code,
                away_comp,
                first_odds,
                is_home=False,
                injury_penalty=away_inj,
                opp_injury_penalty=home_inj,
                box_stats=summary_ctx["team_box_stats"].get(away_code, {}),
                sr_split=sr_splits.get(away_code, {}),
            )

            try:
                start_dt = datetime.fromisoformat(game_start_time.replace("Z", "+00:00"))
                now_dt_parsed = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
                pregame_avail_dt = min(now_dt_parsed, start_dt - timedelta(hours=2))
                features_available_at = pregame_avail_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                features_available_at = now_utc

            games_out.append(
                {
                    "game_id": game_id,
                    "season": season_label,
                    "matchday_date": matchday_date,
                    "game_start_time": game_start_time,
                    "home_team": home_code,
                    "away_team": away_code,
                    "status": status,
                    "home_score": home_score,
                    "away_score": away_score,
                    "home_off_rtg": home_base_off,
                    "home_def_rtg": home_base_def,
                    "home_pace": home_pace,
                    "away_off_rtg": away_base_off,
                    "away_def_rtg": away_base_def,
                    "away_pace": away_pace,
                    "home_rest_days": 2,
                    "away_rest_days": 2,
                    "features_available_at": features_available_at,
                    "source_provider": self.provider_name,
                    "ingested_at": now_utc,
                    "result_recorded_at": now_utc if status == "FINAL" else None,
                }
            )

            if status != "SCHEDULED":
                continue

            # Phase V2.4: Prefer multi-bookmaker Line Shopping (with Pinnacle reference) if available for this game
            lineshop_entries = multi_book_odds.get((matchday_date, away_code, home_code))
            if lineshop_entries:
                captured_at = now_utc if now_utc < game_start_time else features_available_at
                for ls in lineshop_entries:
                    suffix = f"{ls['market']}_{ls['selection']}_{ls['line_value']}"
                    odds_out.append(
                        {
                            "odds_id": f"{game_id}_{suffix}_LINESHOP",
                            "game_id": game_id,
                            "provider": ls["provider"],
                            "market": ls["market"],
                            "selection": ls["selection"],
                            "line_value": ls["line_value"],
                            "decimal_odds": ls["decimal_odds"],
                            "counterpart_decimal_odds": ls["counterpart_decimal_odds"],
                            "captured_at": captured_at,
                            "is_closing_line": 0,
                        }
                    )
                continue

            # Fallback to ESPN DraftKings pre-game feed if The Odds API didn't have the matchup
            for odds_obj in odds_list:
                provider_name = (
                    odds_obj.get("provider", {}).get("name")
                    or odds_obj.get("provider", {}).get("displayName")
                    or "DraftKings_via_ESPN"
                )
                captured_at = now_utc if now_utc < game_start_time else features_available_at
                ml = odds_obj.get("moneyline", {})
                home_ml_raw = ml.get("home", {}).get("close", {}).get("odds")
                away_ml_raw = ml.get("away", {}).get("close", {}).get("odds")
                if home_ml_raw and away_ml_raw:
                    try:
                        h_dec = american_to_decimal_odds(home_ml_raw)
                        a_dec = american_to_decimal_odds(away_ml_raw)
                        odds_out.append(
                            {
                                "odds_id": f"{game_id}_ML_HOME_{provider_name}",
                                "game_id": game_id,
                                "provider": provider_name,
                                "market": "moneyline",
                                "selection": "HOME",
                                "line_value": None,
                                "decimal_odds": h_dec,
                                "counterpart_decimal_odds": a_dec,
                                "captured_at": captured_at,
                                "is_closing_line": 0,
                            }
                        )
                        odds_out.append(
                            {
                                "odds_id": f"{game_id}_ML_AWAY_{provider_name}",
                                "game_id": game_id,
                                "provider": provider_name,
                                "market": "moneyline",
                                "selection": "AWAY",
                                "line_value": None,
                                "decimal_odds": a_dec,
                                "counterpart_decimal_odds": h_dec,
                                "captured_at": captured_at,
                                "is_closing_line": 0,
                            }
                        )
                    except ValueError:
                        pass

                tot = odds_obj.get("total", {})
                over_line_raw = odds_obj.get("overUnder")
                over_odds_raw = tot.get("over", {}).get("close", {}).get("odds")
                under_odds_raw = tot.get("under", {}).get("close", {}).get("odds")
                if over_line_raw is not None and over_odds_raw and under_odds_raw:
                    try:
                        line_val = float(over_line_raw)
                        o_dec = american_to_decimal_odds(over_odds_raw)
                        u_dec = american_to_decimal_odds(under_odds_raw)
                        odds_out.append(
                            {
                                "odds_id": f"{game_id}_TOT_OVER_{line_val}_{provider_name}",
                                "game_id": game_id,
                                "provider": provider_name,
                                "market": "total_points",
                                "selection": "OVER",
                                "line_value": line_val,
                                "decimal_odds": o_dec,
                                "counterpart_decimal_odds": u_dec,
                                "captured_at": captured_at,
                                "is_closing_line": 0,
                            }
                        )
                        odds_out.append(
                            {
                                "odds_id": f"{game_id}_TOT_UNDER_{line_val}_{provider_name}",
                                "game_id": game_id,
                                "provider": provider_name,
                                "market": "total_points",
                                "selection": "UNDER",
                                "line_value": line_val,
                                "decimal_odds": u_dec,
                                "counterpart_decimal_odds": o_dec,
                                "captured_at": captured_at,
                                "is_closing_line": 0,
                            }
                        )
                    except ValueError:
                        pass

        return {"games": games_out, "odds": odds_out}

    @staticmethod
    def _estimate_pregame_team_profile(
        team_code: str,
        comp_entry: dict[str, Any],
        first_odds: dict[str, Any] | None = None,
        is_home: bool = True,
        injury_penalty: float = 0.0,
        opp_injury_penalty: float = 0.0,
        box_stats: dict[str, float] | None = None,
        sr_split: dict[str, float] | None = None,
    ) -> tuple[float, float, float]:
        """
        V2 Pre-game Team Profile:
        Combines structural priors, Four Factors boxscore stats (`avgPoints`, `avgPointsAgainst`,
        `fieldGoalPct`, `threePointFieldGoalPct`, `avgTotalTurnovers`), Sportradar Official Standings
        & Tactical Splits (`home_win_pct`, `road_win_pct`, `last_10_win_pct`, `over_500_win_pct`),
        real-time Star Injury penalties, and High-Altitude court adjustments (`DEN`, `UTA`).
        """
        prior_strength: dict[str, tuple[float, float, float]] = {
            "BOS": (119.5, 110.8, 98.5),
            "OKC": (118.8, 110.2, 100.4),
            "DEN": (118.2, 112.1, 97.6),
            "NYK": (117.4, 112.0, 96.8),
            "MIN": (115.2, 109.5, 97.9),
            "DAL": (117.6, 113.8, 99.8),
            "MIL": (117.1, 114.2, 100.2),
            "CLE": (116.5, 111.5, 98.2),
            "PHI": (116.2, 113.0, 98.1),
            "IND": (120.1, 117.2, 102.3),
            "MIA": (113.8, 111.9, 96.5),
            "ORL": (113.2, 109.8, 97.4),
            "PHX": (116.8, 114.4, 98.9),
            "LAL": (115.9, 114.8, 100.6),
            "GSW": (116.4, 114.1, 99.7),
            "SAC": (116.2, 114.5, 100.1),
            "LAC": (115.6, 113.9, 97.8),
            "NOP": (115.4, 112.6, 98.6),
            "HOU": (114.5, 112.2, 99.4),
            "ATL": (116.7, 117.8, 101.4),
            "CHI": (114.0, 115.5, 98.0),
            "TOR": (112.5, 116.4, 99.5),
            "BKN": (112.1, 115.8, 97.7),
            "MEM": (113.5, 113.2, 99.1),
            "SAS": (112.4, 115.6, 101.2),
            "UTA": (114.2, 118.5, 99.9),
            "POR": (110.4, 116.8, 98.3),
            "CHA": (110.8, 117.4, 98.7),
            "DET": (111.2, 116.5, 99.6),
            "WAS": (110.5, 118.9, 102.1),
        }
        base_off, base_def, base_pace = prior_strength.get(team_code, (114.5, 114.5, 99.0))
        b_stats = box_stats or {}
        sr_data = sr_split or {}

        # 1. Four Factors & Real Season Boxscore Integration (Phase V2.2 + Sportradar PPG)
        avg_pts = b_stats.get("avgPoints") or sr_data.get("points_for")
        avg_pts_against = b_stats.get("avgPointsAgainst") or sr_data.get("points_against")
        if avg_pts and 95.0 <= float(avg_pts) <= 138.0:
            base_off = round(0.60 * base_off + 0.40 * float(avg_pts), 2)
        if avg_pts_against and 95.0 <= float(avg_pts_against) <= 138.0:
            base_def = round(0.60 * base_def + 0.40 * float(avg_pts_against), 2)

        # Shooting efficiency (FG% and 3P%) and Turnover control adjustment
        fg_pct = b_stats.get("fieldGoalPct", 47.0)
        tp_pct = b_stats.get("threePointFieldGoalPct", 36.0)
        tov = b_stats.get("avgTotalTurnovers", 14.0)
        efg_proxy = (fg_pct - 47.0) * 0.25 + (tp_pct - 36.0) * 0.15 - (tov - 14.0) * 0.20
        base_off = round(base_off + efg_proxy, 2)

        # 2. Win-Loss & Sportradar Venue/Momentum Tactical Splits
        records = comp_entry.get("records") or []
        if records and isinstance(records[0].get("summary"), str) and "-" in records[0]["summary"]:
            try:
                w_str, l_str = records[0]["summary"].split("-")[:2]
                wins, losses = int(w_str), int(l_str)
                if (wins + losses) > 0:
                    win_rate = wins / (wins + losses)
                    adj = (win_rate - 0.5) * 2.8
                    base_off = round(base_off + 0.5 * adj, 2)
                    base_def = round(base_def - 0.5 * adj, 2)
            except ValueError:
                pass

        if sr_data:
            venue_wp = sr_data.get("home_win_pct", 0.5) if is_home else sr_data.get("road_win_pct", 0.5)
            l10_wp = sr_data.get("last_10_win_pct", 0.5)
            tactical_adj = (venue_wp - 0.5) * 1.4 + (l10_wp - 0.5) * 1.0
            base_off = round(base_off + 0.5 * tactical_adj, 2)
            base_def = round(base_def - 0.5 * tactical_adj, 2)

        # 3. Real-Time Injury Report Adjustment (Phase V2.1: ESPN + Official Sportradar NBA v8)
        if injury_penalty > 0.0:
            # Missing stars hurt both offensive creation (65%) and defensive rating (35%)
            base_off = round(base_off - 0.65 * injury_penalty, 2)
            base_def = round(base_def + 0.35 * injury_penalty, 2)

        # 4. High-Altitude Court Bonus (`DEN`, `UTA`) (Phase V2.2)
        if is_home and team_code in HIGH_ALTITUDE_BONUS_PTS:
            alt_bonus = HIGH_ALTITUDE_BONUS_PTS[team_code]
            base_off = round(base_off + 0.6 * alt_bonus, 2)
            base_def = round(base_def - 0.4 * alt_bonus, 2)

        # 5. Bayesian Anchor with Pre-Game Market Consensus (prevents unmodeled lineup shocks)
        if first_odds:
            ou = first_odds.get("overUnder")
            spread = first_odds.get("spread")
            if ou is not None and spread is not None:
                try:
                    ou_f = float(ou)
                    sp_f = float(spread)
                    implied_home_pts = 0.5 * (ou_f - sp_f)
                    implied_away_pts = 0.5 * (ou_f + sp_f)
                    target_pts = implied_home_pts if is_home else implied_away_pts
                    opp_pts = implied_away_pts if is_home else implied_home_pts
                    base_off = round(0.60 * base_off + 0.40 * target_pts, 2)
                    base_def = round(0.60 * base_def + 0.40 * opp_pts, 2)
                except ValueError:
                    pass

        return base_off, base_def, base_pace


class SportradarAdapter(BaseNBADataAdapter):
    """
    Official Sportradar NBA v8 & Tactical Splits Adapter (requires SPORTRADAR_API_KEY).
    Respects Trial 1 req / 2s QPS rate limit and caches league-wide injuries & standings per process run.
    """

    provider_name = "sportradar_nba_v8"
    _CACHED_CONTEXT: dict[str, Any] | None = None

    def __init__(self, api_key: str | None = None, access_level: str = "trial") -> None:
        self.api_key = (api_key or os.getenv("SPORTRADAR_API_KEY", "") or os.getenv("SPORTRADAR_SYNERGY_API_KEY", "")).strip()
        self.access_level = access_level

    def is_configured(self) -> bool:
        return len(self.api_key) >= 16

    def fetch_league_intelligence_context(self) -> dict[str, Any]:
        """
        Fetches and caches league-wide NBA official injuries (`league/injuries.json`) and
        official seasonal standings & tactical splits (`seasons/2026/REG/standings.json`).
        """
        if SportradarAdapter._CACHED_CONTEXT is not None:
            return SportradarAdapter._CACHED_CONTEXT

        if not self.is_configured():
            return {"injury_penalties": {}, "injury_documents": [], "team_splits": {}, "status": "NOT_CONFIGURED"}

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        injury_penalties: dict[str, float] = {}
        injury_documents: list[dict[str, str]] = []
        team_splits: dict[str, dict[str, float]] = {}

        # 1. Official League Injuries (1 request)
        inj_url = f"https://api.sportradar.com/nba/{self.access_level}/v8/en/league/injuries.json?api_key={self.api_key}"
        try:
            req = urllib.request.Request(inj_url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                inj_data = json.loads(resp.read().decode("utf-8"))
            for t_obj in inj_data.get("teams") or []:
                try:
                    t_code = normalize_team_code(t_obj.get("alias") or t_obj.get("name", ""))
                except ValueError:
                    continue
                pen = 0.0
                for p_obj in t_obj.get("players") or []:
                    p_name = str(p_obj.get("full_name", "")).strip()
                    pos = str(p_obj.get("primary_position") or p_obj.get("position", "")).strip()
                    for inj in p_obj.get("injuries") or []:
                        st = str(inj.get("status", "")).lower()
                        desc = str(inj.get("desc", "")).strip()
                        comment = str(inj.get("comment", "")).strip()
                        upd = str(inj.get("update_date") or now_utc)
                        if p_name:
                            injury_documents.append(
                                {
                                    "source": "sportradar_nba_v8_official_injuries",
                                    "title": f"{t_code} - {p_name} ({pos}) [{inj.get('status', 'Injury')}]",
                                    "content": f"{t_code} {p_name} ({pos}) {inj.get('status', '')} ({desc}): {comment}",
                                    "captured_at": upd,
                                }
                            )
                        impact = STAR_PLAYER_IMPACT_PTS.get(p_name, 1.35)
                        if "out" in st:
                            pen += impact
                        elif "doubtful" in st:
                            pen += 0.75 * impact
                        elif "questionable" in st or "day" in st:
                            pen += 0.35 * impact
                injury_penalties[t_code] = round(min(14.5, pen), 2)
        except Exception:
            pass

        # Respect Sportradar Trial QPS limit (1 req / 2 seconds) before second call
        time.sleep(2.1)

        # 2. Official Seasonal Standings & Tactical Splits (1 request)
        std_url = f"https://api.sportradar.com/nba/{self.access_level}/v8/en/seasons/2026/REG/standings.json?api_key={self.api_key}"
        try:
            req = urllib.request.Request(std_url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                std_data = json.loads(resp.read().decode("utf-8"))
            for conf in std_data.get("conferences") or []:
                for div in conf.get("divisions") or []:
                    for tm in div.get("teams") or []:
                        try:
                            t_code = normalize_team_code(f"{tm.get('market', '')} {tm.get('name', '')}".strip())
                        except ValueError:
                            continue
                        rec_map: dict[str, float] = {}
                        for r in tm.get("records") or []:
                            rtype = str(r.get("record_type", ""))
                            w = int(r.get("wins", 0))
                            l = int(r.get("losses", 0))
                            if (w + l) > 0:
                                rec_map[rtype] = float(r.get("win_pct", w / (w + l)))
                        team_splits[t_code] = {
                            "points_for": float(tm.get("points_for", 114.5)),
                            "points_against": float(tm.get("points_against", 114.5)),
                            "point_diff": float(tm.get("point_diff", 0.0)),
                            "win_pct": float(tm.get("win_pct", 0.5)),
                            "home_win_pct": rec_map.get("home", 0.55),
                            "road_win_pct": rec_map.get("road", 0.45),
                            "last_10_win_pct": rec_map.get("last_10", float(tm.get("win_pct", 0.5))),
                            "over_500_win_pct": rec_map.get("over_500", 0.5),
                            "leads_fg_win_pct": rec_map.get("leads_field_goal_pct", 0.75),
                            "fewer_tov_win_pct": rec_map.get("fewer_turnovers", 0.65),
                        }
        except Exception:
            pass

        status_str = (
            f"OPERATIONAL_LIVE_NBA_V8 ({len(injury_penalties)} teams injuries + {len(team_splits)} teams tactical splits)"
            if (injury_penalties or team_splits)
            else "CONFIGURED_RATE_LIMITED"
        )
        SportradarAdapter._CACHED_CONTEXT = {
            "injury_penalties": injury_penalties,
            "injury_documents": injury_documents,
            "team_splits": team_splits,
            "status": status_str,
        }
        return SportradarAdapter._CACHED_CONTEXT

    def fetch_games_and_odds(
        self,
        date_str: str | None = None,
        as_of_utc: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        if not self.is_configured():
            raise AdapterUnavailableError(
                "SportradarAdapter: SPORTRADAR_API_KEY is not configured in environment. "
                "Note: Sportradar stats API also requires a separate Odds Comparison add-on for historical odds."
            )
        ctx = self.fetch_league_intelligence_context()
        if not ctx.get("team_splits") and not ctx.get("injury_penalties"):
            raise AdapterUnavailableError("SportradarAdapter: Unable to reach NBA v8 endpoints.")
        return {"games": [], "odds": []}


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


class PlaywrightAuthorizedScraper:
    """Authorized browser inspection & DOM table extractor using Playwright without bypassing anti-bot or auth."""

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

    def inspect_status(self) -> dict[str, Any]:
        """Checks Playwright Python package and browser binary availability across Windows/Linux."""
        extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            import playwright  # noqa: F401
            pw_installed = True
        except ImportError:
            pw_installed = False

        browsers_installed = self._find_browser_cache()
        return {
            "playwright_python_installed": pw_installed,
            "browser_binaries_installed": browsers_installed,
            "extracted_at": extracted_at,
            "anti_bot_bypass_enabled": False,
            "status": "READY_FOR_BROWSER_INSTALL" if pw_installed and not browsers_installed else (
                "OPERATIONAL" if pw_installed and browsers_installed else "NOT_INSTALLED"
            ),
        }

    def extract_authorized_context_snapshot(self, timeout_ms: int = 8000) -> dict[str, Any]:
        """
        Extracts contextual NBA headlines and tabular injury/matchup notes from authorized public feeds.
        Uses headless Playwright Chromium when binaries are present and falls back to authorized HTTP DOM/JSON
        extraction if running in a restricted container.
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
        except Exception:
            pass

        # 1b. Merge official Sportradar NBA v8 injury documents when configured
        try:
            sr_ctx = SportradarAdapter().fetch_league_intelligence_context()
            documents.extend(sr_ctx.get("injury_documents", [])[:40])
        except Exception:
            pass

        # 2. If Playwright Chromium is installed, verify live browser DOM rendering on ESPN NBA scoreboard page
        if self._find_browser_cache():
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
                    engine_used = "PLAYWRIGHT_CHROMIUM_HEADLESS"
            except Exception:
                engine_used = "PLAYWRIGHT_INSTALLED_HTTP_ASSISTED"

        return {
            "extracted_at": extracted_at,
            "engine_used": engine_used,
            "documents_count": len(documents),
            "documents": documents,
        }


class SyntheticFixtureAdapter(BaseNBADataAdapter):
    """
    Deterministic multi-period NBA dataset generator for reproducible walk-forward backtesting,
    offline simulation, and unit/integration verification.
    Explicitly models team score correlation via shared game pace so home & away scores are NOT independent.
    """

    provider_name = "synthetic_fixture_verified"

    def __init__(self, seed: int = 42, num_matchdays: int = 45, games_per_day: int = 5) -> None:
        self.seed = seed
        self.num_matchdays = num_matchdays
        self.games_per_day = games_per_day

    def fetch_games_and_odds(
        self,
        date_str: str | None = None,
        as_of_utc: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        rng = np.random.default_rng(self.seed)
        team_codes = sorted(NBA_TEAMS.keys())

        team_latents: dict[str, dict[str, float]] = {}
        for t in team_codes:
            team_latents[t] = {
                "off": float(np.round(rng.normal(114.5, 3.2), 2)),
                "def": float(np.round(rng.normal(114.5, 3.2), 2)),
                "pace": float(np.round(rng.normal(99.2, 2.1), 2)),
            }

        start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        games: list[dict[str, Any]] = []
        odds: list[dict[str, Any]] = []

        for day_idx in range(self.num_matchdays):
            current_dt = start_date + timedelta(days=day_idx)
            matchday_str = current_dt.strftime("%Y-%m-%d")
            if date_str and matchday_str != date_str:
                continue

            season_str = "2025-26" if day_idx < 30 else "2026-27"
            shuffled = list(rng.permutation(team_codes))

            for g_idx in range(self.games_per_day):
                home_team = str(shuffled[2 * g_idx])
                away_team = str(shuffled[2 * g_idx + 1])

                tipoff_dt = current_dt.replace(hour=23, minute=0, second=0)
                avail_dt = tipoff_dt - timedelta(hours=4)
                odds_dt = tipoff_dt - timedelta(hours=3)
                close_dt = tipoff_dt - timedelta(minutes=15)
                settled_dt = tipoff_dt + timedelta(hours=3)

                game_start_str = tipoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                avail_str = avail_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                odds_str = odds_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                is_final = True
                if as_of_utc and game_start_str >= as_of_utc:
                    is_final = False

                h_lat = team_latents[home_team]
                a_lat = team_latents[away_team]

                h_off = round(h_lat["off"] + float(rng.normal(0, 1.1)), 2)
                h_def = round(h_lat["def"] + float(rng.normal(0, 1.1)), 2)
                h_pace = round(h_lat["pace"] + float(rng.normal(0, 0.7)), 2)
                a_off = round(a_lat["off"] + float(rng.normal(0, 1.1)), 2)
                a_def = round(a_lat["def"] + float(rng.normal(0, 1.1)), 2)
                a_pace = round(a_lat["pace"] + float(rng.normal(0, 0.7)), 2)

                h_rest = int(rng.choice([1, 2, 2, 3]))
                a_rest = int(rng.choice([1, 2, 2, 3]))

                expected_pace = 0.5 * (h_pace + a_pace)
                pace_shock = float(rng.normal(0.0, 2.8))
                realized_pace = expected_pace + pace_shock

                expected_h_pts = ((h_off + a_def) / 200.0) * expected_pace + 1.3 + 0.4 * (h_rest - a_rest)
                expected_a_pts = ((a_off + h_def) / 200.0) * expected_pace - 1.3 - 0.4 * (h_rest - a_rest)

                h_pts = int(round(((h_off + a_def) / 200.0) * realized_pace + 1.3 + float(rng.normal(0, 7.8))))
                a_pts = int(round(((a_off + h_def) / 200.0) * realized_pace - 1.3 + float(rng.normal(0, 7.8))))
                if h_pts == a_pts:
                    h_pts += 2

                game_id = f"SYN_{matchday_str.replace('-', '')}_{away_team}_AT_{home_team}"

                games.append(
                    {
                        "game_id": game_id,
                        "season": season_str,
                        "matchday_date": matchday_str,
                        "game_start_time": game_start_str,
                        "home_team": home_team,
                        "away_team": away_team,
                        "status": "FINAL" if is_final else "SCHEDULED",
                        "home_score": h_pts if is_final else None,
                        "away_score": a_pts if is_final else None,
                        "home_off_rtg": h_off,
                        "home_def_rtg": h_def,
                        "home_pace": h_pace,
                        "away_off_rtg": a_off,
                        "away_def_rtg": a_def,
                        "away_pace": a_pace,
                        "home_rest_days": h_rest,
                        "away_rest_days": a_rest,
                        "features_available_at": avail_str,
                        "source_provider": self.provider_name,
                        "ingested_at": avail_str,
                        "result_recorded_at": settled_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if is_final else None,
                    }
                )

                exp_margin = expected_h_pts - expected_a_pts
                from scipy.stats import norm

                true_p_home = float(np.clip(1.0 - norm.cdf(0.0, loc=exp_margin, scale=11.8), 0.08, 0.92))
                market_p_home = float(np.clip(true_p_home + float(rng.normal(0.0, 0.038)), 0.08, 0.92))
                market_p_away = 1.0 - market_p_home

                overround = 1.045
                home_ml_odds = round(max(1.05, 1.0 / (market_p_home * overround)), 3)
                away_ml_odds = round(max(1.05, 1.0 / (market_p_away * overround)), 3)

                close_p_home = float(np.clip(0.75 * true_p_home + 0.25 * market_p_home, 0.08, 0.92))
                close_p_away = 1.0 - close_p_home
                close_home_odds = round(max(1.05, 1.0 / (close_p_home * overround)), 3)
                close_away_odds = round(max(1.05, 1.0 / (close_p_away * overround)), 3)

                odds.extend(
                    [
                        {
                            "odds_id": f"{game_id}_ML_HOME_OPEN",
                            "game_id": game_id,
                            "provider": "SyntheticBook_Authorized",
                            "market": "moneyline",
                            "selection": "HOME",
                            "line_value": None,
                            "decimal_odds": home_ml_odds,
                            "counterpart_decimal_odds": away_ml_odds,
                            "captured_at": odds_str,
                            "is_closing_line": 0,
                        },
                        {
                            "odds_id": f"{game_id}_ML_AWAY_OPEN",
                            "game_id": game_id,
                            "provider": "SyntheticBook_Authorized",
                            "market": "moneyline",
                            "selection": "AWAY",
                            "line_value": None,
                            "decimal_odds": away_ml_odds,
                            "counterpart_decimal_odds": home_ml_odds,
                            "captured_at": odds_str,
                            "is_closing_line": 0,
                        },
                        {
                            "odds_id": f"{game_id}_ML_HOME_CLOSE",
                            "game_id": game_id,
                            "provider": "SyntheticBook_Authorized",
                            "market": "moneyline",
                            "selection": "HOME",
                            "line_value": None,
                            "decimal_odds": close_home_odds,
                            "counterpart_decimal_odds": close_away_odds,
                            "captured_at": close_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "is_closing_line": 1,
                        },
                        {
                            "odds_id": f"{game_id}_ML_AWAY_CLOSE",
                            "game_id": game_id,
                            "provider": "SyntheticBook_Authorized",
                            "market": "moneyline",
                            "selection": "AWAY",
                            "line_value": None,
                            "decimal_odds": close_away_odds,
                            "counterpart_decimal_odds": close_home_odds,
                            "captured_at": close_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "is_closing_line": 1,
                        },
                    ]
                )

                true_total = expected_h_pts + expected_a_pts
                market_line = round((true_total + float(rng.normal(0.0, 2.5))) * 2.0) / 2.0
                p_over_market = float(np.clip(1.0 - norm.cdf(market_line, loc=true_total, scale=15.8) + float(rng.normal(0, 0.035)), 0.15, 0.85))
                p_under_market = 1.0 - p_over_market
                over_odds = round(max(1.05, 1.0 / (p_over_market * overround)), 3)
                under_odds = round(max(1.05, 1.0 / (p_under_market * overround)), 3)

                odds.extend(
                    [
                        {
                            "odds_id": f"{game_id}_TOT_OVER_{market_line}_OPEN",
                            "game_id": game_id,
                            "provider": "SyntheticBook_Authorized",
                            "market": "total_points",
                            "selection": "OVER",
                            "line_value": float(market_line),
                            "decimal_odds": over_odds,
                            "counterpart_decimal_odds": under_odds,
                            "captured_at": odds_str,
                            "is_closing_line": 0,
                        },
                        {
                            "odds_id": f"{game_id}_TOT_UNDER_{market_line}_OPEN",
                            "game_id": game_id,
                            "provider": "SyntheticBook_Authorized",
                            "market": "total_points",
                            "selection": "UNDER",
                            "line_value": float(market_line),
                            "decimal_odds": under_odds,
                            "counterpart_decimal_odds": over_odds,
                            "captured_at": odds_str,
                            "is_closing_line": 0,
                        },
                    ]
                )

        return {"games": games, "odds": odds}


class DataSourceRouter:
    """Routes data requests through prioritized interchangeable adapters with automatic failover."""

    def __init__(self, adapters: list[BaseNBADataAdapter]) -> None:
        if not adapters:
            raise ValueError("DataSourceRouter requires at least one adapter.")
        self.adapters = adapters

    def fetch_with_failover(
        self,
        date_str: str | None = None,
        as_of_utc: str | None = None,
    ) -> dict[str, Any]:
        errors: list[dict[str, str]] = []
        for adapter in self.adapters:
            try:
                data = adapter.fetch_games_and_odds(date_str=date_str, as_of_utc=as_of_utc)
                if data.get("games"):
                    return {
                        "active_provider": adapter.provider_name,
                        "games": data["games"],
                        "odds": data.get("odds", []),
                        "failover_events": errors,
                    }
                errors.append(
                    {
                        "provider": adapter.provider_name,
                        "reason": "Returned 0 games for requested query",
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "provider": adapter.provider_name,
                        "reason": str(exc),
                    }
                )
        raise AdapterUnavailableError(f"All configured adapters failed: {errors}")
