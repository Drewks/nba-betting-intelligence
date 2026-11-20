---
date_generated: 2026-11-20T22:16:18Z
report_type: independent_audit_report
auditor_agent: nba_auditor
model_version_id: model_f_ensemble_v8
run_manifest_id: RUN_20261120T221609Z_36397AB1
commit_sha: 5f3fcc0bbc6e2c7cbf1facedeef4aa4ad74c6576
config_hash: f886c6d71a3ef7a20e249cf7cd759739a413b929eb3f097971a5effe2843eeec
final_verdict: REMAIN_IN_PAPER_TRADING
---
# Informe de Auditoría Independiente (`nba_auditor`)

## 1. Dictamen Ejecutivo
- **Fecha de auditoría (UTC)**: `2026-11-20T22:16:18Z`
- **Run Manifest / Versión activa**: `RUN_20261120T221609Z_36397AB1` (`model_f_ensemble_v8`, commit `5f3fcc0bbc6e`, config `f886c6d71a3e`)
- **Origen de Base de Datos (`DB Provenance`)**: PRODUCTION_STATE_LIVE (`live: origin/state-live:data/nba_intelligence.sqlite3` | `main: FROZEN_CI_BASELINE`)
- **Shadow Signal Ledger**: Total `180` señales +EV registradas (liquidadas `157`, ROI 1u `-16.58%`, CLV medio `-1.594%`; cero impacto en banca S/100) — evidencia de CLV: `INCONCLUSIVE` (n=`21` partidos / `40` señales, IC95 `[-3.18%, 0.761%]`; para detectar +1.0% hacen falta ~`148` partidos)
- **Dictamen sobre transición de fase**: **`REMAIN_IN_PAPER_TRADING`**
- **Transición automática a dinero real**: `False` (Deshabilitada permanentemente por diseño)
- **Integridad contable del bankroll virtual (S/100.00 PEN)**: `VERIFICADA` — Saldo liquidado observado: `S/97.20 PEN`
- **Violaciones de fuga temporal (Data Leakage) detectadas**: `0`
- **Inmutabilidad de predicciones y liquidaciones (Triggers SQLite)**: `ACTIVA Y VERIFICADA`
- **Integridad del historial (registro append-only de filas)**: `ÍNTEGRO` — faltantes por tabla: `{'predictions': 0, 'simulated_bets': 0, 'odds_snapshots': 0, 'decision_log': 0, 'player_prop_picks': 0, 'bankroll_ledger': 0, 'sniper_alerts': 0}`
- **Integridad de cuotas y timestamps de decisión**: `ÍNTEGRO` — cuotas copiadas entre partidos sin cuarentena: `0` (detectadas `24`); decisiones fechadas después de su ciclo: `0` (heredadas previas al arreglo: `337`)
- **Inconsistencias del ledger**: `0`
- **Reproducibilidad**: `VERIFIED_DETERMINISTIC (max_prob_diff=0.00e+00 <= 1e-12, weights_sha256=ab08be6b7a10, schema_sha256=69215bc1dc97)`

## 2. Evaluación de Puertas de Salida de Simulación (Sección 11)

| Puerta de Validación | Estado | Valor Observado | Criterio Requerido |
| :--- | :--- | :--- | :--- |
| `gate_1_min_500_settled_selections` | **FAIL (Permanece en Simulación)** | `35` | `>= 500` |
| `gate_2_multi_period_oos_evaluation` | **FAIL (Permanece en Simulación)** | `1` | `>= 2 temporal periods/seasons` |
| `gate_3_calibration_non_inferior_to_baseline` | **FAIL (Permanece en Simulación)** | `{'model_brier': 0.252526, 'baseline_brier': 0.251706, 'model_log_loss': 0.710031, 'baseline_log_loss': 0.697968}` | `model Brier <= baseline Brier AND model LogLoss <= baseline LogLoss` |
| `gate_4_zero_information_leakage` | **PASS** | `0` | `0` |
| `gate_5_positive_roi_and_yield` | **FAIL (Permanece en Simulación)** | `{'roi_pct': -5.86, 'yield_pct': -5.6459}` | `ROI > 0% and Yield > 0%` |
| `gate_6_statistical_uncertainty_excludes_zero_edge` | **FAIL (Permanece en Simulación)** | `{'ci_95_lower_pct': -37.3255, 'ci_95_upper_pct': 30.1653, 'compatible_with_zero_edge': True}` | `95% block bootstrap CI lower bound > 0%` |
| `gate_7_reproducible_results` | **PASS** | `True` | `True` |
| `gate_8_data_and_odds_integrity` | **PASS** | `0` | `0` |
| `gate_9_independent_audit_approved` | **FAIL (Permanece en Simulación)** | `False` | `True` |
| `gate_10_non_inferior_to_devigged_market` | **FAIL (Permanece en Simulación)** | `{'model_brier': 0.252526, 'market_brier': 0.239611, 'model_log_loss': 0.710031, 'market_log_loss': 0.671589, 'sample_size': 36}` | `model Brier/LogLoss <= de-vigged market Brier/LogLoss on the same games` |

## 3. Estado Real de Herramientas y Fuentes Inspeccionadas
- **Coordinador**: `Orchestrator Local (Ejecución secuencial verificada)`
- **Python & Entorno Virtual**: `CPython 3.12 (uv cloud/local runner)`
- **Fuente Primaria Activa sin Credenciales**: `ESPNPublicAdapter` (`site.api.espn.com` — Calendario, marcadores, estadísticas y cuotas pre-partido DraftKings)
- **Sportradar (`SportradarAdapter`)**: `CONFIGURED_RATE_LIMITED`
- **NBA.com/stats (`NBAStatsAdapter`)**: `FILTERED_BY_AKAMAI_TLS_WITHOUT_BROWSER_SESSION`
- **Playwright (`PlaywrightAuthorizedScraper`)**: `OPERATIONAL`
- **Política Scrapers Perú (`sources.peru_scraper_policy`)**: `PUBLIC_READONLY_JSON_API_NO_ANTIBOT_BYPASS`
- **PixelRAG (`visual_researcher`)**: `OPERATIONAL_NATIVE_TABULAR_RAG (BROWSERBASE_CLOUD_CDP, 124 docs indexed)`
- **Obsidian Vault (`NBA/`)**: `Operativo en /home/runner/work/nba-betting-intelligence/nba-betting-intelligence/NBA`

## 4. Conclusión Estadística del Auditor
- Con las predicciones calibradas actualmente registradas, el sistema aún no supera simultáneamente las puertas estadísticas de calibración (`gate_3` / `gate_10`); manteniendo trazabilidad contable del bankroll virtual de **S/100.00 PEN**, el sistema **`REMAIN_IN_PAPER_TRADING`** hasta superar las 10 puertas estadísticas (incluyendo >= **500 selecciones liquidadas** e IC 95% Block Bootstrap > 0%).
