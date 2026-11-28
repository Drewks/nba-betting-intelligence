"""
V9 Phase 3: Stale Line Hunter & Latency Arbitrage Engine (src/ingestion/stale_line_hunter.py).
Identifies market latency lag, stale lines, and surebet arbitrage
between global sharp books and Peruvian retail bookmakers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import numpy as np


class StaleLineHunter:
    """
    Identifies market latency lag, stale lines, and surebet arbitrage
    between global sharp books and Peruvian retail bookmakers.
    """

    def __init__(
        self,
        min_steam_delta: float = 0.035,
        min_clv_pct: float = 3.0,
        min_arb_margin_pct: float = 1.0,
    ) -> None:
        self.min_steam_delta = min_steam_delta
        self.min_clv_pct = min_clv_pct
        self.min_arb_margin_pct = min_arb_margin_pct

    def detect_stale_line_opportunity(
        self,
        game_id: str,
        matchday_date: str,
        market: str,
        selection: str,
        sharp_provider: str,
        sharp_fair_prob: float,
        sharp_current_odds: float,
        retail_provider: str,
        retail_offered_odds: float,
        sharp_opening_odds: float | None = None,
        retail_line_value: float | None = None,
        sharp_line_value: float | None = None,
        bankroll_pen: float = 100.0,
    ) -> dict[str, Any] | None:
        """
        Detects if a Peruvian retail bookmaker has lagged behind a sharp line move,
        presenting an immediate positive Closing Line Value (+CLV) opportunity.
        """
        p_sharp = float(np.clip(sharp_fair_prob, 0.05, 0.95))
        r_odds = float(retail_offered_odds)
        if r_odds <= 1.01:
            return None

        p_retail_gross = 1.0 / r_odds

        if sharp_opening_odds and sharp_opening_odds > 1.0:
            p_open = 1.0 / sharp_opening_odds
            steam_delta = (1.0 / sharp_current_odds) - p_open
        else:
            steam_delta = 0.0

        expected_clv_pct = round(((p_sharp / p_retail_gross) - 1.0) * 100.0, 2)
        ev_unit = (p_sharp * r_odds) - 1.0
        ev_pct = round(ev_unit * 100.0, 2)

        line_gap = 0.0
        if retail_line_value is not None and sharp_line_value is not None:
            line_gap = round(float(sharp_line_value) - float(retail_line_value), 1)

        is_stale = (expected_clv_pct >= self.min_clv_pct) and (ev_pct >= 2.5)

        if not is_stale and abs(line_gap) < 1.5:
            return None

        b = r_odds - 1.0
        f_star = max(0.0, (p_sharp * (b + 1.0) - 1.0) / max(0.05, b))
        eff_f = min(0.05, f_star * 0.40)
        stake_pen = round(max(1.00, min(5.00, bankroll_pen * eff_f)), 2) if eff_f > 0 else 1.00

        rationale = (
            f"[LÍNEA DESFASADA / STALE LINE] {retail_provider} mantiene cuota {r_odds:.2f} en {selection} "
            f"mientras {sharp_provider} ajustó a cuota justa {1.0 / p_sharp:.2f} (Steam: {steam_delta * 100:+.1f}%). "
            f"CLV Esperado: +{expected_clv_pct:.1f}% | EV: {ev_pct:+.1f}%. Stake Sugerido: S/ {stake_pen:.2f} PEN."
        )

        return {
            "type": "STALE_LINE_ARBITRAGE",
            "game_id": game_id,
            "matchday_date": matchday_date,
            "market": market,
            "selection": selection,
            "sharp_provider": sharp_provider,
            "retail_provider": retail_provider,
            "retail_offered_odds": r_odds,
            "sharp_fair_odds": round(1.0 / p_sharp, 2),
            "sharp_fair_prob": round(p_sharp, 4),
            "steam_delta": round(steam_delta, 4),
            "line_gap": line_gap,
            "expected_clv_pct": expected_clv_pct,
            "ev_pct": ev_pct,
            "kelly_stake_pen": stake_pen,
            "rationale": rationale,
            "detected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def identify_stale_lines(
        self,
        game_id: str,
        matchday_date: str,
        sharp_line: dict[str, Any],
        retail_lines: list[dict[str, Any]],
        bankroll_pen: float = 100.0,
    ) -> list[dict[str, Any]]:
        """
        High-level batch comparator identifying all retail lines lagging behind a sharp line.
        """
        stale_opportunities: list[dict[str, Any]] = []
        sharp_odds = float(sharp_line.get("decimal_odds") or 0.0)
        if sharp_odds <= 1.0:
            return stale_opportunities

        p_sharp = 1.0 / sharp_odds
        market = str(sharp_line.get("market", "moneyline"))
        selection = str(sharp_line.get("selection", "HOME"))
        sharp_book = str(sharp_line.get("bookmaker", "Pinnacle"))

        for r_line in retail_lines:
            r_book = str(r_line.get("bookmaker", "Retail"))
            r_odds = float(r_line.get("decimal_odds") or 0.0)
            if r_odds <= 1.0:
                continue
            if r_odds <= sharp_odds:
                continue

            expected_clv = round(((r_odds / sharp_odds) - 1.0) * 100.0, 2)
            if expected_clv >= self.min_clv_pct:
                b = r_odds - 1.0
                f_star = max(0.0, (p_sharp * (b + 1.0) - 1.0) / max(0.05, b))
                eff_f = min(0.05, f_star * 0.45)
                stake = round(max(1.00, min(5.00, bankroll_pen * eff_f)), 2)

                stale_opportunities.append({
                    "game_id": game_id,
                    "matchday_date": matchday_date,
                    "market": market,
                    "selection": selection,
                    "sharp_bookmaker": sharp_book,
                    "sharp_odds": sharp_odds,
                    "retail_bookmaker": r_book,
                    "retail_odds": r_odds,
                    "expected_clv_pct": expected_clv,
                    "is_stale_line": True,
                    "kelly_stake_pen": stake,
                    "detected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

        return sorted(stale_opportunities, key=lambda x: x["expected_clv_pct"], reverse=True)

    def compute_surebet_arbitrage(
        self,
        game_id: str,
        matchday_date: str,
        market: str = "moneyline",
        home_book: str | None = None,
        home_odds: float | None = None,
        away_book: str | None = None,
        away_odds: float | None = None,
        book_a: str | None = None,
        odds_a: float | None = None,
        selection_a: str = "HOME",
        book_b: str | None = None,
        odds_b: float | None = None,
        selection_b: str = "AWAY",
        total_stake_pen: float | None = None,
        total_investment_pen: float = 100.0,
    ) -> dict[str, Any] | None:
        """
        Calculates risk-free cross-bookmaker surebet arbitrage between two Peruvian sportsbooks
        and derives exact stake distribution in Soles (S/. PEN).
        Supports both (home_book, away_book) and (book_a, book_b) signatures.
        """
        b_a = book_a or home_book or "Book A"
        o_a = float(odds_a if odds_a is not None else (home_odds or 1.0))
        b_b = book_b or away_book or "Book B"
        o_b = float(odds_b if odds_b is not None else (away_odds or 1.0))
        tot_pen = float(total_stake_pen if total_stake_pen is not None else total_investment_pen)

        if o_a <= 1.0 or o_b <= 1.0:
            return None

        inv_sum = (1.0 / o_a) + (1.0 / o_b)
        is_arb = inv_sum < 1.0
        arb_margin_pct = round((1.0 - inv_sum) * 100.0, 2) if is_arb else round((1.0 - inv_sum) * 100.0, 2)

        stake_a = round(tot_pen / (o_a * inv_sum), 2)
        stake_b = round(tot_pen - stake_a, 2)

        payout_a = round(stake_a * o_a, 2)
        payout_b = round(stake_b * o_b, 2)
        guaranteed_pnl = round(min(payout_a, payout_b) - tot_pen, 2)

        return {
            "type": "SUREBET_ARBITRAGE",
            "game_id": game_id,
            "matchday_date": matchday_date,
            "market": market,
            "is_arbitrage": is_arb,
            "book_a": b_a,
            "selection_a": selection_a,
            "odds_a": o_a,
            "stake_a_pen": stake_a,
            "payout_a_pen": payout_a,
            "book_b": b_b,
            "selection_b": selection_b,
            "odds_b": o_b,
            "stake_b_pen": stake_b,
            "payout_b_pen": payout_b,
            "total_staked_pen": tot_pen,
            "arb_margin_pct": arb_margin_pct,
            "arbitrage_margin_pct": arb_margin_pct,
            "guaranteed_net_profit_pen": guaranteed_pnl,
            "guaranteed_pnl_pen": guaranteed_pnl,
            "roi_pct": round((guaranteed_pnl / tot_pen) * 100.0, 2),
            "rationale": (
                f"[SUREBET ARBITRAJE LIBRE DE RIESGO] {b_a} ({o_a:.2f}) vs {b_b} ({o_b:.2f}). "
                f"Inversión S/ {tot_pen:.2f} PEN: S/ {stake_a:.2f} a {b_a} y S/ {stake_b:.2f} a {b_b}. "
                f"Retorno Seguro: S/ {guaranteed_pnl:+.2f} PEN (Margen: {arb_margin_pct:.2f}%)."
            ),
        }
