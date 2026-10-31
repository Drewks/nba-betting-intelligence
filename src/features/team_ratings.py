"""
Leakage-free pre-game team ratings computed ONLY from the project's own game history.

Replaces hard-coded priors, ESPN W-L records (which include the game itself once FINAL),
and the constant `rest_days = 2` placeholder with values derived strictly from games that
finished before each game's tip-off:

- Opponent-adjusted offensive / defensive ratings (points per 100 possessions proxy)
- Pace proxy (team combined-total tendency relative to the league)
- Real rest days from the schedule (1 = back-to-back)
- Season regression to the league mean when a team has a long layoff (offseason)

The same function is used for training rows (FINAL games) and for upcoming SCHEDULED games,
so train / predict feature distributions are identical.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.validation.validator import parse_iso_utc

SYNTHETIC_PREFIX = "SYN_"

LEAGUE_PPG_PRIOR = 114.0
LEAGUE_PACE_BASE = 99.5
EWMA_ALPHA = 0.08          # ~ 12-game half-life
LEAGUE_ALPHA = 0.01        # slow-moving league averages
OFFSEASON_GAP_DAYS = 60
OFFSEASON_CARRYOVER = 0.55  # keep 55% of last season's deviation from league mean
DEFAULT_REST_DAYS = 3
MAX_REST_DAYS = 5


def is_synthetic_game_id(game_id: str | None) -> bool:
    return str(game_id or "").startswith(SYNTHETIC_PREFIX)


class _TeamState:
    __slots__ = ("pts_for", "pts_against", "game_total", "last_start", "games")

    def __init__(self, league_ppg: float, league_total: float) -> None:
        self.pts_for = league_ppg
        self.pts_against = league_ppg
        self.game_total = league_total
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
    real_games.sort(key=lambda g: g["game_start_time"])

    league_ppg = LEAGUE_PPG_PRIOR
    league_total = 2.0 * LEAGUE_PPG_PRIOR
    teams: dict[str, _TeamState] = {}
    out: dict[str, dict[str, float]] = {}

    def _state(code: str, start: datetime) -> _TeamState:
        st = teams.get(code)
        if st is None:
            st = _TeamState(league_ppg, league_total)
            teams[code] = st
        elif st.last_start is not None and (start - st.last_start).days >= OFFSEASON_GAP_DAYS:
            # New season: regress toward the league mean
            st.pts_for = league_ppg + OFFSEASON_CARRYOVER * (st.pts_for - league_ppg)
            st.pts_against = league_ppg + OFFSEASON_CARRYOVER * (st.pts_against - league_ppg)
            st.game_total = league_total + OFFSEASON_CARRYOVER * (st.game_total - league_total)
            st.last_start = None
        return st

    def _rest(st: _TeamState, start: datetime) -> int:
        if st.last_start is None:
            return DEFAULT_REST_DAYS
        days = (start.date() - st.last_start.date()).days
        return int(max(1, min(MAX_REST_DAYS, days)))

    def _profile(st: _TeamState) -> tuple[float, float, float]:
        pace = LEAGUE_PACE_BASE * (st.game_total / max(150.0, league_total))
        off = st.pts_for * 100.0 / pace
        deff = st.pts_against * 100.0 / pace
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
        total = hs + as_
        # Opponent adjustment using PRE-game opponent strength (no leakage)
        h_for_adj = hs - (a.pts_against - league_ppg)
        h_against_adj = as_ - (a.pts_for - league_ppg)
        a_for_adj = as_ - (h.pts_against - league_ppg)
        a_against_adj = hs - (h.pts_for - league_ppg)

        for st, f_adj, ag_adj in ((h, h_for_adj, h_against_adj), (a, a_for_adj, a_against_adj)):
            st.pts_for += EWMA_ALPHA * (f_adj - st.pts_for)
            st.pts_against += EWMA_ALPHA * (ag_adj - st.pts_against)
            st.game_total += EWMA_ALPHA * (total - st.game_total)
            st.last_start = start
            st.games += 1

        league_ppg += LEAGUE_ALPHA * (0.5 * total - league_ppg)
        league_total += LEAGUE_ALPHA * (total - league_total)

    return out


def apply_pregame_team_ratings(db: Any) -> int:
    """Recomputes and persists leakage-free pre-game ratings for every real (non-synthetic) game."""
    games = db.fetch_all(
        "SELECT game_id, game_start_time, home_team, away_team, status, home_score, away_score FROM games"
    )
    ratings = compute_pregame_team_ratings(games)
    if not ratings:
        return 0
    rows = [
        (
            r["home_off_rtg"], r["home_def_rtg"], r["home_pace"],
            r["away_off_rtg"], r["away_def_rtg"], r["away_pace"],
            r["home_rest_days"], r["away_rest_days"], gid,
        )
        for gid, r in ratings.items()
    ]
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
