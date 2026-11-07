"""Expected Value (EV), gross implied probability, documented de-vigging (Multiplicative, Shin, Power), and Steam Move detection."""

from __future__ import annotations

import itertools
import math
from typing import Any
import numpy as np
from scipy.optimize import minimize

from src.calibration.calibrator import conformal_lower_bound_ev
from src.validation.validator import DataValidationError, validate_odds_record


def calculate_implied_prob_gross(decimal_odds: float) -> float:
    """
    Calculates gross implied probability from decimal odds O:
        p_implicita = 1 / O
    """
    if decimal_odds is None or not isinstance(decimal_odds, (int, float)) or math.isnan(decimal_odds) or decimal_odds <= 1.0:
        raise DataValidationError(f"Decimal odds must be a finite number > 1.0; got {decimal_odds!r}")
    return round(1.0 / float(decimal_odds), 6)


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


def devig_shin(odds_a: float, odds_b: float) -> tuple[float, float, float]:
    """
    V8 Shin's Method (1991, 1993) de-vigging for two-way markets.
    Accounts for asymmetric insider trading / favorite-longshot bias (FLB), where
    bookmakers embed disproportionately higher margin into underdogs/longshots than favorites.
    Given gross implied probabilities pi_a = 1/O_a, pi_b = 1/O_b and S = pi_a + pi_b:
      - If S <= 1.000001 (zero or negative margin), falls back to proportional normalization.
      - Otherwise solves Shin's mapping with insider trading fraction z in (0, 0.25]:
            u_i(z) = (sqrt(z^2 + 4 * (1 - z) * (pi_i^2 / S)) - z) / (2 * (1 - z))
        and normalizes p_fair_i = u_i / (u_a + u_b).
    Returns (p_fair_a, p_fair_b, overround).
    """
    pi_a = calculate_implied_prob_gross(odds_a)
    pi_b = calculate_implied_prob_gross(odds_b)
    total_gross = pi_a + pi_b
    overround = round(total_gross - 1.0, 6)
    if total_gross <= 1.000001 or abs(pi_a - pi_b) < 1e-9:
        return round(pi_a / total_gross, 6), round(pi_b / total_gross, 6), overround

    z = max(1e-6, min(0.25, total_gross - 1.0))
    denom = 2.0 * (1.0 - z)
    u_a = (math.sqrt(z * z + 4.0 * (1.0 - z) * (pi_a * pi_a) / total_gross) - z) / denom
    u_b = (math.sqrt(z * z + 4.0 * (1.0 - z) * (pi_b * pi_b) / total_gross) - z) / denom
    u_sum = u_a + u_b
    if u_sum <= 0.0:
        return round(pi_a / total_gross, 6), round(pi_b / total_gross, 6), overround
    return round(u_a / u_sum, 6), round(u_b / u_sum, 6), overround


def devig_power(odds_a: float, odds_b: float) -> tuple[float, float, float]:
    """
    V8 Power (Logarithmic) de-vigging method.
    Solves for exponent k > 0 such that (1/O_a)^k + (1/O_b)^k = 1.0 via bisection.
    Corrects favorite-longshot bias continuously across heavy favorites and longshots.
    Returns (p_fair_a, p_fair_b, overround).
    """
    pi_a = calculate_implied_prob_gross(odds_a)
    pi_b = calculate_implied_prob_gross(odds_b)
    total_gross = pi_a + pi_b
    overround = round(total_gross - 1.0, 6)
    if abs(total_gross - 1.0) < 1e-7 or abs(pi_a - pi_b) < 1e-9:
        return round(pi_a / total_gross, 6), round(pi_b / total_gross, 6), overround

    low_k, high_k = 0.5, 5.0
    for _ in range(40):
        mid_k = 0.5 * (low_k + high_k)
        val = (pi_a ** mid_k) + (pi_b ** mid_k)
        if val > 1.0:
            low_k = mid_k
        else:
            high_k = mid_k
    k_opt = 0.5 * (low_k + high_k)
    p_a = pi_a ** k_opt
    p_b = pi_b ** k_opt
    s_p = p_a + p_b
    return round(p_a / s_p, 6), round(p_b / s_p, 6), overround


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


