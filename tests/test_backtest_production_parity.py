"""
Parity between production decisions and the evaluation paths that judge them.

The live cycle, the real-odds backtest and the fallback out-of-sample comparisons must evaluate one policy:
the same market anchor schedule, steam handling and pre-bet guards (`config.execution`). These tests fail if
production and an evaluation path compute different market-anchored probabilities for the same inputs.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import scripts.cloud_cycle_calibration as oos_mod
from scripts.cloud_cycle_helpers import (
    build_walk_forward_oos_comparisons_for_active_model,
    evaluate_scheduled_slate_candidates,
)
import src.backtesting.real_odds_backtest as bt_mod
from src.backtesting.real_odds_backtest import (
    DECISION_LEAD_HOURS,
    OpeningPriceDecisionPolicy,
    evaluate_opening_price_side,
    load_market_rows,
    opening_line_hours_to_tipoff,
    opening_quote_record,
    render_markdown,
    run_real_odds_backtest,
)
from src.calibration.calibrator import ProbabilityCalibrator, VennAbersConformalInterval
from src.config import load_config
from src.models.statistical_models import EnsembleStackingModel
from src.paper_trading.execution_helpers import check_candidate_edge_and_model_guards
from src.prediction.ev_calculator import resolve_market_anchor_weight
from src.storage.db import DatabaseManager
from tests.helpers import PROJECT_ROOT, connect_readonly_prod_db

_ISO = "%Y-%m-%dT%H:%M:%SZ"
_GAME_ID = "ESPN_99001_2026-11-24_MIA_AT_BOS"
_START_DT = datetime(2026, 11, 24, 23, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime(_ISO)


def _runner_policy(vig: float = 0.045) -> OpeningPriceDecisionPolicy:
    """The decision policy `scripts/run_real_odds_backtest.py` hands the backtest: production's configuration."""
    cfg = load_config()
    schedule = cfg.model.anchor_schedule
    return OpeningPriceDecisionPolicy(
        model_version_id=cfg.model.version_id,
        anchor_schedule=schedule,
        market_anchor_weight=cfg.model.market_anchor_model_weight,
        moneyline_weight=cfg.model.moneyline_model_weight,
        max_disagreement=cfg.model.max_model_market_disagreement,
        moneyline_max_disagreement=cfg.model.moneyline_max_disagreement,
        moneyline_max_odds=cfg.model.moneyline_max_odds,
        vig=vig,
        hours_to_tipoff=opening_line_hours_to_tipoff(schedule),
    )


