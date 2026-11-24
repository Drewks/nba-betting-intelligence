"""
Parity between production decisions and the walk-forward simulation of the orchestrator.

`src/orchestrator.py` runs `WalkForwardBacktester.run_walk_forward` in step 4, i.e. `run_walk_forward_simulation`:
`scripts/run_pipeline.py` and the initial bootstrap of `scripts/run_cloud_cycle.py` judge the model with it. It must
decide every quote as the live cycle (`scripts/cloud_cycle_helpers.py`) does: the `config.model.anchor_schedule`
weight at the hours to tip-off, the market consensus of the quotes known at the decision and the steam of the
snapshots captured up to it. These tests fail if the walk-forward and production compute different
market-anchored probabilities for the same inputs.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import src.backtesting.walk_forward_helpers as wf_mod
from scripts.cloud_cycle_helpers import evaluate_scheduled_slate_candidates
from src.backtesting.backtester import WalkForwardBacktester
from src.backtesting.walk_forward_helpers import run_walk_forward_simulation
from src.calibration.calibrator import ProbabilityCalibrator, VennAbersConformalInterval
from src.config import load_config
from src.models.statistical_models import EnsembleStackingModel
from src.paper_trading.engine import PaperTradingEngine
from src.prediction.ev_calculator import DEFAULT_MODEL_WEIGHT, devig_shin, resolve_market_anchor_weight
from src.prediction.market_quotes import decision_time_market
from src.storage.db import DatabaseManager

_ISO = "%Y-%m-%dT%H:%M:%SZ"
_GAME_ID = "ESPN_99002_2026-11-24_MIA_AT_BOS"
_MATCHDAY = "2026-11-24"
_START_DT = datetime(2026, 11, 24, 23, 0, tzinfo=timezone.utc)
_FEATURES_AT = "2026-11-24T08:00:00Z"
_TIP_LEAD = timedelta(hours=2)  # the walk-forward decides at max(tip-off - 2 h, newest pre-game quote, features)
_PIN = "Pinnacle [LIVE_API]"

# (odds_id, provider, market, selection, line_value, decimal_odds, counterpart, captured_at, is_closing_line)
Quote = tuple[str, str, str, str, float | None, float, float, datetime, int]


def _iso(dt: datetime) -> str:
    return dt.strftime(_ISO)


def _two_way(
    odds_id: str, provider: str, market: str, line: float | None, odds_a: float, odds_b: float, at: datetime, closing: int = 0
) -> list[Quote]:
    """Both sides of one book's market (HOME/OVER first); a spread's AWAY side carries the opposite line."""
    side_a, side_b = ("OVER", "UNDER") if market == "total_points" else ("HOME", "AWAY")
    line_b = -line if (market == "spread" and line is not None) else line
    return [
        (f"{odds_id}_{side_a}", provider, market, side_a, line, odds_a, odds_b, at, closing),
        (f"{odds_id}_{side_b}", provider, market, side_b, line_b, odds_b, odds_a, at, closing),
    ]


def _two_hours_before_tip() -> tuple[datetime, list[Quote]]:
    """Quotes 30 min before the walk-forward's default decision time (tip-off - 2 h); all three markets."""
    decision = _START_DT - _TIP_LEAD
    at = decision - timedelta(minutes=30)
    return decision, [
        *_two_way("PIN_ML", _PIN, "moneyline", None, 1.80, 2.10, at),
        *_two_way("PIN_TOT", _PIN, "total_points", 224.5, 1.95, 1.90, at),
        *_two_way("PIN_SP", _PIN, "spread", -3.5, 1.93, 1.93, at),
    ]


def _decided_at_newest_quote() -> tuple[datetime, list[Quote]]:
    """The newest quote arrives 40 min before tip-off: both paths decide when it is captured."""
    decision = _START_DT - timedelta(minutes=40)
    return decision, [
        *_two_way("PIN_ML", _PIN, "moneyline", None, 1.80, 2.10, decision),
        *_two_way("PIN_TOT", _PIN, "total_points", 224.5, 1.95, 1.90, decision),
    ]


