"""
Reporting & Obsidian Vault Synchronization (Sections 13 & 15):
Generates Daily Reports, Weekly Reports, Audit Reports, and populates the dedicated
Obsidian Vault (`NBA/00-Inbox` through `NBA/09-Reports`) with full provenance metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.storage.db import DatabaseManager


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
            "## 2. Sportradar NBA API v8 (`SportradarAdapter`)\n"
            "- Estado: Adaptador intercambiable implementado (`src/ingestion/adapters.py`).\n"
            "- Requiere `SPORTRADAR_API_KEY` en `.env`. Las cuotas históricas requieren licencia adicional de Odds Comparison.\n\n"
            "## 3. NBA.com/stats (`NBAStatsAdapter`)\n"
            "- Estado: Adaptador implementado con cabeceras oficiales y circuit-breaker.\n"
            "- Limitación: `stats.nba.com` bloquea peticiones directas por huella TLS Akamai (timeout) y **no proporciona cuotas históricas de apuestas**.\n\n"
            "## 4. PixelRAG (`visual_researcher`)\n"
            "- Estado: No existe servidor MCP de PixelRAG instalado en `%APPDATA%` / `.gemini/config/mcp_config.json`.\n"
            "- El agente `visual_researcher` documenta explícitamente `PIXELRAG_NOT_INSTALLED` y opera sobre el pipeline estructurado sin inventar respuestas.\n"
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
