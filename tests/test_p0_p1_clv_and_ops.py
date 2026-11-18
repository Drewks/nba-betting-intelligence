"""Regression tests for P0 (line-movement CLV & evidence_staking filter) and P1 (prop bloat, cron lag, PDF suffix)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.evaluation.clv import compute_bet_clv, index_closing_rows
from src.ingestion.closing_capture import capture_closing_window
from src.ingestion.nba_injury_report import parse_nba_injury_pdf_bytes
from src.paper_trading.engine import build_production_engine
from src.paper_trading.settlement import persist_closing_lines_for_games
from src.paper_trading.shadow_ledger import clv_evidence_by_market, summarize_shadow_ledger
from src.storage.db import DatabaseManager
from tests.helpers import PROJECT_ROOT


def test_clv_line_movement_totals_and_spread() -> None:
    """When a total or spread moves before tip-off, CLV uses the latest close adjusted for line delta."""
    closes = [
        # Stale earlier close at the old 234.5 number (mimics legacy DB rows before settlement fix)
        {
            "game_id": "G_TOT",
            "market": "total_points",
            "selection": "UNDER",
            "line_value": 234.5,
            "decimal_odds": 1.9259,
            "counterpart_decimal_odds": 1.9434,
            "provider": "Pinnacle [LIVE_API]",
            "captured_at": "2026-11-15T07:12:13Z",
        },
        # True latest closing line moved 1.0 pt down to 233.5 (favorable for UNDER 234.5!)
        {
            "game_id": "G_TOT",
            "market": "total_points",
            "selection": "UNDER",
            "line_value": 233.5,
            "decimal_odds": 1.9091,
            "counterpart_decimal_odds": 1.9804,
            "provider": "Pinnacle [LIVE_API]",
            "captured_at": "2026-11-15T20:23:49Z",
        },
        # Adverse move for UNDER 224.5: closes up at 226.0
        {
            "game_id": "G_TOT_ADV",
            "market": "total_points",
            "selection": "UNDER",
            "line_value": 226.0,
            "decimal_odds": 1.96,
            "counterpart_decimal_odds": 1.90,
            "provider": "Pinnacle [LIVE_API]",
            "captured_at": "2026-11-15T20:23:49Z",
        },
        # Favorable spread move: bet HOME -4.5, closes at HOME -6.0 (+1.5 pts)
        {
            "game_id": "G_SPR",
            "market": "spread",
            "selection": "HOME",
            "line_value": -6.0,
            "decimal_odds": 1.92,
            "counterpart_decimal_odds": 1.96,
            "provider": "Pinnacle [LIVE_API]",
            "captured_at": "2026-11-15T20:23:49Z",
        },
    ]
    idx = index_closing_rows(closes)

    rec_fav = compute_bet_clv(
        {"bet_id": "b1", "game_id": "G_TOT", "market": "total_points", "selection": "UNDER", "line_value": 234.5, "decimal_odds": 1.9259},
        idx,
        "Pinnacle [LIVE_API]",
    )
    assert rec_fav is not None
    assert rec_fav["closing_line_value"] == 233.5
    assert rec_fav["line_delta_pts"] == pytest.approx(1.0)
    assert rec_fav["clv_ev_pct"] > 1.5
    assert rec_fav["method"].endswith("_line_adjusted")

    rec_adv = compute_bet_clv(
        {"bet_id": "b2", "game_id": "G_TOT_ADV", "market": "total_points", "selection": "UNDER", "line_value": 224.5, "decimal_odds": 1.9346},
        idx,
        "Pinnacle [LIVE_API]",
    )
    assert rec_adv is not None
    assert rec_adv["line_delta_pts"] == pytest.approx(-1.5)
    assert rec_adv["clv_ev_pct"] < -5.0

    rec_spr = compute_bet_clv(
        {"bet_id": "b3", "game_id": "G_SPR", "market": "spread", "selection": "HOME", "line_value": -4.5, "decimal_odds": 1.95},
        idx,
        "Pinnacle [LIVE_API]",
    )
    assert rec_spr is not None
    assert rec_spr["closing_line_value"] == -6.0
    assert rec_spr["line_delta_pts"] == pytest.approx(1.5)
    assert rec_spr["clv_ev_pct"] > 2.0


def test_persist_closing_lines_promotes_only_latest_main_line_and_skips_disabled_props(tmp_path: Path) -> None:
    """Only the latest pre-tipoff main line is promoted; stale earlier lines & disabled props are skipped."""
    db = DatabaseManager(tmp_path / "close_main.sqlite3")
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, features_available_at, source_provider, ingested_at
        ) VALUES ('G_MOVE', '2026-27', '2026-11-16', '2026-11-16T01:00:00Z', 'MIL', 'ATL', 'SCHEDULED',
                  '2026-11-15T12:00:00Z', 'espn', '2026-11-15T12:00:00Z')
        """
    )
    for oid, prov, mkt, sel, lv, odds, ctr, ts in (
        ("O_EARLY", "Pinnacle [LIVE_API]", "total_points", "UNDER", 232.0, 1.94, 1.93, "2026-11-15T14:00:00Z"),
        ("O_LATE", "Pinnacle [LIVE_API]", "total_points", "UNDER", 233.5, 1.91, 1.98, "2026-11-16T00:45:00Z"),
        ("O_PROP", "Te Apuesto Perú [LIVE_API]|Trae Young|PTS", "player_prop", "OVER", 24.5, 1.85, 1.85, "2026-11-16T00:45:00Z"),
    ):
        db.insert_odds_snapshot(
            {
                "odds_id": oid,
                "game_id": "G_MOVE",
                "provider": prov,
                "market": mkt,
                "selection": sel,
                "line_value": lv,
                "decimal_odds": odds,
                "counterpart_decimal_odds": ctr,
                "captured_at": ts,
                "is_closing_line": 0,
                "source_type": "OBSERVED",
            }
        )

    promoted = persist_closing_lines_for_games(db, as_of_utc="2026-11-16T00:50:00Z")
    assert promoted == 1
    closes = db.fetch_all("SELECT odds_id, market, line_value FROM v_observed_odds_snapshots WHERE is_closing_line = 1")
    assert [(c["odds_id"], c["market"], float(c["line_value"])) for c in closes] == [
        ("O_LATE_CLOSE", "total_points", 233.5)
    ]


