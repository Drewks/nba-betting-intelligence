---
date_generated: 2026-11-21T04:15:57Z
report_type: weekly_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
run_manifest_id: RUN_20261121T041549Z_BE138C0C
settled_predictions: 36
observed_bankroll_pen: 98.03
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)
- **Fecha generada (UTC)**: `2026-11-21T04:15:57Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual actual liquidado**: `S/98.03 PEN` (`36` apuestas observadas liquidadas)
- **Beneficio neto acumulado**: `S/-1.97 PEN`
- **ROI acumulado**: `-3.98%`
- **Win Rate**: `52.78%` (`19G - 17P`)
- **Apuestas liquidadas**: `36`
- **CLV medio**: `-2.79%`
- **Tasa de batir la línea de cierre (Beat CLV %)**: `18.8%`
- **Ratio de Sharpe simulado (anualizado)**: `n/d`
- **Máximo Drawdown**: `9.00%` (Límite de alerta: `15.00%`)

## 2. Incertidumbre Estadística (Block Bootstrap 95% CI)
- **ROI 95% CI**: `[-36.39%, 32.25%]`
- **Win Rate 95% CI**: `[n/d%, n/d%]`
- **CLV 95% CI**: `[n/d%, n/d%]`
- **Brier Score 95% CI**: `[n/d, n/d]`
- **Interpretación**: `Muestra insuficiente para inferencia bootstrap concluyente.`

## 3. Calibración y Comparación de Modelos (Fuera de Muestra)
| Modelo / Fuente | Brier Score | Log Loss |
|---|---|---|
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.25285` | `0.70830` |
| Modelo A (Baseline Histórico) | `0.25281` | `0.70037` |
| Mercado Sin Margen (Muestra común) | `0.23659` | `0.66479` |
| Modelo sobre Muestra Común | `0.25285` | `0.70830` |
| baseline_naive_ml | `0.23407` | `0.66090` |
| ensemble_calibrated_ml | `0.23787` | `0.68711` |
| baseline_naive_totals | `0.27155` | `0.73984` |
| ensemble_calibrated_totals | `0.26783` | `0.72950` |
| ensemble_raw_ml | `0.20265` | `0.59591` |
| ensemble_calibrated_model_ml | `0.23787` | `0.68711` |
| ensemble_market_anchored_ml | `0.19421` | `0.57092` |
| ensemble_raw_totals | `0.26446` | `0.72297` |
| ensemble_calibrated_model_totals | `0.26783` | `0.72950` |
| ensemble_market_anchored_totals | `0.25571` | `0.70636` |
| ensemble_raw_spread | `0.24792` | `0.68910` |
| ensemble_calibrated_model_spread | `0.24760` | `0.68844` |
| market_devig_spread | `0.24908` | `0.69130` |
| ensemble_market_anchored_spread | `0.24599` | `0.68511` |
| market_devig_ml | `0.22220` | `0.63446` |
| market_devig_totals | `0.25099` | `0.69512` |
| common_subset_raw_ml | `0.23921` | `0.69215` |
| common_subset_raw_totals | `0.26849` | `0.73085` |
| common_subset_calibrated_model_ml | `0.23787` | `0.68711` |
| common_subset_calibrated_model_totals | `0.26783` | `0.72950` |
| common_subset_market_anchored_ml | `0.22514` | `0.64391` |
| common_subset_market_anchored_totals | `0.25542` | `0.70401` |
| common_subset_ensemble_ml | `0.23787` | `0.68711` |
| common_subset_ensemble_totals | `0.26783` | `0.72950` |

## 4. Desempeño por Mercado (Total: 36 Apuestas Observadas | Banca: S/98.03 PEN)
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `24` | `58.3%` | `S/+1.80` | `+5.20%` | `n/d%` | `n/d` |
| `total_points` | `12` | `41.7%` | `S/-3.77` | `-25.32%` | `n/d%` | `n/d` |
| `spread` | `0` | `0.0%` | `S/+0.00` | `+0.00%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `42` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `False`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
