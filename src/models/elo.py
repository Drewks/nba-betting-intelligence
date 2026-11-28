"""
Modelo B: Elo NBA Model.
Dual-horizon Margin-of-Victory Elo system adjusted for modern NBA home-court advantage (50 Elo),
offseason regression (0.66 carryover), schedule density fatigue, geodesic travel, and altitude.
"""

from __future__ import annotations

from typing import Any
import numpy as np

from src.features.builder import build_pregame_features


class EloModel:
    """
    Modelo B (Elo):
    Dual-horizon Margin-of-Victory Elo system adjusted for modern NBA home-court advantage (50 Elo),
    offseason regression (0.66 carryover), schedule density fatigue, geodesic travel, and altitude.
    """

    model_family = "model_b_elo"

    def __init__(
        self,
        version_id: str = "model_b_elo_v1",
        initial_rating: float = 1500.0,
        k_factor: float = 21.0,
        home_advantage_elo: float = 50.0,
        rest_advantage_per_day: float = 15.0,
    ) -> None:
        self.version_id = version_id
        self.initial_rating = initial_rating
        self.k_factor = k_factor
        self.home_advantage_elo = home_advantage_elo
        self.rest_advantage_per_day = rest_advantage_per_day
        self.ratings: dict[str, float] = {}

    def predict_moneyline(
        self,
        game: dict[str, Any],
        historical_games: list[dict[str, Any]],
    ) -> dict[str, Any]:
        feats = build_pregame_features(game, historical_games, market="moneyline")
        r_home = feats["elo_home"]
        r_away = feats["elo_away"]
        elo_diff = feats["elo_diff"]
        p_home = float(np.clip(feats["p_elo"], 0.05, 0.95))
        self.ratings[game["home_team"]] = r_home
        self.ratings[game["away_team"]] = r_away
        return {
            "home_elo": round(r_home, 2),
            "away_elo": round(r_away, 2),
            "elo_diff": round(elo_diff, 2),
            "p_home": round(p_home, 6),
            "p_away": round(1.0 - p_home, 6),
            "uncertainty_std": 0.055,
        }
