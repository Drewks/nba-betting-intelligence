"""
Modelo F+G: V5 Syndicate Meta-Ensemble + 10,000-Game Monte Carlo Hybrid.
Combines Elo, Point Margin, Total Points with Covariance, LightGBM, and Deep Monte Carlo
via out-of-sample shrinkage-regularized log-odds Bayesian pooling with boxscore adjustments.
"""

from __future__ import annotations

import math
from typing import Any
import numpy as np
from scipy.stats import norm
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.features.builder import build_pregame_features
from src.models.common import _filter_strictly_prior_final_games
from src.models.deep_monte_carlo import DeepMonteCarloHybridModel
from src.models.elo import EloModel
from src.models.gbm_model import AdvancedGBMModel
from src.models.point_margin import PointMarginModel
from src.models.total_points import TotalPointsModel


class EnsembleStackingModel:
    """
    Modelo F+G (V5 Syndicate Meta-Ensemble + 10,000-Game Monte Carlo Hybrid):
    Combines Dual-Speed MOV Elo (Model B), Residual-Anchored Point Margin (Model C),
    Pace-Decoupled Total Points with Covariance (Model D), Residual-Boosted LightGBM (Model E),
    and Deep Monte Carlo Possession Simulator (Model G) via strictly out-of-sample
    shrinkage-regularized log-odds Bayesian pooling.
    """

    model_family = "model_f_meta_ensemble"

    def __init__(self, version_id: str = "model_f_ensemble_v5") -> None:
        self.version_id = version_id
        self.model_b = EloModel("model_b_elo_v5")
        self.model_c = PointMarginModel("model_c_point_margin_v5")
        self.model_d = TotalPointsModel("model_d_total_points_v5")
        self.model_e = AdvancedGBMModel("model_e_lightgbm_v5")
        self.model_g = DeepMonteCarloHybridModel(
            "model_g_ml_montecarlo_v5",
            n_simulations=10000,
            shared_margin_model=self.model_c,
            shared_totals_model=self.model_d,
            shared_gbm_model=self.model_e,
        )
        self.ml_weights: list[float] = [0.50, 0.24, 0.14, 0.12]
        self.tot_weights: list[float] = [0.58, 0.24, 0.18]

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)

        # Strictly Out-of-Sample Walk-Forward Weight Estimation (Zero In-Sample Leakage)
        if len(prior) >= 80:
            val_size = 30
            train_sub = prior[:-val_size]
            val_sub = prior[-val_size:]
            val_cutoff = val_sub[0]["game_start_time"]

            self.model_c.fit(train_sub, val_cutoff)
            self.model_d.fit(train_sub, val_cutoff)
            self.model_e.fit(train_sub, val_cutoff)

            brier_b, brier_c, brier_e, brier_g = [], [], [], []
            brier_tot_d, brier_tot_e, brier_tot_g = [], [], []

            for g in val_sub:
                actual_win = 1.0 if g["home_score"] > g["away_score"] else 0.0
                actual_tot = float(g["home_score"] + g["away_score"])

                pb = self.model_b.predict_moneyline(g, prior)["p_home"]
                pc_res = self.model_c.predict_moneyline(g, prior)
                pe_res = self.model_e.predict_moneyline(g, prior)

                line_ref = float(g.get("line_value") or g.get("total_line") or g.get("structural_total") or 228.5)
                pd_tot = self.model_d.predict_total_points(g, prior, line_ref)
                pe_tot = self.model_e.predict_total_points(g, prior, line_ref)
                pg_res = self.model_g.simulate_matchup(
                    g,
                    prior,
                    line_value=line_ref,
                    precomputed_c=pc_res,
                    precomputed_d=pd_tot,
                    precomputed_e_ml=pe_res,
                    precomputed_e_tot=pe_tot,
                )

                brier_b.append((pb - actual_win) ** 2)
                brier_c.append((pc_res["p_home"] - actual_win) ** 2)
                brier_e.append((pe_res["p_home"] - actual_win) ** 2)
                brier_g.append((pg_res["p_home_mc"] - actual_win) ** 2)

                actual_over = 1.0 if actual_tot > line_ref else 0.0
                brier_tot_d.append((pd_tot["p_over"] - actual_over) ** 2)
                brier_tot_e.append((pe_tot["p_over"] - actual_over) ** 2)
                brier_tot_g.append((pg_res["p_over_mc"] - actual_over) ** 2)

            inv_ml = np.array(
                [
                    1.50 / max(0.15, float(np.mean(brier_b))),
                    0.95 / max(0.15, float(np.mean(brier_c))),
                    0.75 / max(0.15, float(np.mean(brier_e))),
                    0.70 / max(0.15, float(np.mean(brier_g))),
                ],
                dtype=float,
            )
            emp_ml_w = inv_ml / np.sum(inv_ml)
            prior_ml_w = np.array([0.50, 0.24, 0.14, 0.12], dtype=float)
            blend_ml_w = 0.70 * prior_ml_w + 0.30 * emp_ml_w
            self.ml_weights = [round(float(w), 4) for w in (blend_ml_w / np.sum(blend_ml_w))]

            inv_tot = np.array(
                [
                    1.45 / max(0.15, float(np.mean(brier_tot_d))),
                    0.85 / max(0.15, float(np.mean(brier_tot_e))),
                    0.75 / max(0.15, float(np.mean(brier_tot_g))),
                ],
                dtype=float,
            )
            emp_tot_w = inv_tot / np.sum(inv_tot)
            prior_tot_w = np.array([0.58, 0.24, 0.18], dtype=float)
            blend_tot_w = 0.70 * prior_tot_w + 0.30 * emp_tot_w
            self.tot_weights = [round(float(w), 4) for w in (blend_tot_w / np.sum(blend_tot_w))]

        # Final fit on full prior history up to cutoff_time_str
        self.model_c.fit(historical_games, cutoff_time_str)
        self.model_d.fit(historical_games, cutoff_time_str)
        self.model_e.fit(historical_games, cutoff_time_str)
        self._fit_boxscore_adjustment(prior)

    BOXSCORE_ADJ_FEATURES: tuple[str, ...] = (
        "bx_missing_pts_diff", "bx_new_absence_pts_diff", "bx_efg_diff", "bx_tov_diff", "bx_orb_diff", "bx_ftr_diff",
    )
    BOXSCORE_ADJ_MIN_GAMES = 300
    BOXSCORE_ADJ_MAX_POINTS = 4.0
    BOXSCORE_ADJ_SIGMA = 12.0

    def _fit_boxscore_adjustment(self, prior: list[dict[str, Any]]) -> None:
        """
        Learns how much real box-score information (regular-rotation points absent in the last game,
        real Four Factors) shifts the expected margin beyond the score-only structural margin.
        Ridge on (actual margin - structural margin); only games that carry box-score features are used.
        """
        self.bx_reg = None
        rows = [g for g in prior[-1500:] if g.get("bx_min_games") and float(g["bx_min_games"]) >= 10]
        if len(rows) < self.BOXSCORE_ADJ_MIN_GAMES:
            return
        X_rows: list[list[float]] = []
        y_vals: list[float] = []
        for g in rows:
            feats = build_pregame_features(g, prior, market="moneyline")
            X_rows.append([feats[c] for c in self.BOXSCORE_ADJ_FEATURES])
            y_vals.append(float(g["home_score"] - g["away_score"]) - float(feats["structural_margin"]))
        reg = make_pipeline(StandardScaler(), RidgeCV(alphas=[10.0, 100.0, 1000.0, 5000.0]))
        reg.fit(np.asarray(X_rows, dtype=float), np.asarray(y_vals, dtype=float))
        reg[-1].intercept_ = 0.0
        self.bx_reg = reg

    def boxscore_margin_shift(self, game: dict[str, Any], historical_games: list[dict[str, Any]]) -> float:
        reg = getattr(self, "bx_reg", None)
        if reg is None or not game.get("bx_min_games") or float(game["bx_min_games"]) < 10:
            return 0.0
        feats = build_pregame_features(game, historical_games, market="moneyline")
        x = np.asarray([[feats[c] for c in self.BOXSCORE_ADJ_FEATURES]], dtype=float)
        return float(np.clip(reg.predict(x)[0], -self.BOXSCORE_ADJ_MAX_POINTS, self.BOXSCORE_ADJ_MAX_POINTS))

    @staticmethod
    def _pool_probs_log_odds(probs: list[float], weights: list[float]) -> float:
        eps = 1e-5
        logits = [math.log(max(eps, min(1.0 - eps, p)) / (1.0 - max(eps, min(1.0 - eps, p)))) for p in probs]
        pooled_logit = sum(w * lg for w, lg in zip(weights, logits, strict=False))
        return float(np.clip(1.0 / (1.0 + math.exp(-pooled_logit)), 0.05, 0.95))

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
    ) -> dict[str, Any]:
        pb = self.model_b.predict_moneyline(game, historical_games)["p_home"]
        c_res = self.model_c.predict_moneyline(game, historical_games)
        e_res = self.model_e.predict_moneyline(game, historical_games)
        pc = c_res["p_home"]
        pe = e_res["p_home"]
        mc_res = self.model_g.simulate_matchup(
            game, historical_games, precomputed_c=c_res, precomputed_e_ml=e_res
        )
        pg = mc_res["p_home_mc"]

        p_home = self._pool_probs_log_odds([pb, pc, pe, pg], self.ml_weights)
        sub_std = float(np.std([pb, pc, pe, pg]))
        unc_std = round(max(0.032, min(0.095, 0.036 + 0.45 * sub_std)), 4)

        bx_shift = self.boxscore_margin_shift(game, historical_games)
        if bx_shift != 0.0:
            z = float(norm.ppf(np.clip(p_home, 1e-4, 1.0 - 1e-4))) + bx_shift / self.BOXSCORE_ADJ_SIGMA
            p_home = float(np.clip(norm.cdf(z), 0.05, 0.95))

        return {
            "boxscore_margin_shift": round(bx_shift, 3),
            "p_home": round(p_home, 6),
            "p_away": round(1.0 - p_home, 6),
            "p_elo": pb,
            "p_margin": pc,
            "p_gbm": pe,
            "p_montecarlo": pg,
            "expected_margin": round(0.55 * c_res["expected_margin"] + 0.45 * mc_res["mc_expected_margin"] + bx_shift, 3),
            "ensemble_weights": self.ml_weights,
            "overtime_prob": mc_res["overtime_prob"],
            "blowout_prob": mc_res["blowout_prob"],
            "conformal_q10_margin": mc_res["conformal_q10_margin"],
            "conformal_q90_margin": mc_res["conformal_q90_margin"],
            "uncertainty_std": unc_std,
        }

    def predict_total_points(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        line_value: float,
    ) -> dict[str, float]:
        pd_res = self.model_d.predict_total_points(game, historical_games, line_value)
        pe_res = self.model_e.predict_total_points(game, historical_games, line_value)
        mc_res = self.model_g.simulate_matchup(
            game,
            historical_games,
            line_value,
            precomputed_d=pd_res,
            precomputed_e_tot=pe_res,
        )
        pg_over = mc_res["p_over_mc"]

        p_over = self._pool_probs_log_odds([pd_res["p_over"], pe_res["p_over"], pg_over], self.tot_weights)
        sub_std = float(np.std([pd_res["p_over"], pe_res["p_over"], pg_over]))
        unc_std = round(max(0.034, min(0.098, 0.038 + 0.45 * sub_std)), 4)

        return {
            "expected_total": round(0.60 * pd_res["expected_total"] + 0.25 * pe_res["expected_total"] + 0.15 * mc_res["mc_expected_total"], 2),
            "total_std_with_covariance": pd_res["total_std_with_covariance"],
            "p_over": round(p_over, 6),
            "p_under": round(1.0 - p_over, 6),
            "p_montecarlo_over": pg_over,
            "overtime_prob": mc_res["overtime_prob"],
            "blowout_prob": mc_res["blowout_prob"],
            "clutch_foul_prob": mc_res["clutch_foul_prob"],
            "conformal_q10_total": mc_res["conformal_q10_total"],
            "conformal_q90_total": mc_res["conformal_q90_total"],
            "uncertainty_std": unc_std,
        }

    def predict_spread(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        spread_line_home: float,
    ) -> dict[str, float]:
        """
        Pools PointMarginModel, AdvancedGBMModel, and DeepMonteCarloHybridModel spread cover probabilities
        for spread_line_home (e.g. -6.5 or +4.0).
        """
        c_sp = self.model_c.predict_spread(game, historical_games, spread_line_home)
        e_ml = self.model_e.predict_moneyline(game, historical_games)
        mc_res = self.model_g.simulate_matchup(game, historical_games)

        target_diff = -float(spread_line_home)
        e_mar = float(e_ml.get("expected_margin", c_sp["expected_margin"]))
        mc_mar = float(mc_res["mc_expected_margin"])
        scale = float(c_sp["margin_std"])

        p_e_cover = float(np.clip(1.0 - norm.cdf(target_diff, loc=e_mar, scale=scale), 0.05, 0.95))
        p_mc_cover = float(np.clip(1.0 - norm.cdf(target_diff, loc=mc_mar, scale=scale), 0.05, 0.95))

        p_cover_home = self._pool_probs_log_odds(
            [c_sp["p_cover_home"], p_e_cover, p_mc_cover],
            [0.52, 0.24, 0.24],
        )
        sub_std = float(np.std([c_sp["p_cover_home"], p_e_cover, p_mc_cover]))
        unc_std = round(max(0.034, min(0.095, 0.038 + 0.45 * sub_std)), 4)

        return {
            "spread_line_home": float(spread_line_home),
            "expected_margin": round(0.55 * c_sp["expected_margin"] + 0.45 * mc_mar, 3),
            "margin_std": c_sp["margin_std"],
            "p_cover_home": round(p_cover_home, 6),
            "p_cover_away": round(1.0 - p_cover_home, 6),
            "p_push_estimate": c_sp["p_push_estimate"],
            "conformal_q10_margin": mc_res["conformal_q10_margin"],
            "conformal_q90_margin": mc_res["conformal_q90_margin"],
            "uncertainty_std": unc_std,
        }
