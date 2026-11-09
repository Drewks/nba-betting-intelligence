"""
Leakage-free pre-game features from real box scores (possessions, Four Factors, player availability).

Single chronological pass: the features emitted for a game use only box scores of games that STARTED
EARLIER (and, with `info_lag_days`, at least that many days earlier). Box scores of the game itself
are applied to the team states only after its features were emitted.

What this adds over score-only ratings:
  - real possessions -> points per possession (offense / defense, opponent-adjusted) and true pace;
  - real Dean Oliver Four Factors (eFG%, TOV%, ORB%, FT rate), offense and defense;
  - availability proxy: regular-rotation minutes/points that were ABSENT in the team's most recent
    game (a player who sat out the last game is likely still out; live cycles can override this with
    the actual injury report).
"""

from __future__ import annotations

from collections import deque
from datetime import timedelta
from typing import Any

from src.validation.validator import parse_iso_utc

LEAGUE_PPP = 1.14
LEAGUE_PACE = 99.5
ALPHA_RATING = 0.06
ALPHA_FACTOR = 0.08
ALPHA_PLAYER = 0.25
HCA_PPP = 0.0125  # ~1.25 points per 100 possessions per side
ROTATION_MIN_MINUTES = 12.0
ROSTER_WINDOW_GAMES = 12
GAME_DURATION = timedelta(hours=3, minutes=30)

FEATURE_NAMES: tuple[str, ...] = (
    "bx_exp_margin", "bx_exp_total", "bx_net_ppp_diff", "bx_pace_avg",
    "bx_efg_diff", "bx_tov_diff", "bx_orb_diff", "bx_ftr_diff", "bx_tpa_rate_sum",
    "bx_missing_pts_diff", "bx_missing_pts_sum", "bx_missing_min_diff", "bx_new_absence_pts_diff",
    "bx_min_games",
)


def possessions(t: dict[str, float]) -> float:
    return t["fga"] + 0.44 * t["fta"] - t["orb"] + t["tov"]


class _Team:
    def __init__(self) -> None:
        self.off = LEAGUE_PPP
        self.deff = LEAGUE_PPP
        self.pace = LEAGUE_PACE
        self.efg, self.tov, self.orb, self.ftr, self.tpa = 0.545, 0.125, 0.25, 0.20, 0.42
        self.d_efg, self.d_tov, self.d_orb, self.d_ftr = 0.545, 0.125, 0.25, 0.20
        self.games = 0
        # name -> [avg_min, avg_pts, games_played, last_team_game_index_played]
        self.players: dict[str, list[float]] = {}
        self.recent_played: deque[set[str]] = deque(maxlen=4)

    def availability(self) -> tuple[float, float, float]:
        """(missing_minutes, missing_points, newly_missing_points) relative to the last game played."""
        if not self.recent_played:
            return 0.0, 0.0, 0.0
        last = self.recent_played[-1]
        prev = set().union(*list(self.recent_played)[:-1]) if len(self.recent_played) > 1 else set()
        miss_min = miss_pts = new_pts = 0.0
        for name, (avg_min, avg_pts, gp, last_idx) in self.players.items():
            if gp < 3 or avg_min < ROTATION_MIN_MINUTES or (self.games - last_idx) > ROSTER_WINDOW_GAMES:
                continue
            if name not in last:
                miss_min += avg_min
                miss_pts += avg_pts
                if name in prev:
                    new_pts += avg_pts
        return miss_min, miss_pts, new_pts


def _factors(t: dict[str, float], opp: dict[str, float]) -> tuple[float, float, float, float, float]:
    fga = max(1.0, t["fga"])
    efg = (t["fgm"] + 0.5 * t["tpm"]) / fga
    tov = t["tov"] / max(1.0, possessions(t))
    orb = t["orb"] / max(1.0, t["orb"] + opp["drb"])
    ftr = t["fta"] / fga
    return efg, tov, orb, ftr, t["tpa"] / fga


