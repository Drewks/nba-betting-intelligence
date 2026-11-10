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

from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any
import uuid
import numpy as np

from src.config import (
    DEFAULT_AGGRESSIVE_PROFILE,
    DEFAULT_CONSERVATIVE_PROFILE,
    RiskConfig,
    load_config,
)
from src.paper_trading.staking import fractional_kelly_stake
from src.prediction.ev_calculator import optimize_simultaneous_kelly_portfolio
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


def compute_cppi_multiplier(
    current_bankroll: float,
    peak_bankroll: float,
    floor_fraction: float = 0.85,
) -> float:
    """
    V9 Phase 5: Constant Proportion Portfolio Insurance (CPPI) Capital Preservation Shield.
    Calculates dynamic risk multiplier based on cushion above an 85% high-water mark floor:
    - When bankroll is at or above peak: multiplier = 1.0 (full capacity).
    - When bankroll approaches the floor: exposure scales down towards 0.15.
    """
    peak = max(1.0, float(peak_bankroll))
    floor_val = peak * floor_fraction
    cushion = max(0.0, float(current_bankroll) - floor_val)
    target_cushion = max(1.0, peak * (1.0 - floor_fraction))

    cushion_ratio = cushion / target_cushion
    if cushion_ratio >= 1.0:
        return 1.0
    elif cushion_ratio <= 0.0:
        return 0.15
    else:
        return round(max(0.15, min(1.0, float(cushion_ratio))), 4)


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
                    allow_parlays=True,
                    allow_player_props_betting=True,
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
        """
        Active Risk Governor based on Closing Line Value (CLV).
        If the market has moved against our entry prices on recent bets (mean CLV < 0%),
        automatically trims stake scaling to protect bankroll during adverse market regimes.
        Parameters and brackets are configured via config/model_config.yaml (clv_governor).
        Returns (scaling_factor, mean_clv_pct).
        """
        gov_cfg = getattr(getattr(self, "risk_config", None), "clv_governor", None)
        effective_lookback = lookback if lookback is not None else (gov_cfg.lookback_bets if gov_cfg else 25)
        min_sample = gov_cfg.min_sample_size if gov_cfg else 4

        rows = self.db.fetch_all(
            f"""
            SELECT b.bet_id, b.decimal_odds,
                   (
                       SELECT o.decimal_odds
                       FROM v_observed_odds_snapshots o
                       WHERE o.game_id = b.game_id
                         AND o.market = b.market
                         AND o.selection = b.selection
                         AND COALESCE(o.line_value, -9999) = COALESCE(b.line_value, -9999)
                         AND o.is_closing_line = 1
                       ORDER BY (CASE WHEN o.provider LIKE '%Pinnacle%' THEN 1 ELSE 0 END) DESC,
                                o.captured_at DESC
                       LIMIT 1
                   ) AS closing_odds
            FROM v_observed_simulated_bets b
            WHERE b.status IN ('WON', 'LOST', 'PUSH')
              AND {self.scope_predicate("b")}
              AND closing_odds IS NOT NULL
            ORDER BY b.settled_at DESC
            LIMIT ?
            """,
            (effective_lookback,),
        )
        if len(rows) < min_sample:
            return 1.0, None
        clvs = [
            ((float(r["decimal_odds"]) / float(r["closing_odds"])) - 1.0) * 100.0
            for r in rows
            if float(r["closing_odds"]) > 1.0
        ]
        if not clvs:
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

    def persist_closing_lines_for_games(self, as_of_utc: str | None = None) -> int:
        """
        Promotes the latest strictly pre-tipoff OBSERVED odds capture to a formal closing line
        (is_closing_line = 1) for real games that are FINAL or within 45 minutes of tip-off.
        - Only rows from `v_observed_odds_snapshots` are eligible (never quarantined/derived/synthetic odds),
          so a fabricated quote can never be laundered into an "observed" closing line.
        - The closing copy inherits the source row's provider and source_type.
        - Strictly requires captured_at < game_start_time (zero temporal leakage).
        Returns the count of newly inserted closing odds rows.
        """
        now_dt = parse_iso_utc(as_of_utc) if as_of_utc else datetime.now(timezone.utc)
        cutoff_str = (now_dt + timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
        games_needing_close = self.db.fetch_all(
            """
            SELECT g.game_id, g.game_start_time, g.status
            FROM games g
            WHERE g.game_id NOT LIKE 'SYN%'
              AND (g.status IN ('FINAL', 'POSTPONED', 'CANCELLED') OR g.game_start_time <= ?)
              AND EXISTS (
                  SELECT 1 FROM v_observed_odds_snapshots o
                  WHERE o.game_id = g.game_id AND o.is_closing_line = 0 AND o.captured_at < g.game_start_time
              )
              AND NOT EXISTS (
                  SELECT 1 FROM v_observed_odds_snapshots o
                  WHERE o.game_id = g.game_id AND o.is_closing_line = 1
                    AND o.captured_at >= (
                        SELECT MAX(o2.captured_at) FROM v_observed_odds_snapshots o2
                        WHERE o2.game_id = g.game_id AND o2.is_closing_line = 0
                          AND o2.captured_at < g.game_start_time
                    )
              )
            """,
            (cutoff_str,),
        )
        inserted_count = 0
        with self.db.connect() as conn:
            for g in games_needing_close:
                gid = g["game_id"]
                start_ts = g["game_start_time"]
                latest_time_row = conn.execute(
                    """
                    SELECT MAX(captured_at) AS max_captured
                    FROM v_observed_odds_snapshots
                    WHERE game_id = ? AND is_closing_line = 0 AND captured_at < ?
                    """,
                    (gid, start_ts),
                ).fetchone()
                if not latest_time_row or not latest_time_row["max_captured"]:
                    continue
                max_captured = latest_time_row["max_captured"]

                snapshots = conn.execute(
                    """
                    SELECT * FROM v_observed_odds_snapshots
                    WHERE game_id = ? AND is_closing_line = 0 AND captured_at = ?
                    """,
                    (gid, max_captured),
                ).fetchall()

                for s in snapshots:
                    close_id = f"{s['odds_id']}_CLOSE"
                    existing_close = conn.execute("SELECT 1 FROM odds_snapshots WHERE odds_id = ?", (close_id,)).fetchone()
                    if existing_close:
                        ts_compact = s["captured_at"].replace("-", "").replace(":", "").replace("T", "_").replace("Z", "")
                        close_id = f"{s['odds_id']}_CLOSE_{ts_compact}"
                    inserted = self.db.insert_odds_snapshot(
                        {
                            "odds_id": close_id,
                            "game_id": s["game_id"],
                            "provider": s["provider"],
                            "market": s["market"],
                            "selection": s["selection"],
                            "line_value": s["line_value"],
                            "decimal_odds": s["decimal_odds"],
                            "counterpart_decimal_odds": s["counterpart_decimal_odds"],
                            "captured_at": s["captured_at"],
                            "is_closing_line": 1,
                            "source_type": s["source_type"],
                        },
                        conn=conn,
                    )
                    inserted_count += int(inserted)
        return inserted_count

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
        """
        Calculates contextual Kelly-Conviction stake:
        - MODO ALFA PURO (Confianza Ciega en el Modelo, sin freno CPPI por defecto):
          * Underdog (<50%): S/ 3.50 - S/ 5.50 PEN
          * Medium probability (50% - 58%): S/ 6.00 - S/ 9.50 PEN
          * High probability (58% - 65%): S/ 10.00 - S/ 14.50 PEN
          * Maximum conviction (>=65%): S/ 15.00 - S/ 20.00 PEN
        Also integrates Monte Carlo Overtime Guard, Venn-Abers Conformal bounds,
        and sharp steam move modulation.
        """
        p = max(0.01, min(0.99, float(calibrated_prob)))
        b = max(0.05, float(decimal_odds) - 1.0)
        f_kelly = max(0.0, (p * (b + 1.0) - 1.0) / b)

        mode = getattr(self, "staking_mode", "AGGRESSIVE_ALPHA")
        ct_cfg = getattr(getattr(self, "risk_config", None), "conviction_tiers", None)
        if ct_cfg:
            prof = ct_cfg.aggressive if mode == "AGGRESSIVE_ALPHA" else ct_cfg.conservative
        else:
            prof = DEFAULT_AGGRESSIVE_PROFILE if mode == "AGGRESSIVE_ALPHA" else DEFAULT_CONSERVATIVE_PROFILE

        t_low = prof.tier_low
        t_mid = prof.tier_mid
        t_high = prof.tier_high
        t_star = prof.tier_star

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

        # Reasonable longshot moderation only on extreme outliers
        if decimal_odds > prof.max_longshot_odds:
            raw_stake = min(raw_stake, prof.max_longshot_stake)

        # Monte Carlo Overtime Guard
        ot_cfg = getattr(getattr(self, "risk_config", None), "overtime_guard", None)
        if ot_cfg and ot_cfg.enabled:
            if str(selection).upper() == "UNDER" and float(overtime_prob) >= ot_cfg.min_overtime_prob:
                raw_stake *= ot_cfg.under_haircut
        elif str(selection).upper() == "UNDER" and float(overtime_prob) >= 0.068:
            raw_stake *= 0.85

        # Risk Modulators: Conformal Agreement / Uncertainty adjustment & Steam Moves
        rm_cfg = getattr(getattr(self, "risk_config", None), "risk_modulators", None)
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

        # Active CLV Governor: scale down if market has been closing against us
        if apply_clv_governor:
            clv_factor, _ = self.get_recent_clv_governor_factor()
            raw_stake *= clv_factor

        # Scale proportionally with current settled bankroll (relative to initial S/100)
        bankroll_scale = max(0.80, min(1.50, float(current_bankroll_pen) / max(1.0, self.initial_bankroll_pen)))
        scaled_stake = raw_stake * bankroll_scale

        # CPPI Capital Preservation Shield: disabled by default in Pure Alpha Mode
        # Only activates if explicitly requested or if enable_cppi_shield is set to True
        should_apply_cppi = apply_cppi_shield if apply_cppi_shield is not None else getattr(self, "enable_cppi_shield", False)
        if should_apply_cppi:
            cppi_mult = self.compute_cppi_multiplier(current_bankroll_pen, peak_bankroll_override=peak_bankroll_pen)
            scaled_stake *= cppi_mult

        return round(max(min_stake_floor, min(self.max_stake_pen, scaled_stake)), 2)

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
            peak_row = self.db.fetch_one("SELECT MAX(bankroll_after_pen) AS max_br FROM simulated_bets WHERE bankroll_after_pen IS NOT NULL")
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
            # V7 Multi-Bet Simultaneous Kelly Optimization across slate candidates
            if proposed_stake_pen is None:
                qualifying = [c for c in sorted_candidates if float(c.get("ev_unit", -1.0)) > self.min_ev_threshold]
                if len(qualifying) >= 2:
                    curr_br = self.get_bankroll_state()["settled_bankroll_pen"]
                    max_indiv = min(0.06, self.max_stake_pen / max(1.0, curr_br))
                    opt_picks = optimize_simultaneous_kelly_portfolio(
                        qualifying,
                        bankroll_pen=curr_br,
                        max_total_exposure_fraction=0.15,
                        max_individual_fraction=max_indiv,
                    )
                    pred_to_opt = {c["prediction_id"]: c for c in opt_picks if "prediction_id" in c}
                    for c in sorted_candidates:
                        if c.get("prediction_id") in pred_to_opt:
                            c["kelly_recommended_stake_pen"] = pred_to_opt[c["prediction_id"]]["kelly_recommended_stake_pen"]
                            c["kelly_optimal_fraction"] = pred_to_opt[c["prediction_id"]]["kelly_optimal_fraction"]
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

            # 2c. Longshot bias variance guard: deep underdogs (> 3.50 odds) require a substantial margin of safety
            # (EV >= 15%) because low-probability tails carry high estimation variance on a micro-bankroll.
            if dec_odds > 3.50 and ev_pct < 15.0:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "EXCESSIVE_LONGSHOT_VARIANCE",
                        f"Longshot odds {dec_odds:.2f} (> 3.50) require EV >= 15.0% (observed: {ev_pct:.2f}%); skipped to protect bankroll.",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            # 2d. Adverse Sharp Steam Move Guard (V6): block betting into heavy reverse sharp line movement
            steam_delta = float(cand.get("steam_delta") or 0.0)
            if steam_delta <= -0.045:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "ADVERSE_SHARP_STEAM_MOVE",
                        f"Market fair probability moved {steam_delta * 100:.2f}% against this side since opening (<= -4.5%); skipped.",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            # 2e. Conformal Prediction Interval Width Guard (V7 Fase 3):
            conf_w = cand.get("conformal_width")
            if conf_w is not None and float(conf_w) > 0.22:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "CONFORMAL_UNCERTAINTY_TOO_WIDE",
                        f"Venn-Abers conformal prediction interval width {float(conf_w):.3f} > 0.22; epistemic uncertainty too high.",
                        ev_pct, emitted_at, model_version_id
                    )
                )
                continue

            # 2f. Meta-Labeling CLV Filter Guard (V8 Fase 2):
            if cand.get("meta_label_pass") is False:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        cand.get("meta_label_reason") or "NEGATIVE_EXPECTED_CLV",
                        f"Meta-labeling model predicts negative Closing Line Value (P(CLV > 0) = {float(cand.get('p_positive_clv') or 0.0):.2f}); skipped to protect edge.",
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

            # 3. Check single-game anti-correlation limit (max 1 bet per game across all markets)
            if self.single_bet_per_game:
                if game_id in selected_games:
                    no_bet_decisions.append(
                        self._record_decision(
                            game_id, matchday_date, market, selection, "NO_BET",
                            "CORRELATED_GAME_EXPOSURE",
                            f"Another selection for game {game_id} was already placed in this matchday.",
                            ev_pct, emitted_at, model_version_id
                        )
                    )
                    continue

                existing_pending_in_game = self.db.fetch_one(
                    "SELECT bet_id, market, selection FROM simulated_bets WHERE game_id = ? AND status = 'PENDING'",
                    (game_id,),
                )
                if existing_pending_in_game:
                    no_bet_decisions.append(
                        self._record_decision(
                            game_id, matchday_date, market, selection, "NO_BET",
                            "PENDING_BET_IN_SAME_GAME",
                            f"Game already has an active pending bet ({existing_pending_in_game['bet_id']}: "
                            f"{existing_pending_in_game['market']} {existing_pending_in_game['selection']})",
                            ev_pct, emitted_at, model_version_id
                        )
                    )
                    continue
            elif (game_id, market) in selected_game_markets:
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "MARKET_ALREADY_SELECTED",
                        "Another selection in the same game and market was already placed",
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

            # 5a. Check Hybrid Market Allocation (70% Totales / 30% Moneyline)
            if self.hybrid_allocation_enabled:
                if market == "moneyline" and day_ml_count >= self.max_moneyline_per_matchday:
                    no_bet_decisions.append(
                        self._record_decision(
                            game_id, matchday_date, market, selection, "NO_BET",
                            "MARKET_CAP_REACHED",
                            f"Matchday cap of {self.max_moneyline_per_matchday} moneyline pick(s) reached (70/30 hybrid allocation)",
                            ev_pct, emitted_at, model_version_id
                        )
                    )
                    continue
                elif market == "total_points" and day_totals_count >= self.max_totals_per_matchday:
                    if day_ml_count > 0 or day_count >= self.max_selections_per_matchday:
                        no_bet_decisions.append(
                            self._record_decision(
                                game_id, matchday_date, market, selection, "NO_BET",
                                "MARKET_CAP_REACHED",
                                f"Matchday cap of {self.max_totals_per_matchday} total_points pick(s) reached (70/30 hybrid allocation)",
                                ev_pct, emitted_at, model_version_id
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
            state = self.get_bankroll_state()
            if proposed_stake_pen is not None:
                bet_stake = stake
            elif self.staking_mode == "FRACTIONAL_KELLY":
                # Stake grows with the calibrated, market-anchored probability for this price; 0 = no edge.
                bet_stake = fractional_kelly_stake(
                    prob=float(cal_prob),
                    decimal_odds=dec_odds,
                    bankroll_pen=state["settled_bankroll_pen"],
                    kelly_fraction=self.kelly_fraction,
                    min_stake_pen=self.min_stake_pen,
                    max_stake_pen=self.max_stake_pen,
                    max_bankroll_fraction=self.max_stake_bankroll_fraction,
                )
                if bet_stake <= 0.0:
                    no_bet_decisions.append(
                        self._record_decision(
                            game_id, matchday_date, market, selection, "NO_BET",
                            "KELLY_STAKE_BELOW_MINIMUM",
                            f"Fractional Kelly stake below S/{self.min_stake_pen:.2f} (no material edge at {dec_odds:.3f}).",
                            ev_pct, emitted_at, model_version_id
                        )
                    )
                    continue
            elif self.dynamic_conviction_staking:
                if cand.get("kelly_recommended_stake_pen") is not None:
                    bet_stake = round(float(cand["kelly_recommended_stake_pen"]), 2)
                else:
                    bet_stake = self.compute_contextual_stake_pen(
                        calibrated_prob=float(cal_prob),
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

            # Check Portfolio Exposure Cap (max 20% total exposure per AGENTS.md)
            max_allowed_exposure = state["settled_bankroll_pen"] * self.max_portfolio_exposure_pct
            if (state["pending_exposure_pen"] + bet_stake) > (max_allowed_exposure + 0.01):
                no_bet_decisions.append(
                    self._record_decision(
                        game_id, matchday_date, market, selection, "NO_BET",
                        "PORTFOLIO_EXPOSURE_LIMIT",
                        f"Pending exposure S/{state['pending_exposure_pen']:.2f} + S/{bet_stake:.2f} exceeds cap of S/{max_allowed_exposure:.2f} (20% bankroll).",
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
            if market == "total_points":
                day_totals_count += 1
            elif market == "moneyline":
                day_ml_count += 1
            selected_games.add(game_id)
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

        if market == "spread":
            if line_value is None:
                raise DataValidationError("spread settlement requires line_value")
            side_margin = float(home_score - away_score) if selection == "HOME" else float(away_score - home_score)
            adjusted_margin = side_margin + float(line_value)
            if abs(adjusted_margin) < 1e-6:
                return "PUSH", 0.0, summary
            if adjusted_margin > 0.0:
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

    # -------------------------------------------------------------------------
    # V8 Player Props & SGP Paper Trading Settlement & Performance Tracking
    # -------------------------------------------------------------------------
    def record_player_prop_pick(
        self,
        prop_dict: dict[str, Any],
        enforce_scheduled_status: bool = False,
        allow_parlay: bool | None = None,
    ) -> str:
        """
        Records a single player prop paper bet with PENDING status.
        Enforces game existence, scheduled status, pre-tipoff timing, and official active roster verification.
        Combined bets (SGP / parlays) are prohibited by AGENTS.md and rejected unless a research caller
        opts in explicitly with allow_parlay=True.
        """
        if allow_parlay is None:
            allow_parlay = load_config().risk.allow_parlays
        if str(prop_dict.get("prop_category", "")).upper() == "SGP" and not allow_parlay:
            raise RiskLimitError("Combined bets (SGP/parlays) are disabled (risk_management.allow_parlays = false).")
        prop_id = prop_dict.get("prop_id") or f"PROP_{uuid.uuid4().hex[:10].upper()}"
        emitted_at = prop_dict.get("emitted_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        gid = prop_dict["game_id"]

        # 1. Verify game exists and is SCHEDULED (when enforced)
        game = self.db.fetch_one("SELECT game_id, game_start_time, status, home_team, away_team FROM games WHERE game_id = ?", (gid,))
        if not game:
            raise DataValidationError(f"Cannot record prop on nonexistent game: {gid}")
        if enforce_scheduled_status and game["status"] != "SCHEDULED":
            raise DataValidationError(f"Cannot record prop on game {gid} with status '{game['status']}' (must be 'SCHEDULED')")

        # 2. Strict pre-tipoff timing guard
        start_ts = game.get("game_start_time")
        if enforce_scheduled_status and start_ts:
            t_emitted = parse_iso_utc(emitted_at)
            t_start = parse_iso_utc(start_ts)
            if t_emitted >= t_start:
                raise TemporalLeakageError(
                    f"Temporal leakage violation: prop {prop_id} emitted at {emitted_at} >= game tipoff {start_ts}"
                )

        # 3. Dynamic roster verification
        team = prop_dict.get("team", "NBA")
        player_name = prop_dict.get("player_name", "")
        cat = prop_dict.get("prop_category", "")

        # If single player prop, verify player belongs to specified team
        if cat != "SGP" and team != "NBA":
            roster_rows = self.db.fetch_all("SELECT player_name FROM team_rosters WHERE team_id = ? AND is_active = 1", (team,))
            if roster_rows:
                from src.ingestion.roster_manager import normalize_name
                norm_p = normalize_name(player_name)
                norm_active = {normalize_name(r["player_name"]) for r in roster_rows}
                if norm_p not in norm_active:
                    other_team_row = self.db.fetch_one(
                        "SELECT team_id FROM team_rosters WHERE (player_name LIKE ? OR ? LIKE ('%' || player_name || '%')) AND is_active = 1",
                        (f"%{player_name}%", player_name),
                    )
                    actual_team = other_team_row["team_id"] if other_team_row else "Unknown"
                    raise DataValidationError(
                        f"Roster integrity violation: {player_name} is not on active roster of {team} (currently on {actual_team})"
                    )

        stake_pen = round(float(prop_dict.get("stake_pen") or prop_dict.get("kelly_stake_pen") or 1.00), 2)
        if stake_pen <= 0.0:
            stake_pen = 1.00

        self.db.execute_insert(
            """
            INSERT OR IGNORE INTO player_prop_picks (
                prop_id, game_id, matchday_date, player_name, team, prop_category,
                line_value, selection, decimal_odds, projected_mean, projected_std,
                model_prob, conformal_p_low, conformal_p_high, ev_pct, ev_lower_bound_pct,
                stake_pen, kelly_stake_pen, usage_bump_pct, rationale, emitted_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """,
            (
                prop_id,
                prop_dict["game_id"],
                prop_dict["matchday_date"],
                prop_dict["player_name"],
                prop_dict.get("team", "NBA"),
                prop_dict["prop_category"],
                float(prop_dict["line_value"]),
                prop_dict["selection"],
                float(prop_dict["decimal_odds"]),
                float(prop_dict.get("projected_mean", 0.0)),
                float(prop_dict.get("projected_std", 0.0)),
                float(prop_dict["model_prob"]),
                float(prop_dict.get("conformal_p_low", 0.0)),
                float(prop_dict.get("conformal_p_high", 1.0)),
                float(prop_dict.get("ev_pct", 0.0)),
                float(prop_dict.get("ev_lower_bound_pct", 0.0)),
                stake_pen,
                float(prop_dict.get("kelly_stake_pen", stake_pen)),
                float(prop_dict.get("usage_bump_pct", 0.0)),
                prop_dict.get("rationale", "Prop opportunity identified by V8 quantitative model"),
                emitted_at,
            ),
        )
        return prop_id

    def settle_player_prop(
        self,
        prop_id: str,
        actual_stat: float | None = None,
        game_status: str = "FINAL",
        home_score: int | None = None,
        away_score: int | None = None,
        settled_at: str | None = None,
    ) -> dict[str, Any]:
        """
        Settles a single PENDING simulated player prop or SGP parlay bet.
        Enforces immutable audit integrity and temporal ordering.
        """
        prop = self.db.fetch_one("SELECT * FROM player_prop_picks WHERE prop_id = ?", (prop_id,))
        if not prop:
            raise DataValidationError(f"Player prop pick ID {prop_id!r} does not exist")

        if prop["status"] != "PENDING":
            raise DoubleSettlementError(
                f"Prop {prop_id} has already been settled with status '{prop['status']}' and cannot be settled twice."
            )

        game = self.db.fetch_one("SELECT * FROM games WHERE game_id = ?", (prop["game_id"],))
        if not game:
            raise DataValidationError(f"Associated game {prop['game_id']} not found")

        settlement_ts = settled_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if game_status not in ("VOID", "CANCELLED", "POSTPONED") and parse_iso_utc(settlement_ts) <= parse_iso_utc(game["game_start_time"]):
            raise TemporalLeakageError(
                f"Cannot settle prop {prop_id} at {settlement_ts} before or at game_start_time ({game['game_start_time']})"
            )

        stake_pen = float(prop.get("stake_pen") or prop.get("kelly_stake_pen") or 1.0)
        decimal_odds = float(prop["decimal_odds"])
        line_val = float(prop["line_value"])
        cat = str(prop["prop_category"]).upper()
        sel = str(prop["selection"]).upper()

        if game_status in ("POSTPONED", "CANCELLED", "VOID"):
            outcome_status = "VOID"
            net_profit = 0.0
            stat_recorded = 0.0
            summary = f"Prop {game_status}"
        else:
            if game_status != "FINAL":
                raise DataValidationError(f"Cannot settle prop before game is FINAL (status={game_status})")

            if cat == "SGP":
                if actual_stat is not None:
                    is_won = float(actual_stat) >= 1.0
                    stat_recorded = float(actual_stat)
                else:
                    if home_score is None or away_score is None:
                        raise DataValidationError("SGP settlement requires game scores or explicit actual_stat")
                    raise DataValidationError("SGP settlement requires actual_stat indicator (1.0 = hit, 0.0 = miss)")

                if is_won:
                    outcome_status = "WON"
                    net_profit = round(stake_pen * (decimal_odds - 1.0), 4)
                    summary = f"SGP Acertada: Combinada correlacionada ganadora (+S/{net_profit:.2f} PEN)"
                else:
                    outcome_status = "LOST"
                    net_profit = round(-stake_pen, 4)
                    summary = f"SGP Fallada: Al menos una pierna no se cumplió (-S/{stake_pen:.2f} PEN)"
            else:
                if actual_stat is None:
                    raise DataValidationError(f"Prop {cat} settlement requires actual_stat value")
                stat_recorded = float(actual_stat)

                if sel == "OVER":
                    if stat_recorded > line_val:
                        outcome_status = "WON"
                        net_profit = round(stake_pen * (decimal_odds - 1.0), 4)
                        summary = f"{prop['player_name']} {cat} {stat_recorded:.1f} > {line_val:.1f} (GANADA +S/{net_profit:.2f} PEN)"
                    elif stat_recorded < line_val:
                        outcome_status = "LOST"
                        net_profit = round(-stake_pen, 4)
                        summary = f"{prop['player_name']} {cat} {stat_recorded:.1f} < {line_val:.1f} (PERDIDA -S/{stake_pen:.2f} PEN)"
                    else:
                        outcome_status = "PUSH"
                        net_profit = 0.0
                        summary = f"{prop['player_name']} {cat} {stat_recorded:.1f} == {line_val:.1f} (EMPATE / DEVUELTA)"
                elif sel == "UNDER":
                    if stat_recorded < line_val:
                        outcome_status = "WON"
                        net_profit = round(stake_pen * (decimal_odds - 1.0), 4)
                        summary = f"{prop['player_name']} {cat} {stat_recorded:.1f} < {line_val:.1f} (GANADA +S/{net_profit:.2f} PEN)"
                    elif stat_recorded > line_val:
                        outcome_status = "LOST"
                        net_profit = round(-stake_pen, 4)
                        summary = f"{prop['player_name']} {cat} {stat_recorded:.1f} > {line_val:.1f} (PERDIDA -S/{stake_pen:.2f} PEN)"
                    else:
                        outcome_status = "PUSH"
                        net_profit = 0.0
                        summary = f"{prop['player_name']} {cat} {stat_recorded:.1f} == {line_val:.1f} (EMPATE / DEVUELTA)"
                else:
                    raise DataValidationError(f"Unsupported prop selection: {sel}")

        # Compute updated props bankroll from initial bankroll + prior cumulative P&L + current net profit
        prior_pnl_row = self.db.fetch_one(
            """
            SELECT COALESCE(SUM(net_profit_pen), 0.0) AS total_prior_pnl
            FROM player_prop_picks
            WHERE status IN ('WON', 'LOST', 'PUSH', 'VOID')
              AND net_profit_pen IS NOT NULL
              AND prop_id != ?
            """ ,
            (prop_id,),
        )
        total_prior_pnl = float(prior_pnl_row["total_prior_pnl"]) if prior_pnl_row else 0.0
        new_bankroll = round(self.initial_bankroll_pen + total_prior_pnl + net_profit, 4)
        if new_bankroll < 0.0:
            raise RiskLimitError(f"Negative props bankroll violation detected: S/{new_bankroll:.2f}")

        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    UPDATE player_prop_picks
                    SET status = ?,
                        actual_stat = ?,
                        net_profit_pen = ?,
                        bankroll_after_pen = ?,
                        actual_result_summary = ?,
                        settled_at = ?
                    WHERE prop_id = ?
                    """,
                    (
                        outcome_status,
                        stat_recorded,
                        net_profit,
                        new_bankroll,
                        summary,
                        settlement_ts,
                        prop_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DoubleSettlementError(f"Database trigger blocked settlement on prop {prop_id}: {exc}") from exc

        return {
            "prop_id": prop_id,
            "status": outcome_status,
            "actual_stat": stat_recorded,
            "net_profit_pen": net_profit,
            "bankroll_after_pen": new_bankroll,
            "actual_result_summary": summary,
            "settled_at": settlement_ts,
        }

    def settle_pending_player_props(
        self,
        game_boxscores: dict[str, dict[str, dict[str, float]]] | None = None,
        settled_at: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Scans all PENDING player prop and SGP picks whose games are FINAL/POSTPONED/CANCELLED,
        resolves their boxscore statistics, and executes immutable settlement.
        """
        pending_props = self.db.fetch_all(
            """
            SELECT p.prop_id, p.game_id, p.player_name, p.team, p.prop_category, p.line_value,
                   p.selection, g.status as game_status, g.home_score, g.away_score,
                   g.home_team, g.away_team, g.result_recorded_at
            FROM player_prop_picks p
            JOIN games g ON p.game_id = g.game_id
            WHERE p.status = 'PENDING'
              AND g.status IN ('FINAL', 'POSTPONED', 'CANCELLED')
            """
        )
        settled_results: list[dict[str, Any]] = []
        for prop in pending_props:
            pid = prop["prop_id"]
            gid = prop["game_id"]
            g_status = prop["game_status"]
            ts = settled_at or prop["result_recorded_at"]

            if g_status in ("POSTPONED", "CANCELLED"):
                try:
                    res = self.settle_player_prop(pid, game_status=g_status, settled_at=ts)
                    settled_results.append(res)
                except Exception as exc:
                    logger.warning(f"Failed to settle postponed prop {pid}: {exc}")
                continue

            cat = prop["prop_category"]
            p_name = prop["player_name"]
            stat_val: float | None = None

            if game_boxscores and gid in game_boxscores:
                g_box = game_boxscores[gid]
                p_stats = g_box.get(p_name)
                if not p_stats:
                    for k, v in g_box.items():
                        if k in p_name or p_name in k:
                            p_stats = v
                            break
                if p_stats and cat in p_stats:
                    stat_val = float(p_stats[cat])
                elif cat == "SGP" and p_stats and "SGP" in p_stats:
                    stat_val = float(p_stats["SGP"])

            if stat_val is not None:
                try:
                    res = self.settle_player_prop(
                        prop_id=pid,
                        actual_stat=stat_val,
                        game_status=g_status,
                        home_score=prop["home_score"],
                        away_score=prop["away_score"],
                        settled_at=ts,
                    )
                    settled_results.append(res)
                except Exception as exc:
                    logger.warning(f"Failed to settle prop {pid}: {exc}")

        return settled_results

    def get_player_props_performance_metrics(self) -> dict[str, Any]:
        """
        Computes institutional performance metrics for Player Props & SGP Paper Trading:
        Win rate, Net Profit (PEN), ROI %, Brier Score, Conformal Coverage, and category breakdown.
        """
        all_props = self.db.fetch_all("SELECT * FROM player_prop_picks ORDER BY emitted_at DESC")
        settled = [p for p in all_props if p["status"] in ("WON", "LOST", "PUSH", "VOID")]
        won = [p for p in settled if p["status"] == "WON"]
        lost = [p for p in settled if p["status"] == "LOST"]
        push = [p for p in settled if p["status"] == "PUSH"]
        void = [p for p in settled if p["status"] == "VOID"]

        total_staked = sum(float(p.get("stake_pen") or p.get("kelly_stake_pen") or 1.0) for p in settled if p["status"] in ("WON", "LOST"))
        net_profit = sum(float(p.get("net_profit_pen") or 0.0) for p in settled)

        current_bankroll = round(self.initial_bankroll_pen + net_profit, 2)

        resolved_count = len(won) + len(lost)
        win_rate = (len(won) / resolved_count * 100.0) if resolved_count > 0 else 0.0
        roi_pct = (net_profit / total_staked * 100.0) if total_staked > 0 else 0.0

        squared_errors = []
        conformal_hits = 0
        for p in settled:
            if p["status"] in ("WON", "LOST"):
                y_true = 1.0 if p["status"] == "WON" else 0.0
                prob = float(p.get("model_prob") or 0.5)
                squared_errors.append((prob - y_true) ** 2)
                p_low = float(p.get("conformal_p_low") or 0.0)
                p_high = float(p.get("conformal_p_high") or 1.0)
                if p_low <= y_true <= p_high or (p["status"] == "WON" and prob >= 0.5) or (p["status"] == "LOST" and prob < 0.5):
                    conformal_hits += 1

        brier_score = float(np.mean(squared_errors)) if squared_errors else 0.0
        conformal_coverage = (conformal_hits / resolved_count * 100.0) if resolved_count > 0 else 100.0

        categories = ["PTS", "REB", "AST", "PRA", "3PM", "PR", "PA", "RA", "SGP"]
        breakdown: dict[str, dict[str, Any]] = {}
        for cat in categories:
            cat_props = [p for p in settled if p.get("prop_category") == cat]
            c_won = [p for p in cat_props if p["status"] == "WON"]
            c_lost = [p for p in cat_props if p["status"] == "LOST"]
            c_staked = sum(float(p.get("stake_pen") or p.get("kelly_stake_pen") or 1.0) for p in cat_props if p["status"] in ("WON", "LOST"))
            c_net = sum(float(p.get("net_profit_pen") or 0.0) for p in cat_props)
            c_res = len(c_won) + len(c_lost)
            breakdown[cat] = {
                "total_settled": len(cat_props),
                "won": len(c_won),
                "lost": len(c_lost),
                "win_rate_pct": round(len(c_won) / c_res * 100.0, 1) if c_res > 0 else 0.0,
                "total_staked_pen": round(c_staked, 2),
                "net_profit_pen": round(c_net, 2),
                "roi_pct": round(c_net / c_staked * 100.0, 2) if c_staked > 0 else 0.0,
            }

        return {
            "total_picks": len(all_props),
            "pending_picks": len(all_props) - len(settled),
            "settled_picks": len(settled),
            "won_picks": len(won),
            "lost_picks": len(lost),
            "push_picks": len(push),
            "void_picks": len(void),
            "win_rate_pct": round(win_rate, 2),
            "total_staked_pen": round(total_staked, 2),
            "total_net_profit_pen": round(net_profit, 2),
            "current_props_bankroll_pen": round(current_bankroll, 2),
            "roi_pct": round(roi_pct, 2),
            "brier_score": round(brier_score, 4),
            "conformal_coverage_pct": round(conformal_coverage, 1),
            "category_breakdown": breakdown,
            "recent_settled": settled[:15],
        }


def build_production_engine(db: DatabaseManager) -> PaperTradingEngine:
    """The single place that turns config/model_config.yaml into the production paper-trading engine."""
    cfg = load_config()
    risk = cfg.risk
    hyb = cfg.hybrid_allocation
    return PaperTradingEngine(
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
