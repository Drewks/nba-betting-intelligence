"""
Regression tests for the 2026-11-16 audit findings:

1. Production outage: the scheduled workflow ran the suite against the live database, so a test that
   pinned the bankroll to S/93.47 failed as soon as a bet settled and the cycle never ran.
2. Live book quotes were matched to games by team pair only, so two games of the same teams on
   consecutive days received the same quotes (and a bet was placed with another game's price).
3. Decision timestamps were "tip-off − 2 h" (a time in the future) instead of the real decision time.
4. Cross-book "(Best of N books)" aggregates and stale quotes were treated as executable prices.
5. The 2026-27 season was reported as an untouched holdout although it was visible before the freeze.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any

import yaml

from scripts.cloud_cycle_helpers import _pair_valid_pretip_quotes
from src.backtesting.real_odds_metrics import summarize_holdout_partition
from src.config import load_config, parse_config
from src.ingestion.peru_book_parsers import parse_event_start_utc, select_slate_row_by_start_time
from src.storage.db import DatabaseManager
from src.storage.migrations import m014_quarantine_misattributed_same_pair_quotes
from tests.helpers import PROJECT_ROOT


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


# 1. Workflow: tests must run on main's frozen baseline, before the live state is restored
def test_workflow_runs_tests_before_restoring_live_state() -> None:
    wf = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "nba_cloud_automation.yml").read_text(encoding="utf-8"))
    steps = next(iter(wf["jobs"].values()))["steps"]
    names = [str(s.get("name", "")) for s in steps]
    run_text = [str(s.get("run", "")) for s in steps]
    test_idx = next(i for i, r in enumerate(run_text) if "uv run pytest" in r)
    # Since 2026-11-24 the live database is decompressed from state-live's .gz instead of checked out
    restore_idx = next(
        i for i, r in enumerate(run_text) if "state-live" in r and "src.storage.state_live restore" in r
    )
    cycle_idx = next(i for i, n in enumerate(names) if "Ciclo de Inteligencia" in n)
    assert test_idx < restore_idx < cycle_idx


def test_no_test_pins_live_bankroll_values() -> None:
    e2e = (PROJECT_ROOT / "tests" / "test_slate_intelligence_e2e.py").read_text(encoding="utf-8")
    assert "93.47" not in e2e


# 2. Same teams on consecutive days: the event start time decides the game
def test_select_slate_row_uses_start_time_for_mini_series() -> None:
    pair = frozenset({"POR", "MIN"})
    day1 = {"team_pair": pair, "start_time": "2026-11-17T01:00:00Z", "event_id": 1}
    day2 = {"team_pair": pair, "start_time": "2026-11-18T01:00:00Z", "event_id": 2}
    assert select_slate_row_by_start_time([day1, day2], "2026-11-17T01:00:00Z") is day1
    assert select_slate_row_by_start_time([day1, day2], "2026-11-18T01:00:00Z") is day2
    # Only the first game is listed: the second game must not receive its quotes
    assert select_slate_row_by_start_time([day1], "2026-11-18T01:00:00Z") is None
    # Lima local time (UTC-5) on the book side is still the same game
    lima = {"team_pair": pair, "start_time": "2026-11-16 20:00:00", "event_id": 3}
    assert select_slate_row_by_start_time([lima], "2026-11-17T01:00:00Z") is lima


def test_select_slate_row_without_reference_or_dates_is_conservative() -> None:
    pair = frozenset({"POR", "MIN"})
    a = {"team_pair": pair, "start_time": None}
    b = {"team_pair": pair, "start_time": None}
    assert select_slate_row_by_start_time([a], None) is a
    assert select_slate_row_by_start_time([a, b], None) is None
    assert select_slate_row_by_start_time([a, b], "2026-11-17T01:00:00Z") is None
    assert select_slate_row_by_start_time([], "2026-11-17T01:00:00Z") is None


def test_parse_event_start_formats() -> None:
    assert parse_event_start_utc("2026-11-17T01:00:00Z") == _utc("2026-11-17T01:00:00Z")
    assert parse_event_start_utc("2026-11-17 01:00:00") == _utc("2026-11-17T01:00:00Z")
    assert parse_event_start_utc(1794704400000) is not None
    assert parse_event_start_utc("not a date") is None
    assert parse_event_start_utc("") is None


def _seed_game(db: DatabaseManager, game_id: str, start: str, home: str = "MIN", away: str = "POR") -> None:
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, features_available_at, source_provider, ingested_at
        ) VALUES (?, '2026-27', ?, ?, ?, ?, 'SCHEDULED', '2026-11-16T12:00:00Z', 'espn', '2026-11-16T12:00:00Z')
        """,
        (game_id, start[:10], start, home, away),
    )


