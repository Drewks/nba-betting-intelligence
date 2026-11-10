"""
V7 Fase 4 — Bayesian Walk-Forward Hyperparameter Optimization with Optuna (TPE Sampler).
Strictly chronological cross-validation with zero temporal leakage.
Optimizes multi-horizon EWMA rates, Huber blowout caps, spread sigma and momentum blend on a
validation window, minimizing (Brier Score + 0.5 * Log-Loss) of the RAW model probability, and adopts
the result only if it also improves an untouched holdout window.

History note: before 2026-11-09 the objective used a "market proxy" computed from the FINAL score of
each game (target leakage), which produced an impossible Brier of 0.072. Those results are invalid.
"""

from __future__ import annotations

from datetime import datetime

import json
from pathlib import Path
from typing import Any
import numpy as np
import optuna

from src.calibration.calibrator import compute_brier_score, compute_log_loss
from src.features.team_ratings import (
    HCA_PER_SIDE,
    LEAGUE_ALPHA,
    LEAGUE_PACE_BASE,
    LEAGUE_PPG_PRIOR,
    OFFSEASON_CARRYOVER,
    OFFSEASON_GAP_DAYS,
    is_synthetic_game_id,
)
from src.prediction.ev_calculator import (
    DEFAULT_MODEL_WEIGHT,
    market_anchored_probability,
)
from src.storage.db import DatabaseManager
from src.validation.validator import parse_iso_utc


class _ParametricTeamState:
    __slots__ = (
        "pts_for_slow",
        "pts_against_slow",
        "pts_for_fast",
        "pts_against_fast",
        "tempo_slow",
        "tempo_fast",
        "last_start",
        "games",
    )

    def __init__(self, league_ppg: float) -> None:
        self.pts_for_slow = league_ppg
        self.pts_against_slow = league_ppg
        self.pts_for_fast = league_ppg
        self.pts_against_fast = league_ppg
        self.tempo_slow = 0.0
        self.tempo_fast = 0.0
        self.last_start: datetime | None = None
        self.games = 0


