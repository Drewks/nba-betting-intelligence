"""
V8 Phase 2 / Phase 3: Logit-Space Market Residual Learning with Empirical Training.
Anchors directly to the Shin de-vigged sharp market consensus probability and predicts
the residual micro-edge Delta_z from situational context.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any
import numpy as np

logger = logging.getLogger(__name__)


class MarketResidualModel:
    """
    V8 Phase 2 / Phase 3: Logit-Space Market Residual Learning with Empirical Training.
    Anchors directly to the Shin de-vigged sharp market consensus probability:
        z_0 = logit(p_sharp_shin)
    and predicts the residual micro-edge Delta_z from situational context:
        Delta_z = w_ff * four_factors_diff + w_xe * shot_quality_xeFG_diff + w_fatigue * fatigue_diff + w_alt * altitude_advantage + w_travel * (travel_miles_diff / 1000) + w_rest * rest_diff
    Bounded by Huber clipping to prevent extreme variance:
        z_final = z_0 + clip(Delta_z, -0.45, 0.45)
        p_final = 1 / (1 + exp(-z_final))

    Includes an empirical fit() method implementing L2-regularized logistic regression
    to optimize residual weights on genuine out-of-sample market observations.
    """
    model_family = "model_residual_market_v8"
    FEATURE_KEYS = [
        "four_factors",
        "shot_quality",
        "fatigue",
        "altitude",
        "travel",
        "rest",
    ]

    def __init__(
        self,
        version_id: str = "model_residual_v8",
        config_path: Path | str | None = None,
    ) -> None:
        self.version_id = version_id
        self.config_path = Path(config_path or "config/market_residual_weights.json")
        self.weights = {
            "four_factors": 0.85,
            "shot_quality": 0.75,
            "fatigue": 0.05,
            "altitude": 0.08,
            "travel": 0.04,
            "rest": 0.03,
        }
        self.is_trained = False
        self._load_weights_if_available()

    def _load_weights_if_available(self) -> None:
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                if "weights" in data and isinstance(data["weights"], dict):
                    for k in self.FEATURE_KEYS:
                        if k in data["weights"]:
                            self.weights[k] = float(data["weights"][k])
                    self.is_trained = bool(data.get("is_trained", True))
            except Exception as exc:
                logger.debug(f"Could not load market residual weights: {exc}")

    def save_weights(self) -> None:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version_id": self.version_id,
                "weights": self.weights,
                "is_trained": self.is_trained,
            }
            self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Failed to save market residual weights: {exc}")

    def _extract_feature_vector(self, features: dict[str, Any]) -> np.ndarray:
        ff = float(features.get("four_factors_diff") or 0.0)
        xe = float(features.get("shot_quality_xeFG_diff") or 0.0)
        fat = float(features.get("fatigue_diff") or 0.0)
        alt = float(features.get("altitude_advantage") or 0.0)
        trv = float(features.get("travel_miles_diff") or 0.0) / 1000.0
        rst = float(features.get("rest_diff") or 0.0)
        return np.array([ff, xe, fat, alt, trv, rst], dtype=float)

    MIN_FIT_SAMPLES = 300
    HOLDOUT_FRACTION = 0.30

    def fit(
        self,
        training_records: list[dict[str, Any]],
        l2_reg: float = 2.0,
    ) -> dict[str, Any]:
        """
        Fits the residual weights on the chronologically EARLIER part of the records and accepts them
        only if they STRICTLY improve log-loss over the pure sharp-market probability on the LATER,
        untouched holdout part. Records must be ordered by game time and carry the pre-game sharp
        probability (`sharp_home_prob`), features, and the outcome (`home_won` in {0, 1}).
        """
        n_total = len(training_records)
        if n_total < self.MIN_FIT_SAMPLES:
            return {
                "fitted": False,
                "accepted": False,
                "reason": "INSUFFICIENT_SAMPLE_SIZE",
                "sample_size": n_total,
                "min_required": self.MIN_FIT_SAMPLES,
                "weights": self.weights,
            }

        records = sorted(training_records, key=lambda r: str(r.get("game_start_time", "")))
        X_all = np.asarray([self._extract_feature_vector(r.get("features") or {}) for r in records], dtype=float)
        p_sharp = np.clip(np.asarray([float(r["sharp_home_prob"]) for r in records], dtype=float), 0.02, 0.98)
        z0_all = np.log(p_sharp / (1.0 - p_sharp))
        y_all = np.asarray([1.0 if int(r["home_won"]) == 1 else 0.0 for r in records], dtype=float)

        split = int(round(n_total * (1.0 - self.HOLDOUT_FRACTION)))
        X, z0_arr, y_arr = X_all[:split], z0_all[:split], y_all[:split]
        X_h, z0_h, y_h = X_all[split:], z0_all[split:], y_all[split:]
        n = len(y_arr)

        def _logloss(z: np.ndarray, y: np.ndarray) -> float:
            p = np.clip(1.0 / (1.0 + np.exp(-z)), 1e-6, 1.0 - 1e-6)
            return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))

        def loss_and_grad(w: np.ndarray) -> tuple[float, np.ndarray]:
            raw = np.dot(X, w)
            inside = (np.abs(raw) < 0.45).astype(float)  # gradient is zero where the clip is active
            z = z0_arr + np.clip(raw, -0.45, 0.45)
            p = np.clip(1.0 / (1.0 + np.exp(-z)), 1e-6, 1.0 - 1e-6)
            ce = -np.mean(y_arr * np.log(p) + (1.0 - y_arr) * np.log(1.0 - p))
            loss = ce + 0.5 * l2_reg * float(np.sum(w ** 2))
            grad = (np.dot(X.T, (p - y_arr) * inside) / n) + l2_reg * w
            return float(loss), grad

        from scipy.optimize import minimize
        res = minimize(
            fun=loss_and_grad,
            x0=np.zeros(len(self.FEATURE_KEYS)),
            jac=True,
            method="L-BFGS-B",
            bounds=[(-2.0, 2.0) for _ in self.FEATURE_KEYS],
        )
        fitted_w = res.x if res.success else np.zeros(len(self.FEATURE_KEYS))

        holdout_market_ll = _logloss(z0_h, y_h)
        holdout_fitted_ll = _logloss(z0_h + np.clip(np.dot(X_h, fitted_w), -0.45, 0.45), y_h)
        accepted = holdout_fitted_ll < holdout_market_ll
        if accepted:
            for idx, k in enumerate(self.FEATURE_KEYS):
                self.weights[k] = round(float(fitted_w[idx]), 4)
            self.is_trained = True
            self.save_weights()

        return {
            "fitted": True,
            "accepted": accepted,
            "sample_size": n_total,
            "train_size": n,
            "holdout_size": len(y_h),
            "holdout_market_log_loss": round(holdout_market_ll, 5),
            "holdout_fitted_log_loss": round(holdout_fitted_ll, 5),
            "holdout_log_loss_gain": round(holdout_market_ll - holdout_fitted_ll, 5),
            "weights": self.weights,
        }

    def predict_residual(
        self,
        features: dict[str, Any],
        sharp_home_prob: float,
    ) -> dict[str, float]:
        p_sharp = float(np.clip(sharp_home_prob, 0.03, 0.97))
        z_0 = math.log(p_sharp / (1.0 - p_sharp))

        x_vec = self._extract_feature_vector(features)
        w_vec = np.array([self.weights[k] for k in self.FEATURE_KEYS], dtype=float)

        delta_z = float(np.dot(x_vec, w_vec))
        capped_delta = float(np.clip(delta_z, -0.45, 0.45))
        z_final = z_0 + capped_delta
        p_final = float(np.clip(1.0 / (1.0 + math.exp(-z_final)), 0.03, 0.97))

        return {
            "p_home": round(p_final, 6),
            "p_away": round(1.0 - p_final, 6),
            "p_sharp_base": round(p_sharp, 6),
            "delta_logit": round(capped_delta, 5),
            "residual_edge": round(p_final - p_sharp, 6),
        }
