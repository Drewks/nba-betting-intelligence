"""
End-to-End Integration Test for Slate Intelligence and Dashboard Generation.
Verifies that:
1. compute_upcoming_slate_intelligence queries v_observed_odds_snapshots (not non-existent 'odds' table).
2. Aggregates best observed odds for moneyline and total points correctly.
3. Formats predictions and verdicts accurately for scheduled games.
4. export_bets_and_tracking_dashboard executes cleanly from end to end without crashing.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from src.reporting.slate_intelligence import compute_upcoming_slate_intelligence
from src.reporting.dashboard_export import export_bets_and_tracking_dashboard
from src.storage.db import DatabaseManager


@pytest.fixture
def e2e_db(tmp_path: Path) -> DatabaseManager:
    """Creates a temporary database initialized with standard schema and fixtures."""
    db_file = tmp_path / "test_slate_e2e.sqlite3"
    db = DatabaseManager(db_file)

    # Insert a finished game for feature building and model fitting
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, home_team, away_team, game_start_time, status,
            home_score, away_score, home_off_rtg, home_def_rtg, home_pace, away_off_rtg,
            away_def_rtg, away_pace, home_rest_days, away_rest_days,
            features_available_at, ingested_at, source_provider
        ) VALUES (
            'ESPN_PAST_001', '2026-27', '2026-11-08', 'BOS', 'MIA', '2026-11-08T19:00:00Z', 'FINAL',
            112, 104, 115.0, 110.0, 99.5, 111.0, 112.5, 98.0, 2, 2,
            '2026-11-08T18:00:00Z', '2026-11-08T18:00:00Z', 'ESPN'
        )
        """,
        (),
    )

    # Insert an upcoming scheduled game with essential features
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, home_team, away_team, game_start_time, status,
            home_off_rtg, home_def_rtg, home_pace, away_off_rtg, away_def_rtg, away_pace,
            home_rest_days, away_rest_days, features_available_at, ingested_at, source_provider
        ) VALUES (
            'ESPN_UPCOMING_001', '2026-27', '2026-11-12', 'LAL', 'DEN', '2026-11-12T22:30:00Z', 'SCHEDULED',
            114.2, 111.8, 100.2, 116.5, 113.0, 99.0, 2, 1,
            '2026-11-12T10:00:00Z', '2026-11-12T10:00:00Z', 'ESPN'
        )
        """,
        (),
    )

    # Insert observed moneyline and totals odds snapshots
    db.execute_insert(
        """
        INSERT INTO odds_snapshots (
            odds_id, game_id, market, selection, decimal_odds, counterpart_decimal_odds,
            provider, captured_at, source_type, is_closing_line
        ) VALUES
        ('ODD_ML_H', 'ESPN_UPCOMING_001', 'moneyline', 'HOME', 1.85, 2.05, 'Betano Perú', '2026-11-12T10:00:00Z', 'OBSERVED', 0),
        ('ODD_ML_A', 'ESPN_UPCOMING_001', 'moneyline', 'AWAY', 2.05, 1.85, 'Betano Perú', '2026-11-12T10:00:00Z', 'OBSERVED', 0),
        ('ODD_TOT_O', 'ESPN_UPCOMING_001', 'total_points', 'OVER', 1.92, 1.90, 'RETAbet Perú', '2026-11-12T10:00:00Z', 'OBSERVED', 0),
        ('ODD_TOT_U', 'ESPN_UPCOMING_001', 'total_points', 'UNDER', 1.90, 1.92, 'RETAbet Perú', '2026-11-12T10:00:00Z', 'OBSERVED', 0)
        """,
        (),
    )

    return db


def test_compute_upcoming_slate_intelligence_e2e(e2e_db: DatabaseManager) -> None:
    """Verifies that compute_upcoming_slate_intelligence executes with zero SQL errors."""
    slate = compute_upcoming_slate_intelligence(e2e_db)
    assert len(slate) == 1

    item = slate[0]
    assert item["game_id"] == "ESPN_UPCOMING_001"
    assert item["home_team_code"] == "LAL"
    assert item["away_team_code"] == "DEN"

    odds = item["odds"]
    assert odds["home_odds"] == 1.85
    assert odds["away_odds"] == 2.05
    assert odds["over_odds"] == 1.92
    assert odds["under_odds"] == 1.90

    proj = item["projections"]
    assert "p_home_pct" in proj
    assert "p_away_pct" in proj
    assert "expected_total" in proj
    assert "expected_margin" in proj

    assert item["verdict_status"] in ("PENDING_BET", "NO_BET")


def test_export_bets_and_tracking_dashboard_e2e(e2e_db: DatabaseManager, tmp_path: Path) -> None:
    """Verifies full export of bets, slate intelligence, markdown and CSV dashboards."""
    csv_file = tmp_path / "apuestas_historial.csv"
    md_file = tmp_path / "SEGUIMIENTO_APUESTAS.md"

    metrics = {
        "status": "HEALTHY",
        "current_settled_bankroll_pen": 100.0,
        "settled_bankroll_pen": 100.0,
        "net_profit_pen": 0.0,
        "daily_pnl_pen": 0.0,
        "active_bets_count": 0,
        "roi_pct": 0.0,
        "yield_pct": 0.0,
        "clv_mean_roi_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "brier_score_model_f": 0.21,
        "brier_score_market_anchor": 0.21,
        "expected_calibration_error": 0.03,
        "total_simulated_bets": 0,
        "settled_bets_count": 0,
        "won_bets_count": 0,
        "lost_bets_count": 0,
    }

    result = export_bets_and_tracking_dashboard(
        db=e2e_db,
        metrics=metrics,
        csv_output_path=csv_file,
        md_output_path=md_file,
    )

    assert Path(result["csv_path"]).exists()
    assert Path(result["md_path"]).exists()

    md_content = Path(result["md_path"]).read_text(encoding="utf-8")
    assert "LAL" in md_content or "DEN" in md_content or "SEGUIMIENTO" in md_content