def compute_boxscore_features(
    games: list[dict[str, Any]],
    boxscores: dict[str, dict[str, Any]],
    info_lag_days: int = 0,
) -> dict[str, dict[str, float]]:
    """Returns {game_id: features}. `games` may include SCHEDULED games (they only read state)."""
    ordered = sorted(games, key=lambda g: (str(g["game_start_time"]), str(g["game_id"])))
    teams: dict[str, _Team] = {}
    league_ppp, league_pace = LEAGUE_PPP, LEAGUE_PACE
    out: dict[str, dict[str, float]] = {}
    pending: deque[tuple[Any, dict[str, Any]]] = deque()  # (available_from_dt, game) waiting to update states

    def _apply(g: dict[str, Any]) -> None:
        nonlocal league_ppp, league_pace
        box = boxscores.get(g["game_id"])
        if not box:
            return
        hc, ac = g["home_team"], g["away_team"]
        ht, at = box["teams"].get(hc), box["teams"].get(ac)
        if not ht or not at:
            return
        h, a = teams.setdefault(hc, _Team()), teams.setdefault(ac, _Team())
        poss = max(60.0, 0.5 * (possessions(ht) + possessions(at)))
        h_ppp, a_ppp = ht["pts"] / poss, at["pts"] / poss
        # Opponent- and venue-adjusted observations using PRE-update opponent states
        h_off_obs = h_ppp - HCA_PPP - (a.deff - league_ppp)
        h_def_obs = a_ppp + HCA_PPP - (a.off - league_ppp)
        a_off_obs = a_ppp + HCA_PPP - (h.deff - league_ppp)
        a_def_obs = h_ppp - HCA_PPP - (h.off - league_ppp)
        pace_obs_h = poss - (a.pace - league_pace)
        pace_obs_a = poss - (h.pace - league_pace)
        hf, af = _factors(ht, at), _factors(at, ht)
        for st, off_o, def_o, pace_o, own, opp in (
            (h, h_off_obs, h_def_obs, pace_obs_h, hf, af),
            (a, a_off_obs, a_def_obs, pace_obs_a, af, hf),
        ):
            al = max(ALPHA_RATING, 1.0 / (st.games + 1.0)) if st.games < 10 else ALPHA_RATING
            st.off += al * (off_o - st.off)
            st.deff += al * (def_o - st.deff)
            st.pace += al * (pace_o - st.pace)
            st.efg += ALPHA_FACTOR * (own[0] - st.efg)
            st.tov += ALPHA_FACTOR * (own[1] - st.tov)
            st.orb += ALPHA_FACTOR * (own[2] - st.orb)
            st.ftr += ALPHA_FACTOR * (own[3] - st.ftr)
            st.tpa += ALPHA_FACTOR * (own[4] - st.tpa)
            st.d_efg += ALPHA_FACTOR * (opp[0] - st.d_efg)
            st.d_tov += ALPHA_FACTOR * (opp[1] - st.d_tov)
            st.d_orb += ALPHA_FACTOR * (opp[2] - st.d_orb)
            st.d_ftr += ALPHA_FACTOR * (opp[3] - st.d_ftr)
            st.games += 1
        for code, st in ((hc, h), (ac, a)):
            played: set[str] = set()
            for p in box["players"].get(code) or []:
                if float(p.get("min") or 0.0) <= 0.0:
                    continue
                played.add(p["name"])
                rec = st.players.get(p["name"])
                if rec is None:
                    st.players[p["name"]] = [float(p["min"]), float(p["pts"]), 1.0, float(st.games)]
                else:
                    rec[0] += ALPHA_PLAYER * (float(p["min"]) - rec[0])
                    rec[1] += ALPHA_PLAYER * (float(p["pts"]) - rec[1])
                    rec[2] += 1.0
                    rec[3] = float(st.games)
            st.recent_played.append(played)
        league_ppp += 0.01 * (0.5 * (h_ppp + a_ppp) - league_ppp)
        league_pace += 0.01 * (poss - league_pace)

    lag = timedelta(days=info_lag_days)
    for g in ordered:
        start = parse_iso_utc(g["game_start_time"])
        # A game becomes usable only once it has certainly finished (tip-off + 3.5 h, plus the optional lag)
        while pending and pending[0][0] <= start:
            _apply(pending.popleft()[1])
        h, a = teams.get(g["home_team"]) or _Team(), teams.get(g["away_team"]) or _Team()
        pace = h.pace + a.pace - league_pace
        h_ppp = h.off + a.deff - league_ppp + HCA_PPP
        a_ppp = a.off + h.deff - league_ppp - HCA_PPP
        hm_min, hm_pts, hn_pts = h.availability()
        am_min, am_pts, an_pts = a.availability()
        out[g["game_id"]] = {
            "bx_exp_margin": round(pace * (h_ppp - a_ppp), 3),
            "bx_exp_total": round(pace * (h_ppp + a_ppp), 3),
            "bx_net_ppp_diff": round((h.off - h.deff) - (a.off - a.deff), 5),
            "bx_pace_avg": round(pace, 3),
            "bx_efg_diff": round((h.efg - h.d_efg) - (a.efg - a.d_efg), 5),
            "bx_tov_diff": round((h.d_tov - h.tov) - (a.d_tov - a.tov), 5),
            "bx_orb_diff": round((h.orb - h.d_orb) - (a.orb - a.d_orb), 5),
            "bx_ftr_diff": round((h.ftr - h.d_ftr) - (a.ftr - a.d_ftr), 5),
            "bx_tpa_rate_sum": round(h.tpa + a.tpa, 5),
            # positive = away team is missing more -> good for home
            "bx_missing_pts_diff": round(am_pts - hm_pts, 3),
            "bx_missing_pts_sum": round(am_pts + hm_pts, 3),
            "bx_missing_min_diff": round(am_min - hm_min, 3),
            "bx_new_absence_pts_diff": round(an_pts - hn_pts, 3),
            "bx_min_games": float(min(h.games, a.games)),
        }
        if g.get("status") == "FINAL" and g["game_id"] in boxscores:
            pending.append((start + GAME_DURATION + lag, g))
    return out


def attach_boxscore_features(
    games: list[dict[str, Any]],
    boxscores: dict[str, dict[str, Any]],
    info_lag_days: int = 0,
) -> list[dict[str, Any]]:
    """Returns copies of `games` with their pre-game bx_* features merged in."""
    feats = compute_boxscore_features(games, boxscores, info_lag_days=info_lag_days)
    return [{**g, **feats.get(g["game_id"], {})} for g in games]
