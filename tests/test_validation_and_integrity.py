"""
Data Validation, Anti-Leakage, Temporal Split and Integrity Regressions Tests (`tests/test_validation_and_integrity.py`).
Modular test suite extracted from legacy test_nba_intelligence monolith.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest

from src.backtesting.backtester import WalkForwardBacktester
from src.calibration.calibrator import ProbabilityCalibrator
from src.ingestion.adapters import (
    AdapterUnavailableError,
    BaseNBADataAdapter,
    DataSourceRouter,
)
from src.paper_trading.engine import PaperTradingEngine
from src.storage.db import DatabaseManager
from src.validation.validator import (
    DataValidationError,
    TemporalLeakageError,
    detect_duplicates,
    validate_game_record,
    validate_odds_record,
    validate_temporal_split,
)
from tests.helpers import _seed_sample_game_and_prediction



# 9. Detección de datos futuros
def test_09_detect_future_data_leakage() -> None:
    with pytest.raises(TemporalLeakageError):
        validate_game_record(
            {
                "game_id": "G_LEAK",
                "season": "2026-27",
                "matchday_date": "2026-10-20",
                "game_start_time": "2026-10-20T23:00:00Z",
                "home_team": "BOS",
                "away_team": "MIA",
                "status": "SCHEDULED",
                "features_available_at": "2026-10-20T23:30:00Z",  # After tipoff!
                "source_provider": "test",
            }
        )
    with pytest.raises(TemporalLeakageError):
        validate_odds_record(
            {
                "game_id": "G_LEAK",
                "provider": "TestBook",
                "market": "moneyline",
                "selection": "HOME",
                "decimal_odds": 1.95,
                "captured_at": "2026-10-20T23:05:00Z",  # Post-tipoff odds!
            },
            game_start_time="2026-10-20T23:00:00Z",
        )


# 10. Separación temporal de entrenamiento y evaluación
def test_10_temporal_train_eval_separation() -> None:
    train_games = [{"game_id": "G1", "game_start_time": "2026-10-10T23:00:00Z"}]
    eval_games_valid = [{"game_id": "G2", "game_start_time": "2026-10-11T23:00:00Z"}]
    validate_temporal_split(train_games, eval_games_valid)

    eval_games_overlapping = [{"game_id": "G3", "game_start_time": "2026-10-09T23:00:00Z"}]
    with pytest.raises(TemporalLeakageError):
        validate_temporal_split(train_games, eval_games_overlapping)


# 11. Reproducción de resultados históricos con datos genuinos
def test_11_historical_reproducibility(tmp_path: Path) -> None:
    conn = sqlite3.connect("data/nba_intelligence.sqlite3")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT g.* FROM games g
        INNER JOIN (SELECT DISTINCT game_id FROM odds_snapshots) o ON g.game_id = o.game_id
        WHERE g.status = 'FINAL'
        ORDER BY g.game_start_time
        LIMIT 50
        """
    )
    games = [dict(r) for r in cur.fetchall()]
    game_ids = [g["game_id"] for g in games]
    placeholders = ",".join("?" for _ in game_ids)
    cur.execute(f"SELECT * FROM odds_snapshots WHERE game_id IN ({placeholders}) ORDER BY captured_at", game_ids)
    odds = [dict(r) for r in cur.fetchall()]
    conn.close()

    db1 = DatabaseManager(tmp_path / "repro1.sqlite3")
    bt1 = WalkForwardBacktester(db1, PaperTradingEngine(db1), warmup_matchdays=5, retrain_every_matchdays=3)
    res1 = bt1.run_walk_forward(games, odds)

    db2 = DatabaseManager(tmp_path / "repro2.sqlite3")
    bt2 = WalkForwardBacktester(db2, PaperTradingEngine(db2), warmup_matchdays=5, retrain_every_matchdays=3)
    res2 = bt2.run_walk_forward(games, odds)

    assert res1["net_profit_pen"] == res2["net_profit_pen"]
    assert res1["roi_pct"] == res2["roi_pct"]
    assert res1["overall_brier_score"] == res2["overall_brier_score"]