def _steam_then_closing_move() -> tuple[datetime, list[Quote]]:
    """The line moves before the decision (steam); the closing line, captured after it, moves much further."""
    decision = _START_DT - _TIP_LEAD
    opening, latest, closing = decision - timedelta(hours=5), decision - timedelta(minutes=30), _START_DT - timedelta(minutes=5)
    return decision, [
        *_two_way("PIN_ML_OPEN", _PIN, "moneyline", None, 2.00, 1.87, opening),
        *_two_way("PIN_TOT_OPEN", _PIN, "total_points", 224.5, 2.10, 1.76, opening),
        *_two_way("PIN_ML", _PIN, "moneyline", None, 1.80, 2.10, latest),
        *_two_way("PIN_TOT", _PIN, "total_points", 224.5, 1.95, 1.90, latest),
        *_two_way("PIN_ML_CLOSE", _PIN, "moneyline", None, 1.50, 2.70, closing, closing=1),
        *_two_way("PIN_TOT_CLOSE", _PIN, "total_points", 224.5, 1.70, 2.20, closing, closing=1),
    ]


def _quotes_production_would_not_take() -> tuple[datetime, list[Quote]]:
    """
    Besides one takeable book per market: a cross-book aggregate named after a sharp book, a sharp quote older
    than `max_quote_age_hours` and a ~10% margin book. None of them may move the consensus; all count for steam.
    """
    decision = _START_DT - _TIP_LEAD
    return decision, [
        *_two_way("STALE_LV", "LowVig.ag (LineShop)", "moneyline", None, 1.70, 2.25, decision - timedelta(hours=8)),
        *_two_way("AGG_ML", "Pinnacle (Best of 12 books)", "moneyline", None, 2.05, 2.05, decision - timedelta(minutes=35)),
        *_two_way("PIN_ML", _PIN, "moneyline", None, 1.80, 2.10, decision - timedelta(minutes=30)),
        *_two_way("TA_TOT", "Te Apuesto Perú [LIVE_API]", "total_points", 224.5, 1.70, 1.95, decision - timedelta(minutes=40)),
        *_two_way("DK_TOT", "DraftKings", "total_points", 224.5, 1.91, 1.91, decision - timedelta(minutes=30)),
    ]


_SCENARIOS: dict[str, Callable[[], tuple[datetime, list[Quote]]]] = {
    "two_hours_before_tip": _two_hours_before_tip,
    "decided_at_newest_quote": _decided_at_newest_quote,
    "steam_then_closing_move": _steam_then_closing_move,
    "quotes_production_would_not_take": _quotes_production_would_not_take,
}


def _game(status: str) -> dict[str, Any]:
    final = status == "FINAL"
    return {
        "game_id": _GAME_ID,
        "season": "2026-27",
        "matchday_date": _MATCHDAY,
        "game_start_time": _iso(_START_DT),
        "home_team": "BOS",
        "away_team": "MIA",
        "status": status,
        "home_score": 112 if final else None,  # home win; 216 points: UNDER 224.5, BOS covers -3.5
        "away_score": 104 if final else None,
        "home_off_rtg": 116.0,
        "home_def_rtg": 110.5,
        "home_pace": 99.2,
        "away_off_rtg": 112.5,
        "away_def_rtg": 113.0,
        "away_pace": 98.8,
        "home_rest_days": 2,
        "away_rest_days": 2,
        "features_available_at": _FEATURES_AT,
        "source_provider": "espn",
        "ingested_at": _FEATURES_AT,
        "result_recorded_at": _iso(_START_DT + timedelta(hours=3)) if final else None,
    }


def _odds_rows(quotes: list[Quote]) -> list[dict[str, Any]]:
    return [
        {
            "odds_id": odds_id,
            "game_id": _GAME_ID,
            "provider": provider,
            "market": market,
            "selection": selection,
            "line_value": line,
            "decimal_odds": odds,
            "counterpart_decimal_odds": counterpart,
            "captured_at": _iso(at),
            "is_closing_line": closing,
            "source_type": "OBSERVED",
        }
        for odds_id, provider, market, selection, line, odds, counterpart, at, closing in quotes
    ]


def _production_decisions(tmp_path: Path, odds_rows: list[dict[str, Any]], decision_dt: datetime) -> list[dict[str, Any]]:
    """The live slate evaluation on the SCHEDULED game at `decision_dt`, with the arguments the cycle passes."""
    cfg = load_config()
    db = DatabaseManager(tmp_path / "production.sqlite3")
    game = _game("SCHEDULED")
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
            f"INSERT INTO games ({', '.join(game)}) VALUES ({', '.join('?' for _ in game)})", tuple(game.values())
        )
        for row in odds_rows:
            conn.execute(
                f"INSERT INTO odds_snapshots ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})", tuple(row.values())
            )
    cal_bundle = {
        "ml_cal": ProbabilityCalibrator(),
        "tot_cal": ProbabilityCalibrator(),
        "sp_cal": ProbabilityCalibrator(),
        "ml_va": VennAbersConformalInterval(),
        "tot_va": VennAbersConformalInterval(),
        "sp_va": VennAbersConformalInterval(),
        "run_manifest_id": "RUN_TEST_WALK_FORWARD_PARITY",
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
        now_str=_iso(decision_dt),
    )
    return res[_MATCHDAY]


