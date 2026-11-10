"""
Unit and regression tests for Phase 1 Risk Configuration Centralization:
Validates that conviction tiers, Overtime Guard, CLV Governor bands, and Risk Modulators
are strictly controlled by config/model_config.yaml without any hardcoded drift.
"""

from __future__ import annotations

from pathlib import Path

from src.config import (
    CLVGovernorConfig,
    OvertimeGuardConfig,
    RiskConfig,
    load_config,
)
from src.paper_trading.engine import PaperTradingEngine
from src.storage.db import DatabaseManager


def test_phase1_config_loading_and_dataclasses() -> None:
    """Verifies that load_config cleanly instantiates typed risk dataclasses."""
    load_config.cache_clear()
    cfg = load_config()

    # Conviction tiers
    assert cfg.risk.conviction_tiers.aggressive.tier_star.base == 15.00
    assert cfg.risk.conviction_tiers.conservative.tier_star.base == 4.80
    assert cfg.risk.conviction_tiers.conservative.edge_modulator_floor == 0.20

    # Overtime Guard
    assert cfg.risk.overtime_guard.enabled is True
    assert cfg.risk.overtime_guard.min_overtime_prob == 0.068
    assert cfg.risk.overtime_guard.under_haircut == 0.85

    # CLV Governor
    assert cfg.risk.clv_governor.enabled is True
    assert cfg.risk.clv_governor.lookback_bets == 25
    assert cfg.risk.clv_governor.severe_negative_factor == 0.50
    assert cfg.risk.clv_governor.positive_alpha_factor == 1.10

    # Risk Modulators
    assert cfg.risk.risk_modulators.sharp_steam_factor == 1.08
    assert cfg.risk.risk_modulators.adverse_steam_factor == 0.85


def test_phase1_custom_overtime_guard_configuration(tmp_path: Path) -> None:
    """Verifies that custom overtime haircut in config directly governs stake reduction."""
    db = DatabaseManager(tmp_path / "test_ot.sqlite3")

    # Engine with custom 50% haircut
    custom_risk = RiskConfig(
        virtual_bankroll_initial_pen=100.0,
        staking_mode="fractional_kelly",
        kelly_fraction=0.50,
        min_stake_pen=1.00,
        max_stake_bankroll_fraction=0.10,
        base_stake_pen=1.00,
        max_stake_pen=10.00,
        max_selections_per_matchday=3,
        min_ev_threshold=0.05,
        max_portfolio_exposure_pct=0.30,
        allow_parlays=True,
        allow_player_props_betting=True,
        overtime_guard=OvertimeGuardConfig(enabled=True, min_overtime_prob=0.05, under_haircut=0.50),
    )
    engine = PaperTradingEngine(db=db, dynamic_conviction_staking=True, max_stake_pen=10.0, risk_config=custom_risk, enable_cppi_shield=False)

    # Standard stake with OT prob 0.06 (exceeds 0.05 threshold -> gets 50% haircut)
    stake_ot = engine.compute_contextual_stake_pen(
        calibrated_prob=0.54,
        decimal_odds=2.00,
        ev_unit=0.08,
        current_bankroll_pen=100.0,
        selection="UNDER",
        overtime_prob=0.06,
        apply_clv_governor=False,
    )

    # Standard stake without OT
    stake_normal = engine.compute_contextual_stake_pen(
        calibrated_prob=0.54,
        decimal_odds=2.00,
        ev_unit=0.08,
        current_bankroll_pen=100.0,
        selection="UNDER",
        overtime_prob=0.01,
        apply_clv_governor=False,
    )

    assert stake_ot < stake_normal
    assert round(stake_ot, 1) == round(stake_normal * 0.50, 1)


def test_phase1_custom_clv_governor_bands(tmp_path: Path) -> None:
    """Verifies that CLV Governor bands follow configuration dynamically."""
    db = DatabaseManager(tmp_path / "test_clv.sqlite3")

    # Insert mock closing odds and bets with -5% CLV
    from tests.test_nba_intelligence import _seed_sample_game_and_prediction
    for i in range(5):
        g_id = f"G_CLV_{i}"
        pred_id = _seed_sample_game_and_prediction(db, g_id)
        db.execute_insert(
            f"""
            INSERT INTO odds_snapshots (odds_id, game_id, provider, market, selection, line_value, decimal_odds, counterpart_decimal_odds, captured_at, is_closing_line, source_type)
            VALUES ('ODDS_{i}', '{g_id}', 'Pinnacle', 'moneyline', 'HOME', NULL, 2.00, 1.90, '2026-11-09T19:50:00Z', 1, 'OBSERVED')
            """
        )
        db.execute_insert(
            f"""
            INSERT INTO simulated_bets (bet_id, prediction_id, game_id, matchday_date, market, selection, decimal_odds, estimated_prob, estimated_ev, stake_pen, emitted_at, model_version_id, status, settled_at, net_profit_pen)
            VALUES ('BET_{i}', '{pred_id}', '{g_id}', '2026-11-09', 'moneyline', 'HOME', 1.90, 0.55, 0.05, 1.0, '2026-11-09T18:00:00Z', 'm', 'WON', '2026-11-09T23:00:00Z', 0.90)
            """
        )

    # Custom governor that penalizes negative CLV down to 0.25 (instead of 0.50)
    custom_risk = RiskConfig(
        virtual_bankroll_initial_pen=100.0,
        staking_mode="fractional_kelly",
        kelly_fraction=0.50,
        min_stake_pen=1.00,
        max_stake_bankroll_fraction=0.10,
        base_stake_pen=1.00,
        max_stake_pen=10.00,
        max_selections_per_matchday=3,
        min_ev_threshold=0.05,
        max_portfolio_exposure_pct=0.30,
        allow_parlays=True,
        allow_player_props_betting=True,
        clv_governor=CLVGovernorConfig(severe_negative_threshold=-2.0, severe_negative_factor=0.25),
    )
    engine = PaperTradingEngine(db=db, risk_config=custom_risk)
    factor, mean_clv = engine.get_recent_clv_governor_factor()

    assert mean_clv is not None and mean_clv < -2.0
    assert factor == 0.25
