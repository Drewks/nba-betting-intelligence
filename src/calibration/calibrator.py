"""
Model Calibration & Controlled Retraining (Sections 5 & 9):
- Computes Brier Score, Log Loss, and Reliability Curves (ECE)
- Implements temperature-regularized Logistic (Platt) calibration and Isotonic calibration (gated by sample size)
- Enforces monotonic positive slope and small-sample intercept shrinkage to prevent directional Home/Away or Over/Under bias
- Strictly prohibits future outcomes (game_start_time >= calibration_cutoff_time raises TemporalLeakageError)
- Selects models/calibrators based on out-of-sample probabilistic metrics, never solely on ROI
"""

from __future__ import annotations

from typing import Any
import numpy as np
from scipy.optimize import minimize
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
    - 'logistic': temperature-regularized Platt scaling on log-odds when sample size >= min_samples_logistic
    - 'isotonic': Isotonic + regularized Platt blend when sample size >= min_samples_isotonic
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
        self.eff_slope: float = 1.0
        self.eff_intercept: float = 0.0
        self.cutoff_time_str: str | None = None
        self.train_sample_size: int = 0

    @property
    def is_fitted(self) -> bool:
        """True once a logistic or isotonic calibrator has been fitted (not identity fallback)."""
        return self.active_method != "identity" and (
            self.logistic_model is not None or self.isotonic_model is not None
        )

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
            self.eff_slope = 1.0
            self.eff_intercept = 0.0
            return self.active_method

        p_arr = np.asarray(probs, dtype=float)
        y_arr = np.asarray(outcomes, dtype=int)

        chosen = self.requested_method
        if chosen == "auto":
            # Smooth Bayesian-prior temperature scaling preserves strict monotonicity and avoids
            # step-function overfitting of isotonic regression on noisy sports outcomes.
            chosen = "logistic"
        elif chosen == "isotonic" and self.train_sample_size < self.min_samples_isotonic:
            chosen = "logistic"

        X_logit = _logit(p_arr).reshape(-1, 1)
        lr = LogisticRegression(C=0.6, random_state=42)
        lr.fit(X_logit, y_arr)
        self.logistic_model = lr

        # Fisher-information-scaled Empirical-Bayes Platt temperature scaling in log-odds space:
        # Scales the prior precision by the empirical per-sample Fisher information `E[p(1-p) z^2]`
        # so high-dispersion, already-calibrated markets (e.g. Moneyline) receive strong small-sample
        # protection toward slope=1.0 while low-dispersion market-relative markets (Totals / Spreads)
        # rapidly learn temperature shrinkage without chasing transient Over/Home base-rate drift.
        z_vec = X_logit.ravel()
        y_float = y_arr.astype(float)
        n_f = float(self.train_sample_size)
        p_id = np.clip(p_arr, 1e-5, 1.0 - 1e-5)
        w_var = p_id * (1.0 - p_id)
        fisher_slope = float(np.mean(w_var * (z_vec ** 2)))
        fisher_int = float(np.mean(w_var))
        lam_slope = (105.0 * max(0.015, fisher_slope)) / n_f
        lam_intercept = (220.0 * max(0.05, fisher_int)) / n_f

        def _platt_obj_and_grad(params: np.ndarray) -> tuple[float, np.ndarray]:
            a, b = float(params[0]), float(params[1])
            z = np.clip(a * z_vec + b, -20.0, 20.0)
            p = np.clip(1.0 / (1.0 + np.exp(-z)), 1e-7, 1.0 - 1e-7)
            nll = -float(np.mean(y_float * np.log(p) + (1.0 - y_float) * np.log(1.0 - p)))
            loss = nll + 0.5 * lam_slope * ((a - 1.0) ** 2) + 0.5 * lam_intercept * (b ** 2)
            diff = p - y_float
            g_a = float(np.mean(diff * z_vec)) + lam_slope * (a - 1.0)
            g_b = float(np.mean(diff)) + lam_intercept * b
            return loss, np.array([g_a, g_b], dtype=float)

        opt = minimize(
            _platt_obj_and_grad,
            x0=np.array([1.0, 0.0], dtype=float),
            jac=True,
            method="L-BFGS-B",
            bounds=[(0.12, 1.35), (-0.06, 0.06)],
        )
        if opt.success:
            raw_slope = float(opt.x[0])
            raw_intercept = float(opt.x[1])
        else:
            raw_slope = float(np.clip(float(lr.coef_[0][0]), 0.15, 1.35))
            raw_intercept = 0.0

        self.eff_slope = raw_slope
        # Enforce strict zero intercept on small samples (N <= 50) to prevent directional bias
        intercept_w = min(1.0, max(0.0, (self.train_sample_size - 50.0) / 350.0))
        self.eff_intercept = float(np.clip(raw_intercept * intercept_w, -0.05, 0.05))

        if chosen == "isotonic":
            iso = IsotonicRegression(y_min=0.03, y_max=0.97, out_of_bounds="clip")
            iso.fit(p_arr, y_arr)
            self.isotonic_model = iso
            self.active_method = "isotonic"
        else:
            self.active_method = "logistic"

        return self.active_method

    def _platt_predict(self, p_arr: np.ndarray) -> np.ndarray:
        logits = _logit(p_arr)
        cal_logits = self.eff_slope * logits + self.eff_intercept
        return 1.0 / (1.0 + np.exp(-cal_logits))

    def transform(self, raw_probabilities: list[float] | np.ndarray) -> np.ndarray:
        p_arr = np.asarray(raw_probabilities, dtype=float)
        if self.active_method == "isotonic" and self.isotonic_model is not None:
            iso_cal = self.isotonic_model.predict(p_arr)
            platt_cal = self._platt_predict(p_arr)
            # Smoothly weight isotonic only as sample size grows (prevents step-function variance on N=100..300)
            iso_w = min(0.28, max(0.0, (self.train_sample_size - 100.0) / 1000.0))
            blended = iso_w * iso_cal + (1.0 - iso_w) * platt_cal
            return np.round(np.clip(blended, 0.03, 0.97), 6)
        if self.active_method == "logistic" and self.logistic_model is not None:
            cal = self._platt_predict(p_arr)
            return np.round(np.clip(cal, 0.03, 0.97), 6)
        return np.round(np.clip(p_arr, 0.03, 0.97), 6)

    def transform_single(self, raw_probability: float) -> float:
        return float(self.transform([raw_probability])[0])


