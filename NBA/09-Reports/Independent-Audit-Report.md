---
date_generated: 2026-11-28T15:52:51Z
report_type: independent_audit_report
auditor_agent: nba_auditor
model_version_id: model_f_ensemble_v9
run_manifest_id: RUN_20261128T155240Z_51BB6A77
commit_sha: a72b834e04344d8c753dd27aae610907a7065a85
config_hash: 55ded746521566188d95daae92636ec70c00d75e32408e8036b53bda2289bebd
final_verdict: REMAIN_IN_PAPER_TRADING
---
# Informe de Auditoría Independiente (`nba_auditor`)

## 1. Dictamen Ejecutivo
- **Fecha de auditoría (UTC)**: `2026-11-28T15:52:51Z`
- **Run Manifest / Versión activa**: `RUN_20261128T155240Z_51BB6A77` (`model_f_ensemble_v9`, commit `a72b834e0434`, config `55ded7465215`)
- **Origen de Base de Datos (`DB Provenance`)**: PRODUCTION_STATE_LIVE (`live: origin/state-live:data/nba_intelligence.sqlite3.gz` | `main: FROZEN_CI_BASELINE`)
- **Shadow Signal Ledger**: Total `352` señales +EV registradas (liquidadas `343`, ROI 1u `-15.77%`, CLV medio `-2.434%`; cero impacto en banca S/100) — evidencia de CLV: `NO_EDGE` (n=`40` partidos / `69` señales, IC95 `[-3.539%, -0.684%]`; para detectar +1.0% hacen falta ~`157` partidos)
- **Dictamen sobre transición de fase**: **`REMAIN_IN_PAPER_TRADING`**
- **Transición automática a dinero real**: `False` (Deshabilitada permanentemente por diseño)
- **Integridad contable del bankroll virtual (S/100.00 PEN)**: `VERIFICADA` — Saldo liquidado observado: `S/96.80 PEN`
- **Violaciones de fuga temporal (Data Leakage) detectadas**: `0`
- **Inmutabilidad de predicciones y liquidaciones (Triggers SQLite)**: `ACTIVA Y VERIFICADA`
- **Integridad del historial (registro append-only de filas)**: `ÍNTEGRO` — faltantes por tabla: `{'predictions': 0, 'simulated_bets': 0, 'odds_snapshots': 0, 'decision_log': 0, 'player_prop_picks': 0, 'bankroll_ledger': 0, 'sniper_alerts': 0}`
- **Integridad de cuotas y timestamps de decisión**: `ÍNTEGRO` — cuotas copiadas entre partidos sin cuarentena: `0` (detectadas `24`); decisiones fechadas después de su ciclo: `0` (heredadas previas al arreglo: `337`)
- **Integridad temporal de ingestión**: `ÍNTEGRO` — partidos ingeridos tras el tip-off con `features_available_at` previo al tip-off sin reparación auditada: `0` (registrados en `audit_repairs`: `131`); cuotas con `captured_at` anterior a su descarga sin registro y cuarentena: `0` (detectadas `12`, cierres `6`); triggers de congelamiento temporal: `ACTIVOS`
- **Inconsistencias del ledger**: `0`
- **Reproducibilidad**: `VERIFIED_DETERMINISTIC (max_prob_diff=0.00e+00 <= 1e-12, weights_sha256=ab08be6b7a10, schema_sha256=969476e727ed)`

## 2. Evaluación de Puertas de Salida de Simulación (Sección 11)

| Puerta de Validación | Estado | Valor Observado | Criterio Requerido |
| :--- | :--- | :--- | :--- |
| `gate_1_min_500_settled_selections` | **FAIL (Permanece en Simulación)** | `40` | `>= 500` |
| `gate_2_multi_period_oos_evaluation` | **FAIL (Permanece en Simulación)** | `1` | `>= 2 temporal periods/seasons` |
| `gate_3_calibration_non_inferior_to_baseline` | **PASS** | `{'model_brier': 0.224862, 'baseline_brier': 0.272919, 'model_log_loss': 0.638342, 'baseline_log_loss': 0.741321}` | `model Brier <= baseline Brier AND model LogLoss <= baseline LogLoss` |
| `gate_4_zero_information_leakage` | **PASS** | `0` | `0` |
| `gate_5_positive_roi_and_yield` | **FAIL (Permanece en Simulación)** | `{'roi_pct': -5.7389, 'yield_pct': -5.7389}` | `ROI > 0% and Yield > 0%` |
| `gate_6_statistical_uncertainty_excludes_zero_edge` | **FAIL (Permanece en Simulación)** | `{'ci_95_lower_pct': -36.2719, 'ci_95_upper_pct': 26.199, 'compatible_with_zero_edge': True}` | `95% block bootstrap CI lower bound > 0%` |
| `gate_7_reproducible_results` | **PASS** | `True` | `True` |
| `gate_8_data_and_odds_integrity` | **PASS** | `0` | `0` |
| `gate_9_independent_audit_approved` | **PASS** | `True` | `True` |
| `gate_10_non_inferior_to_devigged_market` | **PASS** | `{'model_brier': 0.224862, 'market_brier': 0.228071, 'model_log_loss': 0.638342, 'market_log_loss': 0.645928, 'sample_size': 10}` | `model Brier/LogLoss <= de-vigged market Brier/LogLoss on the same games` |

## 3. Estado Real de Herramientas y Fuentes Inspeccionadas
- **Coordinador**: `Orchestrator Local (Ejecución secuencial verificada)`
- **Python & Entorno Virtual**: `CPython 3.12 (uv cloud/local runner)`
- **Fuente Primaria Activa sin Credenciales**: `ESPNPublicAdapter` (`site.api.espn.com` — Calendario, marcadores, estadísticas y cuotas pre-partido DraftKings)
- **Sportradar (`SportradarAdapter`)**: `OPERATIONAL_LIVE_NBA_V8 (97 injury docs + 30 teams tactical splits)`
- **NBA.com/stats (`NBAStatsAdapter`)**: `FILTERED_BY_AKAMAI_TLS_WITHOUT_BROWSER_SESSION`
- **Playwright (`PlaywrightAuthorizedScraper`)**: `READY_FOR_BROWSER_INSTALL`
- **Política Scrapers Perú (`sources.peru_scraper_policy`)**: `PUBLIC_READONLY_JSON_API_NO_ANTIBOT_BYPASS`
- **PixelRAG (`visual_researcher`)**: `OPERATIONAL_NATIVE_TABULAR_RAG (BROWSERBASE_CLOUD_CDP, 123 docs indexed)`
- **Obsidian Vault (`NBA/`)**: `Operativo en /home/runner/work/nba-betting-intelligence/nba-betting-intelligence/NBA`

## 4. Conclusión Estadística del Auditor
- Aunque el motor calibrado supera al modelo Baseline (`Modelo A`) y es no-inferior al mercado sin margen en la muestra común observada (`gate_3` y `gate_10` aprobadas); manteniendo trazabilidad contable del bankroll virtual de **S/100.00 PEN**, el sistema **`REMAIN_IN_PAPER_TRADING`** hasta superar las 10 puertas estadísticas (incluyendo >= **500 selecciones liquidadas** e IC 95% Block Bootstrap > 0%).