SHARP_BOOK_KEYWORDS: tuple[str, ...] = ("pinnacle", "betfair", "matchbook", "lowvig", "circa", "bookmaker")

# Weight of the (calibrated) model probability when blending with the de-vigged market consensus.
# Sharp NBA closing lines are very efficient; a pure model estimate that disagrees by 10+ points
# is far more likely to be model error than edge. 0.30 is a conservative prior until enough real
# out-of-sample results exist to learn it.
DEFAULT_MODEL_WEIGHT = 0.30
MAX_MODEL_MARKET_DISAGREEMENT = 0.15


def compute_market_consensus(odds_rows: list[dict[str, Any]], method: str = "shin") -> dict[tuple[str, str, float | None], dict[str, Any]]:
    """
    De-vigged fair probability consensus per (market, selection, line_value).
    Prefers sharp books (Pinnacle, Betfair, Matchbook, LowVig...) and falls back to the median of
    all books. Only rows with a counterpart price (two-way market) are used.
    Supports method='shin' (default, corrects favorite-longshot bias), 'power', or 'multiplicative'.
    """
    devig_fn = devig_shin if method == "shin" else (devig_power if method == "power" else devig_multiplicative)
    groups: dict[tuple[str, str, float | None], dict[str, list[float]]] = {}
    for o in odds_rows:
        cp = o.get("counterpart_decimal_odds")
        if cp is None or float(cp) <= 1.0 or float(o.get("decimal_odds") or 0.0) <= 1.0:
            continue
        p_fair, _, _ = devig_fn(float(o["decimal_odds"]), float(cp))
        key = (o["market"], o["selection"], o.get("line_value"))
        bucket = groups.setdefault(key, {"sharp": [], "all": []})
        bucket["all"].append(p_fair)
        if any(k in str(o.get("provider", "")).lower() for k in SHARP_BOOK_KEYWORDS):
            bucket["sharp"].append(p_fair)

    out: dict[tuple[str, str, float | None], dict[str, Any]] = {}
    for key, b in groups.items():
        src = b["sharp"] if b["sharp"] else b["all"]
        srt = sorted(src)
        mid = len(srt) // 2
        median = srt[mid] if len(srt) % 2 else 0.5 * (srt[mid - 1] + srt[mid])
        out[key] = {
            "p_market": round(median, 6),
            "source": "sharp" if b["sharp"] else "consensus",
            "n_books": len(src),
        }
    return out


def compute_line_steam(odds_history: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, float]]:
    """
    Computes chronological line movement ("Steam Move" velocity) per (market, selection)
    across ordered pre-game odds_snapshots:
        steam_delta = p_fair_latest - p_fair_opening
    Positive steam_delta (> 0) indicates sharp money steaming toward this selection (implied fair prob rising).
    Negative steam_delta (< 0) indicates market steaming against this selection.
    """
    ordered = sorted(odds_history, key=lambda r: str(r.get("captured_at", "")))
    by_side: dict[tuple[str, str], list[float]] = {}
    for o in ordered:
        dec = o.get("decimal_odds")
        cp = o.get("counterpart_decimal_odds")
        if dec is None or float(dec) <= 1.0:
            continue
        if cp is not None and float(cp) > 1.0:
            p_f, _, _ = devig_shin(float(dec), float(cp))
        else:
            p_f = calculate_implied_prob_gross(float(dec))
        key = (str(o.get("market", "")), str(o.get("selection", "")))
        by_side.setdefault(key, []).append(p_f)

    out: dict[tuple[str, str], dict[str, float]] = {}
    for key, probs in by_side.items():
        p_open = probs[0]
        p_latest = probs[-1]
        out[key] = {
            "p_fair_open": round(p_open, 6),
            "p_fair_latest": round(p_latest, 6),
            "steam_delta": round(p_latest - p_open, 6),
            "n_snapshots": float(len(probs)),
        }
    return out


