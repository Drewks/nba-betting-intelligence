"""
Regression tests for the 2026-11-15 audit remediation findings & roadmap items.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from src.backtesting.backtester import WalkForwardBacktester
from src.backtesting.real_odds_backtest import run_real_odds_backtest
from src.config import load_config
from src.paper_trading.engine import build_production_engine
from src.paper_trading.shadow_ledger import settle_pending_shadow_candidates, summarize_shadow_ledger
from src.prediction.totals_closing import fit_totals_closing_estimator
from src.storage.db import DatabaseManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_zero_pytest_current_test_leakage_in_src() -> None:
    leaks = [
        str(p.relative_to(PROJECT_ROOT))
        for p in (PROJECT_ROOT / "src").rglob("*.py")
        if "PYTEST_CURRENT_TEST" in p.read_text(encoding="utf-8")
    ]
    assert leaks == []


def test_modularization_max_line_count_under_1000() -> None:
    oversized = [
        (str(p.relative_to(PROJECT_ROOT)), len(p.read_text(encoding="utf-8").splitlines()))
        for root_name in ("src", "scripts")
        for p in (PROJECT_ROOT / root_name).rglob("*.py")
        if len(p.read_text(encoding="utf-8").splitlines()) >= 1000
    ]
    assert oversized == []


def test_governance_policy_aligned_with_model_config() -> None:
    load_config.cache_clear()
    cfg = load_config()
    assert cfg.risk.kelly_fraction == pytest.approx(0.25)
    assert cfg.risk.min_ev_threshold == pytest.approx(0.02)
    assert cfg.risk.max_stake_pen == pytest.approx(10.0)
    assert cfg.risk.allow_parlays is False
    assert cfg.risk.allow_player_props_betting is False
    assert cfg.sources.betting_allowed_source_types == ("OBSERVED",)
    assert cfg.sources.peru_scraper_policy == "PUBLIC_READONLY_JSON_API_NO_ANTIBOT_BYPASS"
    assert cfg.evaluation.holdout_season == "2026-27"
    assert cfg.evaluation.trials_evaluated_count >= 1

    agents_md = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    pt_md = (PROJECT_ROOT / ".agents" / "agents" / "paper_trading_manager.md").read_text(encoding="utf-8")
    skill_md = (PROJECT_ROOT / ".agents" / "skills" / "nba-intelligence-ops" / "SKILL.md").read_text(encoding="utf-8")
    readme_md = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    for doc in (agents_md, pt_md, skill_md, readme_md):
        assert "25%" in doc or "0.25" in doc
        assert "10.00" in doc
        assert "2.0%" in doc or "0.02" in doc
    for doc in (agents_md, skill_md, readme_md):
        assert "state-live" in doc
    assert "S/6.00 PEN" not in skill_md


def test_shadow_candidates_recording_settlement_and_immutability_triggers(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "shadow_test.sqlite3")
    engine = build_production_engine(db)
    start_ts = "2030-01-15T23:00:00Z"
    feat_ts = "2030-01-15T18:00:00Z"
    cap_ts = "2030-01-15T19:00:00Z"
    close_ts = "2030-01-15T22:55:00Z"

    cfg = load_config()
    model_ver = cfg.model.version_id
    with db.connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO model_versions (
                model_version_id, model_family, market, train_start_date, train_end_date,
                trained_at, hyperparameters_json, is_active, approved_by
            ) VALUES (?, 'ensemble', 'moneyline', '2024-10-01', '2026-10-01', ?, '{}', 1, 'test')
            """,
            (model_ver, feat_ts),
        )
        conn.execute(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, home_off_rtg, home_def_rtg, home_pace, away_off_rtg, away_def_rtg, away_pace,
                home_rest_days, away_rest_days, features_available_at, source_provider, ingested_at
            ) VALUES ('ESPN_SHD_1', '2026-27', '2030-01-15', ?, 'BOS', 'LAL', 'SCHEDULED',
                      116.0, 110.0, 99.0, 113.0, 112.0, 98.5, 2, 2, ?, 'ESPN', ?)
            """,
            (start_ts, feat_ts, feat_ts),
        )
        conn.execute(
            """
            INSERT INTO odds_snapshots (
                odds_id, game_id, provider, market, selection, line_value, decimal_odds,
                counterpart_decimal_odds, captured_at, source_type, is_closing_line
            ) VALUES
            ('ODD_ML_Q', 'ESPN_SHD_1', 'Pinnacle', 'moneyline', 'HOME', NULL, 2.00, 1.90, ?, 'OBSERVED', 0),
            ('ODD_TOT_SUB', 'ESPN_SHD_1', 'Betano', 'total_points', 'OVER', 225.5, 1.90, 1.95, ?, 'OBSERVED', 0),
            ('ODD_SP_LOWK', 'ESPN_SHD_1', 'RETAbet', 'spread', 'HOME', -2.5, 1.95, 1.90, ?, 'OBSERVED', 0),
            ('ODD_TOT_CL', 'ESPN_SHD_1', 'Pinnacle', 'total_points', 'OVER', 225.5, 1.82, 2.04, ?, 'OBSERVED', 1)
            """,
            (cap_ts, cap_ts, cap_ts, close_ts),
        )
        conn.execute(
            """
            INSERT INTO predictions (
                prediction_id, game_id, market, selection, model_version_id,
                raw_probability, calibrated_probability, uncertainty_std, implied_prob_gross,
                implied_prob_fair, decimal_odds_used, odds_provider, odds_captured_at,
                ev_unit, ev_pct, emitted_at, features_snapshot_json
            ) VALUES
            ('PRED_SHD_1', 'ESPN_SHD_1', 'moneyline', 'HOME', ?, 0.56, 0.56, 0.04, 0.50, 0.487, 2.00, 'Pinnacle', ?, 0.12, 12.0, ?, '{}'),
            ('PRED_SHD_2', 'ESPN_SHD_1', 'total_points', 'OVER', ?, 0.534, 0.534, 0.04, 0.526, 0.519, 1.90, 'Betano', ?, 0.0146, 1.46, ?, '{}'),
            ('PRED_SHD_3', 'ESPN_SHD_1', 'spread', 'HOME', ?, 0.525, 0.525, 0.04, 0.513, 0.493, 1.95, 'RETAbet', ?, 0.02375, 2.375, ?, '{}')
            """,
            (model_ver, cap_ts, cap_ts, model_ver, cap_ts, cap_ts, model_ver, cap_ts, cap_ts),
        )

    cands = [
        {
            "prediction_id": "PRED_SHD_1",
            "model_version_id": model_ver,
            "game_id": "ESPN_SHD_1",
            "market": "moneyline",
            "selection": "HOME",
            "line_value": None,
            "decimal_odds_used": 2.00,
            "calibrated_probability": 0.56,
            "estimated_probability": 0.56,  # +12% EV -> qualifies
            "raw_model_probability": 0.56,
            "ev_unit": 0.12,
            "ev_pct": 12.0,
            "odds_provider": "Pinnacle",
            "odds_source_type": "OBSERVED",
            "emitted_at": cap_ts,
        },
        {
            "prediction_id": "PRED_SHD_2",
            "model_version_id": model_ver,
            "game_id": "ESPN_SHD_1",
            "market": "total_points",
            "selection": "OVER",
            "line_value": 225.5,
            "decimal_odds_used": 1.90,
            "calibrated_probability": 0.534,
            "estimated_probability": 0.534,  # ~1.46% EV (< 2% min_ev_threshold -> blocked)
            "raw_model_probability": 0.534,
            "ev_unit": 0.0146,
            "ev_pct": 1.46,
            "odds_provider": "Betano",
            "odds_source_type": "OBSERVED",
            "emitted_at": cap_ts,
        },
        {
            "prediction_id": "PRED_SHD_3",
            "model_version_id": model_ver,
            "game_id": "ESPN_SHD_1",
            "market": "spread",
            "selection": "HOME",
            "line_value": -2.5,
            "decimal_odds_used": 1.95,
            "calibrated_probability": 0.525,
            "estimated_probability": 0.525,  # +2.38% EV -> blocked by same-game cap or tiny Kelly (< S/1.00)
            "raw_model_probability": 0.525,
            "ev_unit": 0.02375,
            "ev_pct": 2.375,
            "odds_provider": "RETAbet",
            "odds_source_type": "OBSERVED",
            "emitted_at": cap_ts,
        },
    ]
    res = engine.evaluate_and_record_matchday_selections("2030-01-15", cands)
    assert len(res["placed_bets"]) == 1
    assert engine.get_bankroll_state()["pending_exposure_pen"] == res["placed_bets"][0]["stake_pen"]

    shadows = db.fetch_all("SELECT * FROM shadow_candidates ORDER BY market")
    assert len(shadows) == 3
    reasons = {r["market"]: r["rejection_reason"] for r in shadows}
    assert reasons["moneyline"] == "QUALIFIED_POSITIVE_EV"
    assert reasons["total_points"] == "EV_BELOW_THRESHOLD"
    # spread was also same game (CORRELATED_GAME_EXPOSURE or KELLY_STAKE_BELOW_MINIMUM)
    assert reasons["spread"] in ("KELLY_STAKE_BELOW_MINIMUM", "CORRELATED_GAME_EXPOSURE")

    # Settle FINAL game: BOS 118, LAL 110 (total 228 > 225.5, BOS covers -2.5)
    with db.connect() as conn:
        conn.execute(
            "UPDATE games SET status = 'FINAL', home_score = 118, away_score = 110, result_recorded_at = '2030-01-16T03:00:00Z' WHERE game_id = 'ESPN_SHD_1'"
        )
    settled_sh = settle_pending_shadow_candidates(db)
    assert len(settled_sh) == 3
    summary = summarize_shadow_ledger(db)
    assert summary["settled"] == 3
    assert summary["won"] == 3
    assert summary["unit_profit_1u"] > 0.0

    # Immutability triggers block post-settlement tampering and deletion
    settled_id = shadows[0]["shadow_id"]
    with pytest.raises(sqlite3.DatabaseError):
        with db.connect() as conn:
            conn.execute("UPDATE shadow_candidates SET status = 'VOID' WHERE shadow_id = ?", (settled_id,))
    with pytest.raises(sqlite3.DatabaseError):
        with db.connect() as conn:
            conn.execute("DELETE FROM shadow_candidates WHERE shadow_id = ?", (settled_id,))


def test_by_model_version_and_walk_forward_oos_and_by_market_wiring(tmp_path: Path) -> None:
    from scripts.cloud_cycle_helpers import build_walk_forward_oos_comparisons_for_active_model

    db = DatabaseManager(tmp_path / "mver.sqlite3")
    cfg = load_config()
    base_dt = datetime(2025, 1, 1, 20, 0, tzinfo=timezone.utc)
    teams = ["BOS", "NYK", "DEN", "DAL", "LAL", "MIA"]
    final_games: list[dict] = []

    with db.connect() as conn:
        for i in range(165):
            dt = base_dt + timedelta(days=i // 2, hours=(i % 2) * 3)
            g_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            m_date = dt.strftime("%Y-%m-%d")
            f_str = (dt - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
            ht = teams[i % len(teams)]
            at = teams[(i + 1) % len(teams)]
            hs = 112 + (i % 9)
            as_ = 104 + ((i * 3) % 11)
            gid = f"ESPN_MVER_{i}"
            row = (
                gid, "2025-26", m_date, g_str, ht, at, "FINAL", hs, as_,
                115.0 + (i % 4), 111.0, 99.0, 113.0, 112.0 + (i % 3), 98.5, 2, 2, f_str, "ESPN", f_str,
            )
            conn.execute(
                """
                INSERT INTO games (
                    game_id, season, matchday_date, game_start_time, home_team, away_team,
                    status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
                    away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
                    features_available_at, source_provider, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            if i >= 120:
                cap_str = (dt - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
                conn.execute(
                    """
                    INSERT INTO odds_snapshots (
                        odds_id, game_id, provider, market, selection, line_value,
                        decimal_odds, counterpart_decimal_odds, captured_at, source_type, is_closing_line
                    ) VALUES
                    (?, ?, 'Pinnacle', 'moneyline', 'HOME', NULL, 1.85, 2.05, ?, 'OBSERVED', 0),
                    (?, ?, 'Pinnacle', 'moneyline', 'AWAY', NULL, 2.05, 1.85, ?, 'OBSERVED', 0),
                    (?, ?, 'Pinnacle', 'total_points', 'OVER', 221.5, 1.92, 1.92, ?, 'OBSERVED', 0),
                    (?, ?, 'Pinnacle', 'total_points', 'UNDER', 221.5, 1.92, 1.92, ?, 'OBSERVED', 0)
                    """,
                    (
                        f"OMLH_{i}", gid, cap_str,
                        f"OMLA_{i}", gid, cap_str,
                        f"OTOV_{i}", gid, cap_str,
                        f"OTUN_{i}", gid, cap_str,
                    ),
                )

        # Insert 1 legacy pre-m012 prediction row to confirm version breakdown excludes false calibration
        conn.execute(
            """
            INSERT OR IGNORE INTO model_versions (
                model_version_id, model_family, market, train_start_date, train_end_date,
                trained_at, hyperparameters_json, is_active, approved_by
            ) VALUES ('model_f_ensemble_v4', 'legacy', 'moneyline', '2024-01-01', '2025-01-01', '2025-01-01T00:00:00Z', '{}', 0, 'test')
            """
        )
        conn.execute(
            """
            INSERT INTO predictions (
                prediction_id, game_id, market, selection, model_version_id,
                raw_probability, calibrated_probability, uncertainty_std, implied_prob_gross,
                implied_prob_fair, decimal_odds_used, odds_provider, odds_captured_at,
                ev_unit, ev_pct, emitted_at, features_snapshot_json
            ) VALUES ('PLEG_1', 'ESPN_MVER_164', 'moneyline', 'HOME', 'model_f_ensemble_v4',
                      0.60, 0.56, 0.05, 0.54, 0.52, 1.85, 'Pinnacle', '2025-03-01T18:00:00Z',
                      0.03, 3.0, '2025-03-01T18:00:00Z', '{}')
            """
        )

    final_games = db.fetch_all("SELECT * FROM games WHERE status = 'FINAL' ORDER BY game_start_time ASC")
    now_str = "2026-01-01T00:00:00Z"
    oos_recs = build_walk_forward_oos_comparisons_for_active_model(
        db,
        final_games,
        cfg.model.version_id,
        now_str,
        market_anchor_weight=cfg.model.market_anchor_model_weight,
        moneyline_weight=cfg.model.moneyline_model_weight,
    )
    assert len(oos_recs) >= 15
    assert all(r["model_c_ml"] is not None for r in oos_recs)

    engine = build_production_engine(db)
    bt = WalkForwardBacktester(db, engine)
    metrics = bt.compute_comprehensive_metrics(
        model_comparison_records=oos_recs,
        calibration_evaluation_source="WALK_FORWARD_FROZEN_ACTIVE_VERSION_OOS",
    )
    assert metrics["overall_brier_score"] is not None
    assert metrics["calibration_evaluation_source"] == "WALK_FORWARD_FROZEN_ACTIVE_VERSION_OOS"
    assert metrics["active_model_version_id"] == cfg.model.version_id
    assert "model_f_ensemble_v4" in metrics["by_model_version"]
    assert metrics["by_model_version"]["model_f_ensemble_v4"]["has_m012_cal_probs"] is False
    assert set(metrics["performance_by_market"].keys()) == {"moneyline", "total_points", "spread"}


def test_totals_closing_estimator_and_holdout_bonferroni() -> None:
    prior_rows = [
        {
            "p_over": 0.42 + 0.003 * idx,
            "tot_open_line": 225.0,
            "tot_close_line": 225.0 + 14.0 * ((0.42 + 0.003 * idx) - 0.50),
        }
        for idx in range(55)
    ]
    est = fit_totals_closing_estimator(prior_rows, min_samples=40)
    assert est.is_active is True
    assert est.slope > 0.0
    sig_over = est.predict(0.64)
    sig_under = est.predict(0.36)
    assert sig_over["predicted_side"] == "OVER" and sig_over["qualifies"] is True
    assert sig_under["predicted_side"] == "UNDER" and sig_under["qualifies"] is True

    market_path = PROJECT_ROOT / "data" / "raw" / "market_consensus_2024-25.csv"
    assert market_path.exists()
    from src.backtesting.real_odds_backtest import load_market_rows
    from tests.helpers import connect_readonly_prod_db

    conn = connect_readonly_prod_db()
    games = [dict(r) for r in conn.execute("SELECT * FROM games WHERE season = '2024-25' AND status = 'FINAL' ORDER BY game_start_time LIMIT 220").fetchall()]
    conn.close()
    m_rows = load_market_rows([market_path])

    res = run_real_odds_backtest(
        games,
        m_rows,
        start_date=games[160]["matchday_date"],
        trials_evaluated_count=3,
    )
    assert "full_slate_evaluation" in res
    assert "holdout_partition" in res
    assert "uncapped_shadow" in res
    assert "totals_clv_targeted" in res
    assert res["totals_clv_targeted"]["estimator"]["holdout_excluded_from_fit"] is True
    mt = res["betting"]["multiple_testing"]
    assert mt["trials_evaluated_count"] == 3
    if mt["roi"]["raw_p_value"] is not None:
        assert mt["roi"]["bonferroni_p_value"] >= mt["roi"]["raw_p_value"]


def test_sync_state_live_refuses_tracked_main_db_overwrite() -> None:
    from scripts.sync_state_live import extract_state_live_db

    with pytest.raises(RuntimeError, match="Refusing to overwrite tracked"):
        extract_state_live_db(PROJECT_ROOT / "data" / "nba_intelligence.sqlite3", fetch=False)
