"""
Contextual NBA domain constants for ingestion adapters:
- Star player spread point values
- High-altitude home court bonuses
- NBA referee crew profiles (over/under and home margin tendencies)
- Long-term injury classification keywords

Dynamically loaded from config/situational_factors.json.
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


def _load_situational_factors_json() -> dict[str, Any]:
    p = _resolve_config_path("situational_factors.json")
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load situational_factors.json: %s", exc)
    return {}


_factors = _load_situational_factors_json()

# High-impact NBA star players (estimated point spread value when ruled OUT)
STAR_PLAYER_IMPACT_PTS: dict[str, float] = {
    k: float(v) for k, v in _factors.get("star_player_impact_pts", {}).items()
}

# High-altitude home courts (extra home advantage in points)
HIGH_ALTITUDE_BONUS_PTS: dict[str, float] = {
    k: float(v) for k, v in _factors.get("high_altitude_bonus_pts", {}).items()
}

# NBA Official Referee Crew Profiles: (total_points_delta_per_ref, home_margin_delta_per_ref)
NBA_REFEREE_CREW_PROFILE: dict[str, tuple[float, float]] = {
    k: (float(v[0]), float(v[1]))
    for k, v in _factors.get("referee_crew_profiles", {}).items()
}

# Long-term injury keywords
LONG_TERM_INJURY_KEYWORDS: tuple[str, ...] = tuple(
    _factors.get("long_term_injury_keywords", [])
)
