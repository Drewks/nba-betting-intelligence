"""
Leakage-free pre-game features from real box scores (possessions, exact 48-min regulation pace,
Four Factors, 3PT luck regression, participation-delta player availability, and RAPM context).

Single chronological pass: the features emitted for a game use only box scores of games that STARTED
EARLIER (and, with `info_lag_days`, at least that many days earlier). Box scores of the game itself
are applied to the team and career player states only after its pre-game features were emitted.

What this adds over score-only ratings:
  - real possessions -> points per possession (offense / defense, opponent-adjusted) and exact
    48-minute regulation pace (OT-debiased via summed player minutes when available);
  - real Dean Oliver Four Factors (eFG%, TOV%, ORB%, FT rate), offense and defense, plus 3PT luck;
  - offseason carryover regression and clean team-roster reset (>= 60-day gap) while preserving
    each player's causal multi-season career boxscore profile across trades/seasons;
  - participation-delta availability: unpriced absence shock weighted by how much each absent
    player actually participated in the team's recent rating window (zero double-counting), with
    live official NBA injury report OUT overrides applied identically to availability and lineup shares.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
import re
from typing import Any
import unicodedata

from src.validation.validator import parse_iso_utc

LEAGUE_PPP = 1.14
LEAGUE_PACE = 99.5
LEAGUE_3P_PCT = 0.362
LEAGUE_FT_PCT = 0.782
ALPHA_RATING = 0.06
ALPHA_FACTOR = 0.08
ALPHA_TP_LUCK = 0.14
ALPHA_PLAYER = 0.25
ALPHA_PART_SLOW = 0.06
HCA_PPP = 0.0125  # ~1.25 points per 100 possessions per side
ROTATION_MIN_MINUTES = 12.0
ROSTER_WINDOW_GAMES = 12
OFFSEASON_GAP_DAYS = 60
GAME_DURATION = timedelta(hours=3, minutes=30)

FEATURE_NAMES: tuple[str, ...] = (
    "bx_exp_margin",
    "bx_exp_total",
    "bx_net_ppp_diff",
    "bx_pace_avg",
    "bx_reg_pace_avg",
    "bx_efg_diff",
    "bx_tov_diff",
    "bx_orb_diff",
    "bx_ftr_diff",
    "bx_ftr_sum",
    "bx_tpa_rate_sum",
    "bx_tp_luck_diff",
    "bx_tp_luck_sum",
    "bx_missing_pts_diff",
    "bx_missing_pts_sum",
    "bx_missing_min_diff",
    "bx_new_absence_pts_diff",
    "bx_unpriced_pts_diff",
    "bx_unpriced_pts_sum",
    "bx_lineup_prior_diff",
    "bx_min_games",
)


_NAME_SUFFIX_TOKENS = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})


def player_name_key(name: str) -> str:
    """
    Diacritic- and generational-suffix-normalized alphanumeric key used to match ESPN box-score names
    with official NBA injury-report PDF names (e.g. 'Nikola Jokić' == 'Nikola Jokic',
    'Ernest Udeh Jr.' == 'Jr., Ernest Udeh').
    """
    ascii_str = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii").lower()
    tokens = [re.sub(r"[^a-z0-9]", "", tok) for tok in re.split(r"[\s,]+", ascii_str)]
    core = [tok for tok in tokens if tok and tok not in _NAME_SUFFIX_TOKENS]
    return "".join(core) if core else re.sub(r"[^a-z0-9]", "", ascii_str)


def possessions(t: dict[str, float]) -> float:
    return float(t["fga"]) + 0.44 * float(t["fta"]) - float(t["orb"]) + float(t["tov"])


class _CareerPlayerStats:
    __slots__ = ("ewma_pts36", "ewma_min", "ewma_start", "gp")

    def __init__(self) -> None:
        self.ewma_pts36: float = 15.0
        self.ewma_min: float = 15.0
        self.ewma_start: float = 0.30
        self.gp: float = 0.0

    def prior_value(self) -> float:
        """Strictly causal empirical-Bayes boxscore prior impact per 48-min slot."""
        w_sh = self.gp / (self.gp + 15.0)
        return w_sh * (
            0.12 * (self.ewma_pts36 - 15.0)
            + 0.08 * (self.ewma_min - 20.0)
            + 0.70 * (self.ewma_start - 0.35)
        )

    def update(self, minutes: float, pts: float, starter: float) -> None:
        p36 = max(2.0, min(42.0, 36.0 * pts / max(4.0, minutes)))
        alpha = max(0.06, 1.0 / (self.gp + 2.0))
        self.ewma_pts36 += alpha * (p36 - self.ewma_pts36)
        self.ewma_min += alpha * (minutes - self.ewma_min)
        self.ewma_start += alpha * (starter - self.ewma_start)
        self.gp += 1.0


class _Team:
    def __init__(self) -> None:
        self.off = LEAGUE_PPP
        self.deff = LEAGUE_PPP
        self.pace = LEAGUE_PACE
        self.reg_pace = LEAGUE_PACE
        self.efg, self.tov, self.orb, self.ftr, self.tpa = 0.545, 0.125, 0.25, 0.20, 0.42
        self.d_efg, self.d_tov, self.d_orb, self.d_ftr, self.d_tpa = 0.545, 0.125, 0.25, 0.20, 0.42
        self.tp_luck_o, self.tp_luck_d = 0.0, 0.0
        self.games = 0
        self.last_start: datetime | None = None
        # name -> [avg_min, avg_pts, games_played, last_team_game_index_played, ewma_part_slow]
        self.players: dict[str, list[float]] = {}
        self.recent_played: deque[set[str]] = deque(maxlen=4)

    def apply_offseason_reset(self, start: datetime, league_ppp: float, league_pace: float) -> None:
        """Regresses team profile toward league priors and clears stale prior-season roster state."""
        if self.last_start is None or (start - self.last_start).days < OFFSEASON_GAP_DAYS:
            return
        self.off = league_ppp + 0.65 * (self.off - league_ppp)
        self.deff = league_ppp + 0.65 * (self.deff - league_ppp)
        self.pace = league_pace + 0.55 * (self.pace - league_pace)
        self.reg_pace = league_pace + 0.55 * (self.reg_pace - league_pace)
        self.efg = 0.545 + 0.55 * (self.efg - 0.545)
        self.d_efg = 0.545 + 0.55 * (self.d_efg - 0.545)
        self.tov = 0.125 + 0.55 * (self.tov - 0.125)
        self.d_tov = 0.125 + 0.55 * (self.d_tov - 0.125)
        self.orb = 0.250 + 0.55 * (self.orb - 0.250)
        self.d_orb = 0.250 + 0.55 * (self.d_orb - 0.250)
        self.ftr = 0.200 + 0.55 * (self.ftr - 0.200)
        self.d_ftr = 0.200 + 0.55 * (self.d_ftr - 0.200)
        self.tpa = 0.420 + 0.55 * (self.tpa - 0.420)
        self.d_tpa = 0.420 + 0.55 * (self.d_tpa - 0.420)
        self.tp_luck_o *= 0.20
        self.tp_luck_d *= 0.20
        self.players = {}
        self.recent_played.clear()
        self.last_start = None

    def availability_from_out_list(self, out_keys: frozenset[str]) -> tuple[float, float, float, float]:
        """
        Same quantities as `availability`, but with the official injury report's OUT list instead of
        the "did not play the last game" proxy: rotation minutes/points of players ruled out, the
        points of those among them who played the last game (newly absent), and participation-weighted
        unpriced absence points.
        """
        last = self.recent_played[-1] if self.recent_played else set()
        miss_min = miss_pts = new_pts = unpriced_pts = 0.0
        for name, (avg_min, avg_pts, gp, last_idx, part_slow) in self.players.items():
            if gp < 3 or avg_min < ROTATION_MIN_MINUTES or (self.games - last_idx) > ROSTER_WINDOW_GAMES:
                continue
            if player_name_key(name) in out_keys:
                miss_min += avg_min
                miss_pts += avg_pts
                unpriced_pts += avg_pts * part_slow
                if name in last:
                    new_pts += avg_pts
        return miss_min, miss_pts, new_pts, unpriced_pts

    def availability(self) -> tuple[float, float, float, float]:
        """(missing_minutes, missing_points, newly_missing_points, unpriced_points) relative to last game."""
        if not self.recent_played:
            return 0.0, 0.0, 0.0, 0.0
        last = self.recent_played[-1]
        prev = set().union(*list(self.recent_played)[:-1]) if len(self.recent_played) > 1 else set()
        miss_min = miss_pts = new_pts = unpriced_pts = 0.0
        for name, (avg_min, avg_pts, gp, last_idx, part_slow) in self.players.items():
            if gp < 3 or avg_min < ROTATION_MIN_MINUTES or (self.games - last_idx) > ROSTER_WINDOW_GAMES:
                continue
            if name not in last:
                miss_min += avg_min
                miss_pts += avg_pts
                unpriced_pts += avg_pts * part_slow
                if name in prev:
                    new_pts += avg_pts
        return miss_min, miss_pts, new_pts, unpriced_pts

    def expected_lineup_shares(
        self,
        out_keys: frozenset[str] | None,
        career: dict[str, _CareerPlayerStats],
    ) -> tuple[dict[str, float], float]:
        """
        Builds strictly pre-game expected player minute shares (summing to 5.0 court slots) and
        their combined causal boxscore prior value from players in the team's most recent game.
        When `out_keys` is provided (live official injury report), removes players explicitly ruled
        OUT from that same base lineup so empty-OUT slates have exact train/serving parity (zero
        serving-only restoration skew); falls back to non-OUT recent players only if removing OUT
        players empties the lineup.
        """
        last = self.recent_played[-1] if self.recent_played else set()
        raw_m: dict[str, float] = {}
        if out_keys is not None:
            for name in last:
                if player_name_key(name) in out_keys:
                    continue
                rec = self.players.get(name)
                raw_m[name] = max(2.0, rec[0] if rec is not None else 15.0)
            if not raw_m and self.recent_played:
                recent_pool = set().union(*list(self.recent_played))
                for name in recent_pool:
                    if player_name_key(name) in out_keys:
                        continue
                    rec = self.players.get(name)
                    if rec is not None and (self.games - rec[3]) <= 4:
                        raw_m[name] = max(2.0, rec[0])
        elif last:
            for name in last:
                rec = self.players.get(name)
                raw_m[name] = max(2.0, rec[0] if rec is not None else 15.0)

        if not raw_m:
            return {}, 0.0
        tot_m = sum(raw_m.values()) or 240.0
        shares: dict[str, float] = {}
        prior_val = 0.0
        for name in sorted(raw_m):
            sh = 5.0 * raw_m[name] / tot_m
            shares[name] = sh
            c_st = career.get(name)
            if c_st is not None:
                prior_val += sh * c_st.prior_value()
        return shares, prior_val


def _factors(
    t: dict[str, float],
    opp: dict[str, float],
    league_3p_pct: float = LEAGUE_3P_PCT,
) -> tuple[float, float, float, float, float, float]:
    fga = max(1.0, float(t["fga"]))
    efg = (float(t["fgm"]) + 0.5 * float(t["tpm"])) / fga
    tov = float(t["tov"]) / max(1.0, possessions(t))
    orb = float(t["orb"]) / max(1.0, float(t["orb"]) + float(opp["drb"]))
    ftr = float(t["fta"]) / fga
    tpa_r = float(t["tpa"]) / fga
    tp_luck = (float(t["tpm"]) / max(1.0, float(t["tpa"]))) - league_3p_pct
    return efg, tov, orb, ftr, tpa_r, tp_luck


def _extract_post_obs_for_game(
    g: dict[str, Any],
    box: dict[str, Any],
    career: dict[str, _CareerPlayerStats],
    league_3p_pct: float = LEAGUE_3P_PCT,
    league_ft_pct: float = LEAGUE_FT_PCT,
) -> dict[str, Any] | None:
    """
    Computes clean post-game efficiency, exact 48-min regulation pace, luck-adjusted efficiency,
    causal OT addition, and actual player minute shares + boxscore stat tuples for a FINAL game
    (used strictly during training of prior games).
    """
    hc, ac = g["home_team"], g["away_team"]
    ht, at = box["teams"].get(hc), box["teams"].get(ac)
    if not ht or not at:
        return None
    hp = box["players"].get(hc) or []
    ap = box["players"].get(ac) or []
    h_min = sum(float(p.get("min") or 0.0) for p in hp)
    a_min = sum(float(p.get("min") or 0.0) for p in ap)
    team_min = 0.5 * (h_min + a_min) if (h_min >= 180.0 and a_min >= 180.0) else 240.0

    poss_raw = max(60.0, 0.5 * (possessions(ht) + possessions(at)))
    reg_pace = poss_raw * (240.0 / team_min)
    h_pts = float(ht["pts"])
    a_pts = float(at["pts"])
    h_ortg = 100.0 * h_pts / poss_raw
    a_ortg = 100.0 * a_pts / poss_raw
    act_tot = h_pts + a_pts
    ot_add = max(0.0, act_tot - act_tot * (240.0 / team_min)) if team_min > 250.0 else 0.0

    h_3p_ex = float(ht["tpm"]) - league_3p_pct * float(ht["tpa"])
    a_3p_ex = float(at["tpm"]) - league_3p_pct * float(at["tpa"])
    h_ftm = float(ht.get("ftm", league_ft_pct * float(ht["fta"])))
    a_ftm = float(at.get("ftm", league_ft_pct * float(at["fta"])))
    h_ft_ex = h_ftm - league_ft_pct * float(ht["fta"])
    a_ft_ex = a_ftm - league_ft_pct * float(at["fta"])
    h_ortg_la = 100.0 * (h_pts - 0.50 * 3.0 * h_3p_ex - 0.40 * h_ft_ex) / poss_raw
    a_ortg_la = 100.0 * (a_pts - 0.50 * 3.0 * a_3p_ex - 0.40 * a_ft_ex) / poss_raw

    home_shares: dict[str, float] = {}
    away_shares: dict[str, float] = {}
    home_pstats: list[tuple[str, float, float, float]] = []
    away_pstats: list[tuple[str, float, float, float]] = []
    prior_mar_offset = 0.0
    hm_tot = max(180.0, h_min) if h_min > 0.0 else 240.0
    for p in hp:
        mv = float(p.get("min") or 0.0)
        if mv > 0.0:
            pname = str(p["name"])
            pts_v = float(p.get("pts") or 0.0)
            st_v = 1.0 if p.get("starter") else 0.0
            sh = 5.0 * mv / hm_tot
            home_shares[pname] = home_shares.get(pname, 0.0) + sh
            home_pstats.append((pname, mv, pts_v, st_v))
            c_st = career.get(pname)
            if c_st is not None:
                prior_mar_offset += sh * c_st.prior_value()
    am_tot = max(180.0, a_min) if a_min > 0.0 else 240.0
    for p in ap:
        mv = float(p.get("min") or 0.0)
        if mv > 0.0:
            pname = str(p["name"])
            pts_v = float(p.get("pts") or 0.0)
            st_v = 1.0 if p.get("starter") else 0.0
            sh = 5.0 * mv / am_tot
            away_shares[pname] = away_shares.get(pname, 0.0) + sh
            away_pstats.append((pname, mv, pts_v, st_v))
            c_st = career.get(pname)
            if c_st is not None:
                prior_mar_offset -= sh * c_st.prior_value()

    return {
        "reg_pace": round(reg_pace, 4),
        "h_ortg": round(h_ortg, 4),
        "a_ortg": round(a_ortg, 4),
        "h_ortg_la": round(h_ortg_la, 4),
        "a_ortg_la": round(a_ortg_la, 4),
        "ot_add": round(ot_add, 4),
        "home_shares": home_shares,
        "away_shares": away_shares,
        "home_pstats": home_pstats,
        "away_pstats": away_pstats,
        "prior_mar_offset": round(prior_mar_offset, 5),
    }


def _run_boxscore_pass(
    games: list[dict[str, Any]],
    boxscores: dict[str, dict[str, Any]],
    info_lag_days: int = 0,
    availability_overrides: dict[str, dict[str, frozenset[str]]] | None = None,
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, Any]]]:
    """
    Single strictly causal chronological pass producing:
      1. `pregame_feats`: {game_id: dict[str, float]} containing strictly pre-game numeric features.
      2. `rapm_context`: {game_id: {"_bx_exp_lineup": (home_shares, away_shares), "_bx_post_obs": ...}}
         where `_bx_post_obs` is only populated for FINAL games with boxscores (never for SCHEDULED
         games and never read at prediction time for the target game).
    """
    overrides = availability_overrides or {}
    ordered = sorted(games, key=lambda g: (str(g["game_start_time"]), str(g["game_id"])))
    teams: dict[str, _Team] = {}
    career: dict[str, _CareerPlayerStats] = {}
    league_ppp, league_pace = LEAGUE_PPP, LEAGUE_PACE
    league_3p_pct, league_ft_pct = LEAGUE_3P_PCT, LEAGUE_FT_PCT
    pregame_feats: dict[str, dict[str, float]] = {}
    rapm_context: dict[str, dict[str, Any]] = {}
    pending: deque[tuple[datetime, dict[str, Any]]] = deque()

    def _apply(g: dict[str, Any]) -> None:
        nonlocal league_ppp, league_pace, league_3p_pct, league_ft_pct
        box = boxscores.get(g["game_id"])
        if not box:
            return
        hc, ac = g["home_team"], g["away_team"]
        ht, at = box["teams"].get(hc), box["teams"].get(ac)
        if not ht or not at:
            return
        start_g = parse_iso_utc(g["game_start_time"])
        h = teams.setdefault(hc, _Team())
        a = teams.setdefault(ac, _Team())
        h.apply_offseason_reset(start_g, league_ppp, league_pace)
        a.apply_offseason_reset(start_g, league_ppp, league_pace)

        # Snapshot post-game clean observation using strictly pre-update causal league & career priors
        post_obs = _extract_post_obs_for_game(g, box, career, league_3p_pct=league_3p_pct, league_ft_pct=league_ft_pct)
        if post_obs is not None:
            rapm_context.setdefault(g["game_id"], {})["_bx_post_obs"] = post_obs

        hp = box["players"].get(hc) or []
        ap = box["players"].get(ac) or []
        h_min = sum(float(p.get("min") or 0.0) for p in hp)
        a_min = sum(float(p.get("min") or 0.0) for p in ap)
        team_min = 0.5 * (h_min + a_min) if (h_min >= 180.0 and a_min >= 180.0) else 240.0

        poss = max(60.0, 0.5 * (possessions(ht) + possessions(at)))
        reg_poss = poss * (240.0 / team_min)
        h_ppp, a_ppp = float(ht["pts"]) / poss, float(at["pts"]) / poss
        h_off_obs = h_ppp - HCA_PPP - (a.deff - league_ppp)
        h_def_obs = a_ppp + HCA_PPP - (a.off - league_ppp)
        a_off_obs = a_ppp + HCA_PPP - (h.deff - league_ppp)
        a_def_obs = h_ppp - HCA_PPP - (h.off - league_ppp)
        pace_obs_h = poss - (a.pace - league_pace)
        pace_obs_a = poss - (h.pace - league_pace)
        rpace_obs_h = reg_poss - (a.reg_pace - league_pace)
        rpace_obs_a = reg_poss - (h.reg_pace - league_pace)
        hf = _factors(ht, at, league_3p_pct=league_3p_pct)
        af = _factors(at, ht, league_3p_pct=league_3p_pct)
        for st, off_o, def_o, pace_o, rpace_o, own, opp in (
            (h, h_off_obs, h_def_obs, pace_obs_h, rpace_obs_h, hf, af),
            (a, a_off_obs, a_def_obs, pace_obs_a, rpace_obs_a, af, hf),
        ):
            al = max(ALPHA_RATING, 1.0 / (st.games + 1.0)) if st.games < 10 else ALPHA_RATING
            st.off += al * (off_o - st.off)
            st.deff += al * (def_o - st.deff)
            st.pace += al * (pace_o - st.pace)
            st.reg_pace += al * (rpace_o - st.reg_pace)
            st.efg += ALPHA_FACTOR * (own[0] - st.efg)
            st.tov += ALPHA_FACTOR * (own[1] - st.tov)
            st.orb += ALPHA_FACTOR * (own[2] - st.orb)
            st.ftr += ALPHA_FACTOR * (own[3] - st.ftr)
            st.tpa += ALPHA_FACTOR * (own[4] - st.tpa)
            st.d_efg += ALPHA_FACTOR * (opp[0] - st.d_efg)
            st.d_tov += ALPHA_FACTOR * (opp[1] - st.d_tov)
            st.d_orb += ALPHA_FACTOR * (opp[2] - st.d_orb)
            st.d_ftr += ALPHA_FACTOR * (opp[3] - st.d_ftr)
            st.d_tpa += ALPHA_FACTOR * (opp[4] - st.d_tpa)
            st.tp_luck_o += ALPHA_TP_LUCK * (own[5] - st.tp_luck_o)
            st.tp_luck_d += ALPHA_TP_LUCK * (opp[5] - st.tp_luck_d)
            st.games += 1
            st.last_start = start_g
        for code, st in ((hc, h), (ac, a)):
            played: set[str] = set()
            for p in box["players"].get(code) or []:
                mv = float(p.get("min") or 0.0)
                if mv <= 0.0:
                    continue
                pname = str(p["name"])
                pts_v = float(p.get("pts") or 0.0)
                starter_v = 1.0 if p.get("starter") else 0.0
                played.add(pname)
                c_st = career.setdefault(pname, _CareerPlayerStats())
                c_st.update(mv, pts_v, starter_v)
                rec = st.players.get(pname)
                if rec is None:
                    st.players[pname] = [mv, pts_v, 1.0, float(st.games), 0.25]
                else:
                    rec[0] += ALPHA_PLAYER * (mv - rec[0])
                    rec[1] += ALPHA_PLAYER * (pts_v - rec[1])
                    rec[2] += 1.0
                    rec[3] = float(st.games)
                    rec[4] += ALPHA_PART_SLOW * (1.0 - rec[4])
            for pname, rec in st.players.items():
                if pname not in played:
                    rec[4] *= (1.0 - ALPHA_PART_SLOW)
            st.recent_played.append(played)
        league_ppp += 0.01 * (0.5 * (h_ppp + a_ppp) - league_ppp)
        league_pace += 0.01 * (reg_poss - league_pace)
        tot_tpa = float(ht["tpa"]) + float(at["tpa"])
        if tot_tpa > 0.0:
            game_3p = (float(ht["tpm"]) + float(at["tpm"])) / tot_tpa
            league_3p_pct += 0.008 * (game_3p - league_3p_pct)
        tot_fta = float(ht["fta"]) + float(at["fta"])
        if tot_fta > 0.0 and "ftm" in ht and "ftm" in at:
            game_ft = (float(ht["ftm"]) + float(at["ftm"])) / tot_fta
            league_ft_pct += 0.008 * (game_ft - league_ft_pct)

    lag = timedelta(days=info_lag_days)
    for g in ordered:
        start = parse_iso_utc(g["game_start_time"])
        while pending and pending[0][0] <= start:
            _apply(pending.popleft()[1])

        h = teams.get(g["home_team"])
        if h is not None:
            h.apply_offseason_reset(start, league_ppp, league_pace)
        else:
            h = _Team()
        a = teams.get(g["away_team"])
        if a is not None:
            a.apply_offseason_reset(start, league_ppp, league_pace)
        else:
            a = _Team()

        pace = h.pace + a.pace - league_pace
        reg_pace = h.reg_pace + a.reg_pace - league_pace
        h_ppp = h.off + a.deff - league_ppp + HCA_PPP
        a_ppp = a.off + h.deff - league_ppp - HCA_PPP

        game_overrides = overrides.get(g["game_id"]) or {}
        h_out = game_overrides.get(g["home_team"])
        a_out = game_overrides.get(g["away_team"])
        hm_min, hm_pts, hn_pts, hu_pts = (
            h.availability_from_out_list(h_out) if h_out is not None else h.availability()
        )
        am_min, am_pts, an_pts, au_pts = (
            a.availability_from_out_list(a_out) if a_out is not None else a.availability()
        )
        h_shares, h_prior = h.expected_lineup_shares(h_out, career)
        a_shares, a_prior = a.expected_lineup_shares(a_out, career)

        pregame_feats[g["game_id"]] = {
            "bx_exp_margin": round(reg_pace * (h_ppp - a_ppp), 3),
            "bx_exp_total": round(reg_pace * (h_ppp + a_ppp), 3),
            "bx_net_ppp_diff": round((h.off - h.deff) - (a.off - a.deff), 5),
            "bx_pace_avg": round(pace, 3),
            "bx_reg_pace_avg": round(reg_pace, 3),
            "bx_efg_diff": round((h.efg - h.d_efg) - (a.efg - a.d_efg), 5),
            "bx_tov_diff": round((h.d_tov - h.tov) - (a.d_tov - a.tov), 5),
            "bx_orb_diff": round((h.orb - h.d_orb) - (a.orb - a.d_orb), 5),
            "bx_ftr_diff": round((h.ftr - h.d_ftr) - (a.ftr - a.d_ftr), 5),
            "bx_ftr_sum": round(h.ftr + a.ftr + h.d_ftr + a.d_ftr, 5),
            "bx_tpa_rate_sum": round(h.tpa + a.tpa, 5),
            "bx_tp_luck_diff": round((h.tp_luck_o - h.tp_luck_d) - (a.tp_luck_o - a.tp_luck_d), 5),
            "bx_tp_luck_sum": round(h.tp_luck_o + a.tp_luck_o + h.tp_luck_d + a.tp_luck_d, 5),
            # positive = away team is missing more -> good for home
            "bx_missing_pts_diff": round(am_pts - hm_pts, 3),
            "bx_missing_pts_sum": round(am_pts + hm_pts, 3),
            "bx_missing_min_diff": round(am_min - hm_min, 3),
            "bx_new_absence_pts_diff": round(an_pts - hn_pts, 3),
            "bx_unpriced_pts_diff": round(au_pts - hu_pts, 3),
            "bx_unpriced_pts_sum": round(au_pts + hu_pts, 3),
            "bx_lineup_prior_diff": round(h_prior - a_prior, 4),
            "bx_min_games": float(min(h.games, a.games)),
        }
        rapm_context[g["game_id"]] = {
            "_bx_exp_lineup": (h_shares, a_shares),
        }
        if g.get("status") == "FINAL" and g["game_id"] in boxscores:
            pending.append((start + GAME_DURATION + lag, g))

    # Flush remaining pending FINAL games so their `_bx_post_obs` is available for future training
    while pending:
        _apply(pending.popleft()[1])

    return pregame_feats, rapm_context


def compute_boxscore_features(
    games: list[dict[str, Any]],
    boxscores: dict[str, dict[str, Any]],
    info_lag_days: int = 0,
    availability_overrides: dict[str, dict[str, frozenset[str]]] | None = None,
) -> dict[str, dict[str, float]]:
    """
    Returns strictly pre-game `{game_id: dict[str, float]}`. `games` may include SCHEDULED games
    (they only read state). Never includes any data derived from `boxscores[game_id]` itself.
    """
    pregame_feats, _ = _run_boxscore_pass(
        games,
        boxscores,
        info_lag_days=info_lag_days,
        availability_overrides=availability_overrides,
    )
    return pregame_feats


def compute_boxscore_feature_bundle(
    games: list[dict[str, Any]],
    boxscores: dict[str, dict[str, Any]],
    info_lag_days: int = 0,
    availability_overrides: dict[str, dict[str, frozenset[str]]] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Returns `{game_id: {bx_* floats + _bx_exp_lineup + (_bx_post_obs for FINAL games only)}}`
    so production and backtest callers can enrich games in one chronological pass.
    """
    pregame_feats, rapm_ctx = _run_boxscore_pass(
        games,
        boxscores,
        info_lag_days=info_lag_days,
        availability_overrides=availability_overrides,
    )
    return {
        gid: {**pregame_feats.get(gid, {}), **rapm_ctx.get(gid, {})}
        for gid in pregame_feats
    }


def attach_boxscore_features(
    games: list[dict[str, Any]],
    boxscores: dict[str, dict[str, Any]],
    info_lag_days: int = 0,
    availability_overrides: dict[str, dict[str, frozenset[str]]] | None = None,
) -> list[dict[str, Any]]:
    """Returns copies of `games` with their pre-game `bx_*` features and RAPM context merged in."""
    bundle = compute_boxscore_feature_bundle(
        games,
        boxscores,
        info_lag_days=info_lag_days,
        availability_overrides=availability_overrides,
    )
    return [{**g, **bundle.get(g["game_id"], {})} for g in games]
