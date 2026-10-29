"""
Statistical NBA Models (Section 5):
- Model A: BaselineModel (historical reference probabilities and rolling rates)
- Model B: EloModel (sequential Elo adjusted for home court and rest days)
- Model C: PointMarginModel (Ridge regression on offensive/defensive/net ratings, pace, rest, form)
- Model D: TotalPointsModel (normal distribution explicitly accounting for home/away score covariance)
- Model E: AdvancedGBMModel (LightGBM evaluated strictly out-of-sample)
"""

from __future__ import annotations

from typing import Any
import numpy as np
from scipy.stats import norm
from sklearn.linear_model import Ridge
from lightgbm import LGBMClassifier, LGBMRegressor

from src.features.builder import build_pregame_features
from src.validation.validator import parse_iso_utc, validate_essential_features


FEATURE_COLUMNS: list[str] = [
    "home_off_rtg",
    "home_def_rtg",
    "away_off_rtg",
    "away_def_rtg",
    "net_rtg_diff",
    "expected_pace",
    "rest_diff",
    "recent_margin_diff",
    "home_court_indicator",
]


def _filter_strictly_prior_final_games(
    historical_games: list[dict[str, Any]],
    cutoff_time_str: str,
) -> list[dict[str, Any]]:
    cutoff_dt = parse_iso_utc(cutoff_time_str)
    valid = [
        g
        for g in historical_games
        if g.get("status") == "FINAL"
        and g.get("home_score") is not None
        and g.get("away_score") is not None
        and parse_iso_utc(g["game_start_time"]) < cutoff_dt
    ]
    valid.sort(key=lambda g: g["game_start_time"])
    return valid


class BaselineModel:
    """
    Modelo A (Baseline):
    Uses historical home win frequency, team rolling win rates, and historical total points distribution.
    Provides an explicit benchmark to measure whether complex models add value.
    """

    model_family = "model_a_baseline"

    def __init__(self, version_id: str = "model_a_baseline_v1") -> None:
        self.version_id = version_id
        self.historical_home_win_rate: float = 0.565
        self.historical_total_mean: float = 228.5
        self.historical_total_std: float = 17.5

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        if not prior:
            return
        home_wins = [1.0 if g["home_score"] > g["away_score"] else 0.0 for g in prior]
        totals = [float(g["home_score"] + g["away_score"]) for g in prior]
        self.historical_home_win_rate = float(np.clip(np.mean(home_wins), 0.35, 0.70))
        self.historical_total_mean = float(np.mean(totals))
        self.historical_total_std = max(10.0, float(np.std(totals, ddof=1)) if len(totals) > 2 else 17.5)

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
    ) -> dict[str, float]:
        feats = build_pregame_features(game, historical_games, market="moneyline")
        win_pct_diff = feats["home_recent_win_pct"] - feats["away_recent_win_pct"]
        p_home = float(np.clip(self.historical_home_win_rate + 0.15 * win_pct_diff, 0.08, 0.92))
        return {
            "p_home": round(p_home, 6),
            "p_away": round(1.0 - p_home, 6),
            "uncertainty_std": 0.085,
        }

    def predict_total_points(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        line_value: float,
    ) -> dict[str, float]:
        validate_essential_features(game, "total_points")
        p_over = float(np.clip(1.0 - norm.cdf(line_value, loc=self.historical_total_mean, scale=self.historical_total_std), 0.05, 0.95))
        return {
            "expected_total": round(self.historical_total_mean, 2),
            "total_std": round(self.historical_total_std, 2),
            "p_over": round(p_over, 6),
            "p_under": round(1.0 - p_over, 6),
            "uncertainty_std": 0.09,
        }