def _simulate_parametric_ratings_and_preds(
    games: list[dict[str, Any]],
    alpha_slow: float,
    alpha_fast: float,
    tempo_alpha_slow: float,
    tempo_alpha_fast: float,
    blowout_cap: float,
    market_model_weight: float,
    spread_sigma: float = 11.6,
    momentum_blend_weight: float = 0.88,
    eval_slice_size: int = 150,
    holdout_size: int = 0,
) -> tuple[list[float], list[float], list[int]]:
    """
    Computes strict chronological ratings with trial parameters and returns
    (raw_probs, anchored_probs, outcomes) on the out-of-sample evaluation slice.
    """
    real = [g for g in games if not is_synthetic_game_id(g.get("game_id")) and g.get("status") == "FINAL"]
    if len(real) < 80:
        # If insufficient real games (e.g. synthetic simulation study / tests), allow synthetic fixtures
        real = [g for g in games if g.get("status") == "FINAL"]
    real.sort(key=lambda g: (str(g.get("game_start_time", "")), str(g.get("game_id", ""))))

    if len(real) < 80:
        return [], [], []

    eval_n = min(eval_slice_size, len(real) // 3)
    # Evaluation window [window_start, window_end): the last `holdout_size` games are excluded so they
    # can be kept as an untouched final holdout by the caller.
    window_end = len(real) - max(0, int(holdout_size))
    train_end_idx = window_end - eval_n
    if train_end_idx < 40:
        return [], [], []

    league_ppg = LEAGUE_PPG_PRIOR
    league_total = 2.0 * LEAGUE_PPG_PRIOR
    teams: dict[str, _ParametricTeamState] = {}
    scale_100 = 100.0 / LEAGUE_PACE_BASE

    def _get_state(code: str, start: Any) -> _ParametricTeamState:
        st = teams.get(code)
        if st is None:
            st = _ParametricTeamState(league_ppg)
            teams[code] = st
        elif st.last_start is not None and (start - st.last_start).days >= OFFSEASON_GAP_DAYS:
            st.pts_for_slow = league_ppg + OFFSEASON_CARRYOVER * (st.pts_for_slow - league_ppg)
            st.pts_against_slow = league_ppg + OFFSEASON_CARRYOVER * (st.pts_against_slow - league_ppg)
            st.pts_for_fast = st.pts_for_slow
            st.pts_against_fast = st.pts_against_slow
            st.tempo_slow *= 0.55
            st.tempo_fast = st.tempo_slow
            st.last_start = None
        return st

    raw_preds: list[float] = []
    anchored_preds: list[float] = []
    outcomes: list[int] = []

    from scipy.stats import norm

    for idx, g in enumerate(real):
        start = parse_iso_utc(g["game_start_time"])
        h = _get_state(g["home_team"], start)
        a = _get_state(g["away_team"], start)

        w_slow = float(momentum_blend_weight)
        w_fast = 1.0 - w_slow
        h_pf = w_slow * h.pts_for_slow + w_fast * h.pts_for_fast
        h_pa = w_slow * h.pts_against_slow + w_fast * h.pts_against_fast
        a_pf = w_slow * a.pts_for_slow + w_fast * a.pts_for_fast
        a_pa = w_slow * a.pts_against_slow + w_fast * a.pts_against_fast

        h_off, h_def = h_pf * scale_100, h_pa * scale_100
        a_off, a_def = a_pf * scale_100, a_pa * scale_100

        # Estimated margin in points
        expected_margin = (h_off - a_def) - (a_off - h_def) + (2.0 * HCA_PER_SIDE)
        p_home_model = float(np.clip(1.0 - norm.cdf(0.0, loc=expected_margin, scale=spread_sigma), 0.05, 0.95))

        # Out-of-sample evaluation slice (never in-sample, strictly pre-game without score leakage)
        if train_end_idx <= idx < window_end:
            actual_y = 1 if int(g["home_score"]) > int(g["away_score"]) else 0
            # Anchor ONLY to a genuine pre-game market probability when the record carries one.
            # Without it there is no anchoring at all (a constant 0.50 "market" is not a market).
            pregame_mkt = g.get("market_prob")
            anchored_p = (
                market_anchored_probability(p_home_model, market_prob=float(pregame_mkt), model_weight=market_model_weight)
                if pregame_mkt is not None
                else p_home_model
            )

            raw_preds.append(round(p_home_model, 5))
            anchored_preds.append(round(anchored_p, 5))
            outcomes.append(actual_y)

        # Update ratings strictly after predicting (causal order)
        hs, as_ = float(g["home_score"]), float(g["away_score"])
        raw_total = hs + as_
        raw_margin = hs - as_

        exp_eff_total = (
            league_total
            + (h.pts_for_slow - league_ppg)
            + (a.pts_against_slow - league_ppg)
            + (a.pts_for_slow - league_ppg)
            + (h.pts_against_slow - league_ppg)
        )
        exp_game_total = exp_eff_total + h.tempo_slow + a.tempo_slow

        is_likely_ot = (abs(raw_margin) <= 7.0) and (raw_total > exp_game_total + 18.0)
        reg_total = (raw_total - 13.0) if is_likely_ot else raw_total
        capped_total = max(league_total - 38.0, min(league_total + 38.0, reg_total))
        tempo_err = capped_total - exp_game_total

        clean_possession_weight = max(0.58, min(1.0, 1.0 - 0.020 * max(0.0, abs(raw_margin) - 18.0)))
        effective_tempo_err = tempo_err * clean_possession_weight

        capped_margin = max(-blowout_cap, min(blowout_cap, raw_margin))
        adj_hs = 0.5 * (capped_total + capped_margin)
        adj_as = 0.5 * (capped_total - capped_margin)

        h_for_adj = (adj_hs - HCA_PER_SIDE) - (a.pts_against_slow - league_ppg) - 0.35 * a.tempo_slow
        h_against_adj = (adj_as + HCA_PER_SIDE) - (a.pts_for_slow - league_ppg) - 0.35 * a.tempo_slow
        a_for_adj = (adj_as + HCA_PER_SIDE) - (h.pts_against_slow - league_ppg) - 0.35 * h.tempo_slow
        a_against_adj = (adj_hs - HCA_PER_SIDE) - (h.pts_for_slow - league_ppg) - 0.35 * h.tempo_slow

        fast_alpha_eff = alpha_fast * clean_possession_weight
        for st, f_adj, ag_adj in ((h, h_for_adj, h_against_adj), (a, a_for_adj, a_against_adj)):
            st.pts_for_slow += alpha_slow * (f_adj - st.pts_for_slow)
            st.pts_against_slow += alpha_slow * (ag_adj - st.pts_against_slow)
            st.pts_for_fast += fast_alpha_eff * (f_adj - st.pts_for_fast)
            st.pts_against_fast += fast_alpha_eff * (ag_adj - st.pts_against_fast)
            st.tempo_slow += tempo_alpha_slow * effective_tempo_err
            st.tempo_fast += tempo_alpha_fast * effective_tempo_err
            st.last_start = start
            st.games += 1

        league_ppg += LEAGUE_ALPHA * (0.5 * capped_total - league_ppg)
        league_total = 2.0 * league_ppg

    return raw_preds, anchored_preds, outcomes


class OptunaWalkForwardOptimizer:
    """
    Optuna-powered Walk-Forward Hyperparameter Optimizer:
    Tunes structural vs. fast EWMA learning rates, Huber blowout margins,
    and market-anchoring weights to minimize out-of-sample Brier Score and Log-Loss.
    """

    def __init__(self, db: DatabaseManager | None = None, seed: int = 42) -> None:
        self.db = db
        self.seed = seed

    def optimize(
        self,
        games: list[dict[str, Any]] | None = None,
        n_trials: int = 25,
        eval_slice_size: int = 150,
        output_json_path: Path | str | None = None,
        holdout_size: int | None = None,
    ) -> dict[str, Any]:
        """
        Tunes rating hyperparameters on a VALIDATION window and decides adoption on an untouched
        HOLDOUT window (the most recent games). Selecting and reporting on the same games would overfit
        the selection; here the holdout is evaluated exactly twice (baseline vs. best) after tuning.
        The objective scores the raw model probability; no market anchoring is tuned because historical
        games carry no observed pre-game market probability.
        """
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        if games is None:
            if self.db is None:
                raise ValueError("OptunaWalkForwardOptimizer requires games or an active DatabaseManager.")
            games = self.db.fetch_all("SELECT * FROM v_observed_games WHERE status = 'FINAL' ORDER BY game_start_time ASC")

        hold_n = eval_slice_size if holdout_size is None else int(holdout_size)
        defaults: dict[str, float] = {
            "alpha_slow": 0.045,
            "alpha_fast": 0.110,
            "tempo_alpha_slow": 0.055,
            "tempo_alpha_fast": 0.130,
            "blowout_cap": 28.0,
            "spread_sigma": 11.6,
            "momentum_blend_weight": 0.88,
        }

        def _score(params: dict[str, float], holdout: bool) -> tuple[float, float, float, int]:
            raw, _anch, y = _simulate_parametric_ratings_and_preds(
                games=games,
                alpha_slow=params["alpha_slow"],
                alpha_fast=params["alpha_fast"],
                tempo_alpha_slow=params["tempo_alpha_slow"],
                tempo_alpha_fast=params["tempo_alpha_fast"],
                blowout_cap=params["blowout_cap"],
                market_model_weight=DEFAULT_MODEL_WEIGHT,
                spread_sigma=params["spread_sigma"],
                momentum_blend_weight=params["momentum_blend_weight"],
                eval_slice_size=eval_slice_size if not holdout else hold_n,
                holdout_size=hold_n if not holdout else 0,
            )
            if not y:
                raise ValueError("Insufficient games for walk-forward optimization (need validation + holdout windows).")
            brier = compute_brier_score(raw, y)
            logloss = compute_log_loss(raw, y)
            return round(brier + 0.5 * logloss, 5), brier, logloss, len(y)

        baseline_score, base_brier, base_logloss, val_n = _score(defaults, holdout=False)

        sampler = optuna.samplers.TPESampler(seed=self.seed)
        study = optuna.create_study(direction="minimize", sampler=sampler)

        def objective(trial: optuna.Trial) -> float:
            params = {
                "alpha_slow": trial.suggest_float("alpha_slow", 0.016, 0.060, step=0.002),
                "alpha_fast": trial.suggest_float("alpha_fast", 0.090, 0.190, step=0.005),
                "tempo_alpha_slow": trial.suggest_float("tempo_alpha_slow", 0.020, 0.070, step=0.002),
                "tempo_alpha_fast": trial.suggest_float("tempo_alpha_fast", 0.060, 0.150, step=0.005),
                "blowout_cap": trial.suggest_float("blowout_cap", 22.0, 30.0, step=1.0),
                "spread_sigma": trial.suggest_float("spread_sigma", 10.2, 13.0, step=0.1),
                "momentum_blend_weight": trial.suggest_float("momentum_blend_weight", 0.75, 0.95, step=0.01),
            }
            return _score(params, holdout=False)[0]

        study.optimize(objective, n_trials=n_trials)

        best_score = float(study.best_value)
        best_params = {k: float(v) for k, v in study.best_params.items()}
        improvement = round(max(0.0, (baseline_score - best_score) / baseline_score) * 100.0, 2)

        hold_base, hold_base_brier, hold_base_ll, hold_count = _score(defaults, holdout=True)
        hold_best, hold_best_brier, hold_best_ll, _ = _score(best_params, holdout=True)
        adopt = hold_best < hold_base

        summary: dict[str, Any] = {
            "objective": "raw model Brier + 0.5 * LogLoss (no market anchoring tuned)",
            "n_trials": len(study.trials),
            "eval_sample_size": val_n,
            "holdout_sample_size": hold_count,
            "baseline_score": baseline_score,
            "baseline_brier": base_brier,
            "baseline_log_loss": base_logloss,
            "best_score": best_score,
            "improvement_pct": improvement,
            "best_hyperparameters": best_params,
            "default_hyperparameters": defaults,
            "holdout": {
                "baseline_score": hold_base,
                "baseline_brier": hold_base_brier,
                "baseline_log_loss": hold_base_ll,
                "best_score": hold_best,
                "best_brier": hold_best_brier,
                "best_log_loss": hold_best_ll,
            },
            "adoption_decision": "ADOPT_ON_HOLDOUT_IMPROVEMENT" if adopt else "REJECT_NO_HOLDOUT_IMPROVEMENT",
        }

        if output_json_path:
            out_path = Path(output_json_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        return summary
