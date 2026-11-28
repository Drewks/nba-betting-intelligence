from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.ingestion.nba_injury_report import (
    NBAOfficialInjuryFeed,
    canonicalize_nba_player_name,
    merge_official_and_espn_injuries,
    parse_nba_injury_pdf_bytes,
)
from src.prediction.injury_sniper import InjurySniperMonitor
from src.storage.db import DatabaseManager


def test_canonicalize_nba_player_name_handles_hyphens_and_suffixes() -> None:
    assert canonicalize_nba_player_name("Barnes, Scottie") == "Scottie Barnes"
    assert canonicalize_nba_player_name("Jackson- Davis, Trayce") == "Trayce Jackson-Davis"
    assert canonicalize_nba_player_name("McCullar Jr., Kevin") == "Kevin McCullar Jr."
    assert canonicalize_nba_player_name("Lively II, Dereck") == "Dereck Lively II"
    assert canonicalize_nba_player_name("Already Clean") == "Already Clean"


def test_parse_nba_injury_pdf_bytes_with_wrapped_reasons_and_pending_team(monkeypatch) -> None:
    class _FakePage:
        def __init__(self, tokens: list[tuple[float, float, str]]) -> None:
            self._tokens = tokens

        def extract_text(self, visitor_text=None, **_kwargs) -> str:
            if visitor_text is not None:
                for x, y, txt in self._tokens:
                    visitor_text(txt, None, [1.0, 0.0, 0.0, 1.0, x, y], None, 9.0)
            return ""

    class _FakeReader:
        def __init__(self, _stream) -> None:
            self.pages = [
                _FakePage(
                    [
                        (289.1, 62.0, "Injury"),
                        (355.6, 62.0, "Report:"),
                        (23.1, 115.2, "Game"),
                        (53.0, 115.2, "Date"),
                        (119.6, 115.2, "Game"),
                        (149.4, 115.2, "Time"),
                        (200.0, 115.2, "Matchup"),
                        (264.2, 115.2, "Team"),
                        (425.0, 115.2, "Player"),
                        (456.9, 115.2, "Name"),
                        (585.7, 115.2, "Current"),
                        (624.1, 115.2, "Status"),
                        (666.1, 115.2, "Reason"),
                        # Row 1: Barnes single-line
                        (24.1, 136.3, "11/12/2026"),
                        (120.6, 136.3, "07:00"),
                        (145.8, 136.3, "(ET)"),
                        (201.0, 136.3, "TOR@PHI"),
                        (265.2, 136.3, "Toronto"),
                        (300.3, 136.3, "Raptors"),
                        (426.0, 136.3, "Barnes,"),
                        (458.6, 136.3, "Scottie"),
                        (586.7, 136.3, "Out"),
                        (667.1, 136.3, "Injury/Illness"),
                        (721.8, 136.3, "-"),
                        (727.1, 136.3, "Left"),
                        (750.0, 136.3, "Groin"),
                        (775.0, 136.3, "Strain"),
                        # Row 2: wrapped vertically-centered 2-line Reason around y=166
                        (667.1, 159.0, "Injury/Illness"),
                        (721.8, 159.0, "-"),
                        (727.1, 159.0, "Left"),
                        (750.0, 159.0, "Knee"),
                        (426.0, 166.0, "Jackson-"),
                        (460.0, 166.0, "Davis,"),
                        (488.0, 166.0, "Trayce"),
                        (586.7, 166.0, "Out"),
                        (667.1, 173.0, "Management"),
                        # Row 3: NOT YET SUBMITTED team
                        (265.2, 195.0, "Philadelphia"),
                        (315.0, 195.0, "76ers"),
                        (667.1, 195.0, "NOT YET SUBMITTED"),
                        # Page footer at bottom
                        (398.5, 545.4, "Page 1 of 1"),
                    ]
                )
            ]

    monkeypatch.setattr("src.ingestion.nba_injury_report.PdfReader", _FakeReader)
    parsed = parse_nba_injury_pdf_bytes(
        b"%PDF-1.4 dummy",
        report_url="https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-11-12_08_00PM.pdf",
        captured_at="2026-11-13T01:05:00Z",
    )

    assert parsed["player_count"] == 2
    assert parsed["not_yet_submitted_teams"] == ["PHI"]
    tor = parsed["by_team"]["TOR"]
    assert len(tor) == 2
    assert tor[0]["name"] == "Scottie Barnes"
    assert tor[0]["status"] == "Out"
    assert tor[0]["notes"] == "Injury/Illness - Left Groin Strain"
    assert tor[1]["name"] == "Trayce Jackson-Davis"
    assert tor[1]["notes"] == "Injury/Illness - Left Knee Management"


