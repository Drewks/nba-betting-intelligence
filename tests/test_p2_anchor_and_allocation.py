"""Tests for P2: time-decaying market anchor, evidence-guided allocation, and early cron window."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.cloud_cycle_helpers import evaluate_scheduled_slate_candidates
from src.calibration.calibrator import ProbabilityCalibrator, VennAbersConformalInterval
from src.config import ConfigError, MarketAnchorScheduleConfig, load_config, parse_config
from src.models.statistical_models import EnsembleStackingModel
from src.paper_trading.engine import PaperTradingEngine
from src.prediction.ev_calculator import resolve_market_anchor_weight
from src.storage.db import DatabaseManager
from tests.helpers import PROJECT_ROOT


def _seed_model_and_game(
    db: DatabaseManager,
    game_id: str,
    *,
    matchday_date: str = "2026-11-24",
    start_time: str = "2026-11-24T23:00:00Z",
    home_team: str = "BOS",
    away_team: str = "MIA",
    status: str = "SCHEDULED",
    home_score: int | None = None,
    away_score: int | None = None,
) -> None:
    with db.connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO model_versions (
                model_version_id, model_family, market, train_start_date, train_end_date,
                trained_at, hyperparameters_json, approved_by
            ) VALUES (
                'model_f_ensemble_v8', 'ensemble', 'moneyline',
                '2025-10-01', '2026-11-20', '2026-11-20T00:00:00Z', '{}', 'test'
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, home_score, away_score,
                home_off_rtg, home_def_rtg, home_pace,
                away_off_rtg, away_def_rtg, away_pace,
                home_rest_days, away_rest_days,
                features_available_at, source_provider, ingested_at
            ) VALUES (?, '2026-27', ?, ?, ?, ?, ?, ?, ?,
                      116.0, 110.5, 99.2, 112.5, 113.0, 98.8, 2, 2,
                      '2026-11-24T10:00:00Z', 'espn', '2026-11-24T10:00:00Z')
            """,
            (game_id, matchday_date, start_time, home_team, away_team, status, home_score, away_score),
        )


def test_market_anchor_schedule_config_defaults_and_validation() -> None:
    cfg = load_config()
    sched = cfg.model.anchor_schedule
    assert sched.enabled is True
    assert sched.horizon_hours == 12.0
    assert sched.decay_power == 1.0
    assert (sched.moneyline_open_weight, sched.moneyline_close_weight) == (0.28, 0.11)
    assert (sched.total_points_open_weight, sched.total_points_close_weight) == (0.30, 0.00)
    assert (sched.spread_open_weight, sched.spread_close_weight) == (0.24, 0.02)
    assert cfg.hybrid_allocation.allocation_mode == "evidence_guided"

    base_raw = yaml.safe_load((PROJECT_ROOT / "config" / "model_config.yaml").read_text(encoding="utf-8"))

    # Reject close_weight > open_weight
    bad_inversion = yaml.safe_load(yaml.safe_dump(base_raw))
    bad_inversion["model"]["market_anchor_schedule"]["moneyline_close_weight"] = 0.40
    with pytest.raises(ConfigError):
        parse_config(bad_inversion)

    # Reject out-of-range horizon / decay_power
    bad_horizon = yaml.safe_load(yaml.safe_dump(base_raw))
    bad_horizon["model"]["market_anchor_schedule"]["horizon_hours"] = 99.0
    with pytest.raises(ConfigError):
        parse_config(bad_horizon)

    bad_power = yaml.safe_load(yaml.safe_dump(base_raw))
    bad_power["model"]["market_anchor_schedule"]["decay_power"] = 10.0
    with pytest.raises(ConfigError):
        parse_config(bad_power)

    # Reject unknown allocation_mode
    bad_alloc = yaml.safe_load(yaml.safe_dump(base_raw))
    bad_alloc["hybrid_allocation"]["allocation_mode"] = "magic_override"
    with pytest.raises(ConfigError):
        parse_config(bad_alloc)


