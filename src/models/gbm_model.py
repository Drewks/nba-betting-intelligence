"""
Modelo E: Advanced LightGBM Residual-Boosted Model.
Uses regularized shallow trees trained with exponential recency weights to learn non-linear
residual corrections on top of structural margin and total baselines without overfitting.
"""

from __future__ import annotations

from typing import Any
import numpy as np
from scipy.stats import norm
from lightgbm import LGBMClassifier, LGBMRegressor

from src.features.builder import build_pregame_features
from src.models.common import (
    MARGIN_FEATURE_COLUMNS,
    TOTAL_FEATURE_COLUMNS,
    _filter_strictly_prior_final_games,
    build_oof_sigma_metadata,
    iter_expanding_temporal_oof_folds,
    make_fold_record,
)
from src.models.point_margin import PointMarginModel
from src.models.total_points import TotalPointsModel


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
        self.default_total_residual_std: float = 18.2
        self.total_residual_std: float = 18.2
        self.default_win_prob_std: float = 11.5
        self.margin_residual_std: float = 13.6
        self.win_prob_std: float = 11.5
        self.sigma_metadata: dict[str, Any] = {}
        self.is_fitted = False

    @staticmethod
    def _build_estimators() -> tuple[LGBMClassifier, LGBMRegressor, LGBMRegressor]:
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
        return clf, mar_reg, reg

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        if len(prior) < 30:
            self.is_fitted = False
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

        train_sample = prior[-1000:] if len(prior) > 1000 else prior
        X_mar_rows: list[list[float]] = []
        X_tot_rows: list[list[float]] = []
        y_cls: list[int] = []
        y_mar_res: list[float] = []
        y_tot_res: list[float] = []
        s_mar: list[float] = []
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
            s_mar.append(float(feats["structural_margin"]))
            s_tot.append(float(feats["structural_total"]))

        Xm = np.asarray(X_mar_rows, dtype=float)
        Xt = np.asarray(X_tot_rows, dtype=float)
        yc = np.asarray(y_cls, dtype=int)
        ym_res = np.asarray(y_mar_res, dtype=float)
        yt_res = np.asarray(y_tot_res, dtype=float)
        sm_vec = np.asarray(s_mar, dtype=float)
        st_vec = np.asarray(s_tot, dtype=float)
        actual_mars = sm_vec + ym_res
        actual_tots = st_vec + yt_res

        # Strictly temporal expanding walk-forward OOF residuals for sigma (F-001).
        min_warmup = min(60, max(15, len(train_sample) // 3))
        folds = iter_expanding_temporal_oof_folds(train_sample, min_warmup=min_warmup, n_folds=5)
        oof_tot_res: list[float] = []
        oof_mar_res: list[float] = []
        fold_records: list[dict[str, Any]] = []

        for train_idx, val_idx, fold_cutoff in folds:
            w_f = np.exp(np.linspace(-0.75, 0.0, len(train_idx)))
            _clf_f, mar_f, reg_f = self._build_estimators()
            mar_f.fit(Xm[train_idx], ym_res[train_idx], sample_weight=w_f)
            reg_f.fit(Xt[train_idx], yt_res[train_idx], sample_weight=w_f)
            mar_pred_f = sm_vec[val_idx] + 0.25 * np.clip(np.asarray(mar_f.predict(Xm[val_idx]), dtype=float), -4.0, 4.0)
            tot_pred_f = st_vec[val_idx] + 0.22 * np.clip(np.asarray(reg_f.predict(Xt[val_idx]), dtype=float), -5.0, 5.0)
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

        w_tr = np.exp(np.linspace(-0.75, 0.0, len(Xm)))
        clf, mar_reg, reg = self._build_estimators()
        clf.fit(Xm, yc, sample_weight=w_tr)
        mar_reg.fit(Xm, ym_res, sample_weight=w_tr)
        reg.fit(Xt, yt_res, sample_weight=w_tr)

        # In-sample residuals stored strictly as diagnostic comparison vs OOS (never used for sigma).
        ins_tot_preds = st_vec + 0.22 * np.clip(np.asarray(reg.predict(Xt), dtype=float), -5.0, 5.0)
        ins_mar_preds = sm_vec + 0.25 * np.clip(np.asarray(mar_reg.predict(Xm), dtype=float), -4.0, 4.0)
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
        self.is_fitted = True

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
    ) -> dict[str, Any]:
        feats = build_pregame_features(game, historical_games, market="moneyline")
        if not self.is_fitted or self.clf is None or self.mar_reg is None:
            fallback = PointMarginModel()
            return fallback.predict_moneyline(game, historical_games)

        xm_vec = np.asarray([[feats[c] for c in MARGIN_FEATURE_COLUMNS]], dtype=float)
        res_mar = float(np.clip(self.mar_reg.predict(xm_vec)[0], -4.0, 4.0))
        gbm_margin = feats["structural_margin"] + 0.25 * res_mar
        p_from_mar = float(1.0 - norm.cdf(0.0, loc=gbm_margin, scale=self.win_prob_std))
        p_from_clf = float(self.clf.predict_proba(xm_vec)[0][1])
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
            "uncertainty_std": 0.058,
        }
