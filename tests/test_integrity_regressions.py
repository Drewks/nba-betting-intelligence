"""
Regression tests for the 2026-11-09 integrity audit:
settlement ingestion, odds provenance, history immutability, fail-closed gates, CLV,
AGENTS.md risk limits and the injury sniper probability model.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from src.agents.specialized_agents import NBAAuditorAgent, NBADataScoutAgent
from src.backtesting.backtester import WalkForwardBacktester, evaluate_simulation_exit_gates
from src.config import ConfigError, parse_config
from src.evaluation.clv import summarize_clv
from src.ingestion.adapters import BaseNBADataAdapter, DataSourceRouter
from src.paper_trading.engine import PaperTradingEngine, RiskLimitError
from src.storage import migrations
from src.storage.db import DatabaseManager


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class _StaticAdapter(BaseNBADataAdapter):
    provider_name = "static_test"

    def __init__(self, games: list[dict[str, Any]], odds: list[dict[str, Any]] | None = None) -> None:
        self.games = games
        self.odds = odds or []

    def fetch_games_and_odds(self, date_str: str | None = None, as_of_utc: str | None = None) -> dict[str, list[dict[str, Any]]]:
        return {"games": self.games, "odds": self.odds}


def _game(status: str, start: datetime, avail: datetime, **kw: Any) -> dict[str, Any]:
    g = {
        "game_id": "ESPN_1_TEST_BOS_AT_NYK",
        "season": "2026-27",
        "matchday_date": _iso(start)[:10],
        "game_start_time": _iso(start),
        "home_team": "NYK",
        "away_team": "BOS",
        "status": status,
        "home_score": None,
        "away_score": None,
        "home_off_rtg": 115.0,
        "home_def_rtg": 112.0,
        "home_pace": 99.0,
        "away_off_rtg": 116.0,
        "away_def_rtg": 111.0,
        "away_pace": 98.0,
        "home_rest_days": 2,
        "away_rest_days": 2,
        "features_available_at": _iso(avail),
        "source_provider": "espn_v2_syndicate_enriched",
        "ingested_at": _iso(avail),
        "result_recorded_at": None,
    }
    g.update(kw)
    return g


# 1. Results ingested after tip-off must update the game (the 2026-11-09 regression discarded them)
def test_final_result_ingestion_updates_status_and_preserves_pregame_features(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    scout = NBADataScoutAgent(db)
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=5)
    pre_avail = start - timedelta(hours=3)

    scout.ingest_and_validate_dataset(DataSourceRouter([_StaticAdapter([_game("SCHEDULED", start, pre_avail)])]))
    final = _game("FINAL", start, now, home_score=110, away_score=101, result_recorded_at=_iso(now))
    res = scout.ingest_and_validate_dataset(DataSourceRouter([_StaticAdapter([final])]))

    assert res["discarded_games"] == []
    assert res["results_applied"] == 1
    row = db.fetch_one("SELECT status, home_score, away_score, features_available_at FROM games")
    assert row is not None
    assert (row["status"], row["home_score"], row["away_score"]) == ("FINAL", 110, 101)
    assert row["features_available_at"] == _iso(pre_avail)  # pre-game audit trail untouched

    # A stale SCHEDULED record can never revert a FINAL game
    regress = scout.ingest_and_validate_dataset(DataSourceRouter([_StaticAdapter([_game("SCHEDULED", start, pre_avail)])]))
    assert regress["discarded_games"] and "regression" in regress["discarded_games"][0]["reason"].lower()
    assert db.fetch_one("SELECT status FROM games")["status"] == "FINAL"  # type: ignore[index]


def test_final_result_recorded_before_tipoff_is_rejected(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    now = datetime.now(timezone.utc)
    start = now + timedelta(hours=2)
    bad = _game("FINAL", start, now, home_score=100, away_score=90, result_recorded_at=_iso(now))
    res = NBADataScoutAgent(db).ingest_and_validate_dataset(DataSourceRouter([_StaticAdapter([bad])]))
    assert res["discarded_games"]
    assert db.fetch_one("SELECT COUNT(*) AS c FROM games")["c"] == 0  # type: ignore[index]


# 2. Odds provenance
def _seed_game(db: DatabaseManager, game_id: str = "G1", start: str = "2026-11-10T00:00:00Z") -> None:
    db.execute_insert(
        """
        INSERT INTO games (game_id, season, matchday_date, game_start_time, home_team, away_team, status,
                           features_available_at, source_provider, ingested_at)
        VALUES (?, '2026-27', ?, ?, 'NYK', 'BOS', 'SCHEDULED', '2026-11-09T12:00:00Z', 'espn', '2026-11-09T12:00:00Z')
        """,
        (game_id, start[:10], start),
    )


def _odds(odds_id: str, provider: str, sel: str, price: float, counter: float, source_type: str | None = "OBSERVED",
          captured: str = "2026-11-09T20:00:00Z", closing: int = 0) -> dict[str, Any]:
    o: dict[str, Any] = {
        "odds_id": odds_id, "game_id": "G1", "provider": provider, "market": "moneyline", "selection": sel,
        "line_value": None, "decimal_odds": price, "counterpart_decimal_odds": counter,
        "captured_at": captured, "is_closing_line": closing,
    }
    if source_type is not None:
        o["source_type"] = source_type
    return o


def test_odds_writes_require_explicit_source_type(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    _seed_game(db)
    with pytest.raises(ValueError):
        db.insert_odds_snapshot(_odds("O1", "Pinnacle", "HOME", 1.9, 1.95, source_type=None))
    # The raw schema has no default either: a writer that forgets provenance fails
    with pytest.raises(sqlite3.IntegrityError):
        db.execute_insert(
            "INSERT INTO odds_snapshots (odds_id, game_id, provider, market, selection, decimal_odds, captured_at) "
            "VALUES ('O2', 'G1', 'X', 'moneyline', 'HOME', 1.9, '2026-11-09T20:00:00Z')"
        )
    assert db.insert_odds_snapshot(_odds("O3", "Pinnacle", "HOME", 1.9, 1.95)) is True


def test_observed_view_excludes_generated_quotes_and_closing_promotion_never_launders(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    _seed_game(db)
    db.insert_odds_snapshot(_odds("REAL_H", "Pinnacle (LineShop)", "HOME", 1.90, 1.95, captured="2026-11-09T20:00:00Z"))
    # A later, system-generated quote that the old code labelled OBSERVED
    db.insert_odds_snapshot(_odds("FAKE_H", "Pinnacle [LIVE_SCRAPER]", "HOME", 1.91, 1.91, captured="2026-11-09T22:00:00Z"))
    db.insert_odds_snapshot(_odds("DERIVED_H", "RETAbet Perú", "HOME", 1.85, 1.95, source_type="DERIVED", captured="2026-11-09T23:00:00Z"))

    observed = {r["odds_id"] for r in db.fetch_all("SELECT odds_id FROM v_observed_odds_snapshots")}
    assert observed == {"REAL_H"}

    engine = PaperTradingEngine(db)
    assert engine.persist_closing_lines_for_games(as_of_utc="2026-11-10T01:00:00Z") == 1
    closes = db.fetch_all("SELECT odds_id, provider, source_type FROM odds_snapshots WHERE is_closing_line = 1")
    assert [(c["odds_id"], c["source_type"]) for c in closes] == [("REAL_H_CLOSE", "OBSERVED")]


# 3. History immutability: deletions are detected even if triggers are bypassed
def test_auditor_detects_deleted_history(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    _seed_game(db)
    db.insert_odds_snapshot(_odds("O1", "Pinnacle", "HOME", 1.9, 1.95))
    auditor = NBAAuditorAgent(db, PaperTradingEngine(db))
    assert auditor._verify_and_register_history()["missing_rows_total"] == 0

    with db.connect() as conn:  # simulate the 2026-11-09 tampering (trigger dropped, row deleted)
        conn.execute("DROP TRIGGER prevent_odds_delete")
        conn.execute("DELETE FROM odds_snapshots WHERE odds_id = 'O1'")
    result = auditor._verify_and_register_history()
    assert result["missing_rows_total"] == 1
    assert result["missing_rows_by_table"]["odds_snapshots"] == 1

    with pytest.raises(sqlite3.IntegrityError):  # the registry itself is append-only
        with db.connect() as conn:
            conn.execute("DELETE FROM audit_row_registry")


def test_ledger_reconciliation_flags_missing_settlement_entry(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    auditor = NBAAuditorAgent(db, PaperTradingEngine(db))
    assert auditor._reconcile_ledger() == []
    db.execute_insert(
        """
        INSERT INTO games (game_id, season, matchday_date, game_start_time, home_team, away_team, status,
                           home_score, away_score, features_available_at, source_provider, ingested_at)
        VALUES ('G2', '2026-27', '2026-11-08', '2026-11-08T00:00:00Z', 'NYK', 'BOS', 'FINAL', 100, 90,
                '2026-11-07T20:00:00Z', 'espn', '2026-11-07T20:00:00Z')
        """
    )
    db.execute_insert(
        "INSERT INTO model_versions (model_version_id, model_family, market, train_start_date, train_end_date, trained_at, "
        "hyperparameters_json, approved_by) VALUES ('m', 'f', 'moneyline', 'a', 'b', 'c', '{}', 'test')"
    )
    db.execute_insert(
        """
        INSERT INTO predictions (prediction_id, game_id, market, selection, model_version_id, raw_probability,
            calibrated_probability, uncertainty_std, implied_prob_gross, decimal_odds_used, odds_provider,
            odds_captured_at, ev_unit, ev_pct, emitted_at, features_snapshot_json)
        VALUES ('P2', 'G2', 'moneyline', 'HOME', 'm', 0.6, 0.6, 0.05, 0.5, 2.0, 'Pinnacle',
                '2026-11-07T21:00:00Z', 0.2, 20.0, '2026-11-07T21:00:00Z', '{}')
        """
    )
    db.execute_insert(
        """
        INSERT INTO simulated_bets (bet_id, prediction_id, game_id, matchday_date, market, selection, decimal_odds,
            estimated_prob, estimated_ev, stake_pen, emitted_at, model_version_id, status, net_profit_pen)
        VALUES ('B2', 'P2', 'G2', '2026-11-08', 'moneyline', 'HOME', 2.0, 0.6, 0.2, 1.0, '2026-11-07T21:00:00Z',
                'm', 'WON', 1.0)
        """
    )
    issues = auditor._reconcile_ledger()
    assert any("B2" in i and "reservation" in i for i in issues)
    assert any("B2" in i and "settlement" in i for i in issues)


# 4. History restoration migration
def test_restore_migration_skips_non_production_db_and_restores_with_checksum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    applied = {r["migration_id"]: json.loads(r["details_json"]) for r in db.fetch_all("SELECT * FROM schema_migrations")}
    assert applied["2026_11_09_003_restore_history_from_93cfa87"]["action"] == "skipped"

    # Build a tiny bundle and run the restore step directly against a db holding the probe game
    _seed_game(db, game_id=migrations.RESTORE_PROBE_GAME_ID)
    payload = {
        "missing_rows": {
            "odds_snapshots": [{
                "odds_id": "LOST_ODDS", "game_id": migrations.RESTORE_PROBE_GAME_ID, "provider": "Draft Kings",
                "market": "moneyline", "selection": "HOME", "line_value": None, "decimal_odds": 1.64,
                "counterpart_decimal_odds": 2.35, "captured_at": "2026-11-09T20:00:00Z", "is_closing_line": 0,
                "source_type": "OBSERVED",
            }],
        },
        "game_result_restores": [],
        "bet_settlement_restores": [],
        "prop_settlements_overwritten": [],
    }
    import hashlib
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps({"payload_sha256": digest, "payload": payload}), encoding="utf-8")
    monkeypatch.setattr(migrations, "RECOVERY_BUNDLE_PATH", bundle_path)

    with db.connect() as conn:
        summary = migrations.m003_restore_history_from_93cfa87(conn, "test_restore")
    assert summary["odds_snapshots_restored"] == 1
    assert db.fetch_one("SELECT COUNT(*) AS c FROM audit_repairs WHERE row_pk = 'LOST_ODDS'")["c"] == 1  # type: ignore[index]

    tampered = {"payload_sha256": digest, "payload": {**payload, "game_result_restores": [{"x": 1}]}}
    bundle_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        with db.connect() as conn:
            migrations.m003_restore_history_from_93cfa87(conn, "test_restore_2")


# 5. Fail-closed gates and the market benchmark
def test_exit_gates_fail_closed_without_data() -> None:
    gates = evaluate_simulation_exit_gates({})
    assert gates["all_gates_passed"] is False
    assert gates["gates"]["gate_3_calibration_non_inferior_to_baseline"]["passed"] is False
    assert gates["gates"]["gate_7_reproducible_results"]["passed"] is False
    assert gates["gates"]["gate_9_independent_audit_approved"]["passed"] is False
    assert gates["gates"]["gate_10_non_inferior_to_devigged_market"]["passed"] is False

    beats_baseline_only = {
        "overall_brier_score": 0.20, "baseline_brier_score": 0.25, "overall_log_loss": 0.60, "baseline_log_loss": 0.69,
        "model_brier_on_market_subset": 0.20, "market_brier_score": 0.19,
        "model_log_loss_on_market_subset": 0.60, "market_log_loss": 0.58,
    }
    g = evaluate_simulation_exit_gates(beats_baseline_only)["gates"]
    assert g["gate_3_calibration_non_inferior_to_baseline"]["passed"] is True
    assert g["gate_10_non_inferior_to_devigged_market"]["passed"] is False


def test_metrics_have_no_passing_defaults_when_empty(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    m = WalkForwardBacktester(db, PaperTradingEngine(db, exclude_synthetic=True)).compute_comprehensive_metrics()
    for key in ("overall_brier_score", "baseline_brier_score", "overall_ece", "market_brier_score", "mean_clv_pct"):
        assert m[key] is None, key
    assert m["exit_gates_evaluation"]["all_gates_passed"] is False


# 6. CLV in probability space
def test_clv_probability_space_and_outlier_exclusion() -> None:
    closes = [
        {"game_id": "G", "market": "moneyline", "selection": "HOME", "line_value": None, "decimal_odds": 1.80,
         "counterpart_decimal_odds": 2.10, "provider": "Pinnacle (LineShop)", "captured_at": "t2"},
        {"game_id": "G", "market": "moneyline", "selection": "HOME", "line_value": None, "decimal_odds": 1.70,
         "counterpart_decimal_odds": 2.20, "provider": "DraftKings", "captured_at": "t3"},
        {"game_id": "H", "market": "moneyline", "selection": "AWAY", "line_value": None, "decimal_odds": 1.19,
         "counterpart_decimal_odds": 5.00, "provider": "DraftKings", "captured_at": "t3"},
    ]
    bets = [
        {"bet_id": "b1", "game_id": "G", "market": "moneyline", "selection": "HOME", "line_value": None, "decimal_odds": 1.95},
        # The 2026-11-09 fabricated 1.917 price vs a real 1.19 close: a data error, excluded from the mean
        {"bet_id": "b2", "game_id": "H", "market": "moneyline", "selection": "AWAY", "line_value": None, "decimal_odds": 1.917},
    ]
    out = summarize_clv(bets, closes)
    rec = {r["bet_id"]: r for r in out["per_bet"]}
    assert rec["b1"]["closing_provider"].startswith("Pinnacle")  # Pinnacle preferred
    assert 0.0 < rec["b1"]["clv_ev_pct"] < 15.0
    assert rec["b2"]["is_outlier"] is True
    assert out["clv_sample_size"] == 1 and out["clv_outliers_excluded"] == 1


# 7. AGENTS.md risk limits and parlays
def test_config_enforces_agents_md_limits() -> None:
    base = {
        "model": {"version_id": "v", "ewma_alpha_slow": 0.045, "ewma_alpha_fast": 0.11, "tempo_alpha_slow": 0.055,
                  "tempo_alpha_fast": 0.13, "market_anchor_model_weight": 0.3},
        "risk_management": {"virtual_bankroll_initial_pen": 100.0, "staking_mode": "fractional_kelly",
                            "kelly_fraction": 0.25, "min_stake_pen": 0.5, "max_stake_bankroll_fraction": 0.03,
                            "base_stake_pen": 1.0, "max_stake_pen": 3.0,
                            "max_selections_per_matchday": 3, "min_ev_threshold": 0.05, "max_portfolio_exposure_pct": 0.2,
                            "allow_parlays": False, "allow_player_props_betting": False},
        "sources": {"betting_allowed_source_types": ["OBSERVED"]},
    }
    assert parse_config(base).risk.max_stake_pen == 3.0
    for patch in (
        {"max_stake_pen": 25.0},
        {"max_stake_bankroll_fraction": 0.25},
        {"kelly_fraction": 1.5},
        {"staking_mode": "martingale"},
        {"min_stake_pen": 3.5},
        {"min_ev_threshold": 0.02},
        {"max_selections_per_matchday": 5},
    ):
        bad = json.loads(json.dumps(base))
        bad["risk_management"].update(patch)
        with pytest.raises(ConfigError):
            parse_config(bad)


def test_engine_default_cap_and_parlay_rejection(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    with pytest.raises(RiskLimitError):
        PaperTradingEngine(db, base_stake_pen=1.0, max_stake_pen=2.0)
    engine = PaperTradingEngine(db)
    with pytest.raises(RiskLimitError):
        engine.record_player_prop_pick({"game_id": "X", "prop_category": "SGP"}, allow_parlay=False)
    with pytest.raises(RiskLimitError):
        PaperTradingEngine(db, base_stake_pen=1.0, max_stake_pen=25.0, staking_mode="FRACTIONAL_KELLY")


def test_production_engine_matches_config_and_props_exposure_is_capped(tmp_path: Path) -> None:
    from src.config import load_config
    from src.paper_trading.engine import build_production_engine
    from src.prediction.player_props import PlayerPropsEngine

    db = DatabaseManager(tmp_path / "t.sqlite3")
    risk = load_config().risk
    engine = build_production_engine(db)
    assert engine.staking_mode == "FRACTIONAL_KELLY"
    assert (engine.max_stake_pen, engine.kelly_fraction) == (risk.max_stake_pen, risk.kelly_fraction)

    props = PlayerPropsEngine(db=db)
    assert props._props_exposure_allows(0.0, 100.0) is False  # no edge -> never recorded
    assert props._props_exposure_allows(5.0, 100.0) is True
    _seed_game(db, game_id="G1", start="2030-01-01T00:00:00Z")
    for i in range(6):  # 6 x S/5 = S/30 pending = the 30% exposure cap
        engine.record_player_prop_pick({
            "prop_id": f"P{i}", "game_id": "G1", "matchday_date": "2030-01-01", "player_name": "LeBron James",
            "team": "NYK", "prop_category": "PTS", "line_value": 20.5, "selection": "OVER", "decimal_odds": 1.9,
            "model_prob": 0.6, "stake_pen": 5.0,
        })
    assert props._props_exposure_allows(1.0, 100.0) is False


def test_props_recording_is_idempotent_and_capped_per_matchday(tmp_path: Path) -> None:
    from src.config import load_config
    from src.prediction.player_props import PlayerPropsEngine

    db = DatabaseManager(tmp_path / "t.sqlite3")
    _seed_game(db, game_id="G1", start="2030-01-01T00:00:00Z")
    props = PlayerPropsEngine(db=db)

    def pick(player: str, n: int) -> dict:
        return {
            "prop_id": f"PX{n}", "game_id": "G1", "matchday_date": "2030-01-01", "player_name": player,
            "team": "NYK", "prop_category": "PTS", "line_value": 20.5, "selection": "OVER", "decimal_odds": 1.9,
            "projected_mean": 24.0, "projected_std": 6.0, "model_prob": 0.6, "conformal_p_low": 0.55,
            "conformal_p_high": 0.65, "ev_pct": 14.0, "ev_lower_bound_pct": 4.5, "kelly_stake_pen": 2.0,
            "usage_bump_pct": 0.0, "rationale": "[LÍNEA ESTIMADA, no observada] test",
            "emitted_at": "2029-12-31T12:00:00Z",
        }

    assert props._persist_prop_pick(pick("Player A", 1), 100.0) is True
    # A second cycle evaluating the same selection (fresh prop_id) must not create another stake
    assert props._persist_prop_pick(pick("Player A", 2), 100.0) is False
    cap = load_config().risk.max_selections_per_matchday
    recorded = 1 + sum(props._persist_prop_pick(pick(f"Player {c}", 10 + i), 100.0) for i, c in enumerate("BCDEFG"))
    assert recorded == cap
    assert db.fetch_one("SELECT COUNT(*) AS c FROM player_prop_picks")["c"] == cap


# 8. Backtest mode is scoped to the walk-forward call (genuine historical games)
def test_backtester_does_not_leave_engine_in_backtest_mode(tmp_path: Path) -> None:
    import sqlite3

    db = DatabaseManager(tmp_path / "t.sqlite3")
    engine = PaperTradingEngine(db)
    bt = WalkForwardBacktester(db, engine, warmup_matchdays=4, retrain_every_matchdays=2)
    assert engine.is_backtest is False

    conn = sqlite3.connect("data/nba_intelligence.sqlite3")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT g.* FROM games g
        INNER JOIN (SELECT DISTINCT game_id FROM odds_snapshots) o ON g.game_id = o.game_id
        WHERE g.status = 'FINAL'
        ORDER BY g.game_start_time
        LIMIT 40
        """
    )
    games = [dict(r) for r in cur.fetchall()]
    game_ids = [g["game_id"] for g in games]
    placeholders = ",".join("?" for _ in game_ids)
    cur.execute(f"SELECT * FROM odds_snapshots WHERE game_id IN ({placeholders}) ORDER BY captured_at", game_ids)
    odds = [dict(r) for r in cur.fetchall()]
    conn.close()

    bt.run_walk_forward(games, odds)
    assert engine.is_backtest is False


