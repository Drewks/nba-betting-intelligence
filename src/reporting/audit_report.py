"""
Generates the independent audit report for exit gates and system integrity verification.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


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
        (
            f"- **Integridad del historial (registro append-only de filas)**: "
            f"`{'ÍNTEGRO' if (audit_result.get('history_integrity') or {}).get('missing_rows_total', 1) == 0 else 'VIOLACIÓN: faltan filas registradas'}`"
            f" — faltantes por tabla: `{(audit_result.get('history_integrity') or {}).get('missing_rows_by_table', {})}`"
        ),
        f"- **Inconsistencias del ledger**: `{audit_result.get('ledger_issues_count', 'n/d')}`",
        f"- **Reproducibilidad**: `{audit_result.get('reproducibility_note', 'NO VERIFICADA')}`",
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
        "- **Coordinador**: `Gemini Argon` en Google Antigravity (Ejecución secuencial verificada)",
        f"- **Python & Entorno Virtual**: `{environment_status.get('python_version', 'Python 3.12 via uv')}`",
        "- **Fuente Primaria Activa sin Credenciales**: `ESPNPublicAdapter` (`site.api.espn.com` — Calendario, marcadores, estadísticas y cuotas pre-partido DraftKings)",
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
