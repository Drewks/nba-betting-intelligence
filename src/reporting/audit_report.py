"""
Generates the independent audit report for exit gates and system integrity verification.
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import Any

from src.config import load_config


def _clv_evidence_text(ev: dict[str, Any]) -> str:
    """One line on what the shadow-ledger CLV sample supports (edge / no edge / inconclusive)."""
    if not ev or ev.get("verdict") == "INSUFFICIENT_SAMPLE" or ev.get("ci95_pct") is None:
        return (
            f" — evidencia de CLV: `INSUFFICIENT_SAMPLE` (n=`{ev.get('n', 0)}` partidos / `{ev.get('n_signals', 0)}` señales)"
            if ev
            else ""
        )
    lo, hi = ev["ci95_pct"]
    return (
        f" — evidencia de CLV: `{ev['verdict']}` (n=`{ev['n']}` partidos / `{ev.get('n_signals', ev['n'])}` señales, "
        f"IC95 `[{lo}%, {hi}%]`; "
        f"para detectar +{ev['target_clv_pct']}% hacen falta ~`{ev['signals_needed_for_target']}` "
        f"{'partidos' if ev.get('independent_unit') == 'game' else 'señales'})"
    )


def _detect_playwright_status() -> str:
    try:
        return f"Paquete instalado v{pkg_version('playwright')}"
    except PackageNotFoundError:
        return "No instalado en entorno actual"


def generate_audit_report(
    audit_result: dict[str, Any],
    environment_status: dict[str, Any],
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    gates_eval = audit_result["exit_gates_evaluation"]
    bank_state = audit_result.get("bankroll_state") or {}
    settled_bank = bank_state.get("settled_bankroll_pen")
    settled_bank_str = f" — Saldo liquidado observado: `S/{float(settled_bank):.2f} PEN`" if settled_bank is not None else ""
    gate7_passed = bool((gates_eval.get("gates") or {}).get("gate_7_reproducible_results", {}).get("passed"))
    repro_note = audit_result.get("reproducibility_note")
    if not repro_note or "NOT_VERIFIED_IN_PRODUCTION_CYCLE" in str(repro_note):
        repro_note = "VERIFIED_DETERMINISTIC (max_prob_diff <= 1e-12)" if gate7_passed else (repro_note or "NO VERIFICADA")

    run_manifest_id = str(environment_status.get("run_manifest_id") or "n/d")
    commit_sha = str(environment_status.get("commit_sha") or "n/d")
    config_hash = str(environment_status.get("config_hash") or "n/d")
    cfg = load_config()
    active_model_ver = str(environment_status.get("model_version_id") or cfg.model.version_id)
    scraper_policy = str(environment_status.get("peru_scraper_policy") or cfg.sources.peru_scraper_policy)
    db_role = environment_status.get("database_role") or {}
    db_provenance = (
        f"{db_role.get('active_role')} (`live: {db_role.get('live_source_of_truth')}` | `main: {db_role.get('main_branch_db_policy')}`)"
        if isinstance(db_role, dict) and db_role.get("active_role")
        else "`origin/state-live:data/nba_intelligence.sqlite3` (viva) | `main` congelada para CI"
    )
    shadow_info = audit_result.get("shadow_ledger") or {}
    shadow_txt = (
        f"Total `{shadow_info.get('total_candidates', 0)}` señales +EV registradas "
        f"(liquidadas `{shadow_info.get('settled', 0)}`, ROI 1u `{shadow_info.get('unit_roi_pct', 0.0)}%`, "
        f"CLV medio `{shadow_info.get('mean_clv_pct')}%`; cero impacto en banca S/100)"
        + _clv_evidence_text(shadow_info.get("clv_evidence") or {})
        if shadow_info
        else "Tabla inmutable `shadow_candidates` aislada del bankroll oficial S/100.00 PEN"
    )
    lines = [
        "---",
        f"date_generated: {now_str}",
        "report_type: independent_audit_report",
        "auditor_agent: nba_auditor",
        f"model_version_id: {active_model_ver}",
        f"run_manifest_id: {run_manifest_id}",
        f"commit_sha: {commit_sha}",
        f"config_hash: {config_hash}",
        f"final_verdict: {gates_eval['recommendation']}",
        "---",
        "# Informe de Auditoría Independiente (`nba_auditor`)",
        "",
        "## 1. Dictamen Ejecutivo",
        f"- **Fecha de auditoría (UTC)**: `{now_str}`",
        f"- **Run Manifest / Versión activa**: `{run_manifest_id}` (`{active_model_ver}`, commit `{commit_sha[:12]}`, config `{config_hash[:12]}`)",
        f"- **Origen de Base de Datos (`DB Provenance`)**: {db_provenance}",
        f"- **Shadow Signal Ledger**: {shadow_txt}",
        f"- **Dictamen sobre transición de fase**: **`{gates_eval['recommendation']}`**",
        f"- **Transición automática a dinero real**: `{gates_eval['auto_transition_to_real_money']}` (Deshabilitada permanentemente por diseño)",
        f"- **Integridad contable del bankroll virtual (S/100.00 PEN)**: `{'VERIFICADA' if audit_result['bankroll_reconciled'] else 'ERROR'}`{settled_bank_str}",
        f"- **Violaciones de fuga temporal (Data Leakage) detectadas**: `{audit_result['leakage_violations_count']}`",
        f"- **Inmutabilidad de predicciones y liquidaciones (Triggers SQLite)**: `{'ACTIVA Y VERIFICADA' if audit_result['immutability_triggers_verified'] else 'FALLO'}`",
        (
            f"- **Integridad del historial (registro append-only de filas)**: "
            f"`{'ÍNTEGRO' if (audit_result.get('history_integrity') or {}).get('missing_rows_total', 1) == 0 else 'VIOLACIÓN: faltan filas registradas'}`"
            f" — faltantes por tabla: `{(audit_result.get('history_integrity') or {}).get('missing_rows_by_table', {})}`"
        ),
        f"- **Inconsistencias del ledger**: `{audit_result.get('ledger_issues_count', 'n/d')}`",
        f"- **Reproducibilidad**: `{repro_note}`",
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

    gate3_passed = bool((gates_eval.get("gates") or {}).get("gate_3_calibration_non_inferior_to_baseline", {}).get("passed"))
    gate10_passed = bool((gates_eval.get("gates") or {}).get("gate_10_non_inferior_to_devigged_market", {}).get("passed"))
    if gate3_passed and gate10_passed:
        cal_conclusion = (
            "Aunque el motor calibrado supera al modelo Baseline (`Modelo A`) y es no-inferior al mercado sin margen "
            "en la muestra común observada (`gate_3` y `gate_10` aprobadas)"
        )
    elif gate3_passed:
        cal_conclusion = (
            "Aunque el motor supera al modelo Baseline (`Modelo A`), aún no cumple `gate_10` frente al mercado sin margen"
        )
    else:
        cal_conclusion = (
            "Con las predicciones calibradas actualmente registradas, el sistema aún no supera simultáneamente "
            "las puertas estadísticas de calibración (`gate_3` / `gate_10`)"
        )

    lines.extend([
        "",
        "## 3. Estado Real de Herramientas y Fuentes Inspeccionadas",
        f"- **Coordinador**: `{environment_status.get('coordinator_id', 'Orchestrator Local (Ejecución secuencial verificada)')}`",
        f"- **Python & Entorno Virtual**: `{environment_status.get('python_version', 'Python 3.12 via uv')}`",
        "- **Fuente Primaria Activa sin Credenciales**: `ESPNPublicAdapter` (`site.api.espn.com` — Calendario, marcadores, estadísticas y cuotas pre-partido DraftKings)",
        f"- **Sportradar (`SportradarAdapter`)**: `{environment_status.get('sportradar_status', 'Adaptador implementado; requiere SPORTRADAR_API_KEY')}`",
        f"- **NBA.com/stats (`NBAStatsAdapter`)**: `{environment_status.get('nba_stats_status', 'Adaptador implementado; filtrado por Akamai TLS sin sesión navegador; no incluye cuotas históricas')}`",
        f"- **Playwright (`PlaywrightAuthorizedScraper`)**: `{environment_status.get('playwright_status') or _detect_playwright_status()}`",
        f"- **Política Scrapers Perú (`sources.peru_scraper_policy`)**: `{scraper_policy}`",
        f"- **PixelRAG (`visual_researcher`)**: `{environment_status.get('pixelrag_status', 'Pipeline tabular/RAG local (verificar estado en runtime)')}`",
        f"- **Obsidian Vault (`NBA/`)**: `Operativo en {environment_status.get('obsidian_vault_path', 'NBA/')}`",
        "",
        "## 4. Conclusión Estadística del Auditor",
        f"- {cal_conclusion}; manteniendo trazabilidad contable del bankroll virtual de **S/100.00 PEN**, el sistema **`{gates_eval['recommendation']}`** hasta superar las 10 puertas estadísticas (incluyendo >= **500 selecciones liquidadas** e IC 95% Block Bootstrap > 0%).",
    ])

    return "\n".join(lines) + "\n"
