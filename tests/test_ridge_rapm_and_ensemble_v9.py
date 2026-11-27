"""
Comprehensive unit, temporal-integrity, determinism, and edge-case tests for the V9 model upgrades:
- Simultaneous Multi-Horizon Time-Decayed Ridge Adjusted Efficiency + Prior-Informed Player RAPM (`RidgeEfficiencyRAPMModel`)
- Offseason reset, exact 48-min OT-debiased pace, participation-delta availability, and official OUT override parity
- Upgraded `PointMarginModel`, `TotalPointsModel`, `AdvancedGBMModel`, `DeepMonteCarloHybridModel`, and `EnsembleStackingModel`
- Empirical-Bayes Platt temperature calibration in `ProbabilityCalibrator`
"""

from __future__ import annotations

from copy import deepcopy
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
from src.models.ridge_rapm import RidgeEfficiencyRAPMModel
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
    assert cfg.evaluation.trials_evaluated_count == 12
    assert cfg.evaluation.frozen_protocol_id == "V9_FROZEN_2026_11_27"

    ens = EnsembleStackingModel()
    assert ens.version_id == "model_f_ensemble_v9"
    assert ens.model_b.version_id == "model_b_elo_v8"
    assert ens.model_c.version_id == "model_c_point_margin_v9"
    assert ens.model_d.version_id == "model_d_total_points_v9"
    assert ens.model_e.version_id == "model_e_lightgbm_v9"
    assert ens.model_g.version_id == "model_g_ml_montecarlo_v9"
    assert ens.model_h.version_id == "model_h_ridge_rapm_v9"
