"""
Paper Trading Engine (Sections 7 & 8):
- Manages virtual bankroll of S/100.00 PEN (strictly simulation, zero real betting endpoints)
- Enforces stake base S/1.00, max stake S/1.00, max 3 selections per matchday
- Prohibits parlays, Martingale, doubling after loss, loans, or negative balance
- Logs NO_BET decisions when EV or validation gates are not met
- Settles WON, LOST, PUSH, VOID bets with double-settlement prevention and full reconciliation
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
from typing import Any

from src.config import EvidenceStakingConfig, RiskConfig, load_config
from src.evaluation.clv import get_recent_clv_governor_factor as _get_clv_governor
from src.paper_trading.cppi import compute_cppi_multiplier
from src.paper_trading.exceptions import DoubleSettlementError, RiskLimitError
from src.paper_trading.execution_helpers import (
    check_candidate_caps_and_duplicates,
    check_candidate_edge_and_model_guards,
    record_decision_entry,
    reserve_and_insert_simulated_bet,
    sort_and_prepare_candidates,
)
from src.paper_trading.props_ledger import (
    compute_props_calibration_summary,
    get_player_props_performance_metrics as _get_props_metrics,
    record_player_prop_pick as _record_prop_pick,
    settle_pending_player_props as _settle_pending_props,
    settle_player_prop as _settle_prop,
)
from src.paper_trading.settlement import (
    calculate_settlement_outcome,
    persist_closing_lines_for_games as _persist_closing_lines,
    settle_simulated_bet,
)
from src.paper_trading.shadow_ledger import record_shadow_slate
from src.paper_trading.staking import compute_contextual_stake_pen_impl, fractional_kelly_stake
from src.storage.db import DatabaseManager
from src.validation.validator import parse_iso_utc


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
        single_bet_per_game: bool = True,
        enable_cppi_shield: bool = True,
        staking_mode: str = "CONSERVATIVE",
        is_backtest: bool = False,
        max_portfolio_exposure_pct: float = 0.20,
        kelly_fraction: float = 0.25,
        min_stake_pen: float = 0.50,
        max_stake_bankroll_fraction: float = 0.03,
        hybrid_allocation_enabled: bool = False,
        max_totals_per_matchday: int = 2,
        max_moneyline_per_matchday: int = 1,
        risk_config: RiskConfig | None = None,
    ) -> None:
        self.is_backtest = is_backtest
        self.hybrid_allocation_enabled = bool(hybrid_allocation_enabled)
        self.max_totals_per_matchday = int(max_totals_per_matchday)
        self.max_moneyline_per_matchday = int(max_moneyline_per_matchday)
        self.max_portfolio_exposure_pct = max_portfolio_exposure_pct
        self.kelly_fraction = float(kelly_fraction)
        self.min_stake_pen = float(min_stake_pen)
        self.max_stake_bankroll_fraction = float(max_stake_bankroll_fraction)
        # AGENTS.md: flat mode max S/1.00; FRACTIONAL_KELLY capped by config (hard ceiling S/20.00) per selection.
        # The dynamic-conviction mode is a research mode only.
        if dynamic_conviction_staking:
            max_allowed = 25.00
        elif str(staking_mode) == "FRACTIONAL_KELLY":
            max_allowed = 20.00
        else:
            max_allowed = 1.00
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
        self.enable_cppi_shield = bool(enable_cppi_shield)
        self.staking_mode = str(staking_mode)
        # Set by build_production_engine; None keeps Kelly unscaled (tests, research engines).
        self.evidence_staking: EvidenceStakingConfig | None = None
        self._evidence_cache: dict[str, dict[str, Any]] | None = None
        # When True, bankroll / metrics only count bets on REAL games (synthetic SYN_* fixtures are archived benchmarks)
        self.exclude_synthetic = bool(exclude_synthetic)
        # Anti-correlation: limit maximum exposure to at most 1 active bet per game across all markets
        self.single_bet_per_game = bool(single_bet_per_game)
        if risk_config is not None:
            self.risk_config = risk_config
        else:
            try:
                self.risk_config = load_config().risk
            except Exception:
                self.risk_config = RiskConfig(
                    virtual_bankroll_initial_pen=self.initial_bankroll_pen,
                    staking_mode="fractional_kelly",
                    kelly_fraction=self.kelly_fraction,
                    min_stake_pen=self.min_stake_pen,
                    max_stake_bankroll_fraction=self.max_stake_bankroll_fraction,
                    base_stake_pen=self.base_stake_pen,
                    max_stake_pen=self.max_stake_pen,
                    max_selections_per_matchday=self.max_selections_per_matchday,
                    min_ev_threshold=self.min_ev_threshold,
                    max_portfolio_exposure_pct=self.max_portfolio_exposure_pct,
                    allow_parlays=False,
                    allow_player_props_betting=False,
                )
        self._ensure_initial_ledger()

    def scope_predicate(self, alias: str = "") -> str:
        """SQL predicate restricting simulated_bets to the active accounting scope, optionally table-qualified."""
        col = f"{alias}.game_id" if alias else "game_id"
        return f"{col} NOT LIKE 'SYN%'" if self.exclude_synthetic else "1 = 1"

    @property
    def scope_sql(self) -> str:
        """SQL predicate restricting simulated_bets to the active accounting scope."""
        return self.scope_predicate()

    def get_recent_clv_governor_factor(self, lookback: int | None = None) -> tuple[float, float | None]:
        """Active Risk Governor based on Closing Line Value (CLV)."""
        return _get_clv_governor(
            self.db,
            risk_config=getattr(self, "risk_config", None),
            scope_predicate_sql=self.scope_predicate("b"),
            lookback=lookback,
        )

    def persist_closing_lines_for_games(self, as_of_utc: str | None = None) -> int:
        """Promotes latest pre-tipoff OBSERVED odds captures to closing lines (`is_closing_line = 1`)."""
        return _persist_closing_lines(self.db, as_of_utc=as_of_utc)

    def _evidence_kelly_multiplier(self, market: str) -> tuple[float, str | None]:
        """Kelly multiplier for `market` from its shadow-ledger CLV verdict (1.0 when disabled)."""
        cfg = self.evidence_staking
        # The shadow ledger holds signals settled up to now: replaying history with it would let future
        # CLV change past stakes (lookahead), so walk-forward replays are never scaled.
        if cfg is None or not cfg.enabled or self.is_backtest:
            return 1.0, None
        cache = self._evidence_cache
        if cache is None:
            from src.paper_trading.shadow_ledger import clv_evidence_by_market

            cache = clv_evidence_by_market(self.db)
            self._evidence_cache = cache
        verdict = (cache.get(market) or {}).get("verdict")
        return cfg.multiplier(verdict), verdict

    def compute_contextual_stake_pen(
        self,
        calibrated_prob: float,
        decimal_odds: float,
        ev_unit: float,
        current_bankroll_pen: float,
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
        return compute_contextual_stake_pen_impl(
            calibrated_prob=calibrated_prob,
            decimal_odds=decimal_odds,
            ev_unit=ev_unit,
            current_bankroll_pen=current_bankroll_pen,
            initial_bankroll_pen=self.initial_bankroll_pen,
            max_stake_pen=self.max_stake_pen,
            staking_mode=getattr(self, "staking_mode", "AGGRESSIVE_ALPHA"),
            risk_config=getattr(self, "risk_config", None),
            enable_cppi_shield=getattr(self, "enable_cppi_shield", False),
            clv_governor_fn=self.get_recent_clv_governor_factor,
            cppi_fn=lambda br, peak: self.compute_cppi_multiplier(br, peak_bankroll_override=peak),
            uncertainty_std=uncertainty_std,
            selection=selection,
            overtime_prob=overtime_prob,
            steam_delta=steam_delta,
            apply_clv_governor=apply_clv_governor,
            conformal_width=conformal_width,
            ev_lower_bound=ev_lower_bound,
            apply_cppi_shield=apply_cppi_shield,
            peak_bankroll_pen=peak_bankroll_pen,
        )

    def compute_cppi_multiplier(
        self,
        current_bankroll_pen: float,
        floor_fraction: float = 0.85,
        peak_bankroll_override: float | None = None,
    ) -> float:
        """
        V9 Phase 5: Constant Proportion Portfolio Insurance (CPPI) Capital Preservation Shield.
        """
        if peak_bankroll_override is not None:
            peak = float(peak_bankroll_override)
        elif self.db is not None:
            bets_table = "simulated_bets" if (self.is_backtest and not self.exclude_synthetic) else "v_observed_simulated_bets"
            peak_row = self.db.fetch_one(f"SELECT MAX(bankroll_after_pen) AS max_br FROM {bets_table} WHERE bankroll_after_pen IS NOT NULL")
            peak = max(self.initial_bankroll_pen, float(peak_row["max_br"] or self.initial_bankroll_pen) if peak_row else self.initial_bankroll_pen)
        else:
            peak = self.initial_bankroll_pen

        return compute_cppi_multiplier(current_bankroll_pen, peak, floor_fraction)

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
        Computes current bankroll state strictly from observed simulated bets (`v_observed_simulated_bets`)
        so that all reports and summaries share the exact same observed bankroll.
        Falls back to `simulated_bets` only during explicit synthetic walk-forward backtests.
        """
        bets_table = "simulated_bets" if (self.is_backtest and not self.exclude_synthetic) else "v_observed_simulated_bets"
        settled_rows = self.db.fetch_all(
            f"SELECT net_profit_pen FROM {bets_table} WHERE status IN ('WON', 'LOST', 'PUSH', 'VOID') AND {self.scope_sql}"
        )
        pending_rows = self.db.fetch_all(
            f"SELECT stake_pen FROM {bets_table} WHERE status = 'PENDING' AND {self.scope_sql}"
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

        sorted_candidates = sort_and_prepare_candidates(
            candidate_predictions,
            dynamic_conviction_staking=self.dynamic_conviction_staking,
            proposed_stake_pen=proposed_stake_pen,
            min_ev_threshold=self.min_ev_threshold,
            max_stake_pen=self.max_stake_pen,
            get_bankroll_fn=self.get_bankroll_state,
        )

        placed_bets: list[dict[str, Any]] = []
        no_bet_decisions: list[dict[str, Any]] = []

        existing_day_bets = self.db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM simulated_bets WHERE matchday_date = ?",
            (matchday_date,),
        )
        day_count = int(existing_day_bets["cnt"]) if existing_day_bets else 0
        existing_market_rows = self.db.fetch_all(
            "SELECT market, COUNT(*) AS cnt FROM simulated_bets WHERE matchday_date = ? GROUP BY market",
            (matchday_date,),
        )
        day_totals_count = sum(int(r["cnt"]) for r in existing_market_rows if r.get("market") == "total_points")
        day_ml_count = sum(int(r["cnt"]) for r in existing_market_rows if r.get("market") == "moneyline")
        selected_game_markets: set[tuple[str, str]] = set()
        selected_games: set[str] = set()

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

            edge_block = check_candidate_edge_and_model_guards(cand, min_ev_threshold=self.min_ev_threshold)
            if edge_block is None:
                edge_block = check_candidate_caps_and_duplicates(
                    self.db,
                    cand,
                    day_count=day_count,
                    day_totals_count=day_totals_count,
                    day_ml_count=day_ml_count,
                    selected_games=selected_games,
                    selected_game_markets=selected_game_markets,
                    single_bet_per_game=self.single_bet_per_game,
                    max_selections_per_matchday=self.max_selections_per_matchday,
                    hybrid_allocation_enabled=self.hybrid_allocation_enabled,
                    max_moneyline_per_matchday=self.max_moneyline_per_matchday,
                    max_totals_per_matchday=self.max_totals_per_matchday,
                )
            if edge_block is not None:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        edge_block[0], edge_block[1], ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            # 5b. Check game existence and strict pre-tipoff scheduled validity
            game_record = self.db.fetch_one(
                "SELECT game_id, game_start_time, status FROM games WHERE game_id = ?",
                (game_id,),
            )
            if not game_record:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "NONEXISTENT_GAME",
                        f"Game {game_id} does not exist in the database.",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            if not self.is_backtest and game_record["status"] != "SCHEDULED":
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "GAME_NOT_SCHEDULED",
                        f"Game {game_id} has status '{game_record['status']}' (must be 'SCHEDULED').",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            start_iso = game_record.get("game_start_time")
            if start_iso:
                t_emitted = parse_iso_utc(emitted_at)
                t_start = parse_iso_utc(start_iso)
                if t_emitted >= t_start:
                    no_bet_decisions.append(
                        self._record_decision(
                            game_id, matchday_date, market, selection, "NO_BET",
                            "GAME_ALREADY_STARTED",
                            f"Bet emitted at {emitted_at} is after or at tipoff ({start_iso}). Temporal leakage prevented.",
                            ev_pct, emitted_at, model_version_id
                        )
                    )
                    continue

            # 6. Contextual Kelly-Conviction Stake (or v1 fixed stake) & Available Balance Check
            if cal_prob is None:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "MISSING_CALIBRATED_PROB",
                        "Candidate lacks calibrated_probability required for Kelly/EV staking.",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue
            cal_prob_val = float(cal_prob)
            state = self.get_bankroll_state()
            if proposed_stake_pen is not None:
                bet_stake = stake
            elif self.staking_mode == "FRACTIONAL_KELLY":
                # Stake grows with the calibrated, market-anchored probability for this price; 0 = no edge.
                # The fraction is scaled by the market's shadow-ledger CLV evidence (roadmap phase 3).
                evidence_mult, evidence_verdict = self._evidence_kelly_multiplier(market)
                bet_stake = fractional_kelly_stake(
                    prob=cal_prob_val,
                    decimal_odds=dec_odds,
                    bankroll_pen=state["settled_bankroll_pen"],
                    kelly_fraction=self.kelly_fraction * evidence_mult,
                    min_stake_pen=self.min_stake_pen,
                    max_stake_pen=self.max_stake_pen,
                    max_bankroll_fraction=self.max_stake_bankroll_fraction,
                )
                if bet_stake <= 0.0:
                    no_bet_decisions.append(
                        self._record_decision(
                            game_id, matchday_date, market, selection, "NO_BET",
                            "KELLY_STAKE_BELOW_MINIMUM",
                            f"Fractional Kelly stake below S/{self.min_stake_pen:.2f} (no material edge at {dec_odds:.3f})"
                            + (
                                f"; Kelly x{evidence_mult:.2f} by {market} CLV evidence {evidence_verdict}."
                                if evidence_mult < 1.0
                                else "."
                            ),
                            ev_pct, emitted_at, model_version_id
                        )
                    )
                    continue
            elif self.dynamic_conviction_staking:
                if cand.get("kelly_recommended_stake_pen") is not None:
                    bet_stake = round(float(cand["kelly_recommended_stake_pen"]), 2)
                else:
                    bet_stake = self.compute_contextual_stake_pen(
                        calibrated_prob=cal_prob_val,
                        decimal_odds=dec_odds,
                        ev_unit=ev_unit,
                        current_bankroll_pen=state["settled_bankroll_pen"],
                        uncertainty_std=float(cand.get("uncertainty_std") or 0.05),
                        selection=selection,
                        overtime_prob=float(cand.get("overtime_prob") or 0.0),
                        steam_delta=float(cand.get("steam_delta") or 0.0),
                        conformal_width=cand.get("conformal_width"),
                        ev_lower_bound=cand.get("ev_lower_bound"),
                    )
            elif dec_odds > 2.45:
                bet_stake = round(max(0.50, min(self.max_stake_pen, 1.35 / (dec_odds - 0.35))), 2)
            else:
                bet_stake = stake

            # Check Portfolio Exposure Cap configured in risk management
            max_allowed_exposure = state["settled_bankroll_pen"] * self.max_portfolio_exposure_pct
            if (state["pending_exposure_pen"] + bet_stake) > (max_allowed_exposure + 0.01):
                cap_pct_lbl = int(round(self.max_portfolio_exposure_pct * 100))
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "PORTFOLIO_EXPOSURE_LIMIT",
                        f"Pending exposure S/{state['pending_exposure_pen']:.2f} + S/{bet_stake:.2f} exceeds cap of S/{max_allowed_exposure:.2f} ({cap_pct_lbl}% bankroll).",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            if state["available_balance_pen"] < bet_stake or bet_stake <= 0.0:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "INSUFFICIENT_VIRTUAL_BALANCE",
                        f"Available balance S/{state['available_balance_pen']:.2f} < stake S/{bet_stake:.2f} or zero stake",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            state, bet_summary = reserve_and_insert_simulated_bet(
                self.db,
                state=state,
                prediction_id=prediction_id,
                game_id=game_id,
                matchday_date=matchday_date,
                market=market,
                selection=selection,
                line_value=line_value,
                dec_odds=dec_odds,
                cal_prob=cal_prob_val,
                ev_unit=ev_unit,
                ev_pct=ev_pct,
                bet_stake=bet_stake,
                emitted_at=emitted_at,
                model_version_id=model_version_id,
            )

            day_count += 1
            if market == "total_points":
                day_totals_count += 1
            elif market == "moneyline":
                day_ml_count += 1
            selected_games.add(game_id)
            selected_game_markets.add((game_id, market))
            placed_bets.append(bet_summary)

        if not candidate_predictions:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            no_bet_decisions.append(
                self._record_decision(
                    f"MATCHDAY_{matchday_date}", matchday_date, "ALL", "NONE", "NO_BET",
                    "NO_VALID_CANDIDATES", "No games with complete validated data/odds on this matchday",
                    0.0, now_str, "none"
                )
            )

        end_state = self.get_bankroll_state()
        shadow_recorded = record_shadow_slate(
            self.db,
            matchday_date,
            candidate_predictions,
            placed_bets=placed_bets,
            no_bet_decisions=no_bet_decisions,
            bankroll_pen=end_state["settled_bankroll_pen"],
            kelly_fraction=self.kelly_fraction,
            max_bankroll_fraction=self.max_stake_bankroll_fraction,
        )

        return {
            "matchday_date": matchday_date,
            "placed_bets": placed_bets,
            "no_bet_decisions": no_bet_decisions,
            "bankroll_state": end_state,
            "shadow_recorded_count": shadow_recorded,
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
        return record_decision_entry(
            self.db,
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
        )

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
        Delegates to src.paper_trading.settlement.calculate_settlement_outcome.
        """
        return calculate_settlement_outcome(
            market=market,
            selection=selection,
            line_value=line_value,
            decimal_odds=decimal_odds,
            stake_pen=stake_pen,
            game_status=game_status,
            home_score=home_score,
            away_score=away_score,
        )

    def settle_bet(
        self,
        bet_id: str,
        game_status: str,
        home_score: int | None,
        away_score: int | None,
        settled_at: str | None = None,
    ) -> dict[str, Any]:
        """Settles a single PENDING simulated bet via `paper_trading.settlement`."""
        return settle_simulated_bet(
            self.db,
            self.get_bankroll_state,
            bet_id=bet_id,
            game_status=game_status,
            home_score=home_score,
            away_score=away_score,
            settled_at=settled_at,
        )

    # -------------------------------------------------------------------------
    # V8 Player Props & SGP Paper Trading Settlement & Performance Tracking
    # -------------------------------------------------------------------------
    def record_player_prop_pick(
        self,
        prop_dict: dict[str, Any],
        enforce_scheduled_status: bool = False,
        allow_parlay: bool | None = None,
        allow_player_props: bool | None = None,
    ) -> str:
        """Records a player prop paper bet with fail-closed risk gates and roster validation."""
        return _record_prop_pick(
            self.db,
            self.risk_config,
            self._record_decision,
            prop_dict=prop_dict,
            enforce_scheduled_status=enforce_scheduled_status,
            allow_parlay=allow_parlay,
            allow_player_props=allow_player_props,
        )

    def settle_player_prop(
        self,
        prop_id: str,
        actual_stat: float | None = None,
        game_status: str = "FINAL",
        home_score: int | None = None,
        away_score: int | None = None,
        settled_at: str | None = None,
    ) -> dict[str, Any]:
        """Settles a single PENDING simulated player prop or SGP parlay bet."""
        return _settle_prop(
            self.db,
            self.initial_bankroll_pen,
            prop_id=prop_id,
            actual_stat=actual_stat,
            game_status=game_status,
            home_score=home_score,
            away_score=away_score,
            settled_at=settled_at,
        )

    def settle_pending_player_props(
        self,
        game_boxscores: dict[str, dict[str, dict[str, float]]] | None = None,
        settled_at: str | None = None,
    ) -> list[dict[str, Any]]:
        """Scans and settles PENDING player prop picks whose games are settled."""
        return _settle_pending_props(
            self.db,
            self.initial_bankroll_pen,
            game_boxscores=game_boxscores,
            settled_at=settled_at,
        )

    def get_player_props_performance_metrics(self) -> dict[str, Any]:
        """Computes quarantined performance metrics for Player Props & SGP Paper Trading."""
        return _get_props_metrics(self.db, self.initial_bankroll_pen)


def build_production_engine(db: DatabaseManager) -> PaperTradingEngine:
    """The single place that turns config/model_config.yaml into the production paper-trading engine."""
    cfg = load_config()
    risk = cfg.risk
    hyb = cfg.hybrid_allocation
    engine = PaperTradingEngine(
        db=db,
        initial_bankroll_pen=risk.virtual_bankroll_initial_pen,
        base_stake_pen=risk.base_stake_pen,
        max_stake_pen=risk.max_stake_pen,
        max_selections_per_matchday=risk.max_selections_per_matchday,
        min_ev_threshold=risk.min_ev_threshold,
        dynamic_conviction_staking=False,
        enable_cppi_shield=True,
        staking_mode="FRACTIONAL_KELLY" if risk.staking_mode == "fractional_kelly" else "CONSERVATIVE",
        exclude_synthetic=True,
        max_portfolio_exposure_pct=risk.max_portfolio_exposure_pct,
        kelly_fraction=risk.kelly_fraction,
        min_stake_pen=risk.min_stake_pen,
        max_stake_bankroll_fraction=risk.max_stake_bankroll_fraction,
        hybrid_allocation_enabled=hyb.enabled,
        max_totals_per_matchday=hyb.max_totals_per_matchday,
        max_moneyline_per_matchday=hyb.max_moneyline_per_matchday,
    )
    engine.evidence_staking = cfg.evidence_staking
    return engine


__all__ = [
    "DoubleSettlementError",
    "PaperTradingEngine",
    "RiskLimitError",
    "build_production_engine",
    "calculate_settlement_outcome",
    "compute_cppi_multiplier",
    "compute_props_calibration_summary",
]

