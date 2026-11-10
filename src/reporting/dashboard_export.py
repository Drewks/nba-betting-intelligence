"""
Exports Excel/Sheets CSV and markdown dashboards for tracking bets and model readiness.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from typing import Any

from src.evaluation.clv import compute_bet_clv, index_closing_rows
from src.reporting.dashboard_generator import generate_interactive_html_dashboard
from src.reporting.notifier import evaluate_and_notify_readiness, select_and_dispatch_daily_top_pick
from src.reporting.slate_intelligence import compute_upcoming_slate_intelligence
from src.storage.db import DatabaseManager
from src.utils.team_dictionary import format_matchup, get_team_full_name
from src.validation.validator import parse_iso_utc

logger = logging.getLogger(__name__)


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
        FROM v_observed_simulated_bets b
        JOIN games g ON b.game_id = g.game_id
        LEFT JOIN predictions p ON b.prediction_id = p.prediction_id
        ORDER BY g.game_start_time DESC, b.emitted_at DESC
        """
    )

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

    lines = [
        "# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)",
        "",
        f"- **Última actualización**: `{peru_str}` (`{now_str}`)",
        f"- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/{metrics['current_settled_bankroll_pen']:.2f} PEN`** (`{metrics['net_profit_pen']:+.2f} PEN`)",
        f"- **ROI Actual**: `{metrics['roi_pct']:+.2f}%` | **Yield Actual**: `{metrics['yield_pct']:+.2f}%` | **CLV (vs cierre sin margen)**: {clv_str} | **Max Drawdown**: `{max_dd_txt}` | **Apuestas en espera**: `{pending_count}` (`S/{pending_stake_sum:.2f} PEN` reservados)",
        "- **Motor Predictivo Activo**: `Ensemble (Elo + Ridge + LightGBM + Monte Carlo) anclado 70% al mercado sin margen`. Sin ventaja demostrada frente al mercado.",
        "- **Modo de Apuesta Activo**: `Stake fijo S/1.00 PEN (AGENTS.md v1)` | Máx. 3 selecciones/jornada | EV > 5% | Solo cuotas observadas (nunca estimadas).",
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
                "> - **Envío diario a tu correo**: `ACTIVO` *(1 solo correo diario vía GitHub Notification `@Drewks` con la selección de mayor EV entre las apuestas pendientes con cuotas observadas)*.",
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
                    f"- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `{proj['expected_margin']:+.1f} pts` | Total esperado **`{proj['expected_total']:.1f} pts`** *(Rango 80% Conformal: `{proj['conformal_q10_total']:.0f} – {proj['conformal_q90_total']:.0f} pts` | Prob. Prórroga: `{proj['overtime_prob_pct']:.1f}%` | Prob. Paliza: `{proj['blowout_prob_pct']:.1f}%`)*",
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
    try:
        from src.paper_trading.engine import PaperTradingEngine
        pt_eng = PaperTradingEngine(db=db)
        props_metrics = pt_eng.get_player_props_performance_metrics()
    except Exception:
        props_metrics = {}

    if props_metrics:
        lines.extend([
            "",
            "---",
            "",
            "## 🎯 4. Seguimiento Oficial de Paper Trading — Player Props & SGP RETAbet V8",
            "",
            f"- **Banca Virtual de Props**: `S/100.00 PEN` (Inicial) → **`S/{props_metrics.get('current_props_bankroll_pen', 100.0):.2f} PEN`** (`{props_metrics.get('total_net_profit_pen', 0.0):+.2f} PEN`)",
            f"- **Tasa de Acierto (Win Rate)**: **`{props_metrics.get('win_rate_pct', 0.0):.1f}%`** (`{props_metrics.get('won_picks', 0)}G - {props_metrics.get('lost_picks', 0)}P - {props_metrics.get('push_picks', 0)}E`)",
            f"- **ROI Acumulado en Props**: **`{props_metrics.get('roi_pct', 0.0):+.2f}%`** | **Total Apostado**: `S/{props_metrics.get('total_staked_pen', 0.0):.2f} PEN`",
            f"- **Brier Score (Calibración)**: `{props_metrics.get('brier_score', 0.0):.4f}` | **Cobertura Conformal**: `{props_metrics.get('conformal_coverage_pct', 100.0):.1f}%`",
            f"- **Total de Picks Registrados**: `{props_metrics.get('total_picks', 0)}` (`{props_metrics.get('pending_picks', 0)}` en espera / `{props_metrics.get('settled_picks', 0)}` liquidados)",
            "",
            "### 📊 Desglose de Rendimiento por Categoría de Prop",
            "",
            "| Categoría | Liquidadas | Ganadas | Perdidas | Acierto (%) | Total Apostado (S/) | Beneficio Neto (S/) | ROI (%) |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ])
        for cat_k, cat_v in (props_metrics.get("category_breakdown") or {}).items():
            if cat_v.get("total_settled", 0) > 0:
                lines.append(
                    f"| **{cat_k}** | {cat_v['total_settled']} | {cat_v['won']} | {cat_v['lost']} | "
                    f"`{cat_v['win_rate_pct']:.1f}%` | S/{cat_v['total_staked_pen']:.2f} | "
                    f"**S/{cat_v['net_profit_pen']:+.2f}** | `{cat_v['roi_pct']:+.1f}%` |"
                )

        recent_settled = props_metrics.get("recent_settled") or []
        if recent_settled:
            lines.extend([
                "",
                "### 📜 Últimas Apuestas de Props Liquidadas (Auditoría Inmutable)",
                "",
                "| Fecha | Partido | Jugador / Combinada | Mercado | Selección | Línea | Cuota | Stat Real | Estado | Beneficio | Bankroll Post. |",
                "| :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: | :---: | ---: | ---: |",
            ])
            for pr in recent_settled[:15]:
                b_badge = "✅ WON" if pr["status"] == "WON" else ("❌ LOST" if pr["status"] == "LOST" else pr["status"])
                stat_disp = f"`{pr['actual_stat']:.1f}`" if pr.get("actual_stat") is not None else "—"
                lines.append(
                    f"| `{pr['matchday_date']}` | `{pr['game_id']}` | **{pr['player_name']}** | {pr['prop_category']} | "
                    f"{pr['selection']} | `{float(pr['line_value']):.1f}` | `{float(pr['decimal_odds']):.2f}` | "
                    f"{stat_disp} | {b_badge} | **S/{float(pr.get('net_profit_pen') or 0.0):+.2f}** | `S/{float(pr.get('bankroll_after_pen') or 100.0):.2f}` |"
                )

    md_path = Path(md_output_path)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    html_path = md_path.parent / "reports" / "dashboard.html"
    generated_html = generate_interactive_html_dashboard(
        metrics=metrics,
        espn_real_bets=espn_real_bets,
        slate_items=slate_items,
        html_output_path=html_path,
        peru_str=peru_str,
        props_paper_trading=props_metrics,
    )

    # Keep docs/index.html in 100% lockstep for GitHub Pages deployment
    docs_path = md_path.parent / "docs" / "index.html"
    try:
        docs_path.parent.mkdir(parents=True, exist_ok=True)
        docs_path.write_text(generated_html, encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Failed to export docs/index.html: {exc}")

    return {"csv_path": str(csv_path), "md_path": str(md_path), "html_path": str(html_path)}