def market_anchored_probability(
    model_prob: float,
    market_prob: float | None,
    model_weight: float = DEFAULT_MODEL_WEIGHT,
) -> float:
    """p_final = w * p_model + (1 - w) * p_market  (falls back to p_model when no market exists)."""
    if market_prob is None:
        return round(float(model_prob), 6)
    w = max(0.0, min(1.0, float(model_weight)))
    return round(w * float(model_prob) + (1.0 - w) * float(market_prob), 6)


def predict_clv_meta_label(
    odds_record: dict[str, Any],
    game_start_time: str,
    steam_delta: float = 0.0,
    conformal_width: float | None = None,
    model_market_disagreement: float | None = None,
    overround: float | None = None,
) -> dict[str, Any]:
    """
    V8 Phase 2 Meta-Labeling CLV Filter (inspired by Marcos López de Prado).
    Predicts the likelihood of achieving positive Closing Line Value (P(CLV > 0))
    conditioned on line movement velocity (steam), market overround, time to tipoff,
    model disagreement, and conformal prediction set width.
    """
    s_delta = float(steam_delta or 0.0)
    width = float(conformal_width) if conformal_width is not None else 0.12
    ov = float(overround) if overround is not None else 0.045
    disag = abs(float(model_market_disagreement)) if model_market_disagreement is not None else 0.03

    # Calculate hours to tipoff
    try:
        from src.validation.validator import parse_iso_utc
        t_game = parse_iso_utc(game_start_time)
        t_odds = parse_iso_utc(str(odds_record.get("captured_at") or game_start_time))
        hours_to_tipoff = max(0.1, (t_game - t_odds).total_seconds() / 3600.0)
    except Exception:
        hours_to_tipoff = 2.0

    time_factor = 1.0 / (1.0 + 0.04 * min(12.0, hours_to_tipoff))
    z_score = (
        0.15
        + 14.0 * s_delta
        - 1.6 * max(0.0, width - 0.15)
        - 0.9 * max(0.0, disag - 0.08)
        - 2.2 * max(0.0, ov - 0.05)
    )
    p_clv = 1.0 / (1.0 + math.exp(-z_score * time_factor))
    exp_clv = round(s_delta * 100.0 + (p_clv - 0.50) * 8.0, 2)

    if s_delta <= -0.040:
        return {
            "p_positive_clv": round(p_clv, 4),
            "expected_clv_pct": exp_clv,
            "meta_label_pass": False,
            "reason_code": "ADVERSE_STEAM_DECAY",
        }
    if p_clv < 0.48:
        return {
            "p_positive_clv": round(p_clv, 4),
            "expected_clv_pct": exp_clv,
            "meta_label_pass": False,
            "reason_code": "NEGATIVE_EXPECTED_CLV",
        }

    return {
        "p_positive_clv": round(p_clv, 4),
        "expected_clv_pct": exp_clv,
        "meta_label_pass": True,
        "reason_code": "PASS",
    }


