"""
Modelo H: Simultaneous Multi-Horizon Time-Decayed Ridge Adjusted Efficiency &
Prior-Informed Game-Level Player Margin + Off/Def RAPM Engine (`src/models/ridge_rapm.py`).

Solves simultaneously over strictly prior finalized games (`game_start_time < cutoff_time_str`):
  1. Multi-horizon (slow + fast) opponent-adjusted Net Margin per 100 possessions (with HCA & situational
     de-biasing and 3PT/FT shooting-luck blending).
  2. Multi-horizon opponent-adjusted Offensive & Defensive Rating per 100 possessions.
  3. Multi-horizon exact 48-minute Regulation Pace (OT-debiased via real boxscore player minutes) and
     strictly causal expected OT scoring addition (zero hardcoded constant drift).
  4. Prior-informed Game-Level Player Margin RAPM via sparse damped least squares (`lsqr`) on real
     boxscore minute shares centered on consistent cutoff-time causal player priors with an un-damped
     HCA intercept, so talent transfers immediately across trades, offseasons, and live injury OUT overrides.
  5. Mean-centered Game-Level Player Offensive & Defensive RAPM (`rapm_total`), immediately re-pricing
     expected game totals when high-usage scorers or elite rim protectors sit out or return.

Gracefully falls back to score-only simultaneous Ridge when boxscore context is absent (e.g. unit tests).
100% deterministic (lexicographically sorted team/player indices, exact linear solves).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import lsqr

from src.config import RidgeRAPMConfig, load_config
from src.features.builder import build_pregame_features
from src.models.common import _filter_strictly_prior_final_games
from src.validation.validator import parse_iso_utc


def _load_ridge_rapm_config() -> RidgeRAPMConfig:
    try:
        return load_config().model.ridge_rapm
    except Exception:
        return RidgeRAPMConfig()


def _update_career_state_from_game(
    career: dict[str, list[float]],
    game: dict[str, Any],
) -> None:
    """Incrementally advances per-player career boxscore stats from a strictly prior finalized game."""
    post_obs = game.get("_bx_post_obs")
    if not isinstance(post_obs, dict):
        return
    for key in ("home_pstats", "away_pstats"):
        pstats = post_obs.get(key)
        if not pstats:
            continue
        for pname, mv, pts_v, st_v in pstats:
            p36 = max(2.0, min(42.0, 36.0 * float(pts_v) / max(4.0, float(mv))))
            rec = career.get(pname)
            if rec is None:
                rec = [15.0, 15.0, 0.30, 0.0]
                career[pname] = rec
            al = max(0.06, 1.0 / (rec[3] + 2.0))
            rec[0] += al * (p36 - rec[0])
            rec[1] += al * (float(mv) - rec[1])
            rec[2] += al * (float(st_v) - rec[2])
            rec[3] += 1.0


def _priors_from_career_state(career: dict[str, list[float]]) -> dict[str, float]:
    return {
        pname: (rec[3] / (rec[3] + 15.0))
        * (0.12 * (rec[0] - 15.0) + 0.08 * (rec[1] - 20.0) + 0.70 * (rec[2] - 0.35))
        for pname, rec in career.items()
    }


def _build_cutoff_player_priors(
    prior_games: list[dict[str, Any]],
) -> dict[str, float]:
    """
    Computes strictly causal empirical-Bayes per-player boxscore priors as of the training cutoff
    from all strictly prior finalized boxscores, ensuring identical prior centering in RAPM training
    and pre-game inference (zero prior-ramp double-counting).
    """
    career: dict[str, list[float]] = {}
    for g in prior_games:
        _update_career_state_from_game(career, g)
    return _priors_from_career_state(career)


class RidgeEfficiencyRAPMModel:
    """
    Simultaneous Multi-Horizon Ridge Adjusted Efficiency + Prior-Informed Player Margin & Off/Def RAPM.
    Strictly zero lookahead: `predict_matchup` never reads post-game observations on `game`.
    """

    model_family = "model_h_ridge_rapm"

    def __init__(
        self,
        version_id: str = "model_h_ridge_rapm_v9",
        config: RidgeRAPMConfig | None = None,
    ) -> None:
        self.version_id = version_id
        self.config = config or _load_ridge_rapm_config()
        self.is_fitted: bool = False
        self.rapm_fitted: bool = False
        self.od_rapm_fitted: bool = False
        self.team_index: dict[str, int] = {}
        self.player_index: dict[str, int] = {}
        self._player_priors: dict[str, float] = {}
        self._has_cutoff_priors: bool = False

        # Slow & fast solved team vectors
        self._s_slow: np.ndarray = np.empty(0)
        self._hca_m_slow: float = 1.85
        self._o_slow: np.ndarray = np.empty(0)
        self._d_slow: np.ndarray = np.empty(0)
        self._mu_e_slow: float = 114.2
        self._hca_e_slow: float = 0.925
        self._p_slow: np.ndarray = np.empty(0)
        self._mu_p_slow: float = 99.5

        self._s_fast: np.ndarray = np.empty(0)
        self._hca_m_fast: float = 1.85
        self._o_fast: np.ndarray = np.empty(0)
        self._d_fast: np.ndarray = np.empty(0)
        self._mu_e_fast: float = 114.2
        self._hca_e_fast: float = 0.925
        self._p_fast: np.ndarray = np.empty(0)
        self._mu_p_fast: float = 99.5

        # Causal OT points addition (0.0 when score-only fallback without regulation pace)
        self._ot_add: float = 0.0

        # Prior-informed Player Margin RAPM delta vector + un-damped HCA
        self._rapm_delta: np.ndarray = np.empty(0)
        self._rapm_hca: float = 1.85

        # Mean-centered Player Offensive & Defensive RAPM vectors (for player-aware totals)
        self._rapm_off: np.ndarray = np.empty(0)
        self._rapm_def: np.ndarray = np.empty(0)
        self._rapm_mu_e: float = 114.2
        self._rapm_hca_e: float = 0.925

    def _fit_from_extracted(
        self,
        *,
        sample: list[dict[str, Any]],
        prior_all: list[dict[str, Any]],
        cutoff_sec: float,
        extracted: dict[str, dict[str, Any]],
        precomputed_cutoff_priors: dict[str, float] | None = None,
    ) -> None:
        self.is_fitted = False
        self.rapm_fitted = False
        self.od_rapm_fitted = False
        if not self.config.enabled or len(sample) < self.config.min_games_for_team_ridge:
            return

        teams = sorted({str(g["home_team"]) for g in sample} | {str(g["away_team"]) for g in sample})
        if len(teams) < 2:
            return
        t_idx = {t: i for i, t in enumerate(teams)}
        nt = len(teams)
        n_games = len(sample)
        cur_season = str(sample[-1].get("season") or "")
        cfg = self.config

        ts_sec = np.zeros(n_games, dtype=float)
        same_season = np.zeros(n_games, dtype=bool)
        x_mar = np.zeros((n_games, nt + 1), dtype=float)
        x_eff_h = np.zeros((n_games, 2 * nt + 2), dtype=float)
        x_eff_a = np.zeros((n_games, 2 * nt + 2), dtype=float)
        x_pace = np.zeros((n_games, nt + 1), dtype=float)

        y_net = np.zeros(n_games, dtype=float)
        y_ho = np.zeros(n_games, dtype=float)
        y_ao = np.zeros(n_games, dtype=float)
        y_pace = np.zeros(n_games, dtype=float)
        ot_adds = np.zeros(n_games, dtype=float)
        has_box_mask = np.zeros(n_games, dtype=bool)

        player_set: set[str] = set()
        rapm_game_rows: list[tuple[int, dict[str, float], dict[str, float], float]] = []

        for idx, g in enumerate(sample):
            gid = str(g["game_id"])
            rec = extracted[gid]
            ts_sec[idx] = float(rec["ts_sec"])
            same_season[idx] = str(rec["season"]) == cur_season
            hi = t_idx[str(g["home_team"])]
            ai = t_idx[str(g["away_team"])]

            y_net[idx] = float(rec["y_net"])
            y_ho[idx] = float(rec["y_ho"])
            y_ao[idx] = float(rec["y_ao"])
            y_pace[idx] = float(rec["y_pace"])
            ot_adds[idx] = float(rec["ot_add"])
            has_box_mask[idx] = bool(rec["has_box"])

            h_sh = rec["home_shares"]
            a_sh = rec["away_shares"]
            if h_sh and a_sh:
                player_set.update(h_sh.keys())
                player_set.update(a_sh.keys())
                rapm_game_rows.append((idx, h_sh, a_sh, float(rec["prior_mar_offset"])))

            x_mar[idx, hi] = 1.0
            x_mar[idx, ai] = -1.0
            x_mar[idx, nt] = 1.0
            x_eff_h[idx, hi] = 1.0
            x_eff_h[idx, nt + ai] = 1.0
            x_eff_h[idx, 2 * nt] = 1.0
            x_eff_h[idx, 2 * nt + 1] = 1.0
            x_eff_a[idx, ai] = 1.0
            x_eff_a[idx, nt + hi] = 1.0
            x_eff_a[idx, 2 * nt] = 1.0
            x_eff_a[idx, 2 * nt + 1] = -1.0
            x_pace[idx, hi] = 1.0
            x_pace[idx, ai] = 1.0
            x_pace[idx, nt] = 1.0

        ages = np.maximum(0.0, (cutoff_sec - ts_sec) / 86400.0)
        ln2 = math.log(2.0)

        def _solve_horizon(
            hl_days: float,
            s_decay: float,
            lam_m: float,
            lam_e: float,
            lam_p: float,
        ) -> tuple[np.ndarray, float, np.ndarray, np.ndarray, float, float, np.ndarray, float, np.ndarray]:
            w = np.exp(-ln2 * ages / hl_days)
            w = np.where(same_season, w, w * s_decay)

            i_m = np.eye(nt + 1, dtype=float)
            i_m[nt, nt] = 1e-4 / max(1e-6, lam_m)
            z_m = np.zeros((nt + 1, nt + 1), dtype=float)
            z_m[:nt, :nt] = 10.0
            th_m = np.linalg.solve((x_mar.T * w) @ x_mar + lam_m * i_m + z_m, x_mar.T @ (w * y_net))

            i_e = np.eye(2 * nt + 2, dtype=float)
            i_e[2 * nt, 2 * nt] = 1e-4 / max(1e-6, lam_e)
            i_e[2 * nt + 1, 2 * nt + 1] = 1e-4 / max(1e-6, lam_e)
            z_e = np.zeros((2 * nt + 2, 2 * nt + 2), dtype=float)
            z_e[:nt, :nt] = 10.0
            z_e[nt : 2 * nt, nt : 2 * nt] = 10.0
            ea = (x_eff_h.T * w) @ x_eff_h + (x_eff_a.T * w) @ x_eff_a + lam_e * i_e + z_e
            eb = x_eff_h.T @ (w * y_ho) + x_eff_a.T @ (w * y_ao)
            th_e = np.linalg.solve(ea, eb)

            i_p = np.eye(nt + 1, dtype=float)
            i_p[nt, nt] = 1e-4 / max(1e-6, lam_p)
            z_p = np.zeros((nt + 1, nt + 1), dtype=float)
            z_p[:nt, :nt] = 10.0
            th_p = np.linalg.solve((x_pace.T * w) @ x_pace + lam_p * i_p + z_p, x_pace.T @ (w * y_pace))

            return (
                th_m[:nt],
                float(th_m[nt]),
                th_e[:nt],
                th_e[nt : 2 * nt],
                float(th_e[2 * nt]),
                float(th_e[2 * nt + 1]),
                th_p[:nt],
                float(th_p[nt]),
                w,
            )

        (
            self._s_slow,
            self._hca_m_slow,
            self._o_slow,
            self._d_slow,
            self._mu_e_slow,
            self._hca_e_slow,
            self._p_slow,
            self._mu_p_slow,
            w_slow,
        ) = _solve_horizon(
            cfg.slow_half_life_days,
            cfg.slow_season_decay,
            cfg.lam_margin_slow,
            cfg.lam_eff_slow,
            cfg.lam_pace_slow,
        )

        (
            self._s_fast,
            self._hca_m_fast,
            self._o_fast,
            self._d_fast,
            self._mu_e_fast,
            self._hca_e_fast,
            self._p_fast,
            self._mu_p_fast,
            _w_fast,
        ) = _solve_horizon(
            cfg.fast_half_life_days,
            cfg.fast_season_decay,
            cfg.lam_margin_fast,
            cfg.lam_eff_fast,
            cfg.lam_pace_fast,
        )

        # Causal expected OT scoring addition (only when regulation pace from boxscores is active)
        if np.any(has_box_mask):
            w_box = w_slow[has_box_mask]
            w_sum = float(np.sum(w_box))
            if w_sum > 1e-9:
                self._ot_add = float(np.clip(float(np.sum(w_box * ot_adds[has_box_mask])) / w_sum, 0.0, 2.5))
            else:
                self._ot_add = 1.25
        else:
            self._ot_add = 0.0

        self.team_index = t_idx
        self.is_fitted = True

        # Solve Prior-Informed Game-Level Player Margin RAPM & Mean-Centered Off/Def RAPM
        if len(rapm_game_rows) >= cfg.min_games_for_player_rapm and player_set:
            cutoff_priors = (
                precomputed_cutoff_priors
                if precomputed_cutoff_priors is not None
                else _build_cutoff_player_priors(prior_all)
            )
            self._player_priors = cutoff_priors
            self._has_cutoff_priors = bool(cutoff_priors)

            players_sorted = sorted(player_set)
            p_idx = {pn: i for i, pn in enumerate(players_sorted)}
            n_p = len(players_sorted)
            n_r = len(rapm_game_rows)

            r_rows: list[int] = []
            r_cols: list[int] = []
            r_vals: list[float] = []
            y_rapm = np.zeros(n_r, dtype=float)
            hca_scale = 25.0  # Keeps HCA intercept effectively un-damped under lsqr(damp=...)

            # Also assemble Off/Def RAPM weighted means for exact zero-bias mean-centering
            w_p_list = np.zeros(n_r, dtype=float)
            ho_vals = np.zeros(n_r, dtype=float)
            ao_vals = np.zeros(n_r, dtype=float)

            for local_i, (orig_idx, h_sh, a_sh, legacy_prior_off) in enumerate(rapm_game_rows):
                w_p = math.exp(-ln2 * float(ages[orig_idx]) / cfg.player_rapm_half_life_days)
                w_p_list[local_i] = w_p
                sw = math.sqrt(w_p)
                ho_vals[local_i] = float(y_ho[orig_idx])
                ao_vals[local_i] = float(y_ao[orig_idx])

                if self._has_cutoff_priors:
                    prior_off = sum(float(sh) * cutoff_priors.get(pn, 0.0) for pn, sh in h_sh.items()) - sum(
                        float(sh) * cutoff_priors.get(pn, 0.0) for pn, sh in a_sh.items()
                    )
                else:
                    prior_off = legacy_prior_off

                y_rapm[local_i] = sw * (float(y_net[orig_idx]) - prior_off)
                for pn in sorted(h_sh):
                    r_rows.append(local_i)
                    r_cols.append(p_idx[pn])
                    r_vals.append(sw * float(h_sh[pn]))
                for pn in sorted(a_sh):
                    r_rows.append(local_i)
                    r_cols.append(p_idx[pn])
                    r_vals.append(-sw * float(a_sh[pn]))
                r_rows.append(local_i)
                r_cols.append(n_p)
                r_vals.append(sw * hca_scale)

            x_p_mat = csr_matrix((r_vals, (r_rows, r_cols)), shape=(n_r, n_p + 1))
            sol = lsqr(x_p_mat, y_rapm, damp=float(cfg.player_rapm_damp), atol=1e-4, btol=1e-4, iter_lim=120)[0]
            self.player_index = p_idx
            self._rapm_delta = np.asarray(sol[:n_p], dtype=float)
            self._rapm_hca = float(sol[n_p]) * hca_scale
            self.rapm_fitted = True

            # Mean-centered Player Offensive & Defensive RAPM (exact unbiased league efficiency baseline)
            w_p_sum = float(np.sum(w_p_list))
            mu_e_rapm = (
                float(np.sum(w_p_list * 0.5 * (ho_vals + ao_vals))) / w_p_sum
                if w_p_sum > 1e-9
                else self._mu_e_slow
            )
            od_rows: list[int] = []
            od_cols: list[int] = []
            od_vals: list[float] = []
            y_od = np.zeros(2 * n_r, dtype=float)
            for local_i, (_orig_idx, h_sh, a_sh, _legacy_off) in enumerate(rapm_game_rows):
                sw = math.sqrt(float(w_p_list[local_i]))
                r0 = 2 * local_i
                r1 = 2 * local_i + 1
                y_od[r0] = sw * (float(ho_vals[local_i]) - mu_e_rapm)
                y_od[r1] = sw * (float(ao_vals[local_i]) - mu_e_rapm)
                for pn in sorted(h_sh):
                    pi = p_idx[pn]
                    val = sw * float(h_sh[pn])
                    od_rows.append(r0)
                    od_cols.append(pi)
                    od_vals.append(val)
                    od_rows.append(r1)
                    od_cols.append(n_p + pi)
                    od_vals.append(val)
                for pn in sorted(a_sh):
                    pi = p_idx[pn]
                    val = sw * float(a_sh[pn])
                    od_rows.append(r0)
                    od_cols.append(n_p + pi)
                    od_vals.append(val)
                    od_rows.append(r1)
                    od_cols.append(pi)
                    od_vals.append(val)
                # Un-damped HCA_e column at 2*n_p
                od_rows.append(r0)
                od_cols.append(2 * n_p)
                od_vals.append(sw * hca_scale)
                od_rows.append(r1)
                od_cols.append(2 * n_p)
                od_vals.append(-sw * hca_scale)

            x_od_mat = csr_matrix((od_vals, (od_rows, od_cols)), shape=(2 * n_r, 2 * n_p + 1))
            sol_od = lsqr(
                x_od_mat, y_od, damp=float(cfg.player_od_rapm_damp), atol=1e-4, btol=1e-4, iter_lim=120
            )[0]
            self._rapm_off = np.asarray(sol_od[:n_p], dtype=float)
            self._rapm_def = np.asarray(sol_od[n_p : 2 * n_p], dtype=float)
            self._rapm_mu_e = mu_e_rapm
            self._rapm_hca_e = float(sol_od[2 * n_p]) * hca_scale
            self.od_rapm_fitted = True

    def _extract_game_records(
        self,
        games: list[dict[str, Any]],
        prior_for_feats: list[dict[str, Any]],
        precomputed_feats: dict[str, dict[str, float]] | None,
    ) -> dict[str, dict[str, Any]]:
        lb = float(self.config.luck_adjust_blend)
        out: dict[str, dict[str, Any]] = {}
        for g in games:
            gid = str(g["game_id"])
            if gid in out:
                continue
            hs = float(g["home_score"])
            as_ = float(g["away_score"])
            if precomputed_feats is not None and gid in precomputed_feats:
                feats = precomputed_feats[gid]
            else:
                feats = build_pregame_features(g, prior_for_feats, market="total_points")
            sit_mar = float(feats.get("fatigue_diff", 0.0)) + float(feats.get("altitude_advantage", 0.0))
            sit_tot = float(feats.get("b2b_total_drag", 0.0))

            post_obs = g.get("_bx_post_obs")
            if isinstance(post_obs, dict) and "reg_pace" in post_obs:
                reg_pace = float(post_obs["reg_pace"])
                h_ortg_raw = float(post_obs["h_ortg"])
                a_ortg_raw = float(post_obs["a_ortg"])
                h_ortg_la = float(post_obs["h_ortg_la"])
                a_ortg_la = float(post_obs["a_ortg_la"])
                ot_add = float(post_obs.get("ot_add", 0.0))
                h_sh = post_obs.get("home_shares") or {}
                a_sh = post_obs.get("away_shares") or {}
                prior_mar_off = float(post_obs.get("prior_mar_offset", 0.0))
                has_box = True
            else:
                reg_pace = float(g.get("home_pace") or 99.5) * 0.5 + float(g.get("away_pace") or 99.5) * 0.5
                reg_pace = max(90.0, min(110.0, reg_pace))
                h_ortg_raw = 100.0 * hs / reg_pace
                a_ortg_raw = 100.0 * as_ / reg_pace
                h_ortg_la, a_ortg_la = h_ortg_raw, a_ortg_raw
                ot_add = 0.0
                h_sh, a_sh = {}, {}
                prior_mar_off = 0.0
                has_box = False

            net_raw = max(-26.0, min(26.0, h_ortg_raw - a_ortg_raw))
            net_la = max(-26.0, min(26.0, h_ortg_la - a_ortg_la))
            out[gid] = {
                "ts_sec": parse_iso_utc(str(g["game_start_time"])).timestamp(),
                "season": str(g.get("season") or ""),
                "y_net": (1.0 - lb) * net_raw + lb * net_la - sit_mar,
                "y_ho": (1.0 - lb) * h_ortg_raw + lb * h_ortg_la - 0.5 * sit_mar - 0.5 * sit_tot,
                "y_ao": (1.0 - lb) * a_ortg_raw + lb * a_ortg_la + 0.5 * sit_mar - 0.5 * sit_tot,
                "y_pace": reg_pace,
                "ot_add": ot_add,
                "has_box": has_box,
                "home_shares": h_sh,
                "away_shares": a_sh,
                "prior_mar_offset": prior_mar_off,
            }
        return out

    def fit(
        self,
        historical_games: list[dict[str, Any]],
        cutoff_time_str: str,
        precomputed_feats: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self.is_fitted = False
        self.rapm_fitted = False
        self.od_rapm_fitted = False
        if not self.config.enabled:
            return

        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        if len(prior) < self.config.min_games_for_team_ridge:
            return

        sample = prior[-2600:] if len(prior) > 2600 else prior
        cutoff_sec = parse_iso_utc(cutoff_time_str).timestamp()
        extracted = self._extract_game_records(sample, prior, precomputed_feats)
        self._fit_from_extracted(sample=sample, prior_all=prior, cutoff_sec=cutoff_sec, extracted=extracted)

    def predict_matchup(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        precomputed_feats: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """
        Strictly pre-game matchup projection from solved multi-horizon Ridge ratings & Player RAPM.
        Never accesses `_bx_post_obs` on `game`.
        """
        feats = precomputed_feats if precomputed_feats is not None else build_pregame_features(
            game, historical_games, market="total_points"
        )
        struct_mar = float(feats["structural_margin"])
        struct_tot = float(feats["structural_total"])
        struct_pace = float(feats["expected_pace"])

        if not self.is_fitted:
            p_def = float(np.clip(1.0 / (1.0 + math.exp(-struct_mar / 7.8)), 0.03, 0.97))
            return {
                "ridge_margin_slow": struct_mar,
                "ridge_margin_fast": struct_mar,
                "ridge_total_slow": struct_tot,
                "ridge_total_fast": struct_tot,
                "ridge_pace_slow": struct_pace,
                "ridge_pace_fast": struct_pace,
                "rapm_margin": struct_mar,
                "rapm_total": struct_tot,
                "rapm_available": 0.0,
                "blowout_drag_ridge": -0.15 * max(0.0, abs(struct_mar) - 9.0),
                "ot_bonus_ridge": 1.45 * math.exp(-0.5 * (struct_mar / 8.5) ** 2),
                "p_home_ridge": round(p_def, 6),
                "is_fitted": 0.0,
            }

        hc = str(game["home_team"])
        ac = str(game["away_team"])
        hi = self.team_index.get(hc)
        ai = self.team_index.get(ac)

        sit_mar = float(feats.get("fatigue_diff", 0.0)) + float(feats.get("altitude_advantage", 0.0))
        sit_tot = float(feats.get("b2b_total_drag", 0.0))

        s_h_s = float(self._s_slow[hi]) if hi is not None else 0.0
        s_a_s = float(self._s_slow[ai]) if ai is not None else 0.0
        o_h_s = float(self._o_slow[hi]) if hi is not None else 0.0
        d_h_s = float(self._d_slow[hi]) if hi is not None else 0.0
        o_a_s = float(self._o_slow[ai]) if ai is not None else 0.0
        d_a_s = float(self._d_slow[ai]) if ai is not None else 0.0
        p_h_s = float(self._p_slow[hi]) if hi is not None else 0.0
        p_a_s = float(self._p_slow[ai]) if ai is not None else 0.0

        s_h_f = float(self._s_fast[hi]) if hi is not None else 0.0
        s_a_f = float(self._s_fast[ai]) if ai is not None else 0.0
        o_h_f = float(self._o_fast[hi]) if hi is not None else 0.0
        d_h_f = float(self._d_fast[hi]) if hi is not None else 0.0
        o_a_f = float(self._o_fast[ai]) if ai is not None else 0.0
        d_a_f = float(self._d_fast[ai]) if ai is not None else 0.0
        p_h_f = float(self._p_fast[hi]) if hi is not None else 0.0
        p_a_f = float(self._p_fast[ai]) if ai is not None else 0.0

        pace_s = float(np.clip(self._mu_p_slow + p_h_s + p_a_s, 91.0, 108.0))
        pace_f = float(np.clip(self._mu_p_fast + p_h_f + p_a_f, 91.0, 108.0))

        mar_s = (s_h_s - s_a_s + self._hca_m_slow) * (pace_s / 100.0) + sit_mar
        mar_f = (s_h_f - s_a_f + self._hca_m_fast) * (pace_f / 100.0) + sit_mar

        tot_s = pace_s * (2.0 * self._mu_e_slow + o_h_s + d_a_s + o_a_s + d_h_s) / 100.0 + sit_tot + self._ot_add
        tot_f = pace_f * (2.0 * self._mu_e_fast + o_h_f + d_a_f + o_a_f + d_h_f) / 100.0 + sit_tot + self._ot_add

        blow_drag = -0.15 * max(0.0, abs(mar_s) - 9.0)
        ot_bonus = 1.45 * math.exp(-0.5 * (mar_s / 8.5) ** 2)

        # Prior-informed Player Margin RAPM & Mean-Centered Off/Def RAPM (strictly pre-game `_bx_exp_lineup`)
        rapm_mar = mar_s
        rapm_tot = tot_s
        rapm_avail = 0.0
        exp_lineup = game.get("_bx_exp_lineup")
        if self.rapm_fitted and isinstance(exp_lineup, tuple) and len(exp_lineup) == 2:
            h_sh, a_sh = exp_lineup
            if h_sh and a_sh:
                h_delta = sum(
                    float(sh) * float(self._rapm_delta[self.player_index[pn]])
                    for pn, sh in h_sh.items()
                    if pn in self.player_index
                )
                a_delta = sum(
                    float(sh) * float(self._rapm_delta[self.player_index[pn]])
                    for pn, sh in a_sh.items()
                    if pn in self.player_index
                )
                if self._has_cutoff_priors:
                    prior_diff = sum(
                        float(sh) * self._player_priors.get(pn, 0.0) for pn, sh in h_sh.items()
                    ) - sum(
                        float(sh) * self._player_priors.get(pn, 0.0) for pn, sh in a_sh.items()
                    )
                else:
                    prior_diff = float(feats.get("bx_lineup_prior_diff", 0.0))
                rapm_net = prior_diff + (h_delta - a_delta) + self._rapm_hca
                rapm_mar = rapm_net * (pace_s / 100.0) + sit_mar
                rapm_avail = 1.0

                if self.od_rapm_fitted:
                    ho = sum(
                        float(sh) * float(self._rapm_off[self.player_index[pn]])
                        for pn, sh in h_sh.items()
                        if pn in self.player_index
                    )
                    hd = sum(
                        float(sh) * float(self._rapm_def[self.player_index[pn]])
                        for pn, sh in h_sh.items()
                        if pn in self.player_index
                    )
                    ao = sum(
                        float(sh) * float(self._rapm_off[self.player_index[pn]])
                        for pn, sh in a_sh.items()
                        if pn in self.player_index
                    )
                    ad = sum(
                        float(sh) * float(self._rapm_def[self.player_index[pn]])
                        for pn, sh in a_sh.items()
                        if pn in self.player_index
                    )
                    rapm_tot = (
                        pace_s * (2.0 * self._rapm_mu_e + ho + ad + ao + hd) / 100.0
                        + sit_tot
                        + self._ot_add
                    )

        blend_mar = 0.45 * mar_s + 0.40 * rapm_mar + 0.15 * mar_f
        p_ridge = float(np.clip(1.0 / (1.0 + math.exp(-blend_mar / 7.8)), 0.03, 0.97))

        return {
            "ridge_margin_slow": round(float(mar_s), 4),
            "ridge_margin_fast": round(float(mar_f), 4),
            "ridge_total_slow": round(float(tot_s), 4),
            "ridge_total_fast": round(float(tot_f), 4),
            "ridge_pace_slow": round(float(pace_s), 4),
            "ridge_pace_fast": round(float(pace_f), 4),
            "rapm_margin": round(float(rapm_mar), 4),
            "rapm_total": round(float(rapm_tot), 4),
            "rapm_available": rapm_avail,
            "blowout_drag_ridge": round(float(blow_drag), 4),
            "ot_bonus_ridge": round(float(ot_bonus), 4),
            "p_home_ridge": round(p_ridge, 6),
            "is_fitted": 1.0,
        }

    def compute_expanding_oof_predictions(
        self,
        train_sample: list[dict[str, Any]],
        prior_all: list[dict[str, Any]],
        precomputed_feats: dict[str, dict[str, float]],
        *,
        min_warmup: int = 40,
        n_folds: int = 12,
    ) -> dict[int, dict[str, float]]:
        """
        Computes strictly out-of-fold Ridge/RAPM predictions for `train_sample` indices using
        high-freshness expanding temporal folds (~14-day blocks, `parse_iso_utc(train) < parse_iso_utc(fold_cutoff) <= parse_iso_utc(val)`)
        with pre-extracted per-game arrays so downstream meta-models train with zero in-sample leakage
        and production-equivalent Ridge/RAPM freshness.
        """
        n_total = len(train_sample)
        if n_total <= min_warmup or n_folds < 1:
            return {}

        # Group train_sample by exact parsed tipoff timestamp so boundary ties stay together
        parsed_train = [parse_iso_utc(str(g["game_start_time"])).timestamp() for g in train_sample]
        groups: list[list[int]] = []
        for idx, ts_val in enumerate(parsed_train):
            if not groups or ts_val != parsed_train[groups[-1][0]]:
                groups.append([idx])
            else:
                groups[-1].append(idx)

        prefix_count = 0
        eval_start_group = 0
        while eval_start_group < len(groups) and prefix_count < min_warmup:
            prefix_count += len(groups[eval_start_group])
            eval_start_group += 1
        if eval_start_group >= len(groups):
            return {}

        eval_groups = groups[eval_start_group:]
        k_eff = min(int(n_folds), len(eval_groups))
        q, rem = divmod(len(eval_groups), k_eff)

        # Pre-extract per-game records ONCE across all prior_all (zero redundant feature extraction)
        prior_with_ts = sorted(
            [(parse_iso_utc(str(g["game_start_time"])).timestamp(), str(g["game_id"]), g) for g in prior_all],
            key=lambda x: (x[0], x[1]),
        )
        prior_sorted = [item[2] for item in prior_with_ts]
        prior_ts_arr = [item[0] for item in prior_with_ts]
        extracted = self._extract_game_records(prior_sorted, prior_sorted, precomputed_feats)

        oof_map: dict[int, dict[str, float]] = {}
        pos = 0
        prior_ptr = 0
        n_prior = len(prior_sorted)
        running_career: dict[str, list[float]] = {}

        for f_i in range(k_eff):
            size = q + (1 if f_i < rem else 0)
            fold_val_groups = eval_groups[pos : pos + size]
            pos += size
            if not fold_val_groups:
                continue
            val_idx = [i for grp in fold_val_groups for i in grp]
            fold_cutoff_sec = parsed_train[val_idx[0]]

            # Advance pointer strictly monotonically: all games with ts < fold_cutoff_sec
            while prior_ptr < n_prior and prior_ts_arr[prior_ptr] < fold_cutoff_sec:
                _update_career_state_from_game(running_career, prior_sorted[prior_ptr])
                prior_ptr += 1
            fold_prior = prior_sorted[:prior_ptr]
            fold_sample = fold_prior[-2600:] if len(fold_prior) > 2600 else fold_prior

            fold_model = RidgeEfficiencyRAPMModel(f"{self.version_id}_oof", config=self.config)
            fold_model._fit_from_extracted(
                sample=fold_sample,
                prior_all=fold_prior,
                cutoff_sec=fold_cutoff_sec,
                extracted=extracted,
                precomputed_cutoff_priors=_priors_from_career_state(running_career),
            )
            for vi in val_idx:
                g_val = train_sample[vi]
                gid = str(g_val["game_id"])
                oof_map[vi] = fold_model.predict_matchup(
                    g_val,
                    fold_prior,
                    precomputed_feats=precomputed_feats.get(gid),
                )
        return oof_map
