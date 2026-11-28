from __future__ import annotations

from src.agents.specialized_agents import NBADataScoutAgent
from src.ingestion.base import BaseNBADataAdapter
from src.ingestion.espn import ESPNPublicAdapter
from src.ingestion.router import DataSourceRouter
from src.storage.db import DatabaseManager
from src.validation.validator import parse_iso_utc


class MockESPNPregameAdapter(BaseNBADataAdapter):
    provider_name = "mock_espn_pregame"

    def fetch_games_and_odds(self, date_str: str | None = None, as_of_utc: str | None = None) -> dict:
        return {
            "games": [
                {
                    "game_id": "MOCK_GAME_20261112_BOS_AT_NYK",
                    "season": "2026-27",
                    "matchday_date": "2026-11-12",
                    "game_start_time": "2026-11-12T01:00:00Z",
                    "home_team": "NYK",
                    "away_team": "BOS",
                    "status": "SCHEDULED",
                    "home_score": None,
                    "away_score": None,
                    "home_off_rtg": 115.0,
                    "home_def_rtg": 112.0,
                    "home_pace": 98.5,
                    "away_off_rtg": 118.0,
                    "away_def_rtg": 110.0,
                    "away_pace": 99.0,
                    "home_rest_days": 2,
                    "away_rest_days": 1,
                    "features_available_at": "2026-11-11T23:00:00Z",
                    "source_provider": "mock_espn_pregame",
                    "ingested_at": "2026-11-11T23:30:00Z",
                    "result_recorded_at": None,
                }
            ],
            "odds": [
                {
                    "odds_id": "MOCK_ODDS_BOS_NYK_TOT_220.5_DK",
                    "game_id": "MOCK_GAME_20261112_BOS_AT_NYK",
                    "provider": "DraftKings",
                    "market": "total_points",
                    "selection": "OVER",
                    "line_value": 220.5,
                    "decimal_odds": 1.9091,
                    "counterpart_decimal_odds": 1.9091,
                    "captured_at": "2026-11-11T23:30:00Z",
                    "is_closing_line": 0,
                    "source_type": "OBSERVED",
                },
                {
                    "odds_id": "MOCK_ODDS_BOS_NYK_TOT_220.5_DK_UNDER",
                    "game_id": "MOCK_GAME_20261112_BOS_AT_NYK",
                    "provider": "DraftKings",
                    "market": "total_points",
                    "selection": "UNDER",
                    "line_value": 220.5,
                    "decimal_odds": 1.9091,
                    "counterpart_decimal_odds": 1.9091,
                    "captured_at": "2026-11-11T23:30:00Z",
                    "is_closing_line": 0,
                    "source_type": "OBSERVED",
                },
            ],
        }


def test_espn_adapter_features_available_at_strictly_precedes_game_start(monkeypatch):
    import json
    import urllib.request

    sample_scoreboard = {
        "season": {"year": 2027},
        "events": [
            {
                "id": "401800001",
                "date": "2026-11-12T01:00:00Z",
                "competitions": [
                    {
                        "status": {"type": {"name": "STATUS_SCHEDULED"}},
                        "competitors": [
                            {"homeAway": "home", "team": {"abbreviation": "NYK"}},
                            {"homeAway": "away", "team": {"abbreviation": "BOS"}},
                        ],
                        "odds": [],
                    }
                ],
            }
        ],
    }

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(sample_scoreboard).encode("utf-8")

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: _FakeResp())
    monkeypatch.setattr(
        "src.ingestion.espn.SportradarAdapter.fetch_league_intelligence_context",
        lambda _self: {},
    )
    adapter = ESPNPublicAdapter(timeout_seconds=5, enrich_with_the_odds_api=False)
    monkeypatch.setattr(
        adapter,
        "_fetch_event_summary_context",
        lambda _ev_id: {
            "injury_penalties": {},
            "referee_total_adj": 0.0,
            "referee_hca_adj": 0.0,
            "team_box_stats": {},
            "lineup_synergy_details": {},
        },
    )
    monkeypatch.setattr(adapter, "_compute_team_rest_days", lambda _code, _date: 2)

    res = adapter.fetch_games_and_odds(date_str="2026-11-12", as_of_utc="2026-11-11T23:00:00Z")
    assert len(res["games"]) == 1
    game = res["games"][0]
    assert parse_iso_utc(game["features_available_at"]) < parse_iso_utc(game["game_start_time"])


