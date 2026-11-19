---
date_generated: 2026-11-19T03:23:18Z
report_type: weekly_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
run_manifest_id: RUN_20261119T032309Z_83164EA0
settled_predictions: 34
observed_bankroll_pen: 98.51
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)
- **Fecha generada (UTC)**: `2026-11-19T03:23:18Z`
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
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.25681` | `0.71092` |
| Modelo A (Baseline Histórico) | `0.25008` | `0.69448` |
| Mercado Sin Margen (Muestra común) | `0.24501` | `0.68237` |
| Modelo sobre Muestra Común | `0.25681` | `0.71092` |
| baseline_naive_ml | `0.23234` | `0.65727` |
| ensemble_calibrated_ml | `0.24782` | `0.69637` |
| baseline_naive_totals | `0.26781` | `0.73169` |
| ensemble_calibrated_totals | `0.26580` | `0.72546` |
| ensemble_raw_ml | `0.20036` | `0.58597` |
| ensemble_calibrated_model_ml | `0.24782` | `0.69637` |
| ensemble_market_anchored_ml | `0.19367` | `0.56823` |
| ensemble_raw_totals | `0.26377` | `0.72163` |
| ensemble_calibrated_model_totals | `0.26580` | `0.72546` |
| ensemble_market_anchored_totals | `0.25568` | `0.70651` |
| ensemble_raw_spread | `0.24042` | `0.67392` |
| ensemble_calibrated_model_spread | `0.24029` | `0.67365` |
| market_devig_spread | `0.24937` | `0.69188` |
| ensemble_market_anchored_spread | `0.24410` | `0.68134` |
| market_devig_ml | `0.23901` | `0.66958` |
| market_devig_totals | `0.25100` | `0.69516` |
| common_subset_raw_ml | `0.24906` | `0.70034` |
| common_subset_raw_totals | `0.26759` | `0.72912` |
| common_subset_calibrated_model_ml | `0.24782` | `0.69637` |
| common_subset_calibrated_model_totals | `0.26580` | `0.72546` |
| common_subset_market_anchored_ml | `0.23985` | `0.67219` |
| common_subset_market_anchored_totals | `0.25512` | `0.70342` |
| common_subset_ensemble_ml | `0.24782` | `0.69637` |
| common_subset_ensemble_totals | `0.26580` | `0.72546` |

## 4. Desempeño por Mercado (Total: 34 Apuestas Observadas | Banca: S/98.51 PEN)
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `23` | `56.5%` | `S/+0.97` | `+2.97%` | `n/d%` | `n/d` |
| `total_points` | `11` | `45.5%` | `S/-2.46` | `-18.12%` | `n/d%` | `n/d` |
| `spread` | `0` | `0.0%` | `S/+0.00` | `+0.00%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `27` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `False`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