# 13. Recalibración sin fuga de información
def test_13_recalibration_without_data_leakage() -> None:
    cal = ProbabilityCalibrator(method="logistic", min_samples_logistic=5)
    leaked_records = [
        {
            "game_start_time": "2026-10-25T23:00:00Z",
            "raw_probability": 0.60,
            "outcome": 1,
        }
    ]
    with pytest.raises(TemporalLeakageError):
        cal.fit(leaked_records, calibration_cutoff_time="2026-10-20T00:00:00Z")

    valid_records = [
        {
            "game_start_time": f"2026-10-{day:02d}T23:00:00Z",
            "raw_probability": 0.35 if day % 2 == 0 else 0.70,
            "outcome": 0 if day % 2 == 0 else 1,
        }
        for day in range(1, 15)
    ]
    method_used = cal.fit(valid_records, calibration_cutoff_time="2026-10-20T00:00:00Z")
    assert method_used == "logistic"
    transformed = cal.transform_single(0.65)
    assert 0.03 <= transformed <= 0.97


# 14. Recuperación ante fallos de una fuente (con adaptador de datos históricos genuinos)
def test_14_source_failover_recovery() -> None:
    class FailingAdapter(BaseNBADataAdapter):
        provider_name = "failing_primary_source"

        def fetch_games_and_odds(self, date_str=None, as_of_utc=None):
            raise AdapterUnavailableError("Simulated timeout on primary source")

    class LocalHistoricalAdapter(BaseNBADataAdapter):
        provider_name = "local_historical_db"

        def fetch_games_and_odds(self, date_str=None, as_of_utc=None):
            conn = sqlite3.connect("data/nba_intelligence.sqlite3")
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM games WHERE status = 'FINAL' ORDER BY game_start_time LIMIT 10")
            games = [dict(r) for r in cur.fetchall()]
            conn.close()
            return {"games": games, "odds": []}

    fallback_adapter = LocalHistoricalAdapter()
    router = DataSourceRouter([FailingAdapter(), fallback_adapter])
    res = router.fetch_with_failover()
    assert res["active_provider"] == fallback_adapter.provider_name
    assert len(res["failover_events"]) == 1
    assert len(res["games"]) == 10


# 15. Detección de duplicados
def test_15_duplicate_detection_in_data_and_bets(tmp_path: Path) -> None:
    records = [
        {"game_id": "G1", "market": "moneyline"},
        {"game_id": "G2", "market": "moneyline"},
        {"game_id": "G1", "market": "moneyline"},
    ]
    dups = detect_duplicates(records, ("game_id", "market"))
    assert dups == [("G1", "moneyline")]

    db = DatabaseManager(tmp_path / "test_dup_bets.sqlite3")
    engine = PaperTradingEngine(db, initial_bankroll_pen=100.00)
    pred_id = _seed_sample_game_and_prediction(db, "G_DUP")
    cand = {
        "prediction_id": pred_id,
        "game_id": "G_DUP",
        "market": "moneyline",
        "selection": "HOME",
        "line_value": None,
        "decimal_odds_used": 2.10,
        "calibrated_probability": 0.52,
        "ev_unit": 0.092,
        "ev_pct": 9.2,
        "model_version_id": "model_c_test_v1",
        "emitted_at": "2026-10-20T20:00:00Z",
    }
    first_run = engine.evaluate_and_record_matchday_selections("2026-10-20", [cand])
    second_run = engine.evaluate_and_record_matchday_selections("2026-10-20", [cand])
    assert len(first_run["placed_bets"]) == 1
    assert len(second_run["placed_bets"]) == 0
    assert second_run["no_bet_decisions"][0]["reason_code"] == "DUPLICATE_SELECTION"