def _insert_quote(
    db: DatabaseManager,
    odds_id: str,
    game_id: str,
    odds: float,
    captured: str = "2026-11-16T23:06:28Z",
    line: float = 227.5,
) -> None:
    db.insert_odds_snapshot({
        "odds_id": odds_id,
        "game_id": game_id,
        "provider": "Pinnacle [LIVE_API]",
        "market": "total_points",
        "selection": "UNDER",
        "line_value": line,
        "decimal_odds": odds,
        "counterpart_decimal_odds": 1.9091,
        "captured_at": captured,
        "source_type": "OBSERVED",
    })


def test_migration_014_quarantines_quotes_copied_onto_both_games(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "m014.sqlite3")
    _seed_game(db, "G_DAY1", "2026-11-17T01:00:00Z")
    _seed_game(db, "G_DAY2", "2026-11-18T01:00:00Z")
    _seed_game(db, "G_OTHER", "2026-11-17T02:00:00Z", home="BOS", away="NYK")
    # A copied slate entry: three identical quotes of one capture on both games
    for i, odds in enumerate((1.9804, 1.9091, 2.16)):
        _insert_quote(db, f"Q_DAY1_{i}", "G_DAY1", odds, line=227.5 + i)
        _insert_quote(db, f"Q_DAY2_{i}", "G_DAY2", odds, line=227.5 + i)  # the copies
    _insert_quote(db, "Q_OTHER", "G_OTHER", 1.9804)  # same price, different teams: legitimate
    _insert_quote(db, "Q_DAY1_LATER", "G_DAY1", 1.95, captured="2026-11-16T23:30:00Z")  # unique: kept
    # A single coincidental equal price on both games of the same teams (another capture): kept
    _insert_quote(db, "Q_COINC_1", "G_DAY1", 1.87, captured="2026-11-16T20:00:00Z")
    _insert_quote(db, "Q_COINC_2", "G_DAY2", 1.87, captured="2026-11-16T20:00:00Z")

    conn = sqlite3.connect(tmp_path / "m014.sqlite3")
    try:
        details = m014_quarantine_misattributed_same_pair_quotes(conn, "TEST_014")
        conn.commit()
        quarantined = {r[0] for r in conn.execute("SELECT odds_id FROM quarantined_odds")}
        visible = {r[0] for r in conn.execute("SELECT odds_id FROM v_observed_odds_snapshots")}
    finally:
        conn.close()
    copies = {f"Q_DAY{d}_{i}" for d in (1, 2) for i in range(3)}
    assert details["quarantined_quotes"] == 6
    assert quarantined == copies
    assert {"Q_OTHER", "Q_DAY1_LATER", "Q_COINC_1", "Q_COINC_2"} <= visible
    assert not (copies & visible)


# 4. Executable prices only
def _quote(provider: str, sel: str, odds: float, captured: str, line: float = 227.5) -> dict[str, Any]:
    return {
        "provider": provider,
        "market": "total_points",
        "selection": sel,
        "line_value": line,
        "decimal_odds": odds,
        "captured_at": captured,
    }


