"""Regression tests for P0 operational fixes, config centralization, and state-live hygiene."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import Message
import io
import json
import logging
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

import pytest
import yaml

from src.config import ConfigError, ExecutionConfig, load_config, parse_config
from src.ingestion.boxscores import backfill_boxscores
from src.ingestion.sportradar import (
    SportradarAdapter,
    _extract_record_splits,
    resolve_nba_season_year,
)
from src.ingestion.the_odds_api import TheOddsAPIAdapter
from src.paper_trading.execution_helpers import check_candidate_edge_and_model_guards
from src.reporting.notifier import _send_daily_pick_email
from src.storage.db import DatabaseManager
from tests.helpers import PROJECT_ROOT


def test_the_odds_api_401_circuit_breaker_and_quota_exhaustion(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    TheOddsAPIAdapter.reset_circuit_breaker()
    try:
        adapter = TheOddsAPIAdapter(api_key="KEY_401_BREAKER_SECRET_TEST")
        calls = 0

        def raise_401(*_args: object, **_kwargs: object) -> object:
            nonlocal calls
            calls += 1
            raise urllib.error.HTTPError(
                url="https://api.the-odds-api.com/v4/sports/basketball_nba/odds/?apiKey=KEY_401_BREAKER_SECRET_TEST",
                code=401,
                msg="Unauthorized",
                hdrs=Message(),
                fp=io.BytesIO(b"{}"),
            )

        monkeypatch.setattr(urllib.request, "urlopen", raise_401)
        with caplog.at_level(logging.WARNING, logger="src.ingestion.the_odds_api"):
            assert adapter.fetch_multi_book_odds_by_matchup("2026-11-23T00:00:00Z") == {}
            assert adapter.fetch_multi_book_odds_by_matchup("2026-11-23T00:00:00Z") == {}

        assert calls == 1
        assert "TheOddsAPI request failed" in caplog.text
        assert "circuit breaker tripped" in caplog.text
        assert "KEY_401_BREAKER_SECRET_TEST" not in caplog.text

        # Reset and verify header x-requests-remaining=0 also trips the circuit breaker after logging quota
        TheOddsAPIAdapter.reset_circuit_breaker()
        quota_calls = 0

        class _FakeResp:
            headers = {"x-requests-remaining": "0", "x-requests-used": "500"}

            def read(self) -> bytes:
                return b"[]"

            def __enter__(self) -> _FakeResp:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        def return_zero_quota(*_args: object, **_kwargs: object) -> _FakeResp:
            nonlocal quota_calls
            quota_calls += 1
            return _FakeResp()

        monkeypatch.setattr(urllib.request, "urlopen", return_zero_quota)
        assert adapter.fetch_multi_book_odds_by_matchup("2026-11-23T00:00:00Z") == {}
        assert adapter.fetch_multi_book_odds_by_matchup("2026-11-23T00:00:00Z") == {}
        assert quota_calls == 1
        assert TheOddsAPIAdapter._LAST_REMAINING_REQUESTS == 0
    finally:
        TheOddsAPIAdapter.reset_circuit_breaker()


def test_sportradar_dynamic_season_and_list_records_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert resolve_nba_season_year(datetime(2026, 11, 23, tzinfo=timezone.utc)) == 2026
    assert resolve_nba_season_year(datetime(2027, 2, 10, tzinfo=timezone.utc)) == 2026
    assert resolve_nba_season_year(datetime(2026, 9, 15, tzinfo=timezone.utc)) == 2025

    list_splits = _extract_record_splits(
        [
            {"record_type": "home", "wins": 10, "losses": 2},
            {"record_type": "road", "wins": 6, "losses": 6},
            {"record_type": "last_10", "wins": 8, "losses": 2},
        ]
    )
    assert list_splits == {"home": (10, 2), "road": (6, 6), "last_10": (8, 2)}

    dict_splits = _extract_record_splits(
        {
            "home": {"wins": 9, "losses": 3},
            "away": {"wins": 5, "losses": 7},
            "last10": {"wins": 7, "losses": 3},
        }
    )
    assert dict_splits == {"home": (9, 3), "road": (5, 7), "last_10": (7, 3)}

    prev_cache = SportradarAdapter._CACHED_CONTEXT
    SportradarAdapter._CACHED_CONTEXT = None
    requested_urls: list[str] = []
    try:
        class _FakeHTTPResp:
            def __init__(self, payload: dict[str, Any]) -> None:
                self._payload = json.dumps(payload).encode("utf-8")

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> _FakeHTTPResp:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        def fake_urlopen(req: Any, timeout: int = 10) -> _FakeHTTPResp:
            _ = timeout
            url = req.full_url if hasattr(req, "full_url") else str(req)
            requested_urls.append(url)
            if "injuries.json" in url:
                return _FakeHTTPResp(
                    {
                        "teams": [
                            {
                                "alias": "BOS",
                                "players": [
                                    {
                                        "full_name": "Jayson Tatum",
                                        "primary_position": "SF",
                                        "injuries": [{"status": "Questionable", "desc": "Ankle"}],
                                    }
                                ],
                            }
                        ]
                    }
                )
            if "standings.json" in url:
                return _FakeHTTPResp(
                    {
                        "conferences": [
                            {
                                "divisions": [
                                    {
                                        "teams": [
                                            {
                                                "alias": "BOS",
                                                "points_for": 119.2,
                                                "points_against": 108.4,
                                                "records": [
                                                    {"record_type": "home", "wins": 8, "losses": 2},
                                                    {"record_type": "road", "wins": 7, "losses": 3},
                                                    {"record_type": "last_10", "wins": 8, "losses": 2},
                                                ],
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                )
            raise AssertionError(f"Unexpected URL requested: {url}")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        adapter = SportradarAdapter(api_key="S" * 24, synergy_enabled=False, season_year=2026)
        ctx = adapter.fetch_league_intelligence_context()

        assert any("seasons/2026/REG/standings.json" in u for u in requested_urls)
        assert not any("synergy-basketball" in u for u in requested_urls)
        assert ctx["team_splits"]["BOS"]["home_win_pct"] == 0.8
        assert ctx["team_splits"]["BOS"]["road_win_pct"] == 0.7
        assert ctx["team_splits"]["BOS"]["last_10_win_pct"] == 0.8
        assert len(ctx["injury_documents"]) == 1
        assert str(ctx["status"]).startswith("OPERATIONAL_LIVE_NBA_V8 (")
    finally:
        SportradarAdapter._CACHED_CONTEXT = prev_cache


def test_boxscore_backfill_marks_old_404_permanently_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = DatabaseManager(tmp_path / "boxscore_404.sqlite3")
    old_start = "2026-11-01T00:00:00Z"
    fresh_start = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with db.connect() as conn:
        for gid, start, home, away in (
            ("ESPN_900001_2026-11-01_MIA_AT_BOS", old_start, "BOS", "MIA"),
            ("ESPN_900002_2026-11-23_LAL_AT_NYK", fresh_start, "NYK", "LAL"),
        ):
            conn.execute(
                """
                INSERT INTO games (
                    game_id, season, matchday_date, game_start_time, home_team, away_team,
                    status, home_score, away_score, features_available_at, source_provider, ingested_at
                ) VALUES (?, '2026-27', ?, ?, ?, ?, 'FINAL', 110, 104, ?, 'espn', ?)
                """,
                (gid, start[:10], start, home, away, start, now_iso),
            )

    def fail_404(event_id: str, timeout: int = 15) -> dict[str, Any]:
        _ = timeout
        raise urllib.error.HTTPError(
            url=f"https://site.api.espn.com/summary?event={event_id}",
            code=404,
            msg="Not Found",
            hdrs=Message(),
            fp=io.BytesIO(b"{}"),
        )

    monkeypatch.setattr("src.ingestion.boxscores.fetch_boxscore", fail_404)
    r1 = backfill_boxscores(db, workers=1)
    r2 = backfill_boxscores(db, workers=1)
    r3 = backfill_boxscores(db, workers=1)

    assert r1["marked_permanent"] == 0
    assert r2["marked_permanent"] == 0
    assert r3["marked_permanent"] == 1

    old_fail = db.fetch_one("SELECT * FROM boxscore_fetch_failures WHERE game_id = 'ESPN_900001_2026-11-01_MIA_AT_BOS'")
    fresh_fail = db.fetch_one("SELECT * FROM boxscore_fetch_failures WHERE game_id = 'ESPN_900002_2026-11-23_LAL_AT_NYK'")
    assert old_fail["attempts"] == 3 and old_fail["permanently_unavailable"] == 1
    assert fresh_fail["attempts"] == 3 and fresh_fail["permanently_unavailable"] == 0

    def recover_fresh(event_id: str, timeout: int = 15) -> dict[str, Any]:
        _ = timeout
        if event_id == "900001":
            raise AssertionError("Old permanently unavailable game must not be requested again")
        return {
            "teams": {
                "NYK": {"fgm": 40.0, "fga": 82.0, "tpm": 12.0, "tpa": 34.0, "ftm": 18.0, "fta": 22.0, "orb": 9.0, "drb": 34.0, "tov": 11.0, "pts": 110.0},
                "LAL": {"fgm": 38.0, "fga": 84.0, "tpm": 10.0, "tpa": 30.0, "ftm": 18.0, "fta": 24.0, "orb": 8.0, "drb": 31.0, "tov": 13.0, "pts": 104.0},
            },
            "players": {
                "NYK": [{"name": "Jalen Brunson", "min": 36.0, "pts": 30.0, "reb": 4.0, "ast": 8.0, "threed": 3.0, "starter": True}],
                "LAL": [{"name": "LeBron James", "min": 35.0, "pts": 26.0, "reb": 7.0, "ast": 7.0, "threed": 2.0, "starter": True}],
            },
        }

    monkeypatch.setattr("src.ingestion.boxscores.fetch_boxscore", recover_fresh)
    r4 = backfill_boxscores(db, workers=1)
    assert r4["requested"] == 1
    assert r4["stored"] == 1
    assert db.fetch_one("SELECT * FROM boxscore_fetch_failures WHERE game_id = 'ESPN_900002_2026-11-23_LAL_AT_NYK'") is None


def test_execution_guards_loaded_from_config_and_validated() -> None:
    cfg = load_config()
    ex = cfg.execution
    assert ex.max_plausible_ev_unit == 0.45
    assert ex.longshot_odds_threshold == 3.50
    assert ex.longshot_min_ev_pct == 15.0
    assert ex.adverse_steam_threshold == -0.045
    assert ex.max_conformal_width == 0.22

    base_raw = yaml.safe_load((PROJECT_ROOT / "config" / "model_config.yaml").read_text(encoding="utf-8"))
    for bad_key, bad_val in (
        ("max_plausible_ev_unit", 5.0),
        ("longshot_odds_threshold", 1.1),
        ("longshot_min_ev_pct", 150.0),
        ("adverse_steam_threshold", 0.5),
        ("max_conformal_width", 5.0),
    ):
        mut = yaml.safe_load(yaml.safe_dump(base_raw))
        mut["execution"][bad_key] = bad_val
        with pytest.raises(ConfigError):
            parse_config(mut)

    cand = {
        "game_id": "ESPN_123456_2026-11-23_MIA_AT_BOS",
        "market": "moneyline",
        "decimal_odds_used": 2.0,
        "calibrated_probability": 0.55,
        "ev_unit": 0.10,
        "ev_pct": 10.0,
        "conformal_width": 0.15,
    }
    assert check_candidate_edge_and_model_guards(cand, min_ev_threshold=0.02, execution_cfg=ex) is None
    blocked = check_candidate_edge_and_model_guards(
        cand,
        min_ev_threshold=0.02,
        execution_cfg=ExecutionConfig(max_conformal_width=0.10),
    )
    assert blocked is not None and blocked[0] == "CONFORMAL_UNCERTAINTY_TOO_WIDE"


def test_notifier_github_issues_disabled_by_default_and_logs_403_when_enabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("src.reporting.notifier._resolve_github_token", lambda: "ghp_dummy_token")
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    class _ForbiddenClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> _ForbiddenClient:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, *_args: object, **_kwargs: object) -> Any:
            return type("Resp", (), {"status_code": 200, "json": lambda self: [], "text": "[]"})()

        def post(self, *_args: object, **_kwargs: object) -> Any:
            return type("Resp", (), {"status_code": 403, "text": "Resource not accessible by integration"})()

    def fail_if_called(**_kwargs: object) -> object:
        raise AssertionError("httpx.Client must not be called when github_issue_notifications_enabled is False")

    sample_pick = {
        "bet_id": "BET_TEST_1",
        "partido": "MIA @ BOS",
        "mercado": "moneyline",
        "seleccion": "HOME",
        "cuota_decimal": 1.85,
        "casa_apuestas": "Pinnacle",
        "prob_estimada": 58.0,
        "ev_porcentaje": 7.3,
        "hora_partido_peru": "2026-11-23 19:30",
        "stake_pen": 3.50,
    }

    monkeypatch.setattr("src.reporting.notifier.httpx.Client", fail_if_called)
    assert _send_daily_pick_email(sample_pick, "2026-11-23") == []

    monkeypatch.setattr("src.reporting.notifier.httpx.Client", _ForbiddenClient)
    with caplog.at_level(logging.WARNING):
        res = _send_daily_pick_email(sample_pick, "2026-11-23", enable_github_issues=True)
    assert res == []
    assert "403" in caplog.text


def test_workflows_p0_p1_contracts() -> None:
    auto_raw = (PROJECT_ROOT / ".github" / "workflows" / "nba_cloud_automation.yml").read_text(encoding="utf-8")
    auto_wf = yaml.safe_load(auto_raw)
    assert auto_wf["permissions"] == {"contents": "read"}
    assert auto_wf["jobs"]["run-nba-intelligence-cycle"]["permissions"] == {"contents": "write"}
    assert "playwright install chromium" not in auto_raw
    assert "--force-with-lease=" in auto_raw
    assert "git push --force " not in auto_raw
    assert "nba-state-live-db-backup" in auto_raw

    weekly_raw = (PROJECT_ROOT / ".github" / "workflows" / "weekly_backtest.yml").read_text(encoding="utf-8")
    weekly_wf = yaml.safe_load(weekly_raw)
    weekly_triggers = weekly_wf.get("on") or weekly_wf.get(True)
    assert auto_wf["name"] in weekly_triggers["workflow_run"]["workflows"]
    assert "generated_at" in weekly_raw and "should_run" in weekly_raw
    assert "--force-with-lease=" in weekly_raw
    steps = next(iter(weekly_wf["jobs"].values()))["steps"]
    assert all(s.get("if") == "steps.prep.outputs.should_run == 'true'" for s in steps[1:])

    closing_raw = (PROJECT_ROOT / ".github" / "workflows" / "closing_capture.yml").read_text(encoding="utf-8")
    assert yaml.safe_load(closing_raw)["concurrency"]["group"] == "nba-closing-capture"
    assert "--force-with-lease=" in closing_raw
    assert "git push --force " not in closing_raw


def test_cloud_cycle_helpers_modularized_under_limit() -> None:
    import scripts.cloud_cycle_calibration as cal_mod
    import scripts.cloud_cycle_helpers as helpers_mod

    helpers_lines = len((PROJECT_ROOT / "scripts" / "cloud_cycle_helpers.py").read_text(encoding="utf-8").splitlines())
    cal_lines = len((PROJECT_ROOT / "scripts" / "cloud_cycle_calibration.py").read_text(encoding="utf-8").splitlines())
    assert helpers_lines < 750
    assert cal_lines < 750
    assert helpers_mod.build_walk_forward_oos_comparisons_for_active_model is cal_mod.build_walk_forward_oos_comparisons_for_active_model
    assert helpers_mod.fit_and_log_cycle_calibrators is cal_mod.fit_and_log_cycle_calibrators
    assert helpers_mod.compute_totals_line_band_telemetry is cal_mod.compute_totals_line_band_telemetry
    assert helpers_mod._pair_valid_pretip_quotes is cal_mod._pair_valid_pretip_quotes
