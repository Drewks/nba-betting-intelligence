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

from typing import Any

import numpy as np

from src.prediction.ev_calculator import calculate_implied_prob_gross, devig_shin

OUTLIER_THRESHOLD_PCT = 15.0


def _key(row: dict[str, Any]) -> tuple[str, str, str, float | None]:
    lv = row.get("line_value")
    return (str(row["game_id"]), str(row["market"]), str(row["selection"]), None if lv is None else float(lv))


def index_closing_rows(closing_rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, float | None], list[dict[str, Any]]]:
    out: dict[tuple[str, str, str, float | None], list[dict[str, Any]]] = {}
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


def compute_bet_clv(
    bet: dict[str, Any],
    closing_index: dict[tuple[str, str, str, float | None], list[dict[str, Any]]],
    bet_provider: str | None = None,
) -> dict[str, Any] | None:
    close = _pick_close(closing_index.get(_key(bet), []), bet_provider)
    if close is None:
        return None
    close_odds = float(close["decimal_odds"])
    counter = close.get("counterpart_decimal_odds")
    if counter is not None and float(counter) > 1.0:
        p_close_fair, _, _ = devig_shin(close_odds, float(counter))
        method = "shin_devig"
    else:
        p_close_fair = calculate_implied_prob_gross(close_odds)
        method = "gross_implied"
    clv_ev_pct = 100.0 * (float(bet["decimal_odds"]) * float(p_close_fair) - 1.0)
    return {
        "bet_id": bet.get("bet_id"),
        "closing_provider": close.get("provider"),
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
