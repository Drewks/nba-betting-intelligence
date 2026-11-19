---
date_generated: 2026-11-19T04:29:27Z
report_type: weekly_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
run_manifest_id: RUN_20261119T042919Z_48D47DC1
settled_predictions: 34
observed_bankroll_pen: 98.51
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)
- **Fecha generada (UTC)**: `2026-11-19T04:29:27Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual actual liquidado**: `S/98.51 PEN` (`34` apuestas observadas liquidadas)
- **Beneficio neto acumulado**: `S/-1.49 PEN`
- **ROI acumulado**: `-3.20%`
- **Win Rate**: `52.94%` (`18G - 16P`)
- **Apuestas liquidadas**: `34`
- **CLV medio**: `-2.80%`
- **Tasa de batir la línea de cierre (Beat CLV %)**: `20.0%`
- **Ratio de Sharpe simulado (anualizado)**: `n/d`
- **Máximo Drawdown**: `9.00%` (Límite de alerta: `15.00%`)

## 2. Incertidumbre Estadística (Block Bootstrap 95% CI)
- **ROI 95% CI**: `[-37.75%, 33.23%]`
- **Win Rate 95% CI**: `[n/d%, n/d%]`
- **CLV 95% CI**: `[n/d%, n/d%]`
- **Brier Score 95% CI**: `[n/d, n/d]`
- **Interpretación**: `Muestra insuficiente para inferencia bootstrap concluyente.`

## 3. Calibración y Comparación de Modelos (Fuera de Muestra)
| Modelo / Fuente | Brier Score | Log Loss |
|---|---|---|
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.25257` | `0.70192` |
| Modelo A (Baseline Histórico) | `0.25003` | `0.69437` |
| Mercado Sin Margen (Muestra común) | `0.24135` | `0.67495` |
| Modelo sobre Muestra Común | `0.25257` | `0.70192` |
| baseline_naive_ml | `0.23250` | `0.65759` |
| ensemble_calibrated_ml | `0.24154` | `0.68284` |
| baseline_naive_totals | `0.26757` | `0.73115` |
| ensemble_calibrated_totals | `0.26360` | `0.72100` |
| ensemble_raw_ml | `0.19968` | `0.58459` |
| ensemble_calibrated_model_ml | `0.24154` | `0.68284` |
| ensemble_market_anchored_ml | `0.19279` | `0.56659` |
| ensemble_raw_totals | `0.26326` | `0.72059` |
| ensemble_calibrated_model_totals | `0.26360` | `0.72100` |
| ensemble_market_anchored_totals | `0.25546` | `0.70605` |
| ensemble_raw_spread | `0.24463` | `0.68249` |
| ensemble_calibrated_model_spread | `0.24437` | `0.68195` |
| market_devig_spread | `0.24941` | `0.69197` |
| ensemble_market_anchored_spread | `0.24544` | `0.68400` |
| market_devig_ml | `0.23201` | `0.65536` |
| market_devig_totals | `0.25070` | `0.69454` |
| common_subset_raw_ml | `0.24276` | `0.68651` |
| common_subset_raw_totals | `0.26512` | `0.72413` |
| common_subset_calibrated_model_ml | `0.24154` | `0.68284` |
| common_subset_calibrated_model_totals | `0.26360` | `0.72100` |
| common_subset_market_anchored_ml | `0.23288` | `0.65797` |
| common_subset_market_anchored_totals | `0.25424` | `0.70165` |
| common_subset_ensemble_ml | `0.24154` | `0.68284` |
| common_subset_ensemble_totals | `0.26360` | `0.72100` |

## 4. Desempeño por Mercado (Total: 34 Apuestas Observadas | Banca: S/98.51 PEN)
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `23` | `56.5%` | `S/+0.97` | `+2.97%` | `n/d%` | `n/d` |
| `total_points` | `11` | `45.5%` | `S/-2.46` | `-18.12%` | `n/d%` | `n/d` |
| `spread` | `0` | `0.0%` | `S/+0.00` | `+0.00%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `29` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `False`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
