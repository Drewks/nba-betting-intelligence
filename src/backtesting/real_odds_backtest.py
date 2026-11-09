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
  3. Decisions are taken at the OPENING consensus price with the production rules
     (`evaluate_market_opportunity` with market anchoring, EV threshold, model/market disagreement
     guard, long-shot guard, conformal-width guard, CLV meta-label, one bet per game, top-3 per day).
  4. Bets are graded with the real result; CLV is measured against the CLOSING no-vig consensus.

Assumptions (stated, not hidden):
  - The data has no-vig probabilities, not bookmaker prices. A bettable price is reconstructed as
    fair_price / (1 + vig) with a proportional margin `vig` (default 4.5%, a typical single retail book;
    line shopping across books usually does better, see the sensitivity run).
  - Totals: the opening main line is the line quoted closest to 50/50, so its opening over probability
    is taken as 0.50. The closing fair probability at the OPENING line is approximated with a normal
    margin model: Phi(Phi^-1(close_over_prob) + (close_total - open_line) / TOTAL_SIGMA).
"""

from __future__ import annotations

from collections import defaultdict
import csv
from datetime import datetime, timedelta, timezone
import io
import math
from pathlib import Path
from typing import Any
import urllib.request

import numpy as np
from scipy.stats import norm

from src.backtesting.backtester import compute_block_bootstrap_roi_ci, compute_drawdown_series
from src.calibration.calibrator import (
    ProbabilityCalibrator,
    VennAbersConformalInterval,
    compute_brier_score,
    compute_log_loss,
)
from src.features.team_ratings import compute_pregame_team_ratings, is_synthetic_game_id
from src.ingestion.normalizer import normalize_team_code
from src.models.statistical_models import EnsembleStackingModel
from src.paper_trading.staking import fractional_kelly_stake
from src.prediction.ev_calculator import evaluate_market_opportunity
from src.validation.validator import parse_iso_utc

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


# ------------------------------------------------------------------------------------------------
# Data loading
# ------------------------------------------------------------------------------------------------

def download_market_csvs(dest_dir: Path, seasons: list[str] | None = None, timeout: int = 60) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for season in seasons or list(DATA_SOURCES):
        url = DATA_SOURCES[season]
        out = dest_dir / f"market_consensus_{season}.csv"
        if not out.exists():
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


# ------------------------------------------------------------------------------------------------
# Backtest
# ------------------------------------------------------------------------------------------------

def _price(fair_prob: float, vig: float) -> float:
    return round(1.0 / (max(1e-6, fair_prob) * (1.0 + vig)), 4)


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
        out.append({**g, **{k: r[k] for k in (
            "home_off_rtg", "home_def_rtg", "home_pace", "away_off_rtg", "away_def_rtg", "away_pace",
            "home_rest_days", "away_rest_days",
        )}} if r else dict(g))
    return out


def run_real_odds_backtest(
    games: list[dict[str, Any]],
    market_rows: list[dict[str, Any]],
    start_date: str = "2025-01-01",
    end_date: str | None = None,
    retrain_every_days: int = 7,
    vig: float = 0.045,
    model_weight: float = 0.30,
    min_ev: float = 0.05,
    max_disagreement: float = 0.15,
    max_bets_per_day: int = 3,
    initial_bankroll: float = 100.0,
    flat_stake: float = 1.0,
    kelly_fraction: float = 0.25,
    kelly_min_stake: float = 0.50,
    kelly_max_stake: float = 3.00,
    kelly_max_fraction: float = 0.03,
) -> dict[str, Any]:
    real = [g for g in games if not is_synthetic_game_id(g.get("game_id"))]
    real.sort(key=lambda g: (str(g["game_start_time"]), str(g["game_id"])))
    real = _with_current_ratings(real)
    final_games = [g for g in real if g.get("status") == "FINAL" and g.get("home_score") is not None]
    market_by_game = match_market_to_games(market_rows, final_games)

    test_games = [
        g for g in final_games
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
    oos_ml: list[dict[str, Any]] = []
    oos_tot: list[dict[str, Any]] = []
    eval_rows: list[dict[str, Any]] = []
    bets: list[dict[str, Any]] = []
    kelly_bankroll = initial_bankroll
    last_train: datetime | None = None

    for day in sorted(days):
        day_games = sorted(days[day], key=lambda g: g["game_start_time"])
        cutoff = min(str(g["game_start_time"]) for g in day_games)
        cutoff_dt = parse_iso_utc(cutoff)
        history = [g for g in final_games if str(g["game_start_time"]) < cutoff]
        if len(history) < 150:
            continue
        if last_train is None or (cutoff_dt - last_train) >= timedelta(days=retrain_every_days):
            model.fit(history, cutoff)
            past_ml = [r for r in oos_ml if r["game_start_time"] < cutoff]
            past_tot = [r for r in oos_tot if r["game_start_time"] < cutoff]
            if len(past_ml) >= 25:
                ml_cal.fit(past_ml, cutoff)
                ml_va.fit(past_ml, cutoff)
            if len(past_tot) >= 25:
                tot_cal.fit(past_tot, cutoff)
                tot_va.fit(past_tot, cutoff)
            last_train = cutoff_dt

        candidates: list[dict[str, Any]] = []
        day_records: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for g in day_games:
            m = market_by_game[g["game_id"]]
            start_dt = parse_iso_utc(g["game_start_time"])
            decision_ts = (start_dt - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
            p_open_home = float(np.clip(m["open_home_win_prob"], 0.01, 0.99))
            p_close_home = float(np.clip(m["close_home_win_prob"], 0.01, 0.99))

            raw_home = float(model.predict_moneyline(g, history)["p_home"])
            cal_home = float(ml_cal.transform_single(raw_home))
            va_home = ml_va.predict_interval(raw_home)
            home_won = 1 if int(g["home_score"]) > int(g["away_score"]) else 0

            rec: dict[str, Any] = {
                "game_id": g["game_id"], "season": m["season"], "matchday_date": day,
                "home_won": home_won, "raw_home": raw_home, "cal_home": cal_home,
                "anchored_home": model_weight * cal_home + (1.0 - model_weight) * p_open_home,
                "open_home": p_open_home, "close_home": p_close_home,
            }

            sides: list[tuple[str, str, float | None, float, float, float, dict[str, float], str]] = [
                ("moneyline", "HOME", None, cal_home, p_open_home, p_close_home, va_home,
                 "WON" if home_won == 1 else "LOST"),
                ("moneyline", "AWAY", None, 1.0 - cal_home, 1.0 - p_open_home, 1.0 - p_close_home,
                 {"p0": 1.0 - va_home["p1"], "p1": 1.0 - va_home["p0"], "width": va_home["width"]},
                 "WON" if home_won == 0 else "LOST"),
            ]

            line = m.get("open_total")
            tot_result = str(m.get("total_result_open") or "")
            if line is not None and tot_result in ("over", "under", "push"):
                raw_over = float(model.predict_total_points(g, history, float(line))["p_over"])
                cal_over = float(tot_cal.transform_single(raw_over))
                va_over = tot_va.predict_interval(raw_over)
                p_close_over = _close_over_prob_at_line(m.get("close_total"), m.get("close_over_prob"), float(line))
                rec.update({
                    "total_line": float(line), "total_result": tot_result,
                    "raw_over": raw_over, "cal_over": cal_over,
                    "anchored_over": model_weight * cal_over + (1.0 - model_weight) * 0.5,
                    "close_over_at_open_line": p_close_over,
                })
                if p_close_over is not None:
                    over_res = "PUSH" if tot_result == "push" else ("WON" if tot_result == "over" else "LOST")
                    under_res = "PUSH" if tot_result == "push" else ("WON" if tot_result == "under" else "LOST")
                    sides.append(("total_points", "OVER", float(line), cal_over, 0.5, p_close_over, va_over, over_res))
                    sides.append(("total_points", "UNDER", float(line), 1.0 - cal_over, 0.5, 1.0 - p_close_over,
                                  {"p0": 1.0 - va_over["p1"], "p1": 1.0 - va_over["p0"], "width": va_over["width"]},
                                  under_res))
            day_records.append((g, rec))

            for market, sel, ln, cal_p, p_open, p_close, conf, result in sides:
                price = _price(p_open, vig)
                counter = _price(1.0 - p_open, vig)
                odds_record = {
                    "odds_id": f"BT_{g['game_id']}_{market}_{sel}", "game_id": g["game_id"],
                    "provider": "consensus_open", "market": market, "selection": sel, "line_value": ln,
                    "decimal_odds": price, "counterpart_decimal_odds": counter, "captured_at": decision_ts,
                }
                opp = evaluate_market_opportunity(
                    estimated_prob=float(np.clip(cal_p, 0.001, 0.999)),
                    uncertainty_std=0.05,
                    odds_record=odds_record,
                    game_start_time=g["game_start_time"],
                    model_version_id="model_f_ensemble_backtest",
                    simulated_prediction_time=decision_ts,
                    market_consensus_prob=p_open,
                    model_weight=model_weight,
                    max_disagreement=max_disagreement,
                    conformal_interval=conf,
                )
                ev = float(opp["ev_unit"])
                reason = None
                if ev <= min_ev:
                    reason = "EV_BELOW_THRESHOLD"
                elif abs(float(opp.get("model_market_disagreement") or 0.0)) > max_disagreement:
                    reason = "MODEL_MARKET_DISAGREEMENT"
                elif ev > 0.45:
                    reason = "UNVERIFIED_INJURY_OR_LINEUP_OUTLIER"
                elif price > 3.50 and ev < 0.15:
                    reason = "EXCESSIVE_LONGSHOT_VARIANCE"
                elif conf.get("width") is not None and float(conf["width"]) > 0.22:
                    reason = "CONFORMAL_UNCERTAINTY_TOO_WIDE"
                elif opp.get("meta_label_pass") is False:
                    reason = "NEGATIVE_EXPECTED_CLV"
                if reason is None:
                    candidates.append({
                        "game_id": g["game_id"], "matchday_date": day, "season": m["season"],
                        "market": market, "selection": sel, "line_value": ln, "decimal_odds": price,
                        "anchored_prob": float(opp["estimated_probability"]), "ev_unit": ev,
                        "p_open": p_open, "p_close": p_close, "result": result,
                    })

        # Selection: best EV first, one bet per game, at most `max_bets_per_day`
        chosen: list[dict[str, Any]] = []
        seen_games: set[str] = set()
        for c in sorted(candidates, key=lambda c: c["ev_unit"], reverse=True):
            if c["game_id"] in seen_games or len(chosen) >= max_bets_per_day:
                continue
            seen_games.add(c["game_id"])
            chosen.append(c)

        start_kelly_bankroll = kelly_bankroll
        for c in chosen:
            odds = c["decimal_odds"]
            k_stake = fractional_kelly_stake(
                prob=c["anchored_prob"], decimal_odds=odds, bankroll_pen=start_kelly_bankroll,
                kelly_fraction=kelly_fraction, min_stake_pen=kelly_min_stake,
                max_stake_pen=kelly_max_stake, max_bankroll_fraction=kelly_max_fraction,
            )
            mult = (odds - 1.0) if c["result"] == "WON" else (-1.0 if c["result"] == "LOST" else 0.0)
            clv_pct = 100.0 * (odds * c["p_close"] - 1.0)
            kelly_bankroll += k_stake * mult
            bets.append({
                **c,
                "stake_pen": flat_stake,
                "net_profit_pen": round(flat_stake * mult, 4),
                "kelly_stake_pen": k_stake,
                "kelly_net_profit_pen": round(k_stake * mult, 4),
                "status": c["result"],
                "clv_ev_pct": round(clv_pct, 4),
            })

        # Outcomes become available only after the matchday: record OOS predictions afterwards
        for g, rec in day_records:
            eval_rows.append(rec)
            oos_ml.append({"game_start_time": g["game_start_time"], "raw_probability": rec["raw_home"], "outcome": rec["home_won"]})
            if rec.get("total_result") in ("over", "under"):
                oos_tot.append({"game_start_time": g["game_start_time"], "raw_probability": rec["raw_over"],
                                "outcome": 1 if rec["total_result"] == "over" else 0})

    return _summarize(eval_rows, bets, initial_bankroll, kelly_bankroll, {
        "start_date": start_date, "end_date": end_date, "retrain_every_days": retrain_every_days,
        "vig_assumption": vig, "model_weight": model_weight, "min_ev": min_ev,
        "max_disagreement": max_disagreement, "max_bets_per_day": max_bets_per_day,
        "kelly": {"fraction": kelly_fraction, "min_stake": kelly_min_stake, "max_stake": kelly_max_stake,
                  "max_bankroll_fraction": kelly_max_fraction},
        "market_rows": len(market_rows), "matched_games": len(market_by_game), "test_games": len(test_games),
    })


def _score(probs: list[float], ys: list[int]) -> dict[str, float]:
    return {"n": len(ys), "brier": compute_brier_score(probs, ys), "log_loss": compute_log_loss(probs, ys)}


def _summarize(
    eval_rows: list[dict[str, Any]],
    bets: list[dict[str, Any]],
    initial_bankroll: float,
    kelly_bankroll: float,
    config: dict[str, Any],
) -> dict[str, Any]:
    out: dict[str, Any] = {"config": config, "data_attribution": DATA_ATTRIBUTION,
                           "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if eval_rows:
        y = [r["home_won"] for r in eval_rows]
        out["moneyline_quality"] = {
            k: _score([r[f] for r in eval_rows], y)
            for k, f in (("model_raw", "raw_home"), ("model_calibrated", "cal_home"),
                         ("model_anchored_30_70", "anchored_home"), ("market_open", "open_home"),
                         ("market_close", "close_home"))
        }
        tot = [r for r in eval_rows if r.get("total_result") in ("over", "under") and r.get("close_over_at_open_line") is not None]
        if tot:
            yt = [1 if r["total_result"] == "over" else 0 for r in tot]
            out["totals_quality_at_open_line"] = {
                "model_raw": _score([r["raw_over"] for r in tot], yt),
                "model_calibrated": _score([r["cal_over"] for r in tot], yt),
                "market_open_assumed_0.5": _score([0.5] * len(tot), yt),
                "market_close_normal_approx": _score([r["close_over_at_open_line"] for r in tot], yt),
            }

    settled = [b for b in bets if b["status"] in ("WON", "LOST")]
    staked = sum(b["stake_pen"] for b in settled)
    profit = sum(b["net_profit_pen"] for b in bets)
    k_staked = sum(b["kelly_stake_pen"] for b in settled)
    clvs = [b["clv_ev_pct"] for b in bets]
    clv_blocks = compute_block_bootstrap_roi_ci(
        [{"matchday_date": b["matchday_date"], "net_profit_pen": b["clv_ev_pct"] / 100.0, "stake_pen": 1.0} for b in bets]
    ) if bets else {}

    def _group(key: str) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for b in bets:
            groups[str(b[key])].append(b)
        res = {}
        for k, items in sorted(groups.items()):
            s = [b for b in items if b["status"] in ("WON", "LOST")]
            st = sum(b["stake_pen"] for b in s)
            roi_ci = compute_block_bootstrap_roi_ci(items)
            clv_ci = compute_block_bootstrap_roi_ci(
                [{"matchday_date": b["matchday_date"], "net_profit_pen": b["clv_ev_pct"] / 100.0, "stake_pen": 1.0} for b in items]
            )
            res[k] = {
                "bets": len(items),
                "won": sum(1 for b in s if b["status"] == "WON"),
                "roi_flat_pct": round(100.0 * sum(b["net_profit_pen"] for b in items) / st, 2) if st else None,
                "roi_ci95": [roi_ci.get("roi_ci_lower_95_pct"), roi_ci.get("roi_ci_upper_95_pct")],
                "mean_clv_pct": round(float(np.mean([b["clv_ev_pct"] for b in items])), 3) if items else None,
                "clv_ci95": [clv_ci.get("roi_ci_lower_95_pct"), clv_ci.get("roi_ci_upper_95_pct")],
            }
        return res

    out["betting"] = {
        "bets": len(bets),
        "settled": len(settled),
        "won": sum(1 for b in settled if b["status"] == "WON"),
        "push_or_void": len(bets) - len(settled),
        "flat_stake": {
            "net_profit_pen": round(profit, 2),
            "roi_pct": round(100.0 * profit / staked, 2) if staked else None,
            "bootstrap_95": compute_block_bootstrap_roi_ci(bets) if bets else {},
            "drawdown": compute_drawdown_series(initial_bankroll, bets),
        },
        "kelly_stake": {
            "final_bankroll_pen": round(kelly_bankroll, 2),
            "net_profit_pen": round(kelly_bankroll - initial_bankroll, 2),
            "total_staked_pen": round(k_staked, 2),
            "roi_pct": round(100.0 * (kelly_bankroll - initial_bankroll) / k_staked, 2) if k_staked else None,
            "mean_stake_pen": round(float(np.mean([b["kelly_stake_pen"] for b in bets])), 2) if bets else None,
            "drawdown": compute_drawdown_series(
                initial_bankroll, [{"net_profit_pen": b["kelly_net_profit_pen"]} for b in bets]
            ),
        },
        "clv": {
            "mean_clv_ev_pct": round(float(np.mean(clvs)), 3) if clvs else None,
            "beat_close_rate": round(float(np.mean([c > 0 for c in clvs])), 4) if clvs else None,
            "bootstrap_95_pct": {
                "lower": clv_blocks.get("roi_ci_lower_95_pct"), "upper": clv_blocks.get("roi_ci_upper_95_pct"),
            } if clv_blocks else {},
        },
        "by_market": _group("market"),
        "by_season": _group("season"),
    }
    out["bets_sample"] = bets[:20]
    out["bets"] = bets
    return out


def render_markdown(result: dict[str, Any], sensitivity: dict[str, Any] | None = None) -> str:
    cfg = result["config"]
    lines = [
        "# Backtest con cuotas reales (consenso de apertura/cierre, sin margen)",
        "",
        f"- Generado: `{result['generated_at_utc']}`",
        f"- {result['data_attribution']}",
        f"- Periodo de prueba desde `{cfg['start_date']}` | partidos con mercado emparejado: `{cfg['test_games']}`",
        f"- Reentrenamiento cada `{cfg['retrain_every_days']}` días | margen supuesto `{cfg['vig_assumption'] * 100:.1f}%` | "
        f"peso del modelo `{cfg['model_weight']}` | EV mínimo `{cfg['min_ev'] * 100:.0f}%`",
        "",
        "## 1. Calidad probabilística fuera de muestra (todos los partidos)",
        "",
        "| Serie | Mercado | N | Brier | LogLoss |",
        "| :--- | :--- | ---: | ---: | ---: |",
    ]
    for name, sc in (result.get("moneyline_quality") or {}).items():
        lines.append(f"| `{name}` | moneyline | {sc['n']} | {sc['brier']:.5f} | {sc['log_loss']:.5f} |")
    for name, sc in (result.get("totals_quality_at_open_line") or {}).items():
        lines.append(f"| `{name}` | totals (línea de apertura) | {sc['n']} | {sc['brier']:.5f} | {sc['log_loss']:.5f} |")
    b = result["betting"]
    fs, ks, clv = b["flat_stake"], b["kelly_stake"], b["clv"]
    boot = fs.get("bootstrap_95") or {}
    lines += [
        "",
        "## 2. Apuestas simuladas (reglas de producción, precio de apertura)",
        "",
        f"- Apuestas: `{b['bets']}` (ganadas `{b['won']}` / liquidadas `{b['settled']}`, push `{b['push_or_void']}`)",
        f"- **Stake fijo S/1**: neto `S/{fs['net_profit_pen']:+.2f}` | ROI `{fs['roi_pct']}%` | "
        f"IC95 bootstrap `[{boot.get('roi_ci_lower_95_pct')}%, {boot.get('roi_ci_upper_95_pct')}%]` | "
        f"MaxDD `{fs['drawdown']['max_drawdown_pct']:.2f}%`",
        f"- **Stake Kelly 25%** (S/{cfg['kelly']['min_stake']:.2f}–S/{cfg['kelly']['max_stake']:.2f}): banca final "
        f"`S/{ks['final_bankroll_pen']:.2f}` | ROI `{ks['roi_pct']}%` | stake medio `S/{ks['mean_stake_pen']}` | "
        f"MaxDD `{ks['drawdown']['max_drawdown_pct']:.2f}%`",
        f"- **CLV vs cierre sin margen**: media `{clv['mean_clv_ev_pct']}%` | gana al cierre `{clv['beat_close_rate']}` | "
        f"IC95 `[{(clv.get('bootstrap_95_pct') or {}).get('lower')}%, {(clv.get('bootstrap_95_pct') or {}).get('upper')}%]`",
        "",
        "| Grupo | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |",
        "| :--- | ---: | ---: | ---: | ---: |",
    ]

    def _ci(v: list[Any] | None) -> str:
        return f"[{v[0]:.1f}, {v[1]:.1f}]" if v and v[0] is not None and v[1] is not None else "[n/d]"

    for label, grp in (("mercado", b["by_market"]), ("temporada", b["by_season"])):
        for k, v in grp.items():
            lines.append(
                f"| {label}: `{k}` | {v['bets']} | {v['won']} | {v['roi_flat_pct']}% {_ci(v.get('roi_ci95'))} | "
                f"{v['mean_clv_pct']}% {_ci(v.get('clv_ci95'))} |"
            )
    if sensitivity:
        lines += ["", "## 3. Sensibilidad al margen supuesto", "",
                  "| Margen | Mercado | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |",
                  "| ---: | :--- | ---: | ---: | ---: | ---: |"]
        for vig_label, res in sensitivity.items():
            for mk, v in res["betting"]["by_market"].items():
                lines.append(
                    f"| {vig_label} | `{mk}` | {v['bets']} | {v['won']} | {v['roi_flat_pct']}% {_ci(v.get('roi_ci95'))} | "
                    f"{v['mean_clv_pct']}% {_ci(v.get('clv_ci95'))} |"
                )
    lines += [
        "",
        "## Supuestos",
        "- Precio apostable = cuota justa de apertura / (1 + margen). La fuente publica probabilidades sin margen, no precios de casas.",
        "- Totales: la línea principal de apertura es la más cercana a 50/50 (p=0.50); el cierre a esa línea se aproxima con un modelo normal (σ=18).",
        "- Las features usan solo partidos que empezaron antes del primer partido de la jornada; los calibradores solo predicciones previas.",
    ]
    return "\n".join(lines) + "\n"
