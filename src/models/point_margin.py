"""
Modelo C: Point Margin NBA Model (V9 Ridge/RAPM + Boxscore Availability Enhanced).
Estimates expected point differential E[Home - Away] using strictly out-of-fold simultaneous
multi-horizon Ridge adjusted efficiency, prior-informed Player RAPM, real Four Factors,
3PT luck regression, participation-delta player availability, and situational context.
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
from src.models.common import (
    MARGIN_FEATURE_COLUMNS,
    _filter_strictly_prior_final_games,
    build_enhanced_margin_vector,
    build_oof_sigma_metadata,
    fit_oof_logistic_scale,
    iter_expanding_temporal_oof_folds,
    make_fold_record,
)
from src.models.ridge_rapm import RidgeEfficiencyRAPMModel


class PointMarginModel:
    """
    Modelo C (Margen de Puntos):
    Combines strictly out-of-fold simultaneous multi-horizon Ridge adjusted efficiency,
    prior-informed Player RAPM, real Four Factors, participation-delta availability, and
    Elo/situational features via recency-weighted RidgeCV with expanding temporal OOF dispersion.
    """

    model_family = "model_c_point_margin"

    def __init__(
        self,
        version_id: str = "model_c_point_margin_v9",
        alpha: float = 50.0,
        default_residual_std: float = 13.6,
        home_court_points: float = 1.85,
        shared_ridge_rapm: RidgeEfficiencyRAPMModel | None = None,
    ) -> None:
        self.version_id = version_id
        self.alpha = alpha
        self.default_residual_std = default_residual_std
        self.residual_std = default_residual_std
        self.win_prob_std = 12.2
        self.win_logistic_scale = 7.4
        self.home_court_points = home_court_points
        self._owns_ridge_rapm = shared_ridge_rapm is None
        self.ridge_rapm = shared_ridge_rapm or RidgeEfficiencyRAPMModel("model_h_for_margin_v9")
        self.regressor: Any = None
        self.uses_enhanced_features: bool = False
        self.ml_weight: float = 0.22
        self.sigma_metadata: dict[str, Any] = {}
        self.oof_margin_preds: dict[str, float] = {}
        self.oof_win_probs: dict[str, float] = {}
        self.is_fitted = False

    def fit(
        self,
        historical_games: list[dict[str, Any]],
        cutoff_time_str: str,
        *,
        precomputed_feats: dict[str, dict[str, float]] | None = None,
        oof_ridge_map: dict[int, dict[str, float]] | None = None,
        train_sample_override: list[dict[str, Any]] | None = None,
    ) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        self.oof_margin_preds = {}
        self.oof_win_probs = {}
        if len(prior) < 20:
            self.is_fitted = False
            self.uses_enhanced_features = False
            self.sigma_metadata = build_oof_sigma_metadata(
                method="unfitted_insufficient_games",
                oof_residuals=[],
                insample_residuals=None,
                effective_sigma=self.residual_std,
                fold_records=[],
                train_sample=prior,
            )
            return

        if train_sample_override is not None:
            train_sample = train_sample_override
        else:
            train_sample = prior[-1500:] if len(prior) > 1500 else prior

        feats_by_gid: dict[str, dict[str, float]] = {}
        for g in train_sample:
            gid = str(g["game_id"])
            if precomputed_feats is not None and gid in precomputed_feats:
                feats_by_gid[gid] = precomputed_feats[gid]
            else:
                feats_by_gid[gid] = build_pregame_features(g, prior, market="total_points")

        if self._owns_ridge_rapm:
            self.ridge_rapm.fit(prior, cutoff_time_str, precomputed_feats=feats_by_gid)

        # Build strictly out-of-fold Ridge/RAPM features when sample is large enough (>= 80 games)
        use_enhanced = len(train_sample) >= 80 and self.ridge_rapm.is_fitted
        ridge_oof: dict[int, dict[str, float]] = {}
        if use_enhanced:
            if oof_ridge_map is not None:
                ridge_oof = oof_ridge_map
            else:
                min_w = min(80, max(30, len(train_sample) // 4))
                ridge_oof = self.ridge_rapm.compute_expanding_oof_predictions(
                    train_sample, prior, feats_by_gid, min_warmup=min_w, n_folds=12
                )
            if len(ridge_oof) < 40:
                use_enhanced = False

        if use_enhanced:
            self._fit_enhanced(train_sample, feats_by_gid, ridge_oof)
        else:
            self._fit_fallback_small_sample(train_sample, feats_by_gid)

    def _fit_enhanced(
        self,
        train_sample: list[dict[str, Any]],
        feats_by_gid: dict[str, dict[str, float]],
        ridge_oof: dict[int, dict[str, float]],
    ) -> None:
        valid_indices = sorted(ridge_oof.keys())
        sub_games = [train_sample[i] for i in valid_indices]
        x_rows: list[list[float]] = []
        y_vals: list[float] = []
        for orig_i in valid_indices:
            g = train_sample[orig_i]
            gid = str(g["game_id"])
            x_rows.append(build_enhanced_margin_vector(feats_by_gid[gid], ridge_oof[orig_i]))
            y_vals.append(float(g["home_score"] - g["away_score"]))

        x_mat = np.asarray(x_rows, dtype=float)
        y_arr = np.asarray(y_vals, dtype=float)
        alphas = [20.0, 80.0, 250.0, 800.0, 2000.0]

        min_warmup = min(80, max(20, len(sub_games) // 3))
        folds = iter_expanding_temporal_oof_folds(sub_games, min_warmup=min_warmup, n_folds=5)
        oof_residuals: list[float] = []
        fold_records: list[dict[str, Any]] = []

        for train_idx, val_idx, fold_cutoff in folds:
            w_fold = np.exp(np.linspace(-0.65, 0.0, len(train_idx)))
            fold_model = make_pipeline(StandardScaler(), RidgeCV(alphas=alphas))
            fold_model.fit(x_mat[train_idx], y_arr[train_idx], ridgecv__sample_weight=w_fold)
            fold_preds = np.asarray(fold_model.predict(x_mat[val_idx]), dtype=float)
            oof_residuals.extend((y_arr[val_idx] - fold_preds).tolist())
            fold_records.append(make_fold_record(sub_games, train_idx, val_idx, fold_cutoff))
            for local_pos, vi in enumerate(val_idx):
                gid = str(sub_games[vi]["game_id"])
                pred_m = float(fold_preds[local_pos])
                self.oof_margin_preds[gid] = pred_m

        if len(oof_residuals) >= 10:
            oof_std = float(np.std(np.asarray(oof_residuals, dtype=float), ddof=1))
            self.residual_std = float(np.clip(oof_std, 11.5, 15.2))
            sigma_method = "temporal_expanding_oof"
        else:
            self.residual_std = float(self.default_residual_std)
            sigma_method = "insufficient_oof_default_prior"

        self.win_prob_std = float(np.clip(0.86 * self.residual_std, 11.5, 13.0))
        # Fit logistic link scale strictly on OOF margins/outcomes (shrunk toward Gaussian-matched sigma/1.702)
        oof_m_list: list[float] = []
        oof_y_list: list[float] = []
        for g in sub_games:
            gid = str(g["game_id"])
            if gid in self.oof_margin_preds:
                oof_m_list.append(self.oof_margin_preds[gid])
                oof_y_list.append(1.0 if float(g["home_score"]) > float(g["away_score"]) else 0.0)
        prior_scale = float(np.clip(0.535 * self.residual_std, 7.2, 8.0))
        self.win_logistic_scale = fit_oof_logistic_scale(oof_m_list, oof_y_list, prior_scale=prior_scale)

        for gid, pred_m in self.oof_margin_preds.items():
            self.oof_win_probs[gid] = float(
                np.clip(1.0 / (1.0 + math.exp(-pred_m / self.win_logistic_scale)), 0.03, 0.97)
            )

        sample_weights = np.exp(np.linspace(-0.65, 0.0, len(x_mat)))
        model = make_pipeline(StandardScaler(), RidgeCV(alphas=alphas))
        model.fit(x_mat, y_arr, ridgecv__sample_weight=sample_weights)

        insample_preds = np.asarray(model.predict(x_mat), dtype=float)
        self.sigma_metadata = build_oof_sigma_metadata(
            method=sigma_method,
            oof_residuals=oof_residuals,
            insample_residuals=(y_arr - insample_preds),
            effective_sigma=self.residual_std,
            fold_records=fold_records,
            train_sample=sub_games,
        )
        self.regressor = model
        self.uses_enhanced_features = True
        self.is_fitted = True

    def _fit_fallback_small_sample(
        self,
        train_sample: list[dict[str, Any]],
        feats_by_gid: dict[str, dict[str, float]],
    ) -> None:
        x_rows: list[list[float]] = []
        y_vals: list[float] = []
        s_vals: list[float] = []
        for g in train_sample:
            feats = feats_by_gid[str(g["game_id"])]
            x_rows.append([feats[c] for c in MARGIN_FEATURE_COLUMNS])
            y_vals.append(float(g["home_score"] - g["away_score"]))
            s_vals.append(float(feats["structural_margin"]))

        x_mat = np.asarray(x_rows, dtype=float)
        y_arr = np.asarray(y_vals, dtype=float)
        s_arr = np.asarray(s_vals, dtype=float)
        y_res = y_arr - s_arr

        min_warmup = min(40, max(10, len(train_sample) // 3))
        folds = iter_expanding_temporal_oof_folds(train_sample, min_warmup=min_warmup, n_folds=5)
        oof_residuals: list[float] = []
        fold_records: list[dict[str, Any]] = []
        alphas = [40.0, 120.0, 300.0, 600.0, 1200.0]

        for train_idx, val_idx, fold_cutoff in folds:
            w_fold = np.exp(np.linspace(-0.75, 0.0, len(train_idx)))
            fold_model = make_pipeline(StandardScaler(), RidgeCV(alphas=alphas))
            fold_model.fit(x_mat[train_idx], y_res[train_idx], ridgecv__sample_weight=w_fold)
            fold_weight = min(0.28, 0.12 + len(train_idx) / 5000.0)
            fold_preds = s_arr[val_idx] + fold_weight * np.asarray(fold_model.predict(x_mat[val_idx]), dtype=float)
            oof_residuals.extend((y_arr[val_idx] - fold_preds).tolist())
            fold_records.append(make_fold_record(train_sample, train_idx, val_idx, fold_cutoff))

        if len(oof_residuals) >= 10:
            oof_std = float(np.std(np.asarray(oof_residuals, dtype=float), ddof=1))
            self.residual_std = float(np.clip(oof_std, 11.5, 15.0))
            sigma_method = "temporal_expanding_oof"
        else:
            self.residual_std = float(self.default_residual_std)
            sigma_method = "insufficient_oof_default_prior"
        self.win_prob_std = float(np.clip(0.84 * self.residual_std, 11.2, 12.2))
        self.win_logistic_scale = float(np.clip(0.515 * self.residual_std, 6.9, 7.9))

        sample_weights = np.exp(np.linspace(-0.75, 0.0, len(x_mat)))
        model = make_pipeline(StandardScaler(), RidgeCV(alphas=alphas))
        model.fit(x_mat, y_res, ridgecv__sample_weight=sample_weights)

        self.ml_weight = min(0.28, 0.12 + len(train_sample) / 5000.0)
        insample_preds = s_arr + self.ml_weight * np.asarray(model.predict(x_mat), dtype=float)
        self.sigma_metadata = build_oof_sigma_metadata(
            method=sigma_method,
            oof_residuals=oof_residuals,
            insample_residuals=(y_arr - insample_preds),
            effective_sigma=self.residual_std,
            fold_records=fold_records,
            train_sample=train_sample,
        )
        self.regressor = model
        self.uses_enhanced_features = False
        self.is_fitted = True

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        *,
        precomputed_feats: dict[str, float] | None = None,
        precomputed_ridge: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        feats = precomputed_feats if precomputed_feats is not None else build_pregame_features(
            game, historical_games, market="moneyline"
        )
        structural_margin = float(feats["structural_margin"])

        if self.is_fitted and self.regressor is not None:
            if self.uses_enhanced_features:
                ridge_pred = precomputed_ridge if precomputed_ridge is not None else self.ridge_rapm.predict_matchup(
                    game, historical_games, precomputed_feats=feats
                )
                x_vec = np.asarray([build_enhanced_margin_vector(feats, ridge_pred)], dtype=float)
                expected_margin = float(np.clip(self.regressor.predict(x_vec)[0], -28.0, 28.0))
                p_home = float(
                    np.clip(1.0 / (1.0 + math.exp(-expected_margin / self.win_logistic_scale)), 0.03, 0.97)
                )
            else:
                x_vec = np.asarray([[feats[c] for c in MARGIN_FEATURE_COLUMNS]], dtype=float)
                res_pred = float(np.clip(self.regressor.predict(x_vec)[0], -4.0, 4.0))
                expected_margin = structural_margin + self.ml_weight * res_pred
                p_margin = float(1.0 - norm.cdf(0.0, loc=expected_margin, scale=self.win_prob_std))
                p_elo = float(feats["p_elo"])
                p_home = float(np.clip(0.55 * p_margin + 0.45 * p_elo, 0.05, 0.95))
        else:
            expected_margin = structural_margin
            p_margin = float(1.0 - norm.cdf(0.0, loc=expected_margin, scale=self.win_prob_std))
            p_elo = float(feats["p_elo"])
            p_home = float(np.clip(0.55 * p_margin + 0.45 * p_elo, 0.05, 0.95))

        return {
            "expected_margin": round(expected_margin, 3),
            "margin_std": round(self.residual_std, 3),
            "p_home": round(p_home, 6),
            "p_away": round(1.0 - p_home, 6),
            "uncertainty_std": 0.046 if self.uses_enhanced_features else 0.050,
        }

    def predict_spread(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        spread_line_home: float,
        *,
        precomputed_feats: dict[str, float] | None = None,
        precomputed_ridge: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """
        Predicts probability of HOME covering spread_line_home (e.g. -5.5 means Home must win by > 5.5 pts;
        +4.5 means Home covers if Home - Away > -4.5). Handles integer spread push probabilities.
        """
        ml_res = self.predict_moneyline(
            game,
            historical_games,
            precomputed_feats=precomputed_feats,
            precomputed_ridge=precomputed_ridge,
        )
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
            "uncertainty_std": 0.048 if self.uses_enhanced_features else 0.052,
        }