class _RecordingEngine(PaperTradingEngine):
    """The paper engine, keeping a copy of every candidate the walk-forward hands it."""

    def __init__(self, db: DatabaseManager) -> None:
        super().__init__(db, is_backtest=True)
        self.candidates: list[dict[str, Any]] = []

    def evaluate_and_record_matchday_selections(
        self, matchday_date: str, candidate_predictions: list[dict[str, Any]], proposed_stake_pen: float | None = None
    ) -> dict[str, Any]:
        self.candidates.extend(dict(c) for c in candidate_predictions)
        return super().evaluate_and_record_matchday_selections(matchday_date, candidate_predictions, proposed_stake_pen)


def _quote_key(opp: dict[str, Any]) -> tuple[Any, ...]:
    return (opp["odds_provider"], opp["market"], opp["selection"], opp["line_value"], opp["odds_captured_at"])


def _side_key(opp: dict[str, Any]) -> tuple[Any, ...]:
    return (opp["market"], opp["selection"], opp["line_value"])


@pytest.mark.parametrize("scenario", list(_SCENARIOS))
def test_walk_forward_and_production_compute_identical_anchored_probabilities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    cfg = load_config()
    decision_dt, quotes = _SCENARIOS[scenario]()
    odds_rows = _odds_rows(quotes)
    production = _production_decisions(tmp_path, odds_rows, decision_dt)
    assert production, "production must decide the scheduled game"

    calls: list[dict[str, Any]] = []
    real_decide = wf_mod.evaluate_scheduled_market_opportunity

    def spy_decide(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return real_decide(*args, **kwargs)

    monkeypatch.setattr(wf_mod, "evaluate_scheduled_market_opportunity", spy_decide)
    db = DatabaseManager(tmp_path / "walk_forward.sqlite3")
    engine = _RecordingEngine(db)
    records, _closing_rows, skipped = run_walk_forward_simulation(
        db, engine, warmup_matchdays=0, retrain_every_matchdays=1, games=[_game("FINAL")], odds=odds_rows
    )
    walk_forward = engine.candidates

    # Every pre-game quote is decided with the production schedule, at the time production decided.
    assert skipped == 0
    assert len(calls) == len(walk_forward) == sum(1 for r in odds_rows if not r["is_closing_line"])
    hours = (_START_DT - decision_dt).total_seconds() / 3600.0
    for kwargs in calls:
        assert kwargs["anchor_schedule"] == cfg.model.anchor_schedule
        assert kwargs["hours_to_tipoff"] == pytest.approx(hours)
        assert kwargs["simulated_prediction_time"] == _iso(decision_dt)

    wf_by_quote = {_quote_key(w): w for w in walk_forward}
    for prod in production:
        label = f"{scenario}: {prod['odds_provider']} {prod['market']}/{prod['selection']}"
        wf = wf_by_quote[_quote_key(prod)]
        # Same inputs (the model probability of the same quote at the same decision time) ...
        assert wf["calibrated_model_probability"] == pytest.approx(prod["calibrated_model_probability"], abs=1e-9), label
        # ... must give the same anchored probability, through the same weight, steam and consensus.
        assert wf["market_anchored_probability"] == pytest.approx(prod["market_anchored_probability"], abs=1e-9), label
        assert wf["ev_unit"] == pytest.approx(prod["ev_unit"], abs=1e-9), label
        assert wf["model_market_disagreement"] == pytest.approx(prod["model_market_disagreement"], abs=1e-9), label
        assert wf["steam_delta"] == prod["steam_delta"], label
        assert wf["effective_model_weight"] == prod["effective_model_weight"], label
        assert wf["scheduled_model_weight"] == prod["scheduled_model_weight"], label
        assert wf["hours_to_tipoff"] == prod["hours_to_tipoff"], label
        assert prod["scheduled_model_weight"] == resolve_market_anchor_weight(
            prod["market"],
            hours_to_tipoff=hours,
            fallback_weight=cfg.model.market_anchor_model_weight,
            moneyline_weight=cfg.model.moneyline_model_weight,
            schedule=cfg.model.anchor_schedule,
        ), label

    # Quotes production would not take are still read against production's market for their side.
    prod_by_side = {_side_key(p): p for p in production}
    for wf in walk_forward:
        prod = prod_by_side.get(_side_key(wf))
        if prod is not None:
            assert wf["market_anchored_probability"] == pytest.approx(prod["market_anchored_probability"], abs=1e-9), wf

    # The comparison record the walk-forward metrics are built from carries production's probabilities.
    (record,) = records
    assert record["model_anchored_ml"] == pytest.approx(
        prod_by_side[("moneyline", "HOME", None)]["market_anchored_probability"], abs=1e-9
    )
    assert record["model_anchored_tot"] == pytest.approx(
        prod_by_side[("total_points", "OVER", 224.5)]["market_anchored_probability"], abs=1e-9
    )
    if ("spread", "HOME", -3.5) in prod_by_side:
        assert record["model_anchored_sp"] == pytest.approx(
            prod_by_side[("spread", "HOME", -3.5)]["market_anchored_probability"], abs=1e-9
        )

    # The fixed-weight blend with each quote's own price, which the walk-forward used before, is another policy.
    ml_home = prod_by_side[("moneyline", "HOME", None)]
    fixed = DEFAULT_MODEL_WEIGHT * ml_home["calibrated_model_probability"] + (1.0 - DEFAULT_MODEL_WEIGHT) * ml_home[
        "market_fair_probability"
    ]
    assert abs(fixed - ml_home["market_anchored_probability"]) > 1e-3


def test_orchestrator_walk_forward_metrics_score_the_production_probabilities(tmp_path: Path) -> None:
    """Step 4 of the orchestrator (`WalkForwardBacktester.run_walk_forward`) scores production's probabilities."""
    decision_dt, quotes = _quotes_production_would_not_take()
    odds_rows = _odds_rows(quotes)
    prod_by_side = {_side_key(p): p for p in _production_decisions(tmp_path, odds_rows, decision_dt)}
    db = DatabaseManager(tmp_path / "orchestrator_step4.sqlite3")
    backtester = WalkForwardBacktester(db, PaperTradingEngine(db), warmup_matchdays=0, retrain_every_matchdays=1)
    metrics = backtester.run_walk_forward(games=[_game("FINAL")], odds=odds_rows)

    home_won, over_hit = 1, 0
    for key, side, outcome in (
        ("ensemble_market_anchored_ml", ("moneyline", "HOME", None), home_won),
        ("ensemble_market_anchored_totals", ("total_points", "OVER", 224.5), over_hit),
    ):
        scored = metrics["model_comparison"][key]
        assert scored["sample_size"] == 1, key
        p = float(prod_by_side[side]["market_anchored_probability"])
        assert scored["brier_score"] == pytest.approx((p - outcome) ** 2, abs=1e-6), key


def test_decision_time_market_ignores_later_snapshots_and_quotes_production_would_not_take() -> None:
    cfg = load_config()
    decision_dt, quotes = _quotes_production_would_not_take()
    known = _odds_rows(quotes)
    later = _odds_rows(_two_way("PIN_ML_LATER", _PIN, "moneyline", None, 1.50, 2.70, decision_dt + timedelta(minutes=10)))
    market = decision_time_market(known, _START_DT, decision_dt, execution_cfg=cfg.execution)

    # A snapshot captured after the decision changes neither the consensus nor the steam (no lookahead).
    assert decision_time_market(known + later, _START_DT, decision_dt, execution_cfg=cfg.execution) == market
    # Consensus: only the quotes a bet could be taken at (no aggregate, no stale quote, no ~10% margin book).
    pinnacle_home = devig_shin(1.80, 2.10)[0]
    assert market.consensus_prob("moneyline", "HOME", None) == pytest.approx(pinnacle_home, abs=1e-9)
    assert market.consensus_prob("total_points", "OVER", 224.5) == pytest.approx(devig_shin(1.91, 1.91)[0], abs=1e-9)
    assert market.consensus_prob("spread", "HOME", -3.5) is None
    # Steam: every snapshot up to the decision, from the first (the stale quote) to the newest.
    lowvig_home = devig_shin(1.70, 2.25)[0]
    assert market.steam_delta("moneyline", "HOME") == pytest.approx(round(pinnacle_home - lowvig_home, 6), abs=1e-9)
    assert market.steam_delta("spread", "HOME") == 0.0
