"""
Walk-forward backtest against REAL historical market prices (free, CC BY 4.0 data).

Data: consensus no-vig opening and closing lines published on HuggingFace by `minmaxxxer`
(median across ~15-25 bookmakers per game, margins removed proportionally), CC BY 4.0:
  - nba-closing-lines-ats-2024-25, nba-closing-lines-ats-2025-26, nba-odds-2026-27.

Protocol (mirrors production as closely as the data allows):
  1. Games and pre-game features come from the project's own ESPN history; team ratings are recomputed
     with the CURRENT configuration (config/model_config.yaml), using only earlier games.
  2. For every matchday the production ensemble is trained only on games that started before the
     matchday's first tip-off (retrained every `retrain_every_days`); the probability calibrator and
     the Venn-Abers interval are fitted only on earlier out-of-sample predictions.
  3. Decisions are taken at the OPENING consensus price with production's decision function
     (`evaluate_scheduled_market_opportunity`: market anchor schedule, steam handling, EV) and production's
     pre-bet guards (`check_candidate_edge_and_model_guards`: EV threshold, implausible EV, model/market
     disagreement, moneyline odds cap, long-shot floor, adverse steam, conformal width, CLV meta-label),
     then one bet per game and top-3 per day. The data has no opening timestamp: the opening line is taken
     to be quoted at least `horizon_hours` before tip-off, so the schedule gives its open weights. Only the
     opening line is known at decision time, so steam is 0 (the closing line would be lookahead).
     A side whose price `1 / (p_open * (1 + vig))` is <= 1.0 has no bettable price: it gets no bet,
     candidate or uncapped-shadow evaluation (counted in `config.unpriceable_sides_skipped`), the
     opposite side is quoted without a counterpart price, and the game stays in the quality series.
  4. Bets are graded with the real result; CLV is measured against the CLOSING no-vig consensus.
  5. Evaluates `development` vs untouched `holdout_season` (`2026-27`), Bonferroni multiple-testing
     p-values, full-slate signal, `uncapped_shadow`, and chronological `totals_clv_targeted`.
"""

from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
import io
import math
from pathlib import Path
from typing import Any
import urllib.request

import numpy as np
from scipy.stats import norm

from src.backtesting.real_odds_metrics import (
    render_markdown,
    summarize_backtest_results,
)
from src.calibration.calibrator import (
    ProbabilityCalibrator,
    VennAbersConformalInterval,
    calibrate_binary_with_push,
)
from src.config import load_config
from src.features.boxscore_features import attach_boxscore_features
from src.features.team_ratings import compute_pregame_team_ratings, is_synthetic_game_id
from src.ingestion.normalizer import normalize_team_code
from src.models.statistical_models import EnsembleStackingModel
from src.paper_trading.execution_helpers import check_candidate_edge_and_model_guards, check_candidate_risk_guards
from src.paper_trading.staking import fractional_kelly_stake
from src.prediction.ev_calculator import (
    compute_line_steam,
    describe_market_anchor_schedule,
    evaluate_scheduled_market_opportunity,
    market_anchored_probability,
    resolve_market_anchor_weight,
)
from src.prediction.totals_closing import TotalsClosingEstimator, fit_totals_closing_estimator
from src.validation.validator import parse_iso_utc

__all__ = [
    "DATA_ATTRIBUTION",
    "DATA_SOURCES",
    "DECISION_LEAD_HOURS",
    "MATCH_TOLERANCE_HOURS",
    "TOTAL_SIGMA",
    "OpeningPriceDecisionPolicy",
    "download_market_csvs",
    "evaluate_opening_price_side",
    "load_market_rows",
    "match_market_to_games",
    "opening_line_hours_to_tipoff",
    "opening_quote_record",
    "render_markdown",
    "run_real_odds_backtest",
]

DATA_SOURCES: dict[str, str] = {
    "2024-25": "https://huggingface.co/datasets/minmaxxxer/nba-closing-lines-ats-2024-25/resolve/main/nba_2024_25_closing_lines_ats.csv",
    "2025-26": "https://huggingface.co/datasets/minmaxxxer/nba-closing-lines-ats-2025-26/resolve/main/nba_2025_26_closing_lines_ats.csv",
    "2026-27": "https://huggingface.co/datasets/minmaxxxer/nba-odds-2026-27/resolve/main/nba_2026_27_odds.csv",
}
DATA_ATTRIBUTION = (
    "Market data: minmaxxxer, 'NBA closing lines and ATS results' (HuggingFace), CC BY 4.0 — "
    "consensus no-vig opening/closing lines (median across bookmakers)."
)
TOTAL_SIGMA = 18.0
MATCH_TOLERANCE_HOURS = 12.0
# Decision timestamp of every simulated bet: this many hours before its tip-off (the previous matchday's
# games are final by then; the model only knows games that started before the matchday's first tip-off).
DECISION_LEAD_HOURS = 6.0


