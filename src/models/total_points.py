"""
Modelo D: Total Points NBA Model.
Models the distribution of T = Score_home + Score_away using additive offensive/defensive
efficiency deviations from the dynamic league mean, decoupled tempo, B2B fatigue drag,
and blowout deceleration drag. Explicitly estimates and includes Cov(Score_home, Score_away).
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
from src.models.common import TOTAL_FEATURE_COLUMNS, _filter_strictly_prior_final_games


class TotalPointsModel:
    """
    Modelo D (Total de Puntos):
    Models the distribution of T = Score_home + Score_away using additive offensive/defensive
    efficiency deviations from the dynamic league mean, decoupled tempo, B2B fatigue drag,
    and blowout deceleration drag.
    Explicitly estimates and includes the covariance Cov(Score_home, Score_away):
        Var(H + A) = Var(H) + Var(A) + 2 * Cov(H, A).
    """

    model_family = "model_d_total_points"

    def __init__(
        self,
        version_id: str = "model_d_total_points_v1",
        default_total_std: float = 18.2,
    ) -> None:
        self.version_id = version_id
        self.total_std = default_total_std
        self.independent_std = 15.6
        self.score_covariance = 38.0
        self.score_correlation = 0.31
        self.regressor: Any = None
        self.ml_weight: float = 0.25
        self.is_fitted = False

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        if len(prior) < 20:
            self.is_fitted = False
            return

        train_sample = prior[-1000:] if len(prior) > 1000 else prior
        X_rows: list[list[float]] = []
        y_totals: list[float] = []
        s_totals: list[float] = []
        h_res_list: list[float] = []
        a_res_list: list[float] = []

        for g in train_sample:
            feats = build_pregame_features(g, prior, market="total_points")
            X_rows.append([feats[c] for c in TOTAL_FEATURE_COLUMNS])
            h_pts = float(g["home_score"])
            a_pts = float(g["away_score"])
            y_totals.append(h_pts + a_pts)
            s_totals.append(float(feats["structural_total"]))

            exp_h, exp_a = self._structural_team_points(feats)
            h_res_list.append(h_pts - exp_h)
            a_res_list.append(a_pts - exp_a)

        X = np.asarray(X_rows, dtype=float)
        y = np.asarray(y_totals, dtype=float)
        s = np.asarray(s_totals, dtype=float)
        y_res = y - s

        sample_weights = np.exp(np.linspace(-0.75, 0.0, len(X)))
        model = make_pipeline(StandardScaler(), RidgeCV(alphas=[30.0, 100.0, 300.0, 800.0, 1500.0]))
        model.fit(X, y_res, ridgecv__sample_weight=sample_weights)
        self.ml_weight = min(0.30, 0.12 + len(train_sample) / 5000.0)

        h_res = np.asarray(h_res_list, dtype=float)
        a_res = np.asarray(a_res_list, dtype=float)
        var_h = float(np.var(h_res, ddof=1))
        var_a = float(np.var(a_res, ddof=1))
        cov_matrix = np.cov(h_res, a_res, ddof=1)
        cov_ha = float(cov_matrix[0, 1])

        var_indep = max(100.0, var_h + var_a)
        var_total_with_cov = max(196.0, var_h + var_a + 2.0 * cov_ha)

        self.independent_std = float(np.sqrt(var_indep))
        self.total_std = float(np.clip(np.sqrt(var_total_with_cov), 16.2, 20.5))
        self.score_covariance = round(cov_ha, 4)
        denom = math.sqrt(max(1e-6, var_h * var_a))
        self.score_correlation = round(cov_ha / denom, 4)
        self.regressor = model
        self.is_fitted = True

    @staticmethod
    def _structural_team_points(feats: dict[str, float]) -> tuple[float, float]:
        struct_tot = feats["structural_total"]
        struct_mar = feats["structural_margin"]
        exp_h = 0.5 * (struct_tot + struct_mar)
        exp_a = 0.5 * (struct_tot - struct_mar)
        return exp_h, exp_a

    def predict_total_points(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        line_value: float,
    ) -> dict[str, float]:
        feats = build_pregame_features(game, historical_games, market="total_points")
        exp_h, exp_a = self._structural_team_points(feats)
        structural_total = exp_h + exp_a

        if self.is_fitted and self.regressor is not None:
            x_vec = np.asarray([[feats[c] for c in TOTAL_FEATURE_COLUMNS]], dtype=float)
            res_tot = float(np.clip(self.regressor.predict(x_vec)[0], -5.5, 5.5))
            adj = self.ml_weight * res_tot
            expected_total = structural_total + adj
            exp_h += 0.5 * adj
            exp_a += 0.5 * adj
        else:
            expected_total = structural_total

        eff_std = float(np.clip(0.65 * self.total_std + 0.35 * feats["dynamic_total_std"], 16.5, 20.2))

        is_integer_line = abs(line_value - round(line_value)) < 1e-6
        if is_integer_line:
            p_over_raw = 1.0 - norm.cdf(line_value + 0.5, loc=expected_total, scale=eff_std)
            p_under_raw = norm.cdf(line_value - 0.5, loc=expected_total, scale=eff_std)
            p_push = max(0.0, 1.0 - p_over_raw - p_under_raw)
            non_push = max(1e-6, p_over_raw + p_under_raw)
            p_over = float(np.clip(p_over_raw / non_push, 0.05, 0.95))
            p_under = float(np.clip(p_under_raw / non_push, 0.05, 0.95))
        else:
            p_push = 0.0
            p_over = float(np.clip(1.0 - norm.cdf(line_value, loc=expected_total, scale=eff_std), 0.05, 0.95))
            p_under = round(1.0 - p_over, 6)

        return {
            "expected_home_points": round(exp_h, 2),
            "expected_away_points": round(exp_a, 2),
            "expected_total": round(expected_total, 2),
            "total_std_with_covariance": round(eff_std, 3),
            "independent_std_naive": round(self.independent_std, 3),
            "score_covariance": round(self.score_covariance, 3),
            "score_correlation": round(self.score_correlation, 3),
            "p_over": round(p_over, 6),
            "p_under": round(p_under, 6),
            "p_push_estimate": round(float(p_push), 6),
            "uncertainty_std": 0.055,
        }
