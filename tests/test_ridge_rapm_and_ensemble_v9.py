"""
Comprehensive unit, temporal-integrity, determinism, and edge-case tests for the V9 model upgrades:
- Simultaneous Multi-Horizon Time-Decayed Ridge Adjusted Efficiency + Prior-Informed Player RAPM (`RidgeEfficiencyRAPMModel`)
- Offseason reset, exact 48-min OT-debiased pace, participation-delta availability, and official OUT override parity
- Upgraded `PointMarginModel`, `TotalPointsModel`, `AdvancedGBMModel`, `DeepMonteCarloHybridModel`, and `EnsembleStackingModel`
- Empirical-Bayes Platt temperature calibration in `ProbabilityCalibrator`
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.calibration.calibrator import ProbabilityCalibrator
from src.config import ConfigError, RidgeRAPMConfig, load_config, parse_config
from src.features.boxscore_features import (
    attach_boxscore_features,
    compute_boxscore_feature_bundle,
    compute_boxscore_features,
    player_name_key,
)
from src.ingestion.boxscores import load_boxscores
from src.models.ensemble import EnsembleStackingModel
from src.models.gbm_model import AdvancedGBMModel
from src.models.point_margin import PointMarginModel
from src.models.ridge_rapm import RidgeEfficiencyRAPMModel
from src.models.total_points import TotalPointsModel
from tests.helpers import connect_readonly_prod_db


def _make_box(
    home: str,
    away: str,
    h_pts: float,
    a_pts: float,
    h_players: list[tuple[str, float, float, bool]],
    a_players: list[tuple[str, float, float, bool]],
    *,
    fga: float = 88.0,
) -> dict[str, Any]:
    return {
        "teams": {
            home: {
                "fgm": 42.0,
                "fga": fga,
                "tpm": 13.0,
                "tpa": 36.0,
                "ftm": 15.0,
                "fta": 20.0,
                "orb": 10.0,
                "drb": 34.0,
                "tov": 12.0,
                "pts": h_pts,
            },
            away: {
                "fgm": 40.0,
                "fga": fga,
                "tpm": 12.0,
                "tpa": 35.0,
                "ftm": 14.0,
                "fta": 19.0,
                "orb": 9.0,
                "drb": 33.0,
                "tov": 13.0,
                "pts": a_pts,
            },
        },
        "players": {
            home: [{"name": n, "min": m, "pts": p, "starter": s} for n, m, p, s in h_players],
            away: [{"name": n, "min": m, "pts": p, "starter": s} for n, m, p, s in a_players],
        },
    }


def _load_real_sample(limit: int = 180) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    conn = connect_readonly_prod_db()
    games = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM games WHERE status = 'FINAL' AND home_score IS NOT NULL AND game_id NOT LIKE 'SYN%' "
            "ORDER BY game_start_time ASC, game_id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    ]
    conn.close()

    class _RoAdapter:
        def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
            c = connect_readonly_prod_db()
            try:
                return [dict(r) for r in c.execute(query, params).fetchall()]
            finally:
                c.close()

    boxes = load_boxscores(_RoAdapter())
    return games, boxes


def test_ridge_rapm_config_loading_and_validation() -> None:
    load_config.cache_clear()
    cfg = load_config()
    rr = cfg.model.ridge_rapm
    assert rr.enabled is True
    assert rr.slow_half_life_days == 45.0
    assert rr.fast_half_life_days == 18.0
    assert rr.player_rapm_half_life_days == 180.0
    assert rr.min_games_for_team_ridge == 30
    assert rr.min_games_for_player_rapm == 80

    # Out-of-range ridge_rapm parameter fails fast with ConfigError
    raw_bad = {
        "model": {
            "version_id": "test",
            "ewma_alpha_slow": 0.04,
            "ewma_alpha_fast": 0.12,
            "tempo_alpha_slow": 0.05,
            "tempo_alpha_fast": 0.12,
            "market_anchor_model_weight": 0.30,
            "ridge_rapm": {"slow_half_life_days": 0.5},
        },
        "risk_management": {
            "virtual_bankroll_initial_pen": 100.0,
            "staking_mode": "fractional_kelly",
            "kelly_fraction": 0.25,
            "min_stake_pen": 1.0,
            "max_stake_bankroll_fraction": 0.10,
            "base_stake_pen": 1.0,
            "max_stake_pen": 10.0,
            "max_selections_per_matchday": 3,
            "min_ev_threshold": 0.02,
            "max_portfolio_exposure_pct": 0.30,
            "allow_parlays": False,
            "allow_player_props_betting": False,
        },
        "sources": {"betting_allowed_source_types": ["OBSERVED"]},
    }
    with pytest.raises(ConfigError):
        parse_config(raw_bad)


def test_boxscore_offseason_reset_and_exact_ot_regulation_pace() -> None:
    star_roster_s1 = [
        ("Departed Star", 36.0, 28.0, True),
        ("Core Wing", 34.0, 18.0, True),
        ("Center A", 30.0, 12.0, True),
        ("Guard B", 30.0, 14.0, True),
        ("Forward C", 30.0, 10.0, True),
        ("Bench 1", 40.0, 12.0, False),
        ("Bench 2", 40.0, 10.0, False),
    ]
    opp_roster = [
        ("Opp 1", 35.0, 22.0, True),
        ("Opp 2", 35.0, 18.0, True),
        ("Opp 3", 35.0, 16.0, True),
        ("Opp 4", 35.0, 14.0, True),
        ("Opp 5", 35.0, 12.0, True),
        ("Opp 6", 65.0, 20.0, False),
    ]
    # 1OT game has 265 total team minutes -> reg_pace must be scaled down by 240/265!
    ot_home_roster = [(n, m * (265.0 / 240.0), p, s) for n, m, p, s in star_roster_s1]
    ot_opp_roster = [(n, m * (265.0 / 240.0), p, s) for n, m, p, s in opp_roster]

    games: list[dict[str, Any]] = []
    boxes: dict[str, dict[str, Any]] = {}
    for i in range(4):
        gid = f"S1_G{i}"
        games.append(
            {
                "game_id": gid,
                "game_start_time": f"2025-04-0{i + 1}T00:00:00Z",
                "status": "FINAL",
                "home_team": "BOS",
                "away_team": "NYK",
            }
        )
        # Make game 3 an OT game with inflated FGA=105 (raw poss ~ 117, reg poss ~ 106)
        if i == 3:
            boxes[gid] = _make_box("BOS", "NYK", 128.0, 124.0, ot_home_roster, ot_opp_roster, fga=105.0)
        else:
            boxes[gid] = _make_box("BOS", "NYK", 112.0, 106.0, star_roster_s1, opp_roster, fga=88.0)

    # Check OT game exact 48-min regulation pace vs raw pace in post_obs
    bundle = compute_boxscore_feature_bundle(games, boxes)
    ot_obs = bundle["S1_G3"]["_bx_post_obs"]
    assert ot_obs["reg_pace"] < 110.0  # scaled down by 240/265 from ~116 raw possessions

    # Now add a Season 2 game > 60 days later where "Departed Star" is no longer on BOS
    s2_roster = [r for r in star_roster_s1 if r[0] != "Departed Star"] + [("New Rookie", 36.0, 16.0, True)]
    games.append(
        {
            "game_id": "S2_G0",
            "game_start_time": "2025-10-22T23:00:00Z",
            "status": "FINAL",
            "home_team": "BOS",
            "away_team": "NYK",
        }
    )
    boxes["S2_G0"] = _make_box("BOS", "NYK", 110.0, 105.0, s2_roster, opp_roster)
    games.append(
        {
            "game_id": "S2_G1",
            "game_start_time": "2025-10-25T23:00:00Z",
            "status": "SCHEDULED",
            "home_team": "BOS",
            "away_team": "NYK",
        }
    )
    feats_s2 = compute_boxscore_features(games, boxes)
    # Offseason reset clears S1 roster so Departed Star MUST NOT count as missing in S2
    assert feats_s2["S2_G1"]["bx_missing_pts_diff"] == 0.0
    assert feats_s2["S2_G1"]["bx_unpriced_pts_diff"] == 0.0


def test_official_out_override_updates_unpriced_availability_and_rapm_lineup() -> None:
    roster = [
        ("Super Star", 36.0, 30.0, True),
        ("Solid Wing", 32.0, 16.0, True),
        ("Big Man", 30.0, 14.0, True),
        ("Guard Two", 30.0, 12.0, True),
        ("Forward Two", 28.0, 10.0, True),
        ("Sixth Man", 24.0, 10.0, False),
    ]
    opp = [
        ("Opp One", 34.0, 20.0, True),
        ("Opp Two", 32.0, 16.0, True),
        ("Opp Three", 30.0, 14.0, True),
        ("Opp Four", 30.0, 12.0, True),
        ("Opp Five", 28.0, 10.0, True),
        ("Opp Six", 26.0, 8.0, False),
    ]
    games, boxes = [], {}
    for i in range(5):
        gid = f"AV_{i}"
        games.append(
            {
                "game_id": gid,
                "game_start_time": f"2026-11-0{i + 1}T00:00:00Z",
                "status": "FINAL",
                "home_team": "DEN",
                "away_team": "POR",
            }
        )
        boxes[gid] = _make_box("DEN", "POR", 118.0, 106.0, roster, opp)
    games.append(
        {
            "game_id": "NEXT_G",
            "game_start_time": "2026-11-10T01:00:00Z",
            "status": "SCHEDULED",
            "home_team": "DEN",
            "away_team": "POR",
        }
    )

    bundle_healthy = compute_boxscore_feature_bundle(games, boxes)
    overrides = {"NEXT_G": {"DEN": frozenset({player_name_key("Super Star")}), "POR": frozenset()}}
    bundle_out = compute_boxscore_feature_bundle(games, boxes, availability_overrides=overrides)

    assert bundle_out["NEXT_G"]["bx_unpriced_pts_diff"] < bundle_healthy["NEXT_G"]["bx_unpriced_pts_diff"]
    assert bundle_out["NEXT_G"]["bx_lineup_prior_diff"] < bundle_healthy["NEXT_G"]["bx_lineup_prior_diff"]
    h_shares_healthy, _ = bundle_healthy["NEXT_G"]["_bx_exp_lineup"]
    h_shares_out, _ = bundle_out["NEXT_G"]["_bx_exp_lineup"]
    assert "Super Star" in h_shares_healthy
    assert "Super Star" not in h_shares_out
    assert abs(sum(h_shares_out.values()) - 5.0) < 1e-6


def test_zero_lookahead_and_bit_identical_determinism_on_real_nba_games() -> None:
    games, boxes = _load_real_sample(limit=180)
    enriched = attach_boxscore_features(games, boxes)
    target = enriched[160]
    cutoff = str(target["game_start_time"])
    prior = enriched[:160]

    # 1. Bit-identical determinism across two independent fits
    m1 = EnsembleStackingModel("model_f_ensemble_v9_test")
    m2 = EnsembleStackingModel("model_f_ensemble_v9_test")
    m1.fit(prior, cutoff)
    m2.fit(prior, cutoff)
    assert m1.model_h.is_fitted is True
    assert m1.model_h.rapm_fitted is True
    assert m1.model_c.uses_enhanced_features is True
    assert m1.model_d.uses_enhanced_features is True
    assert m1.model_e.uses_enhanced_features is True

    ml1 = m1.predict_moneyline(target, prior)
    ml2 = m2.predict_moneyline(target, prior)
    tot1 = m1.predict_total_points(target, prior, 224.5)
    tot2 = m2.predict_total_points(target, prior, 224.5)
    sp1 = m1.predict_spread(target, prior, -4.5)
    sp2 = m2.predict_spread(target, prior, -4.5)

    assert abs(ml1["p_home"] - ml2["p_home"]) <= 1e-12
    assert abs(tot1["p_over"] - tot2["p_over"]) <= 1e-12
    assert abs(sp1["p_cover_home"] - sp2["p_cover_home"]) <= 1e-12
    assert "p_ridge_rapm" in ml1

    # 2. Zero lookahead: mutating target's own post-game observation AND future games must change NOTHING
    target_tampered = deepcopy(target)
    target_tampered["_bx_post_obs"] = {
        "reg_pace": 140.0,
        "h_ortg": 190.0,
        "a_ortg": 60.0,
        "h_ortg_la": 190.0,
        "a_ortg_la": 60.0,
        "home_shares": {"Fake": 5.0},
        "away_shares": {"Fake2": 5.0},
        "prior_mar_offset": 50.0,
    }
    ml_tamp = m1.predict_moneyline(target_tampered, prior)
    tot_tamp = m1.predict_total_points(target_tampered, prior, 224.5)
    assert ml_tamp["p_home"] == ml1["p_home"]
    assert tot_tamp["p_over"] == tot1["p_over"]

    # Mutating future games beyond cutoff passed into fit() must produce identical model
    with_future = deepcopy(enriched)
    for fg in with_future[160:]:
        fg["home_score"] = 250
        fg["away_score"] = 50
    m3 = EnsembleStackingModel("model_f_ensemble_v9_test")
    m3.fit(with_future, cutoff)
    ml3 = m3.predict_moneyline(target, prior)
    tot3 = m3.predict_total_points(target, prior, 224.5)
    assert abs(ml3["p_home"] - ml1["p_home"]) <= 1e-12
    assert abs(tot3["p_over"] - tot1["p_over"]) <= 1e-12


def test_graceful_fallbacks_empty_small_and_unseen_teams() -> None:
    target = {
        "game_id": "EDGE_1",
        "season": "2026-27",
        "matchday_date": "2026-11-10",
        "game_start_time": "2026-11-10T23:00:00Z",
        "home_team": "SEA",  # unseen team code
        "away_team": "VAN",  # unseen team code
        "status": "SCHEDULED",
        "home_off_rtg": 114.0,
        "home_def_rtg": 114.0,
        "home_pace": 99.5,
        "away_off_rtg": 114.0,
        "away_def_rtg": 114.0,
        "away_pace": 99.5,
        "home_rest_days": 2,
        "away_rest_days": 2,
    }

    # Empty history
    ens_empty = EnsembleStackingModel("edge_empty")
    ens_empty.fit([], "2026-11-10T23:00:00Z")
    ml_e = ens_empty.predict_moneyline(target, [])
    tot_e = ens_empty.predict_total_points(target, [], 228.0)  # integer line -> push mass > 0
    sp_e = ens_empty.predict_spread(target, [], -3.0)  # integer spread -> push mass > 0
    assert 0.03 <= ml_e["p_home"] <= 0.97
    assert abs(tot_e["p_over"] + tot_e["p_under"] + tot_e["p_push"] - 1.0) < 1e-4
    assert tot_e["p_push"] > 0.0
    assert abs(sp_e["p_cover_home"] + sp_e["p_cover_away"] + sp_e["p_push"] - 1.0) < 1e-4
    assert sp_e["p_push"] > 0.0

    # Disabled ridge_rapm config degrades cleanly
    rr_disabled = RidgeEfficiencyRAPMModel("rr_off", config=RidgeRAPMConfig(enabled=False))
    games, _ = _load_real_sample(limit=60)
    rr_disabled.fit(games[:50], str(games[50]["game_start_time"]))
    assert rr_disabled.is_fitted is False
    pred_off = rr_disabled.predict_matchup(games[50], games[:50])
    assert pred_off["is_fitted"] == 0.0


def test_calibrator_removes_overconfidence_on_large_sample_while_protecting_small_sample() -> None:
    from datetime import datetime, timedelta, timezone

    rng = np.random.default_rng(7)
    # Simulate an overconfident totals model whose true logit slope is 0.35 on N=400
    n = 400
    raw_logits = rng.normal(0.0, 0.7, size=n)
    raw_probs = 1.0 / (1.0 + np.exp(-raw_logits))
    true_probs = 1.0 / (1.0 + np.exp(-0.35 * raw_logits))
    outcomes = (rng.random(size=n) < true_probs).astype(int)
    base_dt = datetime(2025, 1, 1, 23, 0, tzinfo=timezone.utc)
    recs = [
        {
            "game_start_time": (base_dt + timedelta(hours=12 * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "raw_probability": float(raw_probs[i]),
            "outcome": int(outcomes[i]),
        }
        for i in range(n)
    ]

    cal = ProbabilityCalibrator(method="logistic", min_samples_logistic=25)
    cal.fit(recs, "2026-12-31T00:00:00Z")
    # Must be able to shrink below the legacy 0.70 floor!
    assert cal.eff_slope < 0.65
    # Overconfident p=0.70 should calibrate strongly toward 0.50
    cal_70 = cal.transform_single(0.70)
    assert 0.52 <= cal_70 <= 0.62


def test_player_name_key_diacritics_and_generational_suffixes() -> None:
    assert player_name_key("Nikola Jokić") == player_name_key("Nikola Jokic")
    assert player_name_key("Luka Dončić") == player_name_key("Luka Doncic")
    assert player_name_key("Alperen Şengün") == player_name_key("Alperen Sengun")
    assert player_name_key("Ernest Udeh Jr.") == player_name_key("Jr., Ernest Udeh")
    assert player_name_key("Jaren Jackson Jr.") == player_name_key("Jaren Jackson")
    assert player_name_key("Gary Payton II") == player_name_key("Gary Payton")

    # End-to-end official OUT override with accented & inverted-suffix injury PDF names
    roster = [
        ("Nikola Jokic", 36.0, 29.0, True),
        ("Ernest Udeh Jr.", 22.0, 12.0, False),
        ("Wing One", 34.0, 16.0, True),
        ("Guard One", 32.0, 15.0, True),
        ("Forward One", 30.0, 12.0, True),
        ("Center Two", 26.0, 10.0, False),
        ("Bench Guard", 60.0, 14.0, False),
    ]
    opp = [
        ("Opp A", 36.0, 20.0, True),
        ("Opp B", 34.0, 18.0, True),
        ("Opp C", 32.0, 16.0, True),
        ("Opp D", 30.0, 14.0, True),
        ("Opp E", 28.0, 12.0, True),
        ("Opp F", 80.0, 24.0, False),
    ]
    games, boxes = [], {}
    for i in range(4):
        gid = f"NM_{i}"
        games.append(
            {
                "game_id": gid,
                "game_start_time": f"2026-11-0{i + 1}T00:00:00Z",
                "status": "FINAL",
                "home_team": "DEN",
                "away_team": "POR",
            }
        )
        boxes[gid] = _make_box("DEN", "POR", 116.0, 108.0, roster, opp)
    games.append(
        {
            "game_id": "NM_NEXT",
            "game_start_time": "2026-11-08T01:00:00Z",
            "status": "SCHEDULED",
            "home_team": "DEN",
            "away_team": "POR",
        }
    )
    overrides = {
        "NM_NEXT": {
            "DEN": frozenset({player_name_key("Nikola Jokić"), player_name_key("Jr., Ernest Udeh")}),
            "POR": frozenset(),
        }
    }
    bundle = compute_boxscore_feature_bundle(games, boxes, availability_overrides=overrides)
    h_shares, _ = bundle["NM_NEXT"]["_bx_exp_lineup"]
    assert "Nikola Jokic" not in h_shares
    assert "Ernest Udeh Jr." not in h_shares
    assert bundle["NM_NEXT"]["bx_missing_pts_diff"] < -35.0


def test_rapm_off_def_totals_causal_ot_and_mixed_iso_oof_safety() -> None:
    games, boxes = _load_real_sample(limit=180)
    enriched = attach_boxscore_features(games, boxes)
    target = enriched[165]
    cutoff = str(target["game_start_time"])
    prior = enriched[:165]

    rr_box = RidgeEfficiencyRAPMModel("rr_box_check")
    rr_box.fit(prior, cutoff)
    assert rr_box.is_fitted is True
    assert rr_box.rapm_fitted is True
    assert rr_box.od_rapm_fitted is True
    assert rr_box._ot_add > 0.0
    pred_box = rr_box.predict_matchup(target, prior)
    assert 180.0 <= pred_box["rapm_total"] <= 270.0

    # Score-only fallback (no boxscores): _ot_add must be 0.0 so OT points are not double-counted
    rr_score_only = RidgeEfficiencyRAPMModel("rr_score_only")
    rr_score_only.fit(games[:165], cutoff)
    assert rr_score_only.is_fitted is True
    assert rr_score_only.rapm_fitted is False
    assert rr_score_only._ot_add == 0.0

    # Mixed ISO-8601 timestamp format (+00:00 vs Z) must not break strict temporal ordering in OOF
    mixed_prior = deepcopy(prior)
    for idx in range(0, len(mixed_prior), 2):
        mixed_prior[idx]["game_start_time"] = str(mixed_prior[idx]["game_start_time"]).replace("Z", "+00:00")
    oof_std = rr_box.compute_expanding_oof_predictions(prior, prior, {}, min_warmup=60, n_folds=4)
    oof_mix = rr_box.compute_expanding_oof_predictions(mixed_prior, mixed_prior, {}, min_warmup=60, n_folds=4)
    assert set(oof_std.keys()) == set(oof_mix.keys())
    for k in sorted(oof_std.keys())[:10]:
        assert abs(oof_std[k]["ridge_margin_slow"] - oof_mix[k]["ridge_margin_slow"]) <= 1e-9


def test_fisher_scaled_calibrator_protects_well_calibrated_moneyline_small_sample() -> None:
    from datetime import datetime, timedelta, timezone

    rng = np.random.default_rng(19)
    n = 60
    raw_logits = rng.normal(0.0, 0.95, size=n)
    raw_probs = 1.0 / (1.0 + np.exp(-raw_logits))
    outcomes = (rng.random(size=n) < raw_probs).astype(int)
    base_dt = datetime(2025, 1, 1, 23, 0, tzinfo=timezone.utc)
    recs = [
        {
            "game_start_time": (base_dt + timedelta(hours=12 * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "raw_probability": float(raw_probs[i]),
            "outcome": int(outcomes[i]),
        }
        for i in range(n)
    ]
    cal = ProbabilityCalibrator(method="auto", min_samples_logistic=25)
    cal.fit(recs, "2026-12-31T00:00:00Z")
    assert 0.80 <= cal.eff_slope <= 1.20
    assert abs(cal.eff_intercept) <= 0.02


def test_v9_version_promotion_and_submodel_isolation() -> None:
    load_config.cache_clear()
    cfg = load_config()
    assert cfg.model.version_id == "model_f_ensemble_v9"
    assert cfg.evaluation.trials_evaluated_count == 20
    assert cfg.evaluation.frozen_protocol_id == "V9_FROZEN_2026_11_27"

    ens = EnsembleStackingModel()
    assert ens.version_id == "model_f_ensemble_v9"
    assert ens.model_b.version_id == "model_b_elo_v8"
    assert ens.model_c.version_id == "model_c_point_margin_v9"
    assert ens.model_d.version_id == "model_d_total_points_v9"
    assert ens.model_e.version_id == "model_e_lightgbm_v9"
    assert ens.model_g.version_id == "model_g_ml_montecarlo_v9"
    assert ens.model_h.version_id == "model_h_ridge_rapm_v9"

    # Standalone submodel defaults also match V9
    assert PointMarginModel().version_id == "model_c_point_margin_v9"
    assert TotalPointsModel().version_id == "model_d_total_points_v9"
    assert AdvancedGBMModel().version_id == "model_e_lightgbm_v9"


def test_reconstruct_comparison_records_strict_version_isolation(tmp_path: Path) -> None:
    from src.backtesting.backtester import WalkForwardBacktester
    from src.backtesting.walk_forward_helpers import reconstruct_comparison_records_from_db
    from src.paper_trading.engine import PaperTradingEngine
    from src.storage.db import DatabaseManager

    db = DatabaseManager(tmp_path / "v8_v9_iso.sqlite3")
    for ver in ("model_f_ensemble_v8", "model_f_ensemble_v9"):
        db.execute_insert(
            "INSERT INTO model_versions (model_version_id, model_family, market, train_start_date, train_end_date, trained_at, hyperparameters_json, approved_by) "
            "VALUES (?, 'model_f_meta_ensemble', 'moneyline', '2026-01-01', '2026-11-27', '2026-11-27T00:00:00Z', '{}', 'test')",
            (ver,),
        )

    games_spec = [
        ("G_V8_ONLY", "2026-11-20", "2026-11-21T00:00:00Z", "BOS", "NYK", 118, 102, "model_f_ensemble_v8", 0.30, 0.30),
        ("G_V9_ONLY", "2026-11-27", "2026-11-28T00:00:00Z", "DEN", "POR", 120, 105, "model_f_ensemble_v9", 0.85, 0.85),
    ]
    for idx, (gid, mdate, gtime, ht, at, hs, as_, ver, p_ml, p_tot) in enumerate(games_spec):
        db.execute_insert(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
                away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
                features_available_at, source_provider, ingested_at
            ) VALUES (?, '2026-27', ?, ?, ?, ?, 'FINAL', ?, ?, 115.0, 111.0, 99.0, 113.0, 112.0, 98.5, 2, 2, '2026-11-19T12:00:00Z', 'espn', '2026-11-19T12:00:00Z')
            """,
            (gid, mdate, gtime, ht, at, hs, as_),
        )
        db.execute_insert(
            """
            INSERT INTO predictions (
                prediction_id, game_id, market, selection, model_version_id, raw_probability,
                calibrated_probability, uncertainty_std, implied_prob_gross, implied_prob_fair,
                decimal_odds_used, odds_provider, odds_captured_at, ev_unit, ev_pct, emitted_at,
                features_snapshot_json, raw_model_probability, calibrated_model_probability,
                market_fair_probability, market_anchored_probability
            ) VALUES (?, ?, 'moneyline', 'HOME', ?, ?, ?, 0.05, 0.52, 0.50, 1.95, 'Pinnacle', '2026-11-19T20:00:00Z', 0.02, 2.0, '2026-11-19T20:00:00Z', '{}', ?, ?, 0.50, ?)
            """,
            (f"PM_{idx}", gid, ver, p_ml, p_ml, p_ml, p_ml, p_ml),
        )
        db.execute_insert(
            """
            INSERT INTO predictions (
                prediction_id, game_id, market, selection, line_value, model_version_id, raw_probability,
                calibrated_probability, uncertainty_std, implied_prob_gross, implied_prob_fair,
                decimal_odds_used, odds_provider, odds_captured_at, ev_unit, ev_pct, emitted_at,
                features_snapshot_json, raw_model_probability, calibrated_model_probability,
                market_fair_probability, market_anchored_probability
            ) VALUES (?, ?, 'total_points', 'OVER', 218.5, ?, ?, ?, 0.05, 0.52, 0.50, 1.92, 'Pinnacle', '2026-11-19T20:00:00Z', 0.02, 2.0, '2026-11-19T20:00:00Z', '{}', ?, ?, 0.50, ?)
            """,
            (f"PT_{idx}", gid, ver, p_tot, p_tot, p_tot, p_tot, p_tot),
        )

    all_recs = reconstruct_comparison_records_from_db(db)
    v9_recs = reconstruct_comparison_records_from_db(db, model_version_id="model_f_ensemble_v9")
    v8_recs = reconstruct_comparison_records_from_db(db, model_version_id="model_f_ensemble_v8")
    assert len(all_recs) == 2
    assert [r["game_id"] for r in v9_recs] == ["G_V9_ONLY"]
    assert [r["game_id"] for r in v8_recs] == ["G_V8_ONLY"]

    bt = WalkForwardBacktester(db, PaperTradingEngine(db))
    m_v9 = bt.compute_comprehensive_metrics(model_version_id="model_f_ensemble_v9", closing_rows=[])
    assert m_v9["model_comparison_sample_size"] == 1
    # V9 predicted 0.85 on winning home team (120-105, total 225 > 218.5) => Brier = (0.85 - 1.0)^2 = 0.0225
    assert abs(float(m_v9["overall_brier_score"]) - 0.0225) < 1e-6

    # Dashboard markdown fallback (metrics=None) must also isolate to active config version (never mixing V8)
    from src.reporting.dashboard_export import generate_bet_tracking_markdown

    md_out = generate_bet_tracking_markdown(db)
    assert "Modelo 0.0225 vs Mercado 0.2500 (N=1)" in md_out