def download_market_csvs(
    dest_dir: Path,
    seasons: list[str] | None = None,
    timeout: int = 60,
    refresh_seasons: list[str] | None = None,
) -> list[Path]:
    """
    Returns the local market CSV per season, downloading missing ones. Seasons in `refresh_seasons`
    are downloaded again: the in-progress season grows every day and the forward holdout (games after
    the protocol freeze) stays empty while the cached copy is never refreshed.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    refresh = set(refresh_seasons or [])
    paths: list[Path] = []
    for season in seasons or list(DATA_SOURCES):
        url = DATA_SOURCES[season]
        out = dest_dir / f"market_consensus_{season}.csv"
        if not out.exists() or season in refresh:
            req = urllib.request.Request(url, headers={"User-Agent": "nba-betting-intelligence-backtest"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                out.write_bytes(resp.read())
        paths.append(out)
    return paths


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        out = float(value)
        return out if math.isfinite(out) else None
    except (TypeError, ValueError):
        return None


def load_market_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for r in csv.DictReader(io.StringIO(text)):
            p_open = _float(r.get("open_home_win_prob"))
            p_close = _float(r.get("close_home_win_prob"))
            if p_open is None or p_close is None or not r.get("start_time_utc"):
                continue
            try:
                home = normalize_team_code(r["home_team"])
                away = normalize_team_code(r["away_team"])
            except ValueError:
                continue
            rows.append(
                {
                    "market_game_id": r.get("game_id"),
                    "season": r.get("season"),
                    "start_time_utc": r["start_time_utc"],
                    "home_team": home,
                    "away_team": away,
                    "open_home_win_prob": p_open,
                    "close_home_win_prob": p_close,
                    "open_total": _float(r.get("open_total")),
                    "close_total": _float(r.get("close_total")),
                    "close_over_prob": _float(r.get("close_over_prob")),
                    "moneyline_winner": r.get("moneyline_winner"),
                    "total_result_open": r.get("total_result_open"),
                    "bookmakers": int(_float(r.get("bookmakers")) or 0),
                }
            )
    return rows


def match_market_to_games(
    market_rows: list[dict[str, Any]], games: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Maps game_id -> market row (same teams, tip-off within MATCH_TOLERANCE_HOURS)."""
    by_teams: dict[tuple[str, str], list[tuple[datetime, dict[str, Any]]]] = defaultdict(list)
    for g in games:
        by_teams[(g["home_team"], g["away_team"])].append((parse_iso_utc(g["game_start_time"]), g))
    out: dict[str, dict[str, Any]] = {}
    for m in market_rows:
        m_dt = parse_iso_utc(m["start_time_utc"])
        best: tuple[float, dict[str, Any]] | None = None
        for g_dt, g in by_teams.get((m["home_team"], m["away_team"]), []):
            diff_h = abs((g_dt - m_dt).total_seconds()) / 3600.0
            if diff_h <= MATCH_TOLERANCE_HOURS and (best is None or diff_h < best[0]):
                best = (diff_h, g)
        if best is not None:
            out[best[1]["game_id"]] = m
    return out


def _price(fair_prob: float, vig: float) -> float:
    return round(1.0 / (max(1e-6, fair_prob) * (1.0 + vig)), 4)


def _bettable_price(fair_prob: float, vig: float) -> float | None:
    """`_price`, or None when the margin pushes it to <= 1.0 (fair_prob >= 1 / (1 + vig)): no bettable price."""
    price = _price(fair_prob, vig)
    return price if price > 1.0 else None


def opening_line_hours_to_tipoff(anchor_schedule: Any) -> float:
    """
    Hours before tip-off at which a bet at the opening price is taken. The source publishes no timestamp for
    the opening line; opening lines are posted well before tip-off, so the line is assumed to be quoted at
    least `horizon_hours` before it (never later than the decision time). At that distance the production
    schedule is at tau = 1 and gives its open weights.
    """
    # Same default horizon as `resolve_market_anchor_weight`.
    horizon = float(getattr(anchor_schedule, "horizon_hours", 12.0)) if anchor_schedule is not None else 0.0
    return max(horizon, DECISION_LEAD_HOURS)


