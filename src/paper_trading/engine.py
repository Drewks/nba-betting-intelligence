"""
Paper Trading Engine (Sections 7 & 8):
- Manages virtual bankroll of S/100.00 PEN (strictly simulation, zero real betting endpoints)
- Enforces stake base S/1.00, max stake S/1.00, max 3 selections per matchday
- Prohibits parlays, Martingale, doubling after loss, loans, or negative balance
- Logs NO_BET decisions when EV or validation gates are not met
- Settles WON, LOST, PUSH, VOID bets with double-settlement prevention and full reconciliation
"""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Any
import uuid

from src.storage.db import DatabaseManager
from src.validation.validator import (
    DataValidationError,
    TemporalLeakageError,
    parse_iso_utc,
)


class RiskLimitError(ValueError):
    """Raised when a proposed bet violates conservative risk or staking rules."""


class DoubleSettlementError(RuntimeError):
    """Raised when attempting to settle a bet that has already been settled."""


class PaperTradingEngine:
    """Manages virtual S/100.00 PEN bankroll, selection filtering, and immutable settlement."""

    def __init__(
        self,
        db: DatabaseManager,
        initial_bankroll_pen: float = 100.00,
        base_stake_pen: float = 1.00,
        max_stake_pen: float = 1.00,
        max_selections_per_matchday: int = 3,
        min_ev_threshold: float = 0.05,
        dynamic_conviction_staking: bool = False,
        exclude_synthetic: bool = False,
    ) -> None:
        max_allowed = 10.00 if dynamic_conviction_staking else 1.00
        if max_stake_pen > max_allowed or base_stake_pen > max_stake_pen or base_stake_pen <= 0.0:
            raise RiskLimitError(
                f"Stake limits must satisfy 0 < base_stake <= max_stake <= S/{max_allowed:.2f} PEN."
            )
        self.db = db
        self.initial_bankroll_pen = round(float(initial_bankroll_pen), 4)
        self.base_stake_pen = round(float(base_stake_pen), 4)
        self.max_stake_pen = round(float(max_stake_pen), 4)
        self.max_selections_per_matchday = int(max_selections_per_matchday)
        self.min_ev_threshold = float(min_ev_threshold)
        self.dynamic_conviction_staking = bool(dynamic_conviction_staking)
        # When True, bankroll / metrics only count bets on REAL games (synthetic SYN_* fixtures are archived benchmarks)
        self.exclude_synthetic = bool(exclude_synthetic)
        self._ensure_initial_ledger()

    @property
    def scope_sql(self) -> str:
        """SQL predicate restricting simulated_bets to the active accounting scope."""
        return "game_id NOT LIKE 'SYN%'" if self.exclude_synthetic else "1 = 1"

    def compute_contextual_stake_pen(
        self,
        calibrated_prob: float,
        decimal_odds: float,
        ev_unit: float,
        current_bankroll_pen: float,
        uncertainty_std: float = 0.05,
        selection: str = "",
        overtime_prob: float = 0.0,
    ) -> float:
        """
        Calculates contextual Kelly-Conviction stake (S/1.00 to S/6.00 PEN on ~S/100 bankroll):
        - Low probability / Underdog (<50%): S/1.00 - S/1.75 PEN
        - Medium probability (50% - 58%): S/2.00 - S/3.25 PEN
        - High probability (58% - 65%): S/3.50 - S/4.75 PEN
        - Maximum conviction (>=65%): S/4.80 - S/6.00 PEN
        Also integrates 10,000-Simulation Monte Carlo Overtime Risk (protects UNDERs when OT risk >= 6.8%)
        and Conformal Model Agreement bonus.
        """
        p = max(0.01, min(0.99, float(calibrated_prob)))
        b = max(0.05, float(decimal_odds) - 1.0)
        f_kelly = max(0.0, (p * (b + 1.0) - 1.0) / b)

        # Human-like probability conviction tiers
        if p < 0.50:
            # Underdog / lower win rate -> protect capital with small stake
            tier_base = 1.00 + max(0.0, (p - 0.35) / 0.15) * 0.55
            kelly_bonus = min(0.25, f_kelly * 1.2)
        elif p < 0.58:
            # Medium probability -> moderate contextual stake
            tier_base = 2.00 + ((p - 0.50) / 0.08) * 0.95
            kelly_bonus = min(0.35, f_kelly * 1.5)
        elif p < 0.65:
            # High probability -> strong conviction stake
            tier_base = 3.50 + ((p - 0.58) / 0.07) * 0.95
            kelly_bonus = min(0.40, f_kelly * 1.8)
        else:
            # Star Pick (>=65% win probability) -> maximum conviction stake
            tier_base = 4.80 + min(1.0, (p - 0.65) / 0.10) * 0.85
            kelly_bonus = min(0.45, f_kelly * 2.0)

        raw_stake = tier_base + kelly_bonus

        # Extra caution on high-variance longshots (odds > 2.50)
        if decimal_odds > 2.50:
            raw_stake = min(raw_stake, 1.65)

        # Monte Carlo Overtime Guard: if betting UNDER in a game with high OT probability (>= 6.8%), trim stake 15%
        if str(selection).upper() == "UNDER" and float(overtime_prob) >= 0.068:
            raw_stake *= 0.85

        # Conformal Agreement / Uncertainty adjustment
        if uncertainty_std > 0.08:
            raw_stake *= 0.82
        elif uncertainty_std <= 0.045:
            raw_stake *= 1.08

        # Scale proportionally with current settled bankroll (relative to initial S/100)
        bankroll_scale = max(0.80, min(1.50, float(current_bankroll_pen) / max(1.0, self.initial_bankroll_pen)))
        scaled_stake = raw_stake * bankroll_scale

        return round(max(1.00, min(self.max_stake_pen, scaled_stake)), 2)

    def _ensure_initial_ledger(self) -> None:
        existing = self.db.fetch_one("SELECT COUNT(*) AS cnt FROM bankroll_ledger")
        if not existing or existing["cnt"] == 0:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.db.execute_insert(
                """
                INSERT INTO bankroll_ledger (
                    timestamp, event_type, reference_bet_id, amount_delta_pen,
                    settled_bankroll_pen, pending_exposure_pen, available_balance_pen
                ) VALUES (?, 'INITIAL_VIRTUAL_BANKROLL', NULL, ?, ?, 0.0, ?)
                """,
                (now_str, self.initial_bankroll_pen, self.initial_bankroll_pen, self.initial_bankroll_pen),
            )

    def get_bankroll_state(self) -> dict[str, float]:
        """
        Computes current bankroll state from immutable simulated_bets history and verifies ledger consistency.
        """
        settled_rows = self.db.fetch_all(
            f"SELECT net_profit_pen FROM simulated_bets WHERE status IN ('WON', 'LOST', 'PUSH', 'VOID') AND {self.scope_sql}"
        )
        pending_rows = self.db.fetch_all(
            f"SELECT stake_pen FROM simulated_bets WHERE status = 'PENDING' AND {self.scope_sql}"
        )

        cumulative_profit = round(sum(float(r["net_profit_pen"] or 0.0) for r in settled_rows), 4)
        settled_bankroll = round(self.initial_bankroll_pen + cumulative_profit, 4)
        pending_exposure = round(sum(float(r["stake_pen"]) for r in pending_rows), 4)
        available_balance = round(settled_bankroll - pending_exposure, 4)

        return {
            "initial_bankroll_pen": self.initial_bankroll_pen,
            "settled_bankroll_pen": settled_bankroll,
            "cumulative_net_profit_pen": cumulative_profit,
            "pending_exposure_pen": pending_exposure,
            "available_balance_pen": available_balance,
            "settled_bets_count": len(settled_rows),
            "pending_bets_count": len(pending_rows),
        }

    def evaluate_and_record_matchday_selections(
        self,
        matchday_date: str,
        candidate_predictions: list[dict[str, Any]],
        proposed_stake_pen: float | None = None,
    ) -> dict[str, Any]:
        """
        Evaluates all candidate predictions for a matchday, enforces the 3-bet daily cap,
        S/1 max stake, and EV >= threshold rule, and logs BET_PLACED or NO_BET for every candidate.
        """
        stake = self.base_stake_pen if proposed_stake_pen is None else round(float(proposed_stake_pen), 4)
        if stake <= 0.0 or stake > self.max_stake_pen:
            raise RiskLimitError(
                f"Proposed stake S/{stake:.2f} violates v1 limit (0 < stake <= S/{self.max_stake_pen:.2f}). "
                "Martingale or stake escalation is prohibited."
            )

        # Sort candidates: in dynamic conviction mode, prioritize high-probability + positive-EV winners
        if self.dynamic_conviction_staking:
            sorted_candidates = sorted(
                candidate_predictions,
                key=lambda c: (
                    float(c.get("ev_unit", -999.0))
                    * ((float(c.get("calibrated_probability") or 0.50) / 0.55) ** 2.0)
                ),
                reverse=True,
            )
        else:
            sorted_candidates = sorted(
                candidate_predictions,
                key=lambda c: float(c.get("ev_unit", -999.0)),
                reverse=True,
            )

        placed_bets: list[dict[str, Any]] = []
        no_bet_decisions: list[dict[str, Any]] = []

        existing_day_bets = self.db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM simulated_bets WHERE matchday_date = ?",
            (matchday_date,),
        )
        day_count = int(existing_day_bets["cnt"]) if existing_day_bets else 0
        selected_game_markets: set[tuple[str, str]] = set()

        for cand in sorted_candidates:
            emitted_at = cand.get("emitted_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            game_id = cand["game_id"]
            market = cand["market"]
            selection = cand["selection"]
            line_value = cand.get("line_value")
            dec_odds = float(cand.get("decimal_odds_used") or 0.0)
            cal_prob = cand.get("calibrated_probability")
            ev_unit = float(cand.get("ev_unit", -1.0))
            ev_pct = float(cand.get("ev_pct", -100.0))
            model_version_id = cand["model_version_id"]
            prediction_id = cand["prediction_id"]

            # 1. Check calibrated probability and valid odds
            if cal_prob is None or dec_odds <= 1.0:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "INVALID_ODDS_OR_PROB", "Missing calibrated probability or invalid decimal odds",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            # 2. Check EV threshold and unmodeled injury-outlier sanity cap
            if ev_unit <= self.min_ev_threshold:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "EV_BELOW_THRESHOLD",
                        f"EV {ev_pct:.2f}% <= threshold {self.min_ev_threshold * 100:.2f}%",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            if str(game_id).startswith("ESPN_") and ev_unit > 0.45:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "UNVERIFIED_INJURY_OR_LINEUP_OUTLIER",
                        f"Extreme EV ({ev_pct:.2f}%) indicates likely star injury/rest not in team-level features; skipped.",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            # 2b. Model vs sharp-market disagreement guard: a huge gap is far more likely to be
            # missing information (injuries, rest, lineup) than genuine edge.
            disagreement = cand.get("model_market_disagreement")
            max_gap = float(cand.get("max_model_market_disagreement") or 0.15)
            if disagreement is not None and abs(float(disagreement)) > max_gap:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "MODEL_MARKET_DISAGREEMENT",
                        f"Model differs from de-vigged market by {abs(float(disagreement)) * 100:.1f} pts "
                        f"(> {max_gap * 100:.0f}); likely missing information, skipped.",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            # 3. Check opposite side of same game+market in current batch
            if (game_id, market) in selected_game_markets:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "MARKET_ALREADY_SELECTED",
                        "Another selection in the same game and market was already placed",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            # 4. Check duplicate in DB
            dup = self.db.fetch_one(
                """
                SELECT bet_id FROM simulated_bets
                WHERE game_id = ? AND market = ? AND selection = ?
                  AND COALESCE(line_value, -9999) = COALESCE(?, -9999)
                """,
                (game_id, market, selection, line_value),
            )
            if dup:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "DUPLICATE_SELECTION",
                        f"Duplicate selection already recorded ({dup['bet_id']})",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            # 5. Check matchday max selections (max 3 per matchday)
            if day_count >= self.max_selections_per_matchday:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "MATCHDAY_CAP_REACHED",
                        f"Matchday cap of {self.max_selections_per_matchday} selections reached",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            # 6. Contextual Kelly-Conviction Stake (or v1 fixed stake) & Available Balance Check
            state = self.get_bankroll_state()
            if proposed_stake_pen is not None:
                bet_stake = stake
            elif self.dynamic_conviction_staking:
                bet_stake = self.compute_contextual_stake_pen(
                    calibrated_prob=float(cal_prob),
                    decimal_odds=dec_odds,
                    ev_unit=ev_unit,
                    current_bankroll_pen=state["settled_bankroll_pen"],
                    uncertainty_std=float(cand.get("uncertainty_std") or 0.05),
                    selection=selection,
                    overtime_prob=float(cand.get("overtime_prob") or 0.0),
                )
            elif dec_odds > 2.45:
                bet_stake = round(max(0.50, min(self.max_stake_pen, 1.35 / (dec_odds - 0.35))), 2)
            else:
                bet_stake = stake

            if state["available_balance_pen"] < bet_stake:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "INSUFFICIENT_VIRTUAL_BALANCE",
                        f"Available balance S/{state['available_balance_pen']:.2f} < stake S/{bet_stake:.2f}",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            # Place simulated bet
            bet_id = f"BET_{matchday_date.replace('-', '')}_{uuid.uuid4().hex[:8].upper()}"
            self.db.execute_insert(
                """
                INSERT INTO simulated_bets (
                    bet_id, prediction_id, game_id, matchday_date, market, selection,
                    line_value, decimal_odds, estimated_prob, estimated_ev, stake_pen,
                    emitted_at, model_version_id, status, net_profit_pen,
                    bankroll_after_pen, actual_result_summary, settled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', NULL, NULL, NULL, NULL)
                """,
                (
                    bet_id,
                    prediction_id,
                    game_id,
                    matchday_date,
                    market,
                    selection,
                    line_value,
                    dec_odds,
                    float(cal_prob),
                    ev_unit,
                    bet_stake,
                    emitted_at,
                    model_version_id,
                ),
            )

            new_state = self.get_bankroll_state()
            self.db.execute_insert(
                """
                INSERT INTO bankroll_ledger (
                    timestamp, event_type, reference_bet_id, amount_delta_pen,
                    settled_bankroll_pen, pending_exposure_pen, available_balance_pen
                ) VALUES (?, 'BET_RESERVED', ?, 0.0, ?, ?, ?)
                """,
                (
                    emitted_at,
                    bet_id,
                    new_state["settled_bankroll_pen"],
                    new_state["pending_exposure_pen"],
                    new_state["available_balance_pen"],
                ),
            )

            self._record_decision(
                game_id, matchday_date, market, selection, "BET_PLACED",
                "QUALIFIED_POSITIVE_EV",
                f"Placed virtual bet {bet_id} with EV {ev_pct:.2f}% and stake S/{bet_stake:.2f}",
                ev_pct, emitted_at, model_version_id
            )

            day_count += 1
            selected_game_markets.add((game_id, market))
            placed_bets.append(
                {
                    "bet_id": bet_id,
                    "prediction_id": prediction_id,
                    "game_id": game_id,
                    "matchday_date": matchday_date,
                    "market": market,
                    "selection": selection,
                    "line_value": line_value,
                    "decimal_odds": dec_odds,
                    "estimated_prob": float(cal_prob),
                    "estimated_ev": ev_unit,
                    "stake_pen": bet_stake,
                    "status": "PENDING",
                }
            )

        if not candidate_predictions:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            no_bet_decisions.append(
                self._record_decision(
                    f"MATCHDAY_{matchday_date}", matchday_date, "ALL", "NONE", "NO_BET",
                    "NO_VALID_CANDIDATES", "No games with complete validated data/odds on this matchday",
                    0.0, now_str, "none"
                )
            )

        return {
            "matchday_date": matchday_date,
            "placed_bets": placed_bets,
            "no_bet_decisions": no_bet_decisions,
            "bankroll_state": self.get_bankroll_state(),
        }

    def _record_decision(
        self,
        game_id: str,
        matchday_date: str,
        market: str,
        selection: str,
        decision_type: str,
        reason_code: str,
        reason_detail: str,
        ev_pct: float,
        emitted_at: str,
        model_version_id: str,
    ) -> dict[str, Any]:
        decision_id = f"DEC_{uuid.uuid4().hex[:10].upper()}"
        self.db.execute_insert(
            """
            INSERT INTO decision_log (
                decision_id, game_id, matchday_date, market, selection,
                decision_type, reason_code, reason_detail, ev_pct, emitted_at, model_version_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                game_id,
                matchday_date,
                market,
                selection,
                decision_type,
                reason_code,
                reason_detail,
                ev_pct,
                emitted_at,
                model_version_id,
            ),
        )
        return {
            "decision_id": decision_id,
            "game_id": game_id,
            "market": market,
            "selection": selection,
            "decision_type": decision_type,
            "reason_code": reason_code,
            "reason_detail": reason_detail,
            "ev_pct": ev_pct,
        }

    @staticmethod
    def calculate_settlement_outcome(
        market: str,
        selection: str,
        line_value: float | None,
        decimal_odds: float,
        stake_pen: float,
        game_status: str,
        home_score: int | None,
        away_score: int | None,
    ) -> tuple[str, float, str]:
        """
        Pure settlement formula (Section 8):
        - WON:  net_profit = S * (O - 1)
        - LOST: net_profit = -S
        - PUSH / VOID: net_profit = 0.0
        Returns (status, net_profit_pen, result_summary).
        """
        if game_status in ("POSTPONED", "CANCELLED"):
            return "VOID", 0.0, f"Game {game_status}"

        if game_status != "FINAL" or home_score is None or away_score is None:
            raise DataValidationError(
                f"Cannot settle bet before game is FINAL with verified scores (status={game_status})"
            )

        summary = f"HOME {home_score} - AWAY {away_score} (Total: {home_score + away_score})"

        if market == "moneyline":
            if home_score == away_score:
                return "PUSH", 0.0, summary
            home_won = home_score > away_score
            if (selection == "HOME" and home_won) or (selection == "AWAY" and not home_won):
                net_profit = round(stake_pen * (decimal_odds - 1.0), 4)
                return "WON", net_profit, summary
            return "LOST", round(-stake_pen, 4), summary

        if market == "total_points":
            if line_value is None:
                raise DataValidationError("total_points settlement requires line_value")
            total_pts = float(home_score + away_score)
            if abs(total_pts - float(line_value)) < 1e-6:
                return "PUSH", 0.0, summary
            over_hit = total_pts > float(line_value)
            if (selection == "OVER" and over_hit) or (selection == "UNDER" and not over_hit):
                net_profit = round(stake_pen * (decimal_odds - 1.0), 4)
                return "WON", net_profit, summary
            return "LOST", round(-stake_pen, 4), summary

        raise DataValidationError(f"Unsupported market for settlement: {market!r}")

    def settle_bet(
        self,
        bet_id: str,
        game_status: str,
        home_score: int | None,
        away_score: int | None,
        settled_at: str | None = None,
    ) -> dict[str, Any]:
        """
        Settles a single PENDING simulated bet after verifying temporal order and preventing double settlement.
        """
        bet = self.db.fetch_one("SELECT * FROM simulated_bets WHERE bet_id = ?", (bet_id,))
        if not bet:
            raise DataValidationError(f"Bet ID {bet_id!r} does not exist")

        if bet["status"] != "PENDING":
            raise DoubleSettlementError(
                f"Bet {bet_id} has already been settled with status '{bet['status']}' and cannot be settled twice."
            )

        game = self.db.fetch_one("SELECT * FROM games WHERE game_id = ?", (bet["game_id"],))
        if not game:
            raise DataValidationError(f"Associated game {bet['game_id']} not found")

        settlement_ts = settled_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if parse_iso_utc(settlement_ts) <= parse_iso_utc(game["game_start_time"]):
            raise TemporalLeakageError(
                f"Cannot settle bet {bet_id} at {settlement_ts} before or at game_start_time ({game['game_start_time']})"
            )

        outcome_status, net_profit, result_summary = self.calculate_settlement_outcome(
            market=bet["market"],
            selection=bet["selection"],
            line_value=bet["line_value"],
            decimal_odds=float(bet["decimal_odds"]),
            stake_pen=float(bet["stake_pen"]),
            game_status=game_status,
            home_score=home_score,
            away_score=away_score,
        )

        pre_state = self.get_bankroll_state()
        new_settled_bankroll = round(pre_state["settled_bankroll_pen"] + net_profit, 4)
        if new_settled_bankroll < 0.0:
            raise RiskLimitError(f"Negative bankroll violation detected: S/{new_settled_bankroll:.2f}")

        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    UPDATE simulated_bets
                    SET status = ?,
                        net_profit_pen = ?,
                        bankroll_after_pen = ?,
                        actual_result_summary = ?,
                        settled_at = ?
                    WHERE bet_id = ?
                    """,
                    (
                        outcome_status,
                        net_profit,
                        new_settled_bankroll,
                        result_summary,
                        settlement_ts,
                        bet_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DoubleSettlementError(f"Database trigger blocked settlement on {bet_id}: {exc}") from exc

        post_state = self.get_bankroll_state()
        self.db.execute_insert(
            """
            INSERT INTO bankroll_ledger (
                timestamp, event_type, reference_bet_id, amount_delta_pen,
                settled_bankroll_pen, pending_exposure_pen, available_balance_pen
            ) VALUES (?, 'BET_SETTLED', ?, ?, ?, ?, ?)
            """,
            (
                settlement_ts,
                bet_id,
                net_profit,
                post_state["settled_bankroll_pen"],
                post_state["pending_exposure_pen"],
                post_state["available_balance_pen"],
            ),
        )

        return {
            "bet_id": bet_id,
            "status": outcome_status,
            "net_profit_pen": net_profit,
            "bankroll_after_pen": new_settled_bankroll,
            "actual_result_summary": result_summary,
            "settled_at": settlement_ts,
        }
