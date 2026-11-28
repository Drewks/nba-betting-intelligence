"""
Player Props Distribution Math & Exceedance Calculation (`src/prediction/props_distribution.py`).
Provides parametric Poisson and Normal models producing unconditional (p_over, p_under, p_push)
triples summing strictly to 1.0 under integer push rules (F-004).
"""

from __future__ import annotations

import math
import numpy as np
from scipy.stats import norm, poisson


def compute_outcome_probabilities(
    prop_category: str,
    line_value: float,
    proj_mean: float,
    proj_std: float,
    dist_type: str = "normal",
) -> dict[str, float]:
    """
    Computes unconditional outcome triple {p_over, p_under, p_push} summing strictly to 1.0.
    For integer lines, p_push > 0 captures P(X == line) without reweighting Over/Under.
    """
    _ = prop_category
    is_integer_line = abs(line_value - round(line_value)) < 1e-4

    if dist_type == "poisson":
        mu = max(1e-4, float(proj_mean))
        if is_integer_line:
            k = int(round(line_value))
            p_under = float(poisson.cdf(k - 1, mu=mu)) if k > 0 else 0.0
            p_push = float(poisson.pmf(k, mu=mu))
            p_over = max(0.0, 1.0 - p_under - p_push)
        else:
            k = int(math.floor(line_value))
            p_under = float(poisson.cdf(k, mu=mu))
            p_over = max(0.0, 1.0 - p_under)
            p_push = 0.0
    else:
        if is_integer_line:
            s = max(0.5, float(proj_std))
            z_low = (line_value - 0.5 - proj_mean) / s
            z_high = (line_value + 0.5 - proj_mean) / s
            p_under = float(norm.cdf(z_low))
            p_over = float(1.0 - norm.cdf(z_high))
            p_push = max(0.0, 1.0 - p_under - p_over)
        else:
            z = (line_value - proj_mean) / max(0.5, float(proj_std))
            p_under = float(norm.cdf(z))
            p_over = max(0.0, 1.0 - p_under)
            p_push = 0.0

    p_over = float(np.clip(p_over, 0.0, 1.0))
    p_under = float(np.clip(p_under, 0.0, 1.0))
    p_push = float(np.clip(p_push, 0.0, 1.0))
    total = p_over + p_under + p_push
    if total > 0.0:
        p_over, p_under, p_push = p_over / total, p_under / total, p_push / total

    p_over_r = round(p_over, 6)
    p_push_r = round(p_push, 6)
    p_under_r = round(max(0.0, 1.0 - p_over_r - p_push_r), 6)
    return {"p_over": p_over_r, "p_under": p_under_r, "p_push": p_push_r}


def compute_exceedance_probabilities(
    prop_category: str,
    line_value: float,
    proj_mean: float,
    proj_std: float,
    dist_type: str = "normal",
) -> tuple[float, float, float]:
    """
    Computes unconditional (p_over, p_under, p_push) summing to 1.0 (F-004 unified contract).
    """
    res = compute_outcome_probabilities(
        prop_category=prop_category,
        line_value=line_value,
        proj_mean=proj_mean,
        proj_std=proj_std,
        dist_type=dist_type,
    )
    return res["p_over"], res["p_under"], res["p_push"]
