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
import re
import pytest

from src.backtesting.backtester import (
    WalkForwardBacktester,
    compute_financial_and_statistical_metrics,
)
from src.config import load_config
from src.paper_trading.engine import PaperTradingEngine, build_production_engine
from src.reporting.dashboard_export import (
    export_bets_and_tracking_dashboard,
    generate_bet_tracking_markdown,
)
from src.reporting.markdown_Panopticon import (
    generate_bet_tracking_markdown as panopticon_generate_bet_tracking_markdown,
)
from src.reporting.slate_intelligence import (
    compute_upcoming_slate_intelligence,
    generate_slate_intelligence_markdown,
)
from src.storage.db import DatabaseManager
from tests.helpers import copy_prod_db


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

    slate_md = generate_slate_intelligence_markdown(e2e_db)
    assert "Cartelera Completa de Próximos Partidos" in slate_md
    assert "LAL" in slate_md or "Los Angeles Lakers" in slate_md


def test_e2e_production_cycle_and_bankroll_reconciliation(tmp_path: Path) -> None:
    """
    Comprehensive End-to-End Production Cycle & Reconciliation Test on a temporary copy
    of `data/nba_intelligence.sqlite3`:
      a) `generate_slate_intelligence_markdown` & `compute_upcoming_slate_intelligence`
         — catching any `no such table: odds` bug.
      b) `PaperTradingEngine.get_bankroll_state()` vs `WalkForwardBacktester.compute_comprehensive_metrics()`
         — asserting `settled_bankroll_pen == current_settled_bankroll_pen` and
         `settled_bets_count == settled_bets_count` (preventing the two-bankrolls bug from ever regressing).
      c) `persist_closing_lines_for_games` with both `Z` and `+00:00` ISO timestamps.
      d) `generate_bet_tracking_markdown` / `export_bets_and_tracking_dashboard`
         — asserting no `VOID` rows appear in the settled props table and the Section 3
         running bankroll matches the header settled bankroll.
    """
    db_file = copy_prod_db(tmp_path, "prod_cycle_reconciliation.sqlite3")
    db = DatabaseManager(db_file)
    engine = build_production_engine(db)

    # (b) Bankroll & Settled Count Single-Source-of-Truth Reconciliation
    bankroll_state = engine.get_bankroll_state()
    default_engine_state = PaperTradingEngine(db, exclude_synthetic=True).get_bankroll_state()
    bt = WalkForwardBacktester(db, engine)
    metrics = bt.compute_comprehensive_metrics()
    fin_metrics = compute_financial_and_statistical_metrics(db, engine)

    assert round(bankroll_state["settled_bankroll_pen"], 2) == round(metrics["current_settled_bankroll_pen"], 2)
    assert round(bankroll_state["settled_bankroll_pen"], 2) == round(fin_metrics["current_settled_bankroll_pen"], 2)
    assert round(default_engine_state["settled_bankroll_pen"], 2) == round(metrics["current_settled_bankroll_pen"], 2)
    assert bankroll_state["settled_bets_count"] == metrics["settled_bets_count"]
    assert bankroll_state["settled_bets_count"] == fin_metrics["settled_bets_count"]
    assert round(bankroll_state["cumulative_net_profit_pen"], 2) == round(metrics["net_profit_pen"], 2)
    # The live bankroll changes every time a bet settles, so it is reconciled against the ledger
    # (independent recomputation from v_observed_simulated_bets) instead of a hard-coded value.
    ledger_row = db.fetch_one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(net_profit_pen), 0.0) AS pnl FROM v_observed_simulated_bets "
        "WHERE status IN ('WON', 'LOST', 'PUSH', 'VOID')"
    )
    expected_bankroll = round(engine.initial_bankroll_pen + float(ledger_row["pnl"]), 2)
    assert round(metrics["current_settled_bankroll_pen"], 2) == expected_bankroll
    assert metrics["settled_bets_count"] == int(ledger_row["n"])

    # (a) Slate Intelligence on realistic production DB + upcoming scheduled game
    db.execute_insert(
        """
        INSERT OR IGNORE INTO games (
            game_id, season, matchday_date, home_team, away_team, game_start_time, status,
            home_off_rtg, home_def_rtg, home_pace, away_off_rtg, away_def_rtg, away_pace,
            home_rest_days, away_rest_days, features_available_at, ingested_at, source_provider
        ) VALUES (
            'ESPN_E2E_UPCOMING_999', '2026-27', '2026-11-15', 'BOS', 'NYK', '2026-11-15T00:30:00Z', 'SCHEDULED',
            117.2, 109.5, 99.8, 114.8, 111.2, 98.4, 2, 1,
            '2026-11-14T12:00:00Z', '2026-11-14T12:00:00Z', 'ESPN'
        )
        """
    )
    db.execute_insert(
        """
        INSERT OR IGNORE INTO odds_snapshots (
            odds_id, game_id, market, selection, line_value, decimal_odds, counterpart_decimal_odds,
            provider, captured_at, source_type, is_closing_line
        ) VALUES
        ('E2E_UP_ML_H', 'ESPN_E2E_UPCOMING_999', 'moneyline', 'HOME', NULL, 1.62, 2.35, 'Pinnacle', '2026-11-14T14:00:00Z', 'OBSERVED', 0),
        ('E2E_UP_ML_A', 'ESPN_E2E_UPCOMING_999', 'moneyline', 'AWAY', NULL, 2.35, 1.62, 'Pinnacle', '2026-11-14T14:00:00Z', 'OBSERVED', 0),
        ('E2E_UP_TOT_O', 'ESPN_E2E_UPCOMING_999', 'total_points', 'OVER', 224.5, 1.91, 1.91, 'Te Apuesto Perú', '2026-11-14T14:00:00+00:00', 'OBSERVED', 0),
        ('E2E_UP_TOT_U', 'ESPN_E2E_UPCOMING_999', 'total_points', 'UNDER', 224.5, 1.91, 1.91, 'Te Apuesto Perú', '2026-11-14T14:00:00+00:00', 'OBSERVED', 0)
        """
    )

    slate_items = compute_upcoming_slate_intelligence(db)
    assert len(slate_items) >= 1
    slate_md = generate_slate_intelligence_markdown(db)
    assert "Cartelera Completa de Próximos Partidos" in slate_md
    assert "Boston Celtics" in slate_md or "BOS" in slate_md

    # (c) Closing Line Persistence with mixed 'Z' and '+00:00' ISO timestamps
    db.execute_insert(
        """
        INSERT OR IGNORE INTO games (
            game_id, season, matchday_date, home_team, away_team, game_start_time, status,
            home_score, away_score, home_off_rtg, home_def_rtg, home_pace, away_off_rtg, away_def_rtg, away_pace,
            home_rest_days, away_rest_days, features_available_at, ingested_at, source_provider
        ) VALUES
        ('ESPN_TZ_Z_001', '2026-27', '2026-11-12', 'LAL', 'MEM', '2026-11-12T22:00:00Z', 'FINAL',
         118, 110, 114.0, 112.0, 100.0, 112.0, 113.0, 99.5, 2, 2, '2026-11-12T10:00:00Z', '2026-11-12T10:00:00Z', 'ESPN'),
        ('ESPN_TZ_OFFSET_002', '2026-27', '2026-11-12', 'MIA', 'PHI', '2026-11-12T22:00:00+00:00', 'FINAL',
         106, 104, 112.0, 110.0, 97.5, 111.0, 111.5, 98.0, 1, 2, '2026-11-12T10:00:00+00:00', '2026-11-12T10:00:00+00:00', 'ESPN')
        """
    )
    db.execute_insert(
        """
        INSERT OR IGNORE INTO odds_snapshots (
            odds_id, game_id, market, selection, line_value, decimal_odds, counterpart_decimal_odds,
            provider, captured_at, source_type, is_closing_line
        ) VALUES
        -- Game 1 (tipoff 22:00:00Z): earlier Z snapshot at 19:00Z, later +00:00 snapshot at 21:30+00:00, and post-tipoff at 22:10+00:00
        ('TZ1_DK_ML_H_EARLY', 'ESPN_TZ_Z_001', 'moneyline', 'HOME', NULL, 1.80, 2.05, 'DraftKings', '2026-11-12T19:00:00Z', 'OBSERVED', 0),
        ('TZ1_DK_ML_H_LATE', 'ESPN_TZ_Z_001', 'moneyline', 'HOME', NULL, 1.74, 2.15, 'DraftKings', '2026-11-12T21:30:00+00:00', 'OBSERVED', 0),
        ('TZ1_PIN_TOT_O', 'ESPN_TZ_Z_001', 'total_points', 'OVER', 226.5, 1.93, 1.89, 'Pinnacle', '2026-11-12T21:45:00Z', 'OBSERVED', 0),
        ('TZ1_POST_TIP', 'ESPN_TZ_Z_001', 'moneyline', 'HOME', NULL, 1.30, 3.40, 'DraftKings', '2026-11-12T22:10:00+00:00', 'OBSERVED', 0),
        -- Game 2 (tipoff 22:00:00+00:00): earlier +00:00 snapshot at 19:00+00:00, later Z snapshot at 21:30Z, and post-tipoff at 22:05Z
        ('TZ2_DK_ML_H_EARLY', 'ESPN_TZ_OFFSET_002', 'moneyline', 'HOME', NULL, 1.95, 1.90, 'DraftKings', '2026-11-12T19:00:00+00:00', 'OBSERVED', 0),
        ('TZ2_DK_ML_H_LATE', 'ESPN_TZ_OFFSET_002', 'moneyline', 'HOME', NULL, 1.88, 1.96, 'DraftKings', '2026-11-12T21:30:00Z', 'OBSERVED', 0),
        ('TZ2_POST_TIP', 'ESPN_TZ_OFFSET_002', 'moneyline', 'HOME', NULL, 1.25, 3.80, 'DraftKings', '2026-11-12T22:05:00Z', 'OBSERVED', 0)
        """
    )

    promoted_count = engine.persist_closing_lines_for_games("2026-11-13T04:00:00Z")
    assert promoted_count >= 3

    g1_closes = db.fetch_all(
        "SELECT odds_id, provider, market, decimal_odds, captured_at FROM v_observed_odds_snapshots WHERE game_id = 'ESPN_TZ_Z_001' AND is_closing_line = 1"
    )
    g1_by_prov_mkt = {(r["provider"], r["market"]): r for r in g1_closes}
    assert ("DraftKings", "moneyline") in g1_by_prov_mkt
    assert g1_by_prov_mkt[("DraftKings", "moneyline")]["decimal_odds"] == pytest.approx(1.74)
    assert ("Pinnacle", "total_points") in g1_by_prov_mkt
    assert g1_by_prov_mkt[("Pinnacle", "total_points")]["decimal_odds"] == pytest.approx(1.93)

    g2_closes = db.fetch_all(
        "SELECT odds_id, provider, market, decimal_odds, captured_at FROM v_observed_odds_snapshots WHERE game_id = 'ESPN_TZ_OFFSET_002' AND is_closing_line = 1"
    )
    assert len(g2_closes) == 1
    assert g2_closes[0]["decimal_odds"] == pytest.approx(1.88)

    # (d) Bet Tracking Markdown (SEGUIMIENTO_APUESTAS.md): zero VOID rows in settled props table & Section 3 bankroll matches header
    assert panopticon_generate_bet_tracking_markdown is generate_bet_tracking_markdown
    md_text = panopticon_generate_bet_tracking_markdown(db, metrics)
    assert f"**Bankroll Liquidado Actual**: **`S/{expected_bankroll:.2f} PEN`**" in md_text

    # Extract Section 3 table rows and verify latest settled bet's Bankroll Post. matches the header bankroll
    sec3_match = re.search(
        r"## 📊 3\. Últimas 20 Apuestas Liquidadas.*?\n((?:\|.*?\n)+)",
        md_text,
        flags=re.DOTALL,
    )
    assert sec3_match is not None, "Section 3 table must be present in SEGUIMIENTO_APUESTAS.md"
    sec3_rows = [
        line.strip()
        for line in sec3_match.group(1).strip().splitlines()
        if line.strip().startswith("| `BET_")
    ]
    assert len(sec3_rows) >= 1
    assert f"`S/{expected_bankroll:.2f}`" in sec3_rows[0], (
        f"Expected latest Section 3 row to end with `S/{expected_bankroll:.2f}`, got: {sec3_rows[0]}"
    )

    # Extract Section 4 settled props table and verify NO VOID rows appear
    if "### 📜 Últimas Apuestas de Props Liquidadas" in md_text:
        props_table_part = md_text.split("### 📜 Últimas Apuestas de Props Liquidadas", 1)[1]
        for line in props_table_part.splitlines():
            if line.strip().startswith("|"):
                assert "| VOID |" not in line, f"VOID prop row leaked into settled props table: {line}"


