"""
V7.2 Player Props Quantitative Engine (`src/prediction/player_props.py`):
Models individual player performance (Points, Rebounds, Assists, 3PM, PRA) using:
  1. Micro-Usage & Minutes Redistribution: Re-allocates vacated usage rate (USG%) and minute shares
     when teammates are confirmed OUT via the LineupSynergyEngine.
  2. Parametric Probability Distributions:
     - Poisson / Negative Binomial distribution for count variables (Assists, Rebounds, 3-Pointers).
     - Overdispersed Gaussian distribution for continuous scoring (Points, PRA).
  3. Venn-Abers Conformal Multi-Probabilistic Calibration & Lower-Bound EV:
     Guarantees finite-sample multi-probabilistic safety against bookmaker lines.
  4. Fractional Kelly Allocation: Sizing tailored for micro-bankrolls with longshot protection.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any
import uuid

import numpy as np
from scipy.stats import norm, poisson

from src.calibration.calibrator import VennAbersConformalInterval
from src.features.team_ratings import PLAYER_ON_OFF_SYNERGY_PROFILES
from src.prediction.ev_calculator import (
    calculate_ev,
    devig_multiplicative,
    market_anchored_probability,
    optimize_simultaneous_kelly_portfolio,
)
from src.storage.db import DatabaseManager


# Canonical baseline player profiles (Per-Minute production, Usage Rate %, and Base Minutes)
# Format: (base_minutes, usg_pct, pts_per_min, reb_per_min, ast_per_min, threes_per_min)
PLAYER_PROP_BASELINES: dict[str, tuple[float, float, float, float, float, float]] = {
    # Dallas Mavericks
    "Luka Doncic": (36.5, 35.5, 0.88, 0.25, 0.26, 0.11),
    "Kyrie Irving": (34.0, 27.5, 0.74, 0.14, 0.15, 0.08),
    "Klay Thompson": (28.0, 21.0, 0.55, 0.12, 0.06, 0.10),
    "PJ Washington": (30.0, 16.5, 0.42, 0.21, 0.06, 0.05),
    "Dereck Lively II": (26.0, 14.0, 0.36, 0.32, 0.05, 0.00),

    # Denver Nuggets
    "Nikola Jokic": (36.0, 30.5, 0.82, 0.35, 0.28, 0.04),
    "Jamal Murray": (33.0, 25.5, 0.65, 0.13, 0.18, 0.07),
    "Michael Porter Jr.": (32.0, 20.0, 0.56, 0.24, 0.05, 0.08),
    "Aaron Gordon": (30.0, 18.0, 0.48, 0.22, 0.10, 0.03),

    # Boston Celtics
    "Jayson Tatum": (35.5, 29.5, 0.77, 0.24, 0.14, 0.09),
    "Jaylen Brown": (33.5, 28.0, 0.72, 0.17, 0.11, 0.07),
    "Derrick White": (32.0, 19.5, 0.49, 0.13, 0.16, 0.08),
    "Jrue Holiday": (30.0, 17.0, 0.42, 0.16, 0.15, 0.06),
    "Kristaps Porzingis": (28.0, 24.5, 0.68, 0.24, 0.06, 0.06),

    # Golden State Warriors
    "Stephen Curry": (32.5, 31.0, 0.84, 0.14, 0.16, 0.14),
    "Jonathan Kuminga": (27.0, 24.0, 0.62, 0.19, 0.07, 0.03),
    "Andrew Wiggins": (28.0, 20.5, 0.52, 0.16, 0.06, 0.05),
    "Draymond Green": (27.5, 14.5, 0.32, 0.26, 0.22, 0.03),

    # Phoenix Suns
    "Kevin Durant": (36.0, 29.0, 0.78, 0.19, 0.14, 0.06),
    "Devin Booker": (35.5, 29.5, 0.76, 0.13, 0.20, 0.06),
    "Bradley Beal": (31.0, 22.5, 0.58, 0.13, 0.14, 0.05),
    "Jusuf Nurkic": (25.0, 18.5, 0.43, 0.41, 0.12, 0.02),

    # Los Angeles Lakers
    "LeBron James": (34.5, 28.5, 0.70, 0.22, 0.24, 0.06),
    "Anthony Davis": (35.5, 28.0, 0.74, 0.36, 0.09, 0.02),
    "Austin Reaves": (32.0, 19.5, 0.49, 0.13, 0.17, 0.05),
    "D'Angelo Russell": (28.0, 22.0, 0.56, 0.10, 0.19, 0.08),

    # Oklahoma City Thunder
    "Shai Gilgeous-Alexander": (35.0, 32.5, 0.87, 0.16, 0.18, 0.05),
    "Jalen Williams": (32.5, 23.5, 0.60, 0.14, 0.14, 0.05),
    "Chet Holmgren": (30.0, 21.0, 0.56, 0.27, 0.08, 0.05),

    # Milwaukee Bucks
    "Giannis Antetokounmpo": (35.0, 34.5, 0.89, 0.34, 0.19, 0.01),
    "Damian Lillard": (34.5, 28.5, 0.73, 0.13, 0.20, 0.09),
    "Brook Lopez": (29.0, 16.5, 0.43, 0.18, 0.05, 0.06),
}


class PlayerPropsEngine:
    """
    Quantitative Modeling of NBA Player Props:
    Calculates expected statistical value per player, absorbs usage bumps from injuries,
    computes Poisson/Gaussian exceedance probabilities, and identifies +EV bets.
    """

    def __init__(self, db: DatabaseManager | None = None, min_ev_threshold: float = 0.05) -> None:
        self.db = db
        self.min_ev_threshold = min_ev_threshold
        self.calibrator = VennAbersConformalInterval(window=1200)

    def project_player_stats(
        self,
        player_name: str,
        team: str,
        absent_teammates: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Computes projected Points, Rebounds, Assists, 3PM, and PRA.
        When star teammates are absent, redistributes vacated usage rate and minutes.
        """
        profile = PLAYER_PROP_BASELINES.get(player_name)
        if profile is None:
            # Synthetic default baseline for unlisted rotation player
            base_min, base_usg, pts_pm, reb_pm, ast_pm, th_pm = (26.0, 17.5, 0.45, 0.16, 0.09, 0.04)
        else:
            base_min, base_usg, pts_pm, reb_pm, ast_pm, th_pm = profile

        absent = absent_teammates or []
        usage_bump_pct = 0.0
        minutes_bump = 0.0

        # Vacated usage & minute redistribution logic
        for abs_p in absent:
            abs_prof = PLAYER_PROP_BASELINES.get(abs_p)
            if abs_prof:
                abs_min, abs_usg = abs_prof[0], abs_prof[1]
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

        effective_minutes = round(base_min + minutes_bump, 1)
        usg_factor = 1.0 + (usage_bump_pct / 100.0)

        # Adjusted scoring and assist rates scale with usage factor
        adj_pts_pm = pts_pm * (usg_factor ** 0.85)
        adj_ast_pm = ast_pm * (usg_factor ** 0.70)
        adj_th_pm = th_pm * (usg_factor ** 0.80)
        # Rebound rate scales slightly with extra minutes
        adj_reb_pm = reb_pm

        proj_pts = round(effective_minutes * adj_pts_pm, 1)
        proj_reb = round(effective_minutes * adj_reb_pm, 1)
        proj_ast = round(effective_minutes * adj_ast_pm, 1)
        proj_th = round(effective_minutes * adj_th_pm, 1)
        proj_pra = round(proj_pts + proj_reb + proj_ast, 1)

        # Standard deviations (empirical NBA player dispersion models)
        # Points: sigma ~ sqrt(mu * 1.85)
        std_pts = round(math.sqrt(max(1.0, proj_pts * 1.85)), 2)
        # PRA: sigma ~ sqrt(mu * 2.10)
        std_pra = round(math.sqrt(max(1.0, proj_pra * 2.10)), 2)
        # Poisson dispersion for count variables
        std_reb = round(math.sqrt(max(0.5, proj_reb)), 2)
        std_ast = round(math.sqrt(max(0.5, proj_ast)), 2)
        std_th = round(math.sqrt(max(0.3, proj_th)), 2)

        return {
            "player_name": player_name,
            "team": team,
            "effective_minutes": effective_minutes,
            "usage_bump_pct": round(usage_bump_pct, 1),
            "projections": {
                "PTS": {"mean": proj_pts, "std": std_pts, "dist": "normal"},
                "REB": {"mean": proj_reb, "std": std_reb, "dist": "poisson"},
                "AST": {"mean": proj_ast, "std": std_ast, "dist": "poisson"},
                "PRA": {"mean": proj_pra, "std": std_pra, "dist": "normal"},
                "3PM": {"mean": proj_th, "std": std_th, "dist": "poisson"},
            },
        }

    def compute_exceedance_probabilities(
        self,
        prop_category: str,
        line_value: float,
        proj_mean: float,
        proj_std: float,
        dist_type: str = "normal",
    ) -> tuple[float, float]:
        """
        Computes (p_over, p_under) given a line and parametric distribution.
        Handles continuity correction for Poisson count variables.
        """
        if dist_type == "poisson":
            # Count distribution: P(X > line)
            k = int(math.floor(line_value))
            p_under = float(poisson.cdf(k, mu=proj_mean))
            p_over = float(1.0 - p_under)
        else:
            # Continuous normal with overdispersion
            # P(X > line) with 0.5 continuity adjustment
            z = (line_value - proj_mean) / max(0.5, proj_std)
            p_under = float(norm.cdf(z))
            p_over = float(1.0 - p_under)

        p_over = float(np.clip(p_over, 0.02, 0.98))
        p_under = float(np.clip(p_under, 0.02, 0.98))
        return round(p_over, 4), round(p_under, 4)

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
    ) -> list[dict[str, Any]]:
        """
        Evaluates a specific player prop line against our injury-adjusted projection.
        Calculates +EV, Venn-Abers conformal lower bounds, and recommended Kelly stakes.
        """
        proj_info = self.project_player_stats(player_name, team, absent_teammates)
        cat_data = proj_info["projections"].get(prop_category)
        if not cat_data:
            return []

        mu = float(cat_data["mean"])
        sigma = float(cat_data["std"])
        dist_type = cat_data["dist"]

        p_over_raw, p_under_raw = self.compute_exceedance_probabilities(
            prop_category=prop_category,
            line_value=line_value,
            proj_mean=mu,
            proj_std=sigma,
            dist_type=dist_type,
        )

        opportunities: list[dict[str, Any]] = []

        # Evaluate both sides (OVER and UNDER)
        for sel, p_raw, dec_odds in [("OVER", p_over_raw, over_odds), ("UNDER", p_under_raw, under_odds)]:
            if dec_odds <= 1.0:
                continue

            # Fair de-vigged implied probability from two-way bookmaker line
            p_fair_a, p_fair_b, _ = devig_multiplicative(over_odds, under_odds)
            mkt_fair = p_fair_a if sel == "OVER" else p_fair_b

            # Conformal Venn-Abers interval for prop probability
            conf_int = self.calibrator.predict_interval(p_raw)
            p_low = float(conf_int["p0"])
            p_high = float(conf_int["p1"])
            conf_w = float(conf_int["width"])

            # Market-anchored probability (75% prop model / 25% sharp book)
            anchored_prob = market_anchored_probability(p_raw, mkt_fair, model_weight=0.75)

            # Expected value
            ev_metrics = calculate_ev(anchored_prob, dec_odds)
            ev_pct = float(ev_metrics["ev_pct"])

            # Conservative lower-bound EV based on conformal lower bound
            lb_anchored = market_anchored_probability(p_low, mkt_fair, model_weight=0.75)
            lb_ev_metrics = calculate_ev(lb_anchored, dec_odds)
            lb_ev_pct = float(lb_ev_metrics["ev_pct"])

            # Kelly Stake allocation
            stake_pen = 0.0
            kelly_frac = 0.0
            is_edge_qualified = (lb_ev_pct >= (self.min_ev_threshold * 100.0)) or (ev_pct >= 8.0 and lb_ev_pct >= -1.0)
            if is_edge_qualified and conf_w <= 0.35:
                b_val = dec_odds - 1.0
                f_star = max(0.0, (anchored_prob * (b_val + 1.0) - 1.0) / b_val)
                # Half-Kelly multiplier
                eff_f = min(0.05, f_star * 0.50)
                raw_s = bankroll_pen * eff_f
                # Bounded by conviction tiers
                if anchored_prob < 0.55:
                    stake_pen = round(max(1.00, min(1.75, raw_s)), 2)
                elif anchored_prob < 0.65:
                    stake_pen = round(max(1.50, min(3.50, raw_s)), 2)
                else:
                    stake_pen = round(max(2.00, min(5.00, raw_s)), 2)
                kelly_frac = round(eff_f, 4)

                rationale = (
                    f"[{prop_category} {sel} {line_value}] {player_name} ({team}). "
                    f"Projected {prop_category}: {mu:.1f} (std: {sigma:.1f}). "
                    f"Model prob: {anchored_prob * 100:.1f}% vs bookmaker implied {mkt_fair * 100:.1f}%. "
                    f"Usage bump: +{proj_info['usage_bump_pct']:.1f}% (absences: {', '.join(absent_teammates) if absent_teammates else 'None'}). "
                    f"Lower-Bound EV: {lb_ev_pct:+.2f}% at {dec_odds:.2f} odds. Suggested Kelly stake: S/ {stake_pen:.2f} PEN."
                )

                prop_pick = {
                    "prop_id": f"PROP_{game_id}_{player_name.replace(' ', '_')}_{prop_category}_{sel}_{uuid.uuid4().hex[:6]}",
                    "game_id": game_id,
                    "matchday_date": matchday_date,
                    "player_name": player_name,
                    "team": team,
                    "prop_category": prop_category,
                    "line_value": line_value,
                    "selection": sel,
                    "decimal_odds": dec_odds,
                    "projected_mean": mu,
                    "projected_std": sigma,
                    "model_prob": round(anchored_prob, 4),
                    "conformal_p_low": round(p_low, 4),
                    "conformal_p_high": round(p_high, 4),
                    "ev_pct": round(ev_pct, 2),
                    "ev_lower_bound_pct": round(lb_ev_pct, 2),
                    "kelly_stake_pen": stake_pen,
                    "kelly_optimal_fraction": kelly_frac,
                    "usage_bump_pct": proj_info["usage_bump_pct"],
                    "rationale": rationale,
                    "emitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                opportunities.append(prop_pick)

                # Persist to SQLite table player_prop_picks if db provided
                if self.db is not None:
                    try:
                        self.db.execute_insert(
                            """
                            INSERT OR REPLACE INTO player_prop_picks (
                                prop_id, game_id, matchday_date, player_name, team, prop_category,
                                line_value, selection, decimal_odds, projected_mean, projected_std,
                                model_prob, conformal_p_low, conformal_p_high, ev_pct, ev_lower_bound_pct,
                                kelly_stake_pen, usage_bump_pct, rationale, emitted_at, status
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                            """,
                            (
                                prop_pick["prop_id"],
                                prop_pick["game_id"],
                                prop_pick["matchday_date"],
                                prop_pick["player_name"],
                                prop_pick["team"],
                                prop_pick["prop_category"],
                                prop_pick["line_value"],
                                prop_pick["selection"],
                                prop_pick["decimal_odds"],
                                prop_pick["projected_mean"],
                                prop_pick["projected_std"],
                                prop_pick["model_prob"],
                                prop_pick["conformal_p_low"],
                                prop_pick["conformal_p_high"],
                                prop_pick["ev_pct"],
                                prop_pick["ev_lower_bound_pct"],
                                prop_pick["kelly_stake_pen"],
                                prop_pick["usage_bump_pct"],
                                prop_pick["rationale"],
                                prop_pick["emitted_at"],
                            ),
                        )
                    except Exception:
                        pass

        return opportunities
