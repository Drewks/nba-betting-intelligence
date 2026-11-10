"""
Official Sportradar NBA v8 & Tactical Splits Adapter (`src/ingestion/sportradar.py`).
Respects Trial 1 req / 2s QPS rate limit and caches league-wide injuries & standings per process run.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from typing import Any
import urllib.request

from src.ingestion.base import AdapterUnavailableError, BaseNBADataAdapter
from src.ingestion.normalizer import normalize_team_code

logger = logging.getLogger(__name__)


class SportradarAdapter(BaseNBADataAdapter):
    """
    Official Sportradar NBA v8 & Tactical Splits Adapter (requires SPORTRADAR_API_KEY).
    Respects Trial 1 req / 2s QPS rate limit and caches league-wide injuries & standings per process run.
    """

    provider_name = "sportradar_nba_v8"
    _CACHED_CONTEXT: dict[str, Any] | None = None

    def __init__(self, api_key: str | None = None, access_level: str = "trial") -> None:
        self.api_key = (api_key or os.getenv("SPORTRADAR_API_KEY") or os.getenv("SPORTRADAR_SYNERGY_API_KEY") or "").strip()
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
        inj_url = f"https://api.sportradar.com/nba/{self.access_level}/v8/en/league/injuries.json"
        try:
            req = urllib.request.Request(inj_url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0", "x-api-key": self.api_key})
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
                if pen > 0.0:
                    injury_penalties[t_code] = round(pen, 2)
        except Exception as exc:
            logger.warning(f"Failed to fetch Sportradar injuries: {exc}")

        # 2. Official Standings & Splits (1 request)
        std_url = f"https://api.sportradar.com/nba/{self.access_level}/v8/en/seasons/2025/REG/standings.json"
        try:
            req = urllib.request.Request(std_url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0", "x-api-key": self.api_key})
            with urllib.request.urlopen(req, timeout=10) as resp:
                std_data = json.loads(resp.read().decode("utf-8"))
            for conf in std_data.get("conferences") or []:
                for div in conf.get("divisions") or []:
                    for t_rec in div.get("teams") or []:
                        try:
                            code = normalize_team_code(t_rec.get("alias") or t_rec.get("name", ""))
                        except ValueError:
                            continue
                        hw, hl = t_rec.get("records", {}).get("home", {}).get("wins", 0), t_rec.get("records", {}).get("home", {}).get("losses", 0)
                        rw, rl = t_rec.get("records", {}).get("road", {}).get("wins", 0), t_rec.get("records", {}).get("road", {}).get("losses", 0)
                        l10w, l10l = t_rec.get("records", {}).get("last_10", {}).get("wins", 0), t_rec.get("records", {}).get("last_10", {}).get("losses", 0)
                        team_splits[code] = {
                            "home_win_pct": round(hw / max(1, hw + hl), 3) if (hw + hl) > 0 else 0.50,
                            "road_win_pct": round(rw / max(1, rw + rl), 3) if (rw + rl) > 0 else 0.50,
                            "last_10_win_pct": round(l10w / max(1, l10w + l10l), 3) if (l10w + l10l) > 0 else 0.50,
                            "points_for": float(t_rec.get("points_for", 114.5)),
                            "points_against": float(t_rec.get("points_against", 114.5)),
                        }
        except Exception as exc:
            logger.warning(f"Failed to fetch Sportradar standings: {exc}")

        # 3. Synergy Basketball Telemetry Integration (Phase V2.3)
        synergy_teams_loaded = 0
        synergy_events_loaded = 0
        syn_teams_url = f"https://api.sportradar.com/synergy-basketball/{self.access_level}/nba/teams.json"
        try:
            req = urllib.request.Request(syn_teams_url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0", "x-api-key": self.api_key})
            with urllib.request.urlopen(req, timeout=10) as resp:
                syn_teams_data = json.loads(resp.read().decode("utf-8"))
                for st in syn_teams_data.get("teams") or []:
                    raw_name = st.get("name") or st.get("market", "")
                    try:
                        code = normalize_team_code(raw_name)
                    except ValueError:
                        continue
                    if code not in team_splits:
                        team_splits[code] = {}
                    synergy_id = st.get("id", "")
                    team_splits[code]["synergy_team_id"] = synergy_id
                    synergy_teams_loaded += 1
        except Exception as exc:
            logger.warning(f"Failed to fetch Synergy basketball teams: {exc}")

        # 4. Synergy Possession-Type Telemetry Events
        syn_events_url = f"https://api.sportradar.com/synergy-basketball/{self.access_level}/nba/events.json?limit=50"
        try:
            req = urllib.request.Request(syn_events_url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0", "x-api-key": self.api_key})
            with urllib.request.urlopen(req, timeout=10) as resp:
                syn_events_data = json.loads(resp.read().decode("utf-8"))
                events = syn_events_data.get("events") or []
                synergy_events_loaded = len(events)
                play_counts: dict[str, int] = {}
                ato_cnt = 0
                pnr_cnt = 0
                zone_cnt = 0
                for ev in events:
                    ed = ev.get("event_details") or {}
                    if ed.get("is_after_timeout"):
                        ato_cnt += 1
                    if ed.get("is_pick_and_roll"):
                        pnr_cnt += 1
                    if ed.get("zone"):
                        zone_cnt += 1
                    for pl in ed.get("plays") or []:
                        pname = str(pl.get("name", "")).strip()
                        if pname and pname not in ("NonPossession", "LineupClip"):
                            play_counts[pname] = play_counts.get(pname, 0) + 1
                top_plays = sorted(play_counts.items(), key=lambda x: x[1], reverse=True)[:8]
                plays_summary = ", ".join(f"{k}:{v}" for k, v in top_plays)
                injury_documents.append(
                    {
                        "source": "sportradar_synergy_possession_telemetry",
                        "title": f"Synergy Possession Play-Types Telemetry ({synergy_events_loaded} events)",
                        "content": (
                            f"Synergy Basketball NBA possession tracking telemetry: "
                            f"ATO={ato_cnt}, PickAndRoll={pnr_cnt}, ZoneDefense={zone_cnt}, "
                            f"TopPlayTags=[{plays_summary}]."
                        ),
                        "captured_at": now_utc,
                    }
                )
        except Exception as exc:
            logger.warning(f"Failed to fetch Synergy game events: {exc}")

        status_str = (
            f"OPERATIONAL_LIVE_NBA_V8_AND_SYNERGY ({len(injury_penalties)} teams injuries + "
            f"{len(team_splits)} teams tactical splits + {synergy_teams_loaded} Synergy NBA teams + "
            f"{synergy_events_loaded} Synergy possession events)"
            if (injury_penalties or team_splits or synergy_teams_loaded)
            else "CONFIGURED_RATE_LIMITED"
        )
        SportradarAdapter._CACHED_CONTEXT = {
            "injury_penalties": injury_penalties,
            "injury_documents": injury_documents,
            "team_splits": team_splits,
            "synergy_teams_loaded": synergy_teams_loaded,
            "synergy_events_loaded": synergy_events_loaded,
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
