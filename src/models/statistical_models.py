"""
Statistical NBA Models (`src/models/statistical_models.py`).
Facade re-exporting all quantitative models and common feature schemas for backward compatibility:
- Model A: BaselineModel (historical reference probabilities and rolling rates)
- Model B: EloModel (dual-speed MOV-adjusted Elo with offseason regression, rest density, geodesic travel & altitude)
- Model C: PointMarginModel (residual-anchored RidgeCV on pace-decoupled efficiency, Elo spread, rest, venue splits & surge)
- Model D: TotalPointsModel (normal distribution with score covariance, tempo decoupling, B2B & blowout drag)
- Model E: AdvancedGBMModel (residual-boosted LightGBM evaluated strictly out-of-sample)
- Model G: DeepMonteCarloHybridModel (10,000-game Q1-Q4 + OT possession simulator with moment-matched expectations)
- Model F: EnsembleStackingModel (out-of-sample shrinkage-weighted log-odds pool)
- MarketResidualModel: Logit-Space Market Residual Learning with Empirical Training
"""

from __future__ import annotations

from src.features.builder import build_pregame_features
from src.models.baseline import BaselineModel
from src.models.common import (
    FEATURE_COLUMNS,
    MARGIN_FEATURE_COLUMNS,
    TOTAL_FEATURE_COLUMNS,
    _filter_strictly_prior_final_games,
)
from src.models.deep_monte_carlo import DeepMonteCarloHybridModel
from src.models.elo import EloModel
from src.models.ensemble import EnsembleStackingModel
from src.models.gbm_model import AdvancedGBMModel
from src.models.market_residual import MarketResidualModel
from src.models.point_margin import PointMarginModel
from src.models.total_points import TotalPointsModel

__all__ = [
    "FEATURE_COLUMNS",
    "MARGIN_FEATURE_COLUMNS",
    "TOTAL_FEATURE_COLUMNS",
    "_filter_strictly_prior_final_games",
    "build_pregame_features",
    "BaselineModel",
    "EloModel",
    "PointMarginModel",
    "TotalPointsModel",
    "AdvancedGBMModel",
    "DeepMonteCarloHybridModel",
    "EnsembleStackingModel",
    "MarketResidualModel",
]
