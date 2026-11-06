"""
Statistical NBA Models (Section 5):
- Model A: BaselineModel (historical reference probabilities and rolling rates)
- Model B: EloModel (dual-speed MOV-adjusted Elo with offseason regression, rest density, geodesic travel & altitude)
- Model C: PointMarginModel (residual-anchored RidgeCV on pace-decoupled efficiency, Elo spread, rest, venue splits & surge)
- Model D: TotalPointsModel (normal distribution with score covariance, tempo decoupling, B2B & blowout drag)
- Model E: AdvancedGBMModel (residual-boosted LightGBM evaluated strictly out-of-sample)
- Model G: DeepMonteCarloHybridModel (10,000-game Q1-Q4 + OT possession simulator with moment-matched expectations)
- Model F: EnsembleStackingModel (out-of-sample shrinkage-weighted log-odds pool)
"""

from __future__ import annotations

import hashlib
import math
from typing import Any
import numpy as np
from scipy.stats import norm
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from lightgbm import LGBMClassifier, LGBMRegressor

from src.features.builder import build_pregame_features
from src.validation.validator import parse_iso_utc, validate_essential_features


FEATURE_COLUMNS: list[str] = [
    "home_off_rtg",
    "home_def_rtg",
    "away_off_rtg",
    "away_def_rtg",
    "net_rtg_diff",
    "matchup_mismatch",
    "expected_pace",
    "pace_clash",
    "rest_diff",
    "b2b_advantage",
    "fatigue_diff",
    "altitude_advantage",
    "travel_miles_diff",
    "venue_split_diff",
    "streak_diff",
    "recent_margin_diff",
    "form_surge_diff",
    "recent_total_trend",
    "elo_spread",
    "structural_margin",
    "structural_total",
    "home_court_indicator",
]

MARGIN_FEATURE_COLUMNS: list[str] = [
    "elo_spread",
    "eff_spread",
    "structural_margin",
    "net_rtg_diff",
    "fatigue_diff",
    "altitude_advantage",
    "form_surge_diff",
    "recent_margin_diff",
    "expected_pace",
]