def test_resolve_market_anchor_weight_monotonic_decay() -> None:
    sched = MarketAnchorScheduleConfig(enabled=True)

    # At >= horizon (12h+), converges cleanly to open weights; at 0h, to close weights
    assert resolve_market_anchor_weight("moneyline", hours_to_tipoff=15.0, fallback_weight=0.30, schedule=sched) == 0.28
    assert resolve_market_anchor_weight("moneyline", hours_to_tipoff=12.0, fallback_weight=0.30, schedule=sched) == 0.28
    assert resolve_market_anchor_weight("moneyline", hours_to_tipoff=0.0, fallback_weight=0.30, schedule=sched) == 0.11

    assert resolve_market_anchor_weight("total_points", hours_to_tipoff=12.0, fallback_weight=0.30, schedule=sched) == 0.30
    assert resolve_market_anchor_weight("total_points", hours_to_tipoff=6.0, fallback_weight=0.30, schedule=sched) == 0.15
    assert resolve_market_anchor_weight("total_points", hours_to_tipoff=2.0, fallback_weight=0.30, schedule=sched) == 0.05
    assert resolve_market_anchor_weight("total_points", hours_to_tipoff=0.0, fallback_weight=0.30, schedule=sched) == 0.00

    assert resolve_market_anchor_weight("spread", hours_to_tipoff=12.0, fallback_weight=0.30, schedule=sched) == 0.24
    assert resolve_market_anchor_weight("spread", hours_to_tipoff=0.0, fallback_weight=0.30, schedule=sched) == 0.02

    # Monotonic across horizons
    ml_weights = [
        resolve_market_anchor_weight("moneyline", hours_to_tipoff=h, fallback_weight=0.30, schedule=sched)
        for h in (0.0, 2.0, 6.0, 12.0)
    ]
    assert ml_weights == sorted(ml_weights)

    # Fallback when schedule disabled or hours_to_tipoff missing
    disabled = MarketAnchorScheduleConfig(enabled=False)
    assert resolve_market_anchor_weight("moneyline", hours_to_tipoff=2.0, fallback_weight=0.30, moneyline_weight=0.25, schedule=disabled) == 0.25
    assert resolve_market_anchor_weight("total_points", hours_to_tipoff=None, fallback_weight=0.30, schedule=sched) == 0.30


