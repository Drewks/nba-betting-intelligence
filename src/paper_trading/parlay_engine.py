"""
Dedicated Paper Trading Engine for Multi-Leg Parlays and Same-Game Parlays (SGP) (`src/paper_trading/parlay_engine.py`).

Manages the isolated S/50.00 PEN virtual sub-bankroll dedicated to compound alpha strategies:
  1. Correlated SGPs (modeled via Gaussian/Vine Copulas with joint edge > 6%).
  2. High-Probability Lock Builder Parlays (individual legs p >= 0.70).

Guarantees complete isolation from the audited Phase 0 main bankroll (S/100 PEN).
All transactions are logged to `parlay_bankroll_ledger` and `parlay_bets` with immutable triggers.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any
import uuid

from src.storage.db import DatabaseManager

logger = logging.getLogger("ParlayEngine")


class ParlayRiskLimitError(ValueError):
    """Raised when a parlay bet exceeds sub-bankroll exposure or risk limits."""


class ParlayTradingEngine:
    """
    Independent ledger and execution engine for parlays and SGP.
    Operates on parlay_bets and parlay_bankroll_ledger.
    """

    def __init__(
        self,
        db: DatabaseManager,
        initial_bankroll_pen: float = 50.00,
        max_stake_pen: float = 5.00,
        min_stake_pen: float = 0.50,
        kelly_fraction: float = 0.40,
        max_parlays_per_matchday: int = 2,
        min_compound_ev_pct: float = 6.0,
        max_stake_bankroll_fraction: float = 0.10,
    ) -> None:
        self.db = db
        self.initial_bankroll_pen = float(initial_bankroll_pen)
        self.max_stake_pen = float(max_stake_pen)
        self.min_stake_pen = float(min_stake_pen)
        self.kelly_fraction = float(kelly_fraction)
        self.max_parlays_per_matchday = int(max_parlays_per_matchday)
        self.min_compound_ev_pct = float(min_compound_ev_pct)
        self.max_stake_bankroll_fraction = float(max_stake_bankroll_fraction)
        self._ensure_initial_ledger()

    def _ensure_initial_ledger(self) -> None:
        existing = self.db.fetch_one("SELECT COUNT(*) AS cnt FROM parlay_bankroll_ledger")
        if not existing or existing["cnt"] == 0:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.db.execute_insert(
                """
                INSERT INTO parlay_bankroll_ledger (
                    timestamp, event_type, reference_parlay_id, amount_delta_pen,
                    settled_bankroll_pen, pending_exposure_pen, available_balance_pen
                ) VALUES (?, 'INITIAL_VIRTUAL_BANKROLL', NULL, ?, ?, 0.0, ?)
                """,
                (now_str, self.initial_bankroll_pen, self.initial_bankroll_pen, self.initial_bankroll_pen),
            )

    def get_bankroll_state(self) -> dict[str, float]:
        """
        Computes current sub-bankroll state directly from immutable parlay_bets history.
        """
        settled_rows = self.db.fetch_all(
            "SELECT net_profit_pen FROM parlay_bets WHERE status IN ('WON', 'LOST', 'PUSH', 'VOID')"
        )
        pending_rows = self.db.fetch_all(
            "SELECT stake_pen FROM parlay_bets WHERE status = 'PENDING'"
        )

        cumulative_profit = round(sum(float(r["net_profit_pen"] or 0.0) for r in settled_rows), 2)
        settled_bankroll = round(self.initial_bankroll_pen + cumulative_profit, 2)
        pending_exposure = round(sum(float(r["stake_pen"]) for r in pending_rows), 2)
        available_balance = round(settled_bankroll - pending_exposure, 2)

        total_settled_staked = sum(float(r.get("stake_pen") or 0.0) for r in self.db.fetch_all(
            "SELECT stake_pen FROM parlay_bets WHERE status IN ('WON', 'LOST', 'PUSH', 'VOID')"
        ))
        roi_pct = round((cumulative_profit / total_settled_staked * 100.0), 2) if total_settled_staked > 0 else 0.0

        return {
            "initial_bankroll_pen": self.initial_bankroll_pen,
            "settled_bankroll_pen": settled_bankroll,
            "pending_exposure_pen": pending_exposure,
            "available_balance_pen": available_balance,
            "cumulative_net_profit_pen": cumulative_profit,
            "roi_pct": roi_pct,
            "settled_parlays_count": float(len(settled_rows)),
            "pending_parlays_count": float(len(pending_rows)),
        }

    def compute_dynamic_stake(self, joint_prob: float, compound_odds: float) -> float:
        """
        Computes fractional Kelly stake with dynamic conviction sizing for multi-leg parlays.
        Returns 0.0 if EV <= 0 or stake < min_stake_pen.
        """
        state = self.get_bankroll_state()
        curr_bankroll = state["available_balance_pen"]
        if curr_bankroll <= 0.0:
            return 0.0

        b = float(compound_odds) - 1.0
        if b <= 0.0:
            return 0.0

        p = min(max(float(joint_prob), 0.0), 1.0)
        # Full Kelly f* = (p * b - (1 - p)) / b = (p * O - 1) / (O - 1)
        full_kelly = (p * float(compound_odds) - 1.0) / b
        if full_kelly <= 0.0:
            return 0.0

        target_fraction = full_kelly * self.kelly_fraction
        capped_fraction = min(target_fraction, self.max_stake_bankroll_fraction)
        raw_stake = curr_bankroll * capped_fraction
        final_stake = round(min(raw_stake, self.max_stake_pen), 2)

        return final_stake if final_stake >= self.min_stake_pen else 0.0

    def record_parlay_bet(self, parlay_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Places a multi-leg parlay or SGP bet in the sub-bankroll with PENDING status.
        Logs to parlay_bets and parlay_bankroll_ledger (BET_RESERVED).
        """
        state = self.get_bankroll_state()
        m_date = str(parlay_dict["matchday_date"])
        strategy_type = str(parlay_dict.get("strategy_type", "SGP_COPULA"))
        legs = list(parlay_dict["legs"])
        num_legs = len(legs)
        if num_legs < 2:
            raise ParlayRiskLimitError(f"Parlays must have at least 2 legs; got {num_legs}.")

        compound_odds = round(float(parlay_dict["compound_odds"]), 4)
        joint_prob = round(float(parlay_dict["joint_prob"]), 4)
        compound_ev_pct = round(float(parlay_dict.get("compound_ev_pct") or ((joint_prob * compound_odds - 1.0) * 100.0)), 2)

        if compound_ev_pct < self.min_compound_ev_pct:
            raise ParlayRiskLimitError(
                f"Compound EV {compound_ev_pct:.2f}% is below sub-bankroll threshold {self.min_compound_ev_pct:.2f}%."
            )

        # Daily matchday cap
        existing_day = self.db.fetch_one(
            "SELECT COUNT(*) AS c FROM parlay_bets WHERE matchday_date = ?", (m_date,)
        )
        if existing_day and int(existing_day["c"]) >= self.max_parlays_per_matchday:
            raise ParlayRiskLimitError(
                f"Matchday parlay cap of {self.max_parlays_per_matchday} reached for {m_date}."
            )

        # Sizing
        proposed_stake = parlay_dict.get("stake_pen")
        if proposed_stake is not None:
            stake = round(float(proposed_stake), 2)
        else:
            stake = self.compute_dynamic_stake(joint_prob, compound_odds)

        if stake < self.min_stake_pen:
            raise ParlayRiskLimitError(
                f"Computed stake S/{stake:.2f} is below minimum S/{self.min_stake_pen:.2f}."
            )
        if stake > self.max_stake_pen:
            raise ParlayRiskLimitError(
                f"Stake S/{stake:.2f} exceeds sub-bankroll cap S/{self.max_stake_pen:.2f}."
            )
        if stake > state["available_balance_pen"]:
            raise ParlayRiskLimitError(
                f"Insufficient available sub-bankroll: S/{state['available_balance_pen']:.2f} available, S/{stake:.2f} requested."
            )

        parlay_id = parlay_dict.get("parlay_id") or f"PARLAY_{uuid.uuid4().hex[:10].upper()}"
        emitted_at = parlay_dict.get("emitted_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Atomic insert
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO parlay_bets (
                    parlay_id, matchday_date, strategy_type, legs_json, num_legs,
                    compound_odds, joint_prob, compound_ev_pct, stake_pen, emitted_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    parlay_id,
                    m_date,
                    strategy_type,
                    json.dumps(legs, ensure_ascii=False),
                    num_legs,
                    compound_odds,
                    joint_prob,
                    compound_ev_pct,
                    stake,
                    emitted_at,
                ),
            )
            # Log ledger reservation
            new_exposure = round(state["pending_exposure_pen"] + stake, 2)
            new_avail = round(state["settled_bankroll_pen"] - new_exposure, 2)
            conn.execute(
                """
                INSERT INTO parlay_bankroll_ledger (
                    timestamp, event_type, reference_parlay_id, amount_delta_pen,
                    settled_bankroll_pen, pending_exposure_pen, available_balance_pen
                ) VALUES (?, 'BET_RESERVED', ?, ?, ?, ?, ?)
                """,
                (
                    emitted_at,
                    parlay_id,
                    -stake,
                    state["settled_bankroll_pen"],
                    new_exposure,
                    new_avail,
                ),
            )

        logger.info(
            "Recorded Parlay Bet %s (%s, %d legs, odds %.3f, EV %.1f%%, stake S/%.2f)",
            parlay_id, strategy_type, num_legs, compound_odds, compound_ev_pct, stake
        )
        return {
            "parlay_id": parlay_id,
            "status": "PLACED",
            "compound_odds": compound_odds,
            "joint_prob": joint_prob,
            "compound_ev_pct": compound_ev_pct,
            "stake_pen": stake,
            "num_legs": num_legs,
            "legs": legs,
        }

    def settle_parlay_bet(
        self,
        parlay_id: str,
        leg_results: list[dict[str, Any]],
        settled_at: str | None = None,
    ) -> dict[str, Any]:
        """
        Settles a parlay bet against leg outcomes.
        leg_results: list of dicts with {'status': 'WON'|'LOST'|'PUSH'|'VOID', 'summary': str} matching leg order.
        """
        parlay = self.db.fetch_one("SELECT * FROM parlay_bets WHERE parlay_id = ?", (parlay_id,))
        if not parlay:
            raise ValueError(f"Parlay {parlay_id} not found.")
        if parlay["status"] != "PENDING":
            raise ValueError(f"Parlay {parlay_id} already settled with status {parlay['status']}.")

        stake = float(parlay["stake_pen"])
        orig_odds = float(parlay["compound_odds"])
        legs = json.loads(parlay["legs_json"])
        if len(leg_results) != len(legs):
            raise ValueError(f"Expected {len(legs)} leg results; got {len(leg_results)}.")

        has_loss = any(r.get("status") == "LOST" for r in leg_results)
        all_push = all(r.get("status") in ("PUSH", "VOID") for r in leg_results)

        now_str = settled_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if has_loss:
            final_status = "LOST"
            net_profit = round(-stake, 2)
            summary = "LOST: " + "; ".join(f"Leg {i+1} {r.get('status')}" for i, r in enumerate(leg_results))
        elif all_push:
            final_status = "VOID"
            net_profit = 0.0
            summary = "VOID: all legs pushed/voided"
        else:
            # Check for partial pushes
            active_legs_odds: list[float] = []
            for leg, res in zip(legs, leg_results, strict=False):
                st = res.get("status")
                if st == "WON":
                    leg_odd = float(leg.get("decimal_odds") or leg.get("odds") or 1.0)
                    active_legs_odds.append(leg_odd)
            if active_legs_odds:
                # Recalculate compound odds
                comp_mult = 1.0
                for o in active_legs_odds:
                    comp_mult *= o
                effective_odds = round(comp_mult, 4) if len(active_legs_odds) < len(legs) else orig_odds
                final_status = "WON"
                net_profit = round(stake * (effective_odds - 1.0), 2)
                summary = f"WON: compound odds {effective_odds:.3f}"
            else:
                final_status = "VOID"
                net_profit = 0.0
                summary = "VOID: no winning legs"

        state = self.get_bankroll_state()
        new_settled_bankroll = round(state["settled_bankroll_pen"] + net_profit, 2)
        new_pending_exposure = round(max(0.0, state["pending_exposure_pen"] - stake), 2)
        new_available = round(new_settled_bankroll - new_pending_exposure, 2)

        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE parlay_bets
                SET status = ?, net_profit_pen = ?, bankroll_after_pen = ?,
                    actual_result_summary = ?, settled_at = ?
                WHERE parlay_id = ?
                """,
                (final_status, net_profit, new_settled_bankroll, summary, now_str, parlay_id),
            )
            conn.execute(
                """
                INSERT INTO parlay_bankroll_ledger (
                    timestamp, event_type, reference_parlay_id, amount_delta_pen,
                    settled_bankroll_pen, pending_exposure_pen, available_balance_pen
                ) VALUES (?, 'BET_SETTLED', ?, ?, ?, ?, ?)
                """,
                (
                    now_str,
                    parlay_id,
                    net_profit,
                    new_settled_bankroll,
                    new_pending_exposure,
                    new_available,
                ),
            )

        logger.info(
            "Settled Parlay Bet %s -> %s (Net: S/%.2f, Bankroll: S/%.2f)",
            parlay_id, final_status, net_profit, new_settled_bankroll
        )
        return {
            "parlay_id": parlay_id,
            "status": final_status,
            "net_profit_pen": net_profit,
            "bankroll_after_pen": new_settled_bankroll,
            "summary": summary,
            "settled_at": now_str,
        }

    def get_active_parlays(self, matchday_date: str | None = None) -> list[dict[str, Any]]:
        if matchday_date:
            return self.db.fetch_all(
                "SELECT * FROM parlay_bets WHERE status = 'PENDING' AND matchday_date = ? ORDER BY emitted_at ASC",
                (matchday_date,),
            )
        return self.db.fetch_all(
            "SELECT * FROM parlay_bets WHERE status = 'PENDING' ORDER BY emitted_at ASC"
        )

    def get_settled_parlays(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            "SELECT * FROM parlay_bets WHERE status IN ('WON', 'LOST', 'PUSH', 'VOID') ORDER BY settled_at DESC LIMIT ?",
            (limit,),
        )