# 9. Config is the single source of truth for the production cycle
def test_cloud_cycle_uses_configured_model_identity_and_anchor_weight() -> None:
    import scripts.run_cloud_cycle as cycle
    from src.config import load_config

    cfg = load_config()
    assert cycle.MODEL_VERSION_ID == cfg.model.version_id
    assert cycle.MARKET_ANCHOR_MODEL_WEIGHT == cfg.model.market_anchor_model_weight


# 10. Variable stake: grows with the model's probability for a given price, zero without edge
def test_fractional_kelly_stake_properties() -> None:
    from src.paper_trading.staking import fractional_kelly_stake

    odds = 1.90
    stakes = [fractional_kelly_stake(p, odds, 100.0) for p in (0.50, 0.55, 0.58, 0.62, 0.70)]
    assert stakes[0] == 0.0  # 0.50 * 1.90 < 1: negative EV -> no bet
    assert stakes[1:] == sorted(stakes[1:]) and stakes[2] > stakes[1]  # higher probability -> larger stake
    assert max(stakes) <= 3.00  # absolute cap
    assert fractional_kelly_stake(0.70, 1.90, 50.0) <= 1.50  # 3% of a S/50 bankroll
    assert fractional_kelly_stake(0.53, 1.90, 100.0) == 0.0  # tiny edge -> below S/0.50 minimum, skipped
    assert fractional_kelly_stake(0.66, 1.40, 100.0) == 0.0  # the old tiers staked S/4.80 here (EV -7.6%)


