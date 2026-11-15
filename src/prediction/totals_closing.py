"""
Chronological Totals Closing-Line Movement Anticipation Model (`src/prediction/totals_closing.py`).

Uses strictly prior finalized Totals markets (`game_date < eval_date` and constrained to
the configured development window) to learn via L2-shrunk OLS whether model Over/Under
probability divergence `(p_over - 0.50)` anticipates closing line movement `(close_line - open_line)`.
Never uses holdout-season observations during fitting.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

# Empirical half-point to fair probability conversion near NBA totals sigma (~18.0 pts -> ~2.2%/pt).
EMPIRICAL_PROB_PCT_PER_POINT = 2.2


@dataclass(frozen=True)
class TotalsClosingEstimator:
    """Frozen ridge-shrunk linear estimator mapping `(p_over - 0.50)` to expected closing total shift."""

    intercept: float = 0.0
    slope: float = 0.0
    sample_size: int = 0
    l2_shrinkage: float = 0.15
    min_samples: int = 40
    in_sample_corr: float = 0.0

    @property
    def is_active(self) -> bool:
        """True only when enough prior data exists and the fitted slope is strictly positive."""
        return self.sample_size >= self.min_samples and self.slope > 0.0

    def predict(
        self,
        p_over: float,
        *,
        min_expected_move_pts: float = 0.25,
    ) -> dict[str, Any]:
        """Predict expected closing line move `(close_total - open_total)` in points and directional CLV."""
        signal = float(p_over) - 0.50
        if not self.is_active:
            return {
                "active": False,
                "expected_move_pts": 0.0,
                "predicted_side": None,
                "expected_clv_pct": 0.0,
                "signal_divergence": round(signal, 6),
                "qualifies": False,
            }
        expected_move = float(np.clip(self.intercept + self.slope * signal, -4.0, 4.0))
        abs_move = abs(expected_move)
        side = "OVER" if expected_move > 0.0 else "UNDER"
        expected_clv_pct = round(abs_move * EMPIRICAL_PROB_PCT_PER_POINT, 4)
        return {
            "active": True,
            "expected_move_pts": round(expected_move, 4),
            "predicted_side": side,
            "expected_clv_pct": expected_clv_pct,
            "signal_divergence": round(signal, 6),
            "qualifies": abs_move >= float(min_expected_move_pts),
        }


def fit_totals_closing_estimator(
    prior_rows: Sequence[dict[str, Any]],
    *,
    l2_shrinkage: float = 0.15,
    min_samples: int = 40,
) -> TotalsClosingEstimator:
    """
    Fits `close_total - open_total ~ intercept + slope * (p_over - 0.50)` using L2 shrinkage
    purely on prior chronological rows supplied by the caller.
    Each row needs `p_over` (or `model_p_over`), `tot_open_line`, and `tot_close_line`.
    Penalty is scaled to probability-squared units `(p_over - 0.50)^2` (~0.0025/game) so
    small samples shrink smoothly without washing out real line-anticipation signal.
    """
    xs: list[float] = []
    ys: list[float] = []
    for row in prior_rows:
        p_raw = row.get("p_over") if row.get("p_over") is not None else row.get("model_p_over")
        open_l = row.get("tot_open_line") if row.get("tot_open_line") is not None else row.get("open_line")
        close_l = row.get("tot_close_line") if row.get("tot_close_line") is not None else row.get("close_line")
        if p_raw is None or open_l is None or close_l is None:
            continue
        diff = float(np.clip(float(close_l) - float(open_l), -6.0, 6.0))
        xs.append(float(p_raw) - 0.50)
        ys.append(diff)

    n = len(xs)
    if n < min_samples:
        return TotalsClosingEstimator(
            intercept=0.0,
            slope=0.0,
            sample_size=n,
            l2_shrinkage=float(l2_shrinkage),
            min_samples=int(min_samples),
            in_sample_corr=0.0,
        )

    x_arr = np.asarray(xs, dtype=float)
    y_arr = np.asarray(ys, dtype=float)
    design = np.column_stack([np.ones(n, dtype=float), x_arr])
    penalty = np.diag([float(l2_shrinkage) * 0.1, float(l2_shrinkage)])
    beta = np.linalg.solve(design.T @ design + penalty, design.T @ y_arr)

    corr = 0.0
    if float(np.std(x_arr)) > 1e-9 and float(np.std(y_arr)) > 1e-9:
        corr = float(np.corrcoef(x_arr, y_arr)[0, 1])

    return TotalsClosingEstimator(
        intercept=round(float(beta[0]), 6),
        slope=round(float(beta[1]), 6),
        sample_size=n,
        l2_shrinkage=float(l2_shrinkage),
        min_samples=int(min_samples),
        in_sample_corr=round(corr, 4),
    )
