"""
ESPN Public NBA API Adapter (`src/ingestion/espn.py`).
V2 Structured Adapter for ESPN's public NBA API + optional TheOddsAPI multi-bookmaker enrichment:
- Real-time injury report extraction & star player point-spread penalty (`summary?event=...`)
- Four Factors boxscore extraction (`avgPoints`, `avgPointsAgainst`, `FG%`, `3P%`, `TOV`),
  real schedule rest days (`Back-to-Back` detection) and high-altitude adjustment (`DEN`, `UTA`)
- Automatically merges multi-bookmaker Line Shopping odds from `TheOddsAPIAdapter` when configured.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
from typing import Any
import urllib.request

from src.features.team_ratings import compute_lineup_synergy_penalty
from src.ingestion.base import AdapterUnavailableError, BaseNBADataAdapter
from src.ingestion.context_constants import (
    HIGH_ALTITUDE_BONUS_PTS,
    LONG_TERM_INJURY_KEYWORDS,
    NBA_REFEREE_CREW_PROFILE,
    STAR_PLAYER_IMPACT_PTS,
)
from src.ingestion.normalizer import (
    american_to_decimal_odds,
    normalize_season,
    normalize_team_code,
)
from src.ingestion.sportradar import SportradarAdapter
from src.ingestion.the_odds_api import TheOddsAPIAdapter
from src.validation.validator import IN_PROGRESS_STATUS, parse_iso_utc

logger = logging.getLogger(__name__)


# ESPN has published the same DraftKings feed as "DraftKings" and "Draft Kings"; two labels made the
# consensus count one book twice and split its quote history.
_PROVIDER_ALIASES: dict[str, str] = {"draft kings": "DraftKings"}

# ESPN status types of a game that is under way (any `in` state is treated the same way).
_ESPN_LIVE_STATUS_NAMES: frozenset[str] = frozenset(
    {
        "STATUS_IN_PROGRESS",
        "STATUS_HALFTIME",
        "STATUS_END_PERIOD",
        "STATUS_END_OF_PERIOD",
        "STATUS_OVERTIME",
    }
)


def canonical_provider_name(name: str) -> str:
    """Maps known aliases of a book to one label (new rows only; stored history is never rewritten)."""
    return _PROVIDER_ALIASES.get(" ".join(name.split()).lower(), name)


def map_espn_status(status_obj: dict[str, Any] | None) -> str:
    """
    Maps an ESPN competition status to the system's game status.

    - Final, postponed and cancelled games are results (ESPN spells the last one `STATUS_CANCELED`).
    - In progress, halftime and end of period (or any `in` state) map to `IN_PROGRESS`: a non-bettable,
      feed-only status that ingestion never stores, so a game under way can never look `SCHEDULED`.
    - Only a pre-game status maps to `SCHEDULED`. Any other status reported for an event that is not
      pre-game (e.g. forfeit, abandoned) is treated as `IN_PROGRESS` as well. A missing status keeps the
      historical default (`SCHEDULED`); ingestion still checks tip-off before storing anything.
    """
    type_obj = (status_obj or {}).get("type") or {}
    name = str(type_obj.get("name") or "").strip().upper()
    state = str(type_obj.get("state") or "").strip().lower()
    if "POSTPONED" in name:
        return "POSTPONED"
    if "CANCEL" in name:
        return "CANCELLED"
    if "FINAL" in name:
        return "FINAL"
    if name in _ESPN_LIVE_STATUS_NAMES or state in ("in", "post"):
        return IN_PROGRESS_STATUS
    if state == "pre" or name in ("", "STATUS_SCHEDULED"):
        return "SCHEDULED"
    return IN_PROGRESS_STATUS


def _has_upcoming_events(payload: dict[str, Any], now_utc: str) -> bool:
    """Returns True only when the ESPN scoreboard payload contains at least one non-completed pre-tipoff event."""
    for event in payload.get("events", []):
        comp = (event.get("competitions") or [{}])[0]
        state = str(((comp.get("status") or {}).get("type") or {}).get("state") or "").strip().lower()
        if state == "post":
            continue
        raw_date = str(event.get("date") or "")
        start_time = (raw_date[:-1] + ":00Z") if (len(raw_date) == 17 and raw_date.endswith("Z")) else raw_date
        if state == "pre" or (start_time and start_time > now_utc):
            return True
    return False


class ESPNPublicAdapter(BaseNBADataAdapter):
    """
    V2 Structured Adapter for ESPN's public NBA API + optional TheOddsAPI multi-bookmaker enrichment.
    """

    provider_name = "espn_v2_syndicate_enriched"

    def __init__(self, timeout_seconds: int = 8, enrich_with_the_odds_api: bool = True) -> None:
        self.timeout_seconds = timeout_seconds
        self.enrich_with_the_odds_api = enrich_with_the_odds_api
        self.odds_api_helper = TheOddsAPIAdapter(timeout_seconds=timeout_seconds)

    def _compute_team_rest_days(self, team_code: str, game_date_str: str) -> int:
        """
        Computes dynamic calendar rest days from the team's most recent previous game date in the database.
        Returns (current_game_date - prev_game_date).days - 1, bounded between 0 and 7.
        Defaults to 3 (standard rested team) when no previous game exists in the database.
        """
        try:
            import sqlite3
            db_path = Path("data/nba_intelligence.sqlite3")
            if not db_path.exists():
                db_path = Path(__file__).resolve().parent.parent.parent / "data" / "nba_intelligence.sqlite3"
            if db_path.exists():
                with sqlite3.connect(str(db_path), timeout=30.0) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        SELECT matchday_date FROM games
                        WHERE (home_team = ? OR away_team = ?)
                          AND matchday_date < ?
                        ORDER BY matchday_date DESC LIMIT 1
                        """,
                        (team_code, team_code, game_date_str),
                    )
                    r = cur.fetchone()
                    if r and r[0]:
                        prev_d = datetime.strptime(r[0], "%Y-%m-%d").date()
                        curr_d = datetime.strptime(game_date_str, "%Y-%m-%d").date()
                        diff = (curr_d - prev_d).days - 1
                        return max(0, min(7, diff))
        except Exception as exc:
            logger.debug(f"Could not compute dynamic rest days for {team_code}: {exc}")
        return 3

    def _fetch_event_summary_context(self, event_id: str) -> dict[str, Any]:
        """Fetches live pre-game injury report (with adaptation decay), referee crew, and Four Factors boxscore."""
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return {
                "fetch_ok": False,
                "injury_penalties": {},
                "injury_reports": {},
                "team_box_stats": {},
                "referee_total_adj": 0.0,
                "referee_hca_adj": 0.0,
            }

        injury_penalties: dict[str, float] = {}
        injury_reports: dict[str, list[dict[str, Any]]] = {}
        lineup_synergy_details: dict[str, dict[str, float]] = {}
        for t_inj in data.get("injuries") or []:
            raw_abbr = t_inj.get("team", {}).get("abbreviation", "")
            try:
                t_code = normalize_team_code(raw_abbr)
            except ValueError:
                continue
            absent_list: list[dict[str, Any]] = []
            for inj in t_inj.get("injuries") or []:
                athlete = inj.get("athlete") or {}
                player_name = athlete.get("displayName", "")
                pos_abbr = (athlete.get("position") or {}).get("abbreviation", "")
                status = str(inj.get("status", "")).lower()
                comment_blob = " ".join(
                    str(inj.get(k) or "") for k in ("shortComment", "longComment", "type")
                ).lower()
                details_blob = str((inj.get("details") or {}).get("detail") or "").lower()
                full_text = f"{comment_blob} {details_blob}"
                adapt_factor = 0.55 if any(kw in full_text for kw in LONG_TERM_INJURY_KEYWORDS) else 1.00
                absent_list.append(
                    {
                        "name": player_name,
                        "status": status,
                        "position": pos_abbr,
                        "adapt_factor": adapt_factor,
                        "default_impact": STAR_PLAYER_IMPACT_PTS.get(player_name, 0.35),
                        "baseline_deduction": 1.0,
                    }
                )
            syn_res = compute_lineup_synergy_penalty(absent_list)
            injury_penalties[t_code] = syn_res["total_net_penalty"]
            injury_reports[t_code] = [dict(item, team=t_code) for item in absent_list]
            lineup_synergy_details[t_code] = syn_res

        ref_total_adj = 0.0
        ref_hca_adj = 0.0
        for off in (data.get("gameInfo") or {}).get("officials") or []:
            ref_name = str(off.get("displayName") or off.get("fullName") or "").strip()
            if ref_name in NBA_REFEREE_CREW_PROFILE:
                t_d, h_d = NBA_REFEREE_CREW_PROFILE[ref_name]
                ref_total_adj += t_d
                ref_hca_adj += h_d
        ref_total_adj = round(max(-3.5, min(3.5, ref_total_adj)), 2)
        ref_hca_adj = round(max(-1.2, min(1.2, ref_hca_adj)), 2)

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
            "fetch_ok": True,
            "injury_penalties": injury_penalties,
            "injury_reports": injury_reports,
            "lineup_synergy_details": lineup_synergy_details,
            "team_box_stats": team_box_stats,
            "referee_total_adj": ref_total_adj,
            "referee_hca_adj": ref_hca_adj,
        }

    get_event_summary_context = _fetch_event_summary_context

    def fetch_player_boxscores(self, event_id: str) -> dict[str, dict[str, float]]:
        """
        Fetches individual player boxscore statistics from ESPN game summary.
        Returns a dict mapping canonical/display player names to their stats.
        """
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}"
        player_stats: dict[str, dict[str, float]] = {}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return player_stats

        for p_team in data.get("boxscore", {}).get("players") or []:
            for stat_cat in p_team.get("statistics") or []:
                labels = [str(lbl).upper() for lbl in stat_cat.get("labels") or []]
                for ath in stat_cat.get("athletes") or []:
                    ath_name = (ath.get("athlete") or {}).get("displayName")
                    if not ath_name:
                        continue
                    stats_vals = ath.get("stats") or []
                    val_map: dict[str, float] = {}
                    for lbl, val_str in zip(labels, stats_vals, strict=False):
                        try:
                            if lbl in ("3PT", "3PM") and "-" in str(val_str):
                                val_map["3PM"] = float(str(val_str).split("-")[0])
                            elif lbl in ("FG", "FGM-A") and "-" in str(val_str):
                                val_map["FGM"] = float(str(val_str).split("-")[0])
                            elif lbl in ("FT", "FTM-A") and "-" in str(val_str):
                                val_map["FTM"] = float(str(val_str).split("-")[0])
                            else:
                                val_map[lbl] = float(val_str)
                        except (ValueError, TypeError):
                            pass
                    pts = val_map.get("PTS", 0.0)
                    reb = val_map.get("REB", 0.0)
                    ast = val_map.get("AST", 0.0)
                    threedm = val_map.get("3PM", val_map.get("3PT", 0.0))
                    val_map["PTS"] = pts
                    val_map["REB"] = reb
                    val_map["AST"] = ast
                    val_map["3PM"] = threedm
                    val_map["PRA"] = pts + reb + ast
                    val_map["PR"] = pts + reb
                    val_map["PA"] = pts + ast
                    val_map["RA"] = reb + ast
                    player_stats[ath_name] = val_map
        return player_stats

    def fetch_games_and_odds(
        self,
        date_str: str | None = None,
        as_of_utc: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        now_utc = as_of_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            now_dt: datetime | None = parse_iso_utc(now_utc)
        except Exception:
            now_dt = None  # unknown fetch time: no quote can be shown to precede tip-off, none is emitted
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
        if (
            self.enrich_with_the_odds_api
            and self.odds_api_helper.is_configured()
            and _has_upcoming_events(payload, now_utc)
        ):
            multi_book_odds = self.odds_api_helper.fetch_multi_book_odds_by_matchup(now_utc)

        if as_of_utc is None:
            # Stamp (and check tip-off against) the moment the responses arrived, not the call entry: a
            # request started just before tip-off can return in-game prices after it.
            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            now_dt = parse_iso_utc(now_utc)

        # Sportradar v8 standings and injuries are wall-clock snapshots (no as-of query), so they describe the
        # league NOW: they are only fetched on a live run with an upcoming game, and only applied below to games
        # that have not started. A replay (`as_of_utc`) or a past/started game never receives today's context.
        sr_injuries: dict[str, float] = {}
        sr_splits: dict[str, dict[str, Any]] = {}
        if as_of_utc is None and _has_upcoming_events(payload, now_utc):
            sr_context = SportradarAdapter().fetch_league_intelligence_context()
            sr_injuries = sr_context.get("injury_penalties", {}) or {}
            sr_splits = sr_context.get("team_splits", {}) or {}

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
            status = map_espn_status(comp.get("status"))
            game_id = f"ESPN_{ev_id}_{matchday_date}_{away_code}_AT_{home_code}"

            start_dt_val: datetime | None = None
            try:
                start_dt_val = parse_iso_utc(game_start_time) if game_start_time else None
            except Exception:
                start_dt_val = None

            if status == IN_PROGRESS_STATUS:
                # A game under way: nothing computed now is pre-game information, so no summary or box
                # score is fetched and no quote is emitted. Ingestion keeps the stored pre-game row as is.
                games_out.append(
                    {
                        "game_id": game_id,
                        "season": season_label,
                        "matchday_date": matchday_date,
                        "game_start_time": game_start_time,
                        "home_team": home_code,
                        "away_team": away_code,
                        "status": status,
                        "home_score": None,
                        "away_score": None,
                        "features_available_at": now_utc,
                        "source_provider": self.provider_name,
                        "ingested_at": now_utc,
                        "result_recorded_at": None,
                    }
                )
                continue

            home_score = None
            away_score = None
            if status == "FINAL":
                try:
                    home_score = int(home_comp.get("score", 0))
                    away_score = int(away_comp.get("score", 0))
                except (ValueError, TypeError):
                    pass

            ctx = self._fetch_event_summary_context(ev_id)
            inj_penalties = ctx["injury_penalties"]
            ref_total_adj = ctx["referee_total_adj"]
            ref_hca_adj = ctx["referee_hca_adj"]
            team_box_stats = ctx["team_box_stats"]
            lineup_synergy = ctx.get("lineup_synergy_details", {})

            h_inj = max(inj_penalties.get(home_code, 0.0), sr_injuries.get(home_code, 0.0))
            a_inj = max(inj_penalties.get(away_code, 0.0), sr_injuries.get(away_code, 0.0))
            h_box = team_box_stats.get(home_code)
            a_box = team_box_stats.get(away_code)
            pregame_now = (
                status == "SCHEDULED" and start_dt_val is not None and now_dt is not None and now_dt < start_dt_val
            )
            if not pregame_now:
                # Wall-clock Sportradar context never describes a game that has already started.
                h_inj = inj_penalties.get(home_code, 0.0)
                a_inj = inj_penalties.get(away_code, 0.0)
            h_sr = sr_splits.get(home_code) if pregame_now else None
            a_sr = sr_splits.get(away_code) if pregame_now else None
            h_syn = lineup_synergy.get(home_code)
            a_syn = lineup_synergy.get(away_code)

            raw_odds_list = comp.get("odds") or []
            first_odds = raw_odds_list[0] if raw_odds_list else None

            h_off, h_def, h_pace = self._estimate_pregame_team_profile(
                home_code,
                home_comp,
                first_odds,
                is_home=True,
                injury_penalty=h_inj,
                opp_injury_penalty=a_inj,
                box_stats=h_box,
                sr_split=h_sr,
                referee_total_adj=ref_total_adj,
                referee_hca_adj=ref_hca_adj,
                synergy_detail=h_syn,
            )
            a_off, a_def, a_pace = self._estimate_pregame_team_profile(
                away_code,
                away_comp,
                first_odds,
                is_home=False,
                injury_penalty=a_inj,
                opp_injury_penalty=h_inj,
                box_stats=a_box,
                sr_split=a_sr,
                referee_total_adj=ref_total_adj,
                referee_hca_adj=ref_hca_adj,
                synergy_detail=a_syn,
            )

            h_rest = self._compute_team_rest_days(home_code, matchday_date)
            a_rest = self._compute_team_rest_days(away_code, matchday_date)

            # The feature snapshot is computed now, so it is available from the ingestion time on. A game
            # first seen after tip-off therefore carries a post-tip availability and can never pass as a
            # pre-game snapshot (the former "tip-off − 2 h" stamp claimed a time before the real capture).
            feat_avail = now_utc

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
                    "home_off_rtg": h_off,
                    "home_def_rtg": h_def,
                    "home_pace": h_pace,
                    "away_off_rtg": a_off,
                    "away_def_rtg": a_def,
                    "away_pace": a_pace,
                    "home_rest_days": h_rest,
                    "away_rest_days": a_rest,
                    "features_available_at": feat_avail,
                    "source_provider": self.provider_name,
                    "ingested_at": now_utc,
                    "result_recorded_at": (now_utc if status == "FINAL" else None),
                }
            )

            # Quotes are only emitted for a game that has not started, stamped with the moment they were
            # fetched. A quote fetched at or after tip-off (or for a game that is not pre-game) is dropped,
            # never stamped with an earlier time (the former "tip-off − 15 min" stamp backdated in-game prices).
            if status != "SCHEDULED" or start_dt_val is None or now_dt is None or now_dt >= start_dt_val:
                continue
            odds_captured_at = now_utc

            lookup_key = (matchday_date, away_code, home_code)
            if lookup_key in multi_book_odds:
                for scraped_quote in multi_book_odds[lookup_key]:
                    m_type = scraped_quote["market"]
                    sel_code = scraped_quote["selection"]
                    line_v = scraped_quote.get("line_value")
                    p_name = scraped_quote.get("provider", "TheOddsAPI_LineShop")
                    tag_v = f"{line_v:.1f}" if line_v is not None else "ML"
                    # A quote served from TheOddsAPI's in-process TTL cache was observed by an earlier HTTP fetch:
                    # it keeps that fetch's time as both capture and fetch moment (never re-stamped as newer).
                    from_cache = bool(scraped_quote.get("from_ttl_cache"))
                    q_captured = str(scraped_quote.get("captured_at") or odds_captured_at) if from_cache else odds_captured_at
                    q_fetched = q_captured if from_cache else now_utc
                    try:
                        if parse_iso_utc(q_captured) >= start_dt_val:
                            continue
                    except Exception:
                        continue
                    quote_row: dict[str, Any] = {
                        "odds_id": f"{game_id}_{m_type}_{sel_code}_{tag_v}_{p_name[:12].replace(' ', '_')}_{q_captured[:16]}",
                        "game_id": game_id,
                        "provider": p_name,
                        "market": m_type,
                        "selection": sel_code,
                        "line_value": line_v,
                        "decimal_odds": scraped_quote["decimal_odds"],
                        "counterpart_decimal_odds": scraped_quote.get("counterpart_decimal_odds"),
                        "captured_at": q_captured,
                        "fetched_at": q_fetched,
                        "is_closing_line": 0,
                        "source_type": scraped_quote.get("source_type", "OBSERVED"),
                    }
                    if from_cache:
                        quote_row["from_ttl_cache"] = True
                    odds_out.append(quote_row)
            else:
                for odds_entry in raw_odds_list:
                    provider_obj = odds_entry.get("provider") or {}
                    provider_name = canonical_provider_name(str(provider_obj.get("name") or "ESPN_Consensus"))
                    captured_at = odds_captured_at

                    home_ml = odds_entry.get("homeTeamOdds", {}).get("moneyLine")
                    away_ml = odds_entry.get("awayTeamOdds", {}).get("moneyLine")

                    if home_ml is not None and away_ml is not None:
                        try:
                            h_dec = american_to_decimal_odds(home_ml)
                            a_dec = american_to_decimal_odds(away_ml)
                            h_tag = str(home_ml).replace("+", "p").replace("-", "m")
                            a_tag = str(away_ml).replace("+", "p").replace("-", "m")

                            odds_out.append(
                                {
                                    "odds_id": f"{game_id}_ML_HOME_{provider_name}_{h_tag}",
                                    "game_id": game_id,
                                    "provider": provider_name,
                                    "market": "moneyline",
                                    "selection": "HOME",
                                    "line_value": None,
                                    "decimal_odds": h_dec,
                                    "counterpart_decimal_odds": a_dec,
                                    "captured_at": captured_at,
                                    "fetched_at": now_utc,
                                    "is_closing_line": 0,
                                    "source_type": "OBSERVED",
                                }
                            )
                            odds_out.append(
                                {
                                    "odds_id": f"{game_id}_ML_AWAY_{provider_name}_{a_tag}",
                                    "game_id": game_id,
                                    "provider": provider_name,
                                    "market": "moneyline",
                                    "selection": "AWAY",
                                    "line_value": None,
                                    "decimal_odds": a_dec,
                                    "counterpart_decimal_odds": h_dec,
                                    "captured_at": captured_at,
                                    "fetched_at": now_utc,
                                    "is_closing_line": 0,
                                    "source_type": "OBSERVED",
                                }
                            )
                        except ValueError:
                            pass

                    over_under = odds_entry.get("overUnder")
                    if over_under is not None:
                        try:
                            line_val = float(over_under)
                            o_odds = odds_entry.get("overOdds", -110)
                            u_odds = odds_entry.get("underOdds", -110)
                            o_dec = american_to_decimal_odds(o_odds)
                            u_dec = american_to_decimal_odds(u_odds)
                            o_tag = str(o_odds).replace("+", "p").replace("-", "m")
                            u_tag = str(u_odds).replace("+", "p").replace("-", "m")

                            odds_out.append(
                                {
                                    "odds_id": f"{game_id}_TOT_OVER_{line_val}_{provider_name}_{o_tag}",
                                    "game_id": game_id,
                                    "provider": provider_name,
                                    "market": "total_points",
                                    "selection": "OVER",
                                    "line_value": line_val,
                                    "decimal_odds": o_dec,
                                    "counterpart_decimal_odds": u_dec,
                                    "captured_at": captured_at,
                                    "fetched_at": now_utc,
                                    "is_closing_line": 0,
                                    "source_type": "OBSERVED",
                                }
                            )
                            odds_out.append(
                                {
                                    "odds_id": f"{game_id}_TOT_UNDER_{line_val}_{provider_name}_{u_tag}",
                                    "game_id": game_id,
                                    "provider": provider_name,
                                    "market": "total_points",
                                    "selection": "UNDER",
                                    "line_value": line_val,
                                    "decimal_odds": u_dec,
                                    "counterpart_decimal_odds": o_dec,
                                    "captured_at": captured_at,
                                    "fetched_at": now_utc,
                                    "is_closing_line": 0,
                                    "source_type": "OBSERVED",
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
        referee_total_adj: float = 0.0,
        referee_hca_adj: float = 0.0,
        synergy_detail: dict[str, float] | None = None,
    ) -> tuple[float, float, float]:
        """V2 Pre-game Team Profile estimation."""
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

        avg_pts = b_stats.get("avgPoints") or sr_data.get("points_for")
        avg_pts_against = b_stats.get("avgPointsAgainst") or sr_data.get("points_against")
        if avg_pts and 95.0 <= float(avg_pts) <= 138.0:
            base_off = round(0.60 * base_off + 0.40 * float(avg_pts), 2)
        if avg_pts_against and 95.0 <= float(avg_pts_against) <= 138.0:
            base_def = round(0.60 * base_def + 0.40 * float(avg_pts_against), 2)

        fg_pct = b_stats.get("fieldGoalPct", 47.0)
        tp_pct = b_stats.get("threePointFieldGoalPct", 36.0)
        tov = b_stats.get("avgTotalTurnovers", 14.0)
        orb = b_stats.get("avgOffensiveRebounds", 10.5)
        tp_dev = tp_pct - 36.0
        shrunk_tp_dev = (
            math.copysign(2.5 + 0.50 * (abs(tp_dev) - 2.5), tp_dev)
            if abs(tp_dev) > 2.5
            else tp_dev
        )
        efg_proxy = (
            (fg_pct - 47.0) * 0.24
            + shrunk_tp_dev * 0.12
            - (tov - 14.0) * 0.22
            + (orb - 10.5) * 0.14
        )
        base_off = round(base_off + efg_proxy, 2)

        if referee_total_adj != 0.0 or referee_hca_adj != 0.0:
            side_hca = 0.5 * referee_hca_adj if is_home else -0.5 * referee_hca_adj
            base_off = round(base_off + 0.25 * referee_total_adj + side_hca, 2)
            base_def = round(base_def + 0.25 * referee_total_adj - side_hca, 2)
            base_pace = round(max(92.0, min(106.0, base_pace + 0.30 * referee_total_adj)), 2)

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
            syn_diff = sr_data.get("synergy_net_diff", 0.0)
            tactical_adj = (venue_wp - 0.5) * 1.4 + (l10_wp - 0.5) * 1.0 + max(-1.5, min(1.5, syn_diff * 0.12))
            base_off = round(base_off + 0.5 * tactical_adj, 2)
            base_def = round(base_def - 0.5 * tactical_adj, 2)
            syn_pace = sr_data.get("synergy_pace_proxy")
            if syn_pace and 92.0 <= float(syn_pace) <= 106.0:
                base_pace = round(0.80 * base_pace + 0.20 * float(syn_pace), 2)

        if synergy_detail and synergy_detail.get("total_net_penalty", 0.0) >= injury_penalty:
            off_p = float(synergy_detail.get("off_rtg_penalty", 0.0))
            def_p = float(synergy_detail.get("def_rtg_penalty", 0.0))
            pace_d = float(synergy_detail.get("pace_delta", 0.0))
            base_off = round(base_off - off_p, 2)
            base_def = round(base_def + def_p, 2)
            base_pace = round(max(92.0, min(106.0, base_pace + pace_d)), 2)
        elif injury_penalty > 0.0:
            base_off = round(base_off - 0.50 * injury_penalty, 2)
            base_def = round(base_def + 0.50 * injury_penalty, 2)

        if is_home and team_code in HIGH_ALTITUDE_BONUS_PTS:
            alt_bonus = HIGH_ALTITUDE_BONUS_PTS[team_code]
            base_off = round(base_off + 0.6 * alt_bonus, 2)
            base_def = round(base_def - 0.4 * alt_bonus, 2)

        return base_off, base_def, base_pace