def test_engine_fractional_kelly_mode_places_variable_stake(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "t.sqlite3")
    _seed_game(db, game_id="G1", start="2030-01-01T00:00:00Z")
    db.execute_insert(
        "INSERT INTO model_versions (model_version_id, model_family, market, train_start_date, train_end_date, trained_at, "
        "hyperparameters_json, approved_by) VALUES ('m', 'f', 'moneyline', 'a', 'b', 'c', '{}', 'test')"
    )
    for pid in ("P_HI", "P_LO"):
        db.execute_insert(
            """
            INSERT INTO predictions (prediction_id, game_id, market, selection, model_version_id, raw_probability,
                calibrated_probability, uncertainty_std, implied_prob_gross, decimal_odds_used, odds_provider,
                odds_captured_at, ev_unit, ev_pct, emitted_at, features_snapshot_json)
            VALUES (?, 'G1', 'moneyline', 'HOME', 'm', 0.6, 0.6, 0.05, 0.5, 1.9, 'Pinnacle',
                    '2029-12-31T12:00:00Z', 0.1, 10.0, '2029-12-31T12:00:00Z', '{}')
            """,
            (pid,),
        )
    engine = PaperTradingEngine(db, base_stake_pen=1.0, max_stake_pen=3.0, staking_mode="FRACTIONAL_KELLY")

    def _cand(pid: str, prob: float) -> dict[str, Any]:
        ev = prob * 1.90 - 1.0
        return {
            "game_id": "G1", "market": "moneyline", "selection": "HOME", "line_value": None,
            "decimal_odds_used": 1.90, "calibrated_probability": prob, "ev_unit": ev, "ev_pct": 100 * ev,
            "model_version_id": "m", "prediction_id": pid, "emitted_at": "2029-12-31T12:00:00Z",
            "model_market_disagreement": 0.05, "max_model_market_disagreement": 0.15,
        }

    res = engine.evaluate_and_record_matchday_selections("2030-01-01", [_cand("P_HI", 0.60)])
    assert len(res["placed_bets"]) == 1
    stake = res["placed_bets"][0]["stake_pen"]
    assert stake == pytest.approx(min(3.0, 100.0 * min(0.03, 0.25 * (0.60 * 1.90 - 1) / 0.90)), abs=0.01)
    assert 1.0 < stake <= 3.0


