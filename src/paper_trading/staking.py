"""
Stake sizing.

`fractional_kelly_stake` makes the stake grow with the model's (calibrated, market-anchored) probability
of winning, for a given price: the Kelly fraction f* = (p * O - 1) / (O - 1) increases with p, and it is
zero when the bet has no positive expected value. This replaces the old probability "tiers", which
assigned large fixed stakes to favourites regardless of price (and even to negative-EV bets).

Guardrails:
  - fractional Kelly (default 25%), because p is an estimate with error;
  - hard cap per bet (absolute PEN and % of bankroll) from config/model_config.yaml (AGENTS.md);
  - stakes below the minimum are skipped (returned as 0.0), never rounded UP to a floor.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.config import DEFAULT_AGGRESSIVE_PROFILE, DEFAULT_CONSERVATIVE_PROFILE


def kelly_fraction_full(prob: float, decimal_odds: float) -> float:
    """Full-Kelly fraction of bankroll; 0 when the bet has no positive edge."""
    b = float(decimal_odds) - 1.0
    if b <= 0.0:
        return 0.0
    p = min(max(float(prob), 0.0), 1.0)
    return max(0.0, (p * float(decimal_odds) - 1.0) / b)


def fractional_kelly_stake(
    prob: float,
    decimal_odds: float,
    bankroll_pen: float,
    kelly_fraction: float = 0.25,
    min_stake_pen: float = 0.50,
    max_stake_pen: float = 3.00,
    max_bankroll_fraction: float = 0.03,
) -> float:
    """Stake in PEN (2 decimals). Returns 0.0 for no edge, an empty bankroll, or a stake below the minimum."""
    if bankroll_pen <= 0.0:
        return 0.0
    f = kelly_fraction_full(prob, decimal_odds) * float(kelly_fraction)
    if f <= 0.0:
        return 0.0
    stake = min(float(bankroll_pen) * min(f, float(max_bankroll_fraction)), float(max_stake_pen))
    stake = round(stake, 2)
    return stake if stake >= float(min_stake_pen) else 0.0



def compute_contextual_stake_pen_impl(
    *,
    calibrated_prob: float,
    decimal_odds: float,
    ev_unit: float,
    current_bankroll_pen: float,
    initial_bankroll_pen: float,
    max_stake_pen: float,
    staking_mode: str,
    risk_config: Any,
    enable_cppi_shield: bool,
    clv_governor_fn: Callable[[], tuple[float, float | None]],
    cppi_fn: Callable[[float, float | None], float],
    uncertainty_std: float = 0.05,
    selection: str = "",
    overtime_prob: float = 0.0,
    steam_delta: float = 0.0,
    apply_clv_governor: bool = True,
    conformal_width: float | None = None,
    ev_lower_bound: float | None = None,
    apply_cppi_shield: bool | None = None,
    peak_bankroll_pen: float | None = None,
) -> float:
    """Calculates contextual Kelly-Conviction stake (research mode, capped at max_stake_pen)."""
    p = max(0.01, min(0.99, float(calibrated_prob)))
    b = max(0.05, float(decimal_odds) - 1.0)
    f_kelly = max(0.0, (p * (b + 1.0) - 1.0) / b)

    ct_cfg = getattr(risk_config, "conviction_tiers", None)
    if ct_cfg:
        prof = ct_cfg.aggressive if staking_mode == "AGGRESSIVE_ALPHA" else ct_cfg.conservative
    else:
        prof = DEFAULT_AGGRESSIVE_PROFILE if staking_mode == "AGGRESSIVE_ALPHA" else DEFAULT_CONSERVATIVE_PROFILE

    t_low, t_mid, t_high, t_star = prof.tier_low, prof.tier_mid, prof.tier_high, prof.tier_star
    if p < t_mid.prob_floor:
        span = max(0.001, t_low.prob_ceil - t_low.prob_floor)
        tier_base = t_low.base + max(0.0, (p - t_low.prob_floor) / span) * t_low.slope
        kelly_bonus = min(t_low.kelly_cap, f_kelly * t_low.kelly_multiplier)
    elif p < t_high.prob_floor:
        span = max(0.001, t_mid.prob_ceil - t_mid.prob_floor)
        tier_base = t_mid.base + ((p - t_mid.prob_floor) / span) * t_mid.slope
        kelly_bonus = min(t_mid.kelly_cap, f_kelly * t_mid.kelly_multiplier)
    elif p < t_star.prob_floor:
        span = max(0.001, t_high.prob_ceil - t_high.prob_floor)
        tier_base = t_high.base + ((p - t_high.prob_floor) / span) * t_high.slope
        kelly_bonus = min(t_high.kelly_cap, f_kelly * t_high.kelly_multiplier)
    else:
        span = max(0.001, t_star.prob_ceil - t_star.prob_floor) if t_star.prob_ceil > t_star.prob_floor else 0.10
        tier_base = t_star.base + min(1.0, (p - t_star.prob_floor) / span) * t_star.slope
        kelly_bonus = min(t_star.kelly_cap, f_kelly * t_star.kelly_multiplier)

    edge_modulator = min(1.0, max(prof.edge_modulator_floor, float(ev_unit) / prof.edge_modulator_div))
    modulated_tier = prof.min_stake_floor + (tier_base - prof.min_stake_floor) * edge_modulator
    raw_stake = modulated_tier + kelly_bonus
    min_stake_floor = prof.min_stake_floor

    if decimal_odds > prof.max_longshot_odds:
        raw_stake = min(raw_stake, prof.max_longshot_stake)

    ot_cfg = getattr(risk_config, "overtime_guard", None)
    if ot_cfg and ot_cfg.enabled:
        if str(selection).upper() == "UNDER" and float(overtime_prob) >= ot_cfg.min_overtime_prob:
            raw_stake *= ot_cfg.under_haircut
    elif str(selection).upper() == "UNDER" and float(overtime_prob) >= 0.068:
        raw_stake *= 0.85

    rm_cfg = getattr(risk_config, "risk_modulators", None)
    if rm_cfg:
        if uncertainty_std > rm_cfg.high_uncertainty_std:
            raw_stake *= rm_cfg.high_uncertainty_factor
        elif uncertainty_std <= rm_cfg.low_uncertainty_std:
            raw_stake *= rm_cfg.low_uncertainty_factor
        if conformal_width is not None:
            if float(conformal_width) <= rm_cfg.narrow_conformal_width:
                raw_stake *= rm_cfg.narrow_conformal_factor
            elif float(conformal_width) >= rm_cfg.wide_conformal_width:
                raw_stake *= rm_cfg.wide_conformal_factor
        if ev_lower_bound is not None and float(ev_lower_bound) > 0.0:
            raw_stake *= rm_cfg.ev_lower_bound_boost_factor
        if float(steam_delta) >= rm_cfg.sharp_steam_delta:
            raw_stake *= rm_cfg.sharp_steam_factor
        elif float(steam_delta) <= rm_cfg.adverse_steam_delta:
            raw_stake *= rm_cfg.adverse_steam_factor
    else:
        if uncertainty_std > 0.08:
            raw_stake *= 0.85
        elif uncertainty_std <= 0.045:
            raw_stake *= 1.10
        if conformal_width is not None:
            if float(conformal_width) <= 0.035:
                raw_stake *= 1.06
            elif float(conformal_width) >= 0.080:
                raw_stake *= 0.88
        if ev_lower_bound is not None and float(ev_lower_bound) > 0.0:
            raw_stake *= 1.05
        if float(steam_delta) >= 0.020:
            raw_stake *= 1.08
        elif float(steam_delta) <= -0.020:
            raw_stake *= 0.85

    if apply_clv_governor:
        clv_factor, _ = clv_governor_fn()
        raw_stake *= clv_factor

    bankroll_scale = max(0.80, min(1.50, float(current_bankroll_pen) / max(1.0, initial_bankroll_pen)))
    scaled_stake = raw_stake * bankroll_scale

    should_apply_cppi = apply_cppi_shield if apply_cppi_shield is not None else enable_cppi_shield
    if should_apply_cppi:
        scaled_stake *= cppi_fn(current_bankroll_pen, peak_bankroll_pen)

    return round(max(min_stake_floor, min(max_stake_pen, scaled_stake)), 2)
