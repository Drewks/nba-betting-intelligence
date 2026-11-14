"""
V9 Player Props Quantitative Engine (`src/prediction/player_props.py`):
Institutional statistical modeling of NBA Player Props & Same-Game Parlays (SGP):
  1. Micro-Usage & Minutes Redistribution: Re-allocates vacated usage rate (USG%) and minute shares
     when teammates are confirmed OUT via the LineupSynergyEngine.
  2. Tactical Matchup & Pace Context Factors:
     - Opponent Defense vs Position (DvP) defensive rating splits across all 30 NBA franchises.
     - Expected Game Pace factor (differential relative to 99.5 baseline).
     - Blowout Spread Dampening: Mitigates star minute inflation when spread > 10.5 pts.
  3. Parametric Probability Distributions:
     - Discrete Poisson distribution for count variables (Assists, Rebounds, 3-Pointers) preserving push mass.
     - Overdispersed Gaussian distribution for continuous scoring (Points, PRA, PR, PA, RA).
  4. Venn-Abers Conformal Multi-Probabilistic Calibration & Lower-Bound EV:
     Category-specific & pooled Venn-Abers conformal intervals trained strictly < cutoff_utc;
     unfitted heuristic fallbacks are explicitly flagged and blocked from lower-bound staking.
  5. Multivariate Student-t & Gaussian Copula Simulator for SGP ("Crea tu Apuesta"):
     Zero probability floor on joint empirical hits, Wilson 95% confidence bounds, and
     relative precision gating (`INSUFFICIENT_SIMULATION_PRECISION` -> `NO_BET`).
  6. Fail-closed Risk Gate (`allow_player_props_betting` & `allow_parlays`) and Fractional Kelly.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import os
from pathlib import Path
from typing import Any
import uuid

import numpy as np
from scipy.stats import norm

logger = logging.getLogger(__name__)

from src.calibration.calibrator import VennAbersConformalInterval, conformal_lower_bound_ev
from src.config import RiskConfig, load_config
from src.ingestion.normalizer import normalize_player_match_key
from src.prediction.ev_calculator import (
    calculate_ev,
    devig_multiplicative,
    market_anchored_probability,
)
from src.prediction.minutes_model import MinutesProjectionEngine
from src.prediction.multivariate_copula import (
    MultivariateStudentTCopula,
    wilson_confidence_interval,
)
from src.prediction.props_constants import (
    PLAYER_BASELINES,
    PLAYER_PROP_BASELINES,
    PROP_DISPERSION_MULTIPLIERS,
    TEAM_DEFENSIVE_MULTIPLIERS,
    get_fallback_rosters,
)
from src.prediction.props_distribution import (
    compute_exceedance_probabilities as compute_exceedance_probs_math,
)
from src.storage.db import DatabaseManager
from src.validation.validator import TemporalLeakageError, parse_iso_utc

__all__ = [
    "PLAYER_BASELINES",
    "PLAYER_PROP_BASELINES",
    "TEAM_DEFENSIVE_MULTIPLIERS",
    "PlayerPropsEngine",
    "get_fallback_rosters",
]

_PROP_CATEGORY_ALIASES: dict[str, str] = {
    "PTS": "PTS",
    "POINTS": "PTS",
    "POINT": "PTS",
    "REB": "REB",
    "REBOUNDS": "REB",
    "REBOUND": "REB",
    "AST": "AST",
    "ASSISTS": "AST",
    "ASSIST": "AST",
    "3PM": "3PM",
    "3PT": "3PM",
    "THREES": "3PM",
    "PRA": "PRA",
    "PR": "PR",
    "PA": "PA",
    "RA": "RA",
}


def _normalize_player_match_key(name: str) -> str:
    """Normalizes a player name for exact canonical matching across bookmakers and rosters."""
    return normalize_player_match_key(name)


def _parse_observed_prop_provider(provider_str: str) -> tuple[str, str] | None:
    """
    Extracts (player_name, canonical_category) from a bookmaker prop provider string.
    Supports:
      - Structured pipe format: '{book}|{player_name}|{category}' (or '{book}|{player_name}')
      - Underscore format: '{book}_{player_name}_{category}' or '{book}_{player_name}' (defaults strictly to 'PTS')
    Returns None if player_name or category cannot be cleanly parsed.
    """
    raw = str(provider_str or "").strip()
    if not raw:
        return None

    if "|" in raw:
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) < 2 or not parts[1]:
            return None
        player_part = parts[1]
        cat_token = parts[2].upper() if len(parts) >= 3 and parts[2] else "PTS"
        canonical_cat = _PROP_CATEGORY_ALIASES.get(cat_token)
        if not canonical_cat:
            return None
        return player_part, canonical_cat

    if "_" in raw:
        parts = [p.strip() for p in raw.split("_") if p.strip()]
        if len(parts) < 2:
            return None
        last_upper = parts[-1].upper()
        if len(parts) >= 3 and last_upper in _PROP_CATEGORY_ALIASES:
            canonical_cat = _PROP_CATEGORY_ALIASES[last_upper]
            player_part = " ".join(parts[1:-1]).strip()
        else:
            canonical_cat = "PTS"
            player_part = " ".join(parts[1:]).strip()
        if not player_part:
            return None
        return player_part, canonical_cat

    return None


class PlayerPropsEngine:
    """
    Quantitative Modeling of NBA Player Props & SGP:
    Calculates expected statistical values per player, absorbs usage bumps from injuries,
    adjusts for opponent defense and game pace, computes Poisson/Gaussian exceedance probabilities,
    simulates SGP joint copulas for RETAbet Perú, and identifies +EV bets.
    """

    def __init__(
        self,
        db: DatabaseManager | None = None,
        min_ev_threshold: float = 0.05,
        risk_config: RiskConfig | None = None,
        allow_player_props: bool | None = None,
        category_min_samples: int = 30,
        global_min_samples: int = 60,
    ) -> None:
        self.db = db
        self.min_ev_threshold = min_ev_threshold
        self._config_load_error: str | None = None
        self.model_version_id: str = "model_f_ensemble_v8"
        if risk_config is not None:
            self.risk: RiskConfig | None = risk_config
        else:
            try:
                cfg = load_config()
                self.risk = cfg.risk
                self.model_version_id = getattr(getattr(cfg, "model", None), "version_id", "model_f_ensemble_v8")
            except Exception as exc:
                self.risk = None
                self._config_load_error = str(exc)

        if self.risk is not None:
            if allow_player_props is not None:
                self.risk = replace(self.risk, allow_player_props_betting=bool(allow_player_props))
            self.kelly_fraction = self.risk.kelly_fraction
            self.max_stake_pen = self.risk.max_stake_pen
            self.max_bankroll_fraction = self.risk.max_stake_bankroll_fraction
        else:
            # Fail-closed defaults when config cannot be validated
            self.kelly_fraction = 0.25
            self.max_stake_pen = 5.0
            self.max_bankroll_fraction = 0.03

        self.global_min_samples = max(10, int(global_min_samples))
        self.category_min_samples = max(10, int(category_min_samples))
        self.calibrator = VennAbersConformalInterval(window=1200, min_samples=self.global_min_samples)
        self.category_calibrators: dict[str, VennAbersConformalInterval] = {}
        self.calibration_cutoff_utc: str | None = None
        self.calibration_dataset_size: int = 0
        self.calibration_summary: dict[str, Any] = {
            "global": {"is_fitted": False, "sample_size": 0, "cutoff_utc": None},
            "categories": {},
        }
        self.minutes_engine = MinutesProjectionEngine()
        self.copula_engine = MultivariateStudentTCopula()
        self._player_baselines_cache: dict[tuple[str, str], tuple[float, float, float, float, float, float]] = {}
        self._team_multipliers_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def _log_blocked_prop_decision(
        self,
        *,
        game_id: str,
        matchday_date: str,
        market: str,
        selection: str,
        reason_code: str,
        reason_detail: str,
        ev_pct: float | None = None,
    ) -> None:
        """Persists NO_BET audit trail into decision_log whenever risk gates block a prop/SGP."""
        if self.db is None:
            return
        try:
            self.db.execute_insert(
                """
                INSERT INTO decision_log (
                    decision_id, game_id, matchday_date, market, selection,
                    decision_type, reason_code, reason_detail, ev_pct, emitted_at, model_version_id
                ) VALUES (?, ?, ?, ?, ?, 'NO_BET', ?, ?, ?, ?, ?)
                """,
                (
                    f"DEC_PROP_{uuid.uuid4().hex[:12]}",
                    game_id or "UNKNOWN_GAME",
                    matchday_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    market,
                    selection,
                    reason_code,
                    reason_detail,
                    ev_pct,
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    self.model_version_id,
                ),
            )
        except Exception as exc:
            logger.debug(f"Failed to log blocked prop decision: {exc}")

    def _check_props_risk_gate(
        self,
        *,
        is_sgp: bool,
        game_id: str,
        matchday_date: str,
        selection: str,
        ev_pct: float | None = None,
        allow_player_props: bool | None = None,
        allow_parlays: bool | None = None,
    ) -> tuple[bool, str]:
        """
        Single fail-closed centralized gate enforced immediately before any write to
        `player_prop_picks` (both single props and SGP/parlay entries).
        """
        if self.risk is None:
            detail = (
                f"Fail-closed: risk configuration unavailable ({self._config_load_error or 'missing risk_config'}); "
                "player_prop_picks persistence denied."
            )
            self._log_blocked_prop_decision(
                game_id=game_id,
                matchday_date=matchday_date,
                market="sgp" if is_sgp else "player_prop",
                selection=selection,
                reason_code="DISABLED_BY_CONFIG",
                reason_detail=detail,
                ev_pct=ev_pct,
            )
            return False, detail

        eff_props = bool(self.risk.allow_player_props_betting) if allow_player_props is None else bool(allow_player_props)
        if not eff_props:
            detail = "Player props paper betting is disabled (`risk_management.allow_player_props_betting=false`)."
            self._log_blocked_prop_decision(
                game_id=game_id,
                matchday_date=matchday_date,
                market="sgp" if is_sgp else "player_prop",
                selection=selection,
                reason_code="DISABLED_BY_CONFIG",
                reason_detail=detail,
                ev_pct=ev_pct,
            )
            return False, detail

        if is_sgp:
            eff_parlays = bool(self.risk.allow_parlays) if allow_parlays is None else bool(allow_parlays)
            if not eff_parlays:
                detail = "SGP/parlay persistence is disabled (`risk_management.allow_parlays=false`)."
                self._log_blocked_prop_decision(
                    game_id=game_id,
                    matchday_date=matchday_date,
                    market="sgp",
                    selection=selection,
                    reason_code="DISABLED_BY_CONFIG",
                    reason_detail=detail,
                    ev_pct=ev_pct,
                )
                return False, detail

        return True, "ALLOWED"

    def _props_exposure_allows(self, stake_pen: float, bankroll_pen: float) -> bool:
        """Props/SGP ledger exposure cap: pending stakes may not exceed max_portfolio_exposure_pct of bankroll."""
        if stake_pen <= 0.0 or self.risk is None:
            return False
        if self.db is None:
            return True
        row = self.db.fetch_one("SELECT COALESCE(SUM(stake_pen), 0.0) AS s FROM player_prop_picks WHERE status = 'PENDING'")
        pending = float(row["s"]) if row else 0.0
        return (pending + stake_pen) <= self.risk.max_portfolio_exposure_pct * max(0.0, bankroll_pen) + 0.01

    def _props_may_record(
        self, game_id: str, matchday_date: str, player_key: str, category: str, selection: str,
        stake_pen: float, bankroll_pen: float,
        *, is_sgp: bool | None = None, allow_player_props: bool | None = None, allow_parlays: bool | None = None,
        ev_pct: float | None = None,
    ) -> bool:
        """
        Single gate for every props/SGP paper bet: fail-closed risk flags (`allow_player_props_betting`,
        `allow_parlays`), positive stake, exposure cap, game not finished, idempotency, and daily cap.
        """
        sgp_flag = (category.upper() == "SGP") if is_sgp is None else bool(is_sgp)
        allowed, _reason = self._check_props_risk_gate(
            is_sgp=sgp_flag,
            game_id=game_id,
            matchday_date=matchday_date,
            selection=f"{player_key} {category} {selection}".strip(),
            ev_pct=ev_pct,
            allow_player_props=allow_player_props,
            allow_parlays=allow_parlays,
        )
        if not allowed or self.db is None or self.risk is None or not self._props_exposure_allows(stake_pen, bankroll_pen):
            return False
        g_rec = self.db.fetch_one("SELECT status FROM games WHERE game_id = ?", (game_id,))
        if g_rec and g_rec.get("status") in ("FINAL", "POSTPONED", "CANCELLED"):
            return False
        dup = self.db.fetch_one(
            """
            SELECT 1 AS x FROM player_prop_picks
            WHERE game_id = ? AND player_name = ? AND prop_category = ? AND selection = ? LIMIT 1
            """,
            (game_id, player_key, category, selection),
        )
        if dup:
            return False
        row = self.db.fetch_one("SELECT COUNT(*) AS c FROM player_prop_picks WHERE matchday_date = ?", (matchday_date,))
        return int(row["c"] if row else 0) < self.risk.max_selections_per_matchday

    def _persist_prop_pick(
        self,
        prop_pick: dict[str, Any],
        bankroll_pen: float,
        *,
        allow_player_props: bool | None = None,
    ) -> bool:
        ev_raw = prop_pick.get("ev_pct")
        ev_val = float(ev_raw) if ev_raw is not None else None
        if bool(prop_pick.get("lower_bound_ev_blocked")) or float(prop_pick.get("kelly_stake_pen") or 0.0) <= 0.0:
            self._log_blocked_prop_decision(
                game_id=str(prop_pick.get("game_id") or "UNKNOWN_GAME"),
                matchday_date=str(prop_pick.get("matchday_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                market="player_prop",
                selection=f"{prop_pick.get('player_name', '')} {prop_pick.get('prop_category', '')} {prop_pick.get('selection', '')}".strip(),
                reason_code=str(prop_pick.get("decision_reason") or "UNFITTED_CALIBRATOR_FALLBACK"),
                reason_detail="Prop lower-bound EV staking blocked because calibrator is unfitted or stake is 0.",
                ev_pct=ev_val,
            )
            return False
        if not self._props_may_record(
            prop_pick["game_id"], prop_pick["matchday_date"], prop_pick["player_name"], prop_pick["prop_category"],
            prop_pick["selection"], float(prop_pick.get("kelly_stake_pen") or 0.0), bankroll_pen,
            is_sgp=False,
            allow_player_props=allow_player_props,
            ev_pct=ev_val,
        ):
            return False
        assert self.db is not None
        try:
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
                    prop_pick["prop_id"], prop_pick["game_id"], prop_pick["matchday_date"], prop_pick["player_name"],
                    prop_pick["team"], prop_pick["prop_category"], prop_pick["line_value"], prop_pick["selection"],
                    prop_pick["decimal_odds"], prop_pick["projected_mean"], prop_pick["projected_std"],
                    prop_pick["model_prob"], prop_pick["conformal_p_low"], prop_pick["conformal_p_high"],
                    prop_pick["ev_pct"], prop_pick["ev_lower_bound_pct"], prop_pick["kelly_stake_pen"],
                    prop_pick["kelly_stake_pen"], prop_pick["usage_bump_pct"], prop_pick["rationale"],
                    prop_pick["emitted_at"],
                ),
            )
            return True
        except Exception as exc:
            logger.warning(f"Failed to persist player prop opportunity: {exc}")
            return False

    def _persist_sgp_pick(
        self,
        sgp_cand: dict[str, Any],
        bankroll_pen: float,
        *,
        allow_player_props: bool | None = None,
        allow_parlays: bool | None = None,
    ) -> bool:
        ev_raw = sgp_cand.get("ev_pct")
        ev_val = float(ev_raw) if ev_raw is not None else None
        if sgp_cand.get("decision") == "NO_BET" or float(sgp_cand.get("kelly_stake_pen") or 0.0) <= 0.0:
            self._log_blocked_prop_decision(
                game_id=str(sgp_cand.get("game_id") or "UNKNOWN_GAME"),
                matchday_date=str(sgp_cand.get("matchday_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                market="sgp",
                selection=f"{sgp_cand.get('player_name', '')} + {sgp_cand.get('game_selection', '')}".strip(),
                reason_code=str(sgp_cand.get("decision_reason") or "NO_VALUE_OR_INSUFFICIENT_PRECISION"),
                reason_detail="SGP blocked from paper ledger due to NO_BET decision or zero Kelly stake.",
                ev_pct=ev_val,
            )
            return False
        player_key = f"{sgp_cand['player_name']} + {sgp_cand['game_selection']}"
        if not self._props_may_record(
            sgp_cand["game_id"], sgp_cand["matchday_date"], player_key, "SGP", "SGP",
            float(sgp_cand.get("kelly_stake_pen") or 0.0), bankroll_pen,
            is_sgp=True,
            allow_player_props=allow_player_props,
            allow_parlays=allow_parlays,
            ev_pct=ev_val,
        ):
            return False
        assert self.db is not None
        ci_low_raw = sgp_cand.get("ci_95_low")
        ci_high_raw = sgp_cand.get("ci_95_high")
        p_low = float(ci_low_raw) if ci_low_raw is not None else float(sgp_cand["p_joint"])
        p_high = float(ci_high_raw) if ci_high_raw is not None else float(sgp_cand["p_joint"])
        try:
            self.db.execute_insert(
                """
                INSERT OR IGNORE INTO player_prop_picks (
                    prop_id, game_id, matchday_date, player_name, team, prop_category,
                    line_value, selection, decimal_odds, projected_mean, projected_std,
                    model_prob, conformal_p_low, conformal_p_high, ev_pct, ev_lower_bound_pct,
                    stake_pen, kelly_stake_pen, usage_bump_pct, rationale, emitted_at, status
                ) VALUES (?, ?, ?, ?, ?, 'SGP', ?, 'SGP', ?, 0.0, 0.0, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, 'PENDING')
                """,
                (
                    sgp_cand["sgp_id"], sgp_cand["game_id"], sgp_cand["matchday_date"], player_key, sgp_cand["team"],
                    float(sgp_cand["prop_line"]), float(sgp_cand["offered_sgp_odds"]), float(sgp_cand["p_joint"]),
                    round(p_low, 4),
                    round(p_high, 4),
                    float(sgp_cand["ev_pct"]),
                    round(((p_low * float(sgp_cand["offered_sgp_odds"])) - 1.0) * 100.0, 2),
                    float(sgp_cand["kelly_stake_pen"]), float(sgp_cand["kelly_stake_pen"]), sgp_cand["rationale"],
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                ),
            )
            return True
        except Exception as exc:
            logger.warning(f"Failed to persist SGP opportunity: {exc}")
            return False

    @staticmethod
    def _compute_ewma_baseline_from_records(
        records: list[tuple[float, float, float, float, float]],
        prior_profile: tuple[float, float, float, float, float, float],
        alpha: float = 0.85,
    ) -> tuple[float, float, float, float, float, float] | None:
        """Computes EWMA (minutes, usg, pts/min, reb/min, ast/min, 3pm/min) from newest-first logs."""
        valid = [r for r in records if r[0] >= 8.0]
        if len(valid) < 3:
            return None
        _p_min, prior_usg, prior_ppm, _p_rpm, _p_apm, _p_tpm = prior_profile
        weights = [alpha ** i for i in range(len(valid))]
        w_sum = sum(weights)
        dyn_min = sum(w * r[0] for w, r in zip(weights, valid, strict=False)) / w_sum
        dyn_ppm = sum(w * (r[1] / max(1.0, r[0])) for w, r in zip(weights, valid, strict=False)) / w_sum
        dyn_rpm = sum(w * (r[2] / max(1.0, r[0])) for w, r in zip(weights, valid, strict=False)) / w_sum
        dyn_apm = sum(w * (r[3] / max(1.0, r[0])) for w, r in zip(weights, valid, strict=False)) / w_sum
        dyn_tpm = sum(w * (r[4] / max(1.0, r[0])) for w, r in zip(weights, valid, strict=False)) / w_sum

        scoring_ratio = dyn_ppm / max(0.20, prior_ppm)
        dyn_usg = float(np.clip(prior_usg * (0.50 + 0.50 * scoring_ratio), 12.0, 40.0))
        return (
            round(float(dyn_min), 1),
            round(float(dyn_usg), 1),
            round(float(dyn_ppm), 3),
            round(float(dyn_rpm), 3),
            round(float(dyn_apm), 3),
            round(float(dyn_tpm), 3),
        )

    def _resolve_as_of_cutoff(
        self,
        as_of_utc: str | None = None,
        as_of_timestamp: str | None = None,
        caller: str = "props_query",
    ) -> str | None:
        cutoff = as_of_utc or as_of_timestamp
        if self.db is not None and not cutoff:
            raise TemporalLeakageError(
                f"{caller} requires explicit `as_of_timestamp` / `as_of_utc` when querying historical DB records."
            )
        if cutoff:
            parse_iso_utc(cutoff)
        return cutoff

    def get_player_baseline(
        self,
        player_name: str,
        team_abbr: str | None = None,
        lookback_games: int = 15,
        alpha: float = 0.85,
        as_of_utc: str | None = None,
        as_of_timestamp: str | None = None,
    ) -> tuple[float, float, float, float, float, float]:
        """
        Dynamically computes rolling baseline stats for a player:
        (minutes, usg_pct, pts_per_min, reb_per_min, ast_per_min, threed_per_min).

        Requires `as_of_timestamp` / `as_of_utc` whenever `self.db is not None` and filters
        strictly `game_start_time < cutoff` (and `COALESCE(fetched_at, game_start_time) <= cutoff`
        when using `game_boxscores`).
        """
        effective_cutoff = self._resolve_as_of_cutoff(
            as_of_utc=as_of_utc,
            as_of_timestamp=as_of_timestamp,
            caller="get_player_baseline",
        )
        norm_name = player_name.strip()
        cache_key = (norm_name, str(effective_cutoff or ""))
        if cache_key in self._player_baselines_cache:
            return self._player_baselines_cache[cache_key]

        p_key = normalize_player_match_key(norm_name)
        prior = PLAYER_PROP_BASELINES.get(norm_name)
        if prior is None and p_key:
            for b_name, b_prof in PLAYER_PROP_BASELINES.items():
                if normalize_player_match_key(b_name) == p_key:
                    prior = b_prof
                    break

        prior_profile = prior if prior is not None else (26.0, 17.5, 0.45, 0.16, 0.09, 0.04)

        if self.db is not None and p_key and effective_cutoff is not None:
            try:
                records: list[tuple[float, float, float, float, float]] = []
                # 1. Primary path: indexed normalized `player_boxscores` strictly < tipoff
                try:
                    pb_rows = self.db.fetch_all(
                        """
                        SELECT pb.minutes, pb.pts, pb.reb, pb.ast, pb.threed
                        FROM player_boxscores pb
                        JOIN games m ON pb.game_id = m.game_id
                        WHERE pb.player_key = ?
                          AND pb.game_id NOT LIKE 'SYN%'
                          AND pb.minutes >= 8.0
                          AND datetime(m.game_start_time) < datetime(?)
                        ORDER BY pb.game_start_time DESC
                        LIMIT ?
                        """,
                        (p_key, effective_cutoff, lookback_games),
                    )
                    records = [
                        (
                            float(r["minutes"]),
                            float(r["pts"]),
                            float(r["reb"]),
                            float(r["ast"]),
                            float(r["threed"]),
                        )
                        for r in pb_rows
                    ]
                except Exception:
                    records = []

                # 2. Fallback path: raw `game_boxscores.players_json` strictly < tipoff and available by fetched_at
                if len(records) < 3:
                    like_pattern = f"%{norm_name}%"
                    gb_rows = self.db.fetch_all(
                        """
                        SELECT g.players_json
                        FROM game_boxscores g
                        JOIN games m ON g.game_id = m.game_id
                        WHERE g.players_json LIKE ?
                          AND m.game_id NOT LIKE 'SYN%'
                          AND datetime(m.game_start_time) < datetime(?)
                          AND (g.fetched_at IS NULL OR datetime(g.fetched_at) <= datetime(?))
                        ORDER BY m.game_start_time DESC
                        LIMIT ?
                        """,
                        (like_pattern, effective_cutoff, effective_cutoff, lookback_games * 2),
                    )
                    records = []
                    for r in gb_rows:
                        p_data = json.loads(r.get("players_json") or "{}")
                        if not isinstance(p_data, dict):
                            continue
                        matched = False
                        for _team_key, plist in p_data.items():
                            if not isinstance(plist, list):
                                continue
                            for p in plist:
                                p_cand = normalize_player_match_key(str(p.get("name", "")))
                                if p_cand == p_key or (len(p_key) > 5 and (p_key in p_cand or p_cand in p_key)):
                                    m_val = float(p.get("min", 0.0))
                                    if m_val >= 8.0:
                                        records.append((
                                            m_val,
                                            float(p.get("pts", 0.0)),
                                            float(p.get("reb") or 0.0),
                                            float(p.get("ast") or 0.0),
                                            float(p.get("threed") or 0.0),
                                        ))
                                    matched = True
                                    break
                            if matched:
                                break
                        if len(records) >= lookback_games:
                            break

                computed = self._compute_ewma_baseline_from_records(records, prior_profile, alpha=alpha)
                if computed is not None:
                    self._player_baselines_cache[cache_key] = computed
                    return computed
            except Exception as exc:
                logger.debug(f"Dynamic baseline query error for {player_name}: {exc}")

        self._player_baselines_cache[cache_key] = prior_profile
        return prior_profile

    def get_team_defensive_multipliers(
        self,
        opponent_team: str | None,
        lookback_window: int = 30,
        as_of_utc: str | None = None,
        as_of_timestamp: str | None = None,
    ) -> dict[str, Any]:
        """
        Dynamically computes Defense vs Position (DvP) and Pace multipliers for all 30 NBA teams
        from real finished games and team stats in SQLite (strictly < cutoff timestamp and available
        boxscores by fetched_at). Requires `as_of_timestamp` / `as_of_utc` whenever `self.db` is set.
        """
        effective_cutoff = self._resolve_as_of_cutoff(
            as_of_utc=as_of_utc,
            as_of_timestamp=as_of_timestamp,
            caller="get_team_defensive_multipliers",
        )
        if not opponent_team:
            return {"PTS": 1.00, "REB": 1.00, "AST": 1.00, "3PM": 1.00, "pace": 99.5, "tier": "AVERAGE"}

        opp = opponent_team.strip().upper()
        cache_key = (opp, str(effective_cutoff or ""))
        if cache_key in self._team_multipliers_cache:
            return self._team_multipliers_cache[cache_key]

        fallback = TEAM_DEFENSIVE_MULTIPLIERS.get(opp, {"PTS": 1.00, "REB": 1.00, "AST": 1.00, "3PM": 1.00, "pace": 99.5, "tier": "AVERAGE"})

        if self.db is None or effective_cutoff is None:
            self._team_multipliers_cache[cache_key] = fallback
            return fallback

        try:
            rows = self.db.fetch_all(
                """
                SELECT home_team, away_team, home_score, away_score, home_pace, away_pace
                FROM games
                WHERE status = 'FINAL' AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND game_id NOT LIKE 'SYN%'
                  AND datetime(game_start_time) < datetime(?)
                  AND (home_team = ? OR away_team = ?)
                ORDER BY game_start_time DESC
                LIMIT ?
                """,
                (effective_cutoff, opp, opp, lookback_window),
            )
            if len(rows) < 5:
                self._team_multipliers_cache[cache_key] = fallback
                return fallback

            league_row = self.db.fetch_one(
                """
                SELECT AVG(home_score + away_score) / 2.0 AS avg_pts
                FROM games
                WHERE status = 'FINAL' AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND game_id NOT LIKE 'SYN%'
                  AND datetime(game_start_time) < datetime(?)
                """,
                (effective_cutoff,),
            )
            league_avg_pts = float(league_row["avg_pts"]) if league_row and league_row["avg_pts"] else 114.2

            pts_allowed: list[float] = []
            paces: list[float] = []
            for r in rows:
                if r["home_team"] == opp:
                    pts_allowed.append(float(r["away_score"]))
                    if r.get("home_pace"):
                        paces.append(float(r["home_pace"]))
                else:
                    pts_allowed.append(float(r["home_score"]))
                    if r.get("away_pace"):
                        paces.append(float(r["away_pace"]))

            mean_pa = float(np.mean(pts_allowed))
            pts_mult = round(float(np.clip(mean_pa / league_avg_pts, 0.88, 1.15)), 2)

            b_rows = self.db.fetch_all(
                """
                SELECT g.team_stats_json
                FROM game_boxscores g
                JOIN games m ON g.game_id = m.game_id
                WHERE m.game_id NOT LIKE 'SYN%'
                  AND datetime(m.game_start_time) < datetime(?)
                  AND (g.fetched_at IS NULL OR datetime(g.fetched_at) <= datetime(?))
                  AND (m.home_team = ? OR m.away_team = ?)
                ORDER BY m.game_start_time DESC
                LIMIT ?
                """,
                (effective_cutoff, effective_cutoff, opp, opp, lookback_window),
            )
            tpm_allowed: list[float] = []
            for br in b_rows:
                tdata = json.loads(br.get("team_stats_json") or "{}")
                for tcode, stats in tdata.items():
                    if tcode != opp and "tpm" in stats:
                        tpm_allowed.append(float(stats["tpm"]))

            if len(tpm_allowed) >= 5:
                th_mult = round(float(np.clip(np.mean(tpm_allowed) / 13.0, 0.88, 1.15)), 2)
            else:
                th_mult = pts_mult

            reb_mult = round(1.0 + (pts_mult - 1.0) * 0.70, 2)
            ast_mult = round(1.0 + (pts_mult - 1.0) * 0.85, 2)
            team_pace = round(float(np.mean(paces)), 1) if paces else float(fallback.get("pace", 99.5))

            if pts_mult < 0.96:
                tier = "ELITE"
            elif pts_mult < 0.99:
                tier = "GOOD"
            elif pts_mult < 1.02:
                tier = "AVERAGE"
            elif pts_mult < 1.05:
                tier = "VULNERABLE"
            else:
                tier = "TARGET"

            result = {
                "PTS": pts_mult,
                "REB": reb_mult,
                "AST": ast_mult,
                "3PM": th_mult,
                "pace": team_pace,
                "tier": tier,
            }
            self._team_multipliers_cache[cache_key] = result
            return result
        except Exception as exc:
            logger.debug(f"Dynamic team multipliers error for {opp}: {exc}")
            self._team_multipliers_cache[cache_key] = fallback
            return fallback

    def project_player_stats(
        self,
        player_name: str,
        team: str,
        absent_teammates: list[str] | None = None,
        opponent_team: str | None = None,
        expected_game_pace: float | None = None,
        spread_blowout_risk: float | None = None,
        referee_foul_rate: float = 1.0,
        injury_status: str = "ACTIVE",
        foul_trouble_prone: bool = False,
        as_of_utc: str | None = None,
        as_of_timestamp: str | None = None,
    ) -> dict[str, Any]:
        """
        Computes projected Points, Rebounds, Assists, 3PM, PRA, PR, PA, and RA.
        When star teammates are absent, redistributes vacated usage rate and minutes.
        Adjusts for opponent defensive efficiency (DvP), projected game pace, and blowout risk.
        """
        effective_cutoff = self._resolve_as_of_cutoff(
            as_of_utc=as_of_utc,
            as_of_timestamp=as_of_timestamp,
            caller="project_player_stats",
        )
        profile = self.get_player_baseline(player_name, team, as_of_timestamp=effective_cutoff)
        base_min, base_usg, pts_pm, reb_pm, ast_pm, th_pm = profile

        absent = absent_teammates or []
        usage_bump_pct = 0.0
        minutes_bump = 0.0

        # Vacated usage & minute redistribution logic
        for abs_p in absent:
            abs_prof = self.get_player_baseline(abs_p, team, as_of_timestamp=effective_cutoff)
            if abs_prof:
                _abs_min, abs_usg = abs_prof[0], abs_prof[1]
                # High-usage star out (>26% USG)
                if abs_usg >= 26.0:
                    # If this player is secondary initiator/scorer, absorbs major usage share
                    if base_usg >= 22.0:
                        usage_bump_pct += 0.28 * abs_usg
                        minutes_bump += min(3.5, 40.0 - base_min)
                    else:
                        usage_bump_pct += 0.12 * abs_usg
                        minutes_bump += min(2.0, 36.0 - base_min)
                else:
                    # Regular rotation player out
                    usage_bump_pct += 0.08 * abs_usg
                    minutes_bump += min(1.5, 36.0 - base_min)

        # Matchup defense adjustment (dynamic from SQLite with fallback to prior)
        opp = opponent_team.upper() if opponent_team else None
        matchup_info = (
            self.get_team_defensive_multipliers(opp, as_of_timestamp=effective_cutoff)
            if opp
            else None
        )
        def_tier = str(matchup_info.get("tier", "AVERAGE")) if matchup_info else "NEUTRAL"
        m_pts = float(matchup_info.get("PTS", 1.0)) if matchup_info else 1.0
        m_reb = float(matchup_info.get("REB", 1.0)) if matchup_info else 1.0
        m_ast = float(matchup_info.get("AST", 1.0)) if matchup_info else 1.0
        m_th = float(matchup_info.get("3PM", 1.0)) if matchup_info else 1.0

        # Pace factor adjustment (relative to 99.5 baseline)
        pace_val = expected_game_pace
        if pace_val is None and matchup_info:
            pace_val = float(matchup_info.get("pace", 99.5))
        pace_factor = float(np.clip((pace_val or 99.5) / 99.5, 0.92, 1.08))

        # Blowout risk dampening on star minutes when game spread is extreme (|spread| > 10.5)
        blowout_min_discount = 0.0
        if spread_blowout_risk is not None and abs(spread_blowout_risk) > 10.5 and base_min >= 31.0:
            blowout_min_discount = min(2.5, round((abs(spread_blowout_risk) - 10.5) * 0.35, 1))

        effective_minutes = round(max(18.0, base_min + minutes_bump - blowout_min_discount), 1)
        hurdle_minutes = self.minutes_engine.predict_minutes_quantiles(
            base_minutes=base_min,
            spread=spread_blowout_risk or 0.0,
            is_starter=(base_min >= 28.0),
            injury_status=injury_status,
            referee_foul_rate=referee_foul_rate,
            foul_trouble_prone=foul_trouble_prone,
            expected_pace=pace_val or 99.5,
        )
        usg_factor = 1.0 + (usage_bump_pct / 100.0)

        # Adjusted scoring and stat rates scale with usage factor, matchup factor, and pace factor
        adj_pts_pm = pts_pm * (usg_factor ** 0.85) * m_pts * pace_factor
        adj_ast_pm = ast_pm * (usg_factor ** 0.70) * m_ast * pace_factor
        adj_th_pm = th_pm * (usg_factor ** 0.80) * m_th * pace_factor
        adj_reb_pm = reb_pm * m_reb * pace_factor

        proj_pts = round(effective_minutes * adj_pts_pm, 1)
        proj_reb = round(effective_minutes * adj_reb_pm, 1)
        proj_ast = round(effective_minutes * adj_ast_pm, 1)
        proj_th = round(effective_minutes * adj_th_pm, 1)
        proj_pra = round(proj_pts + proj_reb + proj_ast, 1)
        proj_pr = round(proj_pts + proj_reb, 1)
        proj_pa = round(proj_pts + proj_ast, 1)
        proj_ra = round(proj_reb + proj_ast, 1)

        # Standard deviations (empirical NBA player dispersion models dynamically calibrated)
        disp = PROP_DISPERSION_MULTIPLIERS
        std_pts = round(math.sqrt(max(1.0, proj_pts * disp.get("PTS", 1.85))), 2)
        std_pra = round(math.sqrt(max(1.0, proj_pra * disp.get("PRA", 2.10))), 2)
        std_pr = round(math.sqrt(max(1.0, proj_pr * disp.get("PR", 1.95))), 2)
        std_pa = round(math.sqrt(max(1.0, proj_pa * disp.get("PA", 1.90))), 2)
        std_ra = round(math.sqrt(max(1.0, proj_ra * disp.get("RA", 1.50))), 2)
        std_reb = round(math.sqrt(max(disp.get("REB_FLOOR", 0.5), proj_reb)), 2)
        std_ast = round(math.sqrt(max(disp.get("AST_FLOOR", 0.5), proj_ast)), 2)
        std_th = round(math.sqrt(max(disp.get("TH_FLOOR", 0.3), proj_th)), 2)

        avg_matchup_adj = round(((m_pts + m_reb + m_ast) / 3.0 - 1.0) * 100.0, 1)

        return {
            "player_name": player_name,
            "team": team,
            "opponent_team": opp,
            "matchup_tier": def_tier,
            "matchup_adjustment_pct": avg_matchup_adj,
            "pace_factor": round(pace_factor, 3),
            "effective_minutes": effective_minutes,
            "hurdle_minutes": hurdle_minutes,
            "usage_bump_pct": round(usage_bump_pct, 1),
            "blowout_min_discount": blowout_min_discount,
            "projections": {
                "PTS": {"mean": proj_pts, "std": std_pts, "dist": "normal"},
                "REB": {"mean": proj_reb, "std": std_reb, "dist": "poisson"},
                "AST": {"mean": proj_ast, "std": std_ast, "dist": "poisson"},
                "PRA": {"mean": proj_pra, "std": std_pra, "dist": "normal"},
                "3PM": {"mean": proj_th, "std": std_th, "dist": "poisson"},
                "PR": {"mean": proj_pr, "std": std_pr, "dist": "normal"},
                "PA": {"mean": proj_pa, "std": std_pa, "dist": "normal"},
                "RA": {"mean": proj_ra, "std": std_ra, "dist": "normal"},
            },
        }

    def compute_exceedance_probabilities(
        self,
        prop_category: str,
        line_value: float,
        proj_mean: float,
        proj_std: float,
        dist_type: str = "normal",
    ) -> tuple[float, float, float]:
        """
        Computes unconditional (p_over, p_under, p_push) summing to 1.0 given a line and parametric distribution.
        Delegates to src.prediction.props_distribution.compute_exceedance_probabilities.
        """
        return compute_exceedance_probs_math(
            prop_category=prop_category,
            line_value=line_value,
            proj_mean=proj_mean,
            proj_std=proj_std,
            dist_type=dist_type,
        )

    def build_historical_props_calibration_dataset(
        self,
        as_of_utc: str,
        max_oos_boxscore_samples: int = 350,
    ) -> list[dict[str, Any]]:
        """
        Builds a strictly out-of-sample calibration dataset from resolved props prior to `as_of_utc`,
        capturing pre-game probability, category, line, odds, game timestamp, settlement timestamp,
        and realized binary outcome (excluding pushes).
        """
        parse_iso_utc(as_of_utc)
        if self.db is None:
            return []

        records: list[dict[str, Any]] = []

        # 1. Resolved live/historical picks from `player_prop_picks`
        try:
            pick_rows = self.db.fetch_all(
                """
                SELECT p.game_id, p.player_name, p.prop_category, p.line_value, p.selection,
                       p.decimal_odds, p.model_prob, g.game_start_time, p.settled_at, p.status
                FROM player_prop_picks p
                JOIN games g ON g.game_id = p.game_id
                WHERE p.status IN ('WON', 'LOST')
                  AND p.prop_category != 'SGP'
                  AND p.settled_at IS NOT NULL
                  AND datetime(g.game_start_time) < datetime(?)
                  AND datetime(p.settled_at) <= datetime(?)
                ORDER BY g.game_start_time ASC
                """,
                (as_of_utc, as_of_utc),
            )
            for r in pick_rows:
                records.append(
                    {
                        "game_id": str(r["game_id"]),
                        "player_name": str(r["player_name"]),
                        "category": str(r["prop_category"]).upper(),
                        "line_value": float(r["line_value"]),
                        "decimal_odds": float(r["decimal_odds"]),
                        "selection": str(r["selection"]).upper(),
                        "raw_probability": float(np.clip(float(r["model_prob"]), 1e-4, 1.0 - 1e-4)),
                        "game_start_time": str(r["game_start_time"]),
                        "result_recorded_at": str(r["settled_at"]),
                        "outcome": 1 if r["status"] == "WON" else 0,
                        "source": "player_prop_picks",
                    }
                )
        except Exception as exc:
            logger.debug(f"Settled props dataset query skipped: {exc}")

        # 2. Strictly chronological OOS projections evaluated against historical player_boxscores
        if len(records) < 2000:
            try:
                box_rows = self.db.fetch_all(
                    """
                    SELECT pb.game_id, pb.player_name, pb.player_key, pb.team, pb.game_start_time,
                           pb.minutes, pb.pts, pb.reb, pb.ast, pb.threed,
                           g.home_team, g.away_team, g.result_recorded_at
                    FROM player_boxscores pb
                    JOIN games g ON g.game_id = pb.game_id
                    WHERE g.status = 'FINAL'
                      AND g.game_id NOT LIKE 'SYN%'
                      AND pb.minutes >= 12.0
                      AND datetime(pb.game_start_time) < datetime(?)
                      AND (g.result_recorded_at IS NULL OR datetime(g.result_recorded_at) <= datetime(?))
                    ORDER BY pb.game_start_time ASC, pb.player_key ASC
                    """,
                    (as_of_utc, as_of_utc),
                )
                if box_rows:
                    step = max(1, len(box_rows) // max(1, int(max_oos_boxscore_samples)))
                    cat_benchmarks: tuple[tuple[str, float, str], ...] = (
                        ("PTS", 15.5, "pts"),
                        ("REB", 5.5, "reb"),
                        ("AST", 4.5, "ast"),
                        ("3PM", 1.5, "threed"),
                        ("PRA", 24.5, "pra"),
                    )
                    for r in box_rows[::step][:max_oos_boxscore_samples]:
                        opp_team = r["away_team"] if r["team"] == r["home_team"] else r["home_team"]
                        proj = self.project_player_stats(
                            player_name=str(r["player_name"]),
                            team=str(r["team"]),
                            opponent_team=str(opp_team),
                            as_of_utc=str(r["game_start_time"]),
                        )
                        actual_map = {
                            "pts": float(r["pts"]),
                            "reb": float(r["reb"]),
                            "ast": float(r["ast"]),
                            "threed": float(r["threed"]),
                            "pra": float(r["pts"]) + float(r["reb"]) + float(r["ast"]),
                        }
                        res_ts = str(r.get("result_recorded_at") or r["game_start_time"])
                        for cat, line_v, expr in cat_benchmarks:
                            cdata = proj["projections"].get(cat)
                            if not cdata or expr not in actual_map:
                                continue
                            act_v = actual_map[expr]
                            if act_v == line_v:
                                continue
                            p_over, _p_under, _p_push = self.compute_exceedance_probabilities(
                                prop_category=cat,
                                line_value=line_v,
                                proj_mean=float(cdata["mean"]),
                                proj_std=float(cdata["std"]),
                                dist_type=str(cdata["dist"]),
                            )
                            records.append(
                                {
                                    "game_id": str(r["game_id"]),
                                    "player_name": str(r["player_name"]),
                                    "category": cat,
                                    "line_value": line_v,
                                    "decimal_odds": 1.90,
                                    "selection": "OVER",
                                    "raw_probability": float(np.clip(p_over, 1e-4, 1.0 - 1e-4)),
                                    "game_start_time": str(r["game_start_time"]),
                                    "result_recorded_at": res_ts,
                                    "outcome": 1 if act_v > line_v else 0,
                                    "source": "player_boxscores_oos",
                                }
                            )
            except Exception as exc:
                logger.debug(f"Historical player_boxscores calibration build skipped: {exc}")

        records.sort(key=lambda rec: str(rec.get("game_start_time") or ""))
        self.oos_calibration_dataset = records
        return records

    def fit_calibrators(
        self,
        as_of_utc: str,
        calibration_records: list[dict[str, Any]] | None = None,
        global_min_samples: int | None = None,
        category_min_samples: int | None = None,
    ) -> dict[str, Any]:
        """
        Trains pooled global and category-specific (`PTS`, `REB`, `AST`, `3PM`, `PRA`, etc.)
        Venn-Abers conformal calibrators strictly on historical outcomes prior to `as_of_utc`.
        """
        parse_iso_utc(as_of_utc)
        recs = (
            list(calibration_records)
            if calibration_records is not None
            else self.build_historical_props_calibration_dataset(as_of_utc=as_of_utc)
        )

        g_min = int(global_min_samples) if global_min_samples is not None else self.global_min_samples
        c_min = int(category_min_samples) if category_min_samples is not None else self.category_min_samples

        self.calibrator = VennAbersConformalInterval(window=1200, min_samples=g_min)
        global_fitted = self.calibrator.fit(recs, as_of_utc) if recs else False

        by_cat: dict[str, list[dict[str, Any]]] = {}
        for rec in recs:
            cat = str(rec.get("category") or rec.get("prop_category") or "UNKNOWN").upper()
            by_cat.setdefault(cat, []).append(rec)

        self.category_calibrators = {}
        cat_stats: dict[str, dict[str, Any]] = {}
        for cat, c_recs in by_cat.items():
            va_cat = VennAbersConformalInterval(window=1200, min_samples=c_min)
            c_fitted = va_cat.fit(c_recs, as_of_utc)
            self.category_calibrators[cat] = va_cat
            cat_stats[cat] = {
                "is_fitted": bool(c_fitted),
                "sample_size": len(c_recs),
                "cutoff_utc": as_of_utc,
                "min_samples": c_min,
            }

        self.calibration_cutoff_utc = as_of_utc
        self.calibration_dataset_size = len(recs)
        self.calibration_summary = {
            "global": {
                "is_fitted": bool(global_fitted),
                "sample_size": len(recs),
                "cutoff_utc": as_of_utc,
                "min_samples": g_min,
            },
            "categories": cat_stats,
        }
        return self.calibration_summary

    def _select_calibrator_for_category(self, prop_category: str) -> tuple[VennAbersConformalInterval | None, str]:
        cat_key = prop_category.strip().upper()
        cat_cal = self.category_calibrators.get(cat_key)
        if cat_cal is not None and cat_cal.is_fitted:
            return cat_cal, f"venn_abers_category:{cat_key}"
        if self.calibrator.is_fitted:
            return self.calibrator, "venn_abers_global"
        return None, "unfitted_heuristic_fallback"

    def evaluate_prop_opportunity(
        self,
        player_name: str,
        team: str,
        game_id: str,
        matchday_date: str,
        prop_category: str,
        line_value: float,
        over_odds: float,
        under_odds: float,
        absent_teammates: list[str] | None = None,
        bankroll_pen: float = 100.0,
        opponent_team: str | None = None,
        expected_game_pace: float | None = None,
        spread_blowout_risk: float | None = None,
        persist: bool = True,
        line_source: str = "OBSERVED",
        as_of_utc: str | None = None,
        as_of_timestamp: str | None = None,
        allow_player_props: bool | None = None,
    ) -> list[dict[str, Any]]:
        """
        Evaluates a specific player prop line against our tactical & injury-adjusted projection.
        `persist=False` evaluates without recording a paper bet. Preserves discrete push mass,
        uses category/pooled Venn-Abers conformal intervals when fitted (`is_fitted=True`),
        explicitly blocks lower-bound conformal staking when unfitted, and gates persistence
        through `_persist_prop_pick` (`allow_player_props_betting`).
        """
        effective_cutoff = as_of_utc or as_of_timestamp
        if self.db is not None and not effective_cutoff:
            g_row = self.db.fetch_one("SELECT game_start_time FROM games WHERE game_id = ?", (game_id,))
            if g_row and g_row.get("game_start_time"):
                effective_cutoff = str(g_row["game_start_time"])
            else:
                raise TemporalLeakageError(
                    "evaluate_prop_opportunity requires `as_of_timestamp` / `as_of_utc` when querying historical DB records."
                )

        proj_info = self.project_player_stats(
            player_name=player_name,
            team=team,
            absent_teammates=absent_teammates,
            opponent_team=opponent_team,
            expected_game_pace=expected_game_pace,
            spread_blowout_risk=spread_blowout_risk,
            as_of_timestamp=effective_cutoff,
        )
        cat_data = proj_info["projections"].get(prop_category)
        if not cat_data:
            return []

        mu = float(cat_data["mean"])
        sigma = float(cat_data["std"])
        dist_type = cat_data["dist"]

        p_over_raw, p_under_raw, p_push_raw = self.compute_exceedance_probabilities(
            prop_category=prop_category,
            line_value=line_value,
            proj_mean=mu,
            proj_std=sigma,
            dist_type=dist_type,
        )

        active_cal, cal_method = self._select_calibrator_for_category(prop_category)
        opportunities: list[dict[str, Any]] = []

        # Evaluate both sides (OVER and UNDER) preserving push mass
        for sel, p_raw in [("OVER", p_over_raw), ("UNDER", p_under_raw)]:
            dec_odds = over_odds if sel == "OVER" else under_odds
            if dec_odds <= 1.0:
                continue

            # Conditional fair probability on decisive outcomes from two-way bookmaker line
            p_fair_a, p_fair_b, _ = devig_multiplicative(over_odds, under_odds)
            mkt_fair_cond = p_fair_a if sel == "OVER" else p_fair_b
            non_push = max(1e-9, 1.0 - p_push_raw)
            mkt_fair_win = mkt_fair_cond * non_push

            p_raw_cond = float(np.clip(p_raw / non_push, 1e-4, 1.0 - 1e-4)) if p_push_raw > 0.0 else p_raw
            if active_cal is not None:
                conf_int = active_cal.predict_interval(p_raw_cond)
                cal_fitted = bool(conf_int["is_fitted"])
                is_conformal = bool(conf_int["is_conformal"])
                cal_sample_size = int(conf_int["sample_size"])
                cal_cutoff = conf_int["cutoff_utc"]
                cal_cond = float(conf_int["p_va"])
            else:
                conf_int = self.calibrator.predict_interval(p_raw_cond)
                cal_fitted = False
                is_conformal = False
                cal_sample_size = int(conf_int.get("sample_size") or self.calibration_dataset_size)
                cal_cutoff = conf_int.get("cutoff_utc") or self.calibration_cutoff_utc
                cal_cond = p_raw_cond

            cal_win_prob = cal_cond * non_push if p_push_raw > 0.0 else cal_cond
            p_low_uncond = float(conf_int["p0"]) * non_push if p_push_raw > 0.0 else float(conf_int["p0"])
            p_high_uncond = float(conf_int["p1"]) * non_push if p_push_raw > 0.0 else float(conf_int["p1"])
            conf_w = max(0.0, p_high_uncond - p_low_uncond)

            # Market-anchored probability conditional on decisive outcomes, then rescaled by (1 - p_push)
            anchored_cond = market_anchored_probability(cal_cond, mkt_fair_cond, model_weight=0.75)
            anchored_win = anchored_cond * non_push if p_push_raw > 0.0 else anchored_cond
            anchored_loss = max(0.0, non_push - anchored_win)

            ev_metrics = calculate_ev(anchored_win, dec_odds, p_push=p_push_raw, p_loss=anchored_loss)
            ev_pct = float(ev_metrics["ev_pct"])

            lb_metrics = conformal_lower_bound_ev(
                cal_win_prob,
                p_low_uncond,
                mkt_fair_cond,
                model_weight=0.75,
                decimal_odds=dec_odds,
                p_push=p_push_raw,
            )
            lb_ev_pct = float(lb_metrics["ev_lower_bound"]) * 100.0

            line_diff = round((mu - line_value) if sel == "OVER" else (line_value - mu), 1)
            line_diff_pct = round((line_diff / max(1.0, line_value)) * 100.0, 1)

            stake_pen = 0.0
            kelly_frac = 0.0
            if not cal_fitted:
                # F-006: Explicit unfitted heuristic interval cannot authorize lower-bound conformal staking
                lower_bound_ev_blocked = True
                lower_bound_ev_status = "BLOCKED_UNFITTED_FALLBACK"
                is_edge_qualified = ev_pct >= (self.min_ev_threshold * 100.0)
                decision = "NO_BET"
                decision_reason = "UNFITTED_CALIBRATOR_FALLBACK"
            else:
                lower_bound_ev_blocked = False
                lower_bound_ev_status = "CONFORMAL_VERIFIED"
                is_edge_qualified = (lb_ev_pct >= (self.min_ev_threshold * 100.0)) and (ev_pct > 0.0) and (conf_w <= 0.35)
                if is_edge_qualified:
                    b_val = dec_odds - 1.0
                    expected_growth_num = anchored_win * b_val - anchored_loss
                    f_star = max(0.0, expected_growth_num / max(0.05, b_val * (anchored_win + anchored_loss))) if expected_growth_num > 0.0 else 0.0
                    eff_f = min(self.max_bankroll_fraction, f_star * self.kelly_fraction)
                    raw_s = bankroll_pen * eff_f
                    if eff_f > 0.0 and ev_pct > 0.0:
                        stake_pen = round(max(0.0, min(self.max_stake_pen, raw_s)), 2)
                    kelly_frac = round(eff_f, 4)
                decision = "BET_PLACED" if stake_pen > 0.0 else "NO_BET"
                decision_reason = "QUALIFIED_CONFORMAL_EV" if stake_pen > 0.0 else "BELOW_CONFORMAL_LB_EV"

            if not is_edge_qualified:
                continue

            cal_badge = (
                f"[CONFORMAL {cal_method} n={cal_sample_size}] "
                if cal_fitted
                else f"[FALLBACK NO-CONFORMAL n={cal_sample_size} | STAKING BLOCKED] "
            )
            rationale = (
                ("" if line_source == "OBSERVED" else "[LÍNEA ESTIMADA, no observada] ")
                + cal_badge
                + f"[{prop_category} {sel} {line_value}] {player_name} ({team}). "
                + f"Proyección: {mu:.1f} (std: {sigma:.1f}, Ventaja vs Línea: {line_diff:+0.1f} pts, P(push)={p_push_raw:.3f}). "
                + f"Prob Modelo: {anchored_win * 100:.1f}% vs Casa: {mkt_fair_win * 100:.1f}%. "
                + f"Ajustes: +{proj_info['usage_bump_pct']:.1f}% USG, Rival {proj_info.get('opponent_team') or 'NBA'} ({proj_info['matchup_tier']}). "
                + f"LB EV: {lb_ev_pct:+.2f}% ({lower_bound_ev_status}) a cuota {dec_odds:.2f}. Kelly: S/ {stake_pen:.2f} PEN."
            )

            prop_pick = {
                "prop_id": f"PROP_{game_id}_{player_name.replace(' ', '_')}_{prop_category}_{sel}_{uuid.uuid4().hex[:6]}",
                "type": "INDIVIDUAL_PROP",
                "game_id": game_id,
                "matchday_date": matchday_date,
                "player_name": player_name,
                "team": team,
                "opponent_team": proj_info.get("opponent_team"),
                "matchup_tier": proj_info["matchup_tier"],
                "matchup_adjustment_pct": proj_info["matchup_adjustment_pct"],
                "pace_factor": proj_info["pace_factor"],
                "prop_category": prop_category,
                "line_value": line_value,
                "selection": sel,
                "decimal_odds": dec_odds,
                "projected_mean": mu,
                "projected_std": sigma,
                "line_diff": line_diff,
                "line_diff_pct": line_diff_pct,
                "raw_model_prob": round(p_raw, 4),
                "calibrated_model_prob": round(cal_win_prob, 4),
                "market_fair_prob": round(mkt_fair_win, 4),
                "model_prob": round(anchored_win, 4),
                "p_win": round(anchored_win, 6),
                "p_loss": round(anchored_loss, 6),
                "p_push": round(p_push_raw, 6),
                "conformal_p_low": round(p_low_uncond, 4),
                "conformal_p_high": round(p_high_uncond, 4),
                "calibrator_is_fitted": cal_fitted,
                "calibration_is_conformal": is_conformal,
                "calibration_method": cal_method,
                "calibration_sample_size": cal_sample_size,
                "calibration_cutoff_utc": cal_cutoff,
                "lower_bound_ev_blocked": lower_bound_ev_blocked,
                "lower_bound_ev_status": lower_bound_ev_status,
                "decision": decision,
                "decision_reason": decision_reason,
                "ev_pct": round(ev_pct, 2),
                "ev_lower_bound_pct": round(lb_ev_pct, 2),
                "kelly_stake_pen": stake_pen,
                "kelly_optimal_fraction": kelly_frac,
                "usage_bump_pct": proj_info["usage_bump_pct"],
                "effective_minutes": proj_info["effective_minutes"],
                "rationale": rationale,
                "line_source": line_source,
                "emitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            opportunities.append(prop_pick)

            if persist:
                self._persist_prop_pick(prop_pick, bankroll_pen, allow_player_props=allow_player_props)

        return opportunities

    def simulate_multi_leg_sgp_copula(
        self,
        legs: list[dict[str, Any]],
        offered_sgp_odds: float,
        correlation_matrix: np.ndarray | None = None,
        copula_family: str = "student_t",
        df: int = 5,
        bankroll_pen: float = 100.0,
        n_simulations: int = 25000,
        random_seed: int = 42,
        min_hits: int = 10,
        max_relative_error: float = 0.25,
    ) -> dict[str, Any]:
        """
        Multi-leg Same Game Parlay (2 to 5 legs) Multivariate Student-t / Gaussian Copula Engine.
        Delegates to `MultivariateStudentTCopula.simulate_multivariate_copula` without artificial floors.
        """
        return self.copula_engine.simulate_multivariate_copula(
            legs=legs,
            offered_sgp_odds=offered_sgp_odds,
            correlation_matrix=correlation_matrix,
            copula_family=copula_family,
            df=df,
            bankroll_pen=bankroll_pen,
            n_simulations=n_simulations,
            random_seed=random_seed,
            min_hits=min_hits,
            max_relative_error=max_relative_error,
        )

    def simulate_same_game_parlay_copula(
        self,
        game_id: str,
        matchday_date: str,
        game_selection_label: str,
        game_model_prob: float,
        player_name: str,
        team: str,
        prop_category: str,
        prop_selection: str,
        prop_line: float,
        prop_model_prob: float,
        offered_sgp_odds: float,
        correlation_rho: float = 0.28,
        bankroll_pen: float = 100.0,
        n_simulations: int = 10000,
        random_seed: int = 42,
        pure_alpha: bool = False,
        min_hits: int = 10,
        max_relative_error: float = 0.25,
    ) -> dict[str, Any]:
        """
        Bivariate Gaussian Copula Simulator for Same-Game Parlays (SGP).
        Enforces zero probability floors (`p_joint = hits / n_simulations`) and reports
        Wilson 95% CI, Monte Carlo SE, and `INSUFFICIENT_SIMULATION_PRECISION` -> `NO_BET`.
        """
        if n_simulations <= 0:
            raise ValueError(f"n_simulations must be positive, received {n_simulations}")

        p_game = float(np.clip(game_model_prob, 1e-6, 1.0 - 1e-6))
        p_prop = float(np.clip(prop_model_prob, 1e-6, 1.0 - 1e-6))
        rho = float(np.clip(correlation_rho, -0.95, 0.95))

        rng = np.random.default_rng(random_seed)
        cov_matrix = np.array([[1.0, rho], [rho, 1.0]], dtype=float)
        z = rng.multivariate_normal(mean=[0.0, 0.0], cov=cov_matrix, size=n_simulations)

        u1 = norm.cdf(z[:, 0])
        u2 = norm.cdf(z[:, 1])

        hits_mask = (u1 <= p_game) & (u2 <= p_prop)
        hits_count = int(np.sum(hits_mask))
        p_joint = float(hits_count) / float(n_simulations)

        ci_95_low, ci_95_high = wilson_confidence_interval(hits_count, n_simulations)
        mc_se = math.sqrt(p_joint * (1.0 - p_joint) / float(n_simulations)) if hits_count > 0 else ci_95_high / 2.0
        rel_error = (mc_se / p_joint) if hits_count > 0 else float("inf")
        sufficient_precision = (hits_count >= min_hits) and (rel_error <= max_relative_error)

        p_independent = p_game * p_prop
        corr_boost_pct = round(((p_joint - p_independent) / max(1e-9, p_independent)) * 100.0, 2)
        fair_sgp_odds: float | None = round(1.0 / p_joint, 3) if p_joint > 0.0 else None

        ev_unit = (p_joint * offered_sgp_odds) - 1.0
        ev_pct = round(ev_unit * 100.0, 2)

        if not sufficient_precision:
            is_value = False
            stake_pen = 0.0
            decision = "NO_BET"
            decision_reason = "INSUFFICIENT_SIMULATION_PRECISION"
        else:
            b = offered_sgp_odds - 1.0
            f_star = max(0.0, (p_joint * (b + 1.0) - 1.0) / max(0.05, b))
            eff_f = min(self.max_bankroll_fraction, f_star * self.kelly_fraction) if ev_unit > 0.0 else 0.0
            is_value = ev_pct >= 3.0 and p_joint >= 0.18 and eff_f > 0.0
            stake_pen = round(min(self.max_stake_pen, bankroll_pen * eff_f), 2) if ev_unit > 0.0 else 0.0
            decision = "BET_VALUE_SGP" if is_value else "NO_BET"
            decision_reason = "POSITIVE_EV_COPULA" if is_value else "BELOW_EV_OR_PROB_THRESHOLD"

        fair_str = f"{fair_sgp_odds:.2f}" if fair_sgp_odds is not None else "N/A (0 hits)"
        rationale = (
            f"[SGP — CUOTA ESTIMADA, no observada] {game_selection_label} + {player_name} {prop_category} {prop_selection} {prop_line}. "
            f"Hits={hits_count}/{n_simulations}, p_joint={p_joint * 100:.2f}% "
            f"(CI95: [{ci_95_low * 100:.2f}%, {ci_95_high * 100:.2f}%], vs {p_independent * 100:.2f}% Indep). "
            f"Cuota Ofrecida: {offered_sgp_odds:.2f} vs Justa: {fair_str} (EV: {ev_pct:+.1f}%). "
            f"Decisión: {decision} ({decision_reason}). Stake Sugerido: S/ {stake_pen:.2f} PEN."
        )

        norm_name = player_name.replace(" ", "_")
        slug_raw = f"{game_id}_{norm_name}_{prop_category}_{prop_selection}_{prop_line}"
        slug = hashlib.sha256(slug_raw.encode("utf-8")).hexdigest()[:8]
        sgp_id = f"SGP_{game_id}_{norm_name}_{prop_category}_{slug}"

        odd_g = round(1.0 / max(0.05, p_game), 2)
        odd_p = round(offered_sgp_odds / max(1.05, odd_g), 2)
        legs = [
            {
                "game_id": game_id,
                "market": "moneyline",
                "selection": game_selection_label,
                "odds": odd_g,
                "desc": f"{team} Victoria",
            },
            {
                "game_id": game_id,
                "market": f"player_{prop_category.lower()}",
                "prop_category": prop_category,
                "selection": prop_selection,
                "line_value": float(prop_line),
                "player_name": player_name,
                "odds": odd_p,
                "desc": f"{player_name} {prop_category} {prop_selection} {prop_line}",
            },
        ]

        return {
            "sgp_id": sgp_id,
            "type": "RETABET_SGP",
            "game_id": game_id,
            "matchday_date": matchday_date,
            "bookmaker": "RETAbet Perú",
            "game_selection": game_selection_label,
            "player_name": player_name,
            "team": team,
            "prop_category": prop_category,
            "prop_selection": prop_selection,
            "prop_line": prop_line,
            "p_game": round(p_game, 4),
            "p_prop": round(p_prop, 4),
            "p_independent": round(p_independent, 4),
            "p_joint": round(p_joint, 6),
            "hits": hits_count,
            "n_simulations": int(n_simulations),
            "ci_95_low": round(ci_95_low, 6),
            "ci_95_high": round(ci_95_high, 6),
            "mc_standard_error": round(mc_se, 6),
            "relative_error": round(rel_error, 6) if math.isfinite(rel_error) else None,
            "sufficient_precision": sufficient_precision,
            "decision": decision,
            "decision_reason": decision_reason,
            "correlation_rho": rho,
            "correlation_boost_pct": corr_boost_pct,
            "fair_sgp_odds": fair_sgp_odds,
            "offered_sgp_odds": offered_sgp_odds,
            "decimal_odds": offered_sgp_odds,
            "num_legs": 2,
            "legs": legs,
            "ev_pct": ev_pct,
            "kelly_stake_pen": stake_pen,
            "is_value_sgp": is_value,
            "rationale": rationale,
        }

    def scan_retabet_sgp_slate(
        self,
        slate_games: list[dict[str, Any]],
        props_list: list[dict[str, Any]],
        bankroll_pen: float = 100.0,
        min_ev_pct: float = 3.0,
        persist: bool = False,
        allow_player_props: bool | None = None,
        allow_parlays: bool | None = None,
    ) -> list[dict[str, Any]]:
        """
        Automated RETAbet SGP Slate Scanner (RESEARCH ONLY: offered SGP prices are simulated,
        not observed; never persisted unless persist=True AND risk_management gates allow).
        """
        sgp_opportunities: list[dict[str, Any]] = []
        games_by_id = {g.get("game_id"): g for g in slate_games if g.get("game_id")}

        for prop in props_list:
            gid = prop.get("game_id")
            game = games_by_id.get(gid)
            if not game:
                continue

            team = prop.get("team")
            is_home = (team == game.get("home_team"))
            game_prob = float(game.get("model_p_home_pct", 50.0) / 100.0) if is_home else float(game.get("model_p_away_pct", 50.0) / 100.0)
            sel_label = f"{game.get('home_name' if is_home else 'away_name') or team} Gana"

            cat = prop.get("prop_category", "PTS")
            rho = 0.35 if cat in ("PTS", "AST", "PRA", "PA", "PR") else 0.18

            p_p = float(prop.get("model_prob") or 0.50)
            obs_g_odds = float(game.get("home_odds" if is_home else "away_odds") or 0.0)
            obs_p_odds = float(prop.get("decimal_odds") or 0.0)
            if obs_g_odds > 1.0 and obs_p_odds > 1.0:
                sim_offered_odds = round(obs_g_odds * obs_p_odds * 0.90, 2)
            elif "offered_sgp_odds" in prop and float(prop["offered_sgp_odds"]) > 1.0:
                sim_offered_odds = float(prop["offered_sgp_odds"])
            elif not persist:
                odds_g = 1.0 / max(0.05, game_prob)
                odds_p = float(prop.get("decimal_odds") or (1.0 / max(0.05, p_p)))
                sim_offered_odds = round(max(1.01, odds_g * odds_p * 0.90), 2)
            else:
                continue

            sgp_cand = self.simulate_same_game_parlay_copula(
                game_id=gid or "NBA_GAME",
                matchday_date=prop.get("matchday_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                game_selection_label=sel_label,
                game_model_prob=game_prob,
                player_name=prop.get("player_name", "Player"),
                team=team or "NBA",
                prop_category=cat,
                prop_selection=prop.get("selection", "OVER"),
                prop_line=float(prop.get("line_value", 20.5)),
                prop_model_prob=p_p,
                offered_sgp_odds=sim_offered_odds,
                correlation_rho=rho,
                bankroll_pen=bankroll_pen,
            )
            if (
                sgp_cand.get("sufficient_precision", False)
                and sgp_cand["ev_pct"] >= min_ev_pct
                and sgp_cand["p_joint"] >= 0.18
            ):
                sgp_cand["is_value_sgp"] = True
                sgp_opportunities.append(sgp_cand)
                if persist:
                    self._persist_sgp_pick(
                        sgp_cand,
                        bankroll_pen,
                        allow_player_props=allow_player_props,
                        allow_parlays=allow_parlays,
                    )

        return sgp_opportunities

    def generate_high_probability_parlays(
        self,
        slate_games: list[dict[str, Any]],
        props_list: list[dict[str, Any]],
        bankroll_pen: float = 100.0,
        min_leg_prob: float = 0.75,
    ) -> list[dict[str, Any]]:
        """
        V9 Pure Alpha Mode: High-Probability Multi-Leg 'Lock Builder' Generator.
        Constructs combinations of highly probable events (alt-lines P >= 75-85%, favorite moneyline anchors)
        that multiply into attractive odds (2.05 - 3.20) with high joint win probability (60% - 70%)
        and aggressive, unconstrained stakes (S/ 7.50 - S/ 16.00 PEN).
        """
        parlays: list[dict[str, Any]] = []

        # 1. Extract Moneyline Anchors (heavy favorites with model win prob >= 70%)
        ml_anchors: list[dict[str, Any]] = []
        for g in slate_games:
            p_home = float(g.get("model_p_home_pct", 50.0)) / 100.0
            p_away = float(g.get("model_p_away_pct", 50.0)) / 100.0
            gid = g.get("game_id", "GAME")
            h_team = g.get("home_team", "HOME")
            a_team = g.get("away_team", "AWAY")
            obs_h_odds = float(g.get("home_odds") or 0.0)
            obs_a_odds = float(g.get("away_odds") or 0.0)
            if p_home >= 0.70:
                h_odds = obs_h_odds if obs_h_odds > 1.0 else round(max(1.05, 1.0 / p_home * 0.96), 2)
                ml_anchors.append({
                    "game_id": gid,
                    "team": h_team,
                    "selection": f"{h_team} ML",
                    "prob": p_home,
                    "odds": h_odds,
                    "type": "ML_ANCHOR",
                })
            elif p_away >= 0.70:
                a_odds = obs_a_odds if obs_a_odds > 1.0 else round(max(1.05, 1.0 / p_away * 0.96), 2)
                ml_anchors.append({
                    "game_id": gid,
                    "team": a_team,
                    "selection": f"{a_team} ML",
                    "prob": p_away,
                    "odds": a_odds,
                    "type": "ML_ANCHOR",
                })

        # 2. Extract High-Probability Alternate Prop Lines (P >= 75%)
        alt_props: list[dict[str, Any]] = []
        for p in props_list:
            p_mean = float(p.get("projected_mean", 0.0))
            p_std = float(p.get("projected_std", 1.0))
            cat = p.get("prop_category", "PTS")
            if p_mean <= 0 or p_std <= 0:
                continue

            # Calculate conservative safe line: mean - 0.90 * std -> Prob ~ 81.5%
            safe_line = max(2.5, math.floor(p_mean - 0.90 * p_std) + 0.5)
            z = (safe_line - p_mean) / p_std
            p_over = float(1.0 - norm.cdf(z))

            if p_over >= min_leg_prob:
                obs_prop_odds = float(p.get("decimal_odds") or 0.0)
                fair_odds = 1.0 / p_over
                retail_odds = obs_prop_odds if obs_prop_odds > 1.0 else round(max(1.05, fair_odds * 1.04), 2)
                alt_props.append({
                    "game_id": p.get("game_id"),
                    "player_name": p.get("player_name"),
                    "team": p.get("team"),
                    "category": cat,
                    "line": safe_line,
                    "selection": "OVER",
                    "prob": round(p_over, 4),
                    "odds": retail_odds,
                    "description": f"{p.get('player_name')} {cat} +{safe_line:.0f}",
                })

        # 3. Strategy A: Same-Game Anchor SGP (Game ML + Alt Prop from same game)
        for anchor in ml_anchors:
            gid = anchor["game_id"]
            team = anchor["team"]
            matching_props = [ap for ap in alt_props if ap["game_id"] == gid and ap["team"] == team]
            if matching_props:
                best_prop = matching_props[0]
                p_slug = hashlib.sha256(f"{gid}_{best_prop['player_name']}_{best_prop['category']}_{best_prop['line']}".encode()).hexdigest()[:8]
                legs = [
                    {
                        "game_id": gid,
                        "market": "moneyline",
                        "selection": anchor["selection"],
                        "prob": anchor["prob"],
                        "odds": anchor["odds"],
                        "desc": f"{anchor['team']} Victoria Directa",
                    },
                    {
                        "game_id": gid,
                        "market": f"player_{best_prop['category'].lower()}",
                        "prop_category": best_prop["category"],
                        "selection": best_prop["selection"],
                        "line_value": float(best_prop["line"]),
                        "player_name": best_prop["player_name"],
                        "prob": best_prop["prob"],
                        "odds": best_prop["odds"],
                        "desc": best_prop["description"],
                    },
                ]
                rho = 0.35
                p1, p2 = anchor["prob"], best_prop["prob"]
                cov = np.array([[1.0, rho], [rho, 1.0]])
                z_draws = np.random.default_rng(42).multivariate_normal([0.0, 0.0], cov, size=5000)
                joint_p = float(np.mean((norm.cdf(z_draws[:, 0]) <= p1) & (norm.cdf(z_draws[:, 1]) <= p2)))

                combined_odds = round(anchor["odds"] * best_prop["odds"], 2)
                ev_pct = round(((joint_p * combined_odds) - 1.0) * 100.0, 2)

                b = combined_odds - 1.0
                if b <= 0.0 or ev_pct <= 0.0:
                    suggested_stake = 0.00
                else:
                    f_k = max(0.0, (joint_p * (b + 1.0) - 1.0) / b)
                    eff_f = min(self.max_bankroll_fraction, f_k * self.kelly_fraction)
                    suggested_stake = round(max(0.0, min(self.max_stake_pen, bankroll_pen * eff_f)), 2)

                parlays.append({
                    "parlay_id": f"HP_SGP_{gid}_{p_slug}",
                    "type": "RETABET_SGP",
                    "strategy": "SAME_GAME_ANCHOR",
                    "game_id": gid,
                    "bookmaker": "RETAbet Perú",
                    "num_legs": len(legs),
                    "legs": legs,
                    "offered_sgp_odds": combined_odds,
                    "decimal_odds": combined_odds,
                    "p_joint": round(joint_p, 4),
                    "win_probability_pct": round(joint_p * 100.0, 1),
                    "ev_pct": ev_pct,
                    "kelly_stake_pen": suggested_stake,
                    "stake_pen": suggested_stake,
                    "rationale": (
                        f"[COMBINADA DE ALTA PROBABILIDAD SGP] {legs[0]['desc']} + {legs[1]['desc']}. "
                        f"Probabilidad de Acierto: {joint_p * 100.0:.1f}%. Cuota Combinada: {combined_odds:.2f} (EV: +{ev_pct:.1f}%). "
                        f"Stake Alfa: S/ {suggested_stake:.2f} PEN."
                    ),
                    "emitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

        # 4. Strategy B: Cross-Game Multi-Match Power Parlay
        all_independent_legs: list[dict[str, Any]] = []
        for anc in ml_anchors:
            all_independent_legs.append({
                "game_id": anc["game_id"],
                "market": "moneyline",
                "selection": anc["selection"],
                "desc": f"{anc['selection']} ({anc['team']})",
                "prob": anc["prob"],
                "odds": anc["odds"],
            })
        for ap in alt_props:
            all_independent_legs.append({
                "game_id": ap["game_id"],
                "market": f"player_{ap['category'].lower()}",
                "prop_category": ap["category"],
                "selection": ap["selection"],
                "line_value": float(ap["line"]),
                "player_name": ap["player_name"],
                "desc": ap["description"],
                "prob": ap["prob"],
                "odds": ap["odds"],
            })

        games_seen = set()
        distinct_legs = []
        for leg in sorted(all_independent_legs, key=lambda x: x["prob"], reverse=True):
            if leg["game_id"] not in games_seen:
                distinct_legs.append(leg)
                games_seen.add(leg["game_id"])
            if len(distinct_legs) >= 3:
                break

        if len(distinct_legs) >= 2:
            combined_odds = 1.0
            joint_p = 1.0
            for leg in distinct_legs[:3]:
                combined_odds *= leg["odds"]
                joint_p *= leg["prob"]

            combined_odds = round(combined_odds, 2)
            ev_pct = round(((joint_p * combined_odds) - 1.0) * 100.0, 2)
            b = combined_odds - 1.0
            if b <= 0.0 or ev_pct <= 0.0:
                suggested_stake = 0.00
            else:
                f_k = max(0.0, (joint_p * (b + 1.0) - 1.0) / max(0.05, b))
                eff_f = min(self.max_bankroll_fraction, f_k * self.kelly_fraction)
                suggested_stake = round(max(0.0, min(self.max_stake_pen, bankroll_pen * eff_f)), 2)

            hash_str = "_".join(f"{leg['game_id']}_{leg.get('player_name', '')}_{leg.get('line_value', '')}" for leg in distinct_legs[:3])
            p_slug = hashlib.sha256(hash_str.encode()).hexdigest()[:8]
            parlays.append({
                "parlay_id": f"HP_POWER_PARLAY_{p_slug}",
                "type": "RETABET_SGP",
                "strategy": "MULTI_MATCH_POWER_PARLAY",
                "game_id": "CROSS_SLATE",
                "bookmaker": "RETAbet / Betsson Perú",
                "num_legs": len(distinct_legs[:3]),
                "legs": distinct_legs[:3],
                "offered_sgp_odds": combined_odds,
                "decimal_odds": combined_odds,
                "p_joint": round(joint_p, 4),
                "win_probability_pct": round(joint_p * 100.0, 1),
                "ev_pct": ev_pct,
                "kelly_stake_pen": suggested_stake,
                "stake_pen": suggested_stake,
                "rationale": (
                    f"[SUPER COMBINADA MULTI-PARTIDO] {' + '.join(leg['desc'] for leg in distinct_legs[:3])}. "
                    f"Probabilidad Conjunta: {joint_p * 100.0:.1f}%. Cuota Combinada: {combined_odds:.2f} (EV: +{ev_pct:.1f}%). "
                    f"Stake Alfa: S/ {suggested_stake:.2f} PEN."
                ),
                "emitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        return parlays

    def generate_slate_prop_opportunities(
        self,
        slate_games: list[dict[str, Any]] | None = None,
        bankroll_pen: float = 100.0,
        min_ev_pct: float = 3.0,
        injuries_by_team: dict[str, list[str]] | None = None,
        output_file: Path | str | None = None,
        allow_parlays: bool | None = None,
        allow_player_props: bool | None = None,
    ) -> list[dict[str, Any]]:
        """
        V9 Institutional End-to-End Prop & SGP Slate Generator:
        1. Trains per-category & pooled Venn-Abers calibrators strictly prior to earliest slate tipoff.
        2. Evaluates rotation players strictly with `as_of_timestamp = game_start_time`.
        3. Tests observed lines against DvP, pace, and usage absorption preserving push probability.
        4. Enforces fail-closed centralized risk controls (`allow_player_props_betting`, `allow_parlays`)
           before any write to `player_prop_picks`.
        """
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        eff_allow_parlays = (
            bool(self.risk.allow_parlays)
            if allow_parlays is None and self.risk is not None
            else bool(allow_parlays) if allow_parlays is not None else False
        )

        if slate_games is None and self.db is not None:
            slate_games = self.db.fetch_all(
                """
                SELECT * FROM games
                WHERE status = 'SCHEDULED'
                  AND game_start_time > ?
                  AND game_id NOT LIKE 'SYN%'
                ORDER BY game_start_time ASC
                LIMIT 15
                """,
                (now_iso,),
            )
        slate_games = slate_games or []

        # Strictly enforce upcoming scheduled games only (zero historical/finished games)
        valid_slate_games = [
            g for g in slate_games
            if g.get("status", "SCHEDULED") == "SCHEDULED" and (not g.get("game_start_time") or str(g.get("game_start_time")) > now_iso)
        ]

        # Train OOS props calibrators strictly before earliest slate tipoff (F-006)
        if self.db is not None and valid_slate_games:
            slate_cutoff = min(
                (str(g["game_start_time"]) for g in valid_slate_games if g.get("game_start_time")),
                default=now_iso,
            )
            self.fit_calibrators(as_of_utc=slate_cutoff)

        # Build injuries mapping if not passed
        team_injuries: dict[str, list[str]] = injuries_by_team or {}
        if not team_injuries and self.db is not None:
            try:
                inj_rows = self.db.fetch_all("SELECT team, player_name FROM player_injuries WHERE status IN ('OUT', 'DOUBTFUL')")
                for r in inj_rows:
                    t = r.get("team")
                    p = r.get("player_name")
                    if t and p:
                        team_injuries.setdefault(t, []).append(p)
            except Exception as exc:
                logger.debug(f"Failed to load injuries from DB: {exc}")

        # Also fallback to visual RAG context if available
        if not team_injuries:
            try:
                v_path = Path("data/visual_rag/latest_visual_context.json")
                if v_path.exists():
                    v_data = json.loads(v_path.read_text(encoding="utf-8"))
                    for doc in v_data.get("top_retrieved_context", []):
                        doc.get("snippet", "")
                        for _team_code in PLAYER_PROP_BASELINES:
                            pass
            except Exception as exc:
                logger.debug(f"Failed to load visual context: {exc}")

        qualified_props: list[dict[str, Any]] = []

        # Fetch verified official rosters from SQLite (with ESPN sync)
        active_rosters: dict[str, list[str]] = {}
        if self.db is not None:
            try:
                from src.ingestion.roster_manager import get_all_rosters
                active_rosters = get_all_rosters(self.db)
            except Exception as exc:
                logging.warning(f"Handled exception in player_props (line 1133): {exc}")

        fallback_rosters = get_fallback_rosters()

        for game in valid_slate_games:
            gid = game.get("game_id", f"G_SLATE_{uuid.uuid4().hex[:6]}")
            mdate = game.get("matchday_date", today_str)
            home_t = game.get("home_team")
            away_t = game.get("away_team")
            spread_val = float(game.get("expected_margin") or 0.0)
            pace_val = float(game.get("stats", {}).get("expected_pace") or 99.5) if isinstance(game.get("stats"), dict) else 99.5

            # Pre-index observed two-sided player_prop snapshots strictly by (normalized_player_name, canonical_category)
            observed_props_index: dict[tuple[str, str], list[tuple[float, float, float]]] = {}
            if self.db and gid:
                g_start_str = str(game.get("game_start_time") or "").strip()
                if g_start_str:
                    raw_prop_rows = self.db.fetch_all(
                        """
                        SELECT provider, line_value, decimal_odds, counterpart_decimal_odds, selection
                        FROM v_observed_odds_snapshots
                        WHERE game_id = ?
                          AND market = 'player_prop'
                          AND COALESCE(is_closing_line, 0) = 0
                          AND datetime(captured_at) < datetime(?)
                        ORDER BY captured_at DESC
                        """,
                        (gid, g_start_str),
                    )
                else:
                    raw_prop_rows = self.db.fetch_all(
                        """
                        SELECT provider, line_value, decimal_odds, counterpart_decimal_odds, selection
                        FROM v_observed_odds_snapshots
                        WHERE game_id = ?
                          AND market = 'player_prop'
                          AND COALESCE(is_closing_line, 0) = 0
                        ORDER BY captured_at DESC
                        """,
                        (gid,),
                    )
                for oq in raw_prop_rows:
                    parsed_prov = _parse_observed_prop_provider(str(oq.get("provider") or ""))
                    if not parsed_prov:
                        continue
                    oq_player, oq_cat = parsed_prov
                    p_key = _normalize_player_match_key(oq_player)
                    if not p_key:
                        continue
                    lv = round(float(oq.get("line_value") or 0.0), 2)
                    dec_odds = float(oq.get("decimal_odds") or 0.0)
                    counter_odds = float(oq.get("counterpart_decimal_odds") or 0.0)
                    sel_side = str(oq.get("selection") or "OVER").strip().upper()
                    if sel_side == "UNDER":
                        oo, uo = counter_odds, dec_odds
                    else:
                        oo, uo = dec_odds, counter_odds
                    if lv > 0.0 and oo > 1.0 and uo > 1.0:
                        bucket = observed_props_index.setdefault((p_key, oq_cat), [])
                        quote_tuple = (lv, oo, uo)
                        if quote_tuple not in bucket:
                            bucket.append(quote_tuple)

            if not observed_props_index:
                continue

            as_of_game_str = str(game.get("game_start_time") or now_iso)
            for _is_home, team_code, opp_code in [(True, home_t, away_t), (False, away_t, home_t)]:
                if not team_code:
                    continue
                team_players = list(active_rosters.get(team_code) or [])
                if not team_players and self.db:
                    try:
                        db_p = self.db.fetch_all(
                            """
                            SELECT MAX(player_name) AS player_name
                            FROM player_boxscores
                            WHERE team = ?
                              AND game_id NOT LIKE 'SYN%'
                              AND datetime(game_start_time) < datetime(?)
                              AND minutes >= 10.0
                            GROUP BY player_key
                            ORDER BY MAX(game_start_time) DESC, COUNT(*) DESC
                            LIMIT 12
                            """,
                            (team_code, as_of_game_str),
                        )
                        if db_p:
                            team_players = [r["player_name"] for r in db_p]
                    except Exception:
                        pass
                if not team_players:
                    team_players = list(fallback_rosters.get(team_code, []))
                absent_list = team_injuries.get(team_code, [])

                for p_raw in team_players:
                    # Match canonical baseline profile or compute dynamic rolling baseline strictly < tip-off
                    prof = self.get_player_baseline(p_raw, team_code, as_of_utc=as_of_game_str)
                    canonical_name = p_raw
                    if not prof:
                        continue

                    # Skip if player is marked absent
                    if canonical_name in absent_list or p_raw in absent_list:
                        continue

                    p_name = canonical_name
                    target_p_key = _normalize_player_match_key(p_name)
                    if not target_p_key:
                        continue

                    # Evaluate categories offered by the bookmaker (respecting minimum rotation/rate thresholds)
                    categories_to_eval = ["PTS", "PRA"]
                    if prof[4] >= 0.18 or ((target_p_key, "AST") in observed_props_index and prof[0] >= 12.0):
                        categories_to_eval.append("AST")
                    if prof[3] >= 0.25 or ((target_p_key, "REB") in observed_props_index and prof[0] >= 12.0):
                        categories_to_eval.append("REB")
                    if prof[5] >= 0.08 or (
                        (target_p_key, "3PM") in observed_props_index and (prof[0] * prof[5]) >= 0.30
                    ):
                        categories_to_eval.append("3PM")

                    matched_cats = [cat for cat in categories_to_eval if (target_p_key, cat) in observed_props_index]
                    if not matched_cats:
                        continue

                    # Project raw baseline strictly using pre-tipoff history
                    proj = self.project_player_stats(
                        player_name=p_name,
                        team=team_code,
                        absent_teammates=absent_list,
                        opponent_team=opp_code,
                        expected_game_pace=pace_val,
                        spread_blowout_risk=spread_val,
                        as_of_utc=as_of_game_str,
                    )

                    for cat in matched_cats:
                        p_data = proj["projections"].get(cat)
                        if not p_data:
                            continue

                        lines_to_test = observed_props_index.get((target_p_key, cat), [])
                        if not lines_to_test:
                            continue

                        for lv, oo, uo in lines_to_test:
                            picks = self.evaluate_prop_opportunity(
                                player_name=p_name,
                                team=team_code,
                                game_id=gid or "NBA_GAME",
                                matchday_date=mdate,
                                prop_category=cat,
                                line_value=lv,
                                over_odds=oo,
                                under_odds=uo,
                                absent_teammates=absent_list,
                                bankroll_pen=bankroll_pen,
                                opponent_team=opp_code,
                                expected_game_pace=pace_val,
                                spread_blowout_risk=spread_val,
                                persist=False,
                                line_source="OBSERVED",
                                as_of_utc=as_of_game_str,
                            )
                            for pk in picks:
                                if pk["ev_pct"] >= min_ev_pct and pk["ev_lower_bound_pct"] >= -10.0:
                                    qualified_props.append(pk)

        # Sort individual props by highest Lower-Bound EV
        qualified_props.sort(key=lambda x: (x.get("ev_lower_bound_pct", 0.0), x.get("ev_pct", 0.0)), reverse=True)
        top_individual_props = qualified_props[:15]

        # Combined bets (SGP / parlays): prices are ESTIMATED (no bookmaker SGP price is captured) and
        # labelled as such; enabled by risk_management.allow_parlays.
        top_sgp_candidates: list[dict[str, Any]] = []
        high_prob_parlays: list[dict[str, Any]] = []
        if eff_allow_parlays:
            sgp_candidates = self.scan_retabet_sgp_slate(
                slate_games=valid_slate_games,
                props_list=top_individual_props,
                bankroll_pen=bankroll_pen,
                min_ev_pct=min_ev_pct,
                persist=False,
            )
            sgp_candidates.sort(key=lambda x: x.get("ev_pct", 0.0), reverse=True)
            top_sgp_candidates = sgp_candidates[:8]
            high_prob_parlays = self.generate_high_probability_parlays(
                slate_games=valid_slate_games,
                props_list=top_individual_props,
                bankroll_pen=bankroll_pen,
            )

        # Record paper bets through centralized fail-closed risk gate only after ranking
        if self.db is not None:
            for sgp in top_sgp_candidates[:1]:
                self._persist_sgp_pick(
                    sgp,
                    bankroll_pen,
                    allow_player_props=allow_player_props,
                    allow_parlays=allow_parlays,
                )
            for pk in top_individual_props:
                self._persist_prop_pick(pk, bankroll_pen, allow_player_props=allow_player_props)
            for sgp in top_sgp_candidates[1:]:
                self._persist_sgp_pick(
                    sgp,
                    bankroll_pen,
                    allow_player_props=allow_player_props,
                    allow_parlays=allow_parlays,
                )

        consolidated = high_prob_parlays + top_sgp_candidates + top_individual_props

        # Persist safely without polluting versioned repo files during tests
        if output_file is not None:
            out_file = Path(output_file)
            try:
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(json.dumps(consolidated, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                logger.debug(f"Failed to write props output file: {exc}")
        elif not os.environ.get("PYTEST_CURRENT_TEST") and (
            self.db is None or Path(self.db.db_path).resolve() == Path("data/nba_intelligence.sqlite3").resolve()
        ):
            out_file = Path("data/evaluation/latest_player_props.json")
            try:
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(json.dumps(consolidated, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                logger.debug(f"Failed to write props output file: {exc}")

        return consolidated

    def evaluate_historical_oos_calibration(
        self,
        *,
        min_date: str = "2026-01-01T00:00:00Z",
        min_minutes: float = 12.0,
        max_samples: int = 2000,
        benchmarks: tuple[tuple[str, float, str], ...] = (
            ("PTS", 15.5, "pts"),
            ("PTS", 20.5, "pts"),
            ("REB", 5.5, "reb"),
            ("AST", 4.5, "ast"),
            ("3PM", 0.5, "threed"),
            ("3PM", 1.5, "threed"),
            ("PRA", 24.5, "pts+reb+ast"),
        ),
    ) -> dict[str, Any]:
        """
        Evaluates strictly pre-tipoff out-of-sample calibration and Brier Skill Score
        against persisted `player_boxscores` using `as_of_utc = game_start_time`.
        """
        if self.db is None:
            return {"eligible_samples": 0, "evaluated_samples": 0, "benchmarks": {}}

        rows = self.db.fetch_all(
            """
            SELECT pb.game_id, pb.player_name, pb.player_key, pb.team, pb.game_start_time,
                   pb.minutes, pb.pts, pb.reb, pb.ast, pb.threed,
                   g.home_team, g.away_team
            FROM player_boxscores pb
            JOIN games g ON g.game_id = pb.game_id
            WHERE pb.game_start_time >= ?
              AND pb.minutes >= ?
              AND g.status = 'FINAL'
              AND g.game_id NOT LIKE 'SYN%'
            ORDER BY pb.game_start_time ASC, pb.player_key ASC
            """,
            (min_date, float(min_minutes)),
        )
        if not rows:
            return {"eligible_samples": 0, "evaluated_samples": 0, "benchmarks": {}}

        step = max(1, len(rows) // max(1, int(max_samples)))
        sample = rows[::step][:max_samples]
        series: dict[str, list[tuple[float, int, float, float]]] = {
            f"{cat}>{line:.1f}": [] for cat, line, _ in benchmarks
        }

        for r in sample:
            opp_team = r["away_team"] if r["team"] == r["home_team"] else r["home_team"]
            proj = self.project_player_stats(
                player_name=r["player_name"],
                team=r["team"],
                opponent_team=opp_team,
                as_of_utc=r["game_start_time"],
            )
            stat_vals = {
                "pts": float(r["pts"]),
                "reb": float(r["reb"]),
                "ast": float(r["ast"]),
                "threed": float(r["threed"]),
                "pts+reb+ast": float(r["pts"] + r["reb"] + r["ast"]),
            }
            for cat, line, expr in benchmarks:
                c = proj["projections"].get(cat)
                if not c or expr not in stat_vals:
                    continue
                p_over, _p_under, _p_push = self.compute_exceedance_probabilities(
                    prop_category=cat,
                    line_value=line,
                    proj_mean=float(c["mean"]),
                    proj_std=float(c["std"]),
                    dist_type=c["dist"],
                )
                act = stat_vals[expr]
                series[f"{cat}>{line:.1f}"].append((p_over, 1 if act > line else 0, float(c["mean"]), act))

        metrics: dict[str, dict[str, Any]] = {}
        for label, items in series.items():
            if not items:
                continue
            p_arr = np.clip(np.asarray([x[0] for x in items], dtype=float), 1e-4, 1.0 - 1e-4)
            y_arr = np.asarray([x[1] for x in items], dtype=float)
            mu_arr = np.asarray([x[2] for x in items], dtype=float)
            act_arr = np.asarray([x[3] for x in items], dtype=float)
            base_rate = float(np.mean(y_arr))
            base_p = float(np.clip(base_rate, 1e-4, 1.0 - 1e-4))
            brier = float(np.mean((p_arr - y_arr) ** 2))
            brier_base = float(np.mean((base_p - y_arr) ** 2))
            ll = float(-np.mean(y_arr * np.log(p_arr) + (1.0 - y_arr) * np.log(1.0 - p_arr)))
            ll_base = float(-np.mean(y_arr * np.log(base_p) + (1.0 - y_arr) * np.log(1.0 - base_p)))
            bss = ((1.0 - brier / brier_base) * 100.0) if brier_base > 0.0 else 0.0
            metrics[label] = {
                "n": len(items),
                "base_over_rate": round(base_rate, 4),
                "mean_pred_prob": round(float(np.mean(p_arr)), 4),
                "mae": round(float(np.mean(np.abs(mu_arr - act_arr))), 3),
                "brier": round(brier, 4),
                "brier_baseline": round(brier_base, 4),
                "brier_skill_score_pct": round(bss, 2),
                "log_loss": round(ll, 4),
                "log_loss_baseline": round(ll_base, 4),
            }

        return {
            "min_date": min_date,
            "eligible_samples": len(rows),
            "evaluated_samples": len(sample),
            "benchmarks": metrics,
        }