def test_expected_lineup_shares_no_train_serving_skew_on_official_report() -> None:
    core = [
        ("Starter A", 36.0, 26.0, True),
        ("Starter B", 34.0, 20.0, True),
        ("Starter C", 32.0, 16.0, True),
        ("Starter D", 30.0, 14.0, True),
        ("Starter E", 28.0, 12.0, True),
        ("Bench 1", 22.0, 10.0, False),
        ("Bench 2", 20.0, 8.0, False),
        ("Bench 3", 19.0, 6.0, False),
        ("Bench 4", 19.0, 4.0, False),
    ]
    garbage = [
        ("Garbage 1", 4.0, 1.0, False),
        ("Garbage 2", 3.0, 1.0, False),
        ("Garbage 3", 3.0, 0.0, False),
    ]
    opp = [
        ("Opp A", 36.0, 22.0, True),
        ("Opp B", 34.0, 18.0, True),
        ("Opp C", 32.0, 16.0, True),
        ("Opp D", 30.0, 14.0, True),
        ("Opp E", 28.0, 12.0, True),
        ("Opp F", 80.0, 24.0, False),
    ]

    games, boxes = [], {}
    for i in range(4):
        gid = f"SK_{i}"
        games.append(
            {
                "game_id": gid,
                "game_start_time": f"2026-11-0{i + 1}T00:00:00Z",
                "status": "FINAL",
                "home_team": "BOS",
                "away_team": "MIA",
            }
        )
        # Garbage-time fringe players only appeared in game 1 (blowout), not in last game (i == 3)
        roster = core + garbage if i == 1 else core
        boxes[gid] = _make_box("BOS", "MIA", 116.0, 106.0, roster, opp)

    games.append(
        {
            "game_id": "SK_NEXT",
            "game_start_time": "2026-11-06T00:00:00Z",
            "status": "SCHEDULED",
            "home_team": "BOS",
            "away_team": "MIA",
        }
    )

    b_none = compute_boxscore_feature_bundle(games, boxes, availability_overrides=None)
    b_empty_report = compute_boxscore_feature_bundle(
        games,
        boxes,
        availability_overrides={"SK_NEXT": {"BOS": frozenset(), "MIA": frozenset()}},
    )
    h_none, _ = b_none["SK_NEXT"]["_bx_exp_lineup"]
    h_empty, _ = b_empty_report["SK_NEXT"]["_bx_exp_lineup"]

    # Empty official OUT list must match training bit-for-bit (no garbage-time dilution!)
    assert h_empty == h_none
    assert "Garbage 1" not in h_empty
    assert abs(sum(h_empty.values()) - 5.0) < 1e-6

    # Even when a rotation player missed the last game (e.g. injured/questionable/resting),
    # an empty official OUT list must preserve exact train/serving parity with no-override path
    # (no serving-only restoration skew).
    boxes_rest = deepcopy(boxes)
    boxes_rest["SK_3"] = _make_box("BOS", "MIA", 112.0, 106.0, [p for p in core if p[0] != "Starter A"], opp)
    b_rest_none = compute_boxscore_feature_bundle(games, boxes_rest, availability_overrides=None)
    b_rest_empty = compute_boxscore_feature_bundle(
        games,
        boxes_rest,
        availability_overrides={"SK_NEXT": {"BOS": frozenset(), "MIA": frozenset()}},
    )
    h_rest_none, _ = b_rest_none["SK_NEXT"]["_bx_exp_lineup"]
    h_rest_empty, _ = b_rest_empty["SK_NEXT"]["_bx_exp_lineup"]
    assert h_rest_empty == h_rest_none
    assert "Starter A" not in h_rest_empty
    assert "Garbage 1" not in h_rest_empty

    # Newly ruled OUT player from last game is excluded and remaining shares re-normalize to 5.0
    b_out_star = compute_boxscore_feature_bundle(
        games,
        boxes,
        availability_overrides={"SK_NEXT": {"BOS": frozenset({player_name_key("Starter A")}), "MIA": frozenset()}},
    )
    h_out_star, _ = b_out_star["SK_NEXT"]["_bx_exp_lineup"]
    assert "Starter A" not in h_out_star
    assert "Starter B" in h_out_star
    assert abs(sum(h_out_star.values()) - 5.0) < 1e-6


