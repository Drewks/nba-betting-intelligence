"""
Parsers for public read-only sportsbook JSON APIs (`src/ingestion/peru_book_parsers.py`).

Supports strictly read-only public feeds (Te Apuesto Perú, Betano Perú, Pinnacle Arcadia)
with zero antibot / WAF circumvention. Extracted from `src/ingestion/live_peru_scraper.py`
to keep the main live-odds client concise.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

from src.ingestion.normalizer import american_to_decimal_odds
from src.utils.team_dictionary import get_team

TEAPUESTO_NBA_TOURNAMENT_ID = "46"
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
    player_props: list[dict[str, Any]] | None = None
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


def _epoch_ms_to_utc_iso(ms_val: Any) -> str:
    """Converts millisecond epoch timestamps from Betano JSON payloads to UTC ISO strings."""
    try:
        ms = int(ms_val)
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Two games between the same teams are at least ~20 h apart; a book that lists its start time in
# local time (Lima, UTC-5) is still well inside this window.
MAX_EVENT_START_DIFF_HOURS = 8.0


def parse_event_start_utc(raw: Any) -> datetime | None:
    """Parses a book's event start time (ISO with Z/offset, 'YYYY-MM-DD HH:MM:SS' as UTC, or epoch ms)."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw) / 1000.0, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(raw).strip()
    if text.isdigit():
        return parse_event_start_utc(int(text))
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def select_slate_row_by_start_time(
    candidates: list[dict[str, Any]],
    game_start_time: str | None,
    max_diff_hours: float = MAX_EVENT_START_DIFF_HOURS,
) -> dict[str, Any] | None:
    """
    Picks the book event that is the same game as `game_start_time` among events of the same team pair.

    - Without a reference start time (legacy callers) only an unambiguous single candidate is accepted.
    - Events whose start time is known must be within `max_diff_hours`; the closest one wins.
    - An event without a start time is accepted only when it is the sole candidate and no dated
      candidate exists, since it cannot be told apart from another game of the same teams.
    """
    if not candidates:
        return None
    target = parse_event_start_utc(game_start_time) if game_start_time else None
    if target is None:
        return candidates[0] if len(candidates) == 1 else None
    dated: list[tuple[float, dict[str, Any]]] = []
    undated: list[dict[str, Any]] = []
    for row in candidates:
        start = parse_event_start_utc(row.get("start_time"))
        if start is None:
            undated.append(row)
            continue
        diff_h = abs((start - target).total_seconds()) / 3600.0
        if diff_h <= max_diff_hours:
            dated.append((diff_h, row))
    if dated:
        dated.sort(key=lambda item: item[0])
        return dated[0][1]
    if len(candidates) == 1 and undated:
        return undated[0]
    return None


