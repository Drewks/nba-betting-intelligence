"""
Statistical summarization, holdout partitioning, multiple-testing correction,
and Markdown reporting helpers for `real_odds_backtest.py`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import math
from typing import Any

import numpy as np
from scipy.stats import t as student_t_dist

from src.backtesting.metrics import compute_block_bootstrap_roi_ci, compute_drawdown_series
from src.calibration.calibrator import compute_brier_score, compute_log_loss


def score_probabilities(probs: list[float], ys: list[int]) -> dict[str, float]:
    """Computes sample count, Brier score, and LogLoss."""
    return {
        "n": len(ys),
        "brier": compute_brier_score(probs, ys),
        "log_loss": compute_log_loss(probs, ys),
    }


def compute_multiple_testing_stats(
    bets: list[dict[str, Any]],
    trials_evaluated_count: int = 1,
) -> dict[str, Any]:
    """
    Computes one-sided Student-t p-values on flat 1u net profits and CLV alongside
    Bonferroni correction across `trials_evaluated_count`.
    """
    trials = max(1, int(trials_evaluated_count))
    settled = [b for b in bets if b.get("status") in ("WON", "LOST")]
    clvs = [float(b["clv_ev_pct"]) for b in bets if b.get("clv_ev_pct") is not None]

    roi_raw_p: float | None = None
    roi_bonf_p: float | None = None
    roi_t_stat: float | None = None
    if len(settled) >= 2:
        profits = np.asarray([float(b.get("net_profit_pen") or 0.0) for b in settled], dtype=float)
        std = float(np.std(profits, ddof=1))
        if std > 1e-12:
            t_val = float(np.mean(profits)) / (std / math.sqrt(len(profits)))
            roi_t_stat = round(t_val, 4)
            roi_raw_p = float(np.clip(student_t_dist.sf(t_val, df=len(profits) - 1), 0.0, 1.0))
            roi_bonf_p = min(1.0, roi_raw_p * trials)

    clv_raw_p: float | None = None
    clv_bonf_p: float | None = None
    clv_t_stat: float | None = None
    if len(clvs) >= 2:
        c_arr = np.asarray(clvs, dtype=float)
        c_std = float(np.std(c_arr, ddof=1))
        if c_std > 1e-12:
            t_clv = float(np.mean(c_arr)) / (c_std / math.sqrt(len(c_arr)))
            clv_t_stat = round(t_clv, 4)
            clv_raw_p = float(np.clip(student_t_dist.sf(t_clv, df=len(c_arr) - 1), 0.0, 1.0))
            clv_bonf_p = min(1.0, clv_raw_p * trials)

    return {
        "trials_evaluated_count": trials,
        "method": "bonferroni_one_sided_t",
        "roi": {
            "n_settled": len(settled),
            "t_stat": roi_t_stat,
            "raw_p_value": round(roi_raw_p, 6) if roi_raw_p is not None else None,
            "bonferroni_p_value": round(roi_bonf_p, 6) if roi_bonf_p is not None else None,
            "significant_bonferroni_05": bool(roi_bonf_p is not None and roi_bonf_p < 0.05),
        },
        "clv": {
            "n": len(clvs),
            "t_stat": clv_t_stat,
            "raw_p_value": round(clv_raw_p, 6) if clv_raw_p is not None else None,
            "bonferroni_p_value": round(clv_bonf_p, 6) if clv_bonf_p is not None else None,
            "significant_bonferroni_05": bool(clv_bonf_p is not None and clv_bonf_p < 0.05),
        },
    }


def summarize_unit_track(
    bets: list[dict[str, Any]],
    trials_evaluated_count: int = 1,
) -> dict[str, Any]:
    """Summarizes an auxiliary 1u flat evaluation track (e.g. uncapped_shadow or totals_clv_targeted)."""
    settled = [b for b in bets if b.get("status") in ("WON", "LOST")]
    staked = sum(float(b.get("stake_pen") or 1.0) for b in settled)
    profit = sum(float(b.get("net_profit_pen") or 0.0) for b in bets)
    clvs = [float(b["clv_ev_pct"]) for b in bets if b.get("clv_ev_pct") is not None]

    by_market: dict[str, dict[str, Any]] = {}
    for mkt in sorted({str(b.get("market") or "unknown") for b in bets}):
        m_items = [b for b in bets if b.get("market") == mkt]
        m_s = [b for b in m_items if b.get("status") in ("WON", "LOST")]
        m_staked = sum(float(b.get("stake_pen") or 1.0) for b in m_s)
        m_profit = sum(float(b.get("net_profit_pen") or 0.0) for b in m_items)
        m_clvs = [float(b["clv_ev_pct"]) for b in m_items if b.get("clv_ev_pct") is not None]
        by_market[mkt] = {
            "bets": len(m_items),
            "settled": len(m_s),
            "won": sum(1 for b in m_s if b.get("status") == "WON"),
            "roi_1u_pct": round(100.0 * m_profit / m_staked, 2) if m_staked else None,
            "mean_clv_pct": round(float(np.mean(m_clvs)), 3) if m_clvs else None,
        }

    return {
        "bets": len(bets),
        "settled": len(settled),
        "won": sum(1 for b in settled if b.get("status") == "WON"),
        "push_or_void": len(bets) - len(settled),
        "net_profit_1u": round(profit, 4),
        "roi_1u_pct": round(100.0 * profit / staked, 2) if staked else None,
        "mean_clv_pct": round(float(np.mean(clvs)), 3) if clvs else None,
        "beat_close_rate": round(float(np.mean([c > 0.0 for c in clvs])), 4) if clvs else None,
        "multiple_testing": compute_multiple_testing_stats(bets, trials_evaluated_count),
        "by_market": by_market,
    }


def compute_line_movement_signal(eval_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Rule-free test across ALL games: does calibrated disagreement with opening line predict
    the direction of open->close movement?
    """
    def _stats(rows: list[tuple[str, float, float]]) -> dict[str, Any]:
        moved = [(d, x, y) for d, x, y in rows if abs(y) > 1e-9 and abs(x) > 1e-9]
        if len(moved) < 30:
            return {"n": len(moved)}
        xs = np.asarray([x for _, x, _ in moved])
        ys = np.asarray([y for _, _, y in moved])
        corr = float(np.corrcoef(xs, ys)[0, 1])
        by_day: dict[str, list[int]] = defaultdict(list)
        for i, (d, _, _) in enumerate(moved):
            by_day[d].append(i)
        keys = sorted(by_day)
        rng = np.random.default_rng(42)
        boots = []
        for _ in range(500):
            idx = [i for k in rng.choice(len(keys), size=len(keys)) for i in by_day[keys[int(k)]]]
            if len(idx) > 2:
                boots.append(float(np.corrcoef(xs[idx], ys[idx])[0, 1]))
        return {
            "n": len(moved),
            "correlation": round(corr, 4),
            "correlation_ci95": [round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)],
            "directional_hit_rate": round(float(np.mean(np.sign(xs) == np.sign(ys))), 4),
        }

    out: dict[str, Any] = {}
    for season in sorted({str(r["season"]) for r in eval_rows}) + ["ALL"]:
        rows = [r for r in eval_rows if season == "ALL" or str(r["season"]) == season]
        out[season] = {
            "moneyline": _stats([(r["matchday_date"], r["cal_home"] - r["open_home"], r["close_home"] - r["open_home"]) for r in rows]),
            "totals": _stats([
                (r["matchday_date"], r["cal_over"] - 0.5, float(r["close_total_line"]) - float(r["total_line"]))
                for r in rows if r.get("cal_over") is not None and r.get("close_total_line") is not None
            ]),
        }
    return out


