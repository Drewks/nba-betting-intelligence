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
    target_start_str = str(target_game["game_start_time"])
    target_start = parse_iso_utc(target_start_str)
    home_team = target_game["home_team"]
    away_team = target_game["away_team"]

    prior_games = [
        g
        for g in historical_final_games
        if g.get("status") == "FINAL"
        and g.get("home_score") is not None
        and g.get("away_score") is not None
        and (
            str(g.get("game_start_time", "")) < target_start_str
            if len(str(g.get("game_start_time", ""))) == len(target_start_str)
            else parse_iso_utc(g["game_start_time"]) < target_start
        )
    ]

    def _recent_margins_and_totals(team_code: str) -> tuple[list[float], list[float]]:
        margins: list[float] = []
        totals: list[float] = []
        for g in prior_games:
            if g["home_team"] == team_code:
                margins.append(float(g["home_score"] - g["away_score"]))
                totals.append(float(g["home_score"] + g["away_score"]))
            elif g["away_team"] == team_code:
                margins.append(float(g["away_score"] - g["home_score"]))
                totals.append(float(g["home_score"] + g["away_score"]))
        return margins[-rolling_window:], totals[-rolling_window:]

    def _ewma(values: list[float], default: float = 0.0) -> float:
        if not values:
            return default
        weights = np.exp(np.linspace(-1.0, 0.0, len(values)))
        return float(np.average(values, weights=weights))

    home_margins, home_totals = _recent_margins_and_totals(home_team)
    away_margins, away_totals = _recent_margins_and_totals(away_team)

    home_recent_net = _ewma(home_margins, 0.0)
    away_recent_net = _ewma(away_margins, 0.0)
    home_win_pct = _ewma([1.0 if m > 0 else 0.0 for m in home_margins], 0.5)
    away_win_pct = _ewma([1.0 if m > 0 else 0.0 for m in away_margins], 0.5)
    recent_total_trend = 0.5 * (_ewma(home_totals, 228.5) + _ewma(away_totals, 228.5)) - 228.5

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

    # Non-linear Back-to-Back (B2B) fatigue penalty (away B2B is harsher due to travel)
    h_b2b_pen = -1.65 if h_rest <= 1.0 else (0.45 if h_rest >= 3.0 else 0.0)
    a_b2b_pen = -2.25 if a_rest <= 1.0 else (0.35 if a_rest >= 3.0 else 0.0)
    b2b_advantage = h_b2b_pen - a_b2b_pen

    # Direct offensive vs opposing defensive mismatch
    matchup_mismatch = (h_off - a_def) - (a_off - h_def)

    return {
        "home_off_rtg": h_off,
        "home_def_rtg": h_def,
        "home_net_rtg": round(home_net_rtg, 4),
        "away_off_rtg": a_off,
        "away_def_rtg": a_def,
        "away_net_rtg": round(away_net_rtg, 4),
        "net_rtg_diff": round(home_net_rtg - away_net_rtg, 4),
        "matchup_mismatch": round(matchup_mismatch, 4),
        "home_pace": h_pace,
        "away_pace": a_pace,
        "expected_pace": round(expected_pace, 4),
        "pace_clash": round(abs(h_pace - a_pace), 4),
        "home_rest_days": h_rest,
        "away_rest_days": a_rest,
        "rest_diff": round(h_rest - a_rest, 4),
        "b2b_advantage": round(b2b_advantage, 4),
        "home_recent_margin": round(home_recent_net, 4),
        "away_recent_margin": round(away_recent_net, 4),
        "recent_margin_diff": round(home_recent_net - away_recent_net, 4),
        "recent_total_trend": round(recent_total_trend, 4),
        "home_recent_win_pct": round(home_win_pct, 4),
        "away_recent_win_pct": round(away_win_pct, 4),
        "home_court_indicator": 1.0,
    }
