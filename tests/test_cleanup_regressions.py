"""Regression tests for code-cleanup, P2 steam modulation, config centralization, and reporting accuracy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.config import load_config
from src.ingestion.sportradar import resolve_nba_season_year
from src.prediction.ev_calculator import evaluate_market_opportunity
from src.reporting.dashboard_export import export_bets_and_tracking_dashboard
from src.reporting.obsidian_sync import sync_obsidian_vault
from src.reporting.telegram_interactive import TelegramInteractiveListener
from src.storage.db import DatabaseManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_adverse_steam_never_increases_low_p2_model_weight() -> None:
    """P2 decayed weights (< 0.15 or 0.00) must never bounce back up under adverse or zero-anchor steam."""
    odds_record = {
        "odds_id": "O_STEAM_CLEAN_1",
        "game_id": "ESPN_STEAM_CLEAN_1",
        "provider": "Pinnacle",
        "market": "total_points",
        "selection": "OVER",
        "line_value": 224.5,
        "decimal_odds": 1.92,
        "counterpart_decimal_odds": 1.92,
        "captured_at": "2026-11-24T22:00:00Z",
    }

    expectations = [
        # (base_weight, adverse_expected, confirming_expected)
        (0.00, 0.00, 0.00),
        (0.02, 0.00, 0.06),
        (0.11, 0.03, 0.15),
        (0.30, 0.22, 0.34),
    ]
    for base_w, adv_w, conf_w in expectations:
        opp_adv = evaluate_market_opportunity(
            estimated_prob=0.60,
            uncertainty_std=0.04,
            odds_record=odds_record,
            game_start_time="2026-11-25T00:00:00Z",
            model_version_id="model_f_ensemble_v8",
            simulated_prediction_time="2026-11-24T22:05:00Z",
            market_consensus_prob=0.50,
            model_weight=base_w,
            steam_delta=-0.035,
        )
        opp_conf = evaluate_market_opportunity(
            estimated_prob=0.60,
            uncertainty_std=0.04,
            odds_record=odds_record,
            game_start_time="2026-11-25T00:00:00Z",
            model_version_id="model_f_ensemble_v8",
            simulated_prediction_time="2026-11-24T22:05:00Z",
            market_consensus_prob=0.50,
            model_weight=base_w,
            steam_delta=0.035,
        )
        assert opp_adv["effective_model_weight"] == pytest.approx(adv_w, abs=1e-6)
        assert opp_conf["effective_model_weight"] == pytest.approx(conf_w, abs=1e-6)
        if base_w == 0.0:
            assert opp_adv["market_anchored_probability"] == pytest.approx(0.50, abs=1e-6)
            assert opp_conf["market_anchored_probability"] == pytest.approx(0.50, abs=1e-6)


def test_telegram_interactive_uses_production_engine_and_config_copy(tmp_path: Path) -> None:
    cfg = load_config()
    db = DatabaseManager(tmp_path / "tg_cfg.sqlite3")
    listener = TelegramInteractiveListener(
        bot_token="DUMMY_TOKEN",
        allowed_chat_ids=["123456"],
        db=db,
        offset_file=tmp_path / "offset.txt",
    )
    assert listener.paper_engine.min_ev_threshold == pytest.approx(cfg.risk.min_ev_threshold)
    assert listener.paper_engine.max_stake_pen == pytest.approx(cfg.risk.max_stake_pen)
    assert listener.paper_engine.allocation_mode == cfg.hybrid_allocation.allocation_mode
    assert listener.paper_engine.kelly_fraction == pytest.approx(cfg.risk.kelly_fraction)

    help_text = listener.handle_help("Andre")
    assert f"EV ≥ {cfg.risk.min_ev_threshold * 100.0:.1f}%" in help_text
    assert f"S/ {cfg.risk.max_stake_pen:.2f} PEN" in help_text
    assert "EV ≥ 5%" not in help_text


def test_workflows_preserve_weekly_backtest_csvs_and_no_leaked_train_script() -> None:
    assert not (PROJECT_ROOT / "scripts" / "train_models.py").exists()

    auto_wf = (PROJECT_ROOT / ".github" / "workflows" / "nba_cloud_automation.yml").read_text(encoding="utf-8")
    assert "market_consensus_" in auto_wf
    assert "STATE_BASE_SHA" in auto_wf

    closing_wf = (PROJECT_ROOT / ".github" / "workflows" / "closing_capture.yml").read_text(encoding="utf-8")
    assert "--window 25" in closing_wf
    assert 'LOOP_INTERVAL_SECONDS: "900"' in closing_wf
    assert "next 25 minutes" in closing_wf
    assert "every 15 minutes" in closing_wf


def test_reporting_copy_matches_active_sources_config(tmp_path: Path) -> None:
    cfg = load_config()
    vault_dir = tmp_path / "vault"
    sync_obsidian_vault(
        vault_dir,
        daily_report_md="# Daily",
        weekly_report_md="# Weekly",
        audit_report_md="# Audit",
        metrics={
            "current_settled_bankroll_pen": 100.0,
            "net_profit_pen": 0.0,
            "roi_pct": 0.0,
            "settled_bets_count": 0,
            "exit_gates_evaluation": {"recommendation": "REMAIN_IN_PAPER_TRADING"},
        },
        environment_status={},
        target_date="2026-11-23",
    )
    sources_note = (vault_dir / "01-Sources" / "Data-Sources-and-Limitations.md").read_text(encoding="utf-8")
    assert f"seasons/{resolve_nba_season_year()}/REG/standings.json" in sources_note
    assert "25+ casas" not in sources_note
    if not cfg.sources.sportradar_synergy_enabled:
        assert "sportradar_synergy_enabled: false" in sources_note
        assert f"región `{cfg.sources.the_odds_api_regions}`" in sources_note

    db = DatabaseManager(tmp_path / "dash_copy.sqlite3")
    now_dt = datetime.now(timezone.utc)
    tip_iso = (now_dt + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    matchday = (now_dt + timedelta(hours=3)).strftime("%Y-%m-%d")
    cap_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team, status,
                home_off_rtg, home_def_rtg, home_pace, away_off_rtg, away_def_rtg, away_pace,
                home_rest_days, away_rest_days, features_available_at, source_provider, ingested_at
            )
            VALUES (
                'ESPN_CLEAN_1', '2026-27', ?, ?, 'BOS', 'NYK', 'SCHEDULED',
                118.0, 110.0, 99.0, 114.0, 113.0, 98.0, 2, 1, ?, 'espn_public_api', ?
            )
            """,
            (matchday, tip_iso, cap_iso, cap_iso),
        )
        conn.execute(
            """
            INSERT INTO model_versions (model_version_id, model_family, market, train_start_date, train_end_date, trained_at, hyperparameters_json, approved_by)
            VALUES (?, 'meta_ensemble', 'moneyline', '2024-10-01', '2026-11-01', ?, '{}', 'test')
            """,
            (cfg.model.version_id, cap_iso),
        )
        conn.execute(
            """
            INSERT INTO odds_snapshots (odds_id, game_id, provider, market, selection, line_value, decimal_odds, counterpart_decimal_odds, captured_at, source_type)
            VALUES ('ODDS_CLEAN_1', 'ESPN_CLEAN_1', 'Pinnacle', 'moneyline', 'HOME', NULL, 1.75, 2.20, ?, 'OBSERVED')
            """,
            (cap_iso,),
        )
        conn.execute(
            """
            INSERT INTO predictions (
                prediction_id, game_id, market, selection, line_value, model_version_id,
                raw_probability, calibrated_probability, uncertainty_std, implied_prob_gross,
                implied_prob_fair, bookmaker_overround, decimal_odds_used, odds_provider,
                odds_captured_at, ev_unit, ev_pct, emitted_at, features_snapshot_json
            ) VALUES (
                'PRED_CLEAN_1', 'ESPN_CLEAN_1', 'moneyline', 'HOME', NULL, ?,
                0.62, 0.62, 0.04, 0.5714, 0.556, 0.025, 1.75, 'Pinnacle', ?, 0.085, 8.5, ?, '{}'
            )
            """,
            (cfg.model.version_id, cap_iso, cap_iso),
        )
        conn.execute(
            """
            INSERT INTO simulated_bets (
                bet_id, prediction_id, game_id, matchday_date, market, selection, line_value,
                decimal_odds, estimated_prob, estimated_ev, stake_pen, emitted_at,
                model_version_id, status
            ) VALUES (
                'BET_CLEAN_1', 'PRED_CLEAN_1', 'ESPN_CLEAN_1', ?, 'moneyline', 'HOME', NULL,
                1.75, 0.62, 0.085, 2.50, ?, ?, 'PENDING'
            )
            """,
            (matchday, cap_iso, cfg.model.version_id),
        )

    metrics = {
        "current_settled_bankroll_pen": 100.0,
        "net_profit_pen": 0.0,
        "roi_pct": 0.0,
        "yield_pct": 0.0,
        "settled_bets_count": 0,
        "live_espn_settled_bets_count": 0,
        "overall_brier_score": None,
        "baseline_brier_score": None,
        "overall_log_loss": None,
        "baseline_log_loss": None,
        "max_drawdown_pct": 0.0,
        "ece_score": None,
        "roi_ci_lower_pct": -10.0,
        "roi_ci_upper_pct": 10.0,
        "roi_ci_90_lower_pct": -8.0,
        "roi_ci_90_upper_pct": 8.0,
        "leakage_violations": 0,
        "exit_gates_evaluation": {"gates": {}, "recommendation": "REMAIN_IN_PAPER_TRADING"},
    }
    res = export_bets_and_tracking_dashboard(
        db=db,
        metrics=metrics,
        csv_output_path=tmp_path / "apuestas_historial.csv",
        md_output_path=tmp_path / "SEGUIMIENTO_APUESTAS.md",
    )
    tracker_md = Path(res["md_path"]).read_text(encoding="utf-8")
    assert "25 Casas" not in tracker_md
    if not cfg.sources.github_issue_notifications_enabled:
        assert "GitHub Issues desactivado" in tracker_md
