"""Constructs strictly pre-game team features and historical rolling statistics without lookahead."""

from __future__ import annotations

from typing import Any
import numpy as np

from src.validation.validator import parse_iso_utc, validate_essential_features


def build_pregame_features(
    target_game: dict[str, Any],
    historical_final_games: list[dict[str, Any]],
    market: str = "moneyline",
    rolling_window: int = 10,
) -> dict[str, float]:
    """
    Computes pre-game feature vector for target_game using ONLY historical games
    that finished strictly before target_game['game_start_time'].
    """
    validate_essential_features(target_game, market)
    target_start = parse_iso_utc(target_game["game_start_time"])
    home_team = target_game["home_team"]
    away_team = target_game["away_team"]

    prior_games = [
        g
        for g in historical_final_games
        if g.get("status") == "FINAL"
        and g.get("home_score") is not None
        and g.get("away_score") is not None
        and parse_iso_utc(g["game_start_time"]) < target_start
    ]
    prior_games.sort(key=lambda g: g["game_start_time"])

    def _recent_margins(team_code: str) -> list[float]:
        margins: list[float] = []
        for g in prior_games:
            if g["home_team"] == team_code:
                margins.append(float(g["home_score"] - g["away_score"]))
            elif g["away_team"] == team_code:
                margins.append(float(g["away_score"] - g["home_score"]))
        return margins[-rolling_window:]

    home_margins = _recent_margins(home_team)
    away_margins = _recent_margins(away_team)

    home_recent_net = float(np.mean(home_margins)) if home_margins else 0.0
    away_recent_net = float(np.mean(away_margins)) if away_margins else 0.0
    home_win_pct = float(np.mean([1.0 if m > 0 else 0.0 for m in home_margins])) if home_margins else 0.5
    away_win_pct = float(np.mean([1.0 if m > 0 else 0.0 for m in away_margins])) if away_margins else 0.5

    h_off = float(target_game["home_off_rtg"])
    h_def = float(target_game["home_def_rtg"])
    a_off = float(target_game["away_off_rtg"])
    a_def = float(target_game["away_def_rtg"])
    h_pace = float(target_game.get("home_pace") or 99.0)
    a_pace = float(target_game.get("away_pace") or 99.0)
    h_rest = float(target_game["home_rest_days"])
    a_rest = float(target_game["away_rest_days"])

    home_net_rtg = h_off - h_def
    away_net_rtg = a_off - a_def
    expected_pace = 0.5 * (h_pace + a_pace)

    return {
        "home_off_rtg": h_off,
        "home_def_rtg": h_def,
        "home_net_rtg": round(home_net_rtg, 4),
        "away_off_rtg": a_off,
        "away_def_rtg": a_def,
        "away_net_rtg": round(away_net_rtg, 4),
        "net_rtg_diff": round(home_net_rtg - away_net_rtg, 4),
        "home_pace": h_pace,
        "away_pace": a_pace,
        "expected_pace": round(expected_pace, 4),
        "home_rest_days": h_rest,
        "away_rest_days": a_rest,
        "rest_diff": round(h_rest - a_rest, 4),
        "home_recent_margin": round(home_recent_net, 4),
        "away_recent_margin": round(away_recent_net, 4),
        "recent_margin_diff": round(home_recent_net - away_recent_net, 4),
        "home_recent_win_pct": round(home_win_pct, 4),
        "away_recent_win_pct": round(away_win_pct, 4),
        "home_court_indicator": 1.0,
    }