def summarize_holdout_partition(
    eval_rows: list[dict[str, Any]],
    bets: list[dict[str, Any]],
    *,
    development_seasons: tuple[str, ...],
    holdout_season: str,
    frozen_protocol_id: str,
    trials_evaluated_count: int,
    season_holdout_contaminated: bool = True,
    forward_holdout_start_utc: str | None = None,
) -> dict[str, Any]:
    """
    Partitions backtest performance into development, the season holdout and the forward holdout.

    The season holdout is only "untouched" if it was never looked at while choosing the policy; the
    flag `season_holdout_contaminated` records that it was. The forward holdout (games starting after
    the protocol freeze) is the only partition that is out-of-sample by construction.
    """
    dev_set = set(development_seasons)

    def _partition_summary(p_rows: list[dict[str, Any]], p_bets: list[dict[str, Any]]) -> dict[str, Any]:
        s = [b for b in p_bets if b.get("status") in ("WON", "LOST")]
        staked = sum(float(b.get("stake_pen") or 1.0) for b in s)
        prof = sum(float(b.get("net_profit_pen") or 0.0) for b in p_bets)
        clvs = [float(b["clv_ev_pct"]) for b in p_bets if b.get("clv_ev_pct") is not None]
        ml_brier = None
        if p_rows:
            ml_brier = score_probabilities([r["cal_home"] for r in p_rows], [r["home_won"] for r in p_rows])["brier"]
        return {
            "games": len(p_rows),
            "bets": len(p_bets),
            "settled": len(s),
            "won": sum(1 for b in s if b.get("status") == "WON"),
            "roi_flat_pct": round(100.0 * prof / staked, 2) if staked else None,
            "mean_clv_pct": round(float(np.mean(clvs)), 3) if clvs else None,
            "moneyline_brier": ml_brier,
            "multiple_testing": compute_multiple_testing_stats(p_bets, trials_evaluated_count),
        }

    dev_rows = [r for r in eval_rows if str(r.get("season")) != holdout_season and (not dev_set or str(r.get("season")) in dev_set)]
    dev_bets = [b for b in bets if str(b.get("season")) != holdout_season and (not dev_set or str(b.get("season")) in dev_set)]
    hold_rows = [r for r in eval_rows if str(r.get("season")) == holdout_season]
    hold_bets = [b for b in bets if str(b.get("season")) == holdout_season]

    forward: dict[str, Any] | None = None
    if forward_holdout_start_utc:
        start_by_game = {str(r.get("game_id")): str(r.get("game_start_time") or "") for r in eval_rows}
        fwd_rows = [r for r in eval_rows if str(r.get("game_start_time") or "") >= forward_holdout_start_utc]
        fwd_bets = [b for b in bets if start_by_game.get(str(b.get("game_id")), "") >= forward_holdout_start_utc]
        forward = {"start_utc": forward_holdout_start_utc, **_partition_summary(fwd_rows, fwd_bets)}

    return {
        "frozen_protocol_id": frozen_protocol_id,
        "development_seasons": list(development_seasons),
        "holdout_season": holdout_season,
        "season_holdout_contaminated": bool(season_holdout_contaminated),
        "development": _partition_summary(dev_rows, dev_bets),
        "untouched_holdout": _partition_summary(hold_rows, hold_bets),
        "forward_holdout": forward,
    }


