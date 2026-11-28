"""Tests for TheOddsAPI quota minimization (TTL cache, config regions/markets, and smart call skipping)."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.agents.specialized_agents import NBADataScoutAgent
from src.config import ConfigError, load_config, parse_config
from src.ingestion.espn import ESPNPublicAdapter
from src.ingestion.the_odds_api import TheOddsAPIAdapter
from src.storage.db import DatabaseManager
from tests.helpers import PROJECT_ROOT


def test_the_odds_api_config_validation() -> None:
    cfg = load_config()
    assert cfg.sources.the_odds_api_regions == "eu"
    assert cfg.sources.the_odds_api_markets == "h2h,totals"
    assert cfg.sources.the_odds_api_cache_ttl_seconds == 300

    base_raw = yaml.safe_load((PROJECT_ROOT / "config" / "model_config.yaml").read_text(encoding="utf-8"))

    bad_region = yaml.safe_load(yaml.safe_dump(base_raw))
    bad_region["sources"]["the_odds_api_regions"] = "eu,mars"
    with pytest.raises(ConfigError):
        parse_config(bad_region)

    bad_market = yaml.safe_load(yaml.safe_dump(base_raw))
    bad_market["sources"]["the_odds_api_markets"] = "h2h,player_props"
    with pytest.raises(ConfigError):
        parse_config(bad_market)

    bad_ttl = yaml.safe_load(yaml.safe_dump(base_raw))
    bad_ttl["sources"]["the_odds_api_cache_ttl_seconds"] = 99999
    with pytest.raises(ConfigError):
        parse_config(bad_ttl)


def test_the_odds_api_ttl_cache_deduplicates_multi_date_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    TheOddsAPIAdapter.reset_circuit_breaker()
    try:
        urls_called: list[str] = []
        payload = [
            {
                "home_team": "Boston Celtics",
                "away_team": "Miami Heat",
                "commence_time": "2026-11-24T23:30:00Z",
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "title": "Pinnacle",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Boston Celtics", "price": 1.65},
                                    {"name": "Miami Heat", "price": 2.35},
                                ],
                            },
                            {
                                "key": "totals",
                                "outcomes": [
                                    {"name": "Over", "point": 222.5, "price": 1.92},
                                    {"name": "Under", "point": 222.5, "price": 1.94},
                                ],
                            },
                        ],
                    }
                ],
            }
        ]

        class _FakeResp:
            headers = {"x-requests-used": "2", "x-requests-remaining": "482"}

            def read(self) -> bytes:
                return json.dumps(payload).encode("utf-8")

            def __enter__(self) -> _FakeResp:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        def fake_urlopen(req: Any, timeout: int = 10) -> _FakeResp:
            _ = timeout
            url = req.full_url if hasattr(req, "full_url") else str(req)
            urls_called.append(url)
            return _FakeResp()

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        a1 = TheOddsAPIAdapter(api_key="QUOTA_TEST_KEY_123456")
        a2 = TheOddsAPIAdapter(api_key="QUOTA_TEST_KEY_123456")

        res1 = a1.fetch_multi_book_odds_by_matchup("2026-11-24T15:00:00Z")
        res2 = a1.fetch_multi_book_odds_by_matchup("2026-11-24T15:00:10Z")
        res3 = a2.fetch_multi_book_odds_by_matchup("2026-11-24T15:00:20Z")
        res4 = a2.fetch_multi_book_odds_by_matchup("2026-11-24T15:00:30Z")

        assert len(urls_called) == 1
        assert "regions=eu&markets=h2h,totals" in urls_called[0]
        assert ("2026-11-24", "MIA", "BOS") in res1
        assert res2[("2026-11-24", "MIA", "BOS")][0]["captured_at"] == "2026-11-24T15:00:00Z"
        assert res3 == res4

        # Mutating returned caller structures must not corrupt the cached copy
        res1[("2026-11-24", "MIA", "BOS")][0]["decimal_odds"] = 999.0
        res_clean = a1.fetch_multi_book_odds_by_matchup("2026-11-24T15:00:40Z")
        assert res_clean[("2026-11-24", "MIA", "BOS")][0]["decimal_odds"] != 999.0

        # Clearing cache allows fresh fetch
        TheOddsAPIAdapter.clear_cache()
        a1.fetch_multi_book_odds_by_matchup("2026-11-24T15:05:01Z")
        assert len(urls_called) == 2
    finally:
        TheOddsAPIAdapter.reset_circuit_breaker()


def test_espn_adapter_skips_the_odds_api_for_completed_past_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    past_payload = {
        "season": {"year": 2027},
        "events": [
            {
                "id": "401910001",
                "date": "2026-11-22T01:00Z",
                "competitions": [
                    {
                        "status": {"type": {"state": "post", "completed": True}},
                        "competitors": [
                            {"homeAway": "home", "team": {"abbreviation": "BOS"}, "score": "110"},
                            {"homeAway": "away", "team": {"abbreviation": "MIA"}, "score": "102"},
                        ],
                    }
                ],
            }
        ],
    }
    pre_payload = {
        "season": {"year": 2027},
        "events": [
            {
                "id": "401910099",
                "date": "2026-11-25T01:00Z",
                "competitions": [
                    {
                        "status": {"type": {"state": "pre", "completed": False}},
                        "competitors": [
                            {"homeAway": "home", "team": {"abbreviation": "BOS"}},
                            {"homeAway": "away", "team": {"abbreviation": "MIA"}},
                        ],
                    }
                ],
            }
        ],
    }
    current_payload: dict[str, Any] = past_payload

    class _FakeESPNResp:
        def __init__(self, data: dict[str, Any]) -> None:
            self._data = json.dumps(data).encode("utf-8")

        def read(self) -> bytes:
            return self._data

        def __enter__(self) -> _FakeESPNResp:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_kw: _FakeESPNResp(current_payload))
    monkeypatch.setattr(
        "src.ingestion.espn.SportradarAdapter.fetch_league_intelligence_context",
        lambda _self: {"injury_penalties": {}, "team_splits": {}},
    )

    odds_calls = 0
    adapter = ESPNPublicAdapter(enrich_with_the_odds_api=True)
    adapter.odds_api_helper = TheOddsAPIAdapter(api_key="DUMMY_ACTIVE_KEY_789")

    def fake_multi_book(_now_utc: str) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
        nonlocal odds_calls
        odds_calls += 1
        return {}

    monkeypatch.setattr(adapter.odds_api_helper, "fetch_multi_book_odds_by_matchup", fake_multi_book)

    adapter.fetch_games_and_odds(date_str="2026-11-22", as_of_utc="2026-11-23T15:00:00Z")
    assert odds_calls == 0

    current_payload = pre_payload
    adapter.fetch_games_and_odds(date_str="2026-11-24", as_of_utc="2026-11-23T15:00:00Z")
    assert odds_calls == 1


def test_settlement_and_scout_probe_disable_the_odds_api_enrichment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle_src = (PROJECT_ROOT / "scripts" / "run_cloud_cycle.py").read_text(encoding="utf-8")
    assert 'enrich_with_the_odds_api=(mode != "settle_and_calibrate")' in cycle_src

    init_kwargs: list[dict[str, Any]] = []

    class _FakeESPNAdapter:
        def __init__(self, **kwargs: Any) -> None:
            init_kwargs.append(kwargs)

        def fetch_games_and_odds(self) -> dict[str, list[Any]]:
            return {"games": [], "odds": []}

    class _FakeInjFeed:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def fetch_latest_report(self) -> dict[str, Any]:
            return {"fetch_ok": False, "player_count": 0}

    monkeypatch.setattr("src.agents.specialized_agents.ESPNPublicAdapter", _FakeESPNAdapter)
    monkeypatch.setattr("src.ingestion.nba_injury_report.NBAOfficialInjuryFeed", _FakeInjFeed)
    monkeypatch.setenv("SPORTRADAR_API_KEY", "")
    monkeypatch.setattr("src.agents.specialized_agents.PlaywrightAuthorizedScraper.inspect_status", lambda _s: {"status": "OK"})

    db = DatabaseManager(tmp_path / "scout_probe.sqlite3")
    scout = NBADataScoutAgent(db)
    scout.investigate_sources()
    assert len(init_kwargs) == 1
    assert init_kwargs[0]["enrich_with_the_odds_api"] is False