def _seed_scheduled_game(db: DatabaseManager, quotes: list[tuple[str, str, str, float | None, float, float, str]]) -> None:
    cfg = load_config()
    with db.connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO model_versions (
                model_version_id, model_family, market, train_start_date, train_end_date,
                trained_at, hyperparameters_json, approved_by
            ) VALUES (?, 'ensemble', 'moneyline', '2025-10-01', '2026-11-20', '2026-11-20T00:00:00Z', '{}', 'test')
            """,
            (cfg.model.version_id,),
        )
        conn.execute(
            """
            INSERT INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, home_score, away_score,
                home_off_rtg, home_def_rtg, home_pace,
                away_off_rtg, away_def_rtg, away_pace,
                home_rest_days, away_rest_days,
                features_available_at, source_provider, ingested_at
            ) VALUES (?, '2026-27', '2026-11-24', ?, 'BOS', 'MIA', 'SCHEDULED', NULL, NULL,
                      116.0, 110.5, 99.2, 112.5, 113.0, 98.8, 2, 2,
                      '2026-11-24T08:00:00Z', 'espn', '2026-11-24T08:00:00Z')
            """,
            (_GAME_ID, _iso(_START_DT)),
        )
        for odds_id, mkt, sel, lv, dec, cp, cap in quotes:
            conn.execute(
                """
                INSERT INTO odds_snapshots (
                    odds_id, game_id, provider, market, selection, line_value,
                    decimal_odds, counterpart_decimal_odds, captured_at, is_closing_line, source_type
                ) VALUES (?, ?, 'Pinnacle [LIVE_API]', ?, ?, ?, ?, ?, ?, 0, 'OBSERVED')
                """,
                (odds_id, _GAME_ID, mkt, sel, lv, dec, cp, cap),
            )


def _production_decisions(db: DatabaseManager, now_str: str) -> list[dict[str, Any]]:
    """Runs the production slate evaluation (`scripts/cloud_cycle_helpers.py`) with identity calibrators."""
    cfg = load_config()
    cal_bundle = {
        "ml_cal": ProbabilityCalibrator(),
        "tot_cal": ProbabilityCalibrator(),
        "sp_cal": ProbabilityCalibrator(),
        "ml_va": VennAbersConformalInterval(),
        "tot_va": VennAbersConformalInterval(),
        "sp_va": VennAbersConformalInterval(),
        "run_manifest_id": "RUN_TEST_PARITY",
    }
    res = evaluate_scheduled_slate_candidates(
        db,
        all_final_games=[],
        bx_features={},
        model_f=EnsembleStackingModel(cfg.model.version_id),
        model_version_id=cfg.model.version_id,
        cal_bundle=cal_bundle,
        market_anchor_weight=cfg.model.market_anchor_model_weight,
        moneyline_weight=cfg.model.moneyline_model_weight,
        moneyline_max_disagreement=cfg.model.moneyline_max_disagreement,
        moneyline_max_odds=cfg.model.moneyline_max_odds,
        now_str=now_str,
    )
    return res["2026-11-24"]


@pytest.mark.parametrize(
    ("decision_hours", "with_steam"),
    [
        (None, False),  # the backtest's opening-line assumption (>= horizon -> open weights)
        (6.0, False),   # mid-decay: both paths must share the time decay, not just the open weights
        (None, True),   # line movement before the decision: both paths must share the steam modulation
    ],
)
def test_production_and_backtest_compute_identical_anchored_probabilities(
    tmp_path: Path, decision_hours: float | None, with_steam: bool
) -> None:
    cfg = load_config()
    policy = _runner_policy()
    if decision_hours is not None:
        policy = replace(policy, hours_to_tipoff=decision_hours)
    decision_dt = _START_DT - timedelta(hours=policy.hours_to_tipoff)
    latest = _iso(decision_dt - timedelta(minutes=30))
    quotes: list[tuple[str, str, str, float | None, float, float, str]] = [
        ("O_ML_H", "moneyline", "HOME", None, 1.80, 2.10, latest),
        ("O_ML_A", "moneyline", "AWAY", None, 2.10, 1.80, latest),
        ("O_TOT_O", "total_points", "OVER", 224.5, 1.95, 1.90, latest),
        ("O_TOT_U", "total_points", "UNDER", 224.5, 1.90, 1.95, latest),
    ]
    if with_steam:
        earlier = _iso(decision_dt - timedelta(hours=5))
        quotes += [
            ("O_ML_H0", "moneyline", "HOME", None, 2.00, 1.87, earlier),
            ("O_ML_A0", "moneyline", "AWAY", None, 1.87, 2.00, earlier),
            ("O_TOT_O0", "total_points", "OVER", 224.5, 2.10, 1.76, earlier),
            ("O_TOT_U0", "total_points", "UNDER", 224.5, 1.76, 2.10, earlier),
        ]
    db = DatabaseManager(tmp_path / "parity.sqlite3")
    _seed_scheduled_game(db, quotes)

    production = _production_decisions(db, _iso(decision_dt))
    assert {(o["market"], o["selection"]) for o in production} == {
        ("moneyline", "HOME"),
        ("moneyline", "AWAY"),
        ("total_points", "OVER"),
        ("total_points", "UNDER"),
    }

    decision_ts = _iso(_START_DT - timedelta(hours=DECISION_LEAD_HOURS))
    for prod in production:
        # The same inputs, evaluated the way the backtest evaluates a side at the opening price.
        quote = opening_quote_record(
            _GAME_ID,
            _iso(_START_DT),
            prod["market"],
            prod["selection"],
            prod["line_value"],
            float(prod["market_fair_probability"]),
            vig=policy.vig,
            hours_to_tipoff=policy.hours_to_tipoff,
        )
        backtest = evaluate_opening_price_side(
            policy,
            quote,
            game_start_time=_iso(_START_DT),
            decision_ts=decision_ts,
            calibrated_prob=float(prod["calibrated_model_probability"]),
            raw_model_prob=float(prod["raw_model_probability"]),
            market_prob=float(prod["market_fair_probability"]),
            p_push=float(prod["p_push"]),
            conformal_interval=None,
            steam_delta=float(prod["steam_delta"]),
        )
        label = f"{prod['market']}/{prod['selection']}"
        assert backtest["hours_to_tipoff"] == prod["hours_to_tipoff"], label
        assert backtest["scheduled_model_weight"] == prod["scheduled_model_weight"], label
        assert backtest["effective_model_weight"] == prod["effective_model_weight"], label
        assert backtest["market_anchored_probability"] == pytest.approx(prod["market_anchored_probability"], abs=1e-9), label
        assert prod["scheduled_model_weight"] == resolve_market_anchor_weight(
            prod["market"],
            hours_to_tipoff=policy.hours_to_tipoff,
            fallback_weight=cfg.model.market_anchor_model_weight,
            moneyline_weight=cfg.model.moneyline_model_weight,
            schedule=cfg.model.anchor_schedule,
        ), label

    by_side = {(o["market"], o["selection"]): o for o in production}
    if with_steam:
        # The market moved before the decision: at least one side had its weight modulated, in both paths.
        assert any(o["effective_model_weight"] != o["scheduled_model_weight"] for o in production)
    if decision_hours is None and not with_steam:
        ml_home = by_side[("moneyline", "HOME")]
        sched = cfg.model.anchor_schedule
        assert ml_home["effective_model_weight"] == pytest.approx(sched.moneyline_open_weight)
        # The fixed-weight rule the backtest used before would not reproduce the production probability.
        fixed_w = float(cfg.model.moneyline_model_weight or cfg.model.market_anchor_model_weight)
        if abs(fixed_w - sched.moneyline_open_weight) > 1e-9:
            fixed = fixed_w * ml_home["calibrated_model_probability"] + (1.0 - fixed_w) * ml_home["market_fair_probability"]
            assert abs(fixed - ml_home["market_anchored_probability"]) > 1e-6


def _small_real_sample() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    conn = connect_readonly_prod_db()
    games = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM games WHERE season = '2024-25' AND status = 'FINAL' ORDER BY game_start_time LIMIT 220"
        ).fetchall()
    ]
    conn.close()
    market_rows = load_market_rows([PROJECT_ROOT / "data" / "raw" / "market_consensus_2024-25.csv"])
    return games, market_rows


def test_real_odds_backtest_decides_every_side_with_production_rule_and_reports_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = load_config()
    schedule = cfg.model.anchor_schedule
    decisions: list[tuple[dict[str, Any], dict[str, Any]]] = []
    guard_calls = {"edge": 0, "risk": 0}
    real_decide = bt_mod.evaluate_scheduled_market_opportunity
    real_edge = bt_mod.check_candidate_edge_and_model_guards
    real_risk = bt_mod.check_candidate_risk_guards

    def spy_decide(*args: Any, **kwargs: Any) -> dict[str, Any]:
        out = real_decide(*args, **kwargs)
        decisions.append((kwargs, out))
        return out

    def spy_edge(*args: Any, **kwargs: Any) -> Any:
        guard_calls["edge"] += 1
        return real_edge(*args, **kwargs)

    def spy_risk(*args: Any, **kwargs: Any) -> Any:
        guard_calls["risk"] += 1
        return real_risk(*args, **kwargs)

    monkeypatch.setattr(bt_mod, "evaluate_scheduled_market_opportunity", spy_decide)
    monkeypatch.setattr(bt_mod, "check_candidate_edge_and_model_guards", spy_edge)
    monkeypatch.setattr(bt_mod, "check_candidate_risk_guards", spy_risk)

    games, market_rows = _small_real_sample()
    res = run_real_odds_backtest(
        games,
        market_rows,
        start_date=games[160]["matchday_date"],
        anchor_schedule=schedule,
        market_anchor_weight=cfg.model.market_anchor_model_weight,
        moneyline_model_weight=cfg.model.moneyline_model_weight,
        moneyline_max_disagreement=cfg.model.moneyline_max_disagreement,
        moneyline_max_odds=cfg.model.moneyline_max_odds,
        min_ev=cfg.risk.min_ev_threshold,
    )

    assert decisions, "the backtest must decide through evaluate_scheduled_market_opportunity"
    assert guard_calls["edge"] == len(decisions)  # every side is screened by production's pre-bet guards
    assert guard_calls["risk"] == sum(1 for _, out in decisions if float(out["ev_unit"]) > 0.0)

    opening_hours = opening_line_hours_to_tipoff(schedule)
    assert opening_hours >= schedule.horizon_hours
    expected = {
        market: resolve_market_anchor_weight(
            market,
            hours_to_tipoff=opening_hours,
            fallback_weight=cfg.model.market_anchor_model_weight,
            moneyline_weight=cfg.model.moneyline_model_weight,
            schedule=schedule,
        )
        for market in ("moneyline", "total_points")
    }
    assert expected == {"moneyline": schedule.moneyline_open_weight, "total_points": schedule.total_points_open_weight}
    for kwargs, out in decisions:
        assert kwargs["anchor_schedule"] == schedule
        assert kwargs["hours_to_tipoff"] == opening_hours
        assert kwargs["steam_delta"] == 0.0  # only the opening line is known when the bet is decided
        assert out["effective_model_weight"] == expected[out["market"]]
    anchor_cfg = res["config"]["market_anchor"]
    assert anchor_cfg["effective_model_weights"] == {market: [w] for market, w in expected.items()}
    assert anchor_cfg["decision_hours_to_tipoff"] == opening_hours
    assert "model_weight" not in res["config"]

    # The full-slate quality series is the production HOME-side decision, not a fixed 30/70 blend.
    home = {
        out["game_id"]: float(out["market_anchored_probability"])
        for _, out in decisions
        if (out["market"], out["selection"]) == ("moneyline", "HOME")
    }
    won = {g["game_id"]: int(int(g["home_score"]) > int(g["away_score"])) for g in games}
    quality = res["moneyline_quality"]["model_anchored_production"]
    assert quality["n"] == len(home)
    assert quality["brier"] == pytest.approx(sum((p - won[gid]) ** 2 for gid, p in home.items()) / len(home), abs=1e-6)

    md = render_markdown(res)
    config_line = next(line for line in md.splitlines() if line.startswith("- Reentrenamiento"))
    assert "peso del modelo" not in config_line
    assert f"moneyline `{expected['moneyline']:.2f}`" in config_line
    assert f"totales `{expected['total_points']:.2f}`" in config_line
    assert f"horizon_hours={schedule.horizon_hours:g}" in config_line
    assert (
        f"moneyline `{schedule.moneyline_open_weight:.2f}→{schedule.moneyline_close_weight:.2f}`" in config_line
    )
    assert f"al menos `{opening_hours:.1f} h` antes del inicio" in md  # documented opening-line assumption


def _seed_oos_history(db: DatabaseManager) -> list[dict[str, Any]]:
    """165 final games; the last 45 have Pinnacle quotes 1 h before tip-off, and the even ones an earlier
    moneyline quote 5 h before tip-off that the market then moved away from (adverse steam for HOME)."""
    base_dt = datetime(2025, 1, 1, 20, 0, tzinfo=timezone.utc)
    teams = ["BOS", "NYK", "DEN", "DAL", "LAL", "MIA"]
    with db.connect() as conn:
        for i in range(165):
            dt = base_dt + timedelta(days=i // 2, hours=(i % 2) * 3)
            f_str = _iso(dt - timedelta(hours=3))
            gid = f"ESPN_PARITY_{i}"
            conn.execute(
                """
                INSERT INTO games (
                    game_id, season, matchday_date, game_start_time, home_team, away_team,
                    status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
                    away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
                    features_available_at, source_provider, ingested_at
                ) VALUES (?, '2025-26', ?, ?, ?, ?, 'FINAL', ?, ?, ?, 111.0, 99.0, 113.0, ?, 98.5, 2, 2, ?, 'ESPN', ?)
                """,
                (
                    gid, dt.strftime("%Y-%m-%d"), _iso(dt), teams[i % 6], teams[(i + 1) % 6],
                    112 + (i % 9), 104 + ((i * 3) % 11), 115.0 + (i % 4), 112.0 + (i % 3), f_str, f_str,
                ),
            )
            if i < 120:
                continue
            rows = [
                (f"OMLH_{i}", "moneyline", "HOME", None, 1.85, 2.05, 1),
                (f"OMLA_{i}", "moneyline", "AWAY", None, 2.05, 1.85, 1),
                (f"OTOV_{i}", "total_points", "OVER", 221.5, 1.92, 1.92, 1),
                (f"OTUN_{i}", "total_points", "UNDER", 221.5, 1.92, 1.92, 1),
            ]
            if i % 2 == 0:
                rows += [
                    (f"OMLH0_{i}", "moneyline", "HOME", None, 1.70, 2.25, 5),
                    (f"OMLA0_{i}", "moneyline", "AWAY", None, 2.25, 1.70, 5),
                ]
            for odds_id, mkt, sel, lv, dec, cp, hours_before in rows:
                conn.execute(
                    """
                    INSERT INTO odds_snapshots (
                        odds_id, game_id, provider, market, selection, line_value,
                        decimal_odds, counterpart_decimal_odds, captured_at, source_type, is_closing_line
                    ) VALUES (?, ?, 'Pinnacle', ?, ?, ?, ?, ?, ?, 'OBSERVED', 0)
                    """,
                    (odds_id, gid, mkt, sel, lv, dec, cp, _iso(dt - timedelta(hours=hours_before))),
                )
    return db.fetch_all("SELECT * FROM games WHERE status = 'FINAL' ORDER BY game_start_time ASC")


def test_fallback_oos_comparisons_anchor_with_production_schedule_and_steam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = load_config()
    schedule = cfg.model.anchor_schedule
    calls: list[dict[str, Any]] = []
    real_decide = oos_mod.evaluate_scheduled_market_opportunity

    def spy_decide(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return real_decide(*args, **kwargs)

    monkeypatch.setattr(oos_mod, "evaluate_scheduled_market_opportunity", spy_decide)
    db = DatabaseManager(tmp_path / "oos_parity.sqlite3")
    final_games = _seed_oos_history(db)
    recs = build_walk_forward_oos_comparisons_for_active_model(
        db,
        final_games,
        cfg.model.version_id,
        "2026-01-01T00:00:00Z",
        market_anchor_weight=cfg.model.market_anchor_model_weight,
        moneyline_weight=cfg.model.moneyline_model_weight,
        anchor_schedule=schedule,
    )
    anchored = [r for r in recs if r["model_anchored_ml"] is not None]
    assert len(anchored) >= 10
    assert calls and all(c["anchor_schedule"] == schedule for c in calls)

    def scheduled(market: str) -> float:
        return resolve_market_anchor_weight(
            market,
            hours_to_tipoff=1.0,
            fallback_weight=cfg.model.market_anchor_model_weight,
            moneyline_weight=cfg.model.moneyline_model_weight,
            schedule=schedule,
        )

    w_ml, w_tot = scheduled("moneyline"), scheduled("total_points")
    parities = {int(r["game_id"].rsplit("_", 1)[1]) % 2 for r in anchored}
    assert parities == {0, 1}  # games with and without line movement are both scored
    for r in anchored:
        idx = int(r["game_id"].rsplit("_", 1)[1])
        # Decided at the newest quote (1 h before tip-off); HOME steam is adverse on even games.
        assert r["anchor_hours_to_tipoff"] == pytest.approx(1.0)
        expected_w_ml = round(max(0.0, w_ml - 0.08), 6) if idx % 2 == 0 else w_ml
        assert r["model_anchor_weight_ml"] == pytest.approx(expected_w_ml, abs=1e-9)
        assert r["model_anchored_ml"] == pytest.approx(
            expected_w_ml * r["model_cal_ml"] + (1.0 - expected_w_ml) * r["market_ml"], abs=2e-6
        )
        if r["model_anchored_tot"] is not None:
            assert r["model_anchor_weight_tot"] == pytest.approx(w_tot, abs=1e-9)
            assert r["model_anchored_tot"] == pytest.approx(
                w_tot * r["model_cal_tot"] + (1.0 - w_tot) * r["market_tot"], abs=2e-6
            )
    assert any(r["model_anchored_tot"] is not None for r in anchored)
    # The fixed 0.30 blend the fallback used before differs from the production probability.
    assert any(abs(r["model_anchored_ml"] - (0.30 * r["model_cal_ml"] + 0.70 * r["market_ml"])) > 1e-4 for r in anchored)


def test_backtest_decisions_are_screened_by_production_execution_guards() -> None:
    """Backtest decision records carry what production's guards read, and `config.execution` guards bite."""
    cfg = load_config()
    policy = _runner_policy()
    start = "2026-01-10T00:00:00Z"
    decision_ts = _iso(datetime(2026, 1, 10, tzinfo=timezone.utc) - timedelta(hours=DECISION_LEAD_HOURS))

    def side(market: str, selection: str, p_open: float, cal: float, width: float = 0.08) -> dict[str, Any]:
        line = 224.5 if market == "total_points" else None
        quote = opening_quote_record(
            "ESPN_GUARD_1", start, market, selection, line, p_open, vig=policy.vig, hours_to_tipoff=policy.hours_to_tipoff
        )
        return evaluate_opening_price_side(
            policy,
            quote,
            game_start_time=start,
            decision_ts=decision_ts,
            calibrated_prob=cal,
            raw_model_prob=cal,
            market_prob=p_open,
            p_push=0.0,
            conformal_interval={"p0": cal - width / 2.0, "p1": cal + width / 2.0, "width": width},
            steam_delta=0.0,
        )

    def guard(opp: dict[str, Any]) -> str | None:
        block = check_candidate_edge_and_model_guards(opp, min_ev_threshold=cfg.risk.min_ev_threshold)
        return block[0] if block else None

    clean = side("moneyline", "HOME", 0.45, 0.58)
    assert clean["ev_unit"] > cfg.risk.min_ev_threshold
    assert guard(clean) is None
    assert guard(side("moneyline", "HOME", 0.45, 0.58, width=cfg.execution.max_conformal_width + 0.05)) == (
        "CONFORMAL_UNCERTAINTY_TOO_WIDE"
    )
    implausible = side("moneyline", "HOME", 0.24, 0.95)
    assert implausible["ev_unit"] > cfg.execution.max_plausible_ev_unit
    assert guard(implausible) == "UNVERIFIED_INJURY_OR_LINEUP_OUTLIER"
    longshot = side("total_points", "OVER", 0.26, 0.34)
    assert longshot["decimal_odds_used"] > cfg.execution.longshot_odds_threshold
    assert guard(longshot) == "EXCESSIVE_LONGSHOT_VARIANCE"
    if cfg.model.moneyline_max_odds is not None:
        capped = side("moneyline", "HOME", 0.33, 0.42)
        assert capped["decimal_odds_used"] > cfg.model.moneyline_max_odds
        assert guard(capped) == "EXCESSIVE_LONGSHOT_VARIANCE"