def test_augment_resolved_calibration_deduplicates_live_games_and_per_market(tmp_path: Path) -> None:
    from scripts.run_cloud_cycle import _augment_resolved_calibration_from_walk_forward
    from src.storage.db import DatabaseManager

    games, boxes = _load_real_sample(limit=175)
    enriched = attach_boxscore_features(games, boxes)
    db = DatabaseManager(tmp_path / "cal_aug.sqlite3")

    last_10 = enriched[-10:]
    live_ml = [
        {
            "game_id": str(g["game_id"]),
            "raw_probability": 0.612345,
            "game_start_time": str(g["game_start_time"]),
            "result_recorded_at": None,
            "outcome": 1 if int(g["home_score"]) > int(g["away_score"]) else 0,
        }
        for g in last_10
    ]
    live_tot: list[dict[str, Any]] = []
    live_sp: list[dict[str, Any]] = []
    cutoff_after = "2030-01-01T00:00:00Z"

    _augment_resolved_calibration_from_walk_forward(db, enriched, live_ml, live_tot, live_sp, cutoff_after)
    ml_gids = [str(r["game_id"]) for r in live_ml]
    assert len(ml_gids) == len(set(ml_gids)), "Live games must never be duplicated by walk-forward augmentation"
    assert len(ml_gids) == 65
    # Verify original live probabilities for those 10 games were preserved untouched
    preserved = {str(r["game_id"]): r["raw_probability"] for r in live_ml if str(r["game_id"]) in {str(g["game_id"]) for g in last_10}}
    assert len(preserved) == 10
    assert all(abs(v - 0.612345) < 1e-9 for v in preserved.values())


