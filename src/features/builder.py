"""Constructs strictly pre-game team features and historical rolling statistics without lookahead."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
import math
from typing import Any
import numpy as np

from src.features.boxscore_features import FEATURE_NAMES as BOXSCORE_FEATURE_NAMES
from src.validation.validator import parse_iso_utc, validate_essential_features

_INDEX_STORE: dict[str, dict[str, Any]] = {}

LEAGUE_PPG_INIT = 114.2
LEAGUE_TOTAL_INIT = 228.4
LEAGUE_PACE_BASE = 99.5
HIGH_ALTITUDE_TEAMS = frozenset({"DEN", "UTA"})

# Geodesic NBA Arena Coordinates: (latitude, longitude, utc_offset, altitude_ft)
# Adapted from NBA_AI phase5/arena_data.py & travel.py for exact Haversine travel miles,
# timezone jet-lag crossings, "first game home after road trip" penalty, and altitude acclimation.
ARENA_GEODESIC_DATA: dict[str, tuple[float, float, float, float]] = {
    "ATL": (33.7573, -84.3963, -5.0, 1050.0),
    "BOS": (42.3662, -71.0621, -5.0, 20.0),
    "BKN": (40.6826, -73.9754, -5.0, 30.0),
    "CHA": (35.2251, -80.8392, -5.0, 751.0),
    "CHI": (41.8807, -87.6742, -6.0, 594.0),
    "CLE": (41.4965, -81.6882, -5.0, 653.0),
    "DAL": (32.7905, -96.8103, -6.0, 430.0),
    "DEN": (39.7487, -105.0077, -7.0, 5280.0),
    "DET": (42.3410, -83.0551, -5.0, 600.0),
    "GSW": (37.7680, -122.3877, -8.0, 10.0),
    "HOU": (29.7508, -95.3621, -6.0, 50.0),
    "IND": (39.7639, -86.1555, -5.0, 715.0),
    "LAC": (33.9450, -118.3410, -8.0, 120.0),
    "LAL": (34.0430, -118.2673, -8.0, 285.0),
    "MEM": (35.1382, -90.0505, -6.0, 337.0),
    "MIA": (25.7814, -80.1870, -5.0, 10.0),
    "MIL": (43.0451, -87.9172, -6.0, 617.0),
    "MIN": (44.9795, -93.2760, -6.0, 830.0),
    "NOP": (29.9490, -90.0821, -6.0, 10.0),
    "NYK": (40.7505, -73.9934, -5.0, 35.0),
    "OKC": (35.4634, -97.5151, -6.0, 1201.0),
    "ORL": (28.5392, -81.3839, -5.0, 82.0),
    "PHI": (39.9012, -75.1720, -5.0, 39.0),
    "PHX": (33.4457, -112.0712, -7.0, 1086.0),
    "POR": (45.5316, -122.6668, -8.0, 50.0),
    "SAC": (38.5802, -121.4997, -8.0, 30.0),
    "SAS": (29.4270, -98.4375, -6.0, 650.0),
    "TOR": (43.6435, -79.3791, -5.0, 249.0),
    "UTA": (40.7683, -111.9011, -7.0, 4226.0),
    "WAS": (38.8981, -77.0209, -5.0, 25.0),
}


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_miles = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * r_miles * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _compute_travel_leg(
    prev_venue: str | None,
    curr_venue: str,
    team_home_venue: str,
) -> tuple[float, float, float]:
    """Returns (travel_miles, tz_crossings, altitude_climb_ft) for a team traveling to curr_venue."""
    curr_info = ARENA_GEODESIC_DATA.get(curr_venue, (39.0, -98.0, -6.0, 500.0))
    origin = prev_venue if (prev_venue and prev_venue in ARENA_GEODESIC_DATA) else team_home_venue
    prev_info = ARENA_GEODESIC_DATA.get(origin, curr_info)
    if origin == curr_venue:
        return 0.0, 0.0, 0.0
    dist = _haversine_miles(prev_info[0], prev_info[1], curr_info[0], curr_info[1])
    tz_diff = abs(curr_info[2] - prev_info[2])
    alt_climb = max(0.0, curr_info[3] - prev_info[3])
    return dist, tz_diff, alt_climb


def _default_team_snapshot(league_ppg: float = LEAGUE_PPG_INIT) -> dict[str, Any]:
    return {
        "elo_slow": 1500.0,
        "elo_fast": 1500.0,
        "pf_slow": league_ppg,
        "pa_slow": league_ppg,
        "pf_fast": league_ppg,
        "pa_fast": league_ppg,
        "tempo_slow": 0.0,
        "tempo_fast": 0.0,
        "var_total": 335.0,
        "last_start": None,
        "recent_starts": (),
        "road_streak": 0,
        "last_venue": None,
        "home_venue_edge": 0.0,
        "away_venue_edge": 0.0,
        "streak": 0,
        "margins": (),
        "totals": (),
        "games": 0,
        "efg": 0.542,
        "tov": 0.132,
        "orb": 0.248,
        "ftr": 0.215,
        "xefg": 0.540,
    }


def _apply_offseason_regression(snap: dict[str, Any], target_start_dt: Any, league_ppg: float) -> dict[str, Any]:
    last_start = snap["last_start"]
    if last_start is None or (target_start_dt - last_start).days < 60:
        return snap
    elo_s = 1500.0 + 0.66 * (snap["elo_slow"] - 1500.0)
    pf_s = league_ppg + 0.68 * (snap["pf_slow"] - league_ppg)
    pa_s = league_ppg + 0.68 * (snap["pa_slow"] - league_ppg)
    t_s = 0.55 * snap["tempo_slow"]
    return {
        "elo_slow": elo_s,
        "elo_fast": elo_s,
        "pf_slow": pf_s,
        "pa_slow": pa_s,
        "pf_fast": pf_s,
        "pa_fast": pa_s,
        "tempo_slow": t_s,
        "tempo_fast": t_s,
        "var_total": snap["var_total"],
        "last_start": None,
        "recent_starts": (),
        "road_streak": 0,
        "last_venue": None,
        "home_venue_edge": 0.50 * snap["home_venue_edge"],
        "away_venue_edge": 0.50 * snap["away_venue_edge"],
        "streak": 0,
        "margins": snap["margins"][-4:],
        "totals": snap["totals"][-4:],
        "games": snap["games"],
        "efg": 0.542 + 0.65 * (snap.get("efg", 0.542) - 0.542),
        "tov": 0.132 + 0.65 * (snap.get("tov", 0.132) - 0.132),
        "orb": 0.248 + 0.65 * (snap.get("orb", 0.248) - 0.248),
        "ftr": 0.215 + 0.65 * (snap.get("ftr", 0.215) - 0.215),
        "xefg": 0.540 + 0.65 * (snap.get("xefg", 0.540) - 0.540),
    }


def _schedule_density(snap: dict[str, Any], target_start_dt: Any) -> tuple[int, int, int]:
    last_start = snap["last_start"]
    if last_start is None:
        return 3, 0, 0
    target_date = target_start_dt.date()
    days = int(max(1, min(6, (target_date - last_start.date()).days)))
    g4 = 0
    g7 = 0
    for dt in snap["recent_starts"]:
        d_gap = (target_date - dt.date()).days
        if 0 < d_gap <= 4:
            g4 += 1
        if 0 < d_gap <= 7:
            g7 += 1
    return days, g4, g7


_SITUATIONAL_CONFIG_CACHE: Any = None


def _get_situational_factors_config() -> Any:
    global _SITUATIONAL_CONFIG_CACHE
    if _SITUATIONAL_CONFIG_CACHE is None:
        try:
            from src.config import load_config
            _SITUATIONAL_CONFIG_CACHE = load_config().situational_factors
        except Exception:
            from src.config import SituationalFactorsConfig
            _SITUATIONAL_CONFIG_CACHE = SituationalFactorsConfig()
    return _SITUATIONAL_CONFIG_CACHE


def _append_game_to_index(idx: dict[str, Any], g: dict[str, Any]) -> None:
    if g.get("status") != "FINAL" or g.get("home_score") is None or g.get("away_score") is None:
        return
    ts_str = str(g["game_start_time"])
    start_dt = parse_iso_utc(ts_str)
    h_code = g["home_team"]
    a_code = g["away_team"]
    league_ppg = idx["league_ppg"]
    league_total = idx["league_total"]
    teams = idx["teams"]

    h_cur = _apply_offseason_regression(teams.get(h_code) or _default_team_snapshot(league_ppg), start_dt, league_ppg)
    a_cur = _apply_offseason_regression(teams.get(a_code) or _default_team_snapshot(league_ppg), start_dt, league_ppg)

    h_rest, h_g4, h_g7 = _schedule_density(h_cur, start_dt)
    a_rest, a_g4, a_g7 = _schedule_density(a_cur, start_dt)

    dist_h, tz_h, _alt_climb_h = _compute_travel_leg(h_cur["last_venue"], h_code, h_code)
    dist_a, tz_a, alt_climb_a = _compute_travel_leg(a_cur["last_venue"], h_code, a_code)
    first_home_from_road = 1.0 if (dist_h > 700.0 and h_rest <= 2) else 0.0
    sit = _get_situational_factors_config()
    travel_diff_edge = sit.travel_miles_rate * ((dist_a - dist_h) / 1000.0) + sit.timezone_rate * (tz_a - tz_h)

    h_fat = (
        (sit.b2b_penalty_home if h_rest == 1 else (sit.rest_3plus_bonus_home if h_rest >= 3 else 0.0))
        - 0.50 * max(0, h_g4 - 1)
        - 0.20 * max(0, h_g7 - 3)
        - 0.85 * first_home_from_road
        + 0.50 * travel_diff_edge
    )
    a_fat = (
        (sit.b2b_penalty_away if a_rest == 1 else (sit.rest_3plus_bonus_away if a_rest >= 3 else 0.0))
        - 0.60 * max(0, a_g4 - 1)
        - 0.25 * max(0, a_g7 - 3)
        - 0.22 * min(4, a_cur["road_streak"])
        - 0.50 * travel_diff_edge
    )
    fat_diff = h_fat - a_fat

    c_alt = ARENA_GEODESIC_DATA.get(h_code, (39.0, -98.0, -6.0, 500.0))[3]
    alt_pts = (sit.altitude_edge_multiplier * min(1.15, alt_climb_a / sit.altitude_divisor_feet) if c_alt >= sit.altitude_threshold_feet else 0.0) * (1.30 if a_rest == 1 else 1.0)

    elo_ds = (h_cur["elo_slow"] - a_cur["elo_slow"]) + sit.home_court_advantage_elo + 15.0 * fat_diff + 14.0 * alt_pts
    elo_df = (h_cur["elo_fast"] - a_cur["elo_fast"]) + sit.home_court_advantage_elo + 15.0 * fat_diff + 14.0 * alt_pts

    hs = float(g["home_score"])
    as_ = float(g["away_score"])
    raw_tot = hs + as_
    raw_mar = hs - as_
    yw = 1.0 if raw_mar > 0.0 else 0.0

    p_es = 1.0 / (1.0 + 10.0 ** (-elo_ds / 400.0))
    mov = ((min(26.0, abs(raw_mar)) + 3.0) ** 0.8) / (7.5 + 0.006 * abs(elo_ds))
    new_h_elo_s = h_cur["elo_slow"] + 21.0 * mov * (yw - p_es)
    new_a_elo_s = a_cur["elo_slow"] - 21.0 * mov * (yw - p_es)

    p_ef = 1.0 / (1.0 + 10.0 ** (-elo_df / 400.0))
    new_h_elo_f = h_cur["elo_fast"] + 33.0 * mov * (yw - p_ef)
    new_a_elo_f = a_cur["elo_fast"] - 33.0 * mov * (yw - p_ef)

    exp_eff_tot = (
        league_total
        + (h_cur["pf_slow"] - league_ppg)
        + (a_cur["pa_slow"] - league_ppg)
        + (a_cur["pf_slow"] - league_ppg)
        + (h_cur["pa_slow"] - league_ppg)
    )
    exp_game_tot = exp_eff_tot + h_cur["tempo_slow"] + a_cur["tempo_slow"]
    is_likely_ot = (abs(raw_mar) <= 7.0) and (raw_tot > exp_game_tot + 18.0)
    reg_tot = (raw_tot - 13.0) if is_likely_ot else raw_tot
    capped_tot = max(league_total - 38.0, min(league_total + 38.0, reg_tot))
    tempo_err = capped_tot - exp_game_tot

    capped_mar = max(-28.0, min(28.0, raw_mar))
    adj_hs = 0.5 * (capped_tot + capped_mar)
    adj_as = 0.5 * (capped_tot - capped_mar)

    hca_side = 0.925
    h_fa = (adj_hs - hca_side) - (a_cur["pa_slow"] - league_ppg) - 0.35 * a_cur["tempo_slow"]
    h_aa = (adj_as + hca_side) - (a_cur["pf_slow"] - league_ppg) - 0.35 * a_cur["tempo_slow"]
    a_fa = (adj_as + hca_side) - (h_cur["pa_slow"] - league_ppg) - 0.35 * h_cur["tempo_slow"]
    a_aa = (adj_hs - hca_side) - (h_cur["pf_slow"] - league_ppg) - 0.35 * h_cur["tempo_slow"]

    tot_err_sq = min(1400.0, (raw_tot - exp_game_tot) ** 2)

    exp_mar_base = ((h_cur["elo_slow"] - a_cur["elo_slow"]) + 50.0) / 28.0
    mar_res = max(-20.0, min(20.0, capped_mar - exp_mar_base))
    new_h_venue = 0.96 * h_cur["home_venue_edge"] + 0.04 * mar_res
    new_a_venue = 0.96 * a_cur["away_venue_edge"] + 0.04 * (-mar_res)

    new_h_streak = (
        (h_cur["streak"] + 1 if h_cur["streak"] > 0 else 1)
        if raw_mar > 0
        else (h_cur["streak"] - 1 if h_cur["streak"] < 0 else -1)
    )
    new_a_streak = (
        (a_cur["streak"] + 1 if a_cur["streak"] > 0 else 1)
        if raw_mar < 0
        else (a_cur["streak"] - 1 if a_cur["streak"] < 0 else -1)
    )

    h_next = {
        "elo_slow": new_h_elo_s,
        "elo_fast": new_h_elo_f,
        "pf_slow": h_cur["pf_slow"] + 0.045 * (h_fa - h_cur["pf_slow"]),
        "pa_slow": h_cur["pa_slow"] + 0.045 * (h_aa - h_cur["pa_slow"]),
        "pf_fast": h_cur["pf_fast"] + 0.110 * (h_fa - h_cur["pf_fast"]),
        "pa_fast": h_cur["pa_fast"] + 0.110 * (h_aa - h_cur["pa_fast"]),
        "tempo_slow": h_cur["tempo_slow"] + 0.055 * tempo_err,
        "tempo_fast": h_cur["tempo_fast"] + 0.130 * tempo_err,
        "var_total": h_cur["var_total"] + 0.04 * (tot_err_sq - h_cur["var_total"]),
        "last_start": start_dt,
        "recent_starts": (*h_cur["recent_starts"][-11:], start_dt),
        "road_streak": 0,
        "last_venue": h_code,
        "home_venue_edge": new_h_venue,
        "away_venue_edge": h_cur["away_venue_edge"],
        "streak": new_h_streak,
        "margins": (*h_cur["margins"][-14:], raw_mar),
        "totals": (*h_cur["totals"][-14:], raw_tot),
        "games": h_cur["games"] + 1,
        "efg": h_cur.get("efg", 0.542) + 0.040 * (max(0.42, min(0.66, 0.542 + 0.50 * ((adj_hs - league_ppg) / 100.0))) - h_cur.get("efg", 0.542)),
        "tov": h_cur.get("tov", 0.132) + 0.040 * (max(0.08, min(0.20, 0.132 - 0.22 * ((adj_hs - league_ppg) / 100.0))) - h_cur.get("tov", 0.132)),
        "orb": h_cur.get("orb", 0.248) + 0.040 * (max(0.16, min(0.35, 0.248 + 0.18 * ((adj_hs - league_ppg) / 100.0))) - h_cur.get("orb", 0.248)),
        "ftr": h_cur.get("ftr", 0.215) + 0.040 * (max(0.14, min(0.32, 0.215 + 0.16 * ((adj_hs - league_ppg) / 100.0))) - h_cur.get("ftr", 0.215)),
        "xefg": h_cur.get("xefg", 0.540) + 0.040 * (max(0.42, min(0.66, 0.542 + 0.50 * ((adj_hs - league_ppg) / 100.0))) - h_cur.get("xefg", 0.540)),
    }
    a_next = {
        "elo_slow": new_a_elo_s,
        "elo_fast": new_a_elo_f,
        "pf_slow": a_cur["pf_slow"] + 0.045 * (a_fa - a_cur["pf_slow"]),
        "pa_slow": a_cur["pa_slow"] + 0.045 * (a_aa - a_cur["pa_slow"]),
        "pf_fast": a_cur["pf_fast"] + 0.110 * (a_fa - a_cur["pf_fast"]),
        "pa_fast": a_cur["pa_fast"] + 0.110 * (a_aa - a_cur["pa_fast"]),
        "tempo_slow": a_cur["tempo_slow"] + 0.055 * tempo_err,
        "tempo_fast": a_cur["tempo_fast"] + 0.130 * tempo_err,
        "var_total": a_cur["var_total"] + 0.04 * (tot_err_sq - a_cur["var_total"]),
        "last_start": start_dt,
        "recent_starts": (*a_cur["recent_starts"][-11:], start_dt),
        "road_streak": a_cur["road_streak"] + 1,
        "last_venue": h_code,
        "home_venue_edge": a_cur["home_venue_edge"],
        "away_venue_edge": new_a_venue,
        "streak": new_a_streak,
        "margins": (*a_cur["margins"][-14:], -raw_mar),
        "totals": (*a_cur["totals"][-14:], raw_tot),
        "games": a_cur["games"] + 1,
        "efg": a_cur.get("efg", 0.542) + 0.040 * (max(0.42, min(0.66, 0.542 + 0.50 * ((adj_as - league_ppg) / 100.0))) - a_cur.get("efg", 0.542)),
        "tov": a_cur.get("tov", 0.132) + 0.040 * (max(0.08, min(0.20, 0.132 - 0.22 * ((adj_as - league_ppg) / 100.0))) - a_cur.get("tov", 0.132)),
        "orb": a_cur.get("orb", 0.248) + 0.040 * (max(0.16, min(0.35, 0.248 + 0.18 * ((adj_as - league_ppg) / 100.0))) - a_cur.get("orb", 0.248)),
        "ftr": a_cur.get("ftr", 0.215) + 0.040 * (max(0.14, min(0.32, 0.215 + 0.16 * ((adj_as - league_ppg) / 100.0))) - a_cur.get("ftr", 0.215)),
        "xefg": a_cur.get("xefg", 0.540) + 0.040 * (max(0.42, min(0.66, 0.542 + 0.50 * ((adj_as - league_ppg) / 100.0))) - a_cur.get("xefg", 0.540)),
    }

    teams[h_code] = h_next
    teams[a_code] = a_next
    idx["team_ts"].setdefault(h_code, []).append(ts_str)
    idx["team_snaps"].setdefault(h_code, []).append(h_next)
    idx["team_ts"].setdefault(a_code, []).append(ts_str)
    idx["team_snaps"].setdefault(a_code, []).append(a_next)

    league_ppg += 0.015 * (0.5 * capped_tot - league_ppg)
    league_total = 2.0 * league_ppg
    idx["league_ppg"] = league_ppg
    idx["league_total"] = league_total
    idx["league_ts"].append(ts_str)
    idx["league_vals"].append((league_ppg, league_total))
    idx["game_ids"].append(g.get("game_id"))


def _get_or_build_history_index(historical_final_games: list[dict[str, Any]]) -> tuple[dict[str, Any], str | None]:
    if not historical_final_games:
        return {
            "team_ts": {},
            "team_snaps": {},
            "league_ts": [],
            "league_vals": [],
            "game_ids": [],
        }, None

    first_id = str(historical_final_games[0].get("game_id", ""))
    last_id = str(historical_final_games[-1].get("game_id", ""))
    n_in = len(historical_final_games)

    existing = _INDEX_STORE.get(first_id)
    if existing is not None:
        n_ex = len(existing["game_ids"])
        # Case A: Exact prefix or match of already indexed monotonic history
        if n_in <= n_ex and n_in > 0 and existing["game_ids"][n_in - 1] == last_id:
            max_ts = str(historical_final_games[-1].get("game_start_time", ""))
            return existing, max_ts
        # Case B: Monotonic extension of already indexed history
        if n_in > n_ex and n_ex > 0 and str(historical_final_games[n_ex - 1].get("game_id", "")) == existing["game_ids"][n_ex - 1]:
            tail = historical_final_games[n_ex:]
            # Check if tail is already sorted
            is_sorted = all(
                str(tail[i].get("game_start_time", "")) <= str(tail[i + 1].get("game_start_time", ""))
                for i in range(len(tail) - 1)
            )
            if is_sorted:
                for g in tail:
                    _append_game_to_index(existing, g)
                max_ts = str(historical_final_games[-1].get("game_start_time", ""))
                return existing, max_ts

    # Otherwise build fresh sorted index
    valid = [
        g
        for g in historical_final_games
        if g.get("status") == "FINAL"
        and g.get("home_score") is not None
        and g.get("away_score") is not None
    ]
    valid.sort(key=lambda g: (str(g.get("game_start_time", "")), str(g.get("game_id", ""))))

    new_idx: dict[str, Any] = {
        "teams": {},
        "team_ts": {},
        "team_snaps": {},
        "league_ppg": LEAGUE_PPG_INIT,
        "league_total": LEAGUE_TOTAL_INIT,
        "league_ts": [],
        "league_vals": [],
        "game_ids": [],
    }
    for g in valid:
        _append_game_to_index(new_idx, g)

    if valid:
        new_first_id = str(valid[0].get("game_id", ""))
        _INDEX_STORE[new_first_id] = new_idx
        if len(_INDEX_STORE) > 8:
            oldest_key = next(iter(_INDEX_STORE))
            if oldest_key != new_first_id:
                _INDEX_STORE.pop(oldest_key, None)
        return new_idx, str(valid[-1].get("game_start_time", ""))

    return new_idx, None


def _lookup_team_state_before(
    idx_bundle: dict[str, Any],
    team_code: str,
    cutoff_ts_str: str,
    target_start_dt: Any,
    league_ppg: float,
    max_history_ts: str | None = None,
) -> dict[str, Any]:
    ts_list = idx_bundle["team_ts"].get(team_code)
    if not ts_list:
        return _default_team_snapshot(league_ppg)
    pos = bisect_left(ts_list, cutoff_ts_str) - 1
    if max_history_ts is not None and pos >= 0 and ts_list[pos] > max_history_ts:
        pos = bisect_right(ts_list, max_history_ts) - 1
    if pos < 0:
        return _default_team_snapshot(league_ppg)
    snap = idx_bundle["team_snaps"][team_code][pos]
    return _apply_offseason_regression(snap, target_start_dt, league_ppg)


def _lookup_league_before(
    idx_bundle: dict[str, Any],
    cutoff_ts_str: str,
    max_history_ts: str | None = None,
) -> tuple[float, float]:
    l_ts = idx_bundle["league_ts"]
    if not l_ts:
        return LEAGUE_PPG_INIT, LEAGUE_TOTAL_INIT
    pos = bisect_left(l_ts, cutoff_ts_str) - 1
    if max_history_ts is not None and pos >= 0 and l_ts[pos] > max_history_ts:
        pos = bisect_right(l_ts, max_history_ts) - 1
    if pos < 0:
        return LEAGUE_PPG_INIT, LEAGUE_TOTAL_INIT
    return idx_bundle["league_vals"][pos]


def build_pregame_features(
    target_game: dict[str, Any],
    historical_final_games: list[dict[str, Any]],
    market: str = "moneyline",
    rolling_window: int = 10,
) -> dict[str, float]:
    """
    Computes pre-game feature vector for target_game using ONLY historical games
    that finished strictly before target_game['game_start_time'].
    """
    validate_essential_features(target_game, market)
    target_start_str = str(target_game["game_start_time"])
    target_start = parse_iso_utc(target_start_str)
    home_team = target_game["home_team"]
    away_team = target_game["away_team"]

    idx_bundle, max_hist_ts = _get_or_build_history_index(historical_final_games)
    league_ppg, league_avg_total = _lookup_league_before(idx_bundle, target_start_str, max_hist_ts)

    h_snap = _lookup_team_state_before(idx_bundle, home_team, target_start_str, target_start, league_ppg, max_hist_ts)
    a_snap = _lookup_team_state_before(idx_bundle, away_team, target_start_str, target_start, league_ppg, max_hist_ts)

    def _ewma(values: tuple[float, ...] | list[float], default: float = 0.0) -> float:
        if not values:
            return default
        sliced = values[-rolling_window:]
        weights = np.exp(np.linspace(-1.0, 0.0, len(sliced)))
        return float(np.average(sliced, weights=weights))

    home_margins = h_snap["margins"]
    home_totals = h_snap["totals"]
    away_margins = a_snap["margins"]
    away_totals = a_snap["totals"]

    home_recent_net = _ewma(home_margins, 0.0)
    away_recent_net = _ewma(away_margins, 0.0)
    home_win_pct = _ewma([1.0 if m > 0 else 0.0 for m in home_margins], 0.5)
    away_win_pct = _ewma([1.0 if m > 0 else 0.0 for m in away_margins], 0.5)
    recent_total_trend = 0.5 * (
        _ewma(home_totals, league_avg_total) + _ewma(away_totals, league_avg_total)
    ) - league_avg_total

    h_off = float(target_game["home_off_rtg"])
    h_def = float(target_game["home_def_rtg"])
    a_off = float(target_game["away_off_rtg"])
    a_def = float(target_game["away_def_rtg"])
    h_pace = float(target_game.get("home_pace") or 99.5)
    a_pace = float(target_game.get("away_pace") or 99.5)

    h_sched_rest, h_g4, h_g7 = _schedule_density(h_snap, target_start)
    a_sched_rest, a_g4, a_g7 = _schedule_density(a_snap, target_start)
    h_rest = float(target_game.get("home_rest_days") or h_sched_rest)
    a_rest = float(target_game.get("away_rest_days") or a_sched_rest)

    home_net_rtg = h_off - h_def
    away_net_rtg = a_off - a_def
    net_rtg_diff = home_net_rtg - away_net_rtg
    expected_pace = 0.5 * (h_pace + a_pace)

    dist_h, tz_h, _alt_climb_h = _compute_travel_leg(h_snap["last_venue"], home_team, home_team)
    dist_a, tz_a, alt_climb_a = _compute_travel_leg(a_snap["last_venue"], home_team, away_team)
    first_home_from_road = 1.0 if (dist_h > 700.0 and h_rest <= 2.0) else 0.0
    travel_miles_diff = dist_a - dist_h
    sit = _get_situational_factors_config()
    travel_diff_edge = sit.travel_miles_rate * (travel_miles_diff / 1000.0) + sit.timezone_rate * (tz_a - tz_h)

    h_b2b_pen = sit.b2b_penalty_home if h_rest <= 1.0 else (sit.rest_3plus_bonus_home if h_rest >= 3.0 else 0.0)
    a_b2b_pen = sit.b2b_penalty_away if a_rest <= 1.0 else (sit.rest_3plus_bonus_away if a_rest >= 3.0 else 0.0)
    b2b_advantage = h_b2b_pen - a_b2b_pen

    h_fatigue = (
        h_b2b_pen
        - 0.50 * max(0, h_g4 - 1)
        - 0.20 * max(0, h_g7 - 3)
        - 0.85 * first_home_from_road
        + 0.50 * travel_diff_edge
    )
    a_fatigue = (
        a_b2b_pen
        - 0.60 * max(0, a_g4 - 1)
        - 0.25 * max(0, a_g7 - 3)
        - 0.22 * min(4, a_snap["road_streak"])
        - 0.50 * travel_diff_edge
    )
    fatigue_diff = h_fatigue - a_fatigue

    c_alt = ARENA_GEODESIC_DATA.get(home_team, (39.0, -98.0, -6.0, 500.0))[3]
    altitude_advantage = (
        1.35 * min(1.15, alt_climb_a / 4200.0) if c_alt >= 4000.0 else 0.0
    ) * (1.30 if a_rest <= 1.0 else 1.0)

    venue_split_diff = float(h_snap["home_venue_edge"] - a_snap["away_venue_edge"])
    streak_diff = float(h_snap["streak"] - a_snap["streak"])
    matchup_mismatch = (h_off - a_def) - (a_off - h_def)

    scale_100 = 100.0 / LEAGUE_PACE_BASE
    dyn_h_net_s = (h_snap["pf_slow"] - h_snap["pa_slow"]) * scale_100
    dyn_a_net_s = (a_snap["pf_slow"] - a_snap["pa_slow"]) * scale_100
    dyn_h_net_f = (h_snap["pf_fast"] - h_snap["pa_fast"]) * scale_100
    dyn_a_net_f = (a_snap["pf_fast"] - a_snap["pa_fast"]) * scale_100
    dyn_net_diff = (0.88 * dyn_h_net_s + 0.12 * dyn_h_net_f) - (0.88 * dyn_a_net_s + 0.12 * dyn_a_net_f)
    form_surge_diff = (dyn_h_net_f - dyn_h_net_s) - (dyn_a_net_f - dyn_a_net_s)

    min_games = min(h_snap["games"], a_snap["games"])
    live_rating_delta = net_rtg_diff - dyn_net_diff if min_games >= 5 else net_rtg_diff
    elo_ds = (h_snap["elo_slow"] - a_snap["elo_slow"]) + sit.home_court_advantage_elo + 15.0 * fatigue_diff + 14.0 * altitude_advantage
    elo_df = (h_snap["elo_fast"] - a_snap["elo_fast"]) + sit.home_court_advantage_elo + 15.0 * fatigue_diff + 14.0 * altitude_advantage
    elo_diff = 0.82 * elo_ds + 0.18 * elo_df + (8.0 * live_rating_delta if min_games < 15 else 2.5 * live_rating_delta)
    p_elo = 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))
    elo_spread = elo_diff / 28.0

    pace_factor = expected_pace / 100.0
    eff_spread = net_rtg_diff * pace_factor + sit.home_court_advantage_pts + fatigue_diff + altitude_advantage
    w_elo_mar = min(0.55, max(0.15, min_games / 25.0))
    structural_margin = w_elo_mar * elo_spread + (1.0 - w_elo_mar) * eff_spread

    league_rtg = league_ppg * scale_100
    off_def_sum = (h_off - league_rtg) + (a_def - league_rtg) + (a_off - league_rtg) + (h_def - league_rtg)
    h_tempo = 0.72 * h_snap["tempo_slow"] + 0.28 * h_snap["tempo_fast"]
    a_tempo = 0.72 * a_snap["tempo_slow"] + 0.28 * a_snap["tempo_fast"]
    tempo_sum = h_tempo + a_tempo
    b2b_total_drag = (-1.15 if h_rest <= 1.0 else 0.0) + (-1.15 if a_rest <= 1.0 else 0.0)
    blowout_drag = -0.16 * max(0.0, abs(structural_margin) - 9.5)
    structural_total = (
        league_avg_total
        + 0.72 * off_def_sum * pace_factor
        + 0.40 * tempo_sum
        + b2b_total_drag
        + blowout_drag
    )
    dynamic_total_std = float(np.clip(math.sqrt(0.5 * (h_snap["var_total"] + a_snap["var_total"])), 16.5, 20.5))

    return {
        "home_off_rtg": h_off,
        "home_def_rtg": h_def,
        "home_net_rtg": round(home_net_rtg, 4),
        "away_off_rtg": a_off,
        "away_def_rtg": a_def,
        "away_net_rtg": round(away_net_rtg, 4),
        "net_rtg_diff": round(net_rtg_diff, 4),
        "matchup_mismatch": round(matchup_mismatch, 4),
        "home_pace": h_pace,
        "away_pace": a_pace,
        "expected_pace": round(expected_pace, 4),
        "pace_clash": round(abs(h_pace - a_pace), 4),
        "home_rest_days": h_rest,
        "away_rest_days": a_rest,
        "rest_diff": round(h_rest - a_rest, 4),
        "b2b_advantage": round(b2b_advantage, 4),
        "fatigue_diff": round(fatigue_diff, 4),
        "altitude_advantage": round(altitude_advantage, 4),
        "travel_miles_diff": round(travel_miles_diff, 1),
        "away_tz_change": round(tz_a, 1),
        "first_home_from_road": round(first_home_from_road, 1),
        "venue_split_diff": round(venue_split_diff, 4),
        "streak_diff": round(streak_diff, 1),
        "home_recent_margin": round(home_recent_net, 4),
        "away_recent_margin": round(away_recent_net, 4),
        "recent_margin_diff": round(home_recent_net - away_recent_net, 4),
        "form_surge_diff": round(form_surge_diff, 4),
        "recent_total_trend": round(recent_total_trend, 4),
        "four_factors_diff": round(float(target_game.get("four_factors_diff") or (0.40 * (h_snap.get("efg", 0.542) - a_snap.get("efg", 0.542)) + 0.25 * (a_snap.get("tov", 0.132) - h_snap.get("tov", 0.132)) + 0.20 * (h_snap.get("orb", 0.248) - a_snap.get("orb", 0.248)) + 0.15 * (h_snap.get("ftr", 0.215) - a_snap.get("ftr", 0.215)))), 4),
        "shot_quality_xeFG_diff": round(float(target_game.get("shot_quality_xeFG_diff") or (h_snap.get("xefg", 0.540) - a_snap.get("xefg", 0.540))), 4),
        "home_recent_win_pct": round(home_win_pct, 4),
        "away_recent_win_pct": round(away_win_pct, 4),
        "elo_home": round(h_snap["elo_slow"], 2),
        "elo_away": round(a_snap["elo_slow"], 2),
        "elo_diff": round(elo_diff, 3),
        "elo_spread": round(elo_spread, 4),
        "p_elo": round(p_elo, 6),
        "eff_spread": round(eff_spread, 4),
        "structural_margin": round(structural_margin, 4),
        "off_def_sum": round(off_def_sum, 4),
        "tempo_sum": round(tempo_sum, 4),
        "b2b_total_drag": round(b2b_total_drag, 4),
        "blowout_drag": round(blowout_drag, 4),
        "structural_total": round(structural_total, 4),
        "league_avg_total": round(league_avg_total, 4),
        "dynamic_total_std": round(dynamic_total_std, 4),
        "home_court_indicator": 1.0,
        # Real box-score features (possessions, Four Factors, availability) attached to the game record by
        # src/features/boxscore_features.py; 0.0 when no box-score history is available.
        **{k: float(target_game.get(k) or 0.0) for k in BOXSCORE_FEATURE_NAMES},
        "bx_available": 1.0 if target_game.get("bx_min_games") else 0.0,
    }



