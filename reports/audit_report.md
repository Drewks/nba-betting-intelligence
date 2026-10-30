---
date_generated: 2026-10-30T14:25:00Z
report_type: independent_audit_report
auditor_agent: nba_auditor
final_verdict: REMAIN_IN_PAPER_TRADING
---
# Informe de Auditoría Independiente (`nba_auditor`)

## 1. Dictamen Ejecutivo
- **Fecha de auditoría (UTC)**: `2026-10-30T14:25:00Z`
- **Dictamen sobre transición de fase**: **`REMAIN_IN_PAPER_TRADING`**
- **Transición automática a dinero real**: `False` (Deshabilitada permanentemente por diseño)
- **Integridad contable del bankroll virtual (S/100.00 PEN)**: `VERIFICADA`
- **Violaciones de fuga temporal (Data Leakage) detectadas**: `0`
- **Inmutabilidad de predicciones y liquidaciones (Triggers SQLite)**: `ACTIVA Y VERIFICADA`

## 2. Evaluación de Puertas de Salida de Simulación (Sección 11)

| Puerta de Validación | Estado | Valor Observado | Criterio Requerido |
| :--- | :--- | :--- | :--- |
| `gate_1_min_500_settled_selections` | **FAIL (Permanece en Simulación)** | `104` | `>= 500` |
| `gate_2_multi_period_oos_evaluation` | **PASS** | `2` | `>= 2 temporal periods/seasons` |
| `gate_3_calibration_non_inferior_to_baseline` | **PASS** | `{'model_brier': 0.244754, 'baseline_brier': 0.250121, 'model_log_loss': 0.68301, 'baseline_log_loss': 0.694905}` | `model Brier <= baseline Brier AND model LogLoss <= baseline LogLoss` |
| `gate_4_zero_information_leakage` | **PASS** | `0` | `0` |
| `gate_5_positive_roi_and_yield` | **PASS** | `{'roi_pct': 4.9471, 'yield_pct': 4.8084}` | `ROI > 0% and Yield > 0%` |
| `gate_6_statistical_uncertainty_excludes_zero_edge` | **FAIL (Permanece en Simulación)** | `{'ci_95_lower_pct': -19.0361, 'ci_95_upper_pct': 29.2899, 'compatible_with_zero_edge': True}` | `95% block bootstrap CI lower bound > 0%` |
| `gate_7_reproducible_results` | **PASS** | `True` | `True` |
| `gate_8_data_and_odds_integrity` | **PASS** | `0` | `0` |
| `gate_9_independent_audit_approved` | **PASS** | `True` | `True` |

## 3. Estado Real de Herramientas y Fuentes Inspeccionadas
- **Coordinador**: `Gemini Argon` en Google Antigravity (Ejecución secuencial verificada)
- **Python & Entorno Virtual**: `CPython 3.12 (uv cloud/local runner)`
- **Fuente Primaria Activa sin Credenciales**: `ESPNPublicAdapter` (`site.api.espn.com` — Calendario, marcadores, estadísticas y cuotas pre-partido DraftKings)
- **Sportradar (`SportradarAdapter`)**: `OPERATIONAL_LIVE_NBA_V8 (29 teams injuries + 30 teams tactical splits)`
- **NBA.com/stats (`NBAStatsAdapter`)**: `FILTERED_BY_AKAMAI_TLS_WITHOUT_BROWSER_SESSION`
- **Playwright (`PlaywrightAuthorizedScraper`)**: `OPERATIONAL`
- **PixelRAG (`visual_researcher`)**: `OPERATIONAL_NATIVE_TABULAR_RAG (PLAYWRIGHT_CHROMIUM_HEADLESS, 73 docs indexed)`
- **Obsidian Vault (`NBA/`)**: `Operativo en C:\Users\faboa\.gemini\antigravity\scratch\nba-betting-intelligence\NBA`

## 4. Conclusión Estadística del Auditor
- Aunque el motor cuantitativo supera al modelo Baseline (`Modelo A`) en `Brier Score` y `Log Loss` fuera de muestra y mantiene trazabilidad contable exacta sobre el bankroll virtual de **S/100.00 PEN**, el sistema **DEBE PERMANECER EN PAPER TRADING** hasta acumular al menos **500 selecciones liquidadas** fuera de muestra y confirmar que el límite inferior del intervalo de confianza (Block Bootstrap 95%) excluya el 0%.
