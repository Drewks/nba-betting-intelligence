"""
Regression tests for the open Codex review findings closed in Fase 0 (auditoria_2026-11-24.md):

- PR #49: settled bets without a measurable CLV must not consume the CLV governor's lookback window.
- PR #50: wall-clock Sportradar standings/injuries are never applied to started games or historical replays.
- PR #52: a TheOddsAPI TTL-cache hit is re-filtered against the caller's clock and keeps the capture time of
  the HTTP fetch that observed it (never re-stamped as a newer price).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any
import urllib.request

import pytest

from src.agents.specialized_agents import NBADataScoutAgent
from src.config import load_config
from src.evaluation.clv import get_recent_clv_governor_factor
from src.ingestion.adapters import DataSourceRouter
from src.ingestion.the_odds_api import TheOddsAPIAdapter
from src.storage.db import DatabaseManager
from src.validation.validator import TemporalLeakageError, validate_odds_fetch_provenance
from tests.helpers import _seed_sample_game_and_prediction
from tests.test_temporal_integrity_ingestion import LIVE_BOX, _espn_adapter, _event, _scoreboard


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


NOW = datetime.now(timezone.utc).replace(microsecond=0)


# --------------------------------------------------------------------------------------------------------------
# PR #49 — CLV governor lookback
# --------------------------------------------------------------------------------------------------------------
def _seed_settled_bet(db: DatabaseManager, idx: int, *, with_close: bool) -> None:
    game_id = f"G_CLV_LOOKBACK_{idx:02d}"
    pred_id = _seed_sample_game_and_prediction(db, game_id)
    settled_at = _iso(datetime(2026, 10, 21, tzinfo=timezone.utc) + timedelta(hours=idx))
    db.execute_insert(
        """
        INSERT INTO simulated_bets (
            bet_id, prediction_id, game_id, matchday_date, market, selection,
            line_value, decimal_odds, estimated_prob, estimated_ev, stake_pen, status, net_profit_pen,
            emitted_at, settled_at, model_version_id
        ) VALUES (?, ?, ?, '2026-10-20', 'moneyline', 'HOME', NULL, 1.95, 0.55, 0.07, 2.00, 'WON', 1.90,
                  '2026-10-20T20:00:00Z', ?, 'model_c_test_v1')
        """,
        (f"BET_CLV_LOOKBACK_{idx:02d}", pred_id, game_id, settled_at),
    )
    if with_close:
        db.execute_insert(
            """
            INSERT INTO odds_snapshots (
                odds_id, game_id, provider, market, selection, line_value, decimal_odds,
                counterpart_decimal_odds, captured_at, is_closing_line, source_type
            ) VALUES (?, ?, 'Pinnacle', 'moneyline', 'HOME', NULL, 1.80, 2.10, '2026-10-20T22:55:00Z', 1, 'OBSERVED')
            """,
            (f"CLOSE_CLV_LOOKBACK_{idx:02d}", game_id),
        )


def test_clv_governor_lookback_skips_settled_bets_without_a_measurable_close(tmp_path: Path) -> None:
    """The 4 newest settled bets have no closing line; the 4 older ones do. The governor must still see 4 CLVs."""
    db = DatabaseManager(tmp_path / "clv_lookback.sqlite3")
    for idx in range(4):
        _seed_settled_bet(db, idx, with_close=True)  # oldest settlements, measurable CLV
    for idx in range(4, 8):
        _seed_settled_bet(db, idx, with_close=False)  # newest settlements, no closing line captured

    factor, mean_clv = get_recent_clv_governor_factor(db, None, scope_predicate_sql="1 = 1", lookback=4)
    assert mean_clv is not None, "bets without a close consumed the lookback and starved the governor"
    assert mean_clv > 0.0
    assert factor in (1.0, 1.10)

    # The window still stops at `lookback` measurable bets (the newest ones that have a close).
    _, mean_two = get_recent_clv_governor_factor(db, None, scope_predicate_sql="1 = 1", lookback=2)
    assert mean_two is None  # 2 measurable CLVs are below the default min_sample (4)


# --------------------------------------------------------------------------------------------------------------
# PR #50 — Sportradar wall-clock context
# --------------------------------------------------------------------------------------------------------------
_SR_SPLIT = {"home_win_pct": 0.9, "road_win_pct": 0.9, "last_10_win_pct": 0.9, "points_for": 125.0, "points_against": 100.0}
_SR_CONTEXT = {
    "injury_penalties": {"NYK": 0.08, "BOS": 0.08, "LAL": 0.05, "GSW": 0.05},
    "team_splits": {code: dict(_SR_SPLIT) for code in ("NYK", "BOS", "LAL", "GSW")},
}


def _spy_adapter(monkeypatch: pytest.MonkeyPatch, state: dict[str, Any]) -> tuple[Any, list[int], list[dict[str, Any]]]:
    adapter = _espn_adapter(monkeypatch, state)
    sr_calls: list[int] = []

    def _fake_sr(_self: Any) -> dict[str, Any]:
        sr_calls.append(1)
        return _SR_CONTEXT

    monkeypatch.setattr("src.ingestion.espn.SportradarAdapter.fetch_league_intelligence_context", _fake_sr)
    profiles: list[dict[str, Any]] = []
    real_profile = adapter._estimate_pregame_team_profile

    def _spy_profile(team_code: str, *args: Any, **kwargs: Any) -> Any:
        profiles.append({"team": team_code, "sr_split": kwargs.get("sr_split"), "injury": kwargs.get("injury_penalty")})
        return real_profile(team_code, *args, **kwargs)

    monkeypatch.setattr(adapter, "_estimate_pregame_team_profile", _spy_profile)
    return adapter, sr_calls, profiles


def test_sportradar_context_only_reaches_games_that_have_not_started(monkeypatch: pytest.MonkeyPatch) -> None:
    final_ev = _event("401950001", "STATUS_FINAL", "post", NOW - timedelta(days=1), scores=(110, 101))
    sched_ev = _event("401950002", "STATUS_SCHEDULED", "pre", NOW + timedelta(hours=5), home="LAL", away="GSW")
    state: dict[str, Any] = {"payload": _scoreboard(final_ev, sched_ev), "box": {}}
    adapter, sr_calls, profiles = _spy_adapter(monkeypatch, state)

    adapter.fetch_games_and_odds()
    assert len(sr_calls) == 1
    by_team = {p["team"]: p for p in profiles}
    for started in ("NYK", "BOS"):  # yesterday's FINAL game: today's standings/injuries are not its context
        assert by_team[started]["sr_split"] is None
        assert by_team[started]["injury"] == 0.0
    for upcoming in ("LAL", "GSW"):
        assert by_team[upcoming]["sr_split"] == _SR_SPLIT
        assert by_team[upcoming]["injury"] == pytest.approx(0.05)

    # A historical replay never receives wall-clock context, not even for its scheduled game.
    profiles.clear()
    adapter.fetch_games_and_odds(as_of_utc=_iso(NOW))
    assert len(sr_calls) == 1
    assert profiles and all(p["sr_split"] is None and p["injury"] == 0.0 for p in profiles)


def test_sportradar_is_not_called_for_a_slate_with_no_upcoming_game(monkeypatch: pytest.MonkeyPatch) -> None:
    final_ev = _event("401950003", "STATUS_FINAL", "post", NOW - timedelta(days=1), scores=(99, 104))
    adapter, sr_calls, profiles = _spy_adapter(monkeypatch, {"payload": _scoreboard(final_ev), "box": {}})
    adapter.fetch_games_and_odds()
    assert sr_calls == []
    assert profiles and all(p["sr_split"] is None for p in profiles)


# --------------------------------------------------------------------------------------------------------------
# PR #52 — TheOddsAPI TTL cache
# --------------------------------------------------------------------------------------------------------------
def _odds_api_payload(commence: str) -> list[dict[str, Any]]:
    return [
        {
            "home_team": "Boston Celtics",
            "away_team": "Miami Heat",
            "commence_time": commence,
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "title": "Pinnacle",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [{"name": "Boston Celtics", "price": 1.65}, {"name": "Miami Heat", "price": 2.35}],
                        }
                    ],
                }
            ],
        }
    ]


def test_ttl_cache_hit_drops_started_events_and_keeps_the_fetch_capture_time(monkeypatch: pytest.MonkeyPatch) -> None:
    TheOddsAPIAdapter.reset_circuit_breaker()
    try:
        calls: list[str] = []
        payload = _odds_api_payload("2026-11-24T15:05:00Z")

        class _Resp:
            headers = {"x-requests-used": "1", "x-requests-remaining": "400"}

            def read(self) -> bytes:
                return json.dumps(payload).encode("utf-8")

            def __enter__(self) -> _Resp:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        def _urlopen(req: Any, timeout: int = 10) -> _Resp:
            calls.append(str(getattr(req, "full_url", req)))
            return _Resp()

        monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
        adapter = TheOddsAPIAdapter(api_key="CACHE_REFILTER_KEY_123456")
        key = ("2026-11-24", "MIA", "BOS")

        fresh = adapter.fetch_multi_book_odds_by_matchup("2026-11-24T15:00:00Z")
        assert fresh[key][0]["captured_at"] == "2026-11-24T15:00:00Z"
        assert not fresh[key][0].get("from_ttl_cache")

        cached = adapter.fetch_multi_book_odds_by_matchup("2026-11-24T15:02:00Z")
        assert len(calls) == 1
        assert all(q["captured_at"] == "2026-11-24T15:00:00Z" and q["from_ttl_cache"] for q in cached[key])

        # Tip-off (15:05) passed since the fetch: the cached event is gone, as a fresh fetch would drop it.
        assert adapter.fetch_multi_book_odds_by_matchup("2026-11-24T15:06:00Z") == {}
        assert len(calls) == 1
    finally:
        TheOddsAPIAdapter.reset_circuit_breaker()


def test_provenance_accepts_a_cached_quote_only_within_the_cache_ttl() -> None:
    started = datetime(2026, 11, 24, 15, 10, tzinfo=timezone.utc)
    ttl = float(load_config().sources.the_odds_api_cache_ttl_seconds)

    def _quote(fetched: datetime, *, cached: bool, captured: datetime | None = None) -> dict[str, Any]:
        q: dict[str, Any] = {"odds_id": "Q1", "fetched_at": _iso(fetched), "captured_at": _iso(captured or fetched)}
        if cached:
            q["from_ttl_cache"] = True
        return q

    within = started - timedelta(seconds=ttl - 60)
    validate_odds_fetch_provenance(_quote(within, cached=True), _iso(started), max_cache_age_seconds=ttl)
    with pytest.raises(TemporalLeakageError):  # older than the cache can hold
        validate_odds_fetch_provenance(
            _quote(started - timedelta(seconds=ttl + 60), cached=True), _iso(started), max_cache_age_seconds=ttl
        )
    with pytest.raises(TemporalLeakageError):  # not declared as a cache hit
        validate_odds_fetch_provenance(_quote(within, cached=False), _iso(started), max_cache_age_seconds=ttl)
    with pytest.raises(TemporalLeakageError):  # a cached quote must be stamped at its own fetch
        validate_odds_fetch_provenance(
            _quote(within, cached=True, captured=within + timedelta(seconds=30)), _iso(started), max_cache_age_seconds=ttl
        )
    with pytest.raises(TemporalLeakageError, match="BACKDATED_CAPTURE"):  # never captured before it was fetched
        validate_odds_fetch_provenance(
            _quote(started, cached=True, captured=started - timedelta(seconds=30)), _iso(started), max_cache_age_seconds=ttl
        )


def test_cached_quotes_are_stored_with_their_original_fetch_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end: a cached quote reaches odds_snapshots stamped at its HTTP fetch, not at the later ingestion."""
    tip = NOW + timedelta(hours=4)
    cached_at = _iso(NOW - timedelta(seconds=60))
    key = (_iso(tip)[:10], "BOS", "NYK")
    base = {"provider": "Pinnacle (LineShop)", "market": "moneyline", "line_value": None, "commence_time": _iso(tip)}
    multi_book = {
        key: [
            {**base, "selection": "HOME", "decimal_odds": 1.80, "counterpart_decimal_odds": 2.10,
             "captured_at": cached_at, "source_type": "OBSERVED", "from_ttl_cache": True},
            {**base, "selection": "AWAY", "decimal_odds": 2.10, "counterpart_decimal_odds": 1.80,
             "captured_at": cached_at, "source_type": "OBSERVED", "from_ttl_cache": True},
        ]
    }
    state: dict[str, Any] = {"payload": _scoreboard(_event("401950010", "STATUS_SCHEDULED", "pre", tip)), "box": LIVE_BOX}
    adapter = _espn_adapter(monkeypatch, state, multi_book=multi_book)

    raw = adapter.fetch_games_and_odds()
    assert len(raw["odds"]) == 2
    assert all(o["captured_at"] == o["fetched_at"] == cached_at and o["from_ttl_cache"] for o in raw["odds"])

    db = DatabaseManager(tmp_path / "cached_quotes.sqlite3")
    res = NBADataScoutAgent(db).ingest_and_validate_dataset(DataSourceRouter([adapter]))
    assert res["rejected_odds"] == []
    stored = db.fetch_all("SELECT captured_at, fetched_at FROM odds_snapshots ORDER BY selection")
    assert [(r["captured_at"], r["fetched_at"]) for r in stored] == [(cached_at, cached_at)] * 2
