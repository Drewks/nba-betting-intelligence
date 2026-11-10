"""
Player Props Distribution Math & Exceedance Calculation (`src/prediction/props_distribution.py`).
Provides parametric Poisson and Normal models with continuity corrections and conditional push re-weighting.
"""

from __future__ import annotations

import math
import numpy as np
from scipy.stats import norm, poisson


def compute_exceedance_probabilities(
    prop_category: str,
    line_value: float,
    proj_mean: float,
    proj_std: float,
    dist_type: str = "normal",
) -> tuple[float, float]:
    """
    Computes (p_over, p_under) given a line and parametric distribution.
    Handles continuity correction and conditional push re-weighting for integer lines.
    """
    is_integer_line = abs(line_value - round(line_value)) < 1e-4

    if dist_type == "poisson":
        if is_integer_line:
            k = int(round(line_value))
            p_under_raw = float(poisson.cdf(k - 1, mu=proj_mean)) if k > 0 else 0.0
            p_push = float(poisson.pmf(k, mu=proj_mean))
            p_over_raw = float(1.0 - poisson.cdf(k, mu=proj_mean))
            non_push = max(1e-4, 1.0 - p_push)
            p_under = p_under_raw / non_push
            p_over = p_over_raw / non_push
        else:
            k = int(math.floor(line_value))
            p_under = float(poisson.cdf(k, mu=proj_mean))
            p_over = float(1.0 - p_under)
    else:
        if is_integer_line:
            s = max(0.5, proj_std)
            z_low = (line_value - 0.5 - proj_mean) / s
            z_high = (line_value + 0.5 - proj_mean) / s
            p_under_raw = float(norm.cdf(z_low))
            p_over_raw = float(1.0 - norm.cdf(z_high))
            p_push = float(norm.cdf(z_high) - norm.cdf(z_low))
            non_push = max(1e-4, 1.0 - p_push)
            p_under = p_under_raw / non_push
            p_over = p_over_raw / non_push
        else:
            z = (line_value - proj_mean) / max(0.5, proj_std)
            p_under = float(norm.cdf(z))
            p_over = float(1.0 - p_under)

    p_over = float(np.clip(p_over, 0.02, 0.98))
    p_under = float(np.clip(p_under, 0.02, 0.98))
    return round(p_over, 4), round(p_under, 4)