def test_merge_official_and_espn_injuries_prioritizes_official() -> None:
    official = {
        "PHI": [
            {
                "name": "Joel Embiid",
                "team": "PHI",
                "status": "Out",
                "notes": "Left Knee Management",
                "source": "nba_official_injury_report",
            }
        ]
    }
    espn = {
        "PHI": [
            {
                "name": "Joel Embiid",
                "team": "PHI",
                "status": "Questionable",
                "notes": "Knee",
                "default_impact": -6.0,
            },
            {
                "name": "Andre Drummond",
                "team": "PHI",
                "status": "Day-To-Day",
                "notes": "Illness",
            },
        ]
    }
    merged = merge_official_and_espn_injuries(official, espn, ("PHI", "TOR"))
    assert len(merged) == 2
    assert merged[0]["name"] == "Joel Embiid"
    assert merged[0]["status"] == "Out"
    assert merged[0]["source"] == "nba_official_injury_report"
    assert merged[0]["default_impact"] == -6.0
    assert merged[1]["name"] == "Andre Drummond"
    assert merged[1]["source"] == "espn_summary"


def test_candidate_report_urls_orders_slots_from_et_time_backward() -> None:
    # 2026-11-12 20:15 ET == 2026-11-13 01:15 UTC
    as_of = datetime(2026, 11, 13, 1, 15, tzinfo=timezone.utc)
    urls = NBAOfficialInjuryFeed.candidate_report_urls(as_of_utc=as_of)
    assert urls[0].endswith("Injury-Report_2026-11-12_08_00PM.pdf")
    assert urls[1].endswith("Injury-Report_2026-11-12_07_30PM.pdf")


def test_injury_sniper_uses_official_feed_for_transitions(tmp_path: Path, monkeypatch) -> None:
    db = DatabaseManager(tmp_path / "sniper_official.sqlite3")
    now_dt = datetime.now(timezone.utc)
    tip_str = (now_dt + timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    matchday = now_dt.strftime("%Y-%m-%d")

    for code in ("BOS", "NYK"):
        db.execute_insert(
            "INSERT OR IGNORE INTO teams (team_id, full_name, conference, division, updated_at) VALUES (?, ?, 'East', 'Atlantic', ?)",
            (code, code, now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")),
        )
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, features_available_at, source_provider, ingested_at
        ) VALUES (?, '2026-27', ?, ?, 'NYK', 'BOS', 'SCHEDULED', ?, 'espn_public', ?)
        """,
        ("ESPN_999001", matchday, tip_str, now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")),
    )
    db.insert_odds_snapshot(
        {
            "odds_id": "O1",
            "game_id": "ESPN_999001",
            "provider": "DraftKings",
            "market": "moneyline",
            "selection": "HOME",
            "line_value": None,
            "decimal_odds": 2.05,
            "counterpart_decimal_odds": 1.85,
            "captured_at": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "is_closing_line": 0,
            "source_type": "OBSERVED",
        }
    )
    db.insert_odds_snapshot(
        {
            "odds_id": "O2",
            "game_id": "ESPN_999001",
            "provider": "DraftKings",
            "market": "moneyline",
            "selection": "AWAY",
            "line_value": None,
            "decimal_odds": 1.85,
            "counterpart_decimal_odds": 2.05,
            "captured_at": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "is_closing_line": 0,
            "source_type": "OBSERVED",
        }
    )
    # Seed prior snapshot where Jayson Tatum was Available -> Official PDF flips him to Out!
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO injury_status_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "PRIOR_TATUM",
                "ESPN_999001",
                (now_dt - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "BOS",
                "Jayson Tatum",
                "Available",
                "espn_summary",
            ),
        )

    class _FakeESPN:
        def _fetch_event_summary_context(self, _ev_id: str) -> dict[str, Any]:
            return {"fetch_ok": True, "injury_reports": {"NYK": [], "BOS": []}}

    class _FakeOfficialFeed:
        def fetch_latest_report(self, **_kwargs) -> dict[str, Any]:
            return {
                "fetch_ok": True,
                "source": "nba_official_injury_report",
                "by_team": {
                    "BOS": [
                        {
                            "name": "Jayson Tatum",
                            "team": "BOS",
                            "status": "Out",
                            "notes": "Right Ankle Sprain",
                            "source": "nba_official_injury_report",
                            "default_impact": 6.5,
                        }
                    ]
                },
            }

    import numpy as np

    monitor = InjurySniperMonitor(db=db, espn_adapter=_FakeESPN())  # type: ignore[arg-type]
    monitor.__dict__["official_injury_feed"] = _FakeOfficialFeed()
    rng = np.random.default_rng(7)
    cal_records = [
        {
            "game_start_time": f"2026-10-{1 + i % 28:02d}T00:00:00Z",
            "raw_probability": float(p_i),
            "outcome": int(rng.random() < p_i),
        }
        for i, p_i in enumerate(rng.uniform(0.2, 0.8, size=600))
    ]
    assert monitor.calibrator.fit(cal_records, "2026-11-01T00:00:00Z") is True

    res = monitor.scan_pregame_slate(reference_time_utc=now_dt, force_scan_all=True)
    assert res["total_scheduled"] == 1
    assert res["total_alerts_emitted"] >= 1
    snaps = db.fetch_all(
        "SELECT team, player_name, status, source FROM injury_status_snapshots WHERE game_id = ? ORDER BY captured_at DESC",
        ("ESPN_999001",),
    )
    tatum_snap = next((s for s in snaps if s["player_name"] == "Jayson Tatum" and s["status"] == "Out"), None)
    assert tatum_snap is not None
    assert tatum_snap["source"] == "nba_official_injury_report"
