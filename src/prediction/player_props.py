"""
Quarantined compatibility facade for `PlayerPropsEngine`.

Production status: QUARANTINED (`allow_player_props_betting: false`, `allow_parlays: false`
in `config/model_config.yaml`). Implementation lives in `src/prediction/props/`.
"""

from __future__ import annotations

from src.prediction.props import (
    EXPERIMENTAL_QUARANTINED,
    PLAYER_BASELINES,
    PLAYER_PROP_BASELINES,
    TEAM_DEFENSIVE_MULTIPLIERS,
    PlayerPropsEngine,
    _normalize_player_match_key,
    _parse_observed_prop_provider,
    get_fallback_rosters,
)

__all__ = [
    "EXPERIMENTAL_QUARANTINED",
    "PLAYER_BASELINES",
    "PLAYER_PROP_BASELINES",
    "TEAM_DEFENSIVE_MULTIPLIERS",
    "PlayerPropsEngine",
    "_normalize_player_match_key",
    "_parse_observed_prop_provider",
    "get_fallback_rosters",
]
