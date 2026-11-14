"""
Generates the weekly quantitative performance, validation, and promotion report.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.reporting.slate_intelligence import _fmt


def generate_weekly_report(
    metrics: dict[str, Any],
    promotion_eval: dict[str, Any],
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    boot = metrics.get("bootstrap_uncertainty", {})
    by_mkt = metrics.get("performance_by_market", {})
    model_comp = metrics.get("model_comparison", {})

    initial_bankroll = float(metrics.get("initial_bankroll_pen", 100.0))
    settled_bankroll = float(metrics.get("current_settled_bankroll_pen", initial_bankroll))
    net_profit = float(metrics.get("net_profit_pen", round(settled_bankroll - initial_bankroll, 2)))
    settled_count = int(metrics.get("settled_bets_count", 0))
    won_count = int(metrics.get("won_count", 0))
    lost_count = int(metrics.get("lost_count", 0))
    wl_total = won_count + lost_count
    win_rate_pct = (
        float(metrics["win_rate_pct"])
        if metrics.get("win_rate_pct") is not None
        else ((won_count / wl_total * 100.0) if wl_total > 0 else 0.0)
    )

    beat_close_raw = metrics.get("beat_closing_rate_pct")
    if beat_close_raw is None and metrics.get("clv_beat_close_rate") is not None:
        beat_close_raw = float(metrics["clv_beat_close_rate"]) * 100.0

    roi_ci_low = boot.get("roi_ci_lower_pct") if boot.get("roi_ci_lower_pct") is not None else boot.get("roi_ci_lower_95_pct")
    roi_ci_high = boot.get("roi_ci_upper_pct") if boot.get("roi_ci_upper_pct") is not None else boot.get("roi_ci_upper_95_pct")

    lines = [
        "---",
        f"date_generated: {now_str}",
        "report_type: weekly_report",
        "model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]",
        f"settled_predictions: {settled_count}",
        f"observed_bankroll_pen: {settled_bankroll:.2f}",
        "simulation_only: true",
        "---",
        "# Informe Semanal de Rendimiento y Validación Fuera de Muestra",
        "",
        "## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)",
        f"- **Fecha generada (UTC)**: `{now_str}`",
        f"- **Bankroll virtual inicial**: `S/{initial_bankroll:.2f} PEN`",
        f"- **Bankroll virtual actual liquidado**: `S/{settled_bankroll:.2f} PEN` (`{settled_count}` apuestas observadas liquidadas)",
        f"- **Beneficio neto acumulado**: `S/{net_profit:+.2f} PEN`",
        f"- **ROI acumulado**: `{metrics.get('roi_pct', 0.0):+.2f}%`",
        f"- **Win Rate**: `{win_rate_pct:.2f}%` (`{won_count}G - {lost_count}P`)",
        f"- **Apuestas liquidadas**: `{settled_count}`",
        f"- **CLV medio**: `{_fmt(metrics.get('mean_clv_pct'), '.2f', 'n/d')}%`",
        f"- **Tasa de batir la línea de cierre (Beat CLV %)**: `{_fmt(beat_close_raw, '.1f', 'n/d')}%`",
        f"- **Ratio de Sharpe simulado (anualizado)**: `{_fmt(metrics.get('simulated_sharpe_ratio'), '.3f', 'n/d')}`",
        f"- **Máximo Drawdown**: `{metrics.get('max_drawdown_pct', 0.0):.2f}%` (Límite de alerta: `15.00%`)",
        "",
        "## 2. Incertidumbre Estadística (Block Bootstrap 95% CI)",
        f"- **ROI 95% CI**: `[{_fmt(roi_ci_low, '.2f', 'n/d')}%, {_fmt(roi_ci_high, '.2f', 'n/d')}%]`",
        f"- **Win Rate 95% CI**: `[{_fmt(boot.get('win_rate_ci_lower_pct'), '.2f', 'n/d')}%, {_fmt(boot.get('win_rate_ci_upper_pct'), '.2f', 'n/d')}%]`",
        f"- **CLV 95% CI**: `[{_fmt(boot.get('clv_ci_lower_pct'), '.2f', 'n/d')}%, {_fmt(boot.get('clv_ci_upper_pct'), '.2f', 'n/d')}%]`",
        f"- **Brier Score 95% CI**: `[{_fmt(boot.get('brier_ci_lower'), '.5f', 'n/d')}, {_fmt(boot.get('brier_ci_upper'), '.5f', 'n/d')}]`",
        f"- **Interpretación**: `{boot.get('interpretation', 'Muestra insuficiente para inferencia bootstrap concluyente.')}`",
        "",
        "## 3. Calibración y Comparación de Modelos (Fuera de Muestra)",
        "| Modelo / Fuente | Brier Score | Log Loss |",
        "|---|---|---|",
        f"| **Ensemble Ponderado (Modelos B+C+D+E)** | `{_fmt(metrics.get('overall_brier_score'), '.5f', 'n/d')}` | `{_fmt(metrics.get('overall_log_loss'), '.5f', 'n/d')}` |",
        f"| Modelo A (Baseline Histórico) | `{_fmt(metrics.get('baseline_brier_score'), '.5f', 'n/d')}` | `{_fmt(metrics.get('baseline_log_loss'), '.5f', 'n/d')}` |",
        f"| Mercado Sin Margen (Muestra común) | `{_fmt(metrics.get('market_brier_score'), '.5f', 'n/d')}` | `{_fmt(metrics.get('market_log_loss'), '.5f', 'n/d')}` |",
        f"| Modelo sobre Muestra Común | `{_fmt(metrics.get('model_brier_on_market_subset'), '.5f', 'n/d')}` | `{_fmt(metrics.get('model_log_loss_on_market_subset'), '.5f', 'n/d')}` |",
    ]

    for model_key, scores in model_comp.items():
        lines.append(f"| {model_key} | `{_fmt(scores.get('brier_score'), '.5f', 'n/d')}` | `{_fmt(scores.get('log_loss'), '.5f', 'n/d')}` |")

    lines.extend([
        "",
        f"## 4. Desempeño por Mercado (Total: {settled_count} Apuestas Observadas | Banca: S/{settled_bankroll:.2f} PEN)",
        "| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |",
        "|---|---|---|---|---|---|---|",
    ])
    for mkt, data in by_mkt.items():
        m_settled = int(data.get("settled_bets") if data.get("settled_bets") is not None else data.get("settled_count", 0))
        m_won = int(data.get("won", 0))
        m_lost = int(data.get("lost", 0))
        m_wl = m_won + m_lost
        m_wr = (
            float(data["win_rate_pct"])
            if data.get("win_rate_pct") is not None
            else ((m_won / m_wl * 100.0) if m_wl > 0 else 0.0)
        )
        lines.append(
            f"| `{mkt}` | `{m_settled}` | `{m_wr:.1f}%` | "
            f"`S/{data.get('net_profit_pen', 0.0):+.2f}` | `{data.get('roi_pct', 0.0):+.2f}%` | "
            f"`{_fmt(data.get('mean_clv_pct'), '.2f', 'n/d')}%` | `{_fmt(data.get('brier_score'), '.5f', 'n/d')}` |"
        )

    lines.extend([
        "",
        "## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)",
        f"- **Muestra OOS evaluada**: `{promotion_eval.get('oos_sample_size', 0)}` partidos",
        f"- **Criterio de selección**: `{promotion_eval.get('selection_basis')}`",
        f"- **¿Supera al modelo vigente en Brier y Log Loss?**: `{promotion_eval.get('beats_incumbent')}`",
        f"- **¿Supera al Baseline en Brier y Log Loss?**: `{promotion_eval.get('beats_baseline')}`",
        f"- **Recomendación de promoción**: `{'APROBAR PROMOCIÓN CONTROLADA' if promotion_eval.get('recommend_promotion') else 'MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)'}`",
    ])

    return "\n".join(lines) + "\n"