class VennAbersConformalInterval:
    """
    V7 Fase 3 — Inductive Venn-Abers Predictor (conformal family, Vovk & Petej 2014).

    For binary outcomes, split-conformal regression intervals (e.g. MAPIE regressors) are not meaningful on
    a probability. Venn-Abers is the conformal method designed for probabilistic binary classification:
    for each new score s it fits two isotonic regressions on the calibration set augmented with (s, y=0)
    and (s, y=1), producing a probability interval [p0, p1] with a finite-sample multi-probabilistic
    validity guarantee (one of p0/p1 is perfectly calibrated under exchangeability).

    Temporal adaptation: only the most recent `window` resolved games (strictly before the cutoff) are
    used, so the interval widens automatically when the model drifts or data are scarce.
    """

    def __init__(self, window: int = 1200, min_samples: int = 60) -> None:
        self.window = window
        self.min_samples = min_samples
        self.scores: np.ndarray = np.empty(0)
        self.labels: np.ndarray = np.empty(0, dtype=int)
        self.cutoff_time_str: str | None = None
        self.is_fitted = False

    def fit(self, calibration_records: list[dict[str, Any]], calibration_cutoff_time: str) -> bool:
        cutoff_dt = parse_iso_utc(calibration_cutoff_time)
        rows: list[tuple[str, float, int]] = []
        for rec in calibration_records:
            if parse_iso_utc(rec["game_start_time"]) >= cutoff_dt:
                raise TemporalLeakageError(
                    f"Conformal lookahead leakage: game_start_time ({rec['game_start_time']}) "
                    f">= cutoff ({calibration_cutoff_time})"
                )
            res_ts = rec.get("result_recorded_at")
            if res_ts and parse_iso_utc(res_ts) > cutoff_dt:
                raise TemporalLeakageError(
                    f"Conformal lookahead leakage: result_recorded_at ({res_ts}) > cutoff ({calibration_cutoff_time})"
                )
            rows.append((str(rec["game_start_time"]), float(rec["raw_probability"]), int(rec["outcome"])))

        rows.sort(key=lambda r: r[0])
        rows = rows[-self.window:]
        self.cutoff_time_str = calibration_cutoff_time
        if len(rows) < self.min_samples or len({r[2] for r in rows}) < 2:
            self.is_fitted = False
            return False
        self.scores = np.asarray([r[1] for r in rows], dtype=float)
        self.labels = np.asarray([r[2] for r in rows], dtype=int)
        self.is_fitted = True
        return True

    def _iso_at(self, score: float, label: int) -> float:
        x = np.append(self.scores, score)
        y = np.append(self.labels, label)
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        iso.fit(x, y)
        return float(iso.predict([score])[0])

    def predict_interval(self, raw_probability: float) -> dict[str, Any]:
        """
        Returns {p0, p1, p_va (merged point), width, is_fitted, is_conformal, calibration_method,
        sample_size, cutoff_utc}. When not fitted (insufficient history), returns an explicit
        unfitted heuristic interval fallback that MUST NOT be treated as conformal.
        """
        s = float(np.clip(raw_probability, 1e-4, 1.0 - 1e-4))
        n_samples = int(len(self.scores))
        if not self.is_fitted:
            p0, p1 = max(0.0, s - 0.15), min(1.0, s + 0.15)
            return {
                "p0": round(p0, 6),
                "p1": round(p1, 6),
                "p_va": round(s, 6),
                "width": round(p1 - p0, 6),
                "is_fitted": False,
                "is_conformal": False,
                "calibration_method": "unfitted_heuristic_fallback",
                "sample_size": n_samples,
                "cutoff_utc": self.cutoff_time_str,
            }
        p0 = self._iso_at(s, 0)
        p1 = self._iso_at(s, 1)
        lo, hi = min(p0, p1), max(p0, p1)
        # Log-loss optimal merge of the Venn-Abers pair
        p_va = hi / (1.0 - lo + hi) if (1.0 - lo + hi) > 0 else s
        return {
            "p0": round(lo, 6),
            "p1": round(hi, 6),
            "p_va": round(p_va, 6),
            "width": round(hi - lo, 6),
            "is_fitted": True,
            "is_conformal": True,
            "calibration_method": "venn_abers",
            "sample_size": n_samples,
            "cutoff_utc": self.cutoff_time_str,
        }