# 23. Persistencia Automática de Cuotas de Cierre (Closing Lines) Pre-Tipoff y Modos de Ciclo
def test_23_persist_closing_lines_and_cycle_modes(tmp_path: Path) -> None:
    from src.paper_trading.engine import PaperTradingEngine
    from src.storage.db import DatabaseManager

    db = DatabaseManager(tmp_path / "test_p23.sqlite3")
    engine = PaperTradingEngine(
        db=db,
        initial_bankroll_pen=100.00,
        base_stake_pen=1.00,
        max_stake_pen=6.00,
        dynamic_conviction_staking=True,
        exclude_synthetic=True,
    )

    # 1. Seed a scheduled real game starting in 20 minutes
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
            away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
            features_available_at, source_provider, ingested_at
        ) VALUES (
            'REAL_GAME_TIPOFF', '2026-27', '2026-10-25', '2026-10-25T20:00:00Z', 'GSW', 'LAL',
            'SCHEDULED', NULL, NULL, 115.0, 112.0, 100.0, 114.0, 113.0, 99.0, 2, 2,
            '2026-10-25T18:00:00Z', 'espn_real', '2026-10-25T18:00:00Z'
        )
        """
    )
    # Insert open odds captured pre-tipoff
    db.execute_insert(
        """
        INSERT INTO odds_snapshots (
            odds_id, game_id, provider, market, selection, line_value, decimal_odds,
            captured_at, is_closing_line, source_type
        ) VALUES ('ODDS_TIPOFF_HOME', 'REAL_GAME_TIPOFF', 'Pinnacle', 'moneyline', 'HOME', NULL, 1.95, '2026-10-25T19:40:00Z', 0, 'OBSERVED')
        """
    )

    # Run persist_closing_lines_for_games as of 19:45 UTC (15 min before tipoff)
    promoted = engine.persist_closing_lines_for_games(as_of_utc="2026-10-25T19:45:00Z")
    assert promoted == 1

    # Verify that a closing line row now exists with is_closing_line = 1
    closing_row = db.fetch_one(
        "SELECT * FROM odds_snapshots WHERE game_id = 'REAL_GAME_TIPOFF' AND is_closing_line = 1"
    )
    assert closing_row is not None
    assert closing_row["odds_id"] == "ODDS_TIPOFF_HOME_CLOSE"
    assert float(closing_row["decimal_odds"]) == 1.95
    assert closing_row["captured_at"] == "2026-10-25T19:40:00Z"


def test_42_data_integrity_and_dynamic_roster_audit(tmp_path: Path) -> None:
    """
    Test 42: Data Integrity, Tipoff Timing Guards & Dynamic NBA Roster Verification:
    1. Rejection of candidate bets on nonexistent games (NONEXISTENT_GAME).
    2. Rejection of candidate bets on already completed/non-scheduled games (GAME_NOT_SCHEDULED).
    3. Rejection of candidate bets emitted post-tipoff (GAME_ALREADY_STARTED).
    4. Rejection of player props assigned to incorrect NBA franchises (Roster Integrity Violation).
    5. Rejection of player props emitted post-tipoff when enforce_scheduled_status=True.
    6. Dynamic ESPN roster synchronization and team lookup.
    """
    import pytest
    from src.ingestion.roster_manager import ensure_roster_table, get_player_team
    from src.paper_trading.engine import PaperTradingEngine
    from src.storage.db import DatabaseManager
    from src.validation.validator import TemporalLeakageError

    db = DatabaseManager(tmp_path / "test_audit_42.sqlite3")
    engine = PaperTradingEngine(db=db, initial_bankroll_pen=100.0)

    # Seed sample game with start time 2026-11-10T00:00:00Z
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, home_score, away_score, features_available_at, source_provider, ingested_at
        ) VALUES ('G_FUTURE_01', '2026-27', '2026-11-10', '2026-11-10T00:00:00Z', 'LAL', 'BOS',
                  'SCHEDULED', NULL, NULL, '2026-11-09T22:00:00Z', 'ESPN', '2026-11-09T22:00:00Z')
        """
    )
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, home_score, away_score, features_available_at, source_provider, ingested_at
        ) VALUES ('G_FINAL_01', '2026-27', '2026-11-08', '2026-11-08T00:00:00Z', 'DEN', 'MIA',
                  'FINAL', 110, 105, '2026-11-07T22:00:00Z', 'ESPN', '2026-11-07T22:00:00Z')
        """
    )

    # 1. Nonexistent game rejection
    res_nonexistent = engine.evaluate_and_record_matchday_selections(
        matchday_date="2026-11-10",
        candidate_predictions=[
            {
                "prediction_id": "PRED_FAKE",
                "game_id": "G_PHANTOM_999",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 1.95,
                "calibrated_probability": 0.60,
                "ev_unit": 0.17,
                "ev_pct": 17.0,
                "model_version_id": "model_test",
                "emitted_at": "2026-11-09T23:00:00Z",
            }
        ],
    )
    assert len(res_nonexistent["placed_bets"]) == 0
    assert len(res_nonexistent["no_bet_decisions"]) == 1
    assert res_nonexistent["no_bet_decisions"][0]["reason_code"] == "NONEXISTENT_GAME"

    # 2. Non-scheduled game rejection (e.g. FINAL)
    res_final = engine.evaluate_and_record_matchday_selections(
        matchday_date="2026-11-08",
        candidate_predictions=[
            {
                "prediction_id": "PRED_PAST",
                "game_id": "G_FINAL_01",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 1.95,
                "calibrated_probability": 0.60,
                "ev_unit": 0.17,
                "ev_pct": 17.0,
                "model_version_id": "model_test",
                "emitted_at": "2026-11-07T23:00:00Z",
            }
        ],
    )
    assert len(res_final["placed_bets"]) == 0
    assert len(res_final["no_bet_decisions"]) == 1
    assert res_final["no_bet_decisions"][0]["reason_code"] == "GAME_NOT_SCHEDULED"

    # 3. Post-tipoff bet rejection (temporal leakage)
    res_late = engine.evaluate_and_record_matchday_selections(
        matchday_date="2026-11-10",
        candidate_predictions=[
            {
                "prediction_id": "PRED_LATE",
                "game_id": "G_FUTURE_01",
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 1.95,
                "calibrated_probability": 0.60,
                "ev_unit": 0.17,
                "ev_pct": 17.0,
                "model_version_id": "model_test",
                "emitted_at": "2026-11-10T00:05:00Z",  # 5 mins after tipoff!
            }
        ],
    )
    assert len(res_late["placed_bets"]) == 0
    assert len(res_late["no_bet_decisions"]) == 1
    assert res_late["no_bet_decisions"][0]["reason_code"] == "GAME_ALREADY_STARTED"

    # 4. Dynamic Roster Verification & Trade Resolution
    ensure_roster_table(db)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO team_rosters (team_id, player_name, position, is_active, updated_at) VALUES ('LAL', 'Luka Doncic', 'PG', 1, '2026-11-08T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO team_rosters (team_id, player_name, position, is_active, updated_at) VALUES ('BOS', 'Paul George', 'SF', 1, '2026-11-08T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO team_rosters (team_id, player_name, position, is_active, updated_at) VALUES ('DAL', 'Kyrie Irving', 'PG', 1, '2026-11-08T00:00:00Z')"
        )

    # Luka Doncic is on LAL, not DAL!
    assert get_player_team(db, "Luka Doncic") == "LAL"
    assert get_player_team(db, "Paul George") == "BOS"

    # Attempting to record a prop for Luka on DAL should be rejected
    with pytest.raises(DataValidationError, match="Roster integrity violation"):
        engine.record_player_prop_pick({
            "game_id": "G_FUTURE_01",
            "matchday_date": "2026-11-10",
            "player_name": "Luka Doncic",
            "team": "DAL",  # Wrong team!
            "prop_category": "PTS",
            "line_value": 28.5,
            "selection": "OVER",
            "decimal_odds": 1.90,
            "model_prob": 0.58,
        })

    # Recording on correct team (LAL) succeeds
    p_valid_id = engine.record_player_prop_pick({
        "game_id": "G_FUTURE_01",
        "matchday_date": "2026-11-10",
        "player_name": "Luka Doncic",
        "team": "LAL",  # Correct team!
        "prop_category": "PTS",
        "line_value": 28.5,
        "selection": "OVER",
        "decimal_odds": 1.90,
        "model_prob": 0.58,
        "emitted_at": "2026-11-09T23:30:00Z",
    })
    assert p_valid_id.startswith("PROP_")

    # 5. Temporal Leakage on Props (enforce_scheduled_status=True)
    with pytest.raises(TemporalLeakageError, match="Temporal leakage violation"):
        engine.record_player_prop_pick(
            {
                "game_id": "G_FUTURE_01",
                "matchday_date": "2026-11-10",
                "player_name": "Luka Doncic",
                "team": "LAL",
                "prop_category": "PTS",
                "line_value": 28.5,
                "selection": "OVER",
                "decimal_odds": 1.90,
                "model_prob": 0.58,
                "emitted_at": "2026-11-10T00:10:00Z",  # 10 mins post-tipoff!
            },
            enforce_scheduled_status=True,
        )
