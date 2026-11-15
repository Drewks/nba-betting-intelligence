"""
Modelo G: Hybrid ML + 10,000-Game Quarter-by-Quarter Possession Monte Carlo Simulator.
Simulates possessions, Q4 blowout/garbage-time, clutch intentional fouling, and iterative multi-overtime
with moment-matched expectation anchoring to prevent drift while capturing fat-tailed regimes.
"""

from __future__ import annotations

import hashlib
from typing import Any
import numpy as np
from scipy.stats import norm

from src.features.builder import build_pregame_features
from src.models.gbm_model import AdvancedGBMModel
from src.models.point_margin import PointMarginModel
from src.models.total_points import TotalPointsModel


class DeepMonteCarloHybridModel:
    """
    Modelo G (Hybrid Machine Learning + 10,000-Game Quarter-by-Quarter Possession Monte Carlo):
    - Layer 1 (ML Parameter Estimation): Uses RidgeCV + Residual LightGBM + Elo/Efficiency features to estimate
      expected possessions per game, Points Per Possession (PPP) for Home & Away, shared game-environment covariance,
      and 3PT heavy-tailed Student-t volatility.
    - Layer 2 (Vectorized 10,000-Game Monte Carlo Simulator with First-Moment Matching): Simulates Q1-Q3,
      Q4 Blowout/Garbage-Time deceleration, Late-Game Intentional Fouling, and iterative 5-minute Overtime
      periods until resolution without tie-breaking bias, centered via exact first-moment matching.
    - Layer 3 (Parametric Simulation Quantiles & Tail-Risk Telemetry): Extracts unconditional outcome triples
      (win/loss/push), overtime/multi-overtime frequencies, blowout probability, and 80% simulation intervals
      ([Q10, Q90]; explicitly simulation quantiles, not conformal guarantees).
    """

    model_family = "model_g_ml_montecarlo_hybrid"
    HISTORICAL_NBA_OT_RATE: float = 0.060
    HISTORICAL_NBA_MULTI_OT_CONDITIONAL_RATE: float = 0.145

    def __init__(
        self,
        version_id: str = "model_g_ml_montecarlo_v8",
        n_simulations: int = 10000,
        shared_margin_model: PointMarginModel | None = None,
        shared_totals_model: TotalPointsModel | None = None,
        shared_gbm_model: AdvancedGBMModel | None = None,
    ) -> None:
        self.version_id = version_id
        self.n_simulations = int(n_simulations)
        self._owns_submodels = shared_margin_model is None
        self.margin_model = shared_margin_model or PointMarginModel("model_c_for_mc_v8")
        self.totals_model = shared_totals_model or TotalPointsModel("model_d_for_mc_v8")
        self.gbm_model = shared_gbm_model or AdvancedGBMModel("model_e_for_mc_v8")

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        if self._owns_submodels:
            self.margin_model.fit(historical_games, cutoff_time_str)
            self.totals_model.fit(historical_games, cutoff_time_str)
            self.gbm_model.fit(historical_games, cutoff_time_str)

    @staticmethod
    def _deterministic_seed(game_id: str) -> int:
        digest = hashlib.sha256(str(game_id).encode("utf-8")).hexdigest()
        return int(digest[:8], 16)

    def simulate_matchup(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        line_value: float = 228.5,
        precomputed_c: dict[str, float] | None = None,
        precomputed_d: dict[str, float] | None = None,
        precomputed_e_ml: dict[str, float] | None = None,
        precomputed_e_tot: dict[str, float] | None = None,
    ) -> dict[str, float]:
        feats = build_pregame_features(game, historical_games, market="total_points")
        c_res = precomputed_c or self.margin_model.predict_moneyline(game, historical_games)
        d_res = precomputed_d or self.totals_model.predict_total_points(game, historical_games, line_value)
        e_ml = precomputed_e_ml or self.gbm_model.predict_moneyline(game, historical_games)
        e_tot = precomputed_e_tot or self.gbm_model.predict_total_points(game, historical_games, line_value)

        # Layer 1: Blend Elo spread, RidgeCV margin, and GBM margin
        e_mar = e_ml.get("expected_margin", c_res["expected_margin"])
        ml_margin = 0.50 * feats["elo_spread"] + 0.30 * c_res["expected_margin"] + 0.20 * e_mar
        ml_total = 0.72 * d_res["expected_total"] + 0.28 * e_tot["expected_total"]

        # Adjust baseline regulation total down by ~1.35 pts because OT and clutch fouling add ~1.35 pts on average
        reg_total_mean = ml_total - 1.35
        exp_home_reg = 0.5 * (reg_total_mean + ml_margin)
        exp_away_reg = 0.5 * (reg_total_mean - ml_margin)

        exp_pace = max(92.0, min(106.0, float(feats["expected_pace"])))
        ppp_home = exp_home_reg / exp_pace
        ppp_away = exp_away_reg / exp_pace

        # Layer 2: Vectorized 10,000-Game Quarter-by-Quarter Possession Monte Carlo
        rng = np.random.default_rng(self._deterministic_seed(str(game.get("game_id", "NBA_MC"))))
        n = self.n_simulations

        # Shared regulation possessions + shared game-flow/whistle environment shock (induces realistic Cov(H, A) ~ +38)
        poss_q1_q3 = rng.normal(loc=0.75 * exp_pace, scale=3.10, size=n)
        poss_q4 = rng.normal(loc=0.25 * exp_pace, scale=1.80, size=n)
        shared_env_ppp = rng.normal(loc=0.0, scale=0.044, size=n)

        # Independent team shooting shocks (calibrated so std(margin) ~ 11.5 near 0 and std(total) ~ 18.2)
        t_scale = 0.8165
        eff_std_q1_q3 = 0.106 * t_scale
        eff_std_q4 = 0.062 * t_scale

        h_shock_q1_q3 = rng.standard_t(df=6.0, size=n) * eff_std_q1_q3
        a_shock_q1_q3 = rng.standard_t(df=6.0, size=n) * eff_std_q1_q3

        h_q1_q3 = poss_q1_q3 * (ppp_home + shared_env_ppp + h_shock_q1_q3)
        a_q1_q3 = poss_q1_q3 * (ppp_away + shared_env_ppp + a_shock_q1_q3)

        margin_q3 = h_q1_q3 - a_q1_q3
        is_blowout_q3 = np.abs(margin_q3) >= 18.0

        h_shock_q4 = 0.12 * h_shock_q1_q3 + rng.standard_t(df=6.0, size=n) * eff_std_q4
        a_shock_q4 = 0.12 * a_shock_q1_q3 + rng.standard_t(df=6.0, size=n) * eff_std_q4
        h_q4 = poss_q4 * (ppp_home + shared_env_ppp + h_shock_q4)
        a_q4 = poss_q4 * (ppp_away + shared_env_ppp + a_shock_q4)

        # Regime A: Blowout / Garbage-Time Deceleration
        h_q4 = np.where(is_blowout_q3, h_q4 - 1.50 - np.sign(margin_q3) * 0.75, h_q4)
        a_q4 = np.where(is_blowout_q3, a_q4 - 1.50 + np.sign(margin_q3) * 0.75, a_q4)

        h_reg = h_q1_q3 + h_q4
        a_reg = a_q1_q3 + a_q4
        reg_diff = h_reg - a_reg

        # Regime B: Late-Game Intentional Fouling (margin between 1.25 and 6.0 pts entering final 90s)
        is_clutch_foul = (np.abs(reg_diff) >= 1.25) & (np.abs(reg_diff) <= 6.0)
        foul_trigger = is_clutch_foul & (rng.random(size=n) < 0.58)
        extra_ft_leader = np.where(foul_trigger, rng.uniform(2.2, 4.8, size=n), 0.0)
        extra_ft_trailer = np.where(foul_trigger, rng.uniform(0.8, 2.6, size=n), 0.0)

        h_final = h_reg + np.where(reg_diff > 0, extra_ft_leader, extra_ft_trailer)
        a_final = a_reg + np.where(reg_diff < 0, extra_ft_leader, extra_ft_trailer)

        # Regime C: Iterative multi-overtime simulation until winner (F-003, zero home tie-breaker bias)
        is_overtime = np.abs(reg_diff) < 1.25
        ot_periods = np.zeros(n, dtype=int)
        if np.any(is_overtime):
            tie_score = np.rint(0.5 * (h_reg + a_reg))
            h_final = np.where(is_overtime, tie_score, h_final)
            a_final = np.where(is_overtime, tie_score, a_final)
            active_ot = is_overtime.copy()
            max_ot_rounds = 20
            ot_round = 0
            while np.any(active_ot) and ot_round < max_ot_rounds:
                ot_round += 1
                ot_periods[active_ot] += 1
                k = int(np.sum(active_ot))
                ot_poss = np.maximum(6.0, rng.normal(loc=10.3, scale=1.2, size=k))
                ot_env = rng.normal(loc=0.0, scale=0.040, size=k)
                ot_h_pts = np.maximum(0.0, np.rint(ot_poss * (ppp_home + ot_env + rng.normal(0.0, 0.145, size=k))))
                ot_a_pts = np.maximum(0.0, np.rint(ot_poss * (ppp_away + ot_env + rng.normal(0.0, 0.145, size=k))))
                h_final[active_ot] += ot_h_pts
                a_final[active_ot] += ot_a_pts
                active_ot = active_ot & (h_final == a_final)

        raw_margins = h_final - a_final
        raw_totals = h_final + a_final

        # First-moment matching (control variate centering) to eliminate Monte Carlo regime drift
        # while retaining exact empirical skewness, heavy Student-t tails, and OT/foul multi-modality
        sim_margins = raw_margins + (ml_margin - float(np.mean(raw_margins)))
        sim_totals = raw_totals + (ml_total - float(np.mean(raw_totals)))

        p_home_emp = float(np.mean(sim_margins > 0.0))
        p_home_smooth = float(1.0 - norm.cdf(0.0, loc=ml_margin, scale=11.55))
        p_home_mc = float(np.clip(0.50 * p_home_emp + 0.50 * p_home_smooth, 1e-4, 1.0 - 1e-4))

        mc_tot_std = float(np.clip(np.std(sim_totals), 16.5, 20.5))
        is_int_line = abs(line_value - round(line_value)) < 1e-6
        if is_int_line:
            over_mask = sim_totals > (line_value + 0.5)
            under_mask = sim_totals < (line_value - 0.5)
            push_mask = ~(over_mask | under_mask)
            p_over_emp = float(np.mean(over_mask))
            p_under_emp = float(np.mean(under_mask))
            p_push_emp = float(np.mean(push_mask))

            p_over_smooth = float(1.0 - norm.cdf(line_value + 0.5, loc=ml_total, scale=mc_tot_std))
            p_under_smooth = float(norm.cdf(line_value - 0.5, loc=ml_total, scale=mc_tot_std))
            p_push_smooth = max(0.0, 1.0 - p_over_smooth - p_under_smooth)

            # Convex blend of two valid unconditional probability triples sums to exact 1.0 (F-004).
            p_over_mc = 0.50 * p_over_emp + 0.50 * p_over_smooth
            p_under_mc = 0.50 * p_under_emp + 0.50 * p_under_smooth
            p_push_mc = max(0.0, 1.0 - p_over_mc - p_under_mc)
            _ = (p_push_emp, p_push_smooth)
        else:
            p_over_emp = float(np.mean(sim_totals > line_value))
            p_over_smooth = float(1.0 - norm.cdf(line_value, loc=ml_total, scale=mc_tot_std))
            p_over_mc = float(np.clip(0.50 * p_over_emp + 0.50 * p_over_smooth, 1e-4, 1.0 - 1e-4))
            p_push_mc = 0.0
            p_under_mc = 1.0 - p_over_mc

        p_over_r = round(float(p_over_mc), 6)
        p_push_r = round(float(p_push_mc), 6)
        p_under_r = round(max(0.0, 1.0 - p_over_r - p_push_r), 6)

        q10_tot, q90_tot = np.percentile(sim_totals, [10.0, 90.0])
        q10_mar, q90_mar = np.percentile(sim_margins, [10.0, 90.0])
        ot_mask = ot_periods >= 1
        multi_ot_mask = ot_periods >= 2

        return {
            "p_home_mc": round(p_home_mc, 6),
            "p_away_mc": round(1.0 - p_home_mc, 6),
            "p_over_mc": p_over_r,
            "p_under_mc": p_under_r,
            "p_push_mc": p_push_r,
            "mc_expected_margin": round(float(np.mean(sim_margins)), 2),
            "mc_expected_total": round(float(np.mean(sim_totals)), 2),
            "overtime_prob": round(float(np.mean(ot_mask)), 4),
            "multi_overtime_prob": round(float(np.mean(multi_ot_mask)), 4),
            "expected_ot_periods_given_ot": round(float(np.mean(ot_periods[ot_mask])), 3) if np.any(ot_mask) else 0.0,
            "max_ot_periods_simulated": float(int(np.max(ot_periods))),
            "historical_nba_ot_rate": self.HISTORICAL_NBA_OT_RATE,
            "historical_nba_multi_ot_conditional_rate": self.HISTORICAL_NBA_MULTI_OT_CONDITIONAL_RATE,
            "blowout_prob": round(float(np.mean(is_blowout_q3)), 4),
            "clutch_foul_prob": round(float(np.mean(foul_trigger)), 4),
            "simulation_q10_total": round(float(q10_tot), 1),
            "simulation_q90_total": round(float(q90_tot), 1),
            "simulation_q10_margin": round(float(q10_mar), 1),
            "simulation_q90_margin": round(float(q90_mar), 1),
            "is_conformal": 0.0,
            "n_simulations": float(self.n_simulations),
        }
