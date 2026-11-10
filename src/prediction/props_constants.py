"""
NBA Player Props Constants and Baseline Priors (`src/prediction/props_constants.py`).
Loads per-player statistical baselines, defensive multipliers (DvP), and fallback rosters
dynamically from external JSON configurations under config/.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_config_path(filename: str) -> Path:
    """Resolves config file path robustly across arbitrary working directories."""
    candidate = Path("config") / filename
    if candidate.exists():
        return candidate
    alt = Path(__file__).resolve().parent.parent.parent / "config" / filename
    return alt


def load_player_prop_baselines() -> dict[str, tuple[float, float, float, float, float, float]]:
    """Loads baseline player profiles (base_min, usg_pct, pts/min, reb/min, ast/min, 3pm/min) from JSON."""
    p = _resolve_config_path("player_prop_baselines.json")
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            return {
                k: (float(v[0]), float(v[1]), float(v[2]), float(v[3]), float(v[4]), float(v[5]))
                for k, v in raw.items()
            }
        except Exception as exc:
            logger.warning("Failed to load player_prop_baselines.json: %s", exc)
    return {}


def load_team_defensive_multipliers() -> dict[str, dict[str, Any]]:
    """Loads Tactical Defense vs Position (DvP) and Pace multipliers for all 30 teams from JSON."""
    p = _resolve_config_path("team_defensive_multipliers.json")
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load team_defensive_multipliers.json: %s", exc)
    return {}


# Module-level dynamically loaded dictionaries for full backward compatibility
PLAYER_PROP_BASELINES: dict[str, tuple[float, float, float, float, float, float]] = load_player_prop_baselines()
PLAYER_BASELINES = PLAYER_PROP_BASELINES
TEAM_DEFENSIVE_MULTIPLIERS: dict[str, dict[str, Any]] = load_team_defensive_multipliers()

_FALLBACK_ROSTERS_CACHE: dict[str, list[str]] | None = None


def get_fallback_rosters() -> dict[str, list[str]]:
    """Loads fallback rosters from config/fallback_rosters.json with caching."""
    global _FALLBACK_ROSTERS_CACHE
    if _FALLBACK_ROSTERS_CACHE is not None:
        return _FALLBACK_ROSTERS_CACHE
    p = _resolve_config_path("fallback_rosters.json")
    if p.exists():
        try:
            _FALLBACK_ROSTERS_CACHE = json.loads(p.read_text(encoding="utf-8"))
            return _FALLBACK_ROSTERS_CACHE
        except Exception:
            pass
    _FALLBACK_ROSTERS_CACHE = {}
    return _FALLBACK_ROSTERS_CACHE
