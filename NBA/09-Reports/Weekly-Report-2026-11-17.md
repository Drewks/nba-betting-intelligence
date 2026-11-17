---
date_generated: 2026-11-17T00:16:27Z
report_type: weekly_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
run_manifest_id: RUN_20261117T001616Z_69A41B54
settled_predictions: 31
observed_bankroll_pen: 96.03
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)
- **Fecha generada (UTC)**: `2026-11-17T00:16:27Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual actual liquidado**: `S/96.03 PEN` (`31` apuestas observadas liquidadas)
- **Beneficio neto acumulado**: `S/-3.97 PEN`
- **ROI acumulado**: `-9.45%`
- **Win Rate**: `48.39%` (`15G - 16P`)
- **Apuestas liquidadas**: `31`
- **CLV medio**: `-3.38%`
- **Tasa de batir la línea de cierre (Beat CLV %)**: `7.1%`
- **Ratio de Sharpe simulado (anualizado)**: `n/d`
- **Máximo Drawdown**: `9.00%` (Límite de alerta: `15.00%`)

## 2. Incertidumbre Estadística (Block Bootstrap 95% CI)
- **ROI 95% CI**: `[-46.95%, 28.86%]`
- **Win Rate 95% CI**: `[n/d%, n/d%]`
- **CLV 95% CI**: `[n/d%, n/d%]`
- **Brier Score 95% CI**: `[n/d, n/d]`
- **Interpretación**: `Muestra insuficiente para inferencia bootstrap concluyente.`

## 3. Calibración y Comparación de Modelos (Fuera de Muestra)
| Modelo / Fuente | Brier Score | Log Loss |
|---|---|---|
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.15641` | `0.47997` |
| Modelo A (Baseline Histórico) | `0.24479` | `0.68366` |
| Mercado Sin Margen (Muestra común) | `0.17040` | `0.51504` |
| Modelo sobre Muestra Común | `0.15641` | `0.47997` |
| baseline_naive_ml | `0.22726` | `0.64707` |
| ensemble_calibrated_ml | `0.07058` | `0.28268` |
| baseline_naive_totals | `0.26232` | `0.72026` |
| ensemble_calibrated_totals | `0.24223` | `0.67725` |
| ensemble_raw_ml | `0.17663` | `0.53031` |
| ensemble_calibrated_model_ml | `0.07058` | `0.28268` |
| ensemble_market_anchored_ml | `0.17231` | `0.52006` |
| ensemble_raw_totals | `0.26084` | `0.71570` |
| ensemble_calibrated_model_totals | `0.24223` | `0.67725` |
| ensemble_market_anchored_totals | `0.25510` | `0.70570` |
| ensemble_raw_spread | `0.22920` | `0.65135` |
| ensemble_calibrated_model_spread | `0.22920` | `0.65135` |
| market_devig_spread | `0.24596` | `0.68506` |
| ensemble_market_anchored_spread | `0.24057` | `0.67426` |
| market_devig_ml | `0.09045` | `0.33626` |
| market_devig_totals | `0.25034` | `0.69383` |
| common_subset_raw_ml | `0.06961` | `0.27970` |
| common_subset_raw_totals | `0.24108` | `0.67494` |
| common_subset_calibrated_model_ml | `0.07058` | `0.28268` |
| common_subset_calibrated_model_totals | `0.24223` | `0.67725` |
| common_subset_market_anchored_ml | `0.08308` | `0.31816` |
| common_subset_market_anchored_totals | `0.24729` | `0.68773` |
| common_subset_ensemble_ml | `0.07058` | `0.28268` |
| common_subset_ensemble_totals | `0.24223` | `0.67725` |

## 4. Desempeño por Mercado (Total: 31 Apuestas Observadas | Banca: S/96.03 PEN)
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `21` | `52.4%` | `S/-0.41` | `-1.40%` | `n/d%` | `n/d` |
| `total_points` | `10` | `40.0%` | `S/-3.56` | `-28.58%` | `n/d%` | `n/d` |
| `spread` | `0` | `0.0%` | `S/+0.00` | `+0.00%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `9` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
