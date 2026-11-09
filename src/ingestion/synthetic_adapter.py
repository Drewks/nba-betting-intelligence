"""
Synthetic Fixture Adapter (`src/ingestion/synthetic_adapter.py`).
Generates controlled Monte Carlo synthetic fixtures for offline statistical benchmarking.
Quarantined from real observed production data feeds.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from scipy.stats import norm

from src.ingestion.adapters import BaseNBADataAdapter
from src.utils.team_dictionary import NBA_TEAMS


class SyntheticFixtureAdapter(BaseNBADataAdapter):
    """
    Deterministic multi-period NBA dataset generator for reproducible walk-forward backtesting,
    offline simulation, and unit/integration verification.
    Explicitly models team score correlation via shared game pace so home & away scores are NOT independent.
    """

    provider_name = "synthetic_fixture_verified"

    def __init__(self, seed: int = 42, num_matchdays: int = 45, games_per_day: int = 5) -> None:
        self.seed = seed
        self.num_matchdays = num_matchdays
        self.games_per_day = games_per_day

    def fetch_games_and_odds(
        self,
        date_str: str | None = None,
        as_of_utc: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        rng = np.random.default_rng(self.seed)
        team_codes = sorted(NBA_TEAMS.keys())

        team_latents: dict[str, dict[str, float]] = {}
        for t in team_codes:
            team_latents[t] = {
                "off": float(np.round(rng.normal(114.5, 3.2), 2)),
                "def": float(np.round(rng.normal(114.5, 3.2), 2)),
                "pace": float(np.round(rng.normal(99.2, 2.1), 2)),
            }

        start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        games: list[dict[str, Any]] = []
        odds: list[dict[str, Any]] = []

        for day_idx in range(self.num_matchdays):
            current_dt = start_date + timedelta(days=day_idx)
            matchday_str = current_dt.strftime("%Y-%m-%d")
            if date_str and matchday_str != date_str:
                continue

            season_str = "2025-26" if day_idx < 30 else "2026-27"
            shuffled = list(rng.permutation(team_codes))

            for g_idx in range(self.games_per_day):
                home_team = str(shuffled[2 * g_idx])
                away_team = str(shuffled[2 * g_idx + 1])

                tipoff_dt = current_dt.replace(hour=23, minute=0, second=0)
                avail_dt = tipoff_dt - timedelta(hours=4)
                odds_dt = tipoff_dt - timedelta(hours=3)
                close_dt = tipoff_dt - timedelta(minutes=15)
                settled_dt = tipoff_dt + timedelta(hours=3)

                game_start_str = tipoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                avail_str = avail_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                odds_str = odds_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                is_final = True
                if as_of_utc and game_start_str >= as_of_utc:
                    is_final = False

                h_lat = team_latents[home_team]
                a_lat = team_latents[away_team]

                h_off = round(h_lat["off"] + float(rng.normal(0, 1.1)), 2)
                h_def = round(h_lat["def"] + float(rng.normal(0, 1.1)), 2)
                h_pace = round(h_lat["pace"] + float(rng.normal(0, 0.7)), 2)
                a_off = round(a_lat["off"] + float(rng.normal(0, 1.1)), 2)
                a_def = round(a_lat["def"] + float(rng.normal(0, 1.1)), 2)
                a_pace = round(a_lat["pace"] + float(rng.normal(0, 0.7)), 2)

                h_rest = int(rng.choice([1, 2, 2, 3]))
                a_rest = int(rng.choice([1, 2, 2, 3]))

                expected_pace = 0.5 * (h_pace + a_pace)
                pace_shock = float(rng.normal(0.0, 2.8))
                realized_pace = expected_pace + pace_shock

                expected_h_pts = ((h_off + a_def) / 200.0) * expected_pace + 1.3 + 0.4 * (h_rest - a_rest)
                expected_a_pts = ((a_off + h_def) / 200.0) * expected_pace - 1.3 - 0.4 * (h_rest - a_rest)

                h_pts = int(round(((h_off + a_def) / 200.0) * realized_pace + 1.3 + float(rng.normal(0, 7.8))))
                a_pts = int(round(((a_off + h_def) / 200.0) * realized_pace - 1.3 + float(rng.normal(0, 7.8))))
                if h_pts == a_pts:
                    h_pts += 2

                game_id = f"SYN_{matchday_str.replace('-', '')}_{away_team}_AT_{home_team}"

                games.append(
                    {
                        "game_id": game_id,
                        "season": season_str,
                        "matchday_date": matchday_str,
                        "game_start_time": game_start_str,
                        "home_team": home_team,
                        "away_team": away_team,
                        "status": "FINAL" if is_final else "SCHEDULED",
                        "home_score": h_pts if is_final else None,
                        "away_score": a_pts if is_final else None,
                        "home_off_rtg": h_off,
                        "home_def_rtg": h_def,
                        "home_pace": h_pace,
                        "away_off_rtg": a_off,
                        "away_def_rtg": a_def,
                        "away_pace": a_pace,
                        "home_rest_days": h_rest,
                        "away_rest_days": a_rest,
                        "features_available_at": avail_str,
                        "source_provider": self.provider_name,
                        "ingested_at": avail_str,
                        "result_recorded_at": settled_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if is_final else None,
                    }
                )

                exp_margin = expected_h_pts - expected_a_pts

                true_p_home = float(np.clip(1.0 - norm.cdf(0.0, loc=exp_margin, scale=11.8), 0.08, 0.92))
                market_p_home = float(np.clip(true_p_home + float(rng.normal(0.0, 0.038)), 0.08, 0.92))
                market_p_away = 1.0 - market_p_home

                overround = 1.045
                home_ml_odds = round(max(1.05, 1.0 / (market_p_home * overround)), 3)
                away_ml_odds = round(max(1.05, 1.0 / (market_p_away * overround)), 3)

                close_p_home = float(np.clip(0.75 * true_p_home + 0.25 * market_p_home, 0.08, 0.92))
                close_p_away = 1.0 - close_p_home
                close_home_odds = round(max(1.05, 1.0 / (close_p_home * overround)), 3)
                close_away_odds = round(max(1.05, 1.0 / (close_p_away * overround)), 3)

                odds.extend(
                    [
                        {
                            "odds_id": f"{game_id}_ML_HOME_OPEN",
                            "game_id": game_id,
                            "provider": "SyntheticBook_Authorized",
                            "market": "moneyline",
                            "selection": "HOME",
                            "line_value": None,
                            "decimal_odds": home_ml_odds,
                            "counterpart_decimal_odds": away_ml_odds,
                            "captured_at": odds_str,
                            "is_closing_line": 0,
                            "source_type": "SYNTHETIC",
                        },
                        {
                            "odds_id": f"{game_id}_ML_AWAY_OPEN",
                            "game_id": game_id,
                            "provider": "SyntheticBook_Authorized",
                            "market": "moneyline",
                            "selection": "AWAY",
                            "line_value": None,
                            "decimal_odds": away_ml_odds,
                            "counterpart_decimal_odds": home_ml_odds,
                            "captured_at": odds_str,
                            "is_closing_line": 0,
                            "source_type": "SYNTHETIC",
                        },
                        {
                            "odds_id": f"{game_id}_ML_HOME_CLOSE",
                            "game_id": game_id,
                            "provider": "SyntheticBook_Authorized",
                            "market": "moneyline",
                            "selection": "HOME",
                            "line_value": None,
                            "decimal_odds": close_home_odds,
                            "counterpart_decimal_odds": close_away_odds,
                            "captured_at": close_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "is_closing_line": 1,
                            "source_type": "SYNTHETIC",
                        },
                        {
                            "odds_id": f"{game_id}_ML_AWAY_CLOSE",
                            "game_id": game_id,
                            "provider": "SyntheticBook_Authorized",
                            "market": "moneyline",
                            "selection": "AWAY",
                            "line_value": None,
                            "decimal_odds": close_away_odds,
                            "counterpart_decimal_odds": close_home_odds,
                            "captured_at": close_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "is_closing_line": 1,
                            "source_type": "SYNTHETIC",
                        },
                    ]
                )

                true_total = expected_h_pts + expected_a_pts
                market_line = round((true_total + float(rng.normal(0.0, 2.5))) * 2.0) / 2.0
                p_over_market = float(np.clip(1.0 - norm.cdf(market_line, loc=true_total, scale=15.8) + float(rng.normal(0, 0.035)), 0.15, 0.85))
                p_under_market = 1.0 - p_over_market
                over_odds = round(max(1.05, 1.0 / (p_over_market * overround)), 3)
                under_odds = round(max(1.05, 1.0 / (p_under_market * overround)), 3)

                odds.extend(
                    [
                        {
                            "odds_id": f"{game_id}_TOT_OVER_{market_line}_OPEN",
                            "game_id": game_id,
                            "provider": "SyntheticBook_Authorized",
                            "market": "total_points",
                            "selection": "OVER",
                            "line_value": float(market_line),
                            "decimal_odds": over_odds,
                            "counterpart_decimal_odds": under_odds,
                            "captured_at": odds_str,
                            "is_closing_line": 0,
                            "source_type": "SYNTHETIC",
                        },
                        {
                            "odds_id": f"{game_id}_TOT_UNDER_{market_line}_OPEN",
                            "game_id": game_id,
                            "provider": "SyntheticBook_Authorized",
                            "market": "total_points",
                            "selection": "UNDER",
                            "line_value": float(market_line),
                            "decimal_odds": under_odds,
                            "counterpart_decimal_odds": over_odds,
                            "captured_at": odds_str,
                            "is_closing_line": 0,
                            "source_type": "SYNTHETIC",
                        },
                    ]
                )

        return {"games": games, "odds": odds}
