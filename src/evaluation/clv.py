"""
Closing Line Value (CLV) measured in probability space against the de-vigged closing line.

Definition (per settled bet):
    p_close_fair = de-vigged probability of the bet's selection at the closing line (Shin method when
                   the two-way closing pair is available; otherwise the gross 1/O).
    clv_ev_pct   = 100 * (bet_decimal_odds * p_close_fair - 1)
i.e. the expected value of the bet if the closing fair price were the truth. Positive = we got a price
better than the fair close.

Closing reference priority: an observed Pinnacle close > the bet's own provider close > any observed close.
Values with |clv_ev_pct| > OUTLIER_THRESHOLD_PCT are treated as data errors (mismatched lines/books):
they are excluded from the mean and counted, never silently averaged in.
"""

from __future__ import annotations

from statistics import NormalDist
from typing import Any

import numpy as np

from src.prediction.ev_calculator import calculate_implied_prob_gross, devig_shin

OUTLIER_THRESHOLD_PCT = 15.0
TOTALS_SCORE_STD = 18.0
SPREAD_MARGIN_STD = 12.0
_STD_NORMAL = NormalDist(0.0, 1.0)


def _key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row["game_id"]), str(row["market"]), str(row["selection"]).upper())


def index_closing_rows(closing_rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in closing_rows:
        out.setdefault(_key(r), []).append(r)
    return out


def _pick_close(candidates: list[dict[str, Any]], bet_provider: str | None) -> dict[str, Any] | None:
    if not candidates:
        return None
    ordered = sorted(candidates, key=lambda r: str(r.get("captured_at") or ""), reverse=True)
    for r in ordered:
        if "pinnacle" in str(r.get("provider") or "").lower():
            return r
    if bet_provider:
        for r in ordered:
            if str(r.get("provider") or "") == bet_provider:
                return r
    return ordered[0]


def _shift_prob_across_lines(
    p_close_at_close_line: float,
    market: str,
    selection: str,
    bet_line: float | None,
    close_line: float | None,
) -> tuple[float, float]:
    """
    Translates a de-vigged closing probability at `close_line` to the bet's `bet_line` when a
    totals or spread line moved between bet placement and tip-off.
    Returns `(p_fair_at_bet_line, favorable_line_delta_pts)`.
    """
    if bet_line is None or close_line is None or abs(bet_line - close_line) < 1e-9:
        return p_close_at_close_line, 0.0
    if market == "total_points":
        sigma = TOTALS_SCORE_STD
        favorable_delta = (close_line - bet_line) if selection.upper() == "OVER" else (bet_line - close_line)
    elif market == "spread":
        sigma = SPREAD_MARGIN_STD
        # For both HOME and AWAY spreads (winning condition: side_margin + line > 0), a higher bet_line favors the bettor.
        favorable_delta = bet_line - close_line
    else:
        return p_close_at_close_line, 0.0
    p_clamped = min(max(float(p_close_at_close_line), 1e-4), 1.0 - 1e-4)
    z_bet = _STD_NORMAL.inv_cdf(p_clamped) + (favorable_delta / sigma)
    return float(_STD_NORMAL.cdf(z_bet)), round(favorable_delta, 2)


def compute_bet_clv(
    bet: dict[str, Any],
    closing_index: dict[tuple[str, str, str], list[dict[str, Any]]],
    bet_provider: str | None = None,
) -> dict[str, Any] | None:
    close = _pick_close(closing_index.get(_key(bet), []), bet_provider)
    if close is None:
        return None
    close_odds = float(close["decimal_odds"])
    counter = close.get("counterpart_decimal_odds")
    if counter is not None and float(counter) > 1.0:
        p_close_raw, _, _ = devig_shin(close_odds, float(counter))
        method = "shin_devig"
    else:
        p_close_raw = calculate_implied_prob_gross(close_odds)
        method = "gross_implied"

    raw_bet_lv = bet.get("line_value")
    raw_close_lv = close.get("line_value")
    bet_lv = float(raw_bet_lv) if raw_bet_lv is not None else None
    close_lv = float(raw_close_lv) if raw_close_lv is not None else None
    p_close_fair, line_delta_pts = _shift_prob_across_lines(
        float(p_close_raw),
        str(bet.get("market") or ""),
        str(bet.get("selection") or ""),
        bet_lv,
        close_lv,
    )
    if abs(line_delta_pts) > 0.0:
        method = f"{method}_line_adjusted"

    clv_ev_pct = 100.0 * (float(bet["decimal_odds"]) * float(p_close_fair) - 1.0)
    return {
        "bet_id": bet.get("bet_id"),
        "closing_provider": close.get("provider"),
        "closing_line_value": close_lv,
        "line_delta_pts": line_delta_pts,
        "p_close_fair": round(float(p_close_fair), 6),
        "clv_ev_pct": round(clv_ev_pct, 4),
        "method": method,
        "is_outlier": abs(clv_ev_pct) > OUTLIER_THRESHOLD_PCT,
    }


def summarize_clv(
    settled_bets: list[dict[str, Any]],
    closing_rows: list[dict[str, Any]],
    bet_providers: dict[str, str] | None = None,
) -> dict[str, Any]:
    closing_index = index_closing_rows(closing_rows)
    providers = bet_providers or {}
    per_bet = []
    for b in settled_bets:
        rec = compute_bet_clv(b, closing_index, providers.get(str(b.get("prediction_id"))))
        if rec is not None:
            per_bet.append(rec)
    valid = [r["clv_ev_pct"] for r in per_bet if not r["is_outlier"]]
    return {
        "mean_clv_pct": round(float(np.mean(valid)), 4) if valid else None,
        "clv_beat_close_rate": round(float(np.mean([v > 0 for v in valid])), 4) if valid else None,
        "clv_sample_size": len(valid),
        "clv_outliers_excluded": sum(1 for r in per_bet if r["is_outlier"]),
        "clv_bets_without_close": len(settled_bets) - len(per_bet),
        "clv_definition": "100*(bet_odds * p_close_fair - 1), p_close_fair = Shin de-vigged closing (Pinnacle preferred)",
        "per_bet": per_bet,
    }


def get_recent_clv_governor_factor(
    db: Any,
    risk_config: Any = None,
    scope_predicate_sql: str = "b.game_id NOT LIKE 'SYN%'",
    lookback: int | None = None,
) -> tuple[float, float | None]:
    """
    Active Risk Governor based on Closing Line Value (CLV).
    Returns `(scaling_factor, mean_clv_pct)`.
    """
    gov_cfg = getattr(risk_config, "clv_governor", None) if risk_config is not None else None
    effective_lookback = lookback if lookback is not None else (gov_cfg.lookback_bets if gov_cfg else 25)
    min_sample = gov_cfg.min_sample_size if gov_cfg else 4

    bets = db.fetch_all(
        f"""
        SELECT b.bet_id, b.game_id, b.market, b.selection, b.line_value, b.decimal_odds,
               p.odds_provider
        FROM v_observed_simulated_bets b
        LEFT JOIN predictions p ON b.prediction_id = p.prediction_id
        WHERE b.status IN ('WON', 'LOST', 'PUSH')
          AND {scope_predicate_sql}
        ORDER BY b.settled_at DESC
        LIMIT ?
        """,
        (effective_lookback,),
    )
    if not bets:
        return 1.0, None
    closing_rows = db.fetch_all(
        """
        SELECT game_id, market, selection, line_value, decimal_odds, counterpart_decimal_odds, provider, captured_at
        FROM v_observed_odds_snapshots
        WHERE is_closing_line = 1
        """
    )
    closing_index = index_closing_rows(closing_rows)
    clvs: list[float] = []
    for b in bets:
        rec = compute_bet_clv(b, closing_index, b.get("odds_provider"))
        if rec is not None and not rec["is_outlier"]:
            clvs.append(float(rec["clv_ev_pct"]))
    if len(clvs) < min_sample:
        return 1.0, None
    mean_clv = float(np.mean(clvs))
    if gov_cfg:
        if mean_clv < gov_cfg.severe_negative_threshold:
            factor = gov_cfg.severe_negative_factor
        elif mean_clv < gov_cfg.moderate_negative_threshold:
            factor = gov_cfg.moderate_negative_factor
        elif mean_clv >= gov_cfg.positive_alpha_threshold:
            factor = gov_cfg.positive_alpha_factor
        else:
            factor = gov_cfg.neutral_factor
    else:
        if mean_clv < -2.0:
            factor = 0.50
        elif mean_clv < 0.0:
            factor = 0.75
        elif mean_clv >= 2.0:
            factor = 1.10
        else:
            factor = 1.00
    return factor, round(mean_clv, 2)
