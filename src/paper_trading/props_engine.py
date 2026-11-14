"""
Paper Trading & Quantitative Player Props Engine (`src/paper_trading/props_engine.py`).

Re-exports `PlayerPropsEngine` and strict observed-prop provider parsing utilities
from `src.prediction.player_props` so callers referencing either module path access
the identical zero-synthetic, exact-(player, category)-matched engine.
"""

from __future__ import annotations

from src.prediction.player_props import (
    PLAYER_BASELINES,
    PLAYER_PROP_BASELINES,
    TEAM_DEFENSIVE_MULTIPLIERS,
    PlayerPropsEngine,
    _normalize_player_match_key,
    _parse_observed_prop_provider,
    get_fallback_rosters,
)

__all__ = [
    "PLAYER_BASELINES",
    "PLAYER_PROP_BASELINES",
    "TEAM_DEFENSIVE_MULTIPLIERS",
    "PlayerPropsEngine",
    "_normalize_player_match_key",
    "_parse_observed_prop_provider",
    "get_fallback_rosters",
]