def test_slate_intelligence_uses_boxscore_rapm_features(tmp_path: Path) -> None:
    import json
    from datetime import timedelta
    from src.reporting.slate_intelligence import compute_upcoming_slate_intelligence
    from src.storage.db import DatabaseManager
    from src.validation.validator import parse_iso_utc

    games, boxes = _load_real_sample(limit=150)
    db = DatabaseManager(tmp_path / "slate_v9.sqlite3")
    with db.connect() as conn:
        for idx, g in enumerate(games):
            is_last = idx == len(games) - 1
            gid = f"ESPN_TEST_{idx}" if is_last else str(g["game_id"])
            status = "SCHEDULED" if is_last else "FINAL"
            hs = None if is_last else g["home_score"]
            as_ = None if is_last else g["away_score"]
            conn.execute(
                """
                INSERT INTO games (
                    game_id, season, matchday_date, game_start_time, home_team, away_team,
                    status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
                    away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
                    features_available_at, source_provider, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'espn', '2025-01-01T00:00:00Z')
                """,
                (
                    gid,
                    g["season"],
                    g["matchday_date"],
                    g["game_start_time"],
                    g["home_team"],
                    g["away_team"],
                    status,
                    hs,
                    as_,
                    g["home_off_rtg"],
                    g["home_def_rtg"],
                    g["home_pace"],
                    g["away_off_rtg"],
                    g["away_def_rtg"],
                    g["away_pace"],
                    g["home_rest_days"],
                    g["away_rest_days"],
                    g["features_available_at"],
                ),
            )
            if not is_last and str(g["game_id"]) in boxes:
                bx = boxes[str(g["game_id"])]
                conn.execute(
                    "INSERT INTO game_boxscores (game_id, team_stats_json, players_json, source, fetched_at) VALUES (?, ?, ?, 'espn', ?)",
                    (str(g["game_id"]), json.dumps(bx["teams"]), json.dumps(bx["players"]), "2025-01-01T00:00:00Z"),
                )

    slate = compute_upcoming_slate_intelligence(db)
    assert len(slate) == 1

    # Compare directly against EnsembleStackingModel enriched with compute_boxscore_feature_bundle
    obs_all = db.fetch_all("SELECT * FROM v_observed_games ORDER BY game_start_time ASC")
    bx_map = compute_boxscore_feature_bundle(obs_all, boxes)
    finals_enr = [{**g, **bx_map.get(g["game_id"], {})} for g in obs_all if g["status"] == "FINAL"]
    sched_enr = [{**g, **bx_map.get(g["game_id"], {})} for g in obs_all if g["status"] == "SCHEDULED"][0]

    ens = EnsembleStackingModel(load_config().model.version_id)
    fit_cutoff = (parse_iso_utc(str(finals_enr[-1]["game_start_time"])) + timedelta(seconds=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    ens.fit(finals_enr, fit_cutoff)
    assert ens.model_h.rapm_fitted is True
    expected_ml = ens.predict_moneyline(sched_enr, finals_enr)
    assert slate[0]["projections"]["expected_margin"] == expected_ml["expected_margin"]
    assert slate[0]["projections"]["p_home_pct"] == round(expected_ml["p_home"] * 100.0, 1)
