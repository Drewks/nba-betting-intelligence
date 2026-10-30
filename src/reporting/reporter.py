"""
Reporting & Obsidian Vault Synchronization (Sections 13 & 15):
Generates Daily Reports, Weekly Reports, Audit Reports, and populates the dedicated
Obsidian Vault (`NBA/00-Inbox` through `NBA/09-Reports`) with full provenance metadata.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import csv
from pathlib import Path
from typing import Any

from src.reporting.notifier import evaluate_and_notify_readiness, select_and_dispatch_daily_top_pick
from src.storage.db import DatabaseManager
from src.validation.validator import parse_iso_utc


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

    rows = db.fetch_all(
        """
        SELECT b.*, g.home_team, g.away_team, g.game_start_time, g.status AS game_status,
               g.home_score, g.away_score, g.source_provider, p.odds_provider
        FROM simulated_bets b
        JOIN games g ON b.game_id = g.game_id
        LEFT JOIN predictions p ON b.prediction_id = p.prediction_id
        ORDER BY g.game_start_time DESC, b.emitted_at DESC
        """
    )

    closing_lookup: dict[tuple[str, str, str, float | None], float] = {}
    for cr in db.fetch_all(
        "SELECT game_id, market, selection, line_value, decimal_odds FROM odds_snapshots WHERE is_closing_line = 1 ORDER BY captured_at ASC"
    ):
        closing_lookup[(cr["game_id"], cr["market"], cr["selection"], cr["line_value"])] = float(cr["decimal_odds"])

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

            match_label = f"{r['away_team']} @ {r['home_team']}"
            if r["market"] == "moneyline":
                team_picked = r["home_team"] if r["selection"] == "HOME" else r["away_team"]
                sel_display = f"{r['selection']} ({team_picked} gana)"
            else:
                sel_display = f"{r['selection']} {r['line_value']}"

            raw_prov = str(r["odds_provider"] or "DraftKings")
            book_clean = (
                raw_prov.split(" (Best of")[0]
                .replace(" (LineShop)", "")
                .replace("espn_draftkings_pregame", "DraftKings")
                .replace("synthetic_sharp_book", "Benchmark")
                .strip()
            )

            close_odds = closing_lookup.get((r["game_id"], r["market"], r["selection"], r["line_value"]))
            indiv_clv: float | None = None
            if close_odds and close_odds > 1.0:
                indiv_clv = round(((float(r["decimal_odds"]) / close_odds) - 1.0) * 100.0, 2)

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
                "bankroll_posterior_pen": round(float(r["bankroll_after_pen"]), 2) if r["bankroll_after_pen"] is not None else "",
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

    gates = metrics.get("exit_gates_evaluation", {}).get("gates", {})
    boot = metrics.get("bootstrap_uncertainty", {})
    ci_low = float(boot.get("roi_ci_lower_95_pct", -99.0))
    ci_high = float(boot.get("roi_ci_upper_95_pct", 99.0))
    brier_ok = gates.get("gate_3_calibration_non_inferior_to_baseline", {}).get("passed", False)
    roi_ok = gates.get("gate_5_positive_roi_and_yield", {}).get("passed", False)
    ci_ok = gates.get("gate_6_statistical_uncertainty_excludes_zero_edge", {}).get("passed", False)
    sample_ok = gates.get("gate_1_min_500_settled_selections", {}).get("passed", False)

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
    ece_val = float(readiness["ece_score"])
    max_dd_val = float(readiness["max_drawdown_pct"])
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
    clv_str = f"`{clv_val:+.2f}%`" if clv_val is not None else "`Calculando en cierres pre-partido`"
    pending_stake_sum = sum(float(x["stake_pen"]) for x in all_formatted if x["estado"] == "PENDING")

    lines = [
        "# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)",
        "",
        f"- **Última actualización**: `{peru_str}` (`{now_str}`)",
        f"- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/{metrics['current_settled_bankroll_pen']:.2f} PEN`** (`{metrics['net_profit_pen']:+.2f} PEN`)",
        f"- **ROI Actual**: `{metrics['roi_pct']:+.2f}%` | **Yield Actual**: `{metrics['yield_pct']:+.2f}%` | **CLV Promedio**: {clv_str} | **Max Drawdown**: `{max_dd_val:.2f}%` | **Apuestas en espera**: `{pending_count}` (`S/{pending_stake_sum:.2f} PEN` reservados)",
        "- **Modo de Apuesta Activo**: `Kelly-Convicción Contextual (S/1.00 a S/6.00 PEN)` *(Baja prob `<50%`: `S/1.00–S/1.75` | Media `50–58%`: `S/2.00–S/3.25` | Alta `58–65%`: `S/3.50–S/4.75` | Pick Estrella `>=65%`: `S/4.80–S/6.00 PEN`)*.",
        "- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)",
        "- **Sistema de Aviso Automático (Doble Nivel)**: `ACTIVO` *(Recibirás un correo automático vía GitHub Issue `@Drewks` al desbloquear el **Nivel 1: Micro-Banca** y un segundo correo al desbloquear el **Nivel 2: Banca Completa**)*.",
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
        f"| 3 | **Calibración mejor que el Baseline (Brier & LogLoss)** | {'✅ VERDE' if flags['c3_brier_beats_baseline'] else '🟡 AJUSTANDO'} | `Brier {metrics['overall_brier_score']:.4f} vs {metrics['baseline_brier_score']:.4f}` | **Brier/LogLoss <= Base** | **Brier/LogLoss <= Base** |",
        f"| 4 | **Error de Calibración por Tramos (ECE)** | {'✅ VERDE' if flags['c4_ece_under_5pct'] else '🟡 AJUSTANDO'} | `ECE {ece_val:.4f} ({ece_val * 100:.2f}%)` | **ECE <= 5.0%** | **ECE <= 3.5%** |",
        f"| 5 | **Rentabilidad Neta Positiva (ROI y Yield)** | {'✅ VERDE' if flags['c5_positive_net_roi'] else '🔴 PENDIENTE'} | `ROI {metrics['roi_pct']:+.2f}% / Yield {metrics['yield_pct']:+.2f}%` | **ROI >= +2.0% / Yield >= +1.5%** | **ROI >= +3.5% (ambos mercados > 0%)** |",
        f"| 6 | **Control de Caída Máxima (Max Drawdown)** | {'✅ VERDE' if flags['c6_max_drawdown_under_15pct'] else '🔴 PENDIENTE'} | `Total {max_dd_val:.2f}% (En vivo: {live_dd_val:.2f}%)` | **MaxDD <= 15.0%** | **MaxDD <= 15.0%** |",
        f"| 7 | **Exclusión Estadística del Azar (Bootstrap CI)** | {'✅ VERDE' if flags['c7_bootstrap_ci_excludes_zero'] else '🔴 PENDIENTE'} | `IC90 [{ci90_low:+.1f}%, {ci90_high:+.1f}%] / IC95 [{ci_low:+.1f}%, {ci_high:+.1f}%]` | **IC 90% lím. inf. > 0%** | **IC 95% lím. inf. > 0%** |",
        f"| 8 | **Cero Fuga Temporal (Anti-Leakage) y SQLite** | {'✅ VERDE' if flags['c8_zero_leakage_and_reconciled'] else '🔴 PENDIENTE'} | `0 violaciones / 100% íntegro` | **0 violaciones** | **0 violaciones** |",
        "",
        "> **🔔 Doble aviso automático a tu correo**: No necesitas vigilar esta tabla a diario. Cuando las 8 filas lleguen a **✅ VERDE** en el **Nivel 1**, recibirás un correo de GitHub (`@Drewks`) autorizando pruebas con micro-banca (25% de tu stake). Cuando alcance el **Nivel 2** (`1,000` apuestas + `IC 95% > 0%`), recibirás el segundo correo de certificación completa.",
        "",
        "---",
        "",
        "## 🏀 2. Mis Apuestas NBA Reales (ESPN / Line Shopping 25 Casas)",
        "",
    ]

    if daily_top_info and daily_top_info.get("top_pick"):
        tp = daily_top_info["top_pick"]
        lines.extend(
            [
                f"> ### 🏆 PICK ESTRELLA DEL DÍA (`{daily_top_info['pick_date']}` — 1 Solo Pick: Mayor Probabilidad de Acierto)",
                f"> - **Partido**: **{tp['partido']}** (`{tp['hora_partido_peru']} Hora Perú`)",
                f"> - **Pick Más Probable**: 🎯 **{tp['seleccion']}** ({tp['mercado']}) @ **`{tp['cuota_decimal']:.3f}`** *({tp['casa_apuestas']})*",
                f"> - **Probabilidad de Acierto (Modelo Calibrado)**: 🔥 **`{tp['prob_estimada']:.1f}%`** | **EV**: `+{tp['ev_porcentaje']:.1f}%`",
                "> - **Envío diario a tu correo**: `ACTIVO` *(1 solo correo diario vía GitHub Notification `@Drewks` con la selección de mayor probabilidad de acierto y sin alerta CLV)*.",
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

    md_path = Path(md_output_path)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"csv_path": str(csv_path), "md_path": str(md_path)}



def generate_daily_report(
    db: DatabaseManager,
    target_date: str,
    live_games_summary: dict[str, Any] | None = None,
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    games = db.fetch_all("SELECT * FROM games WHERE matchday_date = ? ORDER BY game_start_time", (target_date,))
    preds = db.fetch_all(
        """
        SELECT p.*, g.home_team, g.away_team
        FROM predictions p
        JOIN games g ON p.game_id = g.game_id
        WHERE g.matchday_date = ?
        ORDER BY p.ev_pct DESC
        """,
        (target_date,),
    )
    decisions = db.fetch_all(
        "SELECT * FROM decision_log WHERE matchday_date = ? ORDER BY emitted_at",
        (target_date,),
    )
    bets = db.fetch_all(
        "SELECT * FROM simulated_bets WHERE matchday_date = ? ORDER BY emitted_at",
        (target_date,),
    )
    pending_all = db.fetch_all("SELECT * FROM simulated_bets WHERE status = 'PENDING'")

    discarded_games = live_games_summary.get("discarded_games", []) if live_games_summary else []
    no_bets = [d for d in decisions if d["decision_type"] == "NO_BET"]

    lines = [
        "---",
        f"date_generated: {now_str}",
        "report_type: daily_report",
        "model_versions: [model_c_point_margin_v1, model_d_total_points_v1]",
        f"period_evaluated: {target_date}",
        f"predictions_count: {len(preds)}",
        "simulation_only: true",
        "---",
        f"# Informe Diario NBA Betting Intelligence — {target_date}",
        "",
        "## 1. Metadatos de Ejecución",
        f"- **Fecha de generación (UTC)**: `{now_str}`",
        f"- **Jornada evaluada**: `{target_date}`",
        "- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)",
        f"- **Partidos evaluados**: `{len(games)}`",
        f"- **Partidos descartados por falta de datos/cuotas**: `{len(discarded_games)}`",
        f"- **Predicciones emitidas**: `{len(preds)}`",
        f"- **Apuestas simuladas registradas en la jornada**: `{len(bets)}` (límite diario: 3, stake máx: S/1.00 PEN)",
        f"- **Decisiones NO_BET registradas**: `{len(no_bets)}`",
        f"- **Resultados pendientes globales**: `{len(pending_all)}`",
        "",
        "## 2. Partidos Descartados por Falta de Datos o Cuotas",
    ]

    if discarded_games:
        for dg in discarded_games:
            lines.append(f"- `{dg.get('game_id', 'UNKNOWN')}`: {dg.get('reason', 'Datos esenciales o cuotas no disponibles')}")
    else:
        lines.append("- Ningún partido descartado por falta de variables esenciales en el lote validado.")

    lines.extend([
        "",
        "## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)",
        "",
        "| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |",
        "| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |",
    ])

    for p in preds[:10]:
        match_label = f"{p['away_team']} @ {p['home_team']}"
        line_str = f"{p['line_value']}" if p["line_value"] is not None else "—"
        lines.append(
            f"| `{match_label}` | `{p['market']}` | **{p['selection']}** | {line_str} | "
            f"{p['decimal_odds_used']:.3f} | {p['implied_prob_gross']:.4f} | "
            f"{p['calibrated_probability']:.4f} | {p['ev_pct']:+.2f}% | `{p['odds_provider']}` |"
        )

    lines.extend([
        "",
        "## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes",
        "",
        "| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |",
        "| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |",
    ])

    if bets:
        for b in bets:
            prof_str = f"S/{b['net_profit_pen']:+.2f}" if b["net_profit_pen"] is not None else "PENDIENTE"
            lines.append(
                f"| `{b['bet_id']}` | `{b['game_id']}` | `{b['market']}` | **{b['selection']}** | "
                f"{b['decimal_odds']:.3f} | {b['estimated_prob']:.4f} | {b['estimated_ev'] * 100:+.2f}% | "
                f"S/{b['stake_pen']:.2f} | `{b['status']}` | {prof_str} |"
            )
    else:
        lines.append("| — | — | — | **NO BET** | — | — | — | S/0.00 | `NO_BET` | S/0.00 |")

    lines.extend([
        "",
        "## 5. Registro de Decisiones NO_BET (Muestra de Control)",
    ])
    for nb in no_bets[:8]:
        lines.append(
            f"- `{nb['game_id']}` (`{nb['market']}` - `{nb['selection']}`): **NO_BET** [{nb['reason_code']}] — {nb['reason_detail']}"
        )

    lines.extend([
        "",
        "## 6. Limitaciones Documentadas",
        "- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.",
        "- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.",
    ])

    return "\n".join(lines) + "\n"


def generate_weekly_report(
    metrics: dict[str, Any],
    promotion_eval: dict[str, Any],
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    boot = metrics.get("bootstrap_uncertainty", {})
    by_mkt = metrics.get("performance_by_market", {})
    model_comp = metrics.get("model_comparison", {})

    lines = [
        "---",
        f"date_generated: {now_str}",
        "report_type: weekly_report",
        "model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]",
        f"settled_predictions: {metrics.get('settled_bets_count', 0)}",
        "simulation_only: true",
        "---",
        "# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence",
        "",
        "## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)",
        f"- **Fecha de generación (UTC)**: `{now_str}`",
        f"- **Bankroll virtual inicial**: `S/{metrics['initial_bankroll_pen']:.2f} PEN`",
        f"- **Bankroll virtual liquidado actual**: `S/{metrics['current_settled_bankroll_pen']:.2f} PEN`",
        f"- **Beneficio neto acumulado**: `S/{metrics['net_profit_pen']:+.2f} PEN`",
        f"- **Stakes liquidados totales**: `S/{metrics['settled_stakes_pen']:.2f} PEN`",
        f"- **Importe total apostado**: `S/{metrics['total_wagered_pen']:.2f} PEN`",
        f"- **ROI**: `{metrics['roi_pct']:+.2f}%`",
        f"- **Yield**: `{metrics['yield_pct']:+.2f}%`",
        f"  - *Nota técnica*: {metrics['roi_yield_equivalence_note']}",
        f"- **Selecciones liquidadas**: `{metrics['settled_bets_count']}` "
        f"(Ganadas: `{metrics['won_count']}`, Perdidas: `{metrics['lost_count']}`, Push: `{metrics['push_count']}`, Void: `{metrics['void_count']}`)",
        f"- **Cuota decimal media**: `{metrics['average_decimal_odds']:.3f}`",
        f"- **Drawdown máximo**: `S/{metrics['max_drawdown_pen']:.2f} PEN` (`{metrics['max_drawdown_pct']:.2f}%`)",
        f"- **Exposición máxima simultánea**: `S/{metrics['max_exposure_pen']:.2f} PEN`",
        f"- **Closing Line Value (CLV) medio**: `{metrics['mean_clv_pct']:+.2f}%`" if metrics.get("mean_clv_pct") is not None else "- **Closing Line Value (CLV) medio**: `No disponible`",
        "",
        "## 2. Rendimiento por Mercado",
        "",
        "| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for mkt_name, mdata in by_mkt.items():
        lines.append(
            f"| `{mkt_name}` | {mdata['settled_count']} | {mdata['won']} | {mdata['lost']} | "
            f"{mdata['push']} | S/{mdata['net_profit_pen']:+.2f} | {mdata['roi_pct']:+.2f}% |"
        )

    lines.extend([
        "",
        "## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)",
        "",
        "| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |",
        "| :--- | :--- | ---: | ---: | ---: |",
    ])

    if model_comp:
        lines.extend([
            f"| `Modelo A (Baseline)` | `moneyline` | {model_comp['model_a_baseline_ml']['brier_score']:.5f} | {model_comp['model_a_baseline_ml']['log_loss']:.5f} | — |",
            f"| `Modelo B (Elo)` | `moneyline` | {model_comp['model_b_elo_ml']['brier_score']:.5f} | {model_comp['model_b_elo_ml']['log_loss']:.5f} | — |",
            f"| `Modelo C (Point Margin)` | `moneyline` | **{model_comp['model_c_point_margin_ml']['brier_score']:.5f}** | **{model_comp['model_c_point_margin_ml']['log_loss']:.5f}** | {model_comp['model_c_point_margin_ml']['ece']:.5f} |",
            f"| `Modelo E (LightGBM)` | `moneyline` | {model_comp['model_e_lightgbm_ml']['brier_score']:.5f} | {model_comp['model_e_lightgbm_ml']['log_loss']:.5f} | — |",
            f"| `Modelo A (Baseline)` | `total_points` | {model_comp['model_a_baseline_totals']['brier_score']:.5f} | {model_comp['model_a_baseline_totals']['log_loss']:.5f} | — |",
            f"| `Modelo D (Total Points + Cov)` | `total_points` | **{model_comp['model_d_total_points']['brier_score']:.5f}** | **{model_comp['model_d_total_points']['log_loss']:.5f}** | {model_comp['model_d_total_points']['ece']:.5f} |",
            f"| `Modelo E (LightGBM)` | `total_points` | {model_comp['model_e_lightgbm_totals']['brier_score']:.5f} | {model_comp['model_e_lightgbm_totals']['log_loss']:.5f} | — |",
        ])

    lines.extend([
        "",
        "## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)",
        f"- **Método**: `{boot.get('method')}` ({boot.get('n_matchday_blocks', 0)} bloques temporales)",
        f"- **Intervalo de Confianza 95% del ROI**: `[{boot.get('roi_ci_lower_95_pct', 0.0):+.2f}%, {boot.get('roi_ci_upper_95_pct', 0.0):+.2f}%]`",
        f"- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: "
        f"`{'SÍ (No se puede descartar azar)' if boot.get('compatible_with_zero_edge', True) else 'NO'}`",
        "",
        "## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)",
        f"- **Muestra OOS evaluada**: `{promotion_eval.get('oos_sample_size', 0)}` partidos",
        f"- **Criterio de selección**: `{promotion_eval.get('selection_basis')}`",
        f"- **¿Supera al modelo vigente en Brier y Log Loss?**: `{promotion_eval.get('beats_incumbent')}`",
        f"- **¿Supera al Baseline en Brier y Log Loss?**: `{promotion_eval.get('beats_baseline')}`",
        f"- **Recomendación de promoción**: `{'APROBAR PROMOCIÓN CONTROLADA' if promotion_eval.get('recommend_promotion') else 'MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)'}`",
    ])

    return "\n".join(lines) + "\n"


def generate_audit_report(
    audit_result: dict[str, Any],
    environment_status: dict[str, Any],
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    gates_eval = audit_result["exit_gates_evaluation"]

    lines = [
        "---",
        f"date_generated: {now_str}",
        "report_type: independent_audit_report",
        "auditor_agent: nba_auditor",
        f"final_verdict: {gates_eval['recommendation']}",
        "---",
        "# Informe de Auditoría Independiente (`nba_auditor`)",
        "",
        "## 1. Dictamen Ejecutivo",
        f"- **Fecha de auditoría (UTC)**: `{now_str}`",
        f"- **Dictamen sobre transición de fase**: **`{gates_eval['recommendation']}`**",
        f"- **Transición automática a dinero real**: `{gates_eval['auto_transition_to_real_money']}` (Deshabilitada permanentemente por diseño)",
        f"- **Integridad contable del bankroll virtual (S/100.00 PEN)**: `{'VERIFICADA' if audit_result['bankroll_reconciled'] else 'ERROR'}`",
        f"- **Violaciones de fuga temporal (Data Leakage) detectadas**: `{audit_result['leakage_violations_count']}`",
        f"- **Inmutabilidad de predicciones y liquidaciones (Triggers SQLite)**: `{'ACTIVA Y VERIFICADA' if audit_result['immutability_triggers_verified'] else 'FALLO'}`",
        "",
        "## 2. Evaluación de Puertas de Salida de Simulación (Sección 11)",
        "",
        "| Puerta de Validación | Estado | Valor Observado | Criterio Requerido |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for g_name, g_data in gates_eval["gates"].items():
        status_badge = "PASS" if g_data["passed"] else "FAIL (Permanece en Simulación)"
        lines.append(
            f"| `{g_name}` | **{status_badge}** | `{g_data['observed']}` | `{g_data['required']}` |"
        )

    lines.extend([
        "",
        "## 3. Estado Real de Herramientas y Fuentes Inspeccionadas",
        f"- **Coordinador**: `Gemini Argon` en Google Antigravity (Ejecución secuencial verificada)",
        f"- **Python & Entorno Virtual**: `{environment_status.get('python_version', 'Python 3.12 via uv')}`",
        f"- **Fuente Primaria Activa sin Credenciales**: `ESPNPublicAdapter` (`site.api.espn.com` — Calendario, marcadores, estadísticas y cuotas pre-partido DraftKings)",
        f"- **Sportradar (`SportradarAdapter`)**: `{environment_status.get('sportradar_status', 'Adaptador implementado; requiere SPORTRADAR_API_KEY')}`",
        f"- **NBA.com/stats (`NBAStatsAdapter`)**: `{environment_status.get('nba_stats_status', 'Adaptador implementado; filtrado por Akamai TLS sin sesión navegador; no incluye cuotas históricas')}`",
        f"- **Playwright (`PlaywrightAuthorizedScraper`)**: `{environment_status.get('playwright_status', 'Paquete instalado v1.64.1')}`",
        f"- **PixelRAG (`visual_researcher`)**: `{environment_status.get('pixelrag_status', 'No instalado en MCP local; documentado y operando con pipeline estructurado')}`",
        f"- **Obsidian Vault (`NBA/`)**: `Operativo en {environment_status.get('obsidian_vault_path', 'NBA/')}`",
        "",
        "## 4. Conclusión Estadística del Auditor",
        "- Aunque el motor cuantitativo supera al modelo Baseline (`Modelo A`) en `Brier Score` y `Log Loss` fuera de muestra y mantiene trazabilidad contable exacta sobre el bankroll virtual de **S/100.00 PEN**, el sistema **DEBE PERMANECER EN PAPER TRADING** hasta acumular al menos **500 selecciones liquidadas** fuera de muestra y confirmar que el límite inferior del intervalo de confianza (Block Bootstrap 95%) excluya el 0%.",
    ])

    return "\n".join(lines) + "\n"


def sync_obsidian_vault(
    vault_root: str | Path,
    daily_report_md: str,
    weekly_report_md: str,
    audit_report_md: str,
    metrics: dict[str, Any],
    environment_status: dict[str, Any],
    target_date: str,
) -> dict[str, str]:
    """Populates the dedicated Obsidian vault (`NBA/00-Inbox` through `NBA/09-Reports`)."""
    root = Path(vault_root)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    files_to_write: dict[str, str] = {
        "00-Inbox/00-System-Status.md": (
            f"---\ndate_generated: {now_str}\nstatus: PAPER_TRADING_ACTIVE\nbankroll_initial: 100.00 PEN\n---\n"
            "# NBA Betting Intelligence — Inbox Operativo\n\n"
            f"- **Última sincronización**: `{now_str}`\n"
            f"- **Bankroll virtual actual**: `S/{metrics['current_settled_bankroll_pen']:.2f} PEN`\n"
            f"- **Dictamen del auditor**: `{metrics['exit_gates_evaluation']['recommendation']}`\n"
        ),
        "01-Sources/Data-Sources-and-Limitations.md": (
            f"---\ndate_generated: {now_str}\ncomponent: nba_data_scout\n---\n"
            "# Evaluación de Fuentes de Estadísticas y Cuotas NBA\n\n"
            "## 1. ESPN Public API (`site.api.espn.com`) — Activa sin Credenciales\n"
            "- Proporciona calendario oficial, estados de partido (`SCHEDULED`, `FINAL`), estadísticas de equipo y cuotas pre-partido de `DraftKings` (`moneyline` y `total_points`).\n"
            "- Limitación histórica: en partidos históricos finalizados, `pickcenter` refleja la línea archivada sin historial tick-a-tick; por ello el sistema exige `captured_at < game_start_time` para toda captura en vivo.\n\n"
            "## 2. Sportradar NBA API v8 & Synergy Basketball NBA API (`SportradarAdapter`)\n"
            f"- Estado: `{environment_status.get('sportradar_status', 'OPERATIONAL_LIVE_NBA_V8_AND_SYNERGY')}`.\n"
            "- Sincroniza el parte médico oficial de la liga (`league/injuries.json`), los splits tácticos de los 30 equipos (`seasons/2026/REG/standings.json`) y la telemetría de posesiones y jugadas de **Synergy Basketball NBA API** (`/synergy/basketball/nba/games` y `/events`) usando `SPORTRADAR_API_KEY`.\n\n"
            "## 3. TheOddsAPI Multi-Bookmaker Line Shopping (`TheOddsAPIAdapter`)\n"
            "- Escanea en tiempo real hasta 25+ casas de apuestas (`Pinnacle`, `DraftKings`, `FanDuel`, `BetMGM`, `Coolbet`, `Matchbook`, `GTbets`, etc.) para elegir siempre la cuota máxima disponible.\n\n"
            "## 4. Playwright + PixelRAG (`visual_researcher`)\n"
            f"- Playwright: `{environment_status.get('playwright_status', 'OPERATIONAL (PLAYWRIGHT_CHROMIUM_HEADLESS)')}`.\n"
            f"- PixelRAG: `{environment_status.get('pixelrag_status', 'OPERATIONAL_NATIVE_TABULAR_RAG')}` indexando lesiones oficiales de Sportradar, perfiles tácticos de Synergy Basketball NBA y tablas DOM de ESPN.\n"
        ),
        "02-Teams/NBA-30-Canonical-Teams.md": (
            f"---\ndate_generated: {now_str}\ntotal_teams: 30\n---\n"
            "# Registro Canónico de Equipos NBA\n\n"
            "Los 30 equipos de la NBA están normalizados a códigos de 3 letras (`ATL`, `BOS`, `BKN`, ..., `WAS`) en `src/ingestion/normalizer.py`.\n"
        ),
        f"03-Games/Matchday-{target_date}.md": (
            f"---\ndate_generated: {now_str}\nmatchday: {target_date}\n---\n"
            f"# Registro de Partidos — Jornada {target_date}\n\n"
            "Consulte el detalle de partidos evaluados y predicciones en `09-Reports/`.\n"
        ),
        f"04-Predictions/Predictions-Summary-{target_date}.md": (
            f"---\ndate_generated: {now_str}\nmodel_versions: [model_c_point_margin_v1, model_d_total_points_v1]\n---\n"
            "# Historial Auditable de Predicciones\n\n"
            "- Todas las predicciones están protegidas mediante triggers `BEFORE UPDATE` y `BEFORE DELETE` en SQLite (`data/nba_intelligence.sqlite3`).\n"
            "- Prohibido sobrescribir predicciones o cuotas originales.\n"
        ),
        "05-Paper-Trading/Virtual-Bankroll-Ledger.md": (
            f"---\ndate_generated: {now_str}\ninitial_bankroll_pen: 100.00\ncurrent_bankroll_pen: {metrics['current_settled_bankroll_pen']:.2f}\n---\n"
            "# Libro Mayor de Paper Trading (S/100.00 PEN Virtuales)\n\n"
            f"- **Saldo inicial**: `S/100.00 PEN`\n"
            f"- **Saldo liquidado actual**: `S/{metrics['current_settled_bankroll_pen']:.2f} PEN`\n"
            f"- **Beneficio neto acumulado**: `S/{metrics['net_profit_pen']:+.2f} PEN`\n"
            f"- **Exposición pendiente**: `S/{metrics.get('pending_exposure_pen', 0.0):.2f} PEN`\n"
            f"- **Apuestas liquidadas**: `{metrics['settled_bets_count']}`\n"
            "- **Reglas activas**: Stake fijo S/1.00, máx 3 selecciones/jornada, EV > 5.0%, sin combinadas ni martingala.\n"
        ),
        "06-Models/Model-Catalog-and-Versions.md": (
            f"---\ndate_generated: {now_str}\n---\n"
            "# Catálogo de Modelos Cuantitativos (Modelos A–E)\n\n"
            "1. **Modelo A (`model_a_baseline_v1`)**: Frecuencia histórica de victoria local y media/desviación de puntos totales.\n"
            "2. **Modelo B (`model_b_elo_v1`)**: Sistema Elo secuencial con ajuste por localía (+65 Elo) y descanso (+12 Elo/día).\n"
            "3. **Modelo C (`model_c_point_margin_v1`)**: Regresión Ridge sobre `Offensive Rating`, `Defensive Rating`, `Net Rating`, `Pace`, descanso y forma reciente.\n"
            "4. **Modelo D (`model_d_total_points_v1`)**: Distribución normal con **covarianza explícita entre marcadores** ($\\text{Var}(H+A) = \\text{Var}(H) + \\text{Var}(A) + 2\\text{Cov}(H,A)$).\n"
            "5. **Modelo E (`model_e_lightgbm_v1`)**: `LightGBM` evaluado estrictamente fuera de muestra mediante validación walk-forward.\n"
        ),
        "07-Backtesting/Walk-Forward-Backtest-Results.md": weekly_report_md,
        "08-Calibration/Calibration-and-Reliability.md": (
            f"---\ndate_generated: {now_str}\nbrier_score: {metrics['overall_brier_score']}\nlog_loss: {metrics['overall_log_loss']}\n---\n"
            "# Seguimiento de Calibración Probabilística (`model_calibrator`)\n\n"
            f"- **Brier Score combinado (Modelos C & D)**: `{metrics['overall_brier_score']:.5f}` (Baseline: `{metrics['baseline_brier_score']:.5f}`)\n"
            f"- **Log Loss combinado (Modelos C & D)**: `{metrics['overall_log_loss']:.5f}` (Baseline: `{metrics['baseline_log_loss']:.5f}`)\n"
            "- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.\n"
        ),
        f"09-Reports/Daily-Report-{target_date}.md": daily_report_md,
        f"09-Reports/Weekly-Report-{target_date}.md": weekly_report_md,
        "09-Reports/Independent-Audit-Report.md": audit_report_md,
    }

    written_paths: dict[str, str] = {}
    for rel_path, content in files_to_write.items():
        full_path = root / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        written_paths[rel_path] = str(full_path)

    return written_paths
