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
import json
from pathlib import Path
from typing import Any

from src.config import load_config
from src.validation.validator import parse_iso_utc

SYNTHETIC_PREFIX = "SYN_"

LEAGUE_PPG_PRIOR = 114.2
LEAGUE_PACE_BASE = 99.5
# Untuned structural EWMA priors, loaded from config/model_config.yaml (single source of truth).
# The former values 0.020 / 0.155 / 0.035 / 0.080 came from a leaked Optuna objective and were removed.
_MODEL_CFG = load_config().model
EWMA_ALPHA_SLOW = _MODEL_CFG.ewma_alpha_slow      # Structural opponent-adjusted efficiency
EWMA_ALPHA_FAST = _MODEL_CFG.ewma_alpha_fast      # High-frequency recent momentum/surge
TEMPO_ALPHA_SLOW = _MODEL_CFG.tempo_alpha_slow    # Decoupled pace adaptation
TEMPO_ALPHA_FAST = _MODEL_CFG.tempo_alpha_fast
LEAGUE_ALPHA = 0.015        # slow-moving league averages
OFFSEASON_GAP_DAYS = 60
OFFSEASON_CARRYOVER = 0.68  # retain 68% of prior season's true efficiency deviation
HCA_PER_SIDE = 0.925        # 1.85 pts total modern NBA home-court advantage
BLOWOUT_CAP_MARGIN = 26.0   # Huber cap on garbage-time blowout margins
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
        "efg_slow",
        "tov_slow",
        "orb_slow",
        "ftr_slow",
        "xefg_slow",
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
        self.efg_slow = 0.542
        self.tov_slow = 0.132
        self.orb_slow = 0.248
        self.ftr_slow = 0.215
        self.xefg_slow = 0.540


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
            st.efg_slow = 0.542 + 0.65 * (st.efg_slow - 0.542)
            st.tov_slow = 0.132 + 0.65 * (st.tov_slow - 0.132)
            st.orb_slow = 0.248 + 0.65 * (st.orb_slow - 0.248)
            st.ftr_slow = 0.215 + 0.65 * (st.ftr_slow - 0.215)
            st.xefg_slow = 0.540 + 0.65 * (st.xefg_slow - 0.540)
            st.last_start = None
        return st

    def _rest(st: _TeamState, start: datetime) -> int:
        if st.last_start is None:
            return DEFAULT_REST_DAYS
        days = (start.date() - st.last_start.date()).days
        return int(max(1, min(MAX_REST_DAYS, days)))

    def _profile(st: _TeamState) -> tuple[float, float, float, float, float, float, float, float]:
        pf = 0.88 * st.pts_for_slow + 0.12 * st.pts_for_fast
        pa = 0.88 * st.pts_against_slow + 0.12 * st.pts_against_fast
        off = pf * scale_100
        deff = pa * scale_100
        tempo_blend = 0.72 * st.tempo_slow + 0.28 * st.tempo_fast
        pace = max(94.0, min(105.5, LEAGUE_PACE_BASE + 0.42 * tempo_blend))
        return (
            round(off, 2),
            round(deff, 2),
            round(pace, 2),
            round(st.efg_slow, 4),
            round(st.tov_slow, 4),
            round(st.orb_slow, 4),
            round(st.ftr_slow, 4),
            round(st.xefg_slow, 4),
        )

    for g in real_games:
        start = parse_iso_utc(g["game_start_time"])
        h = _state(g["home_team"], start)
        a = _state(g["away_team"], start)

        h_off, h_def, h_pace, h_efg, h_tov, h_orb, h_ftr, h_xefg = _profile(h)
        a_off, a_def, a_pace, a_efg, a_tov, a_orb, a_ftr, a_xefg = _profile(a)
        ff_diff = (
            0.40 * (h_efg - a_efg)
            + 0.25 * (a_tov - h_tov)
            + 0.20 * (h_orb - a_orb)
            + 0.15 * (h_ftr - a_ftr)
        )
        xefg_diff = h_xefg - a_xefg
        out[g["game_id"]] = {
            "home_off_rtg": h_off,
            "home_def_rtg": h_def,
            "home_pace": h_pace,
            "away_off_rtg": a_off,
            "away_def_rtg": a_def,
            "away_pace": a_pace,
            "home_rest_days": _rest(h, start),
            "away_rest_days": _rest(a, start),
            "home_efg": h_efg,
            "away_efg": a_efg,
            "home_tov": h_tov,
            "away_tov": a_tov,
            "home_orb": h_orb,
            "away_orb": a_orb,
            "home_ftr": h_ftr,
            "away_ftr": a_ftr,
            "four_factors_diff": round(float(ff_diff), 4),
            "shot_quality_xeFG_diff": round(float(xefg_diff), 4),
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

        # V8 Garbage-Time Possession Filter (pbpstats-inspired clean possessions):
        # When raw_margin exceeds 18 pts, 4th-quarter bench units inflate/deflate tempo and uncontested points.
        # Apply smooth cubic transition discounting fast volatility and tempo error.
        margin_excess = max(0.0, abs(raw_margin) - 18.0)
        clean_possession_weight = max(0.50, min(1.0, 1.0 - 0.025 * margin_excess))
        effective_tempo_err = tempo_err * clean_possession_weight

        # Huber blowout cap so 40-point tanking blowouts do not distort team efficiency
        capped_margin = max(-BLOWOUT_CAP_MARGIN, min(BLOWOUT_CAP_MARGIN, raw_margin))
        adj_hs = 0.5 * (capped_total + capped_margin)
        adj_as = 0.5 * (capped_total - capped_margin)

        # Opponent adjustment using PRE-game opponent strength and HCA (no leakage)
        h_for_adj = (adj_hs - HCA_PER_SIDE) - (a.pts_against_slow - league_ppg) - 0.35 * a.tempo_slow
        h_against_adj = (adj_as + HCA_PER_SIDE) - (a.pts_for_slow - league_ppg) - 0.35 * a.tempo_slow
        a_for_adj = (adj_as + HCA_PER_SIDE) - (h.pts_against_slow - league_ppg) - 0.35 * h.tempo_slow
        a_against_adj = (adj_hs - HCA_PER_SIDE) - (h.pts_for_slow - league_ppg) - 0.35 * h.tempo_slow

        fast_alpha_eff = EWMA_ALPHA_FAST * clean_possession_weight
        for st, f_adj, ag_adj in ((h, h_for_adj, h_against_adj), (a, a_for_adj, a_against_adj)):
            st.pts_for_slow += EWMA_ALPHA_SLOW * (f_adj - st.pts_for_slow)
            st.pts_against_slow += EWMA_ALPHA_SLOW * (ag_adj - st.pts_against_slow)
            st.pts_for_fast += fast_alpha_eff * (f_adj - st.pts_for_fast)
            st.pts_against_fast += fast_alpha_eff * (ag_adj - st.pts_against_fast)
            st.tempo_slow += TEMPO_ALPHA_SLOW * effective_tempo_err
            st.tempo_fast += TEMPO_ALPHA_FAST * effective_tempo_err
            st.last_start = start
            st.games += 1

        # V8 Dean Oliver Four Factors Updates with shot quality xeFG
        ff_alpha = 0.040 * clean_possession_weight
        h_box = g.get("home_box_stats") or {}
        a_box = g.get("away_box_stats") or {}
        if h_box and "fieldGoalsMade" in h_box and "fieldGoalsAttempted" in h_box:
            h_fga = max(1.0, float(h_box.get("fieldGoalsAttempted", 88.0)))
            h_fgm = float(h_box.get("fieldGoalsMade", 44.0))
            h_3pm = float(h_box.get("threePointFieldGoalsMade", 13.0))
            h_tov = float(h_box.get("turnovers", 13.0))
            h_fta = float(h_box.get("freeThrowsAttempted", 22.0))
            h_orb = float(h_box.get("offensiveRebounds", 10.0))
            a_drb = float(a_box.get("defensiveRebounds", 34.0)) if a_box else 34.0
            obs_h_efg = (h_fgm + 0.5 * h_3pm) / h_fga
            obs_h_tov = h_tov / max(1.0, h_fga + 0.44 * h_fta + h_tov)
            obs_h_orb = h_orb / max(1.0, h_orb + a_drb)
            obs_h_ftr = h_fta / h_fga
            h_3fga = max(1.0, float(h_box.get("threePointFieldGoalsAttempted", 34.0)))
            obs_h_xefg = obs_h_efg - 0.35 * ((h_3pm / h_3fga) - 0.360)
        else:
            eff_delta_h = (adj_hs - league_ppg) / 100.0
            obs_h_efg = max(0.42, min(0.66, 0.542 + 0.50 * eff_delta_h))
            obs_h_tov = max(0.08, min(0.20, 0.132 - 0.22 * eff_delta_h))
            obs_h_orb = max(0.16, min(0.35, 0.248 + 0.18 * eff_delta_h))
            obs_h_ftr = max(0.14, min(0.32, 0.215 + 0.16 * eff_delta_h))
            obs_h_xefg = obs_h_efg

        if a_box and "fieldGoalsMade" in a_box and "fieldGoalsAttempted" in a_box:
            a_fga = max(1.0, float(a_box.get("fieldGoalsAttempted", 88.0)))
            a_fgm = float(a_box.get("fieldGoalsMade", 44.0))
            a_3pm = float(a_box.get("threePointFieldGoalsMade", 13.0))
            a_tov = float(a_box.get("turnovers", 13.0))
            a_fta = float(a_box.get("freeThrowsAttempted", 22.0))
            a_orb = float(a_box.get("offensiveRebounds", 10.0))
            h_drb = float(h_box.get("defensiveRebounds", 34.0)) if h_box else 34.0
            obs_a_efg = (a_fgm + 0.5 * a_3pm) / a_fga
            obs_a_tov = a_tov / max(1.0, a_fga + 0.44 * a_fta + a_tov)
            obs_a_orb = a_orb / max(1.0, a_orb + h_drb)
            obs_a_ftr = a_fta / a_fga
            a_3fga = max(1.0, float(a_box.get("threePointFieldGoalsAttempted", 34.0)))
            obs_a_xefg = obs_a_efg - 0.35 * ((a_3pm / a_3fga) - 0.360)
        else:
            eff_delta_a = (adj_as - league_ppg) / 100.0
            obs_a_efg = max(0.42, min(0.66, 0.542 + 0.50 * eff_delta_a))
            obs_a_tov = max(0.08, min(0.20, 0.132 - 0.22 * eff_delta_a))
            obs_a_orb = max(0.16, min(0.35, 0.248 + 0.18 * eff_delta_a))
            obs_a_ftr = max(0.14, min(0.32, 0.215 + 0.16 * eff_delta_a))
            obs_a_xefg = obs_a_efg

        h.efg_slow += ff_alpha * (obs_h_efg - h.efg_slow)
        h.tov_slow += ff_alpha * (obs_h_tov - h.tov_slow)
        h.orb_slow += ff_alpha * (obs_h_orb - h.orb_slow)
        h.ftr_slow += ff_alpha * (obs_h_ftr - h.ftr_slow)
        h.xefg_slow += ff_alpha * (obs_h_xefg - h.xefg_slow)

        a.efg_slow += ff_alpha * (obs_a_efg - a.efg_slow)
        a.tov_slow += ff_alpha * (obs_a_tov - a.tov_slow)
        a.orb_slow += ff_alpha * (obs_a_orb - a.orb_slow)
        a.ftr_slow += ff_alpha * (obs_a_ftr - a.ftr_slow)
        a.xefg_slow += ff_alpha * (obs_a_xefg - a.xefg_slow)

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
        FROM v_observed_games
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


# V7 Lineup Synergy & On/Off RAPM Role Profiles dynamically loaded from config/calibrated_weights.json
_SYNERGY_PROFILES_CACHE: dict[str, tuple[float, float, float, float, str]] | None = None
_LINEUP_SYNERGY_CONFIG_CACHE: Any = None


def get_player_on_off_synergy_profiles() -> dict[str, tuple[float, float, float, float, str]]:
    """Loads player on/off RAPM synergy profiles from calibrated weights JSON with fallback to default priors."""
    global _SYNERGY_PROFILES_CACHE
    if _SYNERGY_PROFILES_CACHE is not None:
        return _SYNERGY_PROFILES_CACHE

    profiles: dict[str, tuple[float, float, float, float, str]] = {}
    w_file = Path("config/calibrated_weights.json")
    if not w_file.exists():
        w_file = Path(__file__).resolve().parent.parent.parent / "config" / "calibrated_weights.json"
    if w_file.exists():
        try:
            raw_w = json.loads(w_file.read_text(encoding="utf-8")).get("player_synergy_profiles") or {}
            for name, val in raw_w.items():
                if isinstance(val, dict):
                    profiles[name] = (
                        float(val.get("net_rapm_pts", 3.0)),
                        float(val.get("off_share", 0.5)),
                        float(val.get("def_share", 0.5)),
                        float(val.get("pace_delta_when_out", 0.0)),
                        str(val.get("tactical_role", "TWO_WAY_WING")),
                    )
        except Exception:
            pass
    _SYNERGY_PROFILES_CACHE = profiles
    return profiles


PLAYER_ON_OFF_SYNERGY_PROFILES: dict[str, tuple[float, float, float, float, str]] = get_player_on_off_synergy_profiles()


def _get_lineup_synergy_config() -> Any:
    global _LINEUP_SYNERGY_CONFIG_CACHE
    if _LINEUP_SYNERGY_CONFIG_CACHE is None:
        try:
            from src.config import load_config
            _LINEUP_SYNERGY_CONFIG_CACHE = load_config().lineup_synergy
        except Exception:
            from src.config import LineupSynergyConfig
            _LINEUP_SYNERGY_CONFIG_CACHE = LineupSynergyConfig()
    return _LINEUP_SYNERGY_CONFIG_CACHE


def compute_lineup_synergy_penalty(absent_players: list[dict[str, Any]]) -> dict[str, float]:
    """
    V7 LineupSynergyEngine (pbpstats On/Off RAPM Role-Cluster Model):
    Computes non-linear compound lineup degradation when multiple players in the same tactical role
    (PRIMARY_INITIATOR, RIM_ANCHOR, TWO_WAY_WING) are simultaneously absent, and splits the impact
    asymmetrically into Offensive Rating penalty, Defensive Rating penalty, and Pace delta.
    """
    if not absent_players:
        return {
            "total_net_penalty": 0.0,
            "off_rtg_penalty": 0.0,
            "def_rtg_penalty": 0.0,
            "pace_delta": 0.0,
            "synergy_compound_bonus": 0.0,
        }

    syn_cfg = _get_lineup_synergy_config()
    profiles = get_player_on_off_synergy_profiles()
    off_pen_raw = 0.0
    def_pen_raw = 0.0
    pace_delta_raw = 0.0
    role_effective_units: dict[str, float] = {
        "PRIMARY_INITIATOR": 0.0,
        "RIM_ANCHOR": 0.0,
        "TWO_WAY_WING": 0.0,
        "ROTATION": 0.0,
    }
    role_off_acc: dict[str, float] = dict.fromkeys(role_effective_units, 0.0)
    role_def_acc: dict[str, float] = dict.fromkeys(role_effective_units, 0.0)

    for item in absent_players:
        p_name = str(item.get("name", "")).strip()
        status = str(item.get("status", "out")).lower()
        adapt_factor = float(item.get("adapt_factor", 1.0))
        pos_hint = str(item.get("position", "")).upper()

        if "out" in status:
            prob_out = 1.00
        elif "doubtful" in status:
            prob_out = 0.72
        elif "questionable" in status or "day" in status:
            prob_out = 0.28
        else:
            continue

        if p_name in profiles:
            base_val, off_sh, def_sh, p_delta, role = profiles[p_name]
            unit_weight = prob_out * adapt_factor
        else:
            base_val = float(item.get("default_impact", 0.45))
            if pos_hint in ("PG", "G"):
                off_sh, def_sh, p_delta, role = 0.68, 0.32, -0.15, "PRIMARY_INITIATOR"
            elif pos_hint in ("C", "F-C", "C-F"):
                off_sh, def_sh, p_delta, role = 0.36, 0.64, 0.10, "RIM_ANCHOR"
            elif pos_hint in ("SF", "PF", "F", "SG", "G-F"):
                off_sh, def_sh, p_delta, role = 0.54, 0.46, -0.05, "TWO_WAY_WING"
            else:
                off_sh, def_sh, p_delta, role = 0.50, 0.50, 0.0, "ROTATION"
            unit_weight = prob_out * adapt_factor * (0.65 if base_val >= 1.0 else 0.35)

        eff_impact = base_val * prob_out * adapt_factor
        o_i = eff_impact * off_sh
        d_i = eff_impact * def_sh

        off_pen_raw += o_i
        def_pen_raw += d_i
        pace_delta_raw += p_delta * prob_out * adapt_factor
        role_effective_units[role] = role_effective_units.get(role, 0.0) + unit_weight
        role_off_acc[role] = role_off_acc.get(role, 0.0) + o_i
        role_def_acc[role] = role_def_acc.get(role, 0.0) + d_i

    # Non-linear compound role-cluster synergy degradation:
    # 1. Playmaking vacuum: >= 1.25 effective initiators out compounds offensive degradation (+32%)
    compound_off_bonus = 0.0
    compound_def_bonus = 0.0
    if role_effective_units["PRIMARY_INITIATOR"] >= syn_cfg.initiator_absence_threshold:
        compound_off_bonus += syn_cfg.initiator_absence_penalty * role_off_acc["PRIMARY_INITIATOR"]
        pace_delta_raw -= 0.45
    # 2. Rim protection collapse: interior anchors out compounds defensive degradation
    if role_effective_units["RIM_ANCHOR"] >= syn_cfg.rim_anchor_absence_threshold:
        compound_def_bonus += syn_cfg.rim_anchor_absence_penalty * role_def_acc["RIM_ANCHOR"]
        pace_delta_raw += 0.35
    # 3. Wing creation depletion: effective wings out compounds both sides
    if role_effective_units["TWO_WAY_WING"] >= 1.40:
        compound_off_bonus += syn_cfg.two_way_wing_penalty * role_off_acc["TWO_WAY_WING"]
        compound_def_bonus += syn_cfg.two_way_wing_penalty * role_def_acc["TWO_WAY_WING"]

    # Multi-star cross-role vacuum (e.g. Jokic + Murray/Gordon or Embiid + Maxey out together)
    total_star_units = (
        role_effective_units["PRIMARY_INITIATOR"]
        + role_effective_units["RIM_ANCHOR"]
        + role_effective_units["TWO_WAY_WING"]
    )
    if total_star_units >= 1.75:
        compound_off_bonus += syn_cfg.compound_absence_penalty * off_pen_raw
        compound_def_bonus += syn_cfg.compound_absence_penalty * def_pen_raw

    raw_sum = off_pen_raw + def_pen_raw + compound_off_bonus + compound_def_bonus
    # Subtract normal bench injury baseline (~0.90 pt) unless explicit star compound shock
    baseline_deduction = float(absent_players[0].get("baseline_deduction", 0.90))
    if raw_sum <= baseline_deduction:
        return {
            "total_net_penalty": 0.0,
            "off_rtg_penalty": 0.0,
            "def_rtg_penalty": 0.0,
            "pace_delta": 0.0,
            "synergy_compound_bonus": 0.0,
        }

    scale_after_base = min(13.5, raw_sum - baseline_deduction) / max(1e-6, raw_sum)
    final_off = round((off_pen_raw + compound_off_bonus) * scale_after_base, 2)
    final_def = round((def_pen_raw + compound_def_bonus) * scale_after_base, 2)
    final_total = round(final_off + final_def, 2)
    final_compound = round((compound_off_bonus + compound_def_bonus) * scale_after_base, 2)
    final_pace = round(max(-2.5, min(2.0, pace_delta_raw)), 2)

    return {
        "total_net_penalty": final_total,
        "off_rtg_penalty": final_off,
        "def_rtg_penalty": final_def,
        "pace_delta": final_pace,
        "synergy_compound_bonus": final_compound,
    }
