---
date_generated: 2026-11-13T21:25:07Z
report_type: independent_audit_report
auditor_agent: nba_auditor
final_verdict: REMAIN_IN_PAPER_TRADING
---
# Informe de Auditoría Independiente (`nba_auditor`)

## 1. Dictamen Ejecutivo
- **Fecha de auditoría (UTC)**: `2026-11-13T21:25:07Z`
- **Dictamen sobre transición de fase**: **`REMAIN_IN_PAPER_TRADING`**
- **Transición automática a dinero real**: `False` (Deshabilitada permanentemente por diseño)
- **Integridad contable del bankroll virtual (S/100.00 PEN)**: `VERIFICADA`
- **Violaciones de fuga temporal (Data Leakage) detectadas**: `0`
- **Inmutabilidad de predicciones y liquidaciones (Triggers SQLite)**: `ACTIVA Y VERIFICADA`
- **Integridad del historial (registro append-only de filas)**: `ÍNTEGRO` — faltantes por tabla: `{'predictions': 0, 'simulated_bets': 0, 'odds_snapshots': 0, 'decision_log': 0, 'player_prop_picks': 0, 'bankroll_ledger': 0, 'sniper_alerts': 0}`
- **Inconsistencias del ledger**: `0`
- **Reproducibilidad**: `NOT_VERIFIED_IN_PRODUCTION_CYCLE (requires deterministic re-run)`

## 2. Evaluación de Puertas de Salida de Simulación (Sección 11)

| Puerta de Validación | Estado | Valor Observado | Criterio Requerido |
| :--- | :--- | :--- | :--- |
| `gate_1_min_500_settled_selections` | **FAIL (Permanece en Simulación)** | `28` | `>= 500` |
| `gate_2_multi_period_oos_evaluation` | **FAIL (Permanece en Simulación)** | `1` | `>= 2 temporal periods/seasons` |
| `gate_3_calibration_non_inferior_to_baseline` | **PASS** | `{'model_brier': 0.216116, 'baseline_brier': 0.25043, 'model_log_loss': 0.618878, 'baseline_log_loss': 0.695707}` | `model Brier <= baseline Brier AND model LogLoss <= baseline LogLoss` |
| `gate_4_zero_information_leakage` | **PASS** | `0` | `0` |
| `gate_5_positive_roi_and_yield` | **FAIL (Permanece en Simulación)** | `{'roi_pct': -17.209, 'yield_pct': -17.209}` | `ROI > 0% and Yield > 0%` |
| `gate_6_statistical_uncertainty_excludes_zero_edge` | **FAIL (Permanece en Simulación)** | `{'ci_95_lower_pct': -55.1016, 'ci_95_upper_pct': 25.2771, 'compatible_with_zero_edge': True}` | `95% block bootstrap CI lower bound > 0%` |
| `gate_7_reproducible_results` | **FAIL (Permanece en Simulación)** | `False` | `True` |
| `gate_8_data_and_odds_integrity` | **PASS** | `0` | `0` |
| `gate_9_independent_audit_approved` | **FAIL (Permanece en Simulación)** | `False` | `True` |
| `gate_10_non_inferior_to_devigged_market` | **FAIL (Permanece en Simulación)** | `{'model_brier': 0.216116, 'market_brier': 0.213172, 'model_log_loss': 0.618878, 'market_log_loss': 0.611473, 'sample_size': 87}` | `model Brier/LogLoss <= de-vigged market Brier/LogLoss on the same games` |

## 3. Estado Real de Herramientas y Fuentes Inspeccionadas
- **Coordinador**: `Gemini Argon` en Google Antigravity (Ejecución secuencial verificada)
- **Python & Entorno Virtual**: `CPython 3.12 (uv cloud/local runner)`
- **Fuente Primaria Activa sin Credenciales**: `ESPNPublicAdapter` (`site.api.espn.com` — Calendario, marcadores, estadísticas y cuotas pre-partido DraftKings)
- **Sportradar (`SportradarAdapter`)**: `CONFIGURED_RATE_LIMITED`
- **NBA.com/stats (`NBAStatsAdapter`)**: `FILTERED_BY_AKAMAI_TLS_WITHOUT_BROWSER_SESSION`
- **Playwright (`PlaywrightAuthorizedScraper`)**: `OPERATIONAL`
- **PixelRAG (`visual_researcher`)**: `OPERATIONAL_NATIVE_TABULAR_RAG (BROWSERBASE_CLOUD_CDP, 123 docs indexed)`
- **Obsidian Vault (`NBA/`)**: `Operativo en /home/runner/work/nba-betting-intelligence/nba-betting-intelligence/NBA`

## 4. Conclusión Estadística del Auditor
- Aunque el motor cuantitativo supera al modelo Baseline (`Modelo A`) en `Brier Score` y `Log Loss` fuera de muestra y mantiene trazabilidad contable exacta sobre el bankroll virtual de **S/100.00 PEN**, el sistema **DEBE PERMANECER EN PAPER TRADING** hasta acumular al menos **500 selecciones liquidadas** fuera de muestra y confirmar que el límite inferior del intervalo de confianza (Block Bootstrap 95%) excluya el 0%.