class EloModel:
    """
    Modelo B (Elo):
    Sequential Elo system adjusted for home-court advantage and rest differential,
    strictly using games completed prior to each prediction.
    """

    model_family = "model_b_elo"

    def __init__(
        self,
        version_id: str = "model_b_elo_v1",
        initial_rating: float = 1500.0,
        k_factor: float = 20.0,
        home_advantage_elo: float = 65.0,
        rest_advantage_per_day: float = 12.0,
    ) -> None:
        self.version_id = version_id
        self.initial_rating = initial_rating
        self.k_factor = k_factor
        self.home_advantage_elo = home_advantage_elo
        self.rest_advantage_per_day = rest_advantage_per_day
        self.ratings: dict[str, float] = {}

    def compute_ratings_as_of(
        self,
        historical_games: list[dict[str, Any]],
        cutoff_time_str: str,
    ) -> dict[str, float]:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        ratings: dict[str, float] = {}

        for g in prior:
            h_team = g["home_team"]
            a_team = g["away_team"]
            r_home = ratings.get(h_team, self.initial_rating)
            r_away = ratings.get(a_team, self.initial_rating)

            rest_diff = float(g.get("home_rest_days", 2) - g.get("away_rest_days", 2))
            elo_diff = (r_home + self.home_advantage_elo + self.rest_advantage_per_day * rest_diff) - r_away
            exp_home = 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))

            actual_home = 1.0 if g["home_score"] > g["away_score"] else 0.0
            margin = abs(float(g["home_score"] - g["away_score"]))
            mov_multiplier = ((margin + 3.0) ** 0.8) / (7.5 + 0.006 * abs(elo_diff))

            delta = self.k_factor * mov_multiplier * (actual_home - exp_home)
            ratings[h_team] = r_home + delta
            ratings[a_team] = r_away - delta

        self.ratings = ratings
        return ratings

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
    ) -> dict[str, float]:
        validate_essential_features(game, "moneyline")
        ratings = self.compute_ratings_as_of(historical_games, game["game_start_time"])
        r_home = ratings.get(game["home_team"], self.initial_rating)
        r_away = ratings.get(game["away_team"], self.initial_rating)
        rest_diff = float(game["home_rest_days"] - game["away_rest_days"])

        elo_diff = (r_home + self.home_advantage_elo + self.rest_advantage_per_day * rest_diff) - r_away
        p_home = float(np.clip(1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0)), 0.06, 0.94))
        return {
            "home_elo": round(r_home, 2),
            "away_elo": round(r_away, 2),
            "elo_diff": round(elo_diff, 2),
            "p_home": round(p_home, 6),
            "p_away": round(1.0 - p_home, 6),
            "uncertainty_std": 0.065,
        }


class PointMarginModel:
    """
    Modelo C (Margen de Puntos):
    Estimates expected point differential E[Home - Away] using offensive/defensive/net ratings,
    pace, home court, rest days, and recent form. Maps expected margin to win probability.
    """

    model_family = "model_c_point_margin"

    def __init__(
        self,
        version_id: str = "model_c_point_margin_v1",
        alpha: float = 5.0,
        default_residual_std: float = 11.8,
        home_court_points: float = 2.6,
    ) -> None:
        self.version_id = version_id
        self.alpha = alpha
        self.residual_std = default_residual_std
        self.home_court_points = home_court_points
        self.regressor: Ridge | None = None
        self.is_fitted = False

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        if len(prior) < 15:
            self.is_fitted = False
            return

        X_rows: list[list[float]] = []
        y_vals: list[float] = []
        for idx, g in enumerate(prior):
            sub_hist = prior[:idx]
            feats = build_pregame_features(g, sub_hist, market="moneyline")
            X_rows.append([feats[c] for c in FEATURE_COLUMNS])
            y_vals.append(float(g["home_score"] - g["away_score"]))

        X = np.asarray(X_rows, dtype=float)
        y = np.asarray(y_vals, dtype=float)
        model = Ridge(alpha=50.0, random_state=42)
        model.fit(X, y)
        preds = 0.30 * model.predict(X) + 0.70 * np.asarray(
            [
                (row[4] * (row[5] / 100.0) * 0.5 + self.home_court_points + 0.8 * row[6])
                for row in X_rows
            ],
            dtype=float,
        )
        residuals = y - preds
        self.residual_std = float(np.clip(np.std(residuals, ddof=1), 9.5, 15.0))
        self.regressor = model
        self.is_fitted = True

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
    ) -> dict[str, float]:
        feats = build_pregame_features(game, historical_games, market="moneyline")
        # Theoretical structural efficiency margin
        pace_factor = feats["expected_pace"] / 100.0
        structural_margin = (
            feats["net_rtg_diff"] * pace_factor * 0.5
            + self.home_court_points
            + 0.8 * feats["rest_diff"]
            + 0.08 * feats["recent_margin_diff"]
        )

        if self.is_fitted and self.regressor is not None:
            x_vec = np.asarray([[feats[c] for c in FEATURE_COLUMNS]], dtype=float)
            reg_margin = float(self.regressor.predict(x_vec)[0])
            expected_margin = 0.30 * reg_margin + 0.70 * structural_margin
        else:
            expected_margin = structural_margin

        p_home = float(np.clip(1.0 - norm.cdf(0.0, loc=expected_margin, scale=self.residual_std), 0.05, 0.95))
        return {
            "expected_margin": round(expected_margin, 3),
            "margin_std": round(self.residual_std, 3),
            "p_home": round(p_home, 6),
            "p_away": round(1.0 - p_home, 6),
            "uncertainty_std": 0.052,
        }


