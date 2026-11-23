"""
Exports Excel/Sheets CSV and markdown dashboards for tracking bets and model readiness.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import tempfile
from typing import Any

from src.config import load_config
from src.evaluation.clv import compute_bet_clv, index_closing_rows
from src.paper_trading.engine import compute_props_calibration_summary
from src.reporting.dashboard_generator import generate_interactive_html_dashboard
from src.reporting.notifier import evaluate_and_notify_readiness, select_and_dispatch_daily_top_pick
from src.reporting.slate_intelligence import compute_upcoming_slate_intelligence
from src.storage.db import DatabaseManager
from src.utils.team_dictionary import format_matchup, get_team_full_name
from src.validation.validator import parse_iso_utc

logger = logging.getLogger(__name__)


def _compute_clean_props_metrics(
    db: DatabaseManager,
    initial_bankroll_pen: float = 100.0,
) -> dict[str, Any]:
    """
    Computes truthful Player Props & SGP paper trading metrics strictly separating
    genuinely resolved picks (WON, LOST, PUSH) from voided legacy picks (VOID).
    Joins with `games` to verify team/matchup integrity and computes chronological
    running bankroll across resolved picks.
    """
    try:
        all_props = db.fetch_all(
            """
            SELECT p.*, g.home_team, g.away_team, g.game_start_time
            FROM player_prop_picks p
            LEFT JOIN games g ON p.game_id = g.game_id
            ORDER BY COALESCE(g.game_start_time, p.emitted_at) ASC, p.emitted_at ASC, p.prop_id ASC
            """
        )
    except Exception:
        return {}

    if not all_props:
        return {}

    settled_real = db.fetch_all(
        """
        SELECT p.*, g.home_team, g.away_team, g.game_start_time
        FROM player_prop_picks p
        LEFT JOIN games g ON p.game_id = g.game_id
        WHERE p.status IN ('WON', 'LOST', 'PUSH')
          AND (
              g.home_team IS NULL
              OR p.team IN (g.home_team, g.away_team)
              OR p.team LIKE '%/%'
          )
        ORDER BY p.emitted_at ASC, p.prop_id ASC
        """
    )

    pending_rows = [p for p in all_props if p["status"] == "PENDING"]
    void_rows = [p for p in all_props if p["status"] == "VOID"]
    won = [p for p in settled_real if p["status"] == "WON"]
    lost = [p for p in settled_real if p["status"] == "LOST"]
    push = [p for p in settled_real if p["status"] == "PUSH"]

    total_staked = sum(
        float(p.get("stake_pen") or p.get("kelly_stake_pen") or 1.0)
        for p in settled_real
        if p["status"] in ("WON", "LOST")
    )
    net_profit = sum(float(p.get("net_profit_pen") or 0.0) for p in settled_real)
    current_bankroll = round(initial_bankroll_pen + net_profit, 2)

    wl_count = len(won) + len(lost)
    win_rate = (len(won) / wl_count * 100.0) if wl_count > 0 else 0.0
    roi_pct = (net_profit / total_staked * 100.0) if total_staked > 0 else 0.0
    cal_summary = compute_props_calibration_summary(settled_real)

    running_props_bankroll = initial_bankroll_pen
    chronological_settled: list[dict[str, Any]] = []
    for p in settled_real:
        item = dict(p)
        pnl = float(item.get("net_profit_pen") or 0.0)
        running_props_bankroll = round(running_props_bankroll + pnl, 2)
        item["bankroll_after_pen"] = running_props_bankroll
        if item.get("away_team") and item.get("home_team"):
            item["matchup_display"] = format_matchup(str(item["away_team"]), str(item["home_team"]))
        else:
            item["matchup_display"] = str(item.get("game_id") or "")
        chronological_settled.append(item)

    recent_settled = list(reversed(chronological_settled))

    base_categories = ["PTS", "REB", "AST", "PRA", "3PM", "STL_BLK", "PR", "PA", "RA", "SGP", "SGP_2LEG"]
    seen_cats = [str(p.get("prop_category") or "") for p in all_props if p.get("prop_category")]
    categories = list(dict.fromkeys(base_categories + seen_cats))

    breakdown: dict[str, dict[str, Any]] = {}
    for cat in categories:
        cat_resolved = [p for p in settled_real if p.get("prop_category") == cat]
        cat_void = [p for p in void_rows if p.get("prop_category") == cat]
        c_won = [p for p in cat_resolved if p["status"] == "WON"]
        c_lost = [p for p in cat_resolved if p["status"] == "LOST"]
        c_push = [p for p in cat_resolved if p["status"] == "PUSH"]
        c_staked = sum(
            float(p.get("stake_pen") or p.get("kelly_stake_pen") or 1.0)
            for p in cat_resolved
            if p["status"] in ("WON", "LOST")
        )
        c_net = sum(float(p.get("net_profit_pen") or 0.0) for p in cat_resolved)
        c_wl = len(c_won) + len(c_lost)
        breakdown[cat] = {
            "resolved_count": len(cat_resolved),
            "total_settled": len(cat_resolved),
            "void_count": len(cat_void),
            "won": len(c_won),
            "lost": len(c_lost),
            "push": len(c_push),
            "win_rate_pct": round(len(c_won) / c_wl * 100.0, 1) if c_wl > 0 else 0.0,
            "total_staked_pen": round(c_staked, 2),
            "net_profit_pen": round(c_net, 2),
            "roi_pct": round(c_net / c_staked * 100.0, 2) if c_staked > 0 else 0.0,
        }

    return {
        "total_picks": len(all_props),
        "pending_picks": len(pending_rows),
        "settled_picks": len(settled_real),
        "resolved_picks": len(settled_real),
        "won_picks": len(won),
        "lost_picks": len(lost),
        "push_picks": len(push),
        "void_picks": len(void_rows),
        "win_rate_pct": round(win_rate, 2),
        "total_staked_pen": round(total_staked, 2),
        "total_net_profit_pen": round(net_profit, 2),
        "current_props_bankroll_pen": round(current_bankroll, 2),
        "roi_pct": round(roi_pct, 2),
        "brier_score": cal_summary["brier_score"],
        "log_loss": cal_summary["log_loss"],
        "ece": cal_summary["ece"],
        "accuracy_pct": cal_summary["accuracy_pct"],
        "venn_abers_interval_width_mean": cal_summary["venn_abers_interval_width_mean"],
        "venn_abers_calibrated_count": cal_summary["venn_abers_calibrated_count"],
        "venn_abers_empirical_coverage_valid": cal_summary["venn_abers_empirical_coverage_valid"],
        "conformal_coverage_pct": cal_summary["conformal_coverage_pct"],
        "category_breakdown": breakdown,
        "recent_settled": recent_settled[:20],
    }


def export_bets_and_tracking_dashboard(
    db: DatabaseManager,
    metrics: dict[str, Any],
    csv_output_path: str | Path,
    md_output_path: str | Path,
) -> dict[str, str]:
    """
    Generates:
    1) `data/apuestas_historial.csv`: Excel/Sheets-ready CSV of every simulated bet.
    2) `SEGUIMIENTO_APUESTAS.md`: Personalized bet tracker (real ESPN bets + benchmark bets)
       and the visual Calibration & Real-Money Readiness Traffic Light.
    """
    now_utc = datetime.now(timezone.utc)
    now_peru = now_utc - timedelta(hours=5)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    peru_str = now_peru.strftime("%Y-%m-%d %H:%M (Hora Perú UTC-5)")

    risk_cfg = load_config().risk
    initial_bankroll_pen = float(risk_cfg.virtual_bankroll_initial_pen)
    min_ev_pct = float(risk_cfg.min_ev_threshold) * 100.0
    max_sel = int(risk_cfg.max_selections_per_matchday)
    if str(risk_cfg.staking_mode).lower() == "fractional_kelly":
        kelly_pct = round(float(risk_cfg.kelly_fraction) * 100.0)
        staking_desc = f"Kelly Fraccional ({kelly_pct}%)"
    else:
        staking_desc = f"Stake fijo S/{float(risk_cfg.base_stake_pen):.2f} PEN"
    active_mode_str = f"{staking_desc} | Máx. {max_sel} selecciones/jornada | EV >= {min_ev_pct:.1f}%"

    chronological_rows = db.fetch_all(
        """
        SELECT b.*, g.home_team, g.away_team, g.game_start_time, g.status AS game_status,
               g.home_score, g.away_score, g.source_provider, p.odds_provider
        FROM v_observed_simulated_bets b
        JOIN games g ON b.game_id = g.game_id
        LEFT JOIN predictions p ON b.prediction_id = p.prediction_id
        ORDER BY g.game_start_time ASC, b.emitted_at ASC, b.bet_id ASC
        """
    )

    running_bankroll = initial_bankroll_pen
    observed_running_bankroll: dict[str, float | None] = {}
    for r in chronological_rows:
        if r["status"] != "PENDING" and r["net_profit_pen"] is not None:
            running_bankroll = round(running_bankroll + float(r["net_profit_pen"]), 4)
            observed_running_bankroll[str(r["bet_id"])] = round(running_bankroll, 2)
        else:
            observed_running_bankroll[str(r["bet_id"])] = None

    rows = list(reversed(chronological_rows))

    closing_index = index_closing_rows(
        db.fetch_all(
            """
            SELECT game_id, market, selection, line_value, decimal_odds, counterpart_decimal_odds, provider, captured_at
            FROM v_observed_odds_snapshots WHERE is_closing_line = 1
            """
        )
    )

    csv_path = Path(csv_output_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "bet_id",
        "tipo_fuente",
        "fecha_jornada",
        "hora_partido_peru",
        "partido",
        "mercado",
        "seleccion",
        "linea",
        "cuota_decimal",
        "casa_apuestas",
        "clv_porcentaje",
        "prob_estimada",
        "ev_porcentaje",
        "stake_pen",
        "estado",
        "marcador_final",
        "beneficio_neto_pen",
        "bankroll_posterior_pen",
        "modelo",
    ]

    espn_real_bets: list[dict[str, Any]] = []
    all_formatted: list[dict[str, Any]] = []

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            is_real = str(r["game_id"]).startswith("ESPN_")
            try:
                start_peru = (parse_iso_utc(r["game_start_time"]) - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                start_peru = r["game_start_time"]

            home_full = get_team_full_name(r["home_team"])
            away_full = get_team_full_name(r["away_team"])
            match_label = format_matchup(r["away_team"], r["home_team"])
            if r["market"] == "moneyline":
                team_picked_name = home_full if r["selection"] == "HOME" else away_full
                team_picked_code = r["home_team"] if r["selection"] == "HOME" else r["away_team"]
                sel_display = f"Gana {team_picked_name} ({team_picked_code})"
            else:
                sel_display = f"{r['selection']} {r['line_value']} ({away_full} @ {home_full})"

            raw_prov = str(r["odds_provider"] or "DraftKings")
            book_clean = (
                raw_prov.split(" (Best of")[0]
                .replace(" (LineShop)", "")
                .replace("espn_draftkings_pregame", "DraftKings")
                .replace("synthetic_sharp_book", "Benchmark")
                .strip()
            )

            clv_rec = compute_bet_clv(dict(r), closing_index, r.get("odds_provider"))
            indiv_clv: float | None = (
                round(float(clv_rec["clv_ev_pct"]), 2) if clv_rec is not None and not clv_rec["is_outlier"] else None
            )

            item = {
                "bet_id": r["bet_id"],
                "tipo_fuente": "NBA_REAL_ESPN" if is_real else "SIMULACION_WALKFORWARD",
                "fecha_jornada": r["matchday_date"],
                "hora_partido_peru": start_peru,
                "partido": match_label,
                "mercado": "Ganador (Moneyline)" if r["market"] == "moneyline" else "Total Puntos (Over/Under)",
                "seleccion": sel_display,
                "linea": r["line_value"] if r["line_value"] is not None else "",
                "cuota_decimal": round(float(r["decimal_odds"]), 3),
                "casa_apuestas": book_clean,
                "clv_porcentaje": indiv_clv if indiv_clv is not None else "",
                "prob_estimada": round(float(r["estimated_prob"]) * 100.0, 2),
                "ev_porcentaje": round(float(r["estimated_ev"]) * 100.0, 2),
                "stake_pen": round(float(r["stake_pen"]), 2),
                "estado": r["status"],
                "marcador_final": r["actual_result_summary"] or "En espera",
                "beneficio_neto_pen": round(float(r["net_profit_pen"]), 2) if r["net_profit_pen"] is not None else "",
                "bankroll_posterior_pen": (
                    observed_running_bankroll[str(r["bet_id"])]
                    if observed_running_bankroll.get(str(r["bet_id"])) is not None
                    else ""
                ),
                "modelo": r["model_version_id"],
            }
            writer.writerow(item)
            all_formatted.append(item)
            if is_real:
                espn_real_bets.append(item)

    settled_count = int(metrics.get("settled_bets_count", 0))
    pending_count = int(metrics.get("pending_bets_count", 0))
    progress_pct = min(100.0, round((settled_count / 500.0) * 100.0, 1))
    filled_bars = int(round(progress_pct / 5.0))
    progress_bar = "█" * filled_bars + "░" * (20 - filled_bars)

    boot = metrics.get("bootstrap_uncertainty", {})
    ci_low = float(boot.get("roi_ci_lower_95_pct", -99.0))
    ci_high = float(boot.get("roi_ci_upper_95_pct", 99.0))

    readiness_file = csv_path.parent / "readiness_status.json"
    readiness = evaluate_and_notify_readiness(metrics, readiness_file)
    daily_top_info = select_and_dispatch_daily_top_pick(espn_real_bets, readiness_file)
    is_t1_ready = bool(readiness["is_tier1_micro_bankroll_ready"])
    is_t2_ready = bool(readiness["is_tier2_full_bankroll_ready"])
    passed_gates = int(readiness["passed_gates_count"])
    total_gates = int(readiness["total_gates_count"])
    live_settled = int(readiness["live_espn_settled_bets_count"])
    live_prog_pct = float(readiness["progress_live_pct"])
    live_bars = int(round(live_prog_pct / 5.0))
    live_progress_bar = "█" * live_bars + "░" * (20 - live_bars)
    ece_raw = readiness.get("ece_score")
    max_dd_raw = readiness.get("max_drawdown_pct")
    ece_txt = "n/d" if ece_raw is None else f"{float(ece_raw):.4f} ({float(ece_raw) * 100:.2f}%)"
    max_dd_txt = "n/d" if max_dd_raw is None else f"{float(max_dd_raw):.2f}%"
    model_b = metrics.get("model_brier_on_market_subset")
    market_b = metrics.get("market_brier_score")
    base_b = metrics.get("baseline_brier_score")
    calib_txt = (
        f"Modelo {model_b:.4f} vs Mercado {market_b:.4f} (N={metrics.get('market_comparison_sample_size', 0)})"
        if model_b is not None and market_b is not None
        else "Sin comparación con mercado (faltan cuotas observadas)"
    ) + (f" | Baseline {base_b:.4f}" if base_b is not None else "")
    live_dd_val = float(metrics.get("live_max_drawdown_pct") or 0.0)
    ci90_low = float(readiness["roi_ci_90_lower_pct"])
    ci90_high = float(readiness["roi_ci_90_upper_pct"])
    flags = readiness["criteria_flags_tier1"]

    if is_t2_ready:
        global_banner = "🟢 NIVEL 2 DESBLOQUEADO: ¡CERTIFICADO PARA ENTORNO REAL COMPLETO! (8/8 CRITERIOS NIVEL 2 EN VERDE)"
    elif is_t1_ready:
        global_banner = "🟡 NIVEL 1 DESBLOQUEADO: ¡LISTO PARA PILOTO CON MICRO-BANCA (25% STAKE)! (8/8 CRITERIOS NIVEL 1 EN VERDE)"
    else:
        global_banner = f"🔴 EN FASE DE CALIBRACIÓN Y PAPER TRADING ({passed_gates}/{total_gates} CRITERIOS EN VERDE — NO USAR DINERO REAL AÚN)"

    clv_val = metrics.get("mean_clv_pct")
    clv_str = f"`{clv_val:+.2f}%` (N={metrics.get('clv_sample_size', 0)})" if clv_val is not None else "`Sin cierres observados suficientes`"
    pending_stake_sum = sum(float(x["stake_pen"]) for x in all_formatted if x["estado"] == "PENDING")
    raw_settled_bank = metrics.get("current_settled_bankroll_pen")
    header_settled_bankroll = (
        float(raw_settled_bank)
        if raw_settled_bank is not None
        else round(running_bankroll, 2)
    )
    raw_net_profit = metrics.get("net_profit_pen")
    header_net_profit = (
        float(raw_net_profit)
        if raw_net_profit is not None
        else round(running_bankroll - initial_bankroll_pen, 2)
    )

    lines = [
        "# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)",
        "",
        f"- **Última actualización**: `{peru_str}` (`{now_str}`)",
        f"- **Bankroll Virtual Inicial**: `S/{initial_bankroll_pen:.2f} PEN` | **Bankroll Liquidado Actual**: **`S/{header_settled_bankroll:.2f} PEN`** (`{header_net_profit:+.2f} PEN`)",
        f"- **ROI Actual**: `{float(metrics.get('roi_pct', 0.0)):+.2f}%` | **Yield Actual**: `{float(metrics.get('yield_pct', 0.0)):+.2f}%` | **CLV (vs cierre sin margen)**: {clv_str} | **Max Drawdown**: `{max_dd_txt}` | **Apuestas en espera**: `{pending_count}` (`S/{pending_stake_sum:.2f} PEN` reservados)",
        "- **Motor Predictivo Activo**: `Ensemble (Elo + Ridge + LightGBM + Monte Carlo) anclado 70% al mercado sin margen`. Sin ventaja demostrada frente al mercado.",
        f"- **Modo de Apuesta Activo**: `{active_mode_str}` | Solo cuotas observadas (nunca estimadas).",
        "- **Alcance de métricas**: solo apuestas hechas con cuotas observadas en un mercado real (`v_observed_simulated_bets`).",
        "- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)",
        "- **Sistema de Aviso Automático**: `ACTIVO` *(aviso cuando se cumplan los criterios; cumplirlos solo habilita una revisión humana extendida, nunca dinero real automático)*.",
        "",
        "---",
        "",
        "## 🚦 1. Semáforo de Madurez de 8 Criterios y Graduación en 2 Niveles",
        "",
        f"### Estado Global: **{global_banner}**",
        f"- **Progreso Muestra Total (Nivel 1)**: `[{progress_bar}] {settled_count} / 500 apuestas ({progress_pct:.1f}%)` — *Faltan **{max(0, 500 - settled_count)}** apuestas.*",
        f"- **Progreso Muestra 100% En Vivo (ESPN/OddsAPI)**: `[{live_progress_bar}] {live_settled} / 200 en vivo ({live_prog_pct:.1f}%)` — *Tienes **{pending_count}** apuestas reales en espera hoy.*",
        "",
        "Para blindar tu capital contra rachas de suerte, el sistema evalúa **8 criterios cuantitativos estrictos** divididos en **2 niveles de graduación**:",
        "",
        "| # | Criterio Cuantitativo de Auditoría | Estado Hoy | Valor Actual | Meta Nivel 1 (Piloto Micro-Banca 25%) | Meta Nivel 2 (Banca Completa 100%) |",
        "| :-: | :--- | :---: | :--- | :--- | :--- |",
        f"| 1 | **Muestra total de apuestas liquidadas** | {'✅ VERDE' if flags['c1_total_sample_500'] else '🔴 PENDIENTE'} | `{settled_count} apuestas` | **>= 500 apuestas** | **>= 1,000 apuestas** |",
        f"| 2 | **Muestra 100% En Vivo (Pre-Partido Real)** | {'✅ VERDE' if flags['c2_live_sample_200'] else '🔴 PENDIENTE'} | `{live_settled} liquidadas ({pending_count} activas)` | **>= 200 en vivo** | **>= 500 en vivo** |",
        f"| 3 | **No peor que el Mercado sin margen ni que el Baseline (Brier & LogLoss)** | {'✅ VERDE' if flags.get('c3_brier_beats_baseline_and_market') else '🔴 PENDIENTE'} | `{calib_txt}` | **Modelo <= Mercado** | **Modelo <= Mercado** |",
        f"| 4 | **Error de Calibración por Tramos (ECE)** | {'✅ VERDE' if flags['c4_ece_under_5pct'] else '🟡 AJUSTANDO'} | `ECE {ece_txt}` | **ECE <= 5.0%** | **ECE <= 3.5%** |",
        f"| 5 | **Rentabilidad Neta Positiva (ROI y Yield)** | {'✅ VERDE' if flags['c5_positive_net_roi'] else '🔴 PENDIENTE'} | `ROI {metrics['roi_pct']:+.2f}% / Yield {metrics['yield_pct']:+.2f}%` | **ROI >= +2.0% / Yield >= +1.5%** | **ROI >= +3.5% (ambos mercados > 0%)** |",
        f"| 6 | **Control de Caída Máxima (Max Drawdown)** | {'✅ VERDE' if flags['c6_max_drawdown_under_15pct'] else '🔴 PENDIENTE'} | `Total {max_dd_txt} (En vivo: {live_dd_val:.2f}%)` | **MaxDD <= 15.0%** | **MaxDD <= 15.0%** |",
        f"| 7 | **Exclusión Estadística del Azar (Bootstrap CI)** | {'✅ VERDE' if flags['c7_bootstrap_ci_excludes_zero'] else '🔴 PENDIENTE'} | `IC90 [{ci90_low:+.1f}%, {ci90_high:+.1f}%] / IC95 [{ci_low:+.1f}%, {ci_high:+.1f}%]` | **IC 90% lím. inf. > 0%** | **IC 95% lím. inf. > 0%** |",
        f"| 8 | **Cero Fuga Temporal, historial íntegro y ledger reconciliado** | {'✅ VERDE' if flags['c8_zero_leakage_and_reconciled'] else '🔴 PENDIENTE'} | `{'Sin violaciones' if flags['c8_zero_leakage_and_reconciled'] else 'Violación detectada (ver audit_report)'}` | **0 violaciones** | **0 violaciones** |",
        "",
        "> **Nota**: cumplir los criterios NO autoriza dinero real. Según AGENTS.md, el sistema opera exclusivamente en paper trading; los niveles solo habilitan una revisión humana extendida.",
        "",
        "---",
        "",
        "## 🏀 2. Mis Apuestas NBA Reales (ESPN / TheOddsAPI Line Shopping)",
        "",
    ]

    if daily_top_info and daily_top_info.get("top_pick"):
        tp = daily_top_info["top_pick"]
        try:
            gh_issues_on = bool(load_config().sources.github_issue_notifications_enabled)
        except Exception:
            gh_issues_on = False
        channel_desc = (
            "`ACTIVO` *(1 solo correo diario vía GitHub Notification `@Drewks` con la selección de mayor EV entre las apuestas pendientes con cuotas observadas)*."
            if gh_issues_on
            else "`TELEGRAM / SMTP` *(GitHub Issues desactivado por política de mínimos privilegios `T-018`; despacho por Telegram/SMTP con la selección de mayor EV)*."
        )
        lines.extend(
            [
                f"> ### 🏆 PICK ESTRELLA DEL DÍA (`{daily_top_info['pick_date']}` — 1 Solo Pick: Mayor Probabilidad de Acierto)",
                f"> - **Partido**: **{tp['partido']}** (`{tp['hora_partido_peru']} Hora Perú`)",
                f"> - **Pick Más Probable**: 🎯 **{tp['seleccion']}** ({tp['mercado']}) @ **`{tp['cuota_decimal']:.3f}`** *({tp['casa_apuestas']})*",
                f"> - **Probabilidad de Acierto (Modelo Calibrado)**: 🔥 **`{tp['prob_estimada']:.1f}%`** | **EV**: `+{tp['ev_porcentaje']:.1f}%`",
                f"> - **Despacho diario**: {channel_desc}",
                "",
            ]
        )
    elif daily_top_info and daily_top_info.get("pick_date"):
        lines.extend(
            [
                f"> ### 🏆 PICK ESTRELLA DEL DÍA (`{daily_top_info['pick_date']}`)",
                "> - **Estado**: 🛡️ **Jornada de Alta Volatilidad / Sin Selección >= 50% de Probabilidad**",
                "> - **Protección Activa**: Siguiendo tu directiva de enviar únicamente selecciones con alta probabilidad de acierto, hoy no se emite pick por correo porque las opciones disponibles son underdogs de alta cuota con varianza excesiva.",
                "",
            ]
        )

    lines.extend(
        [
            "Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido, con vigilancia de movimiento en contra `CLV < -5.0%`):",
            "",
            "| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Mejor Cuota (Casa) | Prob. Modelo | EV (%) | CLV (%) | Stake | Estado | Resultado / Ganancia |",
            "| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |",
        ]
    )

    if espn_real_bets:
        for b in espn_real_bets:
            clv_num = float(b["clv_porcentaje"]) if b["clv_porcentaje"] != "" else None
            clv_cell = f"`{clv_num:+.2f}%`" if clv_num is not None else "—"
            is_adverse_move = (b["estado"] == "PENDING" and clv_num is not None and clv_num <= -5.0)
            badge = (
                "⚠️ ALERTA CLV"
                if is_adverse_move
                else (
                    "⏳ PENDIENTE"
                    if b["estado"] == "PENDING"
                    else (
                        "✅ GANADA"
                        if b["estado"] == "WON"
                        else ("❌ PERDIDA" if b["estado"] == "LOST" else f"➖ {b['estado']}")
                    )
                )
            )
            res_str = (
                f"S/{b['beneficio_neto_pen']:+.2f} ({b['marcador_final']})"
                if b["beneficio_neto_pen"] != ""
                else (
                    "⚠️ Movimiento brusco en contra (posible baja de última hora)"
                    if is_adverse_move
                    else "Esperando final del partido"
                )
            )
            lines.append(
                f"| `{b['hora_partido_peru']}` | **{b['partido']}** | {b['mercado']} | **{b['seleccion']}** | "
                f"**{b['cuota_decimal']:.3f}** *({b['casa_apuestas']})* | {b['prob_estimada']:.1f}% | `+{b['ev_porcentaje']:.1f}%` | "
                f"{clv_cell} | S/{b['stake_pen']:.2f} | {badge} | {res_str} |"
            )
    else:
        lines.append("| — | — | — | Sin apuestas reales activas en este momento | — | — | — | — | — | — | — |")

    slate_items = compute_upcoming_slate_intelligence(db)
    active_slate_bets = [s for s in slate_items if s["verdict_status"] == "PENDING_BET" and s.get("bet_details")]

    lines.extend(
        [
            "",
            "### 🔍 2.A Radiografía de Apuestas Activas (¿Qué Está Apostando Hoy, Cuotas y Estadísticas Clave?)",
            "",
        ]
    )
    if active_slate_bets:
        for ab in active_slate_bets:
            bd = ab["bet_details"]
            st = ab["basketball_context"]
            proj = ab["projections"]
            lines.extend(
                [
                    f"#### 🎯 **{ab['matchup_display']}** — `{ab['game_start_time']} UTC`",
                    f"- **¿Qué está apostando el bot?**: **{bd['selection_label']}** en *{bd['bookmaker']}*",
                    f"- **Cuota Tomada vs Cuota Justa**: **`{bd['decimal_odds']:.3f}`** vs Cuota Justa **`{bd['fair_odds']:.3f}`** *(Ventaja Matemática EV: `+{bd['ev_pct']:.2f}%`)*",
                    f"- **Stake y Ganancia Potencial**: Stake **`S/{bd['stake_pen']:.2f} PEN`** → Ganancia neta potencial: **`+S/{bd['potential_profit_pen']:.2f} PEN`**",
                    f"- **Probabilidades**: Modelo Calibrado **`{bd['model_prob_pct']:.1f}%`**",
                    f"- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `{proj['expected_margin']:+.1f} pts` | Total esperado **`{proj['expected_total']:.1f} pts`** *(Intervalo Simulación 80% [Q10–Q90]: `{proj.get('simulation_q10_total', proj.get('conformal_q10_total', 205.0)):.0f} – {proj.get('simulation_q90_total', proj.get('conformal_q90_total', 252.0)):.0f} pts` | Prob. Prórroga: `{proj['overtime_prob_pct']:.1f}%` | Prob. Paliza: `{proj['blowout_prob_pct']:.1f}%`)*",
                    "- **Estadísticas Clave Tomadas en Cuenta**:",
                    f"  - **Rating Elo**: `{ab['home_team_code']} {st['home_elo']}` vs `{ab['away_team_code']} {st['away_elo']}` | **Eficiencia Neta (Off/Def)**: `{ab['home_team_code']} ({st['home_off_rtg']}/{st['home_def_rtg']})` vs `{ab['away_team_code']} ({st['away_off_rtg']}/{st['away_def_rtg']})` (`Dif: {st['net_rtg_diff']:+.1f} pts/100`)",
                    f"  - **Ritmo (Pace)**: `{st['expected_pace']:.1f} posesiones` | **Descanso**: Dif `{st['rest_diff']:+d}d` | **Viaje Geodésico**: `Dif. {st['travel_miles_diff']:+.0f} millas`",
                    f"- **Por qué apostó el modelo**: _{ab['verdict_reason']}_",
                    "",
                ]
            )
    else:
        lines.append("- Actualmente no hay apuestas pendientes en espera de inicio.")
        lines.append("")

    lines.extend(
        [
            "### 📋 2.B Cartelera Completa de Próximos Partidos: Cuotas, Estadísticas a Tomar en Cuenta y Veredicto",
            "",
            "| Hora (UTC) | Partido | Cuotas Ganador (`Local / Visita`) | Proyección Modelo (`Margen / Total`) | Estadísticas Clave (`Elo`, `NetRtg`, `Descanso`) | ¿Qué Hace el Bot y Por Qué? |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    for s in slate_items:
        st = s["basketball_context"]
        proj = s["projections"]
        odds_dict = s["odds"]
        ml_str = (
            f"Local **{odds_dict['home_odds']:.3f}** / Visita **{odds_dict['away_odds']:.3f}**"
            if odds_dict.get("home_odds") and odds_dict.get("away_odds")
            else "⏳ *Sin cuotas publicadas*"
        )
        proj_str = (
            f"**Margen {proj['expected_margin']:+.1f} pts** (Local `{proj['p_home_pct']:.1f}%`) · Total **{proj['expected_total']:.1f} pts**"
        )
        stats_str = (
            f"Elo `{st['home_elo']}/{st['away_elo']}` · Net `{st['net_rtg_diff']:+.1f}` · Pace `{st['expected_pace']:.1f}` · "
            f"Desc `{st['rest_diff']:+d}d`"
        )
        verdict_cell = f"**{s['verdict_summary']}** — _{s['verdict_reason']}_"
        lines.append(
            f"| `{s['game_start_time']}` | **{s['matchup_display']}** | {ml_str} | {proj_str} | {stats_str} | {verdict_cell} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)",
        "",
        "| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |",
        "| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |",
    ])

    settled_items = [x for x in all_formatted if x["estado"] != "PENDING"][:20]
    for s in settled_items:
        badge = "✅ WON" if s["estado"] == "WON" else ("❌ LOST" if s["estado"] == "LOST" else s["estado"])
        lines.append(
            f"| `{s['bet_id']}` | `{s['fecha_jornada']}` | `{s['partido']}` | {s['mercado']} | **{s['seleccion']}** | "
            f"{s['cuota_decimal']:.3f} | {s['prob_estimada']:.1f}% | `+{s['ev_porcentaje']:.1f}%` | {badge} | "
            f"**S/{float(s['beneficio_neto_pen']):+.2f}** | `S/{float(s['bankroll_posterior_pen']):.2f}` |"
        )

    # 4. Section for Player Props & SGP Paper Trading
    props_metrics = _compute_clean_props_metrics(db=db, initial_bankroll_pen=initial_bankroll_pen)

    if props_metrics:
        resolved_picks_count = int(props_metrics.get("resolved_picks", props_metrics.get("settled_picks", 0)))
        void_picks_count = int(props_metrics.get("void_picks", 0))
        lines.extend([
            "",
            "---",
            "",
            "## 🎯 4. Seguimiento Oficial de Paper Trading — Player Props & SGP RETAbet V8",
            "",
            f"- **Banca Virtual de Props**: `S/{initial_bankroll_pen:.2f} PEN` (Inicial) → **`S/{props_metrics.get('current_props_bankroll_pen', initial_bankroll_pen):.2f} PEN`** (`{props_metrics.get('total_net_profit_pen', 0.0):+.2f} PEN`)",
            f"- **Tasa de Acierto (Win Rate)**: **`{props_metrics.get('win_rate_pct', 0.0):.1f}%`** (`{props_metrics.get('won_picks', 0)}G - {props_metrics.get('lost_picks', 0)}P - {props_metrics.get('push_picks', 0)}E`)",
            f"- **ROI Acumulado en Props**: **`{props_metrics.get('roi_pct', 0.0):+.2f}%`** | **Total Apostado (Resueltas)**: `S/{props_metrics.get('total_staked_pen', 0.0):.2f} PEN`",
            (
                f"- **Brier Score (Calibración)**: `{props_metrics.get('brier_score', 0.0):.4f}` | **LogLoss**: `{props_metrics['log_loss']:.4f}` | **Accuracy (`p>=0.5`)**: `{props_metrics.get('accuracy_pct') or 0.0:.1f}%` | **Cobertura Empírica Intervalos Venn-Abers**: `{'n/d (sin intervalos calibrados)' if props_metrics.get('conformal_coverage_pct') is None else format(props_metrics['conformal_coverage_pct'], '.1f') + '%'}`"
                if props_metrics.get("log_loss") is not None
                else f"- **Brier Score (Calibración)**: `{props_metrics.get('brier_score', 0.0):.4f}` | **Cobertura Intervalos Venn-Abers**: `n/d (sin resueltas)`"
            ),
            f"- **Total de Picks Registrados**: `{props_metrics.get('total_picks', 0)}` (`{props_metrics.get('pending_picks', 0)}` en espera / `{resolved_picks_count}` resueltas verificadas / `{void_picks_count}` anuladas `VOID` con impacto `S/0.00 PEN`)",
            "",
            "### 📊 Desglose de Rendimiento por Categoría de Prop",
            "",
            "| Categoría | Resueltas | Ganadas | Perdidas | Anuladas (VOID) | Acierto (%) | Total Apostado (S/) | Beneficio Neto (S/) | ROI (%) |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ])
        for cat_k, cat_v in (props_metrics.get("category_breakdown") or {}).items():
            res_cnt = int(cat_v.get("resolved_count", cat_v.get("total_settled", 0)))
            void_cnt = int(cat_v.get("void_count", 0))
            if res_cnt > 0 or void_cnt > 0:
                lines.append(
                    f"| **{cat_k}** | {res_cnt} | {cat_v['won']} | {cat_v['lost']} | {void_cnt} | "
                    f"`{cat_v['win_rate_pct']:.1f}%` | S/{cat_v['total_staked_pen']:.2f} | "
                    f"**S/{cat_v['net_profit_pen']:+.2f}** | `{cat_v['roi_pct']:+.1f}%` |"
                )

        recent_settled = [
            pr for pr in (props_metrics.get("recent_settled") or [])
            if pr.get("status") in ("WON", "LOST", "PUSH")
        ]
        if recent_settled:
            lines.extend([
                "",
                "### 📜 Últimas Apuestas de Props Liquidadas (Auditoría Inmutable)",
                "",
            ])
            if void_picks_count > 0:
                lines.extend([
                    f"> **Nota de Transparencia de Auditoría**: Existen **{void_picks_count} registros históricos en estado `VOID` (anulados)** procedentes de ciclos sintéticos previos sin verificación de boxscore oficial (impacto financiero **`S/0.00 PEN`**). La tabla inferior muestra **exclusivamente las {resolved_picks_count} apuestas de props con resultado oficial resuelto (`WON`, `LOST`, `PUSH`)**.",
                    "",
                ])
            lines.extend([
                "| Fecha | Partido | Jugador / Combinada | Mercado | Selección | Línea | Cuota | Stat Real | Estado | Beneficio | Bankroll Post. |",
                "| :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: | :---: | ---: | ---: |",
            ])
            for pr in recent_settled[:20]:
                b_badge = "✅ WON" if pr["status"] == "WON" else ("❌ LOST" if pr["status"] == "LOST" else pr["status"])
                stat_disp = f"`{pr['actual_stat']:.1f}`" if pr.get("actual_stat") is not None else "—"
                match_disp = pr.get("matchup_display") or pr.get("game_id") or "—"
                lines.append(
                    f"| `{pr['matchday_date']}` | {match_disp} | **{pr['player_name']}** | {pr['prop_category']} | "
                    f"{pr['selection']} | `{float(pr['line_value']):.1f}` | `{float(pr['decimal_odds']):.2f}` | "
                    f"{stat_disp} | {b_badge} | **S/{float(pr.get('net_profit_pen') or 0.0):+.2f}** | `S/{float(pr.get('bankroll_after_pen') or initial_bankroll_pen):.2f}` |"
                )

    md_path = Path(md_output_path)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    html_path = md_path.parent / "reports" / "dashboard.html"
    generate_interactive_html_dashboard(
        metrics=metrics,
        espn_real_bets=espn_real_bets,
        slate_items=slate_items,
        html_output_path=html_path,
        peru_str=peru_str,
        props_paper_trading=props_metrics,
    )

    # Keep docs/index.html in 100% lockstep relative to md_path.parent
    docs_path = md_path.parent / "docs" / "index.html"
    try:
        docs_path.parent.mkdir(parents=True, exist_ok=True)
        if html_path.exists():
            docs_path.write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Failed to export docs/index.html: {exc}")

    return {"csv_path": str(csv_path), "md_path": str(md_path), "html_path": str(html_path)}


def generate_bet_tracking_markdown(
    db: DatabaseManager,
    metrics: dict[str, Any] | None = None,
) -> str:
    """Convenience helper that generates and returns the SEGUIMIENTO_APUESTAS.md content."""
    if metrics is None:
        from src.backtesting.backtester import WalkForwardBacktester
        from src.paper_trading.engine import build_production_engine

        metrics = WalkForwardBacktester(db, build_production_engine(db)).compute_comprehensive_metrics()
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        res = export_bets_and_tracking_dashboard(
            db=db,
            metrics=metrics,
            csv_output_path=tmp_root / "data" / "apuestas_historial.csv",
            md_output_path=tmp_root / "SEGUIMIENTO_APUESTAS.md",
        )
        return Path(res["md_path"]).read_text(encoding="utf-8")