def summarize_backtest_results(
    eval_rows: list[dict[str, Any]],
    bets: list[dict[str, Any]],
    initial_bankroll: float,
    kelly_bankroll: float,
    config: dict[str, Any],
    data_attribution: str,
    *,
    uncapped_shadow_bets: list[dict[str, Any]] | None = None,
    totals_clv_bets: list[dict[str, Any]] | None = None,
    totals_estimator_meta: dict[str, Any] | None = None,
    development_seasons: tuple[str, ...] = ("2024-25", "2025-26"),
    holdout_season: str = "2026-27",
    trials_evaluated_count: int = 3,
    frozen_protocol_id: str = "V8_FROZEN_2026_11_15",
    season_holdout_contaminated: bool = True,
    forward_holdout_start_utc: str | None = None,
) -> dict[str, Any]:
    """Builds complete backtest result dict preserving `betting`, `bets_sample`, and new evaluation sections."""
    out: dict[str, Any] = {
        "config": config,
        "data_attribution": data_attribution,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if eval_rows:
        y = [r["home_won"] for r in eval_rows]
        out["moneyline_quality"] = {
            k: score_probabilities([r[f] for r in eval_rows], y)
            for k, f in (
                ("model_raw", "raw_home"),
                ("model_calibrated", "cal_home"),
                ("model_anchored_production", "anchored_home"),
                ("market_open", "open_home"),
                ("market_close", "close_home"),
            )
        }
        tot = [r for r in eval_rows if r.get("total_result") in ("over", "under") and r.get("close_over_at_open_line") is not None]
        if tot:
            yt = [1 if r["total_result"] == "over" else 0 for r in tot]
            out["totals_quality_at_open_line"] = {
                "model_raw": score_probabilities([r["raw_over"] for r in tot], yt),
                "model_calibrated": score_probabilities([r["cal_over"] for r in tot], yt),
                "model_anchored_production": score_probabilities([r["anchored_over"] for r in tot], yt),
                "market_open_assumed_0.5": score_probabilities([0.5] * len(tot), yt),
                "market_close_normal_approx": score_probabilities([r["close_over_at_open_line"] for r in tot], yt),
            }

    line_sig = compute_line_movement_signal(eval_rows)
    out["line_movement_signal"] = line_sig
    out["full_slate_evaluation"] = {
        "games_count": len(eval_rows),
        "moneyline_quality": out.get("moneyline_quality"),
        "totals_quality_at_open_line": out.get("totals_quality_at_open_line"),
        "line_movement_signal": line_sig,
    }

    settled = [b for b in bets if b["status"] in ("WON", "LOST")]
    staked = sum(b["stake_pen"] for b in settled)
    profit = sum(b["net_profit_pen"] for b in bets)
    k_staked = sum(b["kelly_stake_pen"] for b in settled)
    clvs = [b["clv_ev_pct"] for b in bets]
    clv_blocks = (
        compute_block_bootstrap_roi_ci(
            [{"matchday_date": b["matchday_date"], "net_profit_pen": b["clv_ev_pct"] / 100.0, "stake_pen": 1.0} for b in bets]
        )
        if bets
        else {}
    )

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

    mult_test = compute_multiple_testing_stats(bets, trials_evaluated_count)
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
                "lower": clv_blocks.get("roi_ci_lower_95_pct"),
                "upper": clv_blocks.get("roi_ci_upper_95_pct"),
            }
            if clv_blocks
            else {},
        },
        "multiple_testing": mult_test,
        "by_market": _group("market"),
        "by_season": _group("season"),
    }
    out["holdout_partition"] = summarize_holdout_partition(
        eval_rows,
        bets,
        development_seasons=development_seasons,
        holdout_season=holdout_season,
        frozen_protocol_id=frozen_protocol_id,
        trials_evaluated_count=trials_evaluated_count,
        season_holdout_contaminated=season_holdout_contaminated,
        forward_holdout_start_utc=forward_holdout_start_utc,
    )
    out["uncapped_shadow"] = summarize_unit_track(uncapped_shadow_bets or [], trials_evaluated_count)
    totals_track = summarize_unit_track(totals_clv_bets or [], trials_evaluated_count)
    totals_track["estimator"] = totals_estimator_meta or {"holdout_excluded_from_fit": True}
    out["totals_clv_targeted"] = totals_track
    out["bets_sample"] = bets[:20]
    out["bets"] = bets
    return out