class TotalPointsModel:
    """
    Modelo D (Total de Puntos):
    Models the distribution of T = Score_home + Score_away using offensive/defensive ratings,
    pace, and rest.
    Explicitly estimates and includes the covariance Cov(Score_home, Score_away):
        Var(H + A) = Var(H) + Var(A) + 2 * Cov(H, A)
    rather than assuming naive independence between team scores.
    """

    model_family = "model_d_total_points"

    def __init__(
        self,
        version_id: str = "model_d_total_points_v1",
        default_total_std: float = 15.8,
    ) -> None:
        self.version_id = version_id
        self.total_std = default_total_std
        self.independent_std = 13.5
        self.score_covariance = 32.0  # Positive covariance induced by shared game pace
        self.score_correlation = 0.28
        self.regressor: Ridge | None = None
        self.is_fitted = False

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        if len(prior) < 15:
            self.is_fitted = False
            return

        X_rows: list[list[float]] = []
        y_totals: list[float] = []
        h_res_list: list[float] = []
        a_res_list: list[float] = []

        for idx, g in enumerate(prior):
            sub_hist = prior[:idx]
            feats = build_pregame_features(g, sub_hist, market="total_points")
            X_rows.append([feats[c] for c in FEATURE_COLUMNS])
            h_pts = float(g["home_score"])
            a_pts = float(g["away_score"])
            y_totals.append(h_pts + a_pts)

            exp_h, exp_a = self._structural_team_points(feats)
            h_res_list.append(h_pts - exp_h)
            a_res_list.append(a_pts - exp_a)

        X = np.asarray(X_rows, dtype=float)
        y = np.asarray(y_totals, dtype=float)
        model = Ridge(alpha=50.0, random_state=42)
        model.fit(X, y)

        h_res = np.asarray(h_res_list, dtype=float)
        a_res = np.asarray(a_res_list, dtype=float)
        var_h = float(np.var(h_res, ddof=1))
        var_a = float(np.var(a_res, ddof=1))
        cov_matrix = np.cov(h_res, a_res, ddof=1)
        cov_ha = float(cov_matrix[0, 1])

        var_indep = max(64.0, var_h + var_a)
        var_total_with_cov = max(81.0, var_h + var_a + 2.0 * cov_ha)

        self.independent_std = float(np.sqrt(var_indep))
        self.total_std = float(np.clip(np.sqrt(var_total_with_cov), 11.0, 22.0))
        self.score_covariance = round(cov_ha, 4)
        denom = math.sqrt(max(1e-6, var_h * var_a))
        self.score_correlation = round(cov_ha / denom, 4)
        self.regressor = model
        self.is_fitted = True

    @staticmethod
    def _structural_team_points(feats: dict[str, float]) -> tuple[float, float]:
        pace = feats["expected_pace"]
        exp_h = ((feats["home_off_rtg"] + feats["away_def_rtg"]) / 200.0) * pace + 1.3
        exp_a = ((feats["away_off_rtg"] + feats["home_def_rtg"]) / 200.0) * pace - 1.3
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
            x_vec = np.asarray([[feats[c] for c in FEATURE_COLUMNS]], dtype=float)
            reg_total = float(self.regressor.predict(x_vec)[0])
            expected_total = 0.30 * reg_total + 0.70 * structural_total
        else:
            expected_total = structural_total

        # Handle integer lines vs half-point lines
        is_integer_line = abs(line_value - round(line_value)) < 1e-6
        if is_integer_line:
            p_over_raw = 1.0 - norm.cdf(line_value + 0.5, loc=expected_total, scale=self.total_std)
            p_under_raw = norm.cdf(line_value - 0.5, loc=expected_total, scale=self.total_std)
            p_push = max(0.0, 1.0 - p_over_raw - p_under_raw)
            non_push = max(1e-6, p_over_raw + p_under_raw)
            p_over = float(np.clip(p_over_raw / non_push, 0.05, 0.95))
            p_under = float(np.clip(p_under_raw / non_push, 0.05, 0.95))
        else:
            p_push = 0.0
            p_over = float(np.clip(1.0 - norm.cdf(line_value, loc=expected_total, scale=self.total_std), 0.05, 0.95))
            p_under = round(1.0 - p_over, 6)

        return {
            "expected_home_points": round(exp_h, 2),
            "expected_away_points": round(exp_a, 2),
            "expected_total": round(expected_total, 2),
            "total_std_with_covariance": round(self.total_std, 3),
            "independent_std_naive": round(self.independent_std, 3),
            "score_covariance": round(self.score_covariance, 3),
            "score_correlation": round(self.score_correlation, 3),
            "p_over": round(p_over, 6),
            "p_under": round(p_under, 6),
            "p_push_estimate": round(float(p_push), 6),
            "uncertainty_std": 0.058,
        }


