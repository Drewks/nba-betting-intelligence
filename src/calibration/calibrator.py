"""
Model Calibration & Controlled Retraining (Sections 5 & 9):
- Computes Brier Score, Log Loss, and Reliability Curves (ECE)
- Implements Logistic (Platt) calibration and Isotonic calibration (gated by sample size)
- Strictly prohibits future outcomes (game_start_time >= calibration_cutoff_time raises TemporalLeakageError)
- Selects models/calibrators based on out-of-sample probabilistic metrics, never solely on ROI
"""

from __future__ import annotations

from typing import Any
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from src.validation.validator import DataValidationError, TemporalLeakageError, parse_iso_utc


def compute_brier_score(probs: list[float] | np.ndarray, outcomes: list[int] | np.ndarray) -> float:
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if len(p) == 0 or len(p) != len(y):
        raise DataValidationError("Invalid arrays for Brier Score calculation")
    return round(float(np.mean((p - y) ** 2)), 6)


def compute_log_loss(probs: list[float] | np.ndarray, outcomes: list[int] | np.ndarray, eps: float = 1e-6) -> float:
    p = np.clip(np.asarray(probs, dtype=float), eps, 1.0 - eps)
    y = np.asarray(outcomes, dtype=float)
    if len(p) == 0 or len(p) != len(y):
        raise DataValidationError("Invalid arrays for Log Loss calculation")
    loss = -np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))
    return round(float(loss), 6)


def compute_reliability_curve(
    probs: list[float] | np.ndarray,
    outcomes: list[int] | np.ndarray,
    n_bins: int = 10,
) -> dict[str, Any]:
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if len(p) == 0 or len(p) != len(y):
        raise DataValidationError("Invalid arrays for reliability curve calculation")

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins_out: list[dict[str, Any]] = []
    ece_acc = 0.0
    n_total = len(p)

    for i in range(n_bins):
        low = float(bin_edges[i])
        high = float(bin_edges[i + 1])
        if i == n_bins - 1:
            mask = (p >= low) & (p <= high)
        else:
            mask = (p >= low) & (p < high)
        cnt = int(np.sum(mask))
        if cnt > 0:
            mean_pred = float(np.mean(p[mask]))
            obs_freq = float(np.mean(y[mask]))
            gap = abs(mean_pred - obs_freq)
            ece_acc += (cnt / n_total) * gap
        else:
            mean_pred = None
            obs_freq = None
            gap = None

        bins_out.append(
            {
                "bin_index": i,
                "bin_lower": round(low, 2),
                "bin_upper": round(high, 2),
                "count": cnt,
                "mean_predicted_prob": round(mean_pred, 4) if mean_pred is not None else None,
                "observed_frequency": round(obs_freq, 4) if obs_freq is not None else None,
                "abs_calibration_gap": round(gap, 4) if gap is not None else None,
            }
        )

    return {
        "sample_size": n_total,
        "ece": round(float(ece_acc), 6),
        "brier_score": compute_brier_score(p, y),
        "log_loss": compute_log_loss(p, y),
        "bins": bins_out,
    }


def _logit(p: np.ndarray, eps: float = 1e-5) -> np.ndarray:
    clipped = np.clip(p, eps, 1.0 - eps)
    return np.log(clipped / (1.0 - clipped))


