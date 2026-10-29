"""Expected Value (EV), gross implied probability, and documented de-vigging methods."""

from __future__ import annotations

import math
from typing import Any

from src.validation.validator import DataValidationError, validate_odds_record


def calculate_implied_prob_gross(decimal_odds: float) -> float:
    """
    Calculates gross implied probability from decimal odds O:
        p_implicita = 1 / O
    """
    if decimal_odds is None or not isinstance(decimal_odds, (int, float)) or math.isnan(decimal_odds) or decimal_odds <= 1.0:
        raise DataValidationError(f"Decimal odds must be a finite number > 1.0; got {decimal_odds!r}")
    return round(1.0 / float(decimal_odds), 6)


def calculate_bookmaker_overround(odds_a: float, odds_b: float) -> float:
    """
    Calculates bookmaker margin (overround / vigorish) for a two-way market:
        overround = (1 / O_a + 1 / O_b) - 1
    """
    p_a = calculate_implied_prob_gross(odds_a)
    p_b = calculate_implied_prob_gross(odds_b)
    return round((p_a + p_b) - 1.0, 6)


def devig_multiplicative(odds_a: float, odds_b: float) -> tuple[float, float, float]:
    """
    Documented multiplicative (proportional) margin removal method.
    Distinguishes gross implied probabilities (1/O) from fair market probabilities:
        p_fair_a = (1/O_a) / (1/O_a + 1/O_b)
        p_fair_b = (1/O_b) / (1/O_a + 1/O_b)
    Returns (p_fair_a, p_fair_b, overround).
    """
    p_a = calculate_implied_prob_gross(odds_a)
    p_b = calculate_implied_prob_gross(odds_b)
    total_gross = p_a + p_b
    overround = round(total_gross - 1.0, 6)
    return round(p_a / total_gross, 6), round(p_b / total_gross, 6), overround


def calculate_ev(estimated_prob: float, decimal_odds: float) -> dict[str, float]:
    """
    Calculates Expected Value per unit staked and percentage EV:
        EV = p * O - 1
        EV_pct = 100 * (p * O - 1)
    """
    if estimated_prob is None or not isinstance(estimated_prob, (int, float)) or math.isnan(estimated_prob):
        raise DataValidationError(f"Invalid estimated probability: {estimated_prob!r}")
    if estimated_prob < 0.0 or estimated_prob > 1.0:
        raise DataValidationError(f"Probability must be in [0, 1]; got {estimated_prob!r}")
    p_gross = calculate_implied_prob_gross(decimal_odds)

    ev_unit = float(estimated_prob) * float(decimal_odds) - 1.0
    ev_pct = 100.0 * ev_unit
    return {
        "implied_prob_gross": p_gross,
        "ev_unit": round(ev_unit, 6),
        "ev_pct": round(ev_pct, 4),
    }


def evaluate_market_opportunity(
    estimated_prob: float,
    uncertainty_std: float,
    odds_record: dict[str, Any],
    game_start_time: str,
    model_version_id: str,
    simulated_prediction_time: str | None = None,
) -> dict[str, Any]:
    """
    Validates odds + timestamp, estimates fair de-vigged probability when counterpart odds exist,
    and returns a structured EV evaluation record.
    """
    validate_odds_record(odds_record, game_start_time, simulated_prediction_time)
    dec_odds = float(odds_record["decimal_odds"])
    counterpart = odds_record.get("counterpart_decimal_odds")

    ev_metrics = calculate_ev(estimated_prob, dec_odds)
    if counterpart is not None and counterpart > 1.0:
        p_fair, _, overround = devig_multiplicative(dec_odds, float(counterpart))
    else:
        p_fair = None
        overround = None

    return {
        "game_id": odds_record["game_id"],
        "market": odds_record["market"],
        "selection": odds_record["selection"],
        "line_value": odds_record.get("line_value"),
        "decimal_odds_used": dec_odds,
        "odds_provider": odds_record["provider"],
        "odds_captured_at": odds_record["captured_at"],
        "estimated_probability": round(float(estimated_prob), 6),
        "uncertainty_std": round(float(uncertainty_std), 6),
        "implied_prob_gross": ev_metrics["implied_prob_gross"],
        "implied_prob_fair": p_fair,
        "bookmaker_overround": overround,
        "ev_unit": ev_metrics["ev_unit"],
        "ev_pct": ev_metrics["ev_pct"],
        "model_version_id": model_version_id,
    }