import math


class AdvancedGBMModel:
    """
    Modelo E (Modelo Avanzado LightGBM):
    Trained and evaluated strictly out-of-sample after establishing solid baselines A-D.
    """

    model_family = "model_e_lightgbm"

    def __init__(self, version_id: str = "model_e_lightgbm_v1") -> None:
        self.version_id = version_id
        self.clf: LGBMClassifier | None = None
        self.reg: LGBMRegressor | None = None
        self.total_residual_std: float = 16.0
        self.is_fitted = False

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        if len(prior) < 30:
            self.is_fitted = False
            return

        X_rows: list[list[float]] = []
        y_cls: list[int] = []
        y_tot: list[float] = []

        for idx, g in enumerate(prior):
            sub_hist = prior[:idx]
            feats = build_pregame_features(g, sub_hist, market="total_points")
            X_rows.append([feats[c] for c in FEATURE_COLUMNS])
            y_cls.append(1 if g["home_score"] > g["away_score"] else 0)
            y_tot.append(float(g["home_score"] + g["away_score"]))

        X = np.asarray(X_rows, dtype=float)
        y_c = np.asarray(y_cls, dtype=int)
        y_t = np.asarray(y_tot, dtype=float)

        clf = LGBMClassifier(
            n_estimators=50,
            learning_rate=0.05,
            max_depth=3,
            num_leaves=7,
            min_child_samples=10,
            random_state=42,
            verbose=-1,
        )
        clf.fit(X, y_c)

        reg = LGBMRegressor(
            n_estimators=50,
            learning_rate=0.05,
            max_depth=3,
            num_leaves=7,
            min_child_samples=10,
            random_state=42,
            verbose=-1,
        )
        reg.fit(X, y_t)
        tot_preds = reg.predict(X)
        self.total_residual_std = float(np.clip(np.std(y_t - tot_preds, ddof=1), 11.5, 22.0))

        self.clf = clf
        self.reg = reg
        self.is_fitted = True

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
    ) -> dict[str, float]:
        feats = build_pregame_features(game, historical_games, market="moneyline")
        if not self.is_fitted or self.clf is None:
            fallback = PointMarginModel()
            return fallback.predict_moneyline(game, historical_games)

        x_vec = np.asarray([[feats[c] for c in FEATURE_COLUMNS]], dtype=float)
        prob_home = float(np.clip(self.clf.predict_proba(x_vec)[0, 1], 0.06, 0.94))
        return {
            "p_home": round(prob_home, 6),
            "p_away": round(1.0 - prob_home, 6),
            "uncertainty_std": 0.062,
        }

    def predict_total_points(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        line_value: float,
    ) -> dict[str, float]:
        feats = build_pregame_features(game, historical_games, market="total_points")
        if not self.is_fitted or self.reg is None:
            fallback = TotalPointsModel()
            return fallback.predict_total_points(game, historical_games, line_value)

        x_vec = np.asarray([[feats[c] for c in FEATURE_COLUMNS]], dtype=float)
        exp_total = float(self.reg.predict(x_vec)[0])
        p_over = float(np.clip(1.0 - norm.cdf(line_value, loc=exp_total, scale=self.total_residual_std), 0.05, 0.95))
        return {
            "expected_total": round(exp_total, 2),
            "total_std": round(self.total_residual_std, 3),
            "p_over": round(p_over, 6),
            "p_under": round(1.0 - p_over, 6),
            "uncertainty_std": 0.065,
        }
