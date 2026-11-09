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