def test_scout_ingests_upcoming_games_and_odds_without_rejection(tmp_path):
    test_db = tmp_path / "test_nba.sqlite3"
    db = DatabaseManager(test_db)
    scout = NBADataScoutAgent(db)
    router = DataSourceRouter([MockESPNPregameAdapter()])

    res = scout.ingest_and_validate_dataset(router, date_str="2026-11-12")
    assert len(res["validated_games"]) == 1
    assert len(res["discarded_games"]) == 0
    assert len(res["validated_odds"]) == 2
    assert len(res["rejected_odds"]) == 0

    # Ensure odds exist in DB
    rows = db.fetch_all("SELECT * FROM v_observed_odds_snapshots WHERE game_id = 'MOCK_GAME_20261112_BOS_AT_NYK'")
    assert len(rows) == 2


def test_scout_resolves_odds_for_preexisting_game_in_db(tmp_path):
    test_db = tmp_path / "test_preexisting.sqlite3"
    db = DatabaseManager(test_db)
    scout = NBADataScoutAgent(db)

    # First ingest only the game
    class GameOnlyAdapter(BaseNBADataAdapter):
        provider_name = "game_only"
        def fetch_games_and_odds(self, date_str=None, as_of_utc=None):
            return {
                "games": [
                    {
                        "game_id": "PREEXISTING_GAME_1",
                        "season": "2026-27",
                        "matchday_date": "2026-11-12",
                        "game_start_time": "2026-11-12T02:00:00Z",
                        "home_team": "LAL",
                        "away_team": "GSW",
                        "status": "SCHEDULED",
                        "home_off_rtg": 114.0,
                        "home_def_rtg": 113.0,
                        "home_pace": 100.0,
                        "away_off_rtg": 116.0,
                        "away_def_rtg": 112.0,
                        "away_pace": 101.0,
                        "home_rest_days": 1,
                        "away_rest_days": 2,
                        "features_available_at": "2026-11-11T20:00:00Z",
                        "source_provider": "game_only",
                        "ingested_at": "2026-11-11T20:30:00Z",
                    }
                ],
                "odds": [],
            }

    scout.ingest_and_validate_dataset(DataSourceRouter([GameOnlyAdapter()]))

    # Now ingest subsequent odds in a separate call where game is already known in DB
    class SubsequentOddsAdapter(BaseNBADataAdapter):
        provider_name = "subsequent_odds"
        def fetch_games_and_odds(self, date_str=None, as_of_utc=None):
            return {
                "games": [
                    {
                        "game_id": "PREEXISTING_GAME_1",
                        "season": "2026-27",
                        "matchday_date": "2026-11-12",
                        "game_start_time": "2026-11-12T02:00:00Z",
                        "home_team": "LAL",
                        "away_team": "GSW",
                        "status": "SCHEDULED",
                        "home_off_rtg": 114.0,
                        "home_def_rtg": 113.0,
                        "home_pace": 100.0,
                        "away_off_rtg": 116.0,
                        "away_def_rtg": 112.0,
                        "away_pace": 101.0,
                        "home_rest_days": 1,
                        "away_rest_days": 2,
                        "features_available_at": "2026-11-11T20:00:00Z",
                        "source_provider": "game_only",
                        "ingested_at": "2026-11-11T20:30:00Z",
                    }
                ],
                "odds": [
                    {
                        "odds_id": "ODDS_FOR_PREEXISTING",
                        "game_id": "PREEXISTING_GAME_1",
                        "provider": "DraftKings",
                        "market": "moneyline",
                        "selection": "HOME",
                        "line_value": None,
                        "decimal_odds": 1.85,
                        "counterpart_decimal_odds": 2.05,
                        "captured_at": "2026-11-11T21:00:00Z",
                        "is_closing_line": 0,
                        "source_type": "OBSERVED",
                    }
                ],
            }

    res2 = scout.ingest_and_validate_dataset(DataSourceRouter([SubsequentOddsAdapter()]))
    assert len(res2["validated_odds"]) == 1
    assert len(res2["rejected_odds"]) == 0
    in_db = db.fetch_all("SELECT * FROM odds_snapshots WHERE odds_id = 'ODDS_FOR_PREEXISTING'")
    assert len(in_db) == 1