# 11. Real-odds backtest pipeline mechanics with genuine historical data
def test_real_odds_backtest_pipeline_runs_walk_forward_without_lookahead() -> None:
    import sqlite3
    from pathlib import Path
    from src.backtesting.real_odds_backtest import load_market_rows, match_market_to_games, run_real_odds_backtest

    # 1. Genuine historical games from sqlite3 database
    db_path = Path("data/nba_intelligence.sqlite3")
    if not db_path.exists():
        db_path = Path(__file__).resolve().parent.parent / "data" / "nba_intelligence.sqlite3"
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM games WHERE season = '2024-25' AND status = 'FINAL' ORDER BY game_start_time LIMIT 220")
    games = [dict(r) for r in cur.fetchall()]
    conn.close()

    # 2. Genuine HuggingFace consensus market closing rows
    market_path = Path("data/raw/market_consensus_2024-25.csv")
    if not market_path.exists():
        market_path = Path(__file__).resolve().parent.parent / "data" / "raw" / "market_consensus_2024-25.csv"
    assert market_path.exists(), "Market consensus CSV must exist"
    market_rows = load_market_rows([market_path])

    matched = match_market_to_games(market_rows, games)
    assert len(matched) >= 200, "Should match at least 200 real games to consensus odds"

    # 3. Walk-forward backtest on genuine data without lookahead
    start_test_date = games[160]["matchday_date"]
    res = run_real_odds_backtest(games, market_rows, start_date=start_test_date, retrain_every_days=7)
    q = res.get("moneyline_quality", {})
    assert set(q) >= {"model_raw", "model_calibrated", "market_open", "market_close"}
    assert q["market_open"]["n"] > 0
    b = res["betting"]
    assert b["bets"] <= 3 * len({g["matchday_date"] for g in games})
    for bet in res["bets_sample"]:
        assert bet["ev_unit"] > 0.05 and bet["kelly_stake_pen"] <= 3.0


