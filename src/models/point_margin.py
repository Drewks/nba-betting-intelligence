"""
Modelo C: Point Margin NBA Model.
Estimates expected point differential E[Home - Away] using a hybrid structural baseline
(combining dual-speed Elo spread, pace-normalized opponent-adjusted net rating, schedule density
fatigue, geodesic travel, altitude, and venue splits) plus a recency-weighted RidgeCV correction.
"""

from __future__ import annotations

from typing import Any
import numpy as np
from scipy.stats import norm
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.features.builder import build_pregame_features
from src.models.common import (
    MARGIN_FEATURE_COLUMNS,
    _filter_strictly_prior_final_games,
    build_oof_sigma_metadata,
    iter_expanding_temporal_oof_folds,
    make_fold_record,
)


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
        self.default_residual_std = default_residual_std
        self.residual_std = default_residual_std
        self.win_prob_std = 11.5
        self.home_court_points = home_court_points
        self.regressor: Any = None
        self.ml_weight: float = 0.22
        self.sigma_metadata: dict[str, Any] = {}
        self.is_fitted = False

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        if len(prior) < 20:
            self.is_fitted = False
            self.sigma_metadata = build_oof_sigma_metadata(
                method="unfitted_insufficient_games",
                oof_residuals=[],
                insample_residuals=None,
                effective_sigma=self.residual_std,
                fold_records=[],
                train_sample=prior,
            )
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

        # Strictly temporal walk-forward out-of-fold residual estimation for sigma (F-001).
        min_warmup = min(40, max(10, len(train_sample) // 3))
        folds = iter_expanding_temporal_oof_folds(train_sample, min_warmup=min_warmup, n_folds=5)
        oof_residuals: list[float] = []
        fold_records: list[dict[str, Any]] = []
        alphas = [40.0, 120.0, 300.0, 600.0, 1200.0]

        for train_idx, val_idx, fold_cutoff in folds:
            w_fold = np.exp(np.linspace(-0.75, 0.0, len(train_idx)))
            fold_model = make_pipeline(StandardScaler(), RidgeCV(alphas=alphas))
            fold_model.fit(X[train_idx], y_res[train_idx], ridgecv__sample_weight=w_fold)
            fold_weight = min(0.28, 0.12 + len(train_idx) / 5000.0)
            fold_preds = s[val_idx] + fold_weight * np.asarray(fold_model.predict(X[val_idx]), dtype=float)
            oof_residuals.extend((y[val_idx] - fold_preds).tolist())
            fold_records.append(make_fold_record(train_sample, train_idx, val_idx, fold_cutoff))

        if len(oof_residuals) >= 10:
            oof_std = float(np.std(np.asarray(oof_residuals, dtype=float), ddof=1))
            self.residual_std = float(np.clip(oof_std, 11.5, 15.0))
            sigma_method = "temporal_expanding_oof"
        else:
            self.residual_std = float(self.default_residual_std)
            sigma_method = "insufficient_oof_default_prior"
        # Near margin=0 (clutch win/loss threshold), effective NBA normal scale is ~0.84 * full-game OOS RMS
        self.win_prob_std = float(np.clip(0.84 * self.residual_std, 11.2, 12.2))

        sample_weights = np.exp(np.linspace(-0.75, 0.0, len(X)))
        model = make_pipeline(StandardScaler(), RidgeCV(alphas=alphas))
        model.fit(X, y_res, ridgecv__sample_weight=sample_weights)

        self.ml_weight = min(0.28, 0.12 + len(train_sample) / 5000.0)
        # In-sample residuals computed solely for OOS-vs-in-sample diagnostic reporting, never for sigma.
        insample_preds = s + self.ml_weight * np.asarray(model.predict(X), dtype=float)
        self.sigma_metadata = build_oof_sigma_metadata(
            method=sigma_method,
            oof_residuals=oof_residuals,
            insample_residuals=(y - insample_preds),
            effective_sigma=self.residual_std,
            fold_records=fold_records,
            train_sample=train_sample,
        )
        self.regressor = model
        self.is_fitted = True

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
    ) -> dict[str, Any]:
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
            p_cover_raw = float(1.0 - norm.cdf(target_diff + 0.5, loc=expected_margin, scale=scale))
            p_loss_raw = float(norm.cdf(target_diff - 0.5, loc=expected_margin, scale=scale))
            p_push = max(0.0, 1.0 - p_cover_raw - p_loss_raw)
            non_push = max(1e-9, p_cover_raw + p_loss_raw)
            p_cond = float(np.clip(p_cover_raw / non_push, 1e-4, 1.0 - 1e-4))
            p_cover_home = (1.0 - p_push) * p_cond
        else:
            p_push = 0.0
            p_cover_home = float(np.clip(1.0 - norm.cdf(target_diff, loc=expected_margin, scale=scale), 1e-4, 1.0 - 1e-4))

        p_cover_r = round(float(p_cover_home), 6)
        p_push_r = round(float(p_push), 6)
        p_away_r = round(max(0.0, 1.0 - p_cover_r - p_push_r), 6)

        return {
            "spread_line_home": float(spread_line_home),
            "expected_margin": round(expected_margin, 3),
            "margin_std": round(scale, 3),
            "p_cover_home": p_cover_r,
            "p_cover_away": p_away_r,
            "p_push": p_push_r,
            "p_push_estimate": p_push_r,
            "uncertainty_std": 0.052,
        }