def parse_teapuesto_nba_events(
    payload: dict[str, Any],
    *,
    captured_at: str | None = None,
    include_live: bool = False,
) -> list[dict[str, Any]]:
    """
    Parses Te Apuesto public tournament-events JSON into standardized NBA pre-game odds rows.
    Extracts Moneyline (219), Totals (225), Spread/Handicap (223), and Player Props (921/924).
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

            elif pmid in ("921", "924") and buckets:
                prop_cat = "PTS" if pmid == "921" else "3PM"
                strip_pattern = (
                    r"\s+total\s+puntos.*$"
                    if pmid == "921"
                    else r"\s+total\s+(?:3-puntos(?:\s+goles\s+de\s+campo)?|triples).*$"
                )
                for bucket in buckets:
                    bname = str(bucket.get("name") or "")
                    raw_player = re.sub(strip_pattern, "", bname, flags=re.IGNORECASE).strip()
                    player_name = _normalize_teapuesto_player_name(raw_player)
                    if not player_name or raw_player == bname:
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
                        sv = odd.get("special_value")
                        if sv is not None and p_line is None:
                            try:
                                p_line = float(sv)
                            except (TypeError, ValueError):
                                pass
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
                                "prop_category": prop_cat,
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


def parse_betano_nba_events(
    payload: dict[str, Any],
    *,
    captured_at: str | None = None,
    include_live: bool = False,
) -> list[dict[str, Any]]:
    """
    Parses Betano Perú public JSON API (`www.betano.pe/api/sport/basquetbol/norteamerica/nba/441g/`)
    into standardized pre-game NBA odds rows (Moneyline H2H1, Total de Puntos FTPO, Hándicap FHOT).
    """
    now_str = captured_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    root = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    blocks = (root or {}).get("blocks") or []

    parsed_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for block in blocks:
        if not isinstance(block, dict):
            continue
        for ev in (block.get("events") or []):
            if not isinstance(ev, dict):
                continue
            ev_id = str(ev.get("id") or "")
            if ev_id and ev_id in seen_ids:
                continue
            if not include_live and ev.get("live"):
                continue

            parts = ev.get("participants") or []
            if len(parts) != 2:
                continue
            t0 = _resolve_team_code(str(parts[0].get("name") or ""))
            t1 = _resolve_team_code(str(parts[1].get("name") or ""))
            if not t0 or not t1 or t0 == t1:
                continue

            ev_name = str(ev.get("name") or "")
            if "@" in ev_name:
                away_code, home_code = t0, t1
            else:
                home_code, away_code = t0, t1

            ml_odds_by_team: dict[str, float] = {}
            total_line: float | None = None
            over_odds: float | None = None
            under_odds: float | None = None
            spread_line_by_team: dict[str, tuple[float, float]] = {}

            for mk in (ev.get("markets") or []):
                if not isinstance(mk, dict):
                    continue
                mtype = str(mk.get("type") or "").upper()
                sels = mk.get("selections") or []

                if mtype == "H2H1" and len(sels) >= 2 and len(ml_odds_by_team) < 2:
                    for s in sels:
                        tcode = _resolve_team_code(str(s.get("name") or ""))
                        try:
                            price = float(s.get("price") or 0.0)
                        except (TypeError, ValueError):
                            price = 0.0
                        if tcode in (home_code, away_code) and price > 1.0:
                            ml_odds_by_team[tcode] = price

                elif mtype == "FTPO" and len(sels) >= 2 and total_line is None:
                    cand_line: float | None = None
                    cand_over: float | None = None
                    cand_under: float | None = None
                    for s in sels:
                        sname = str(s.get("name") or "").lower()
                        try:
                            price = float(s.get("price") or 0.0)
                        except (TypeError, ValueError):
                            price = 0.0
                        if price <= 1.0:
                            continue
                        hcap = s.get("handicap")
                        if hcap is not None:
                            try:
                                cand_line = float(hcap)
                            except (TypeError, ValueError):
                                pass
                        if cand_line is None:
                            m_num = _NUM_RE.search(sname)
                            if m_num:
                                cand_line = float(m_num.group(0))
                        if "más" in sname or "mas" in sname or "over" in sname:
                            cand_over = price
                        elif "menos" in sname or "under" in sname:
                            cand_under = price
                    if cand_line is not None and cand_over and cand_under:
                        total_line, over_odds, under_odds = cand_line, cand_over, cand_under

                elif mtype == "FHOT" and len(sels) >= 2 and len(spread_line_by_team) < 2:
                    for s in sels:
                        raw_sel = str(s.get("name") or "").strip()
                        team_part = re.sub(r"\s*[-+]?\d+(?:\.\d+)?\s*$", "", raw_sel).strip()
                        tcode = _resolve_team_code(team_part)
                        try:
                            price = float(s.get("price") or 0.0)
                        except (TypeError, ValueError):
                            price = 0.0
                        hcap = s.get("handicap")
                        line_val: float | None = None
                        if hcap is not None:
                            try:
                                line_val = float(hcap)
                            except (TypeError, ValueError):
                                line_val = None
                        if line_val is None:
                            m_num = _NUM_RE.search(raw_sel)
                            if m_num:
                                line_val = float(m_num.group(0))
                        if tcode in (home_code, away_code) and line_val is not None and price > 1.0:
                            spread_line_by_team[tcode] = (line_val, price)

            home_odds = ml_odds_by_team.get(home_code)
            away_odds = ml_odds_by_team.get(away_code)
            if not (home_odds and away_odds) and not (total_line and over_odds and under_odds):
                continue

            if ev_id:
                seen_ids.add(ev_id)

            spread_home_line = spread_line_by_team.get(home_code, (None, None))[0]
            spread_home_odds = spread_line_by_team.get(home_code, (None, None))[1]
            spread_away_odds = spread_line_by_team.get(away_code, (None, None))[1]

            parsed_rows.append(
                {
                    "event_id": ev.get("id"),
                    "event_url": ev.get("url"),
                    "start_time": _epoch_ms_to_utc_iso(ev.get("startTime")),
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
                    "player_props": [],
                    "captured_at": now_str,
                    "book_id": "betano_pe",
                    "book_name": "Betano Perú",
                    "source": "Betano Perú API Direct",
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