def test_pairing_excludes_best_of_aggregates_stale_and_future_quotes() -> None:
    start = _utc("2026-11-17T01:00:00Z")
    decision = _utc("2026-11-16T23:00:00Z")
    raw = [
        _quote("Pinnacle [LIVE_API]", "OVER", 1.91, "2026-11-16T22:50:00Z"),
        _quote("Pinnacle [LIVE_API]", "UNDER", 1.98, "2026-11-16T22:50:00Z"),
        _quote("FanDuel (Best of 32 books)", "OVER", 2.05, "2026-11-16T22:50:00Z"),
        _quote("FanDuel (Best of 32 books)", "UNDER", 2.02, "2026-11-16T22:50:00Z"),
        _quote("LowVig.ag (LineShop)", "OVER", 1.95, "2026-11-15T10:00:00Z"),  # 37 h old
        _quote("LowVig.ag (LineShop)", "UNDER", 1.95, "2026-11-15T10:00:00Z"),
        _quote("DraftKings", "OVER", 1.90, "2026-11-16T23:30:00Z"),  # after the decision
        _quote("DraftKings", "UNDER", 1.92, "2026-11-16T23:30:00Z"),
    ]
    paired = _pair_valid_pretip_quotes(
        raw,
        start,
        decision_dt=decision,
        max_quote_age_hours=6.0,
        excluded_provider_markers=("(Best of",),
    )
    assert {p["provider"] for p in paired} == {"Pinnacle [LIVE_API]"}
    # Without the live filters (historical walk-forward) nothing but the time-of-tip rule applies
    assert len(_pair_valid_pretip_quotes(raw, start)) == 8


def test_pairing_drops_high_margin_markets() -> None:
    start = _utc("2026-11-17T01:00:00Z")
    raw = [
        _quote("Pinnacle [LIVE_API]", "OVER", 1.91, "2026-11-16T22:50:00Z"),
        _quote("Pinnacle [LIVE_API]", "UNDER", 1.98, "2026-11-16T22:50:00Z"),  # ~2.9% margin
        _quote("Te Apuesto Perú [LIVE_API]", "OVER", 1.79, "2026-11-16T22:50:00Z"),
        _quote("Te Apuesto Perú [LIVE_API]", "UNDER", 1.84, "2026-11-16T22:50:00Z"),  # ~10.2% margin
    ]
    paired = _pair_valid_pretip_quotes(raw, start, max_overround=0.06)
    assert {p["provider"] for p in paired} == {"Pinnacle [LIVE_API]"}
    assert load_config().execution.max_bookmaker_overround == 0.06


# 5. Honest evaluation protocol
def test_config_declares_contaminated_season_holdout_and_forward_holdout() -> None:
    cfg = load_config()
    assert cfg.evaluation.season_holdout_contaminated is True
    assert cfg.evaluation.forward_holdout_start_utc == "2026-11-27T00:00:00Z"
    assert cfg.evaluation.trials_evaluated_count >= 9
    assert cfg.execution.max_quote_age_hours == 6.0
    assert "(Best of" in cfg.execution.excluded_provider_markers


def test_execution_config_validation() -> None:
    raw = yaml.safe_load((PROJECT_ROOT / "config" / "model_config.yaml").read_text(encoding="utf-8"))
    raw["execution"] = {"max_quote_age_hours": 500}
    try:
        parse_config(raw)
    except ValueError as exc:
        assert "max_quote_age_hours" in str(exc)
    else:  # pragma: no cover - must fail
        raise AssertionError("an out-of-range quote age must be rejected")


