"""
Modelo A: Baseline NBA Model.
Uses historical home win frequency, team rolling win rates, and historical total points distribution.
Provides an explicit benchmark to measure whether complex models add value.
"""

from __future__ import annotations

from typing import Any
import numpy as np
from scipy.stats import norm

from src.features.builder import build_pregame_features
from src.models.common import _filter_strictly_prior_final_games
from src.validation.validator import validate_essential_features


class BaselineModel:
    """
    Modelo A (Baseline):
    Uses historical home win frequency, team rolling win rates, and historical total points distribution.
    Provides an explicit benchmark to measure whether complex models add value.
    """

    model_family = "model_a_baseline"

    def __init__(self, version_id: str = "model_a_baseline_v1") -> None:
        self.version_id = version_id
        self.historical_home_win_rate: float = 0.565
        self.historical_total_mean: float = 228.5
        self.historical_total_std: float = 18.2

    def fit(self, historical_games: list[dict[str, Any]], cutoff_time_str: str) -> None:
        prior = _filter_strictly_prior_final_games(historical_games, cutoff_time_str)
        if not prior:
            return
        home_wins = [1.0 if g["home_score"] > g["away_score"] else 0.0 for g in prior]
        totals = [float(g["home_score"] + g["away_score"]) for g in prior]
        self.historical_home_win_rate = float(np.clip(np.mean(home_wins), 0.35, 0.70))
        self.historical_total_mean = float(np.mean(totals))
        self.historical_total_std = max(10.0, float(np.std(totals, ddof=1)) if len(totals) > 2 else 18.2)

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
    ) -> dict[str, Any]:
        feats = build_pregame_features(game, historical_games, market="moneyline")
        win_pct_diff = feats["home_recent_win_pct"] - feats["away_recent_win_pct"]
        p_home = float(np.clip(self.historical_home_win_rate + 0.15 * win_pct_diff, 0.08, 0.92))
        return {
            "p_home": round(p_home, 6),
            "p_away": round(1.0 - p_home, 6),
            "uncertainty_std": 0.085,
        }

    def predict_total_points(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
        line_value: float,
    ) -> dict[str, float]:
        validate_essential_features(game, "total_points")
        p_over = float(np.clip(1.0 - norm.cdf(line_value, loc=self.historical_total_mean, scale=self.historical_total_std), 0.05, 0.95))
        return {
            "expected_total": round(self.historical_total_mean, 2),
            "total_std": round(self.historical_total_std, 2),
            "p_over": round(p_over, 6),
            "p_under": round(1.0 - p_over, 6),
            "uncertainty_std": 0.09,
        }
