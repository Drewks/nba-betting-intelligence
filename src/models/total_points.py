"""
Modelo D: Total Points NBA Model (V9 Exact 48-Min Pace & Simultaneous Ridge Efficiency Enhanced).
Models the distribution of T = Score_home + Score_away using multi-horizon simultaneous Ridge
offensive/defensive efficiency, exact 48-minute regulation pace, non-linear blowout & OT adjustments,
real Four Factors (FTr, 3PAr, 3PT luck), B2B fatigue drag, and explicit OOF Cov(Score_home, Score_away).
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
    TOTAL_FEATURE_COLUMNS,
    _filter_strictly_prior_final_games,
    build_enhanced_total_vector,
    build_oof_sigma_metadata,
    iter_expanding_temporal_oof_folds,
    make_fold_record,
)
from src.models.ridge_rapm import RidgeEfficiencyRAPMModel


class TotalPointsModel:
    """
    Modelo D (Total de Puntos):
    Models T = Score_home + Score_away anchored on multi-horizon simultaneous Ridge Off/Def efficiency
    and exact 48-minute regulation pace, with residual RidgeCV correction for shot profile, 3PT luck,
    blowout/OT regimes, and B2B drag.
    Explicitly estimates and includes the covariance Cov(Score_home, Score_away):
        Var(H + A) = Var(H) + Var(A) + 2 * Cov(H, A).
    """

    model_family = "model_d_total_points"

    def __init__(
        self,
        version_id: str = "model_d_total_points_v1",
        default_total_std: float = 18.4,
        shared_ridge_rapm: RidgeEfficiencyRAPMModel | None = None,
    ) -> None:
        self.version_id = version_id
        self.default_total_std = default_total_std
        self.total_std = default_total_std
        self.independent_std = 15.6
        self.score_covariance = 38.0
        self.score_correlation = 0.31
        self._owns_ridge_rapm = shared_ridge_rapm is None
        self.ridge_rapm = shared_ridge_rapm or RidgeEfficiencyRAPMModel("model_h_for_totals_v9")
        self.regressor: Any = None
        self.uses_enhanced_features: bool = False
        self.ml_weight: float = 0.25
        self.sigma_metadata: dict[str, Any] = {}
        self.oof_total_preds: dict[str, float] = {}
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
        self.oof_total_preds = {}
        if len(prior) < 20:
            self.is_fitted = False
            self.uses_enhanced_features = False
            self.sigma_metadata = build_oof_sigma_metadata(
                method="unfitted_insufficient_games",
                oof_residuals=[],
                insample_residuals=None,
                effective_sigma=self.total_std,
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

    @staticmethod
    def _enhanced_base_total(ridge_pred: dict[str, float]) -> float:
        t_slow = float(ridge_pred["ridge_total_slow"])
        t_fast = float(ridge_pred["ridge_total_fast"])
        if float(ridge_pred.get("rapm_available", 0.0)) > 0.5 and "rapm_total" in ridge_pred:
            return 0.45 * t_slow + 0.15 * t_fast + 0.40 * float(ridge_pred["rapm_total"])
        return 0.65 * t_slow + 0.35 * t_fast

    def _fit_enhanced(
        self,
        train_sample: list[dict[str, Any]],
        feats_by_gid: dict[str, dict[str, float]],
        ridge_oof: dict[int, dict[str, float]],
    ) -> None:
        valid_indices = sorted(ridge_oof.keys())
        sub_games = [train_sample[i] for i in valid_indices]
        x_rows: list[list[float]] = []
        y_totals: list[float] = []
        base_totals: list[float] = []
        h_scores: list[float] = []
        a_scores: list[float] = []
        eh_list: list[float] = []
        ea_list: list[float] = []

        for orig_i in valid_indices:
            g = train_sample[orig_i]
            gid = str(g["game_id"])
            feats = feats_by_gid[gid]
            r_pred = ridge_oof[orig_i]
            x_rows.append(build_enhanced_total_vector(feats, r_pred))
            h_pts = float(g["home_score"])
            a_pts = float(g["away_score"])
            y_totals.append(h_pts + a_pts)
            b_tot = self._enhanced_base_total(r_pred)
            b_mar = float(r_pred["ridge_margin_slow"])
            base_totals.append(b_tot)
            h_scores.append(h_pts)
            a_scores.append(a_pts)
            eh_list.append(0.5 * (b_tot + b_mar))
            ea_list.append(0.5 * (b_tot - b_mar))

        x_mat = np.asarray(x_rows, dtype=float)
        y_arr = np.asarray(y_totals, dtype=float)
        h_arr = np.asarray(h_scores, dtype=float)
        a_arr = np.asarray(a_scores, dtype=float)
        eh_arr = np.asarray(eh_list, dtype=float)
        ea_arr = np.asarray(ea_list, dtype=float)
        s_arr = np.asarray(base_totals, dtype=float)

        alphas = [40.0, 150.0, 500.0, 1500.0, 4000.0]
        min_warmup = min(80, max(20, len(sub_games) // 3))
        folds = iter_expanding_temporal_oof_folds(sub_games, min_warmup=min_warmup, n_folds=5)
        oof_tot_res: list[float] = []
        oof_h_res: list[float] = []
        oof_a_res: list[float] = []
        fold_records: list[dict[str, Any]] = []

        for train_idx, val_idx, fold_cutoff in folds:
            w_fold = np.exp(np.linspace(-0.65, 0.0, len(train_idx)))
            fold_model = make_pipeline(StandardScaler(), RidgeCV(alphas=alphas))
            fold_model.fit(x_mat[train_idx], y_arr[train_idx], ridgecv__sample_weight=w_fold)
            pred_tot_val = np.clip(np.asarray(fold_model.predict(x_mat[val_idx]), dtype=float), 175.0, 285.0)
            adj_val = pred_tot_val - s_arr[val_idx]
            oof_tot_res.extend((y_arr[val_idx] - pred_tot_val).tolist())
            oof_h_res.extend((h_arr[val_idx] - (eh_arr[val_idx] + 0.5 * adj_val)).tolist())
            oof_a_res.extend((a_arr[val_idx] - (ea_arr[val_idx] + 0.5 * adj_val)).tolist())
            fold_records.append(make_fold_record(sub_games, train_idx, val_idx, fold_cutoff))
            for local_pos, vi in enumerate(val_idx):
                self.oof_total_preds[str(sub_games[vi]["game_id"])] = float(pred_tot_val[local_pos])

        sample_weights = np.exp(np.linspace(-0.65, 0.0, len(x_mat)))
        model = make_pipeline(StandardScaler(), RidgeCV(alphas=alphas))
        model.fit(x_mat, y_arr, ridgecv__sample_weight=sample_weights)

        if len(oof_h_res) >= 10:
            h_res = np.asarray(oof_h_res, dtype=float)
            a_res = np.asarray(oof_a_res, dtype=float)
            sigma_method = "temporal_expanding_oof"
        else:
            h_res = h_arr - eh_arr
            a_res = a_arr - ea_arr
            sigma_method = "insufficient_oof_structural_prior"

        var_h = float(np.var(h_res, ddof=1))
        var_a = float(np.var(a_res, ddof=1))
        cov_matrix = np.cov(h_res, a_res, ddof=1)
        cov_ha = float(cov_matrix[0, 1])

        var_indep = max(100.0, var_h + var_a)
        var_total_with_cov = max(196.0, var_h + var_a + 2.0 * cov_ha)

        self.independent_std = float(np.sqrt(var_indep))
        self.total_std = float(np.clip(np.sqrt(var_total_with_cov), 16.5, 20.5))
        self.score_covariance = round(cov_ha, 4)
        denom = math.sqrt(max(1e-6, var_h * var_a))
        self.score_correlation = round(cov_ha / denom, 4)

        insample_preds = np.clip(np.asarray(model.predict(x_mat), dtype=float), 175.0, 285.0)
        self.sigma_metadata = build_oof_sigma_metadata(
            method=sigma_method,
            oof_residuals=oof_tot_res,
            insample_residuals=(y_arr - insample_preds),
            effective_sigma=self.total_std,
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
        y_totals: list[float] = []
        s_totals: list[float] = []
        h_scores: list[float] = []
        a_scores: list[float] = []
        exp_h_list: list[float] = []
        exp_a_list: list[float] = []

        for g in train_sample:
            feats = feats_by_gid[str(g["game_id"])]
            x_rows.append([feats[c] for c in TOTAL_FEATURE_COLUMNS])
            h_pts = float(g["home_score"])
            a_pts = float(g["away_score"])
            y_totals.append(h_pts + a_pts)
            s_totals.append(float(feats["structural_total"]))

            exp_h, exp_a = self._structural_team_points(feats)
            h_scores.append(h_pts)
            a_scores.append(a_pts)
            exp_h_list.append(exp_h)
            exp_a_list.append(exp_a)

        x_mat = np.asarray(x_rows, dtype=float)
        y_arr = np.asarray(y_totals, dtype=float)
        s_arr = np.asarray(s_totals, dtype=float)
        y_res = y_arr - s_arr
        h_arr = np.asarray(h_scores, dtype=float)
        a_arr = np.asarray(a_scores, dtype=float)
        eh_arr = np.asarray(exp_h_list, dtype=float)
        ea_arr = np.asarray(exp_a_list, dtype=float)

        alphas = [30.0, 100.0, 300.0, 800.0, 1500.0]
        min_warmup = min(40, max(10, len(train_sample) // 3))
        folds = iter_expanding_temporal_oof_folds(train_sample, min_warmup=min_warmup, n_folds=5)
        oof_tot_res: list[float] = []
        oof_h_res: list[float] = []
        oof_a_res: list[float] = []
        fold_records: list[dict[str, Any]] = []

        for train_idx, val_idx, fold_cutoff in folds:
            w_fold = np.exp(np.linspace(-0.75, 0.0, len(train_idx)))
            fold_model = make_pipeline(StandardScaler(), RidgeCV(alphas=alphas))
            fold_model.fit(x_mat[train_idx], y_res[train_idx], ridgecv__sample_weight=w_fold)
            fold_w = min(0.30, 0.12 + len(train_idx) / 5000.0)
            adj_val = fold_w * np.clip(np.asarray(fold_model.predict(x_mat[val_idx]), dtype=float), -5.5, 5.5)
            pred_tot_val = s_arr[val_idx] + adj_val
            oof_tot_res.extend((y_arr[val_idx] - pred_tot_val).tolist())
            oof_h_res.extend((h_arr[val_idx] - (eh_arr[val_idx] + 0.5 * adj_val)).tolist())
            oof_a_res.extend((a_arr[val_idx] - (ea_arr[val_idx] + 0.5 * adj_val)).tolist())
            fold_records.append(make_fold_record(train_sample, train_idx, val_idx, fold_cutoff))

        sample_weights = np.exp(np.linspace(-0.75, 0.0, len(x_mat)))
        model = make_pipeline(StandardScaler(), RidgeCV(alphas=alphas))
        model.fit(x_mat, y_res, ridgecv__sample_weight=sample_weights)
        self.ml_weight = min(0.30, 0.12 + len(train_sample) / 5000.0)

        if len(oof_h_res) >= 10:
            h_res = np.asarray(oof_h_res, dtype=float)
            a_res = np.asarray(oof_a_res, dtype=float)
            sigma_method = "temporal_expanding_oof"
        else:
            h_res = h_arr - eh_arr
            a_res = a_arr - ea_arr
            sigma_method = "insufficient_oof_structural_prior"

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

        insample_preds = s_arr + self.ml_weight * np.clip(np.asarray(model.predict(x_mat), dtype=float), -5.5, 5.5)
        self.sigma_metadata = build_oof_sigma_metadata(
            method=sigma_method,
            oof_residuals=oof_tot_res,
            insample_residuals=(y_arr - insample_preds),
            effective_sigma=self.total_std,
            fold_records=fold_records,
            train_sample=train_sample,
        )
        self.regressor = model
        self.uses_enhanced_features = False
        self.is_fitted = True

    @staticmethod
    def _structural_team_points(feats: dict[str, float]) -> tuple[float, float]:
        struct_tot = float(feats["structural_total"])
        struct_mar = float(feats["structural_margin"])
        exp_h = 0.5 * (struct_tot + struct_mar)
        exp_a = 0.5 * (struct_tot - struct_mar)
        return exp_h, exp_a

    def predict_total_points(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        line_value: float,
        *,
        precomputed_feats: dict[str, float] | None = None,
        precomputed_ridge: dict[str, float] | None = None,
    ) -> dict[str, float]:
        feats = precomputed_feats if precomputed_feats is not None else build_pregame_features(
            game, historical_games, market="total_points"
        )

        if self.is_fitted and self.regressor is not None:
            if self.uses_enhanced_features:
                ridge_pred = precomputed_ridge if precomputed_ridge is not None else self.ridge_rapm.predict_matchup(
                    game, historical_games, precomputed_feats=feats
                )
                base_mar = float(ridge_pred["ridge_margin_slow"])
                x_vec = np.asarray([build_enhanced_total_vector(feats, ridge_pred)], dtype=float)
                expected_total = float(np.clip(self.regressor.predict(x_vec)[0], 175.0, 285.0))
                exp_h = 0.5 * (expected_total + base_mar)
                exp_a = 0.5 * (expected_total - base_mar)
            else:
                exp_h, exp_a = self._structural_team_points(feats)
                structural_total = exp_h + exp_a
                x_vec = np.asarray([[feats[c] for c in TOTAL_FEATURE_COLUMNS]], dtype=float)
                res_tot = float(np.clip(self.regressor.predict(x_vec)[0], -5.5, 5.5))
                adj = self.ml_weight * res_tot
                expected_total = structural_total + adj
                exp_h += 0.5 * adj
                exp_a += 0.5 * adj
        else:
            exp_h, exp_a = self._structural_team_points(feats)
            expected_total = exp_h + exp_a

        eff_std = float(np.clip(0.75 * self.total_std + 0.25 * float(feats["dynamic_total_std"]), 17.0, 20.5))

        is_integer_line = abs(line_value - round(line_value)) < 1e-6
        if is_integer_line:
            p_over_raw = float(1.0 - norm.cdf(line_value + 0.5, loc=expected_total, scale=eff_std))
            p_under_raw = float(norm.cdf(line_value - 0.5, loc=expected_total, scale=eff_std))
            p_push = max(0.0, 1.0 - p_over_raw - p_under_raw)
            non_push = max(1e-9, p_over_raw + p_under_raw)
            p_over_cond = float(np.clip(p_over_raw / non_push, 1e-4, 1.0 - 1e-4))
            p_over = (1.0 - p_push) * p_over_cond
        else:
            p_push = 0.0
            p_over = float(np.clip(1.0 - norm.cdf(line_value, loc=expected_total, scale=eff_std), 1e-4, 1.0 - 1e-4))

        p_over_r = round(float(p_over), 6)
        p_push_r = round(float(p_push), 6)
        p_under_r = round(max(0.0, 1.0 - p_over_r - p_push_r), 6)

        return {
            "expected_home_points": round(exp_h, 2),
            "expected_away_points": round(exp_a, 2),
            "expected_total": round(expected_total, 2),
            "total_std_with_covariance": round(eff_std, 3),
            "independent_std_naive": round(self.independent_std, 3),
            "score_covariance": round(self.score_covariance, 3),
            "score_correlation": round(self.score_correlation, 3),
            "p_over": p_over_r,
            "p_under": p_under_r,
            "p_push": p_push_r,
            "p_push_estimate": p_push_r,
            "uncertainty_std": 0.050 if self.uses_enhanced_features else 0.055,
        }
