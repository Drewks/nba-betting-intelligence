"""
Leakage-free pre-game team ratings computed ONLY from the project's own game history.

Replaces hard-coded priors, ESPN W-L records (which include the game itself once FINAL),
and the constant `rest_days = 2` placeholder with values derived strictly from games that
finished before each game's tip-off:

- Multi-horizon (slow + fast) opponent-adjusted offensive / defensive ratings (points per 100 possessions)
- Pace-decoupled tempo proxy (prevents high offensive efficiency from cancelling itself via game_total division)
- Overtime-debiased and Huber blowout-capped updates (prevents garbage-time & OT distortion)
- Real rest days from the schedule (1 = back-to-back)
- Season regression to the league mean when a team has a long layoff (offseason)
- Preserves centered acute star-injury & Synergy adjustments on SCHEDULED games without shifting total points mean.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.validation.validator import parse_iso_utc

SYNTHETIC_PREFIX = "SYN_"

LEAGUE_PPG_PRIOR = 114.2
LEAGUE_PACE_BASE = 99.5
EWMA_ALPHA_SLOW = 0.045     # ~15-game half-life for structural opponent-adjusted efficiency
EWMA_ALPHA_FAST = 0.110     # ~6-game half-life for recent momentum/surge
TEMPO_ALPHA_SLOW = 0.055    # decoupled tempo learning rate
TEMPO_ALPHA_FAST = 0.130
LEAGUE_ALPHA = 0.015        # slow-moving league averages
OFFSEASON_GAP_DAYS = 60
OFFSEASON_CARRYOVER = 0.68  # retain 68% of prior season's true efficiency deviation
HCA_PER_SIDE = 0.925        # 1.85 pts total modern NBA home-court advantage
BLOWOUT_CAP_MARGIN = 28.0   # Huber cap on garbage-time blowout margins
DEFAULT_REST_DAYS = 3
MAX_REST_DAYS = 6


def is_synthetic_game_id(game_id: str | None) -> bool:
    return str(game_id or "").startswith(SYNTHETIC_PREFIX)


class _TeamState:
    __slots__ = (
        "pts_for_slow",
        "pts_against_slow",
        "pts_for_fast",
        "pts_against_fast",
        "tempo_slow",
        "tempo_fast",
        "last_start",
        "games",
    )

    def __init__(self, league_ppg: float) -> None:
        self.pts_for_slow = league_ppg
        self.pts_against_slow = league_ppg
        self.pts_for_fast = league_ppg
        self.pts_against_fast = league_ppg
        self.tempo_slow = 0.0
        self.tempo_fast = 0.0
        self.last_start: datetime | None = None
        self.games = 0


def compute_pregame_team_ratings(games: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """
    Single chronological pass. For each game returns the pre-game feature values
    {home_off_rtg, home_def_rtg, home_pace, away_off_rtg, away_def_rtg, away_pace,
     home_rest_days, away_rest_days} using only results of games that started earlier.
    Synthetic games are ignored.
    """
    real_games = [g for g in games if not is_synthetic_game_id(g.get("game_id"))]
    real_games.sort(key=lambda g: (str(g.get("game_start_time", "")), str(g.get("game_id", ""))))

    league_ppg = LEAGUE_PPG_PRIOR
    league_total = 2.0 * LEAGUE_PPG_PRIOR
    teams: dict[str, _TeamState] = {}
    out: dict[str, dict[str, float]] = {}
    scale_100 = 100.0 / LEAGUE_PACE_BASE

    def _state(code: str, start: datetime) -> _TeamState:
        st = teams.get(code)
        if st is None:
            st = _TeamState(league_ppg)
            teams[code] = st
        elif st.last_start is not None and (start - st.last_start).days >= OFFSEASON_GAP_DAYS:
            # New season: regress toward the league mean
            st.pts_for_slow = league_ppg + OFFSEASON_CARRYOVER * (st.pts_for_slow - league_ppg)
            st.pts_against_slow = league_ppg + OFFSEASON_CARRYOVER * (st.pts_against_slow - league_ppg)
            st.pts_for_fast = st.pts_for_slow
            st.pts_against_fast = st.pts_against_slow
            st.tempo_slow *= 0.55
            st.tempo_fast = st.tempo_slow
            st.last_start = None
        return st

    def _rest(st: _TeamState, start: datetime) -> int:
        if st.last_start is None:
            return DEFAULT_REST_DAYS
        days = (start.date() - st.last_start.date()).days
        return int(max(1, min(MAX_REST_DAYS, days)))

    def _profile(st: _TeamState) -> tuple[float, float, float]:
        pf = 0.88 * st.pts_for_slow + 0.12 * st.pts_for_fast
        pa = 0.88 * st.pts_against_slow + 0.12 * st.pts_against_fast
        off = pf * scale_100
        deff = pa * scale_100
        tempo_blend = 0.72 * st.tempo_slow + 0.28 * st.tempo_fast
        pace = max(94.0, min(105.5, LEAGUE_PACE_BASE + 0.42 * tempo_blend))
        return round(off, 2), round(deff, 2), round(pace, 2)

    for g in real_games:
        start = parse_iso_utc(g["game_start_time"])
        h = _state(g["home_team"], start)
        a = _state(g["away_team"], start)

        h_off, h_def, h_pace = _profile(h)
        a_off, a_def, a_pace = _profile(a)
        out[g["game_id"]] = {
            "home_off_rtg": h_off,
            "home_def_rtg": h_def,
            "home_pace": h_pace,
            "away_off_rtg": a_off,
            "away_def_rtg": a_def,
            "away_pace": a_pace,
            "home_rest_days": _rest(h, start),
            "away_rest_days": _rest(a, start),
        }

        if g.get("status") != "FINAL" or g.get("home_score") is None or g.get("away_score") is None:
            continue

        hs, as_ = float(g["home_score"]), float(g["away_score"])
        raw_total = hs + as_
        raw_margin = hs - as_

        # Expected game total from pre-game offensive/defensive ratings + pre-game tempo
        exp_eff_total = (
            league_total
            + (h.pts_for_slow - league_ppg)
            + (a.pts_against_slow - league_ppg)
            + (a.pts_for_slow - league_ppg)
            + (h.pts_against_slow - league_ppg)
        )
        exp_game_total = exp_eff_total + h.tempo_slow + a.tempo_slow

        # Debias likely Overtime games (close final margin <= 7 with total >18 pts above expectation)
        is_likely_ot = (abs(raw_margin) <= 7.0) and (raw_total > exp_game_total + 18.0)
        reg_total = (raw_total - 13.0) if is_likely_ot else raw_total
        capped_total = max(league_total - 38.0, min(league_total + 38.0, reg_total))
        tempo_err = capped_total - exp_game_total

        # Huber blowout cap so 40-point tanking blowouts do not distort team efficiency
        capped_margin = max(-BLOWOUT_CAP_MARGIN, min(BLOWOUT_CAP_MARGIN, raw_margin))
        adj_hs = 0.5 * (capped_total + capped_margin)
        adj_as = 0.5 * (capped_total - capped_margin)

        # Opponent adjustment using PRE-game opponent strength and HCA (no leakage)
        h_for_adj = (adj_hs - HCA_PER_SIDE) - (a.pts_against_slow - league_ppg) - 0.35 * a.tempo_slow
        h_against_adj = (adj_as + HCA_PER_SIDE) - (a.pts_for_slow - league_ppg) - 0.35 * a.tempo_slow
        a_for_adj = (adj_as + HCA_PER_SIDE) - (h.pts_against_slow - league_ppg) - 0.35 * h.tempo_slow
        a_against_adj = (adj_hs - HCA_PER_SIDE) - (h.pts_for_slow - league_ppg) - 0.35 * h.tempo_slow

        for st, f_adj, ag_adj in ((h, h_for_adj, h_against_adj), (a, a_for_adj, a_against_adj)):
            st.pts_for_slow += EWMA_ALPHA_SLOW * (f_adj - st.pts_for_slow)
            st.pts_against_slow += EWMA_ALPHA_SLOW * (ag_adj - st.pts_against_slow)
            st.pts_for_fast += EWMA_ALPHA_FAST * (f_adj - st.pts_for_fast)
            st.pts_against_fast += EWMA_ALPHA_FAST * (ag_adj - st.pts_against_fast)
            st.tempo_slow += TEMPO_ALPHA_SLOW * tempo_err
            st.tempo_fast += TEMPO_ALPHA_FAST * tempo_err
            st.last_start = start
            st.games += 1

        league_ppg += LEAGUE_ALPHA * (0.5 * capped_total - league_ppg)
        league_total = 2.0 * league_ppg

    return out


def apply_pregame_team_ratings(db: Any) -> int:
    """
    Recomputes and persists leakage-free pre-game ratings for every real (non-synthetic) game.
    For SCHEDULED games enriched with live ESPN/Sportradar injury & Synergy context, preserves
    a bounded, zero-mean-shift acute net-rating delta while enforcing accurate schedule rest days.
    """
    games = db.fetch_all(
        """
        SELECT game_id, game_start_time, home_team, away_team, status, home_score, away_score,
               home_off_rtg, home_def_rtg, away_off_rtg, away_def_rtg, source_provider
        FROM games
        """
    )
    ratings = compute_pregame_team_ratings(games)
    if not ratings:
        return 0

    games_by_id = {g["game_id"]: g for g in games}
    rows = []
    for gid, r in ratings.items():
        g = games_by_id.get(gid, {})
        h_off, h_def, h_pace = r["home_off_rtg"], r["home_def_rtg"], r["home_pace"]
        a_off, a_def, a_pace = r["away_off_rtg"], r["away_def_rtg"], r["away_pace"]

        # If SCHEDULED and enriched by live adapter, blend bounded acute injury/Synergy net delta
        # symmetrically into off/def so total points expectation is never artificially depressed
        if (
            g.get("status") == "SCHEDULED"
            and g.get("source_provider") == "espn_v2_syndicate_enriched"
            and g.get("home_off_rtg") is not None
            and g.get("away_off_rtg") is not None
        ):
            live_net_diff = (float(g["home_off_rtg"]) - float(g["home_def_rtg"])) - (
                float(g["away_off_rtg"]) - float(g["away_def_rtg"])
            )
            hist_net_diff = (h_off - h_def) - (a_off - a_def)
            acute_delta = max(-4.0, min(4.0, 0.20 * (live_net_diff - hist_net_diff)))
            h_off = round(h_off + 0.25 * acute_delta, 2)
            h_def = round(h_def - 0.25 * acute_delta, 2)
            a_off = round(a_off - 0.25 * acute_delta, 2)
            a_def = round(a_def + 0.25 * acute_delta, 2)

        rows.append(
            (
                h_off,
                h_def,
                h_pace,
                a_off,
                a_def,
                a_pace,
                r["home_rest_days"],
                r["away_rest_days"],
                gid,
            )
        )

    with db.connect() as conn:
        conn.executemany(
            """
            UPDATE games SET home_off_rtg = ?, home_def_rtg = ?, home_pace = ?,
                             away_off_rtg = ?, away_def_rtg = ?, away_pace = ?,
                             home_rest_days = ?, away_rest_days = ?
            WHERE game_id = ?
            """,
            rows,
        )
    return len(rows)