def conformal_lower_bound_ev(
    point_prob: float,
    interval_low: float,
    market_prob: float | None,
    model_weight: float,
    decimal_odds: float,
    p_push: float = 0.0,
) -> dict[str, float]:
    """
    Pessimistic (lower-bound) EV: replaces the model probability with the conservative edge of its
    Venn-Abers interval (never above the point estimate) before applying market anchoring and push mass.
    """
    p_p = max(0.0, min(0.5, float(p_push or 0.0)))
    non_push = max(1e-9, 1.0 - p_p)
    p_low_model = min(float(interval_low), float(point_prob))
    p_low_cond = min(1.0, max(0.0, p_low_model / non_push)) if p_p > 0.0 else p_low_model
    w = max(0.0, min(1.0, float(model_weight)))
    p_low_cond_final = p_low_cond if market_prob is None else w * p_low_cond + (1.0 - w) * float(market_prob)
    p_low_win = non_push * p_low_cond_final if p_p > 0.0 else p_low_cond_final
    p_low_loss = non_push * (1.0 - p_low_cond_final) if p_p > 0.0 else (1.0 - p_low_win)
    ev_low = p_low_win * (float(decimal_odds) - 1.0) - p_low_loss
    return {"p_low_final": round(p_low_win, 6), "ev_lower_bound": round(ev_low, 6)}


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


def calibrate_binary_with_push(
    raw_prob: float,
    p_push: float = 0.0,
    calibrator: ProbabilityCalibrator | None = None,
    va_calibrator: VennAbersConformalInterval | None = None,
) -> dict[str, Any]:
    """
    Calibrates a binary win probability while preserving discrete push mass (`p_push`).
    When `p_push > 0`, maps `raw_prob` into conditional decisive space `P(win | not push)`
    before applying the binary calibrator and conformal Venn-Abers interval, then scales back
    by `(1 - p_push)` so `cal_prob + cal_complement + p_push` remains coherent.
    """
    p_p = max(0.0, min(0.5, float(p_push or 0.0)))
    non_push = max(1e-9, 1.0 - p_p)
    raw_clipped = float(np.clip(float(raw_prob), 1e-4, 1.0 - 1e-4))
    raw_cond = float(np.clip(raw_clipped / non_push, 1e-4, 1.0 - 1e-4)) if p_p > 0.0 else raw_clipped
    cal_cond = float(calibrator.transform_single(raw_cond)) if calibrator is not None else raw_cond
    cal_prob = cal_cond * non_push if p_p > 0.0 else cal_cond

    va_scaled: dict[str, Any] | None = None
    if va_calibrator is not None:
        va_raw = va_calibrator.predict_interval(raw_cond)
        if p_p > 0.0:
            va_scaled = {
                **va_raw,
                "p0": round(non_push * float(va_raw["p0"]), 6),
                "p1": round(non_push * float(va_raw["p1"]), 6),
                "p_va": round(non_push * float(va_raw["p_va"]), 6),
                "width": round(non_push * float(va_raw["width"]), 6),
            }
        else:
            va_scaled = dict(va_raw)

    return {
        "cal_prob": cal_prob,
        "cal_cond": cal_cond,
        "raw_cond": raw_cond,
        "p_push": p_p,
        "non_push": non_push,
        "va_interval": va_scaled,
    }