def evaluate_market_opportunity(
    estimated_prob: float,
    uncertainty_std: float,
    odds_record: dict[str, Any],
    game_start_time: str,
    model_version_id: str,
    simulated_prediction_time: str | None = None,
    market_consensus_prob: float | None = None,
    model_weight: float = DEFAULT_MODEL_WEIGHT,
    max_disagreement: float = MAX_MODEL_MARKET_DISAGREEMENT,
    steam_delta: float = 0.0,
    conformal_interval: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Validates odds + timestamp, estimates fair de-vigged probability (Shin's method) when counterpart odds exist,
    modulates model_weight when sharp steam moves are detected, anchors the estimated probability
    to market consensus (if available), computes Venn-Abers conformal lower-bound EV (if conformal interval provided),
    and returns a structured EV evaluation record.
    """
    validate_odds_record(odds_record, game_start_time, simulated_prediction_time)
    dec_odds = float(odds_record["decimal_odds"])
    counterpart = odds_record.get("counterpart_decimal_odds")

    if counterpart is not None and counterpart > 1.0:
        p_fair, _, overround = devig_shin(dec_odds, float(counterpart))
    else:
        p_fair = None
        overround = None

    market_prob = market_consensus_prob if market_consensus_prob is not None else p_fair
    disagreement = (float(estimated_prob) - float(market_prob)) if market_prob is not None else None

    eff_weight = float(model_weight)
    s_delta = float(steam_delta or 0.0)
    if market_prob is not None and s_delta != 0.0:
        # Adverse steam (>= 2.5% move against our selection): shift weight toward sharp market
        if s_delta <= -0.025:
            eff_weight = max(0.15, eff_weight - 0.08)
        # Confirming steam (>= 2.0% move toward our selection when model also favors this side)
        elif s_delta >= 0.020 and float(estimated_prob) > float(market_prob):
            eff_weight = min(0.42, eff_weight + 0.04)

    anchored_prob = market_anchored_probability(estimated_prob, market_prob, model_weight=eff_weight)

    ev_metrics = calculate_ev(anchored_prob, dec_odds)

    lb_metrics = None
    if conformal_interval is not None and "p0" in conformal_interval:
        p_low = float(conformal_interval["p0"])
        lb_metrics = conformal_lower_bound_ev(
            point_prob=estimated_prob,
            interval_low=p_low,
            market_prob=market_prob,
            model_weight=eff_weight,
            decimal_odds=dec_odds,
        )

    ev_lb_unit = lb_metrics["ev_lower_bound"] if lb_metrics else ev_metrics["ev_unit"]
    ev_lb_pct = round(ev_lb_unit * 100.0, 4)

    clv_meta = predict_clv_meta_label(
        odds_record=odds_record,
        game_start_time=game_start_time,
        steam_delta=s_delta,
        conformal_width=float(conformal_interval["width"]) if (conformal_interval and "width" in conformal_interval) else None,
        model_market_disagreement=disagreement,
        overround=overround,
    )

    return {
        "p_positive_clv": clv_meta["p_positive_clv"],
        "expected_clv_pct": clv_meta["expected_clv_pct"],
        "meta_label_pass": clv_meta["meta_label_pass"],
        "meta_label_reason": clv_meta["reason_code"],
        "game_id": odds_record["game_id"],
        "market": odds_record["market"],
        "selection": odds_record["selection"],
        "line_value": odds_record.get("line_value"),
        "decimal_odds_used": dec_odds,
        "odds_provider": odds_record["provider"],
        "odds_captured_at": odds_record["captured_at"],
        "estimated_probability": round(float(anchored_prob), 6),
        "raw_model_probability": round(float(estimated_prob), 6),
        "uncertainty_std": round(float(uncertainty_std), 6),
        "implied_prob_gross": ev_metrics["implied_prob_gross"],
        "implied_prob_fair": p_fair,
        "bookmaker_overround": overround,
        "ev_unit": ev_metrics["ev_unit"],
        "ev_pct": ev_metrics["ev_pct"],
        "model_version_id": model_version_id,
        "model_market_disagreement": round(float(disagreement), 6) if disagreement is not None else None,
        "max_model_market_disagreement": max_disagreement,
        "steam_delta": round(s_delta, 6),
        "conformal_p_low": round(float(conformal_interval["p0"]), 6) if (conformal_interval and "p0" in conformal_interval) else None,
        "conformal_p_high": round(float(conformal_interval["p1"]), 6) if (conformal_interval and "p1" in conformal_interval) else None,
        "conformal_width": round(float(conformal_interval["width"]), 6) if (conformal_interval and "width" in conformal_interval) else None,
        "ev_lower_bound": round(float(ev_lb_unit), 6),
        "ev_lower_bound_pct": ev_lb_pct,
    }


def optimize_simultaneous_kelly_portfolio(
    candidates: list[dict[str, Any]],
    bankroll_pen: float,
    max_total_exposure_fraction: float = 0.15,
    max_individual_fraction: float = 0.06,
    fractional_multiplier: float = 0.50,
) -> list[dict[str, Any]]:
    """
    V7 Fase 5: Multi-Bet Simultaneous Kelly Portfolio Optimization (scipy.optimize SLSQP).
    Maximizes expected logarithmic bankroll growth E[ln(1 + sum(f_i * R_i))] across simultaneous
    independent game outcomes under a convex joint risk constraint, allocating more capital to
    picks with superior EV / Uncertainty trade-offs.
    """
    if not candidates or bankroll_pen <= 0.0:
        return candidates

    enriched = [dict(c) for c in candidates]
    k = len(enriched)

    # Extract probabilities and decimal odds
    probs: list[float] = []
    odds: list[float] = []
    for c in enriched:
        p = float(c.get("estimated_probability") or c.get("calibrated_probability") or 0.50)
        o = float(c.get("decimal_odds_used") or c.get("decimal_odds") or 1.90)
        probs.append(float(np.clip(p, 0.02, 0.98)))
        odds.append(max(1.05, o))

    p_arr = np.asarray(probs, dtype=float)
    o_arr = np.asarray(odds, dtype=float)

    # Single-bet exact Kelly formula shortcut
    if k == 1:
        p_val = p_arr[0]
        o_val = o_arr[0]
        b_val = o_val - 1.0
        f_star = max(0.0, (p_val * (b_val + 1.0) - 1.0) / b_val)
        eff_f = min(max_individual_fraction, f_star * fractional_multiplier)
        if p_val < 0.50:
            t_cap, t_min = 1.75, 1.00
        elif p_val < 0.58:
            t_cap, t_min = 3.35, 2.00
        elif p_val < 0.65:
            t_cap, t_min = 4.75, 3.50
        else:
            t_cap, t_min = min(6.00, bankroll_pen * max_individual_fraction), 4.80
        raw_s = bankroll_pen * eff_f
        stake = round(max(t_min, min(t_cap, raw_s if raw_s > 0 else t_min)), 2)
        enriched[0]["kelly_optimal_fraction"] = round(float(eff_f), 5)
        enriched[0]["kelly_recommended_stake_pen"] = stake
        return enriched

    # Multi-bet joint state enumeration: 2^k states (fast for k <= 10)
    states = np.asarray(list(itertools.product([0, 1], repeat=k)), dtype=float)
    p_states = np.prod(states * p_arr + (1.0 - states) * (1.0 - p_arr), axis=1)

    # Net payoffs per state: states * odds - 1
    state_returns = states * o_arr - 1.0

    def objective(f: np.ndarray) -> float:
        # wealth = 1 + sum_i (f_i * R_i)
        rets = np.dot(state_returns, f)
        wealth = 1.0 + rets
        if np.any(wealth <= 1e-5):
            return 1e5 + float(np.sum(np.maximum(0.0, 1e-5 - wealth)) * 1e4)
        return -float(np.sum(p_states * np.log(wealth)))

    bounds = [(0.0, max_individual_fraction) for _ in range(k)]
    constraints = {"type": "ineq", "fun": lambda f: max_total_exposure_fraction - np.sum(f)}
    init_f = np.full(k, min(max_individual_fraction, max_total_exposure_fraction / max(1, k)))

    res = minimize(objective, init_f, method="SLSQP", bounds=bounds, constraints=constraints)

    raw_fractions = res.x if res.success else init_f
    scaled_fractions = raw_fractions * fractional_multiplier

    for i, c in enumerate(enriched):
        frac = float(scaled_fractions[i])
        p_c = p_arr[i]
        if p_c < 0.50:
            tier_cap, tier_min = 1.75, 1.00
        elif p_c < 0.58:
            tier_cap, tier_min = 3.35, 2.00
        elif p_c < 0.65:
            tier_cap, tier_min = 4.75, 3.50
        else:
            tier_cap, tier_min = min(6.00, bankroll_pen * max_individual_fraction), 4.80

        raw_stake = bankroll_pen * frac
        stake = round(max(tier_min, min(tier_cap, raw_stake if raw_stake > 0 else tier_min)), 2)
        c["kelly_optimal_fraction"] = round(frac, 5)
        c["kelly_recommended_stake_pen"] = stake

    return enriched