def test_evidence_guided_allocation_prioritizes_non_no_edge_and_caps_no_edge(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "alloc.sqlite3")

    # Seed 16 settled games where total_points shadow signals have consistently negative CLV -> NO_EDGE
    # and 10 moneyline shadow signals with mixed positive CLV -> INCONCLUSIVE (not capped)
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO model_versions (
                model_version_id, model_family, market, train_start_date, train_end_date,
                trained_at, hyperparameters_json, approved_by
            ) VALUES (
                'model_f_ensemble_v8', 'ensemble', 'moneyline',
                '2025-10-01', '2026-11-20', '2026-11-20T00:00:00Z', '{}', 'test'
            )
            """
        )
        for idx in range(16):
            gid = f"G_HIST_{idx:02d}"
            conn.execute(
                """
                INSERT INTO games (
                    game_id, season, matchday_date, game_start_time, home_team, away_team,
                    status, home_score, away_score, features_available_at, source_provider, ingested_at
                ) VALUES (?, '2026-27', '2026-11-20', '2026-11-20T23:00:00Z', 'BOS', 'MIA',
                          'FINAL', 110, 102, '2026-11-20T12:00:00Z', 'espn', '2026-11-20T12:00:00Z')
                """,
                (gid,),
            )
            pred_id = f"PRED_H_{idx:02d}"
            conn.execute(
                """
                INSERT INTO predictions (
                    prediction_id, game_id, market, selection, line_value, model_version_id,
                    raw_probability, calibrated_probability, uncertainty_std, implied_prob_gross,
                    decimal_odds_used, odds_provider, odds_captured_at, ev_unit, ev_pct,
                    emitted_at, features_snapshot_json
                ) VALUES (?, ?, 'total_points', 'UNDER', 225.5, 'model_f_ensemble_v8',
                          0.55, 0.54, 0.04, 0.51, 1.95, 'Pinnacle', '2026-11-20T18:00:00Z',
                          0.053, 5.3, '2026-11-20T18:00:00Z', '{}')
                """,
                (pred_id, gid),
            )
            conn.execute(
                """
                INSERT INTO shadow_candidates (
                    shadow_id, prediction_id, game_id, matchday_date, market, selection, line_value,
                    model_version_id, odds_provider, decimal_odds, raw_probability, calibrated_probability,
                    ev_unit, ev_pct, hypothetical_kelly_stake_pen, decision_status, rejection_reason,
                    closing_decimal_odds, closing_fair_prob, clv_pct, status, hypothetical_unit_profit,
                    emitted_at, settled_at, source_type
                ) VALUES (?, ?, ?, '2026-11-20', 'total_points', 'UNDER', 225.5,
                          'model_f_ensemble_v8', 'Pinnacle', 1.95, 0.55, 0.54,
                          0.053, 5.3, 1.0, 'NO_BET', 'ACCEPTED',
                          2.05, 0.48, -4.0, 'LOST', -1.0,
                          '2026-11-20T18:00:00Z', '2026-11-21T03:00:00Z', 'OBSERVED')
                """,
                (f"SH_TOT_{idx:02d}", pred_id, gid),
            )
            if idx < 10:
                conn.execute(
                    """
                    INSERT INTO shadow_candidates (
                        shadow_id, prediction_id, game_id, matchday_date, market, selection, line_value,
                        model_version_id, odds_provider, decimal_odds, raw_probability, calibrated_probability,
                        ev_unit, ev_pct, hypothetical_kelly_stake_pen, decision_status, rejection_reason,
                        closing_decimal_odds, closing_fair_prob, clv_pct, status, hypothetical_unit_profit,
                        emitted_at, settled_at, source_type
                    ) VALUES (?, ?, ?, '2026-11-20', 'moneyline', 'HOME', NULL,
                              'model_f_ensemble_v8', 'Pinnacle', 1.90, 0.56, 0.56,
                              0.064, 6.4, 1.5, 'BET_PLACED', 'ACCEPTED',
                              1.85, 0.535, ?, 'WON', 0.90,
                              '2026-11-20T18:00:00Z', '2026-11-21T03:00:00Z', 'OBSERVED')
                    """,
                    (f"SH_ML_{idx:02d}", pred_id, gid, 1.0 if idx % 2 == 0 else -0.5),
                )

    # Create 4 upcoming games for matchday 2026-11-24
    cands: list[dict[str, Any]] = []
    for i, (mkt, sel, lv, odds, prob) in enumerate(
        [
            ("total_points", "UNDER", 224.5, 1.95, 0.55),  # NO_EDGE, raw EV=7.25% -> eff rank 3.625%
            ("total_points", "UNDER", 228.5, 1.95, 0.55),  # second NO_EDGE total -> capped at 1/day
            ("moneyline", "HOME", None, 1.90, 0.555),      # INCONCLUSIVE ML, raw EV=5.45% -> eff rank 5.45%
            ("moneyline", "AWAY", None, 1.90, 0.550),      # INCONCLUSIVE ML #2 -> allowed in evidence_guided!
        ]
    ):
        gid = f"ESPN_990{i}_2026-11-24_BOS_AT_MIA"
        _seed_model_and_game(db, gid)
        pid = f"PRED_UP_{i}"
        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO predictions (
                    prediction_id, game_id, market, selection, line_value, model_version_id,
                    raw_probability, calibrated_probability, uncertainty_std, implied_prob_gross,
                    decimal_odds_used, odds_provider, odds_captured_at, ev_unit, ev_pct,
                    emitted_at, features_snapshot_json
                ) VALUES (?, ?, ?, ?, ?, 'model_f_ensemble_v8',
                          ?, ?, 0.04, 0.51, ?, 'Pinnacle [LIVE_API]', '2026-11-24T15:00:00Z',
                          ?, ?, '2026-11-24T15:00:00Z', '{}')
                """,
                (pid, gid, mkt, sel, lv, prob, prob, odds, prob * odds - 1.0, (prob * odds - 1.0) * 100.0),
            )
        cands.append(
            {
                "prediction_id": pid,
                "game_id": gid,
                "market": mkt,
                "selection": sel,
                "line_value": lv,
                "decimal_odds_used": odds,
                "odds_provider": "Pinnacle [LIVE_API]",
                "odds_captured_at": "2026-11-24T15:00:00Z",
                "calibrated_probability": prob,
                "raw_probability": prob,
                "ev_unit": round(prob * odds - 1.0, 6),
                "ev_pct": round((prob * odds - 1.0) * 100.0, 4),
                "uncertainty_std": 0.04,
                "model_version_id": "model_f_ensemble_v8",
                "emitted_at": "2026-11-24T15:00:00Z",
            }
        )

    engine = PaperTradingEngine(
        db=db,
        initial_bankroll_pen=100.0,
        base_stake_pen=1.0,
        max_stake_pen=10.0,
        max_selections_per_matchday=3,
        min_ev_threshold=0.02,
        staking_mode="FRACTIONAL_KELLY",
        exclude_synthetic=True,
        hybrid_allocation_enabled=True,
        max_totals_per_matchday=2,
        max_moneyline_per_matchday=1,
        allocation_mode="evidence_guided",
    )
    res = engine.evaluate_and_record_matchday_selections("2026-11-24", cands, proposed_stake_pen=1.50)
    placed_markets = [b["market"] for b in res["placed_bets"]]
    # Moneyline picks outrank NO_EDGE total_points (both ML placed, bypassing static 1-ML cap)
    assert placed_markets == ["moneyline", "moneyline", "total_points"]
    assert res["no_bet_decisions"][0]["reason_code"] == "MATCHDAY_CAP_REACHED"

    # When slots remain open (< 3), a second NO_EDGE total_points bet is still capped at 1/day (MARKET_CAP_REACHED)
    cands_day2: list[dict[str, Any]] = []
    for i, (mkt, sel, lv, odds, prob) in enumerate(
        [
            ("moneyline", "HOME", None, 1.90, 0.56),
            ("total_points", "UNDER", 224.5, 1.95, 0.55),
            ("total_points", "UNDER", 228.5, 1.95, 0.545),
        ]
    ):
        gid = f"ESPN_992{i}_2026-11-25_BOS_AT_MIA"
        _seed_model_and_game(db, gid, matchday_date="2026-11-25", start_time="2026-11-25T23:00:00Z")
        pid = f"PRED_D2_{i}"
        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO predictions (
                    prediction_id, game_id, market, selection, line_value, model_version_id,
                    raw_probability, calibrated_probability, uncertainty_std, implied_prob_gross,
                    decimal_odds_used, odds_provider, odds_captured_at, ev_unit, ev_pct,
                    emitted_at, features_snapshot_json
                ) VALUES (?, ?, ?, ?, ?, 'model_f_ensemble_v8',
                          ?, ?, 0.04, 0.51, ?, 'Pinnacle [LIVE_API]', '2026-11-25T15:00:00Z',
                          ?, ?, '2026-11-25T15:00:00Z', '{}')
                """,
                (pid, gid, mkt, sel, lv, prob, prob, odds, prob * odds - 1.0, (prob * odds - 1.0) * 100.0),
            )
        cands_day2.append(
            {
                "prediction_id": pid,
                "game_id": gid,
                "market": mkt,
                "selection": sel,
                "line_value": lv,
                "decimal_odds_used": odds,
                "odds_provider": "Pinnacle [LIVE_API]",
                "odds_captured_at": "2026-11-25T15:00:00Z",
                "calibrated_probability": prob,
                "raw_probability": prob,
                "ev_unit": round(prob * odds - 1.0, 6),
                "ev_pct": round((prob * odds - 1.0) * 100.0, 4),
                "uncertainty_std": 0.04,
                "model_version_id": "model_f_ensemble_v8",
                "emitted_at": "2026-11-25T15:00:00Z",
            }
        )
    res_day2 = engine.evaluate_and_record_matchday_selections("2026-11-25", cands_day2, proposed_stake_pen=1.50)
    assert [b["market"] for b in res_day2["placed_bets"]] == ["moneyline", "total_points"]
    assert res_day2["no_bet_decisions"][0]["market"] == "total_points"
    assert res_day2["no_bet_decisions"][0]["reason_code"] == "MARKET_CAP_REACHED"

    # Confirm static_caps mode still strictly caps ML at 1/day on an isolated DB
    db_static = DatabaseManager(tmp_path / "alloc_static.sqlite3")
    cands_static: list[dict[str, Any]] = []
    for i in range(2):
        gid = f"ESPN_991{i}_2026-11-24_BOS_AT_MIA"
        _seed_model_and_game(db_static, gid)
        pid = f"PRED_ST_{i}"
        with db_static.connect() as conn:
            conn.execute(
                """
                INSERT INTO predictions (
                    prediction_id, game_id, market, selection, line_value, model_version_id,
                    raw_probability, calibrated_probability, uncertainty_std, implied_prob_gross,
                    decimal_odds_used, odds_provider, odds_captured_at, ev_unit, ev_pct,
                    emitted_at, features_snapshot_json
                ) VALUES (?, ?, 'moneyline', 'HOME', NULL, 'model_f_ensemble_v8',
                          0.58, 0.58, 0.04, 0.51, 1.90, 'Pinnacle', '2026-11-24T15:00:00Z',
                          0.102, 10.2, '2026-11-24T15:00:00Z', '{}')
                """,
                (pid, gid),
            )
        cands_static.append(
            {
                "prediction_id": pid,
                "game_id": gid,
                "market": "moneyline",
                "selection": "HOME",
                "line_value": None,
                "decimal_odds_used": 1.90,
                "odds_provider": "Pinnacle",
                "odds_captured_at": "2026-11-24T15:00:00Z",
                "calibrated_probability": 0.58,
                "raw_probability": 0.58,
                "ev_unit": 0.102,
                "ev_pct": 10.2,
                "uncertainty_std": 0.04,
                "model_version_id": "model_f_ensemble_v8",
                "emitted_at": "2026-11-24T15:00:00Z",
            }
        )
    static_eng = PaperTradingEngine(
        db=db_static,
        base_stake_pen=1.0,
        max_stake_pen=10.0,
        staking_mode="FRACTIONAL_KELLY",
        hybrid_allocation_enabled=True,
        max_moneyline_per_matchday=1,
        allocation_mode="static_caps",
    )
    res_static = static_eng.evaluate_and_record_matchday_selections("2026-11-24", cands_static, proposed_stake_pen=1.50)
    assert len(res_static["placed_bets"]) == 1
    assert res_static["no_bet_decisions"][0]["reason_code"] == "MARKET_CAP_REACHED"


def test_evaluate_scheduled_slate_records_time_decayed_weight_metadata(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "slate_decay.sqlite3")
    _seed_model_and_game(
        db,
        "ESPN_88001_2026-11-24_MIA_AT_BOS",
        matchday_date="2026-11-24",
        start_time="2026-11-24T22:00:00Z",
    )
    with db.connect() as conn:
        for odds_id, mkt, sel, lv, dec, cp in (
            ("O_ML_H", "moneyline", "HOME", None, 1.85, 2.02),
            ("O_ML_A", "moneyline", "AWAY", None, 2.02, 1.85),
            ("O_TOT_O", "total_points", "OVER", 224.5, 1.93, 1.93),
            ("O_TOT_U", "total_points", "UNDER", 224.5, 1.93, 1.93),
        ):
            conn.execute(
                """
                INSERT INTO odds_snapshots (
                    odds_id, game_id, provider, market, selection, line_value,
                    decimal_odds, counterpart_decimal_odds, captured_at, is_closing_line, source_type
                ) VALUES (?, 'ESPN_88001_2026-11-24_MIA_AT_BOS', 'Pinnacle [LIVE_API]',
                          ?, ?, ?, ?, ?, '2026-11-24T15:30:00Z', 0, 'OBSERVED')
                """,
                (odds_id, mkt, sel, lv, dec, cp),
            )

    # Decision at 16:00Z -> exactly 6.0 hours before 22:00Z tip-off
    cal_bundle = {
        "ml_cal": ProbabilityCalibrator(),
        "tot_cal": ProbabilityCalibrator(),
        "sp_cal": ProbabilityCalibrator(),
        "ml_va": VennAbersConformalInterval(),
        "tot_va": VennAbersConformalInterval(),
        "sp_va": VennAbersConformalInterval(),
        "run_manifest_id": "RUN_TEST_P2",
    }
    res = evaluate_scheduled_slate_candidates(
        db,
        all_final_games=[],
        bx_features={},
        model_f=EnsembleStackingModel("model_f_ensemble_v8"),
        model_version_id="model_f_ensemble_v8",
        cal_bundle=cal_bundle,
        market_anchor_weight=0.30,
        moneyline_weight=0.30,
        moneyline_max_disagreement=0.15,
        moneyline_max_odds=2.80,
        now_str="2026-11-24T16:00:00Z",
    )
    opps = res["2026-11-24"]
    assert opps
    sched = load_config().model.anchor_schedule
    expected_ml = resolve_market_anchor_weight("moneyline", hours_to_tipoff=6.0, fallback_weight=0.30, schedule=sched)
    expected_tot = resolve_market_anchor_weight("total_points", hours_to_tipoff=6.0, fallback_weight=0.30, schedule=sched)

    rows = db.fetch_all("SELECT market, features_snapshot_json FROM predictions")
    snaps_by_mkt = {r["market"]: json.loads(r["features_snapshot_json"]) for r in rows}
    assert snaps_by_mkt["moneyline"]["hours_to_tipoff"] == 6.0
    assert snaps_by_mkt["moneyline"]["effective_model_weight"] == expected_ml
    assert snaps_by_mkt["total_points"]["hours_to_tipoff"] == 6.0
    assert snaps_by_mkt["total_points"]["effective_model_weight"] == expected_tot


def test_early_morning_cron_added_without_closing_capture_collision() -> None:
    auto_raw = (PROJECT_ROOT / ".github" / "workflows" / "nba_cloud_automation.yml").read_text(encoding="utf-8")
    auto_wf = yaml.safe_load(auto_raw)
    closing_wf = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "closing_capture.yml").read_text(encoding="utf-8"))

    main_crons = [c["cron"] for c in (auto_wf.get("on") or auto_wf.get(True))["schedule"]]
    assert "15 11 * * *" in main_crons
    assert 'elif [ "$SCHEDULE" = "15 11 * * *" ] || [ "$SCHEDULE" = "15 15 * * *" ]' in auto_raw

    main_minutes = {c.split()[0] for c in main_crons}
    close_minutes = {
        m
        for c in (closing_wf.get("on") or closing_wf.get(True))["schedule"]
        for m in c["cron"].split()[0].split(",")
    }
    assert main_minutes.isdisjoint(close_minutes)
