"""
V9 Phase 1: Hurdle Minutes & Foul Trouble Hazard Engine (src/prediction/minutes_model.py).
Provides a two-stage hurdle model for NBA player rotation participation and conditional
minutes distributions (P10 floor, P50 median, P90 ceiling) with blowout risk decay
and referee-conditioned foul trouble hazard survival.
"""

from __future__ import annotations

import math


class MinutesProjectionEngine:
    """
    Two-stage hurdle and quantile minutes projection model:
    Stage 1: P(Minutes > 0) hurdle classification (active rotation filter)
    Stage 2: Quantile conditional minutes projection (P10 floor, P50 median, P90 ceiling)
             adjusted for blowout risk, referee crew foul rate, and coach rotation rigidity.
    """

    def __init__(self, default_pace: float = 99.5) -> None:
        self.default_pace = default_pace

    def predict_participation_prob(
        self,
        injury_status: str | None = None,
        rotation_role: str = "STARTER",
        player_name: str = "",
        team: str = "",
        days_rest: int = 1,
    ) -> float:
        """
        Stage 1: Hurdle Classifier estimating probability that player logs > 0 minutes.
        Eliminates DNP (Did Not Play / Coach's Decision) distortions on secondary players.
        """
        status_clean = (injury_status or "").upper().strip()
        if status_clean in ("OUT", "SUSPENDED", "INACTIVE"):
            return 0.00
        if status_clean in ("DOUBTFUL", "DOUBT"):
            return 0.15
        if status_clean in ("QUESTIONABLE", "QUESTION", "GTD"):
            return 0.50
        if status_clean in ("PROBABLE", "DAY_TO_DAY"):
            return 0.88

        role_clean = rotation_role.upper().strip()
        if role_clean == "STARTER":
            return 0.98
        elif role_clean in ("SIXTH_MAN", "KEY_RESERVE"):
            return 0.92
        elif role_clean == "BENCH_ROTATION":
            return 0.80
        elif role_clean == "DEEP_BENCH":
            return 0.40

        return 0.85

    # Descriptive alias
    predict_participation_probability = predict_participation_prob

    def predict_minutes_quantiles(
        self,
        player_name: str = "Player",
        team: str = "NBA",
        baseline_minutes: float | None = None,
        base_minutes: float | None = None,
        spread_margin: float | None = None,
        spread: float | None = None,
        expected_pace: float = 99.5,
        referee_foul_rate: float = 1.0,
        foul_proneness: float | None = None,
        foul_trouble_prone: bool = False,
        is_starter: bool = True,
        coach_rotation_rigidity: float = 1.0,
        injury_status: str | None = None,
        days_rest: int = 1,
    ) -> dict[str, float]:
        """
        Stage 2: Quantile minutes distribution conditional on game context:
        - Spread blowout risk: logistic penalty on minutes when spread >= 8.5
        - Foul trouble hazard: hazard penalty from referee crew tightness
        - Pace adjustment: minute expansion/compression from fast/slow pace
        """
        effective_base = float(base_minutes if base_minutes is not None else (baseline_minutes if baseline_minutes is not None else 30.0))
        effective_spread = float(spread if spread is not None else (spread_margin if spread_margin is not None else 0.0))
        effective_foul = float(foul_proneness if foul_proneness is not None else (1.35 if foul_trouble_prone else 1.0))

        base_min = max(6.0, min(42.0, effective_base))
        abs_spread = abs(effective_spread)

        # 1. Blowout risk logistic function: P(Blowout) rises when spread > 8.5
        # Scale = 0.22, center = 9.0 points
        blowout_prob = 1.0 / (1.0 + math.exp(-0.25 * (abs_spread - 8.5)))
        blowout_prob = max(0.05, min(0.65, blowout_prob))

        # Starters lose minutes in blowouts; bench reserves gain garbage time minutes
        if is_starter:
            blowout_delta = -5.0 * blowout_prob * coach_rotation_rigidity
        else:
            blowout_delta = +4.0 * blowout_prob * coach_rotation_rigidity

        # 2. Foul trouble hazard: risk of early 2nd/3rd quarter benching
        # referee_foul_rate > 1.0 indicates tight whistle crew chief
        foul_hazard = max(0.02, min(0.40, 0.09 * float(referee_foul_rate) * float(effective_foul)))
        foul_delta = -4.2 * foul_hazard

        # 3. Game pace adjustment
        pace_ratio = (float(expected_pace) - self.default_pace) / self.default_pace
        pace_delta = pace_ratio * 1.5

        # Median minutes (P50)
        p50_median = max(6.0, min(41.0, base_min + blowout_delta + foul_delta + pace_delta))

        # Floor (P10): early foul trouble or heavy blowout benching
        p10_floor = max(4.0, p50_median - 6.8 * (1.0 + foul_hazard))

        # Ceiling (P90): overtime risk or tight game with coach running stars into high 30s
        p90_ceiling = min(42.5, p50_median + 4.8)

        # Expected value (weighted quantile composite: 20% P10 + 60% P50 + 20% P90)
        mean_minutes = (0.20 * p10_floor) + (0.60 * p50_median) + (0.20 * p90_ceiling)

        return {
            "p10_floor": round(p10_floor, 1),
            "p50_median": round(p50_median, 1),
            "p90_ceiling": round(p90_ceiling, 1),
            "mean_minutes": round(mean_minutes, 2),
            "blowout_risk": round(blowout_prob, 3),
            "foul_trouble_hazard": round(foul_hazard, 3),
            "blowout_delta_minutes": round(blowout_delta, 2),
            "foul_delta_minutes": round(foul_delta, 2),
        }

    def adjust_stat_projection_by_minutes(
        self,
        raw_stat_mean: float,
        baseline_minutes: float,
        projected_minutes_info: dict[str, float],
    ) -> dict[str, float]:
        """
        Scales per-minute rate stats by the conditional minutes distribution.
        """
        base_min = max(5.0, float(baseline_minutes))
        stat_per_min = float(raw_stat_mean) / base_min

        adj_mean = stat_per_min * float(projected_minutes_info["mean_minutes"])
        adj_p10 = stat_per_min * float(projected_minutes_info["p10_floor"])
        adj_p50 = stat_per_min * float(projected_minutes_info["p50_median"])
        adj_p90 = stat_per_min * float(projected_minutes_info["p90_ceiling"])

        return {
            "stat_per_minute": round(stat_per_min, 4),
            "adjusted_mean": round(adj_mean, 2),
            "stat_p10_floor": round(adj_p10, 2),
            "stat_p50_median": round(adj_p50, 2),
            "stat_p90_ceiling": round(adj_p90, 2),
        }