_ANCHOR_MARKET_LABELS: tuple[tuple[str, str], ...] = (
    ("moneyline", "moneyline"),
    ("total_points", "totales"),
    ("spread", "spread"),
)


def _fmt_weight(value: Any) -> str:
    return f"{float(value):.2f}" if value is not None else "base"


def _fmt_weight_range(values: list[float]) -> str:
    lo, hi = min(values), max(values)
    return _fmt_weight(lo) if abs(hi - lo) < 1e-12 else f"{_fmt_weight(lo)}–{_fmt_weight(hi)}"


def render_market_anchor(cfg: dict[str, Any]) -> tuple[str, str | None]:
    """
    Configuration-line text with the effective model weights and the anchor schedule the decisions used, and
    the assumption bullet that documents them. Results without a `market_anchor` block predate the schedule.
    """
    anchor = cfg.get("market_anchor")
    if not anchor:
        return f"peso fijo del modelo `{cfg.get('model_weight')}`", None
    eff = anchor.get("effective_model_weights") or {}
    sched = anchor.get("schedule") or {}
    hours = anchor.get("decision_hours_to_tipoff")
    hours_txt = f"`{float(hours):.1f} h` antes del inicio" if hours is not None else "horas hasta el inicio n/d"
    eff_txt = ", ".join(
        f"{label} `{_fmt_weight_range([float(w) for w in eff[mkt]])}`" for mkt, label in _ANCHOR_MARKET_LABELS if eff.get(mkt)
    )
    if sched.get("enabled"):
        bounds = ", ".join(
            f"{label} `{_fmt_weight(sched[mkt].get('open_weight'))}→{_fmt_weight(sched[mkt].get('close_weight'))}`"
            for mkt, label in _ANCHOR_MARKET_LABELS
            if isinstance(sched.get(mkt), dict)
        )
        sched_txt = (
            f"calendario `market_anchor_schedule` (`horizon_hours={float(sched.get('horizon_hours', 0.0)):g}`, "
            f"`decay_power={float(sched.get('decay_power', 0.0)):g}`; peso apertura→cierre: {bounds})"
        )
        timing = (
            "La fuente no publica la hora de la línea de apertura: se asume publicada al menos "
            f"{hours_txt} (≥ `horizon_hours`), así que el calendario da sus pesos de apertura."
        )
    else:
        sched_txt = f"calendario `market_anchor_schedule` desactivado (peso base `{anchor.get('fallback_model_weight')}`)"
        timing = "El calendario está desactivado: los pesos no dependen de la hora."
    decision_fn = str(anchor.get("decision_function") or "evaluate_scheduled_market_opportunity").rsplit(".", 1)[-1]
    segment = f"pesos efectivos del modelo a la apertura ({hours_txt}): {eff_txt or 'n/d'} | {sched_txt}"
    assumption = (
        f"- Anclaje modelo/mercado con la función de decisión de producción (`{decision_fn}`): mismo calendario, "
        "mismo manejo de steam y mismas guardas previas a la apuesta de `config.execution` (EV plausible máximo, "
        f"cuotas largas, ancho conformal). {timing} Steam = 0: al decidir solo se conoce la línea de apertura "
        "(usar el cierre sería información futura)."
    )
    return segment, assumption


