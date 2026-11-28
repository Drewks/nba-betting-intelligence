"""
Modelo E: Advanced LightGBM Residual-Boosted Model (V9 Ridge/RAPM + Boxscore Enhanced).
Uses regularized shallow trees trained with exponential recency weights on strictly out-of-fold
Ridge/RAPM anchors, real Four Factors, 3PT luck, participation-delta availability, and situational
context to capture non-linear residual interactions without overfitting.
"""

from __future__ import annotations

import math
from typing import Any

from lightgbm import LGBMClassifier, LGBMRegressor
import numpy as np
from scipy.stats import norm

from src.features.builder import build_pregame_features
from src.models.common import (
    MARGIN_FEATURE_COLUMNS,
    TOTAL_FEATURE_COLUMNS,
    _filter_strictly_prior_final_games,
    build_enhanced_margin_vector,
    build_enhanced_total_vector,
    build_oof_sigma_metadata,
    fit_oof_logistic_scale,
    iter_expanding_temporal_oof_folds,
    make_fold_record,
)
from src.models.point_margin import PointMarginModel
from src.models.ridge_rapm import RidgeEfficiencyRAPMModel
from src.models.total_points import TotalPointsModel


class AdvancedGBMModel:
    """
    Modelo E (Modelo Avanzado LightGBM Residual-Boosted):
    Uses regularized shallow trees (max_depth=2, num_leaves=4, high L1/L2 regularization)
    trained with exponential recency weights to learn non-linear residual corrections on top
    of strictly out-of-fold Ridge/RAPM margin and total anchors without step-function overfitting.
    """

    model_family = "model_e_lightgbm"

    def __init__(
        self,
        version_id: str = "model_e_lightgbm_v9",
        shared_ridge_rapm: RidgeEfficiencyRAPMModel | None = None,
    ) -> None:
        self.version_id = version_id
        self._owns_ridge_rapm = shared_ridge_rapm is None
        self.ridge_rapm = shared_ridge_rapm or RidgeEfficiencyRAPMModel("model_h_for_gbm_v9")
        self.clf: LGBMClassifier | None = None
        self.mar_reg: LGBMRegressor | None = None
        self.reg: LGBMRegressor | None = None
        self.default_total_residual_std: float = 18.4
        self.total_residual_std: float = 18.4
        self.default_win_prob_std: float = 12.2
        self.margin_residual_std: float = 13.6
        self.win_prob_std: float = 12.2
        self.win_logistic_scale: float = 7.4
        self.uses_enhanced_features: bool = False
        self.sigma_metadata: dict[str, Any] = {}
        self.oof_margin_preds: dict[str, float] = {}
        self.oof_win_probs: dict[str, float] = {}
        self.oof_total_preds: dict[str, float] = {}
        self.is_fitted = False

    @staticmethod
    def _build_estimators() -> tuple[LGBMClassifier, LGBMRegressor, LGBMRegressor]:
        clf = LGBMClassifier(
            n_estimators=40,
            learning_rate=0.03,
            max_depth=2,
            num_leaves=4,
            min_child_samples=35,
            subsample=0.8,
            colsample_bytree=0.75,
            reg_alpha=5.0,
            reg_lambda=15.0,
            random_state=42,
            n_jobs=1,
            verbose=-1,
        )
        mar_reg = LGBMRegressor(
            n_estimators=45,
            learning_rate=0.03,
            max_depth=2,
            num_leaves=4,
            min_child_samples=35,
            subsample=0.8,
            colsample_bytree=0.75,
            reg_alpha=5.0,
            reg_lambda=15.0,
            random_state=42,
            n_jobs=1,
            verbose=-1,
        )
        reg = LGBMRegressor(
            n_estimators=40,
            learning_rate=0.03,
            max_depth=2,
            num_leaves=4,
            min_child_samples=35,
            subsample=0.8,
            colsample_bytree=0.75,
            reg_alpha=6.0,
            reg_lambda=20.0,
            random_state=42,
            n_jobs=1,
            verbose=-1,
        )
        return clf, mar_reg, reg

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
        self.oof_total_preds = {}
        if len(prior) < 30:
            self.is_fitted = False
            self.uses_enhanced_features = False
            self.sigma_metadata = {
                "total": build_oof_sigma_metadata(
                    method="unfitted_insufficient_games",
                    oof_residuals=[],
                    insample_residuals=None,
                    effective_sigma=self.total_residual_std,
                    fold_records=[],
                    train_sample=prior,
                ),
                "margin": build_oof_sigma_metadata(
                    method="unfitted_insufficient_games",
                    oof_residuals=[],
                    insample_residuals=None,
                    effective_sigma=self.win_prob_std,
                    fold_records=[],
                    train_sample=prior,
                ),
            }
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
    def _anchor_margin(ridge_pred: dict[str, float]) -> float:
        m_slow = float(ridge_pred["ridge_margin_slow"])
        if float(ridge_pred.get("rapm_available", 0.0)) > 0.5 and "rapm_margin" in ridge_pred:
            return 0.55 * m_slow + 0.45 * float(ridge_pred["rapm_margin"])
        return m_slow

    @staticmethod
    def _anchor_total(ridge_pred: dict[str, float]) -> float:
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
        x_mar_rows: list[list[float]] = []
        x_tot_rows: list[list[float]] = []
        y_cls: list[int] = []
        y_mar_res: list[float] = []
        y_tot_res: list[float] = []
        s_mar: list[float] = []
        s_tot: list[float] = []

        for orig_i in valid_indices:
            g = train_sample[orig_i]
            gid = str(g["game_id"])
            feats = feats_by_gid[gid]
            r_pred = ridge_oof[orig_i]
            x_mar_rows.append(build_enhanced_margin_vector(feats, r_pred))
            x_tot_rows.append(build_enhanced_total_vector(feats, r_pred))
            h_pts = float(g["home_score"])
            a_pts = float(g["away_score"])
            m_anch = self._anchor_margin(r_pred)
            t_anch = self._anchor_total(r_pred)
            y_cls.append(1 if h_pts > a_pts else 0)
            y_mar_res.append((h_pts - a_pts) - m_anch)
            y_tot_res.append((h_pts + a_pts) - t_anch)
            s_mar.append(m_anch)
            s_tot.append(t_anch)

        xm = np.asarray(x_mar_rows, dtype=float)
        xt = np.asarray(x_tot_rows, dtype=float)
        yc = np.asarray(y_cls, dtype=int)
        ym_res = np.asarray(y_mar_res, dtype=float)
        yt_res = np.asarray(y_tot_res, dtype=float)
        sm_vec = np.asarray(s_mar, dtype=float)
        st_vec = np.asarray(s_tot, dtype=float)
        actual_mars = sm_vec + ym_res
        actual_tots = st_vec + yt_res

        min_warmup = min(80, max(20, len(sub_games) // 3))
        folds = iter_expanding_temporal_oof_folds(sub_games, min_warmup=min_warmup, n_folds=5)
        oof_tot_res: list[float] = []
        oof_mar_res: list[float] = []
        fold_records: list[dict[str, Any]] = []
        oof_mar_preds_raw: dict[str, tuple[float, float]] = {}

        for train_idx, val_idx, fold_cutoff in folds:
            w_f = np.exp(np.linspace(-0.65, 0.0, len(train_idx)))
            clf_f, mar_f, reg_f = self._build_estimators()
            if len(set(yc[train_idx].tolist())) >= 2:
                clf_f.fit(xm[train_idx], yc[train_idx], sample_weight=w_f)
                clf_probs_f = np.asarray(clf_f.predict_proba(xm[val_idx]), dtype=float)[:, 1]
            else:
                clf_probs_f = np.full(len(val_idx), 0.5, dtype=float)
            mar_f.fit(xm[train_idx], ym_res[train_idx], sample_weight=w_f)
            reg_f.fit(xt[train_idx], yt_res[train_idx], sample_weight=w_f)
            mar_pred_f = sm_vec[val_idx] + np.clip(np.asarray(mar_f.predict(xm[val_idx]), dtype=float), -7.0, 7.0)
            tot_pred_f = st_vec[val_idx] + 0.55 * np.clip(np.asarray(reg_f.predict(xt[val_idx]), dtype=float), -7.5, 7.5)
            oof_mar_res.extend((actual_mars[val_idx] - mar_pred_f).tolist())
            oof_tot_res.extend((actual_tots[val_idx] - tot_pred_f).tolist())
            fold_records.append(make_fold_record(sub_games, train_idx, val_idx, fold_cutoff))
            for local_pos, vi in enumerate(val_idx):
                gid = str(sub_games[vi]["game_id"])
                m_val = float(mar_pred_f[local_pos])
                oof_mar_preds_raw[gid] = (m_val, float(clf_probs_f[local_pos]))
                self.oof_margin_preds[gid] = m_val
                self.oof_total_preds[gid] = float(tot_pred_f[local_pos])

        if len(oof_tot_res) >= 10:
            oof_tot_std = float(np.std(np.asarray(oof_tot_res, dtype=float), ddof=1))
            oof_mar_std = float(np.std(np.asarray(oof_mar_res, dtype=float), ddof=1))
            self.total_residual_std = float(np.clip(oof_tot_std, 16.5, 20.5))
            self.margin_residual_std = float(np.clip(oof_mar_std, 11.5, 15.2))
            self.win_prob_std = float(np.clip(0.86 * self.margin_residual_std, 11.5, 13.0))
            oof_m_list: list[float] = []
            oof_y_list: list[float] = []
            for g in sub_games:
                gid = str(g["game_id"])
                if gid in self.oof_margin_preds:
                    oof_m_list.append(self.oof_margin_preds[gid])
                    oof_y_list.append(1.0 if float(g["home_score"]) > float(g["away_score"]) else 0.0)
            prior_scale = float(np.clip(0.535 * self.margin_residual_std, 7.2, 8.0))
            self.win_logistic_scale = fit_oof_logistic_scale(oof_m_list, oof_y_list, prior_scale=prior_scale)
            sigma_method = "temporal_expanding_oof"
        else:
            self.total_residual_std = float(self.default_total_residual_std)
            self.margin_residual_std = 13.6
            self.win_prob_std = float(self.default_win_prob_std)
            self.win_logistic_scale = 7.8
            sigma_method = "insufficient_oof_default_prior"

        for gid, (m_pred, p_clf) in oof_mar_preds_raw.items():
            p_m = float(1.0 / (1.0 + math.exp(-m_pred / self.win_logistic_scale)))
            self.oof_win_probs[gid] = float(np.clip(0.82 * p_m + 0.18 * p_clf, 0.03, 0.97))

        w_tr = np.exp(np.linspace(-0.65, 0.0, len(xm)))
        clf, mar_reg, reg = self._build_estimators()
        clf.fit(xm, yc, sample_weight=w_tr)
        mar_reg.fit(xm, ym_res, sample_weight=w_tr)
        reg.fit(xt, yt_res, sample_weight=w_tr)

        ins_tot_preds = st_vec + 0.55 * np.clip(np.asarray(reg.predict(xt), dtype=float), -7.5, 7.5)
        ins_mar_preds = sm_vec + np.clip(np.asarray(mar_reg.predict(xm), dtype=float), -7.0, 7.0)
        self.sigma_metadata = {
            "total": build_oof_sigma_metadata(
                method=sigma_method,
                oof_residuals=oof_tot_res,
                insample_residuals=(actual_tots - ins_tot_preds),
                effective_sigma=self.total_residual_std,
                fold_records=fold_records,
                train_sample=sub_games,
            ),
            "margin": build_oof_sigma_metadata(
                method=sigma_method,
                oof_residuals=oof_mar_res,
                insample_residuals=(actual_mars - ins_mar_preds),
                effective_sigma=self.win_prob_std,
                fold_records=fold_records,
                train_sample=sub_games,
            ),
        }

        self.clf = clf
        self.mar_reg = mar_reg
        self.reg = reg
        self.uses_enhanced_features = True
        self.is_fitted = True

    def _fit_fallback_small_sample(
        self,
        train_sample: list[dict[str, Any]],
        feats_by_gid: dict[str, dict[str, float]],
    ) -> None:
        x_mar_rows: list[list[float]] = []
        x_tot_rows: list[list[float]] = []
        y_cls: list[int] = []
        y_mar_res: list[float] = []
        y_tot_res: list[float] = []
        s_mar: list[float] = []
        s_tot: list[float] = []

        for g in train_sample:
            feats = feats_by_gid[str(g["game_id"])]
            x_mar_rows.append([feats[c] for c in MARGIN_FEATURE_COLUMNS])
            x_tot_rows.append([feats[c] for c in TOTAL_FEATURE_COLUMNS])
            h_pts = float(g["home_score"])
            a_pts = float(g["away_score"])
            y_cls.append(1 if h_pts > a_pts else 0)
            y_mar_res.append((h_pts - a_pts) - float(feats["structural_margin"]))
            y_tot_res.append((h_pts + a_pts) - float(feats["structural_total"]))
            s_mar.append(float(feats["structural_margin"]))
            s_tot.append(float(feats["structural_total"]))

        xm = np.asarray(x_mar_rows, dtype=float)
        xt = np.asarray(x_tot_rows, dtype=float)
        yc = np.asarray(y_cls, dtype=int)
        ym_res = np.asarray(y_mar_res, dtype=float)
        yt_res = np.asarray(y_tot_res, dtype=float)
        sm_vec = np.asarray(s_mar, dtype=float)
        st_vec = np.asarray(s_tot, dtype=float)
        actual_mars = sm_vec + ym_res
        actual_tots = st_vec + yt_res

        min_warmup = min(60, max(15, len(train_sample) // 3))
        folds = iter_expanding_temporal_oof_folds(train_sample, min_warmup=min_warmup, n_folds=5)
        oof_tot_res: list[float] = []
        oof_mar_res: list[float] = []
        fold_records: list[dict[str, Any]] = []

        for train_idx, val_idx, fold_cutoff in folds:
            w_f = np.exp(np.linspace(-0.75, 0.0, len(train_idx)))
            _clf_f, mar_f, reg_f = self._build_estimators()
            mar_f.fit(xm[train_idx], ym_res[train_idx], sample_weight=w_f)
            reg_f.fit(xt[train_idx], yt_res[train_idx], sample_weight=w_f)
            mar_pred_f = sm_vec[val_idx] + 0.25 * np.clip(np.asarray(mar_f.predict(xm[val_idx]), dtype=float), -4.0, 4.0)
            tot_pred_f = st_vec[val_idx] + 0.22 * np.clip(np.asarray(reg_f.predict(xt[val_idx]), dtype=float), -5.0, 5.0)
            oof_mar_res.extend((actual_mars[val_idx] - mar_pred_f).tolist())
            oof_tot_res.extend((actual_tots[val_idx] - tot_pred_f).tolist())
            fold_records.append(make_fold_record(train_sample, train_idx, val_idx, fold_cutoff))

        if len(oof_tot_res) >= 10:
            oof_tot_std = float(np.std(np.asarray(oof_tot_res, dtype=float), ddof=1))
            oof_mar_std = float(np.std(np.asarray(oof_mar_res, dtype=float), ddof=1))
            self.total_residual_std = float(np.clip(oof_tot_std, 16.5, 20.2))
            self.margin_residual_std = float(np.clip(oof_mar_std, 11.5, 15.0))
            self.win_prob_std = float(np.clip(0.84 * self.margin_residual_std, 11.2, 12.2))
            sigma_method = "temporal_expanding_oof"
        else:
            self.total_residual_std = float(self.default_total_residual_std)
            self.margin_residual_std = 13.6
            self.win_prob_std = float(self.default_win_prob_std)
            sigma_method = "insufficient_oof_default_prior"

        w_tr = np.exp(np.linspace(-0.75, 0.0, len(xm)))
        clf, mar_reg, reg = self._build_estimators()
        clf.fit(xm, yc, sample_weight=w_tr)
        mar_reg.fit(xm, ym_res, sample_weight=w_tr)
        reg.fit(xt, yt_res, sample_weight=w_tr)

        ins_tot_preds = st_vec + 0.22 * np.clip(np.asarray(reg.predict(xt), dtype=float), -5.0, 5.0)
        ins_mar_preds = sm_vec + 0.25 * np.clip(np.asarray(mar_reg.predict(xm), dtype=float), -4.0, 4.0)
        self.sigma_metadata = {
            "total": build_oof_sigma_metadata(
                method=sigma_method,
                oof_residuals=oof_tot_res,
                insample_residuals=(actual_tots - ins_tot_preds),
                effective_sigma=self.total_residual_std,
                fold_records=fold_records,
                train_sample=train_sample,
            ),
            "margin": build_oof_sigma_metadata(
                method=sigma_method,
                oof_residuals=oof_mar_res,
                insample_residuals=(actual_mars - ins_mar_preds),
                effective_sigma=self.win_prob_std,
                fold_records=fold_records,
                train_sample=train_sample,
            ),
        }

        self.clf = clf
        self.mar_reg = mar_reg
        self.reg = reg
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
        if not self.is_fitted or self.clf is None or self.mar_reg is None:
            fallback = PointMarginModel()
            return fallback.predict_moneyline(game, historical_games)

        if self.uses_enhanced_features:
            ridge_pred = precomputed_ridge if precomputed_ridge is not None else self.ridge_rapm.predict_matchup(
                game, historical_games, precomputed_feats=feats
            )
            xm_vec = np.asarray([build_enhanced_margin_vector(feats, ridge_pred)], dtype=float)
            res_mar = float(np.clip(self.mar_reg.predict(xm_vec)[0], -7.0, 7.0))
            gbm_margin = self._anchor_margin(ridge_pred) + res_mar
            p_from_mar = float(1.0 / (1.0 + math.exp(-gbm_margin / self.win_logistic_scale)))
            p_from_clf = float(self.clf.predict_proba(xm_vec)[0][1])
            prob_home = float(np.clip(0.82 * p_from_mar + 0.18 * p_from_clf, 0.03, 0.97))
        else:
            xm_vec = np.asarray([[feats[c] for c in MARGIN_FEATURE_COLUMNS]], dtype=float)
            res_mar = float(np.clip(self.mar_reg.predict(xm_vec)[0], -4.0, 4.0))
            gbm_margin = float(feats["structural_margin"]) + 0.25 * res_mar
            p_from_mar = float(1.0 - norm.cdf(0.0, loc=gbm_margin, scale=self.win_prob_std))
            p_from_clf = float(self.clf.predict_proba(xm_vec)[0][1])
            p_elo = float(feats["p_elo"])
            prob_home = float(np.clip(0.52 * p_elo + 0.40 * p_from_mar + 0.08 * p_from_clf, 0.05, 0.95))

        return {
            "p_home": round(prob_home, 6),
            "p_away": round(1.0 - prob_home, 6),
            "expected_margin": round(gbm_margin, 3),
            "uncertainty_std": 0.048 if self.uses_enhanced_features else 0.054,
        }

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
        if not self.is_fitted or self.reg is None:
            fallback = TotalPointsModel()
            return fallback.predict_total_points(game, historical_games, line_value)

        if self.uses_enhanced_features:
            ridge_pred = precomputed_ridge if precomputed_ridge is not None else self.ridge_rapm.predict_matchup(
                game, historical_games, precomputed_feats=feats
            )
            xt_vec = np.asarray([build_enhanced_total_vector(feats, ridge_pred)], dtype=float)
            res_tot = float(np.clip(self.reg.predict(xt_vec)[0], -7.5, 7.5))
            exp_total = self._anchor_total(ridge_pred) + 0.55 * res_tot
        else:
            xt_vec = np.asarray([[feats[c] for c in TOTAL_FEATURE_COLUMNS]], dtype=float)
            res_tot = float(np.clip(self.reg.predict(xt_vec)[0], -5.0, 5.0))
            exp_total = float(feats["structural_total"]) + 0.22 * res_tot

        eff_std = float(np.clip(0.75 * self.total_residual_std + 0.25 * float(feats["dynamic_total_std"]), 17.0, 20.5))
        is_int_line = abs(line_value - round(line_value)) < 1e-6
        if is_int_line:
            p_over_raw = float(1.0 - norm.cdf(line_value + 0.5, loc=exp_total, scale=eff_std))
            p_under_raw = float(norm.cdf(line_value - 0.5, loc=exp_total, scale=eff_std))
            p_push = max(0.0, 1.0 - p_over_raw - p_under_raw)
            non_push = max(1e-9, p_over_raw + p_under_raw)
            p_over_cond = float(np.clip(p_over_raw / non_push, 1e-4, 1.0 - 1e-4))
            p_over = (1.0 - p_push) * p_over_cond
        else:
            p_push = 0.0
            p_over = float(np.clip(1.0 - norm.cdf(line_value, loc=exp_total, scale=eff_std), 1e-4, 1.0 - 1e-4))
        p_over_r = round(float(p_over), 6)
        p_push_r = round(float(p_push), 6)
        p_under_r = round(max(0.0, 1.0 - p_over_r - p_push_r), 6)
        return {
            "expected_total": round(exp_total, 2),
            "total_std": round(eff_std, 3),
            "p_over": p_over_r,
            "p_under": p_under_r,
            "p_push": p_push_r,
            "p_push_estimate": p_push_r,
            "uncertainty_std": 0.052 if self.uses_enhanced_features else 0.058,
        }