def test_holdout_partition_reports_forward_holdout_and_contamination() -> None:
    rows = [
        {"game_id": "A", "season": "2025-26", "game_start_time": "2026-03-01T00:00:00Z", "cal_home": 0.6, "home_won": 1},
        {"game_id": "B", "season": "2026-27", "game_start_time": "2026-11-01T00:00:00Z", "cal_home": 0.4, "home_won": 0},
        {"game_id": "C", "season": "2026-27", "game_start_time": "2026-11-16T00:00:00Z", "cal_home": 0.7, "home_won": 1},
    ]
    bets = [
        {"game_id": "B", "season": "2026-27", "status": "LOST", "stake_pen": 1.0, "net_profit_pen": -1.0, "clv_ev_pct": -2.0},
        {"game_id": "C", "season": "2026-27", "status": "WON", "stake_pen": 1.0, "net_profit_pen": 0.9, "clv_ev_pct": 1.5},
    ]
    out = summarize_holdout_partition(
        rows,
        bets,
        development_seasons=("2024-25", "2025-26"),
        holdout_season="2026-27",
        frozen_protocol_id="TEST",
        trials_evaluated_count=9,
        season_holdout_contaminated=True,
        forward_holdout_start_utc="2026-11-15T00:00:00Z",
    )
    assert out["season_holdout_contaminated"] is True
    assert out["untouched_holdout"]["games"] == 2
    assert out["forward_holdout"]["games"] == 1
    assert out["forward_holdout"]["bets"] == 1
    assert out["forward_holdout"]["roi_flat_pct"] == 90.0


def test_espn_upcoming_games_use_ingestion_time_as_feature_availability() -> None:
    src = (PROJECT_ROOT / "src" / "ingestion" / "espn.py").read_text(encoding="utf-8")
    assert "feat_avail = now_utc" in src
    helpers = (PROJECT_ROOT / "scripts" / "cloud_cycle_helpers.py").read_text(encoding="utf-8")
    assert "pred_dt = max(avail_dt, latest_odds_dt)" not in helpers
    assert "pred_ts = decision_ts" in helpers


def test_espn_provider_aliases_are_canonical() -> None:
    from src.ingestion.espn import canonical_provider_name

    assert canonical_provider_name("Draft Kings") == "DraftKings"
    assert canonical_provider_name("draft  kings") == "DraftKings"
    assert canonical_provider_name("DraftKings") == "DraftKings"
    assert canonical_provider_name("ESPN BET") == "ESPN BET"


def test_clv_evidence_verdicts() -> None:
    from src.paper_trading.shadow_ledger import clv_evidence

    assert clv_evidence([])["verdict"] == "INSUFFICIENT_SAMPLE"
    assert clv_evidence([1.0, 2.0, 3.0])["verdict"] == "INSUFFICIENT_SAMPLE"
    neg = clv_evidence([-3.0 + 0.1 * (i % 5) for i in range(40)])
    assert neg["verdict"] == "NO_EDGE" and neg["ci95_pct"][1] < 0
    pos = clv_evidence([2.0 + 0.1 * (i % 5) for i in range(40)])
    assert pos["verdict"] == "EDGE_SUPPORTED"
    mixed = clv_evidence([(-1.0) ** i * 4.0 for i in range(40)])
    assert mixed["verdict"] == "INCONCLUSIVE"
    assert mixed["signals_needed_for_target"] > 40


def test_clv_evidence_groups_signals_by_game() -> None:
    from src.paper_trading.shadow_ledger import clv_evidence

    clvs = [-3.0, -3.1, -2.9, -3.0] * 3 + [1.0, 1.2]
    games = ["A", "A", "A", "A", "B", "B", "B", "B", "C", "C", "C", "C", "D", "D"]
    ev = clv_evidence(clvs, groups=games)
    assert ev["n"] == 4 and ev["n_signals"] == 14 and ev["independent_unit"] == "game"
    ungrouped = clv_evidence(clvs)
    width = ev["ci95_pct"][1] - ev["ci95_pct"][0]
    assert width > ungrouped["ci95_pct"][1] - ungrouped["ci95_pct"][0]


def test_clv_evidence_uses_student_t_for_small_samples() -> None:
    import math
    import statistics

    from src.paper_trading.shadow_ledger import clv_evidence

    # Ten games with t ~ 2.1: a normal 1.96 interval would exclude zero, the Student-t interval
    # (df=9, 2.262) does not, so no edge is claimed.
    vals = [1.7, -0.3] * 5
    mean, sd = statistics.mean(vals), statistics.stdev(vals)
    assert mean - 1.96 * sd / math.sqrt(10) > 0
    ev = clv_evidence(vals)
    assert ev["ci95_pct"][0] < 0 < ev["ci95_pct"][1]
    assert ev["verdict"] == "INCONCLUSIVE"