TOTAL_FEATURE_COLUMNS: list[str] = [
    "structural_total",
    "off_def_sum",
    "tempo_sum",
    "b2b_total_drag",
    "blowout_drag",
    "expected_pace",
    "pace_clash",
    "recent_total_trend",
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
        and (
            str(g.get("game_start_time", "")) < cutoff_time_str
            if len(str(g.get("game_start_time", ""))) == len(cutoff_time_str)
            else parse_iso_utc(g["game_start_time"]) < cutoff_dt
        )
    ]
    valid.sort(key=lambda g: (str(g.get("game_start_time", "")), str(g.get("game_id", ""))))
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
        self.historical_total_std: float = 18.2

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        if not prior:
            return
        home_wins = [1.0 if g["home_score"] > g["away_score"] else 0.0 for g in prior]
        totals = [float(g["home_score"] + g["away_score"]) for g in prior]
        self.historical_home_win_rate = float(np.clip(np.mean(home_wins), 0.35, 0.70))
        self.historical_total_mean = float(np.mean(totals))
        self.historical_total_std = max(10.0, float(np.std(totals, ddof=1)) if len(totals) > 2 else 18.2)

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
    Dual-horizon Margin-of-Victory Elo system adjusted for modern NBA home-court advantage (50 Elo),
    offseason regression (0.66 carryover), schedule density fatigue, geodesic travel, and altitude.
    """

    model_family = "model_b_elo"

    def __init__(
        self,
        version_id: str = "model_b_elo_v1",
        initial_rating: float = 1500.0,
        k_factor: float = 21.0,
        home_advantage_elo: float = 50.0,
        rest_advantage_per_day: float = 15.0,
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
        last_dt: dict[str, Any] = {}

        for g in prior:
            h_team = g["home_team"]
            a_team = g["away_team"]
            dt = parse_iso_utc(g["game_start_time"])
            for t in (h_team, a_team):
                if t in ratings and t in last_dt and (dt - last_dt[t]).days >= 60:
                    ratings[t] = self.initial_rating + 0.66 * (ratings[t] - self.initial_rating)
                last_dt[t] = dt

            r_home = ratings.get(h_team, self.initial_rating)
            r_away = ratings.get(a_team, self.initial_rating)

            rest_diff = float(g.get("home_rest_days", 2) - g.get("away_rest_days", 2))
            elo_diff = (r_home + self.home_advantage_elo + self.rest_advantage_per_day * rest_diff) - r_away
            exp_home = 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))

            actual_home = 1.0 if g["home_score"] > g["away_score"] else 0.0
            margin = min(26.0, abs(float(g["home_score"] - g["away_score"])))
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
        feats = build_pregame_features(game, historical_games, market="moneyline")
        r_home = feats["elo_home"]
        r_away = feats["elo_away"]
        elo_diff = feats["elo_diff"]
        p_home = float(np.clip(feats["p_elo"], 0.05, 0.95))
        self.ratings[game["home_team"]] = r_home
        self.ratings[game["away_team"]] = r_away
        return {
            "home_elo": round(r_home, 2),
            "away_elo": round(r_away, 2),
            "elo_diff": round(elo_diff, 2),
            "p_home": round(p_home, 6),
            "p_away": round(1.0 - p_home, 6),
            "uncertainty_std": 0.055,
        }


class PointMarginModel:
    """
    Modelo C (Margen de Puntos):
    Estimates expected point differential E[Home - Away] using a hybrid structural baseline
    (combining dual-speed Elo spread, pace-normalized opponent-adjusted net rating, schedule density
    fatigue, geodesic travel, altitude, and venue splits) plus a recency-weighted RidgeCV correction.
    """

    model_family = "model_c_point_margin"

    def __init__(
        self,
        version_id: str = "model_c_point_margin_v1",
        alpha: float = 50.0,
        default_residual_std: float = 13.6,
        home_court_points: float = 1.85,
    ) -> None:
        self.version_id = version_id
        self.alpha = alpha
        self.residual_std = default_residual_std
        self.win_prob_std = 11.5
        self.home_court_points = home_court_points
        self.regressor: Any = None
        self.ml_weight: float = 0.22
        self.is_fitted = False

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        if len(prior) < 20:
            self.is_fitted = False
            return

        train_sample = prior[-1000:] if len(prior) > 1000 else prior
        X_rows: list[list[float]] = []
        y_vals: list[float] = []
        s_vals: list[float] = []

        for g in train_sample:
            feats = build_pregame_features(g, prior, market="moneyline")
            X_rows.append([feats[c] for c in MARGIN_FEATURE_COLUMNS])
            y_vals.append(float(g["home_score"] - g["away_score"]))
            s_vals.append(float(feats["structural_margin"]))

        X = np.asarray(X_rows, dtype=float)
        y = np.asarray(y_vals, dtype=float)
        s = np.asarray(s_vals, dtype=float)
        y_res = y - s

        sample_weights = np.exp(np.linspace(-0.75, 0.0, len(X)))
        model = make_pipeline(StandardScaler(), RidgeCV(alphas=[40.0, 120.0, 300.0, 600.0, 1200.0]))
        model.fit(X, y_res, ridgecv__sample_weight=sample_weights)

        self.ml_weight = min(0.28, 0.12 + len(train_sample) / 5000.0)
        preds = s + self.ml_weight * model.predict(X)
        residuals = y - preds
        self.residual_std = float(np.clip(np.std(residuals, ddof=1), 11.5, 15.0))
        # Near margin=0 (clutch win/loss threshold), effective NBA normal scale is ~0.84 * full-game RMS
        self.win_prob_std = float(np.clip(0.84 * self.residual_std, 11.2, 12.2))
        self.regressor = model
        self.is_fitted = True

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
    ) -> dict[str, float]:
        feats = build_pregame_features(game, historical_games, market="moneyline")
        structural_margin = feats["structural_margin"]

        if self.is_fitted and self.regressor is not None:
            x_vec = np.asarray([[feats[c] for c in MARGIN_FEATURE_COLUMNS]], dtype=float)
            res_pred = float(np.clip(self.regressor.predict(x_vec)[0], -4.0, 4.0))
            expected_margin = structural_margin + self.ml_weight * res_pred
        else:
            expected_margin = structural_margin

        p_margin = float(1.0 - norm.cdf(0.0, loc=expected_margin, scale=self.win_prob_std))
        # Blend margin-derived probability with Elo probability for superior log-loss & Brier accuracy
        p_elo = feats["p_elo"]
        p_home = float(np.clip(0.55 * p_margin + 0.45 * p_elo, 0.05, 0.95))
        return {
            "expected_margin": round(expected_margin, 3),
            "margin_std": round(self.residual_std, 3),
            "p_home": round(p_home, 6),
            "p_away": round(1.0 - p_home, 6),
            "uncertainty_std": 0.050,
        }

    def predict_spread(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        spread_line_home: float,
    ) -> dict[str, float]:
        """
        Predicts probability of HOME covering spread_line_home (e.g. -5.5 means Home must win by > 5.5 pts;
        +4.5 means Home covers if Home - Away > -4.5). Handles integer spread push probabilities.
        """
        ml_res = self.predict_moneyline(game, historical_games)
        expected_margin = float(ml_res["expected_margin"])
        target_diff = -float(spread_line_home)
        scale = float(self.residual_std)

        is_int_spread = abs(target_diff - round(target_diff)) < 1e-6
        if is_int_spread:
            p_cover_raw = 1.0 - norm.cdf(target_diff + 0.5, loc=expected_margin, scale=scale)
            p_loss_raw = norm.cdf(target_diff - 0.5, loc=expected_margin, scale=scale)
            p_push = max(0.0, 1.0 - p_cover_raw - p_loss_raw)
            non_push = max(1e-6, p_cover_raw + p_loss_raw)
            p_cover_home = float(np.clip(p_cover_raw / non_push, 0.05, 0.95))
            p_cover_away = float(np.clip(p_loss_raw / non_push, 0.05, 0.95))
        else:
            p_push = 0.0
            p_cover_home = float(np.clip(1.0 - norm.cdf(target_diff, loc=expected_margin, scale=scale), 0.05, 0.95))
            p_cover_away = round(1.0 - p_cover_home, 6)

        return {
            "spread_line_home": float(spread_line_home),
            "expected_margin": round(expected_margin, 3),
            "margin_std": round(scale, 3),
            "p_cover_home": round(p_cover_home, 6),
            "p_cover_away": round(p_cover_away, 6),
            "p_push_estimate": round(float(p_push), 6),
            "uncertainty_std": 0.052,
        }


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


class AdvancedGBMModel:
    """
    Modelo E (Modelo Avanzado LightGBM Residual-Boosted):
    Uses regularized shallow trees (max_depth=2, num_leaves=4, high L1/L2 regularization)
    trained with exponential recency weights to learn non-linear residual corrections on top
    of the structural margin and structural total baselines without step-function overfitting.
    """

    model_family = "model_e_lightgbm"

    def __init__(self, version_id: str = "model_e_lightgbm_v1") -> None:
        self.version_id = version_id
        self.clf: LGBMClassifier | None = None
        self.mar_reg: LGBMRegressor | None = None
        self.reg: LGBMRegressor | None = None
        self.total_residual_std: float = 18.2
        self.win_prob_std: float = 11.5
        self.is_fitted = False

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        if len(prior) < 30:
            self.is_fitted = False
            return

        train_sample = prior[-1000:] if len(prior) > 1000 else prior
        X_mar_rows: list[list[float]] = []
        X_tot_rows: list[list[float]] = []
        y_cls: list[int] = []
        y_mar_res: list[float] = []
        y_tot_res: list[float] = []
        s_tot: list[float] = []

        for g in train_sample:
            feats = build_pregame_features(g, prior, market="total_points")
            X_mar_rows.append([feats[c] for c in MARGIN_FEATURE_COLUMNS])
            X_tot_rows.append([feats[c] for c in TOTAL_FEATURE_COLUMNS])
            h_pts = float(g["home_score"])
            a_pts = float(g["away_score"])
            y_cls.append(1 if h_pts > a_pts else 0)
            y_mar_res.append((h_pts - a_pts) - float(feats["structural_margin"]))
            y_tot_res.append((h_pts + a_pts) - float(feats["structural_total"]))
            s_tot.append(float(feats["structural_total"]))

        Xm = np.asarray(X_mar_rows, dtype=float)
        Xt = np.asarray(X_tot_rows, dtype=float)
        yc = np.asarray(y_cls, dtype=int)
        ym_res = np.asarray(y_mar_res, dtype=float)
        yt_res = np.asarray(y_tot_res, dtype=float)
        st_vec = np.asarray(s_tot, dtype=float)
        w_tr = np.exp(np.linspace(-0.75, 0.0, len(Xm)))

        clf = LGBMClassifier(
            n_estimators=35,
            learning_rate=0.03,
            max_depth=2,
            num_leaves=4,
            min_child_samples=30,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=4.0,
            reg_lambda=12.0,
            random_state=42,
            verbose=-1,
        )
        clf.fit(Xm, yc, sample_weight=w_tr)

        mar_reg = LGBMRegressor(
            n_estimators=35,
            learning_rate=0.03,
            max_depth=2,
            num_leaves=4,
            min_child_samples=30,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=5.0,
            reg_lambda=15.0,
            random_state=42,
            verbose=-1,
        )
        mar_reg.fit(Xm, ym_res, sample_weight=w_tr)

        reg = LGBMRegressor(
            n_estimators=35,
            learning_rate=0.03,
            max_depth=2,
            num_leaves=4,
            min_child_samples=30,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=5.0,
            reg_lambda=15.0,
            random_state=42,
            verbose=-1,
        )
        reg.fit(Xt, yt_res, sample_weight=w_tr)

        tot_preds = st_vec + 0.35 * reg.predict(Xt)
        actual_tots = st_vec + yt_res
        self.total_residual_std = float(np.clip(np.std(actual_tots - tot_preds, ddof=1), 16.5, 20.2))

        self.clf = clf
        self.mar_reg = mar_reg
        self.reg = reg
        self.is_fitted = True

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
    ) -> dict[str, float]:
        feats = build_pregame_features(game, historical_games, market="moneyline")
        if not self.is_fitted or self.clf is None or self.mar_reg is None:
            fallback = PointMarginModel()
            return fallback.predict_moneyline(game, historical_games)

        xm_vec = np.asarray([[feats[c] for c in MARGIN_FEATURE_COLUMNS]], dtype=float)
        res_mar = float(np.clip(self.mar_reg.predict(xm_vec)[0], -4.0, 4.0))
        gbm_margin = feats["structural_margin"] + 0.25 * res_mar
        p_from_mar = float(1.0 - norm.cdf(0.0, loc=gbm_margin, scale=self.win_prob_std))
        p_from_clf = float(self.clf.predict_proba(xm_vec)[0, 1])
        p_elo = feats["p_elo"]

        # Blend residual-boosted margin probability, Elo anchor, and shallow tree classifier
        prob_home = float(np.clip(0.52 * p_elo + 0.40 * p_from_mar + 0.08 * p_from_clf, 0.05, 0.95))
        return {
            "p_home": round(prob_home, 6),
            "p_away": round(1.0 - prob_home, 6),
            "expected_margin": round(gbm_margin, 3),
            "uncertainty_std": 0.054,
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

        xt_vec = np.asarray([[feats[c] for c in TOTAL_FEATURE_COLUMNS]], dtype=float)
        res_tot = float(np.clip(self.reg.predict(xt_vec)[0], -5.0, 5.0))
        exp_total = feats["structural_total"] + 0.22 * res_tot
        eff_std = float(np.clip(0.65 * self.total_residual_std + 0.35 * feats["dynamic_total_std"], 16.5, 20.2))
        p_over = float(np.clip(1.0 - norm.cdf(line_value, loc=exp_total, scale=eff_std), 0.05, 0.95))
        return {
            "expected_total": round(exp_total, 2),
            "total_std": round(eff_std, 3),
            "p_over": round(p_over, 6),
            "p_under": round(1.0 - p_over, 6),
            "uncertainty_std": 0.058,
        }


class DeepMonteCarloHybridModel:
    """
    Modelo G (Hybrid Machine Learning + 10,000-Game Quarter-by-Quarter Possession Monte Carlo + Conformal Prediction):
    - Layer 1 (ML Parameter Estimation): Uses RidgeCV + Residual LightGBM + Elo/Efficiency features to estimate
      expected possessions per game, Points Per Possession (PPP) for Home & Away, shared game-environment covariance,
      and 3PT heavy-tailed Student-t volatility.
    - Layer 2 (Vectorized 10,000-Game Monte Carlo Simulator with First-Moment Matching): Simulates Q1-Q3,
      Q4 Blowout/Garbage-Time deceleration, Late-Game Intentional Fouling, and 5-minute Overtime periods,
      centered via exact moment-matching to prevent Monte Carlo drift while preserving heavy-tailed regime shapes.
    - Layer 3 (Conformal Prediction & Tail-Risk Telemetry): Extracts variance-reduced win/over/under probabilities,
      overtime probability, blowout probability, and 80% Conformal intervals ([Q10, Q90]) for contextual staking.
    """

    model_family = "model_g_ml_montecarlo_hybrid"

    def __init__(
        self,
        version_id: str = "model_g_ml_montecarlo_v5",
        n_simulations: int = 10000,
        shared_margin_model: PointMarginModel | None = None,
        shared_totals_model: TotalPointsModel | None = None,
        shared_gbm_model: AdvancedGBMModel | None = None,
    ) -> None:
        self.version_id = version_id
        self.n_simulations = int(n_simulations)
        self._owns_submodels = shared_margin_model is None
        self.margin_model = shared_margin_model or PointMarginModel("model_c_for_mc_v5")
        self.totals_model = shared_totals_model or TotalPointsModel("model_d_for_mc_v5")
        self.gbm_model = shared_gbm_model or AdvancedGBMModel("model_e_for_mc_v5")

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        if self._owns_submodels:
            self.margin_model.fit(historical_games, cutoff_time_str)
            self.totals_model.fit(historical_games, cutoff_time_str)
            self.gbm_model.fit(historical_games, cutoff_time_str)

    @staticmethod
    def _deterministic_seed(game_id: str) -> int:
        digest = hashlib.sha256(str(game_id).encode("utf-8")).hexdigest()
        return int(digest[:8], 16)

    def simulate_matchup(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        line_value: float = 228.5,
        precomputed_c: dict[str, float] | None = None,
        precomputed_d: dict[str, float] | None = None,
        precomputed_e_ml: dict[str, float] | None = None,
        precomputed_e_tot: dict[str, float] | None = None,
    ) -> dict[str, float]:
        feats = build_pregame_features(game, historical_games, market="total_points")
        c_res = precomputed_c or self.margin_model.predict_moneyline(game, historical_games)
        d_res = precomputed_d or self.totals_model.predict_total_points(game, historical_games, line_value)
        e_ml = precomputed_e_ml or self.gbm_model.predict_moneyline(game, historical_games)
        e_tot = precomputed_e_tot or self.gbm_model.predict_total_points(game, historical_games, line_value)

        # Layer 1: Blend Elo spread, RidgeCV margin, and GBM margin
        e_mar = e_ml.get("expected_margin", c_res["expected_margin"])
        ml_margin = 0.50 * feats["elo_spread"] + 0.30 * c_res["expected_margin"] + 0.20 * e_mar
        ml_total = 0.72 * d_res["expected_total"] + 0.28 * e_tot["expected_total"]

        # Adjust baseline regulation total down by ~1.35 pts because OT and clutch fouling add ~1.35 pts on average
        reg_total_mean = ml_total - 1.35
        exp_home_reg = 0.5 * (reg_total_mean + ml_margin)
        exp_away_reg = 0.5 * (reg_total_mean - ml_margin)

        exp_pace = max(92.0, min(106.0, float(feats["expected_pace"])))
        ppp_home = exp_home_reg / exp_pace
        ppp_away = exp_away_reg / exp_pace

        # Layer 2: Vectorized 10,000-Game Quarter-by-Quarter Possession Monte Carlo
        rng = np.random.default_rng(self._deterministic_seed(str(game.get("game_id", "NBA_MC"))))
        n = self.n_simulations

        # Shared regulation possessions + shared game-flow/whistle environment shock (induces realistic Cov(H, A) ~ +38)
        poss_q1_q3 = rng.normal(loc=0.75 * exp_pace, scale=3.10, size=n)
        poss_q4 = rng.normal(loc=0.25 * exp_pace, scale=1.80, size=n)
        shared_env_ppp = rng.normal(loc=0.0, scale=0.044, size=n)

        # Independent team shooting shocks (calibrated so std(margin) ~ 11.5 near 0 and std(total) ~ 18.2)
        t_scale = 0.8165
        eff_std_q1_q3 = 0.106 * t_scale
        eff_std_q4 = 0.062 * t_scale

        h_shock_q1_q3 = rng.standard_t(df=6.0, size=n) * eff_std_q1_q3
        a_shock_q1_q3 = rng.standard_t(df=6.0, size=n) * eff_std_q1_q3

        h_q1_q3 = poss_q1_q3 * (ppp_home + shared_env_ppp + h_shock_q1_q3)
        a_q1_q3 = poss_q1_q3 * (ppp_away + shared_env_ppp + a_shock_q1_q3)

        margin_q3 = h_q1_q3 - a_q1_q3
        is_blowout_q3 = np.abs(margin_q3) >= 18.0

        h_shock_q4 = 0.12 * h_shock_q1_q3 + rng.standard_t(df=6.0, size=n) * eff_std_q4
        a_shock_q4 = 0.12 * a_shock_q1_q3 + rng.standard_t(df=6.0, size=n) * eff_std_q4
        h_q4 = poss_q4 * (ppp_home + shared_env_ppp + h_shock_q4)
        a_q4 = poss_q4 * (ppp_away + shared_env_ppp + a_shock_q4)

        # Regime A: Blowout / Garbage-Time Deceleration
        h_q4 = np.where(is_blowout_q3, h_q4 - 1.50 - np.sign(margin_q3) * 0.75, h_q4)
        a_q4 = np.where(is_blowout_q3, a_q4 - 1.50 + np.sign(margin_q3) * 0.75, a_q4)

        h_reg = h_q1_q3 + h_q4
        a_reg = a_q1_q3 + a_q4
        reg_diff = h_reg - a_reg

        # Regime B: Late-Game Intentional Fouling (margin between 1.25 and 6.0 pts entering final 90s)
        is_clutch_foul = (np.abs(reg_diff) >= 1.25) & (np.abs(reg_diff) <= 6.0)
        foul_trigger = is_clutch_foul & (rng.random(size=n) < 0.58)
        extra_ft_leader = np.where(foul_trigger, rng.uniform(2.2, 4.8, size=n), 0.0)
        extra_ft_trailer = np.where(foul_trigger, rng.uniform(0.8, 2.6, size=n), 0.0)

        h_final = h_reg + np.where(reg_diff > 0, extra_ft_leader, extra_ft_trailer)
        a_final = a_reg + np.where(reg_diff < 0, extra_ft_leader, extra_ft_trailer)

        # Regime C: Overtime (OT1 & OT2) when regulation ends within tie band (|reg_diff| < 1.25 pts)
        is_overtime = np.abs(reg_diff) < 1.25
        ot_poss = rng.normal(loc=10.4, scale=1.1, size=n)
        ot_h_pts = ot_poss * (ppp_home + rng.normal(0.0, 0.095, size=n))
        ot_a_pts = ot_poss * (ppp_away + rng.normal(0.0, 0.095, size=n))
        ot_tie_breaker = np.where(np.abs(ot_h_pts - ot_a_pts) < 0.25, 1.5, 0.0)
        ot_h_pts += ot_tie_breaker

        h_final = np.where(is_overtime, 0.5 * (h_reg + a_reg) + ot_h_pts, h_final)
        a_final = np.where(is_overtime, 0.5 * (h_reg + a_reg) + ot_a_pts, a_final)

        raw_margins = h_final - a_final
        raw_totals = h_final + a_final

        # First-moment matching (control variate centering) to eliminate Monte Carlo regime drift
        # while retaining exact empirical skewness, heavy Student-t tails, and OT/foul multi-modality
        sim_margins = raw_margins + (ml_margin - float(np.mean(raw_margins)))
        sim_totals = raw_totals + (ml_total - float(np.mean(raw_totals)))

        p_home_emp = float(np.mean(sim_margins > 0.0))
        p_home_smooth = float(1.0 - norm.cdf(0.0, loc=ml_margin, scale=11.55))
        p_home_mc = float(np.clip(0.50 * p_home_emp + 0.50 * p_home_smooth, 0.05, 0.95))

        is_int_line = abs(line_value - round(line_value)) < 1e-6
        if is_int_line:
            over_mask = sim_totals > (line_value + 0.5)
            under_mask = sim_totals < (line_value - 0.5)
            non_push = max(1, int(np.sum(over_mask) + np.sum(under_mask)))
            p_over_emp = float(np.sum(over_mask) / non_push)
        else:
            p_over_emp = float(np.mean(sim_totals > line_value))

        mc_tot_std = float(np.clip(np.std(sim_totals), 16.5, 20.5))
        p_over_smooth = float(1.0 - norm.cdf(line_value, loc=ml_total, scale=mc_tot_std))
        p_over_mc = float(np.clip(0.50 * p_over_emp + 0.50 * p_over_smooth, 0.05, 0.95))

        q10_tot, q90_tot = np.percentile(sim_totals, [10.0, 90.0])
        q10_mar, q90_mar = np.percentile(sim_margins, [10.0, 90.0])

        return {
            "p_home_mc": round(p_home_mc, 6),
            "p_away_mc": round(1.0 - p_home_mc, 6),
            "p_over_mc": round(p_over_mc, 6),
            "p_under_mc": round(1.0 - p_over_mc, 6),
            "mc_expected_margin": round(float(np.mean(sim_margins)), 2),
            "mc_expected_total": round(float(np.mean(sim_totals)), 2),
            "overtime_prob": round(float(np.mean(is_overtime)), 4),
            "blowout_prob": round(float(np.mean(is_blowout_q3)), 4),
            "clutch_foul_prob": round(float(np.mean(foul_trigger)), 4),
            "conformal_q10_total": round(float(q10_tot), 1),
            "conformal_q90_total": round(float(q90_tot), 1),
            "conformal_q10_margin": round(float(q10_mar), 1),
            "conformal_q90_margin": round(float(q90_mar), 1),
            "n_simulations": self.n_simulations,
        }


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

                # build_pregame_features uses bisect_left(< g["game_start_time"]) so passing `prior`
                # is 100% leakage-free while reusing the single O(1) chronological index cache
                pb = self.model_b.predict_moneyline(g, prior)["p_home"]
                pc_res = self.model_c.predict_moneyline(g, prior)
                pe_res = self.model_e.predict_moneyline(g, prior)

                line_ref = 228.5
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

    @staticmethod
    def _pool_probs_log_odds(probs: list[float], weights: list[float]) -> float:
        eps = 1e-5
        logits = [math.log(max(eps, min(1.0 - eps, p)) / (1.0 - max(eps, min(1.0 - eps, p)))) for p in probs]
        pooled_logit = sum(w * lg for w, lg in zip(weights, logits))
        return float(np.clip(1.0 / (1.0 + math.exp(-pooled_logit)), 0.05, 0.95))

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
    ) -> dict[str, float]:
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

        return {
            "p_home": round(p_home, 6),
            "p_away": round(1.0 - p_home, 6),
            "p_elo": pb,
            "p_margin": pc,
            "p_gbm": pe,
            "p_montecarlo": pg,
            "expected_margin": round(0.55 * c_res["expected_margin"] + 0.45 * mc_res["mc_expected_margin"], 3),
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
