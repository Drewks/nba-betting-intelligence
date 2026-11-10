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
from src.models.common import MARGIN_FEATURE_COLUMNS, TOTAL_FEATURE_COLUMNS, _filter_strictly_prior_final_games
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

        tot_preds = st_vec + 0.35 * np.asarray(reg.predict(Xt), dtype=float)
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
        p_over = float(np.clip(1.0 - norm.cdf(line_value, loc=exp_total, scale=eff_std), 0.05, 0.95))
        return {
            "expected_total": round(exp_total, 2),
            "total_std": round(eff_std, 3),
            "p_over": round(p_over, 6),
            "p_under": round(1.0 - p_over, 6),
            "uncertainty_std": 0.058,
        }