# 12. Box-score features are leakage-free and feed the ensemble adjustment
def _bx_game(i: int, home: str, away: str, hs: int, as_: int, status: str = "FINAL") -> dict[str, Any]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
    return {"game_id": f"ESPN_{1000 + i}_X_{away}_AT_{home}", "game_start_time": _iso(start), "home_team": home,
            "away_team": away, "status": status, "home_score": hs, "away_score": as_}


def _bx_box(home: str, away: str, star_plays: bool = True) -> dict[str, Any]:
    team = {"fgm": 42.0, "fga": 88.0, "tpm": 13.0, "tpa": 36.0, "ftm": 18.0, "fta": 22.0, "orb": 10.0, "drb": 34.0,
            "tov": 13.0, "pts": 115.0}
    roster = [{"name": f"{home}_P{k}", "min": 30.0, "pts": 15.0, "starter": True} for k in range(5)]
    if not star_plays:
        roster[0] = {**roster[0], "min": 0.0, "pts": 0.0}
    return {"teams": {home: dict(team), away: dict(team)},
            "players": {home: roster, away: [{"name": f"{away}_P{k}", "min": 30.0, "pts": 15.0, "starter": True} for k in range(5)]}}


def test_boxscore_features_use_only_earlier_games_and_flag_absences() -> None:
    from src.features.boxscore_features import compute_boxscore_features
    from src.ingestion.boxscores import parse_boxscore

    games = [_bx_game(i, "BOS", "NYK", 110, 100) for i in range(6)]
    boxes = {g["game_id"]: _bx_box("BOS", "NYK", star_plays=(i != 4)) for i, g in enumerate(games)}
    feats = compute_boxscore_features(games, boxes)
    assert feats[games[0]["game_id"]]["bx_min_games"] == 0.0  # nothing known before the first game
    # The star sat out game index 4 -> flagged as missing BEFORE game 5, not before game 4 (no lookahead)
    assert feats[games[4]["game_id"]]["bx_missing_pts_diff"] == 0.0
    assert feats[games[5]["game_id"]]["bx_missing_pts_diff"] < -10.0  # home team is missing ~15 pts
    assert feats[games[5]["game_id"]]["bx_new_absence_pts_diff"] < -10.0
    # Changing the LAST game's box score must not change its own pre-game features
    boxes2 = dict(boxes)
    boxes2[games[5]["game_id"]] = _bx_box("BOS", "NYK", star_plays=False)
    assert compute_boxscore_features(games, boxes2)[games[5]["game_id"]] == feats[games[5]["game_id"]]
    # With a 2-day information lag the absence in game 4 is not yet known before game 5
    assert compute_boxscore_features(games, boxes, info_lag_days=2)[games[5]["game_id"]]["bx_missing_pts_diff"] == 0.0

    parsed = parse_boxscore({"boxscore": {"teams": [
        {"team": {"abbreviation": ab}, "statistics": [
            {"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "40-90"},
            {"name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "displayValue": "10-30"},
            {"name": "freeThrowsMade-freeThrowsAttempted", "displayValue": "20-25"},
            {"name": "offensiveRebounds", "displayValue": "10"}, {"name": "defensiveRebounds", "displayValue": "33"},
            {"name": "totalTurnovers", "displayValue": "12"}]} for ab in ("BOS", "NY")],
        "players": [{"team": {"abbreviation": "BOS"}, "statistics": [{"labels": ["MIN", "PTS"], "athletes": [
            {"athlete": {"displayName": "A"}, "starter": True, "stats": ["35", "28"]},
            {"athlete": {"displayName": "B"}, "starter": False, "stats": []}]}]}]}})
    assert parsed is not None and parsed["teams"]["BOS"]["pts"] == 110.0 and set(parsed["teams"]) == {"BOS", "NYK"}
    assert parsed["players"]["BOS"][1]["min"] == 0.0  # DNP
