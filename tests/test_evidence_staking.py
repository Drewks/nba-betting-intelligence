"""Roadmap phase 3: the Kelly fraction of a market follows its shadow-ledger CLV evidence."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.config import ConfigError, load_config, parse_config
from src.paper_trading.engine import build_production_engine
from src.paper_trading.shadow_ledger import clv_evidence_by_market
from src.storage.db import DatabaseManager
from tests.helpers import PROJECT_ROOT


def _seed(
    db: DatabaseManager,
    n_games: int,
    market: str,
    clv: float,
    *,
    ev_pct: float = 4.5,
    rejection_reason: str = "KELLY_STAKE_BELOW_MINIMUM",
    prefix: str = "G",
) -> None:
    for i in range(n_games):
        gid = f"{prefix}_{market}_{i}"
        db.execute_insert(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, features_available_at, source_provider, ingested_at, home_score, away_score
            ) VALUES (?, '2026-27', '2026-11-10', '2026-11-10T00:00:00Z', 'BOS', 'NYK', 'FINAL',
                      '2026-11-09T12:00:00Z', 'espn', '2026-11-09T12:00:00Z', 110, 100)
            """,
            (gid,),
        )
        db.execute_insert(
            """
            INSERT INTO shadow_candidates (
                shadow_id, prediction_id, game_id, matchday_date, market, selection, line_value,
                model_version_id, odds_provider, decimal_odds, raw_probability, calibrated_probability,
                ev_unit, ev_pct, hypothetical_kelly_stake_pen, decision_status, rejection_reason,
                clv_pct, status, hypothetical_unit_profit, emitted_at, source_type
            ) VALUES (?, NULL, ?, '2026-11-10', ?, 'HOME', NULL, 'v_test', 'Pinnacle', 1.9, 0.55, 0.55,
                      ?, ?, 1.0, 'NO_BET', ?, ?, 'WON', 0.9,
                      '2026-11-09T20:00:00Z', 'OBSERVED')
            """,
            (f"SHD_{gid}", gid, market, ev_pct / 100.0, ev_pct, rejection_reason, clv + 0.2 * (i % 3)),
        )


def test_config_enables_evidence_staking_with_shrink_only_multipliers() -> None:
    es = load_config().evidence_staking
    assert es.enabled is True
    assert es.multiplier("NO_EDGE") == 0.5
    assert es.multiplier("EDGE_SUPPORTED") == 1.0
    assert es.multiplier("INSUFFICIENT_SAMPLE") == 1.0
    assert es.multiplier(None) == 1.0


@pytest.mark.parametrize("bad", [{"NO_EDGE": 1.5}, {"MAYBE": 0.5}])
def test_config_rejects_invalid_multipliers(bad: dict[str, float]) -> None:
    raw = yaml.safe_load((PROJECT_ROOT / "config" / "model_config.yaml").read_text(encoding="utf-8"))
    raw["evidence_staking"] = {"enabled": True, "multipliers": bad}
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_market_with_no_edge_gets_a_smaller_kelly_fraction(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "evidence.sqlite3")
    _seed(db, 12, "total_points", clv=-3.0)   # demonstrably loses to the close
    _seed(db, 4, "moneyline", clv=-3.0)       # too few games to conclude anything
    evidence = clv_evidence_by_market(db)
    assert evidence["total_points"]["verdict"] == "NO_EDGE"
    assert evidence["moneyline"]["verdict"] == "INSUFFICIENT_SAMPLE"

    engine = build_production_engine(db)
    assert engine._evidence_kelly_multiplier("total_points") == (0.5, "NO_EDGE")
    assert engine._evidence_kelly_multiplier("moneyline") == (1.0, "INSUFFICIENT_SAMPLE")
    assert engine._evidence_kelly_multiplier("spread") == (1.0, None)


def test_engines_built_outside_production_are_not_scaled(tmp_path: Path) -> None:
    from src.paper_trading.engine import PaperTradingEngine

    db = DatabaseManager(tmp_path / "evidence2.sqlite3")
    _seed(db, 12, "total_points", clv=-3.0)
    engine = PaperTradingEngine(db, staking_mode="FRACTIONAL_KELLY")
    assert engine._evidence_kelly_multiplier("total_points") == (1.0, None)


def test_walk_forward_replay_is_not_scaled_by_future_evidence(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "evidence3.sqlite3")
    _seed(db, 12, "total_points", clv=-3.0)
    engine = build_production_engine(db)
    assert engine._evidence_kelly_multiplier("total_points") == (0.5, "NO_EDGE")
    engine.is_backtest = True  # what WalkForwardBacktester.run_walk_forward sets during a replay
    assert engine._evidence_kelly_multiplier("total_points") == (1.0, None)


def test_daily_report_shows_evidence_and_forward_holdout(tmp_path: Path) -> None:
    import json

    from src.reporting.daily_report import _evidence_section

    db = DatabaseManager(tmp_path / "evidence_report.sqlite3")
    _seed(db, 12, "total_points", clv=-3.0)
    bt = tmp_path / "bt.json"
    bt.write_text(json.dumps({"main": {
        "generated_at_utc": "2026-11-16T23:38:07Z",
        "holdout_partition": {"forward_holdout": {
            "start_utc": "2026-11-15T00:00:00Z", "games": 11, "bets": 0, "roi_flat_pct": None, "mean_clv_pct": None,
        }},
    }}), encoding="utf-8")
    text = "\n".join(_evidence_section(db, bt))
    assert "`total_points` | 12 (12)" in text and "`NO_EDGE` | ×0.50" in text
    assert "`11` partidos, `0` apuestas" in text
    assert "sin backtest disponible" in "\n".join(_evidence_section(db, tmp_path / "missing.json"))
