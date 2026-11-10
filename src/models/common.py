"""
Common feature definitions and utility functions for NBA statistical models.
"""

from __future__ import annotations

from typing import Any

from src.validation.validator import parse_iso_utc


FEATURE_COLUMNS: list[str] = [
    "home_off_rtg",
    "home_def_rtg",
    "away_off_rtg",
    "away_def_rtg",
    "net_rtg_diff",
    "matchup_mismatch",
    "expected_pace",
    "pace_clash",
    "rest_diff",
    "b2b_advantage",
    "fatigue_diff",
    "altitude_advantage",
    "travel_miles_diff",
    "venue_split_diff",
    "streak_diff",
    "recent_margin_diff",
    "form_surge_diff",
    "recent_total_trend",
    "four_factors_diff",
    "shot_quality_xeFG_diff",
    "elo_spread",
    "structural_margin",
    "structural_total",
    "home_court_indicator",
]

MARGIN_FEATURE_COLUMNS: list[str] = [
    "elo_spread",
    "eff_spread",
    "structural_margin",
    "four_factors_diff",
    "shot_quality_xeFG_diff",
    "net_rtg_diff",
    "fatigue_diff",
    "altitude_advantage",
    "form_surge_diff",
    "recent_margin_diff",
    "expected_pace",
]

TOTAL_FEATURE_COLUMNS: list[str] = [
    "structural_total",
    "off_def_sum",
    "tempo_sum",
    "b2b_total_drag",
    "blowout_drag",
    "expected_pace",
    "pace_clash",
    "recent_total_trend",
]


def _filter_strictly_prior_final_games(
    historical_games: list[dict[str, Any]],
    cutoff_time_str: str,
) -> list[dict[str, Any]]:
    cutoff_dt = parse_iso_utc(cutoff_time_str)
    valid = [
        g
        for g in historical_games
        if g.get("status") == "FINAL"
        and g.get("home_score") is not None
        and g.get("away_score") is not None
        and (
            str(g.get("game_start_time", "")) < cutoff_time_str
            if len(str(g.get("game_start_time", ""))) == len(cutoff_time_str)
            else parse_iso_utc(g["game_start_time"]) < cutoff_dt
        )
    ]
    valid.sort(key=lambda g: (str(g.get("game_start_time", "")), str(g.get("game_id", ""))))
    return valid