def render_markdown(result: dict[str, Any], sensitivity: dict[str, Any] | None = None) -> str:
    """Renders Spanish audit-ready Markdown summary for real consensus odds backtest."""
    cfg = result["config"]
    ml_cap_txt = (
        f" | tope cuota Moneyline `{cfg['moneyline_max_odds']}`"
        if cfg.get("moneyline_max_odds") is not None
        else ""
    )
    anchor_txt, anchor_assumption = render_market_anchor(cfg)
    lines = [
        "# Backtest con cuotas reales (consenso de apertura/cierre, sin margen)",
        "",
        f"- Generado: `{result['generated_at_utc']}`",
        f"- {result['data_attribution']}",
        f"- Periodo de prueba desde `{cfg['start_date']}` | partidos con mercado emparejado: `{cfg['test_games']}`",
        f"- Reentrenamiento cada `{cfg['retrain_every_days']}` días | margen supuesto `{cfg['vig_assumption'] * 100:.1f}%` | "
        f"{anchor_txt} | EV mínimo `{cfg['min_ev'] * 100:.0f}%`{ml_cap_txt}",
    ]
    unpriceable = int(cfg.get("unpriceable_sides_skipped") or 0)
    if unpriceable:
        lines.append(
            f"- Lados sin precio apostable (cuota justa / (1 + margen) ≤ 1.00): `{unpriceable}`, sin apuesta, "
            "candidato ni shadow; sus partidos siguen en la sección 1"
        )
    lines += [
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
        f"- **Stake Kelly {cfg['kelly']['fraction'] * 100:.0f}%** (S/{cfg['kelly']['min_stake']:.2f}–S/{cfg['kelly']['max_stake']:.2f}): banca final "
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
        lines += [
            "",
            "## 3. Sensibilidad al margen supuesto",
            "",
            "| Margen | Mercado | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |",
            "| ---: | :--- | ---: | ---: | ---: | ---: |",
        ]
        for vig_label, res in sensitivity.items():
            for mk, v in res["betting"]["by_market"].items():
                lines.append(
                    f"| {vig_label} | `{mk}` | {v['bets']} | {v['won']} | {v['roi_flat_pct']}% {_ci(v.get('roi_ci95'))} | "
                    f"{v['mean_clv_pct']}% {_ci(v.get('clv_ci95'))} |"
                )
        skipped_by_vig = {
            vig_label: int((res.get("config") or {}).get("unpriceable_sides_skipped") or 0)
            for vig_label, res in sensitivity.items()
        }
        if any(skipped_by_vig.values()):
            lines += [
                "",
                "- Lados sin precio apostable omitidos: "
                + " | ".join(f"margen {k}: `{n}`" for k, n in skipped_by_vig.items() if n),
            ]
    sig = result.get("line_movement_signal") or {}
    if sig:
        lines += [
            "",
            "## 4. ¿El modelo anticipa el movimiento de línea? (todos los partidos, sin reglas de apuesta)",
            "",
            "Correlación entre la discrepancia del modelo con la apertura y el movimiento apertura→cierre.",
            "",
            "| Temporada | Mercado | N | Correlación [IC95] | Acierto de dirección |",
            "| :--- | :--- | ---: | ---: | ---: |",
        ]
        for season, mk in sig.items():
            for market_name, st in mk.items():
                if "correlation" in st:
                    lines.append(
                        f"| {season} | {market_name} | {st['n']} | {st['correlation']:+.3f} "
                        f"[{st['correlation_ci95'][0]:+.3f}, {st['correlation_ci95'][1]:+.3f}] | {st['directional_hit_rate']:.1%} |"
                    )

    hp = result.get("holdout_partition") or {}
    mt = b.get("multiple_testing") or {}
    us = result.get("uncapped_shadow") or {}
    tc = result.get("totals_clv_targeted") or {}
    if hp or mt or us or tc:
        lines += [
            "",
            "## 5. Holdout Congelado, Corrección Múltiple y Pistas Shadow",
            "",
        ]
        if hp:
            dev = hp.get("development") or {}
            hld = hp.get("untouched_holdout") or {}
            hold_label = (
                "Holdout de temporada CONTAMINADO (visto en reportes previos al freeze)"
                if hp.get("season_holdout_contaminated", True)
                else "Holdout intacto"
            )
            lines.append(
                f"- Protocolo congelado: `{hp.get('frozen_protocol_id')}` | "
                f"Desarrollo (`{','.join(hp.get('development_seasons') or [])}`): `{dev.get('games')}` juegos, `{dev.get('bets')}` bets, ROI `{dev.get('roi_flat_pct')}%`, CLV `{dev.get('mean_clv_pct')}%` | "
                f"{hold_label} (`{hp.get('holdout_season')}`): `{hld.get('games')}` juegos, `{hld.get('bets')}` bets, ROI `{hld.get('roi_flat_pct')}%`"
            )
            fwd = hp.get("forward_holdout") or {}
            if fwd:
                lines.append(
                    f"- **Holdout hacia adelante** (partidos desde `{fwd.get('start_utc')}`, único fuera de muestra real): "
                    f"`{fwd.get('games')}` juegos, `{fwd.get('bets')}` bets, ROI `{fwd.get('roi_flat_pct')}%`, CLV `{fwd.get('mean_clv_pct')}%`"
                )
        if mt:
            roi_mt = mt.get("roi") or {}
            clv_mt = mt.get("clv") or {}
            lines.append(
                f"- Pruebas múltiples (`trials={mt.get('trials_evaluated_count')}`, Bonferroni): "
                f"ROI p-raw=`{roi_mt.get('raw_p_value')}`, p-bonf=`{roi_mt.get('bonferroni_p_value')}` | "
                f"CLV p-raw=`{clv_mt.get('raw_p_value')}`, p-bonf=`{clv_mt.get('bonferroni_p_value')}`"
            )
        if us:
            lines.append(
                f"- **Uncapped Shadow (1u sin mínimos ni tope diario)**: `{us.get('bets')}` señales, "
                f"ROI 1u `{us.get('roi_1u_pct')}%`, CLV medio `{us.get('mean_clv_pct')}%`"
            )
        if tc:
            est = tc.get("estimator") or {}
            lines.append(
                f"- **Totals CLV-Targeted (1u anticipación cierre, sin holdout en fit)**: `{tc.get('bets')}` bets, "
                f"ROI 1u `{tc.get('roi_1u_pct')}%`, CLV `{tc.get('mean_clv_pct')}%`, pendiente final `{est.get('slope')}` (`n={est.get('sample_size')}`)"
            )

    lines += [
        "",
        "## Supuestos",
        "- Precio apostable = cuota justa de apertura / (1 + margen). La fuente publica probabilidades sin margen, no precios de casas.",
        "- Totales: la línea principal de apertura es la más cercana a 50/50 (p=0.50); el cierre a esa línea se aproxima con un modelo normal (σ=18).",
        "- Las features usan solo partidos que empezaron antes del primer partido de la jornada; los calibradores y el estimador de cierre solo observaciones previas en desarrollo.",
    ]
    if anchor_assumption:
        lines.append(anchor_assumption)
    return "\n".join(lines) + "\n"