class ProbabilityCalibrator:
    """
    Fits and applies probability calibration strictly without temporal lookahead.
    - 'identity': pass-through when sample size < min_samples_logistic
    - 'logistic': Platt scaling on log-odds when sample size >= min_samples_logistic
    - 'isotonic': Isotonic regression when sample size >= min_samples_isotonic
    """

    def __init__(
        self,
        method: str = "auto",
        min_samples_logistic: int = 30,
        min_samples_isotonic: int = 100,
    ) -> None:
        self.requested_method = method
        self.active_method = "identity"
        self.min_samples_logistic = min_samples_logistic
        self.min_samples_isotonic = min_samples_isotonic
        self.logistic_model: LogisticRegression | None = None
        self.isotonic_model: IsotonicRegression | None = None
        self.cutoff_time_str: str | None = None
        self.train_sample_size: int = 0

    def fit(
        self,
        calibration_records: list[dict[str, Any]],
        calibration_cutoff_time: str,
    ) -> str:
        """
        Fits the calibrator using resolved records strictly prior to calibration_cutoff_time.
        Raises TemporalLeakageError if any record has game_start_time >= calibration_cutoff_time.
        """
        cutoff_dt = parse_iso_utc(calibration_cutoff_time)
        probs: list[float] = []
        outcomes: list[int] = []

        for rec in calibration_records:
            game_dt = parse_iso_utc(rec["game_start_time"])
            if game_dt >= cutoff_dt:
                raise TemporalLeakageError(
                    f"Calibration lookahead leakage detected: record game_start_time ({rec['game_start_time']}) "
                    f">= calibration_cutoff_time ({calibration_cutoff_time})"
                )
            res_ts = rec.get("result_recorded_at")
            if res_ts and parse_iso_utc(res_ts) > cutoff_dt:
                raise TemporalLeakageError(
                    f"Calibration lookahead leakage detected: result_recorded_at ({res_ts}) "
                    f"> calibration_cutoff_time ({calibration_cutoff_time})"
                )
            probs.append(float(rec["raw_probability"]))
            outcomes.append(int(rec["outcome"]))

        self.cutoff_time_str = calibration_cutoff_time
        self.train_sample_size = len(probs)

        if self.train_sample_size < self.min_samples_logistic or len(set(outcomes)) < 2:
            self.active_method = "identity"
            return self.active_method

        p_arr = np.asarray(probs, dtype=float)
        y_arr = np.asarray(outcomes, dtype=int)

        chosen = self.requested_method
        if chosen == "auto":
            chosen = "isotonic" if self.train_sample_size >= self.min_samples_isotonic else "logistic"
        elif chosen == "isotonic" and self.train_sample_size < self.min_samples_isotonic:
            chosen = "logistic"

        if chosen == "isotonic":
            iso = IsotonicRegression(y_min=0.03, y_max=0.97, out_of_bounds="clip")
            iso.fit(p_arr, y_arr)
            self.isotonic_model = iso
            self.active_method = "isotonic"
        else:
            X_logit = _logit(p_arr).reshape(-1, 1)
            lr = LogisticRegression(C=1.0, random_state=42)
            lr.fit(X_logit, y_arr)
            self.logistic_model = lr
            self.active_method = "logistic"

        return self.active_method

    def transform(self, raw_probabilities: list[float] | np.ndarray) -> np.ndarray:
        p_arr = np.asarray(raw_probabilities, dtype=float)
        shrink = min(0.50, max(0.10, self.train_sample_size / 400.0))
        if self.active_method == "isotonic" and self.isotonic_model is not None:
            cal = self.isotonic_model.predict(p_arr)
            blended = (1.0 - shrink) * p_arr + shrink * cal
            return np.round(np.clip(blended, 0.03, 0.97), 6)
        if self.active_method == "logistic" and self.logistic_model is not None:
            X_logit = _logit(p_arr).reshape(-1, 1)
            cal = self.logistic_model.predict_proba(X_logit)[:, 1]
            blended = (1.0 - shrink) * p_arr + shrink * cal
            return np.round(np.clip(blended, 0.03, 0.97), 6)
        return np.round(np.clip(p_arr, 0.03, 0.97), 6)

    def transform_single(self, raw_probability: float) -> float:
        return float(self.transform([raw_probability])[0])


def evaluate_version_promotion(
    incumbent_probs: list[float],
    candidate_probs: list[float],
    baseline_probs: list[float],
    oos_outcomes: list[int],
) -> dict[str, Any]:
    """
    Process C (Section 9): Evaluates whether a candidate model/calibration version should be promoted
    over the incumbent model on out-of-sample data.
    Never selects a model based solely on ROI; requires Brier Score and Log Loss non-inferiority/improvement.
    """
    inc_curve = compute_reliability_curve(incumbent_probs, oos_outcomes)
    cand_curve = compute_reliability_curve(candidate_probs, oos_outcomes)
    base_curve = compute_reliability_curve(baseline_probs, oos_outcomes)

    beats_incumbent = (
        cand_curve["brier_score"] <= inc_curve["brier_score"]
        and cand_curve["log_loss"] <= inc_curve["log_loss"]
    )
    beats_baseline = (
        cand_curve["brier_score"] <= base_curve["brier_score"]
        and cand_curve["log_loss"] <= base_curve["log_loss"]
    )
    promote = bool(beats_incumbent and beats_baseline and len(oos_outcomes) >= 20)

    return {
        "oos_sample_size": len(oos_outcomes),
        "incumbent_brier": inc_curve["brier_score"],
        "incumbent_log_loss": inc_curve["log_loss"],
        "incumbent_ece": inc_curve["ece"],
        "candidate_brier": cand_curve["brier_score"],
        "candidate_log_loss": cand_curve["log_loss"],
        "candidate_ece": cand_curve["ece"],
        "baseline_brier": base_curve["brier_score"],
        "baseline_log_loss": base_curve["log_loss"],
        "beats_incumbent": beats_incumbent,
        "beats_baseline": beats_baseline,
        "recommend_promotion": promote,
        "selection_basis": "OOS_BRIER_AND_LOG_LOSS_AND_CALIBRATION (never ROI alone)",
    }