def test_evidence_staking_excludes_non_bet_rejects_and_uses_live_line_adjusted_clv(tmp_path: Path) -> None:
    """EV_BELOW_THRESHOLD / MODEL_MARKET_DISAGREEMENT rejects never trigger NO_EDGE; moved closes heal stale stored CLV."""
    db = DatabaseManager(tmp_path / "ev_filter.sqlite3")
    for i in range(12):
        gid = f"G_REJ_{i}"
        db.execute_insert(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, features_available_at, source_provider, ingested_at, home_score, away_score
            ) VALUES (?, '2026-27', '2026-11-15', '2026-11-15T23:00:00Z', 'MIL', 'ATL', 'FINAL',
                      '2026-11-15T12:00:00Z', 'espn', '2026-11-15T12:00:00Z', 110, 108)
            """,
            (gid,),
        )
        # 12 rejected EV_BELOW_THRESHOLD rows with -4% CLV must be ignored by clv_evidence_by_market
        db.execute_insert(
            """
            INSERT INTO shadow_candidates (
                shadow_id, prediction_id, game_id, matchday_date, market, selection, line_value,
                model_version_id, odds_provider, decimal_odds, raw_probability, calibrated_probability,
                ev_unit, ev_pct, hypothetical_kelly_stake_pen, decision_status, rejection_reason,
                clv_pct, status, hypothetical_unit_profit, emitted_at, source_type
            ) VALUES (?, NULL, ?, '2026-11-15', 'moneyline', 'HOME', NULL, 'v8', 'Pinnacle [LIVE_API]', 1.9, 0.53, 0.53,
                      0.007, 0.7, 0.2, 'NO_BET', 'EV_BELOW_THRESHOLD', -4.0, 'LOST', -1.0,
                      '2026-11-15T18:00:00Z', 'OBSERVED')
            """,
            (f"SHD_REJ_{i}", gid),
        )
        # 12 eligible total_points candidates whose stored clv_pct was corrupted (-3.26) by old exact-line bug,
        # while the real observed closing line moved 1.5 pts in our favor (234.5 -> 233.0)!
        db.execute_insert(
            """
            INSERT INTO shadow_candidates (
                shadow_id, prediction_id, game_id, matchday_date, market, selection, line_value,
                model_version_id, odds_provider, decimal_odds, raw_probability, calibrated_probability,
                ev_unit, ev_pct, hypothetical_kelly_stake_pen, decision_status, rejection_reason,
                clv_pct, status, hypothetical_unit_profit, emitted_at, source_type
            ) VALUES (?, NULL, ?, '2026-11-15', 'total_points', 'UNDER', 234.5, 'v8', 'Pinnacle [LIVE_API]', 1.93, 0.54, 0.54,
                      0.042, 4.2, 1.1, 'BET_PLACED', 'QUALIFIED_POSITIVE_EV', -3.26, 'WON', 0.93,
                      '2026-11-15T18:00:00Z', 'OBSERVED')
            """,
            (f"SHD_TOT_{i}", gid),
        )
        db.insert_odds_snapshot(
            {
                "odds_id": f"CLOSE_TOT_{i}",
                "game_id": gid,
                "provider": "Pinnacle [LIVE_API]",
                "market": "total_points",
                "selection": "UNDER",
                "line_value": 233.0,
                "decimal_odds": 1.91 + 0.01 * (i % 3),
                "counterpart_decimal_odds": 1.97,
                "captured_at": "2026-11-15T22:50:00Z",
                "is_closing_line": 1,
                "source_type": "OBSERVED",
            }
        )

    ev = clv_evidence_by_market(db)
    assert "moneyline" not in ev
    assert ev["total_points"]["verdict"] == "EDGE_SUPPORTED"
    assert ev["total_points"]["mean_clv_pct"] > 2.0

    engine = build_production_engine(db)
    assert engine._evidence_kelly_multiplier("moneyline") == (1.0, None)
    assert engine._evidence_kelly_multiplier("total_points") == (1.0, "EDGE_SUPPORTED")

    summary = summarize_shadow_ledger(db)
    assert summary["clv_scope"] == "eligible_positive_ev_line_adjusted"
    assert summary["clv_sample_size"] == 12
    assert summary["mean_clv_pct"] > 2.0


def test_closing_capture_skips_player_props_and_workflows_hardened(tmp_path: Path) -> None:
    """Closing capture disables prop persistence; workflows tighten cadence and handle delayed crons."""
    db = DatabaseManager(tmp_path / "cc_props.sqlite3")
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, features_available_at, source_provider, ingested_at
        ) VALUES ('G_CC', '2026-27', '2026-11-17', '2026-11-17T01:00:00Z', 'MIN', 'POR', 'SCHEDULED',
                  '2026-11-16T12:00:00Z', 'espn', '2026-11-16T12:00:00Z')
        """
    )
    seen_kwargs: list[dict[str, Any]] = []

    class _RecordingCollector:
        def collect_slate_odds(self, **kwargs: Any) -> dict[str, Any]:
            seen_kwargs.append(kwargs)
            return {"observed_quotes_count": 0}

    capture_closing_window(db, collector=_RecordingCollector(), now=datetime(2026, 11, 17, 0, 40, tzinfo=timezone.utc), window_minutes=25)
    assert len(seen_kwargs) == 1
    assert seen_kwargs[0]["include_player_props"] is False

    cc_wf = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "closing_capture.yml").read_text(encoding="utf-8"))
    cc_job = next(iter(cc_wf["jobs"].values()))
    assert cc_job["env"]["LOOP_INTERVAL_SECONDS"] == "900"
    assert "--window 25" in "\n".join(str(s.get("run", "")) for s in cc_job["steps"])

    main_raw = (PROJECT_ROOT / ".github" / "workflows" / "nba_cloud_automation.yml").read_text(encoding="utf-8")
    assert "UTC_HOUR=$((10#$(date -u +%H)))" in main_raw
    assert 'if [ "$UTC_HOUR" -ge 14 ]' in main_raw
    assert 'if [ "$UTC_HOUR" -ge 21 ]' in main_raw


