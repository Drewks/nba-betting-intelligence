"""
Modelo F+G+H: V9 Institutional Syndicate Meta-Ensemble + Simultaneous Ridge/RAPM + 10,000-Game Monte Carlo.
Combines Dual-Speed MOV Elo (Model B), Ridge/RAPM Point Margin (Model C), Exact-Pace Ridge Total Points
with Covariance (Model D), Residual-Boosted LightGBM (Model E), 10,000-Game Monte Carlo Simulator (Model G),
and Simultaneous Multi-Horizon Ridge Adjusted Efficiency & Prior-Informed Player RAPM (Model H)
via strictly out-of-sample expanding-window log-loss convex stacking.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

from src.features.builder import build_pregame_features
from src.models.common import _filter_strictly_prior_final_games
from src.models.deep_monte_carlo import DeepMonteCarloHybridModel
from src.models.elo import EloModel
from src.models.gbm_model import AdvancedGBMModel
from src.models.point_margin import PointMarginModel
from src.models.ridge_rapm import RidgeEfficiencyRAPMModel
from src.models.total_points import TotalPointsModel


def _fit_simplex_logloss_weights(
    prob_matrix: np.ndarray,
    outcomes: np.ndarray,
    prior_weights: np.ndarray,
    l2_prior: float = 0.04,
) -> list[float]:
    """
    Optimizes convex simplex log-odds pooling weights `w >= 0, sum(w) = 1` minimizing strictly
    out-of-fold binary log-loss plus gentle L2 shrinkage toward `prior_weights`.
    """
    n_models = prob_matrix.shape[1]
    if prob_matrix.shape[0] < 30 or n_models == 0:
        w_out = prior_weights / float(np.sum(prior_weights))
        return [round(float(w), 4) for w in w_out]

    p_clip = np.clip(prob_matrix, 1e-5, 1.0 - 1e-5)
    logits = np.log(p_clip / (1.0 - p_clip))
    y = np.asarray(outcomes, dtype=float)
    w_prior = np.asarray(prior_weights, dtype=float)
    w_prior = w_prior / float(np.sum(w_prior))

    def _obj(w: np.ndarray) -> float:
        z = logits @ w
        p = np.clip(1.0 / (1.0 + np.exp(-np.clip(z, -20.0, 20.0))), 1e-6, 1.0 - 1e-6)
        nll = -float(np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))
        reg = float(l2_prior * np.sum((w - w_prior) ** 2))
        return nll + reg

    res = minimize(
        _obj,
        x0=w_prior.copy(),
        method="SLSQP",
        bounds=[(0.02, 0.85) for _ in range(n_models)],
        constraints=[{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}],
        options={"ftol": 1e-9, "maxiter": 200},
    )
    w_opt = np.asarray(res.x, dtype=float) if res.success else w_prior
    w_opt = np.clip(w_opt, 0.0, 1.0)
    w_sum = float(np.sum(w_opt))
    w_norm = (w_opt / w_sum) if w_sum > 1e-9 else w_prior
    return [round(float(w), 4) for w in w_norm]


class EnsembleStackingModel:
    """
    Modelo F+G+H (V9 Institutional Meta-Ensemble):
    Combines Dual-Speed MOV Elo (Model B), Ridge/RAPM Point Margin (Model C),
    Exact-Pace Covariance Total Points (Model D), Residual-Boosted LightGBM (Model E),
    Deep Monte Carlo Possession Simulator (Model G), and Simultaneous Ridge/RAPM (Model H)
    via strictly out-of-sample expanding-window log-loss convex stacking.
    """

    model_family = "model_f_meta_ensemble"

    def __init__(self, version_id: str = "model_f_ensemble_v9") -> None:
        self.version_id = version_id
        self.model_h = RidgeEfficiencyRAPMModel("model_h_ridge_rapm_v9")
        self.model_b = EloModel("model_b_elo_v8")
        self.model_c = PointMarginModel("model_c_point_margin_v9", shared_ridge_rapm=self.model_h)
        self.model_d = TotalPointsModel("model_d_total_points_v9", shared_ridge_rapm=self.model_h)
        self.model_e = AdvancedGBMModel("model_e_lightgbm_v9", shared_ridge_rapm=self.model_h)
        self.model_g = DeepMonteCarloHybridModel(
            "model_g_ml_montecarlo_v9",
            n_simulations=10000,
            shared_margin_model=self.model_c,
            shared_totals_model=self.model_d,
            shared_gbm_model=self.model_e,
        )
        # [Model B Elo, Model C Ridge/RAPM Margin, Model E GBM, Model G Monte Carlo]
        self.ml_weights: list[float] = [0.08, 0.44, 0.20, 0.28]
        # [Model D Exact-Pace Ridge Totals, Model E GBM Totals, Model G Monte Carlo Totals]
        self.tot_weights: list[float] = [0.62, 0.22, 0.16]
        self.oof_stack_sample_size: int = 0

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        self.oof_stack_sample_size = 0

        if len(prior) < 20:
            self.model_h.fit(prior, cutoff_time_str)
            self.model_c.fit(prior, cutoff_time_str)
            self.model_d.fit(prior, cutoff_time_str)
            self.model_e.fit(prior, cutoff_time_str)
            return

        train_sample = prior[-1500:] if len(prior) > 1500 else prior
        ridge_window = prior[-2600:] if len(prior) > 2600 else prior

        # Precompute strictly causal pre-game features ONCE across full Ridge/RAPM window
        precomputed_feats: dict[str, dict[str, float]] = {}
        for g in ridge_window:
            gid = str(g["game_id"])
            precomputed_feats[gid] = build_pregame_features(g, prior, market="total_points")

        # 1. Fit Model H on full prior history (for inference) AND compute strictly expanding OOF predictions
        self.model_h.fit(prior, cutoff_time_str, precomputed_feats=precomputed_feats)
        oof_ridge_map: dict[int, dict[str, float]] = {}
        if len(train_sample) >= 80 and self.model_h.is_fitted:
            min_w = min(80, max(30, len(train_sample) // 4))
            oof_ridge_map = self.model_h.compute_expanding_oof_predictions(
                train_sample,
                prior,
                precomputed_feats,
                min_warmup=min_w,
                n_folds=12,
            )

        # 2. Fit Models C, D, E on strictly OOF Ridge/RAPM signals (zero in-sample leakage)
        self.model_c.fit(
            prior,
            cutoff_time_str,
            precomputed_feats=precomputed_feats,
            oof_ridge_map=oof_ridge_map if oof_ridge_map else None,
            train_sample_override=train_sample,
        )
        self.model_d.fit(
            prior,
            cutoff_time_str,
            precomputed_feats=precomputed_feats,
            oof_ridge_map=oof_ridge_map if oof_ridge_map else None,
            train_sample_override=train_sample,
        )
        self.model_e.fit(
            prior,
            cutoff_time_str,
            precomputed_feats=precomputed_feats,
            oof_ridge_map=oof_ridge_map if oof_ridge_map else None,
            train_sample_override=train_sample,
        )

        # 3. Strictly Out-of-Sample Expanding-Window Log-Loss Simplex Stacking (replaces noisy 30-game split)
        self._fit_oof_stacking_weights(train_sample, precomputed_feats)

    def _fit_oof_stacking_weights(
        self,
        train_sample: list[dict[str, Any]],
        precomputed_feats: dict[str, dict[str, float]],
    ) -> None:
        # Moneyline OOF stacking across all games where both Model C and Model E have OOF predictions
        ml_rows: list[list[float]] = []
        ml_outcomes: list[float] = []
        tot_sq_d: list[float] = []
        tot_sq_e: list[float] = []

        for g in train_sample:
            gid = str(g["game_id"])
            pc = self.model_c.oof_win_probs.get(gid)
            pe = self.model_e.oof_win_probs.get(gid)
            if pc is not None and pe is not None:
                feats = precomputed_feats[gid]
                pb = float(np.clip(feats["p_elo"], 0.05, 0.95))
                # MC smooth expectation proxy matches MC Layer 1 blend without 10k draws inside fit()
                c_oof_mar = self.model_c.oof_margin_preds.get(gid, float(feats["structural_margin"]))
                e_oof_mar = self.model_e.oof_margin_preds.get(gid, c_oof_mar)
                mc_mar = 0.65 * c_oof_mar + 0.25 * e_oof_mar + 0.10 * float(feats["elo_spread"])
                pg_proxy = float(
                    np.clip(
                        1.0 / (1.0 + math.exp(-mc_mar / max(6.5, self.model_c.win_logistic_scale))),
                        0.03,
                        0.97,
                    )
                )
                ml_rows.append([pb, pc, pe, pg_proxy])
                ml_outcomes.append(1.0 if float(g["home_score"]) > float(g["away_score"]) else 0.0)

            td = self.model_d.oof_total_preds.get(gid)
            te = self.model_e.oof_total_preds.get(gid)
            if td is not None and te is not None:
                act_t = float(g["home_score"]) + float(g["away_score"])
                tot_sq_d.append((act_t - td) ** 2)
                tot_sq_e.append((act_t - te) ** 2)

        if len(ml_rows) >= 60:
            self.oof_stack_sample_size = len(ml_rows)
            prior_ml = np.array([0.08, 0.44, 0.20, 0.28], dtype=float)
            self.ml_weights = _fit_simplex_logloss_weights(
                np.asarray(ml_rows, dtype=float),
                np.asarray(ml_outcomes, dtype=float),
                prior_weights=prior_ml,
                l2_prior=0.08,
            )

        if len(tot_sq_d) >= 60:
            mse_d = max(100.0, float(np.mean(tot_sq_d)))
            mse_e = max(100.0, float(np.mean(tot_sq_e)))
            # Inverse-MSE shrinkage between Ridge totals (D) and GBM totals (E), keeping MC tail share (G)
            inv_d = 1.0 / mse_d
            inv_e = 1.0 / mse_e
            emp_d = inv_d / (inv_d + inv_e)
            emp_e = inv_e / (inv_d + inv_e)
            # Allocate 0.84 to (D, E) and 0.16 to Monte Carlo tail simulator (G), shrunk toward [0.62, 0.22, 0.16]
            w_d = 0.65 * 0.62 + 0.35 * (0.84 * emp_d)
            w_e = 0.65 * 0.22 + 0.35 * (0.84 * emp_e)
            w_g = 0.16
            s_tot = w_d + w_e + w_g
            self.tot_weights = [round(w_d / s_tot, 4), round(w_e / s_tot, 4), round(w_g / s_tot, 4)]

    def boxscore_margin_shift(self, game: dict[str, Any], historical_games: list[dict[str, Any]]) -> float:
        """
        Diagnostic margin delta between the V9 Ridge/RAPM+Boxscore margin and score-only structural margin.
        Retained for telemetry compatibility without double-counting into `p_home`.
        """
        if not self.model_c.is_fitted or not self.model_c.uses_enhanced_features:
            return 0.0
        feats = build_pregame_features(game, historical_games, market="moneyline")
        ridge_pred = self.model_h.predict_matchup(game, historical_games, precomputed_feats=feats)
        c_res = self.model_c.predict_moneyline(
            game, historical_games, precomputed_feats=feats, precomputed_ridge=ridge_pred
        )
        return round(float(c_res["expected_margin"]) - float(feats["structural_margin"]), 3)

    @staticmethod
    def _pool_probs_log_odds(probs: list[float], weights: list[float]) -> float:
        eps = 1e-5
        logits = [math.log(max(eps, min(1.0 - eps, p)) / (1.0 - max(eps, min(1.0 - eps, p)))) for p in probs]
        pooled_logit = sum(w * lg for w, lg in zip(weights, logits, strict=False))
        return float(np.clip(1.0 / (1.0 + math.exp(-pooled_logit)), 0.03, 0.97))

    @staticmethod
    def _pool_outcome_triples(
        triples: list[tuple[float, float, float]],
        weights: list[float],
    ) -> tuple[float, float, float]:
        """
        Pools unconditional (p_win, p_loss, p_push) probability triples via conditional log-odds
        on (win | win or loss) paired with weighted push probability so p_win + p_loss + p_push == 1.0.
        """
        w_sum = sum(weights) or 1.0
        w_norm = [w / w_sum for w in weights]
        p_push = sum(w * max(0.0, t[2]) for w, t in zip(w_norm, triples, strict=False))
        p_push = max(0.0, min(0.5, float(p_push)))
        cond_wins = []
        for p_w, p_l, _p_p in triples:
            denom = p_w + p_l
            cond_wins.append(p_w / denom if denom > 1e-9 else 0.5)
        eps = 1e-5
        logits = [math.log(max(eps, min(1.0 - eps, p)) / (1.0 - max(eps, min(1.0 - eps, p)))) for p in cond_wins]
        pooled_logit = sum(w * lg for w, lg in zip(w_norm, logits, strict=False))
        p_cond = float(np.clip(1.0 / (1.0 + math.exp(-pooled_logit)), 1e-4, 1.0 - 1e-4))
        non_push = max(0.0, 1.0 - p_push)
        p_w_out = round(non_push * p_cond, 6)
        p_p_out = round(p_push, 6)
        p_l_out = round(max(0.0, 1.0 - p_w_out - p_p_out), 6)
        return p_w_out, p_l_out, p_p_out

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
    ) -> dict[str, Any]:
        feats = build_pregame_features(game, historical_games, market="total_points")
        ridge_pred = self.model_h.predict_matchup(game, historical_games, precomputed_feats=feats)
        pb = float(np.clip(feats["p_elo"], 0.05, 0.95))
        c_res = self.model_c.predict_moneyline(
            game, historical_games, precomputed_feats=feats, precomputed_ridge=ridge_pred
        )
        e_res = self.model_e.predict_moneyline(
            game, historical_games, precomputed_feats=feats, precomputed_ridge=ridge_pred
        )
        pc = float(c_res["p_home"])
        pe = float(e_res["p_home"])
        mc_res = self.model_g.simulate_matchup(
            game,
            historical_games,
            precomputed_c=c_res,
            precomputed_e_ml=e_res,
            precomputed_feats=feats,
            precomputed_ridge=ridge_pred,
        )
        pg = float(mc_res["p_home_mc"])

        p_home = self._pool_probs_log_odds([pb, pc, pe, pg], self.ml_weights)
        sub_std = float(np.std([pb, pc, pe, pg]))
        unc_std = round(max(0.032, min(0.095, 0.036 + 0.45 * sub_std)), 4)

        exp_mar = round(0.65 * float(c_res["expected_margin"]) + 0.20 * float(e_res["expected_margin"]) + 0.15 * float(mc_res["mc_expected_margin"]), 3)
        bx_shift = round(exp_mar - float(feats["structural_margin"]), 3) if self.model_c.uses_enhanced_features else 0.0

        return {
            "boxscore_margin_shift": bx_shift,
            "p_home": round(p_home, 6),
            "p_away": round(1.0 - p_home, 6),
            "p_elo": round(pb, 6),
            "p_margin": round(pc, 6),
            "p_gbm": round(pe, 6),
            "p_montecarlo": round(pg, 6),
            "p_ridge_rapm": round(float(ridge_pred["p_home_ridge"]), 6),
            "expected_margin": exp_mar,
            "ensemble_weights": self.ml_weights,
            "overtime_prob": mc_res["overtime_prob"],
            "multi_overtime_prob": mc_res.get("multi_overtime_prob", 0.0),
            "blowout_prob": mc_res["blowout_prob"],
            "simulation_q10_margin": mc_res["simulation_q10_margin"],
            "simulation_q90_margin": mc_res["simulation_q90_margin"],
            "uncertainty_std": unc_std,
        }

    def predict_total_points(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        line_value: float,
    ) -> dict[str, float]:
        feats = build_pregame_features(game, historical_games, market="total_points")
        ridge_pred = self.model_h.predict_matchup(game, historical_games, precomputed_feats=feats)
        pd_res = self.model_d.predict_total_points(
            game, historical_games, line_value, precomputed_feats=feats, precomputed_ridge=ridge_pred
        )
        pe_res = self.model_e.predict_total_points(
            game, historical_games, line_value, precomputed_feats=feats, precomputed_ridge=ridge_pred
        )
        mc_res = self.model_g.simulate_matchup(
            game,
            historical_games,
            line_value,
            precomputed_d=pd_res,
            precomputed_e_tot=pe_res,
            precomputed_feats=feats,
            precomputed_ridge=ridge_pred,
        )
        pg_over = float(mc_res["p_over_mc"])

        p_over, p_under, p_push = self._pool_outcome_triples(
            [
                (pd_res["p_over"], pd_res["p_under"], pd_res.get("p_push", pd_res.get("p_push_estimate", 0.0))),
                (pe_res["p_over"], pe_res["p_under"], pe_res.get("p_push", pe_res.get("p_push_estimate", 0.0))),
                (pg_over, mc_res["p_under_mc"], mc_res.get("p_push_mc", 0.0)),
            ],
            self.tot_weights,
        )
        sub_std = float(np.std([pd_res["p_over"], pe_res["p_over"], pg_over]))
        unc_std = round(max(0.034, min(0.098, 0.038 + 0.45 * sub_std)), 4)

        return {
            "expected_total": round(
                self.tot_weights[0] * float(pd_res["expected_total"])
                + self.tot_weights[1] * float(pe_res["expected_total"])
                + self.tot_weights[2] * float(mc_res["mc_expected_total"]),
                2,
            ),
            "total_std_with_covariance": pd_res["total_std_with_covariance"],
            "p_over": p_over,
            "p_under": p_under,
            "p_push": p_push,
            "p_push_estimate": p_push,
            "p_montecarlo_over": pg_over,
            "overtime_prob": mc_res["overtime_prob"],
            "multi_overtime_prob": mc_res.get("multi_overtime_prob", 0.0),
            "blowout_prob": mc_res["blowout_prob"],
            "clutch_foul_prob": mc_res["clutch_foul_prob"],
            "simulation_q10_total": mc_res["simulation_q10_total"],
            "simulation_q90_total": mc_res["simulation_q90_total"],
            "uncertainty_std": unc_std,
        }

    def predict_spread(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        spread_line_home: float,
    ) -> dict[str, float]:
        """
        Pools PointMarginModel (Ridge/RAPM), AdvancedGBMModel, and DeepMonteCarloHybridModel spread cover
        probabilities for spread_line_home with unconditional push mass preservation.
        """
        feats = build_pregame_features(game, historical_games, market="total_points")
        ridge_pred = self.model_h.predict_matchup(game, historical_games, precomputed_feats=feats)
        c_sp = self.model_c.predict_spread(
            game, historical_games, spread_line_home, precomputed_feats=feats, precomputed_ridge=ridge_pred
        )
        e_ml = self.model_e.predict_moneyline(
            game, historical_games, precomputed_feats=feats, precomputed_ridge=ridge_pred
        )
        mc_res = self.model_g.simulate_matchup(
            game,
            historical_games,
            precomputed_e_ml=e_ml,
            precomputed_feats=feats,
            precomputed_ridge=ridge_pred,
        )

        target_diff = -float(spread_line_home)
        e_mar = float(e_ml.get("expected_margin", c_sp["expected_margin"]))
        mc_mar = float(mc_res["mc_expected_margin"])
        scale = float(c_sp["margin_std"])
        is_int_spread = abs(target_diff - round(target_diff)) < 1e-6

        def _triple_from_normal(mu: float) -> tuple[float, float, float]:
            if is_int_spread:
                p_w = float(1.0 - norm.cdf(target_diff + 0.5, loc=mu, scale=scale))
                p_l = float(norm.cdf(target_diff - 0.5, loc=mu, scale=scale))
                p_p = max(0.0, 1.0 - p_w - p_l)
                return p_w, p_l, p_p
            p_w = float(np.clip(1.0 - norm.cdf(target_diff, loc=mu, scale=scale), 1e-4, 1.0 - 1e-4))
            return p_w, 1.0 - p_w, 0.0

        t_c = (c_sp["p_cover_home"], c_sp["p_cover_away"], c_sp.get("p_push", c_sp.get("p_push_estimate", 0.0)))
        t_e = _triple_from_normal(e_mar)
        t_mc = _triple_from_normal(mc_mar)

        p_cover_home, p_cover_away, p_push = self._pool_outcome_triples([t_c, t_e, t_mc], [0.58, 0.24, 0.18])
        sub_std = float(np.std([t_c[0], t_e[0], t_mc[0]]))
        unc_std = round(max(0.034, min(0.095, 0.038 + 0.45 * sub_std)), 4)

        return {
            "spread_line_home": float(spread_line_home),
            "expected_margin": round(0.60 * float(c_sp["expected_margin"]) + 0.25 * e_mar + 0.15 * mc_mar, 3),
            "margin_std": c_sp["margin_std"],
            "p_cover_home": p_cover_home,
            "p_cover_away": p_cover_away,
            "p_push": p_push,
            "p_push_estimate": p_push,
            "simulation_q10_margin": mc_res["simulation_q10_margin"],
            "simulation_q90_margin": mc_res["simulation_q90_margin"],
            "uncertainty_std": unc_std,
        }