def opening_quote_record(
    game_id: str,
    game_start_time: str,
    market: str,
    selection: str,
    line_value: float | None,
    p_open: float,
    *,
    vig: float,
    hours_to_tipoff: float,
) -> dict[str, Any]:
    """Opening quote at the no-vig consensus plus margin (counterpart None when the opposite side is <= 1.0)."""
    captured = parse_iso_utc(game_start_time) - timedelta(hours=hours_to_tipoff)
    return {
        "odds_id": f"BT_{game_id}_{market}_{selection}",
        "game_id": game_id,
        "provider": "consensus_open",
        "market": market,
        "selection": selection,
        "line_value": line_value,
        "decimal_odds": _price(p_open, vig),
        "counterpart_decimal_odds": _bettable_price(1.0 - p_open, vig),
        "captured_at": captured.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@dataclass(frozen=True)
class OpeningPriceDecisionPolicy:
    """Production decision parameters as the backtest applies them at the opening price."""

    model_version_id: str
    anchor_schedule: Any
    market_anchor_weight: float
    moneyline_weight: float | None
    max_disagreement: float
    moneyline_max_disagreement: float | None
    moneyline_max_odds: float | None
    vig: float
    hours_to_tipoff: float


def evaluate_opening_price_side(
    policy: OpeningPriceDecisionPolicy,
    quote: dict[str, Any],
    *,
    game_start_time: str,
    decision_ts: str,
    calibrated_prob: float,
    raw_model_prob: float,
    market_prob: float,
    p_push: float,
    conformal_interval: dict[str, Any] | None,
    steam_delta: float,
) -> dict[str, Any]:
    """
    Production decision (`evaluate_scheduled_market_opportunity`) for one side at the opening price: the
    no-vig opening consensus is the market probability and the model weight is the schedule's at
    `policy.hours_to_tipoff`. Adds `calibrated_probability` (the market-anchored probability the engine
    stakes on), the field the production pre-bet guards read.
    """
    opp = evaluate_scheduled_market_opportunity(
        estimated_prob=float(np.clip(calibrated_prob, 0.001, 0.999)),
        raw_model_prob=float(np.clip(raw_model_prob, 0.001, 0.999)),
        uncertainty_std=0.05,
        odds_record=quote,
        game_start_time=game_start_time,
        model_version_id=policy.model_version_id,
        hours_to_tipoff=policy.hours_to_tipoff,
        market_anchor_weight=policy.market_anchor_weight,
        moneyline_weight=policy.moneyline_weight,
        anchor_schedule=policy.anchor_schedule,
        max_disagreement=policy.max_disagreement,
        moneyline_max_disagreement=policy.moneyline_max_disagreement,
        moneyline_max_odds=policy.moneyline_max_odds,
        simulated_prediction_time=decision_ts,
        market_consensus_prob=market_prob,
        steam_delta=steam_delta,
        conformal_interval=conformal_interval,
        p_push=p_push,
    )
    opp["calibrated_probability"] = opp["estimated_probability"]
    return opp


def _close_over_prob_at_line(close_total: float | None, close_over_prob: float | None, line: float) -> float | None:
    if close_total is None or close_over_prob is None:
        return None
    p = float(np.clip(close_over_prob, 0.02, 0.98))
    return float(np.clip(norm.cdf(norm.ppf(p) + (close_total - line) / TOTAL_SIGMA), 0.01, 0.99))


def _with_current_ratings(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ratings = compute_pregame_team_ratings(games)
    out = []
    for g in games:
        r = ratings.get(g["game_id"])
        out.append(
            {
                **g,
                **{
                    k: r[k]
                    for k in (
                        "home_off_rtg",
                        "home_def_rtg",
                        "home_pace",
                        "away_off_rtg",
                        "away_def_rtg",
                        "away_pace",
                        "home_rest_days",
                        "away_rest_days",
                    )
                },
            }
            if r
            else dict(g)
        )
    return out


_RATING_FIELDS = ("off_rtg", "def_rtg", "pace")


def _team_rating_history(games: list[dict[str, Any]]) -> dict[str, list[tuple[str, dict[str, float]]]]:
    """Per team, chronological `(game_start_time, pre-game ratings of that team)` pairs."""
    hist: dict[str, list[tuple[str, dict[str, float]]]] = defaultdict(list)
    for g in games:
        for side in ("home", "away"):
            vals = {f: g.get(f"{side}_{f}") for f in _RATING_FIELDS}
            if all(v is not None for v in vals.values()):
                hist[g[f"{side}_team"]].append(
                    (str(g["game_start_time"]), {k: float(v) for k, v in vals.items() if v is not None})
                )
    for team in hist:
        hist[team].sort(key=lambda t: t[0])
    return hist


def _lagged_team_ratings(
    g: dict[str, Any], hist: dict[str, list[tuple[str, dict[str, float]]]], info_cutoff: str
) -> dict[str, float]:
    """Ratings as known at `info_cutoff` using each team's last earlier game pre-game state."""
    out: dict[str, float] = {}
    for side in ("home", "away"):
        prior = [vals for ts, vals in hist.get(g[f"{side}_team"], []) if ts < info_cutoff]
        if prior:
            for f, v in prior[-1].items():
                out[f"{side}_{f}"] = v
    return out


def run_real_odds_backtest(
    games: list[dict[str, Any]],
    market_rows: list[dict[str, Any]],
    start_date: str = "2025-01-01",
    end_date: str | None = None,
    retrain_every_days: int = 7,
    vig: float = 0.045,
    market_anchor_weight: float | None = None,
    min_ev: float = 0.05,
    max_disagreement: float = 0.15,
    max_bets_per_day: int = 3,
    initial_bankroll: float = 100.0,
    flat_stake: float = 1.0,
    kelly_fraction: float = 0.25,
    kelly_min_stake: float = 0.50,
    kelly_max_stake: float = 3.00,
    kelly_max_fraction: float = 0.03,
    history_lag_days: int = 0,
    boxscores: dict[str, dict[str, Any]] | None = None,
    moneyline_model_weight: float | None = None,
    moneyline_max_disagreement: float | None = None,
    moneyline_max_odds: float | None = None,
    development_seasons: tuple[str, ...] | None = None,
    holdout_season: str | None = None,
    trials_evaluated_count: int | None = None,
    frozen_protocol_id: str | None = None,
    anchor_schedule: Any = None,
) -> dict[str, Any]:
    """
    Walk-forward backtest against consensus opening/closing lines with zero lookahead leakage.

    The model/market blend is production's: `anchor_schedule` (default `config.model.anchor_schedule`) resolved
    at the opening line's hours to tip-off. `market_anchor_weight` (default `config.model.market_anchor_model_weight`)
    and `moneyline_model_weight` are only the fallbacks the schedule leaves to them, as in production; pass a
    disabled `MarketAnchorScheduleConfig` to evaluate fixed weights. `moneyline_max_odds=None` applies the
    configured cap, as production's guards do.
    """
    app_cfg = load_config()
    eval_cfg = app_cfg.evaluation
    exec_cfg = app_cfg.execution
    eff_dev_seasons = tuple(development_seasons) if development_seasons is not None else tuple(eval_cfg.development_seasons)
    eff_holdout = str(holdout_season) if holdout_season is not None else str(eval_cfg.holdout_season)
    eff_trials = int(trials_evaluated_count) if trials_evaluated_count is not None else int(eval_cfg.trials_evaluated_count)
    eff_protocol = str(frozen_protocol_id) if frozen_protocol_id is not None else str(eval_cfg.frozen_protocol_id)
    active_model_version = app_cfg.model.version_id
    schedule = anchor_schedule if anchor_schedule is not None else app_cfg.model.anchor_schedule
    fallback_weight = (
        float(market_anchor_weight) if market_anchor_weight is not None else float(app_cfg.model.market_anchor_model_weight)
    )
    eff_ml_max_odds = moneyline_max_odds if moneyline_max_odds is not None else app_cfg.model.moneyline_max_odds
    policy = OpeningPriceDecisionPolicy(
        model_version_id=active_model_version,
        anchor_schedule=schedule,
        market_anchor_weight=fallback_weight,
        moneyline_weight=moneyline_model_weight,
        max_disagreement=max_disagreement,
        moneyline_max_disagreement=moneyline_max_disagreement,
        moneyline_max_odds=eff_ml_max_odds,
        vig=vig,
        hours_to_tipoff=opening_line_hours_to_tipoff(schedule),
    )
    weights_used: dict[str, set[float]] = defaultdict(set)

    real = [g for g in games if not is_synthetic_game_id(g.get("game_id"))]
    real.sort(key=lambda g: (str(g["game_start_time"]), str(g["game_id"])))
    real = _with_current_ratings(real)
    if boxscores:
        real = attach_boxscore_features(real, boxscores, info_lag_days=history_lag_days)
    team_rating_hist = _team_rating_history(real)
    final_games = [g for g in real if g.get("status") == "FINAL" and g.get("home_score") is not None]
    market_by_game = match_market_to_games(market_rows, final_games)

    test_games = [
        g
        for g in final_games
        if g["game_id"] in market_by_game
        and str(g["game_start_time"])[:10] >= start_date
        and (end_date is None or str(g["game_start_time"])[:10] <= end_date)
    ]
    days: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for g in test_games:
        days[str(g["matchday_date"])].append(g)

    model = EnsembleStackingModel("model_f_ensemble_backtest")
    ml_cal = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    tot_cal = ProbabilityCalibrator(method="auto", min_samples_logistic=25, min_samples_isotonic=100)
    ml_va = VennAbersConformalInterval(window=1200, min_samples=60)
    tot_va = VennAbersConformalInterval(window=1200, min_samples=60)
    tot_closing_est = TotalsClosingEstimator()

    oos_ml: list[dict[str, Any]] = []
    oos_tot: list[dict[str, Any]] = []
    oos_tot_closing: list[dict[str, Any]] = []
    eval_rows: list[dict[str, Any]] = []
    bets: list[dict[str, Any]] = []
    uncapped_shadow_bets: list[dict[str, Any]] = []
    totals_clv_bets: list[dict[str, Any]] = []
    unpriceable_sides = 0
    kelly_bankroll = initial_bankroll
    last_train: datetime | None = None

    for day in sorted(days):
        day_games = sorted(days[day], key=lambda g: g["game_start_time"])
        cutoff = min(str(g["game_start_time"]) for g in day_games)
        cutoff_dt = parse_iso_utc(cutoff)
        info_cutoff = (cutoff_dt - timedelta(days=history_lag_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        history = [g for g in final_games if str(g["game_start_time"]) < info_cutoff]
        if len(history) < 150:
            continue
        if last_train is None or (cutoff_dt - last_train) >= timedelta(days=retrain_every_days):
            model.fit(history, info_cutoff)
            past_ml = [r for r in oos_ml if r["game_start_time"] < info_cutoff]
            past_tot = [r for r in oos_tot if r["game_start_time"] < info_cutoff]
            past_tot_close = [
                r
                for r in oos_tot_closing
                if r["game_start_time"] < info_cutoff and str(r.get("season")) != eff_holdout
            ]
            if len(past_ml) >= 25:
                ml_cal.fit(past_ml, info_cutoff)
                ml_va.fit(past_ml, info_cutoff)
            if len(past_tot) >= 25:
                tot_cal.fit(past_tot, info_cutoff)
                tot_va.fit(past_tot, info_cutoff)
            tot_closing_est = fit_totals_closing_estimator(past_tot_close)
            last_train = cutoff_dt

        candidates: list[dict[str, Any]] = []
        day_records: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for g in day_games:
            if history_lag_days > 0:
                g = {**g, **_lagged_team_ratings(g, team_rating_hist, info_cutoff)}
            m = market_by_game[g["game_id"]]
            season_val = str(m["season"])
            start_dt = parse_iso_utc(g["game_start_time"])
            decision_ts = (start_dt - timedelta(hours=DECISION_LEAD_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
            p_open_home = float(np.clip(m["open_home_win_prob"], 0.01, 0.99))
            p_close_home = float(np.clip(m["close_home_win_prob"], 0.01, 0.99))

            raw_home = float(model.predict_moneyline(g, history)["p_home"])
            cal_home = float(ml_cal.transform_single(raw_home))
            va_home = ml_va.predict_interval(raw_home)
            home_won = 1 if int(g["home_score"]) > int(g["away_score"]) else 0

            rec: dict[str, Any] = {
                "game_id": g["game_id"],
                "season": season_val,
                "matchday_date": day,
                "home_won": home_won,
                "raw_home": raw_home,
                "cal_home": cal_home,
                "anchored_home": None,  # production decision for the HOME side, set below
                "open_home": p_open_home,
                "close_home": p_close_home,
            }

            sides: list[tuple[str, str, float | None, float, float, float, dict[str, Any], str, float, float]] = [
                (
                    "moneyline",
                    "HOME",
                    None,
                    cal_home,
                    p_open_home,
                    p_close_home,
                    va_home,
                    "WON" if home_won == 1 else "LOST",
                    0.0,
                    raw_home,
                ),
                (
                    "moneyline",
                    "AWAY",
                    None,
                    1.0 - cal_home,
                    1.0 - p_open_home,
                    1.0 - p_close_home,
                    {"p0": 1.0 - va_home["p1"], "p1": 1.0 - va_home["p0"], "width": va_home["width"]},
                    "WON" if home_won == 0 else "LOST",
                    0.0,
                    1.0 - raw_home,
                ),
            ]

            line = m.get("open_total")
            tot_result = str(m.get("total_result_open") or "")
            if line is not None and tot_result in ("over", "under", "push"):
                tot_pred = model.predict_total_points(g, history, float(line))
                raw_over = float(tot_pred["p_over"])
                p_push_tot = float(tot_pred.get("p_push", 0.0))
                cal_res = calibrate_binary_with_push(
                    raw_over,
                    p_push=p_push_tot,
                    calibrator=tot_cal,
                    va_calibrator=tot_va,
                )
                cal_over = float(cal_res["cal_prob"])
                va_over = cal_res["va_interval"] or tot_va.predict_interval(raw_over)
                p_close_over = _close_over_prob_at_line(m.get("close_total"), m.get("close_over_prob"), float(line))
                rec.update(
                    {
                        "total_line": float(line),
                        "total_result": tot_result,
                        "raw_over": raw_over,
                        "cal_over": cal_over,
                        "anchored_over": None,  # production decision for the OVER side, set below
                        "p_push_tot": p_push_tot,
                        "close_over_at_open_line": p_close_over,
                        "close_total_line": m.get("close_total"),
                    }
                )
                if p_close_over is not None:
                    over_res = "PUSH" if tot_result == "push" else ("WON" if tot_result == "over" else "LOST")
                    under_res = "PUSH" if tot_result == "push" else ("WON" if tot_result == "under" else "LOST")
                    cal_under = max(0.0, 1.0 - cal_over - p_push_tot)
                    raw_under = max(0.0, 1.0 - raw_over - p_push_tot)
                    sides.append(("total_points", "OVER", float(line), cal_over, 0.5, p_close_over, va_over, over_res, p_push_tot, raw_over))
                    sides.append(
                        (
                            "total_points",
                            "UNDER",
                            float(line),
                            cal_under,
                            0.5,
                            1.0 - p_close_over,
                            {"p0": 1.0 - va_over["p1"], "p1": 1.0 - va_over["p0"], "width": va_over["width"]},
                            under_res,
                            p_push_tot,
                            raw_under,
                        )
                    )
                    clv_sig = tot_closing_est.predict(cal_over)
                    if clv_sig["qualifies"] and clv_sig["predicted_side"] in ("OVER", "UNDER"):
                        p_side = str(clv_sig["predicted_side"])
                        t_price = _price(0.5, vig)
                        t_res = over_res if p_side == "OVER" else under_res
                        t_close = p_close_over if p_side == "OVER" else (1.0 - p_close_over)
                        t_mult = (t_price - 1.0) if t_res == "WON" else (-1.0 if t_res == "LOST" else 0.0)
                        totals_clv_bets.append(
                            {
                                "game_id": g["game_id"],
                                "matchday_date": day,
                                "season": season_val,
                                "market": "total_points",
                                "selection": p_side,
                                "line_value": float(line),
                                "decimal_odds": t_price,
                                "stake_pen": flat_stake,
                                "net_profit_pen": round(flat_stake * t_mult, 4),
                                "status": t_res,
                                "clv_ev_pct": round(100.0 * (t_price * t_close - 1.0), 4),
                                "expected_move_pts": clv_sig["expected_move_pts"],
                            }
                        )
            # Quality-series anchored probabilities depend only on the opening consensus and schedule, so a game
            # stays in the full-slate quality series even if one side's vigged price is <= 1.0 (unbettable).
            rec["anchored_home"] = market_anchored_probability(
                float(np.clip(cal_home, 0.001, 0.999)),
                p_open_home,
                resolve_market_anchor_weight(
                    "moneyline",
                    hours_to_tipoff=policy.hours_to_tipoff,
                    fallback_weight=policy.market_anchor_weight,
                    moneyline_weight=policy.moneyline_weight,
                    schedule=policy.anchor_schedule,
                ),
            )
            if "cal_over" in rec:
                rec["anchored_over"] = market_anchored_probability(
                    float(np.clip(float(rec["cal_over"]), 0.001, 0.999)),
                    0.5,
                    resolve_market_anchor_weight(
                        "total_points",
                        hours_to_tipoff=policy.hours_to_tipoff,
                        fallback_weight=policy.market_anchor_weight,
                        moneyline_weight=policy.moneyline_weight,
                        schedule=policy.anchor_schedule,
                    ),
                )

            # Quotes known at decision time: only bettable opening sides (`price > 1.0`), so production's steam
            # rule yields 0 here (the closing line is after the decision and would be lookahead).
            priceable_sides: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
            for side in sides:
                market, sel, ln, _cal, p_open, *_rest = side
                if _bettable_price(p_open, vig) is None:
                    unpriceable_sides += 1
                    continue
                priceable_sides.append(
                    (
                        side,
                        opening_quote_record(
                            g["game_id"],
                            g["game_start_time"],
                            market,
                            sel,
                            ln,
                            p_open,
                            vig=vig,
                            hours_to_tipoff=policy.hours_to_tipoff,
                        ),
                    )
                )
            steam_map = compute_line_steam([q for _, q in priceable_sides])

            best_shadow_by_mkt: dict[str, dict[str, Any]] = {}
            for (market, sel, ln, cal_p, p_open, p_close, conf, result, p_push_s, raw_s), quote in priceable_sides:
                price = float(quote["decimal_odds"])
                opp = evaluate_opening_price_side(
                    policy,
                    quote,
                    game_start_time=g["game_start_time"],
                    decision_ts=decision_ts,
                    calibrated_prob=cal_p,
                    raw_model_prob=raw_s,
                    market_prob=p_open,
                    p_push=p_push_s,
                    conformal_interval=conf,
                    steam_delta=float((steam_map.get((market, sel)) or {}).get("steam_delta", 0.0)),
                )
                weights_used[market].add(float(opp["effective_model_weight"]))
                if (market, sel) == ("moneyline", "HOME"):
                    rec["anchored_home"] = float(opp["market_anchored_probability"])
                elif (market, sel) == ("total_points", "OVER"):
                    rec["anchored_over"] = float(opp["market_anchored_probability"])
                ev = float(opp["ev_unit"])
                # Production pre-bet guards (src/paper_trading/execution_helpers.py, `config.execution`).
                if ev > 0.0 and check_candidate_risk_guards(opp, execution_cfg=exec_cfg) is None:
                    sh_mult = (price - 1.0) if result == "WON" else (-1.0 if result == "LOST" else 0.0)
                    sh_row = {
                        "game_id": g["game_id"],
                        "matchday_date": day,
                        "season": season_val,
                        "market": market,
                        "selection": sel,
                        "line_value": ln,
                        "decimal_odds": price,
                        "ev_unit": ev,
                        "stake_pen": flat_stake,
                        "net_profit_pen": round(flat_stake * sh_mult, 4),
                        "status": result,
                        "clv_ev_pct": round(100.0 * (price * p_close - 1.0), 4),
                    }
                    prev_sh = best_shadow_by_mkt.get(market)
                    if prev_sh is None or ev > prev_sh["ev_unit"]:
                        best_shadow_by_mkt[market] = sh_row

                if check_candidate_edge_and_model_guards(opp, min_ev_threshold=min_ev, execution_cfg=exec_cfg) is None:
                    candidates.append(
                        {
                            "game_id": g["game_id"],
                            "matchday_date": day,
                            "season": season_val,
                            "market": market,
                            "selection": sel,
                            "line_value": ln,
                            "decimal_odds": price,
                            "anchored_prob": float(opp["estimated_probability"]),
                            "calibrated_model_probability": float(opp["calibrated_model_probability"]),
                            "p_push": p_push_s,
                            "hours_to_tipoff": opp["hours_to_tipoff"],
                            "scheduled_model_weight": float(opp["scheduled_model_weight"]),
                            "effective_model_weight": float(opp["effective_model_weight"]),
                            "ev_unit": ev,
                            "p_open": p_open,
                            "p_close": p_close,
                            "result": result,
                        }
                    )
            day_records.append((g, rec))
            uncapped_shadow_bets.extend(best_shadow_by_mkt.values())

        chosen: list[dict[str, Any]] = []
        seen_games: set[str] = set()
        start_kelly_bankroll = kelly_bankroll
        for c in sorted(candidates, key=lambda c: c["ev_unit"], reverse=True):
            if c["game_id"] in seen_games or len(chosen) >= max_bets_per_day:
                continue
            k_stake = fractional_kelly_stake(
                prob=c["anchored_prob"],
                decimal_odds=c["decimal_odds"],
                bankroll_pen=start_kelly_bankroll,
                kelly_fraction=kelly_fraction,
                min_stake_pen=kelly_min_stake,
                max_stake_pen=kelly_max_stake,
                max_bankroll_fraction=kelly_max_fraction,
            )
            if k_stake <= 0.0:
                continue
            seen_games.add(c["game_id"])
            chosen.append({**c, "_k_stake": k_stake})
        for c in chosen:
            odds = c["decimal_odds"]
            k_stake = c.pop("_k_stake")
            mult = (odds - 1.0) if c["result"] == "WON" else (-1.0 if c["result"] == "LOST" else 0.0)
            clv_pct = 100.0 * (odds * c["p_close"] - 1.0)
            kelly_bankroll += k_stake * mult
            bets.append(
                {
                    **c,
                    "stake_pen": flat_stake,
                    "net_profit_pen": round(flat_stake * mult, 4),
                    "kelly_stake_pen": k_stake,
                    "kelly_net_profit_pen": round(k_stake * mult, 4),
                    "status": c["result"],
                    "clv_ev_pct": round(clv_pct, 4),
                }
            )

        for g, rec in day_records:
            eval_rows.append({**rec, "game_start_time": g["game_start_time"]})
            oos_ml.append({"game_start_time": g["game_start_time"], "raw_probability": rec["raw_home"], "outcome": rec["home_won"]})
            if rec.get("total_result") in ("over", "under"):
                oos_tot.append(
                    {
                        "game_start_time": g["game_start_time"],
                        "raw_probability": rec["raw_over"],
                        "outcome": 1 if rec["total_result"] == "over" else 0,
                    }
                )
            if rec.get("total_line") is not None and rec.get("close_total_line") is not None:
                oos_tot_closing.append(
                    {
                        "game_start_time": g["game_start_time"],
                        "season": rec["season"],
                        "p_over": rec["cal_over"],
                        "tot_open_line": rec["total_line"],
                        "tot_close_line": rec["close_total_line"],
                    }
                )

    return summarize_backtest_results(
        eval_rows,
        bets,
        initial_bankroll,
        kelly_bankroll,
        {
            "start_date": start_date,
            "end_date": end_date,
            "retrain_every_days": retrain_every_days,
            "vig_assumption": vig,
            "market_anchor": {
                "decision_function": (
                    f"{evaluate_scheduled_market_opportunity.__module__}.{evaluate_scheduled_market_opportunity.__qualname__}"
                ),
                "schedule": describe_market_anchor_schedule(schedule),
                "fallback_model_weight": fallback_weight,
                "moneyline_fallback_model_weight": moneyline_model_weight,
                "decision_hours_to_tipoff": policy.hours_to_tipoff,
                "hours_to_tipoff_basis": "opening_line_quoted_at_least_horizon_hours_before_tipoff",
                "steam_basis": "quotes_known_at_decision_opening_line_only",
                # Weights the decisions actually used (after steam modulation), per market.
                "effective_model_weights": {mkt: sorted(ws) for mkt, ws in sorted(weights_used.items())},
            },
            "min_ev": min_ev,
            "history_lag_days": history_lag_days,
            "max_disagreement": max_disagreement,
            "max_bets_per_day": max_bets_per_day,
            "moneyline_max_disagreement": moneyline_max_disagreement,
            "moneyline_max_odds": eff_ml_max_odds,
            "kelly": {
                "fraction": kelly_fraction,
                "min_stake": kelly_min_stake,
                "max_stake": kelly_max_stake,
                "max_bankroll_fraction": kelly_max_fraction,
            },
            "market_rows": len(market_rows),
            "matched_games": len(market_by_game),
            "test_games": len(test_games),
            "unpriceable_sides_skipped": unpriceable_sides,
            "boxscore_features": bool(boxscores),
            "evaluation": {
                "development_seasons": list(eff_dev_seasons),
                "holdout_season": eff_holdout,
                "trials_evaluated_count": eff_trials,
                "frozen_protocol_id": eff_protocol,
                "season_holdout_contaminated": eval_cfg.season_holdout_contaminated,
                "forward_holdout_start_utc": eval_cfg.forward_holdout_start_utc,
            },
        },
        DATA_ATTRIBUTION,
        uncapped_shadow_bets=uncapped_shadow_bets,
        totals_clv_bets=totals_clv_bets,
        totals_estimator_meta={
            "intercept": tot_closing_est.intercept,
            "slope": tot_closing_est.slope,
            "sample_size": tot_closing_est.sample_size,
            "is_active": tot_closing_est.is_active,
            "holdout_excluded_from_fit": True,
        },
        development_seasons=eff_dev_seasons,
        holdout_season=eff_holdout,
        trials_evaluated_count=eff_trials,
        frozen_protocol_id=eff_protocol,
        season_holdout_contaminated=eval_cfg.season_holdout_contaminated,
        forward_holdout_start_utc=eval_cfg.forward_holdout_start_utc,
    )