def test_nba_injury_pdf_bottom_up_wrapped_player_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bottom-up PDF coordinates merge wrapped player suffix lines in visual top-to-bottom order."""

    class _FakePage:
        def __init__(self, tokens: list[tuple[float, float, str]]) -> None:
            self._tokens = tokens

        def extract_text(self, visitor_text: Any = None, **_kwargs: Any) -> str:
            if visitor_text is not None:
                for x, y, txt in self._tokens:
                    visitor_text(txt, None, [1.0, 0.0, 0.0, 1.0, x, y], None, 9.0)
            return ""

    class _FakeReader:
        def __init__(self, _stream: Any) -> None:
            # Bottom-up PDF coordinates: header at y=500, footer at y=40
            self.pages = [
                _FakePage(
                    [
                        (398.5, 40.0, "Page 1 of 1"),
                        (23.1, 500.0, "Game"),
                        (53.0, 500.0, "Date"),
                        (119.6, 500.0, "Game"),
                        (149.4, 500.0, "Time"),
                        (200.0, 500.0, "Matchup"),
                        (264.2, 500.0, "Team"),
                        (425.0, 500.0, "Player"),
                        (456.9, 500.0, "Name"),
                        (585.7, 500.0, "Current"),
                        (624.1, 500.0, "Status"),
                        (666.1, 500.0, "Reason"),
                        # Wrapped player name: "Udeh" on upper line (y=460), "Jr., Ernest" on lower line (y=450)
                        (24.1, 460.0, "11/17/2026"),
                        (120.6, 460.0, "08:00"),
                        (145.8, 460.0, "(ET)"),
                        (201.0, 460.0, "POR@MIN"),
                        (265.2, 460.0, "Portland"),
                        (310.0, 460.0, "Trail"),
                        (340.0, 460.0, "Blazers"),
                        (426.0, 460.0, "Udeh"),
                        (586.7, 460.0, "Out"),
                        (667.1, 460.0, "G League"),
                        (426.0, 450.0, "Jr., Ernest"),
                        (667.1, 450.0, "On Assignment"),
                    ]
                )
            ]

    monkeypatch.setattr("src.ingestion.nba_injury_report.PdfReader", _FakeReader)
    parsed = parse_nba_injury_pdf_bytes(b"%PDF-1.4 dummy", captured_at="2026-11-17T22:00:00Z")
    assert parsed["player_count"] == 1
    rec = parsed["by_team"]["POR"][0]
    assert rec["name"] == "Ernest Udeh Jr."
    assert rec["notes"] == "G League On Assignment"