def test_real_odds_backtest_script_kelly_config_and_zero_leakage(tmp_path: Path) -> None:
    """
    Audits `scripts/run_real_odds_backtest.py`:
    1. Reads active `kelly_fraction` from `config/model_config.yaml` via `load_config()`.
    2. Dynamically labels the exact simulated Kelly fraction and stake caps in Markdown
       (never mislabeling 25% vs 50%).
    3. Loads real FINAL games and real boxscores via `_ReadOnlyDBAdapter` without mutating SQLite.
    4. Enforces zero lookahead leakage via `verify_zero_lookahead_leakage`.
    """
    from scripts.run_real_odds_backtest import (
        _ReadOnlyDBAdapter,
        enrich_backtest_result_metadata,
        fetch_observed_final_games,
        render_configured_markdown,
        verify_zero_lookahead_leakage,
    )
    from src.ingestion.boxscores import load_boxscores

    load_config.cache_clear()
    cfg = load_config()
    db_file = copy_prod_db(tmp_path, "ro_backtest_audit.sqlite3")
    ro_db = _ReadOnlyDBAdapter(db_file)

    games = fetch_observed_final_games(ro_db)
    assert len(games) >= 200
    assert all(g["status"] == "FINAL" and not str(g["game_id"]).startswith("SYN") for g in games)

    boxscores = load_boxscores(ro_db)
    assert len(boxscores) > 0, "Real boxscores must be loaded from game_boxscores table"

    dummy_result = {
        "generated_at_utc": "2026-11-14T12:00:00Z",
        "data_attribution": "HuggingFace minmaxxxer CC BY 4.0",
        "config": {
            "start_date": "2025-01-01",
            "end_date": "2025-04-15",
            "test_games": 250,
            "vig_assumption": 0.045,
            "model_weight": cfg.model.market_anchor_model_weight,
            "min_ev": cfg.risk.min_ev_threshold,
            "max_bets_per_day": cfg.risk.max_selections_per_matchday,
            "retrain_every_days": 7,
            "history_lag_days": 0,
            "boxscore_features": True,
            "kelly": {
                "fraction": cfg.risk.kelly_fraction,
                "min_stake": cfg.risk.min_stake_pen,
                "max_stake": cfg.risk.max_stake_pen,
                "max_bankroll_fraction": cfg.risk.max_stake_bankroll_fraction,
            },
        },
        "moneyline_quality": {
            "model_raw": {"n": 250, "brier": 0.21, "log_loss": 0.61},
            "model_calibrated": {"n": 250, "brier": 0.20, "log_loss": 0.59},
            "market_open": {"n": 250, "brier": 0.20, "log_loss": 0.59},
            "market_close": {"n": 250, "brier": 0.19, "log_loss": 0.58},
        },
        "totals_quality_at_open_line": {
            "model_raw": {"n": 250, "brier": 0.24, "log_loss": 0.68},
            "model_calibrated": {"n": 250, "brier": 0.24, "log_loss": 0.68},
        },
        "betting": {
            "bets": 2,
            "settled": 2,
            "won": 1,
            "push_or_void": 0,
            "flat_stake": {
                "net_profit_pen": 0.1,
                "roi_pct": 5.0,
                "bootstrap_95": {"roi_ci_lower_95_pct": -10.0, "roi_ci_upper_95_pct": 20.0},
                "drawdown": {"max_drawdown_pct": 1.0},
            },
            "kelly_stake": {
                "final_bankroll_pen": 100.2,
                "net_profit_pen": 0.2,
                "total_staked_pen": 3.0,
                "roi_pct": 6.67,
                "mean_stake_pen": 1.5,
                "drawdown": {"max_drawdown_pct": 1.2},
            },
            "clv": {
                "mean_clv_ev_pct": 0.8,
                "beat_close_rate": 0.5,
                "bootstrap_95_pct": {"lower": -1.0, "upper": 2.5},
            },
            "by_market": {},
            "by_season": {},
        },
        "bets": [
            {"matchday_date": "2025-01-10", "game_id": games[-1]["game_id"]},
        ],
        "bets_sample": [],
    }

    assert verify_zero_lookahead_leakage(games, dummy_result, start_date="2025-01-01") is True

    # Verify active config kelly_fraction is labeled accurately
    enrich_backtest_result_metadata(
        dummy_result,
        kelly_fraction=cfg.risk.kelly_fraction,
        kelly_min_stake=cfg.risk.min_stake_pen,
        kelly_max_stake=cfg.risk.max_stake_pen,
        kelly_max_fraction=cfg.risk.max_stake_bankroll_fraction,
        boxscores_count=len(boxscores),
        zero_lookahead_verified=True,
    )
    md_active = render_configured_markdown(dummy_result)
    expected_kelly_pct = f"{cfg.risk.kelly_fraction * 100:.0f}%"
    assert f"Stake Kelly {expected_kelly_pct}" in md_active
    assert f"S/{cfg.risk.min_stake_pen:.2f}–S/{cfg.risk.max_stake_pen:.2f}" in md_active

    # Also verify switching between 25% and 50% never mislabels one as the other
    enrich_backtest_result_metadata(
        dummy_result,
        kelly_fraction=0.25,
        kelly_min_stake=1.00,
        kelly_max_stake=10.00,
        kelly_max_fraction=0.10,
        boxscores_count=len(boxscores),
        zero_lookahead_verified=True,
    )
    md_25 = render_configured_markdown(dummy_result)
    assert "Stake Kelly 25%" in md_25
    assert "Stake Kelly 50%" not in md_25

    enrich_backtest_result_metadata(
        dummy_result,
        kelly_fraction=0.50,
        kelly_min_stake=1.00,
        kelly_max_stake=10.00,
        kelly_max_fraction=0.10,
        boxscores_count=len(boxscores),
        zero_lookahead_verified=True,
    )
    md_50 = render_configured_markdown(dummy_result)
    assert "Stake Kelly 50%" in md_50
    assert "Stake Kelly 25%" not in md_50

    # Verify lookahead guard rejects synthetic games or pre-start bets
    with pytest.raises(ValueError, match="Lookahead"):
        verify_zero_lookahead_leakage(
            games,
            {"bets": [{"matchday_date": "2024-12-15"}]},
            start_date="2025-01-01",
        )

