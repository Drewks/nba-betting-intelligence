---
date_generated: 2026-11-18T16:02:02Z
report_type: weekly_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
run_manifest_id: RUN_20261118T160148Z_F5923B8F
settled_predictions: 33
observed_bankroll_pen: 97.91
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)
- **Fecha generada (UTC)**: `2026-11-18T16:02:02Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual actual liquidado**: `S/97.91 PEN` (`33` apuestas observadas liquidadas)
- **Beneficio neto acumulado**: `S/-2.09 PEN`
- **ROI acumulado**: `-4.65%`
- **Win Rate**: `51.52%` (`17G - 16P`)
- **Apuestas liquidadas**: `33`
- **CLV medio**: `-3.08%`
- **Tasa de batir la línea de cierre (Beat CLV %)**: `17.2%`
- **Ratio de Sharpe simulado (anualizado)**: `n/d`
- **Máximo Drawdown**: `9.00%` (Límite de alerta: `15.00%`)

## 2. Incertidumbre Estadística (Block Bootstrap 95% CI)
- **ROI 95% CI**: `[-40.22%, 30.57%]`
- **Win Rate 95% CI**: `[n/d%, n/d%]`
- **CLV 95% CI**: `[n/d%, n/d%]`
- **Brier Score 95% CI**: `[n/d, n/d]`
- **Interpretación**: `Muestra insuficiente para inferencia bootstrap concluyente.`

## 3. Calibración y Comparación de Modelos (Fuera de Muestra)
| Modelo / Fuente | Brier Score | Log Loss |
|---|---|---|
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.23680` | `0.67140` |
| Modelo A (Baseline Histórico) | `0.24715` | `0.68846` |
| Mercado Sin Margen (Muestra común) | `0.23808` | `0.66937` |
| Modelo sobre Muestra Común | `0.23680` | `0.67140` |
| baseline_naive_ml | `0.23077` | `0.65419` |
| ensemble_calibrated_ml | `0.22300` | `0.64810` |
| baseline_naive_totals | `0.26354` | `0.72273` |
| ensemble_calibrated_totals | `0.25060` | `0.69471` |
| ensemble_raw_ml | `0.19302` | `0.57041` |
| ensemble_calibrated_model_ml | `0.22300` | `0.64810` |
| ensemble_market_anchored_ml | `0.18796` | `0.55638` |
| ensemble_raw_totals | `0.26059` | `0.71520` |
| ensemble_calibrated_model_totals | `0.25060` | `0.69471` |
| ensemble_market_anchored_totals | `0.25471` | `0.70469` |
| ensemble_raw_spread | `0.24016` | `0.67337` |
| ensemble_calibrated_model_spread | `0.23997` | `0.67296` |
| market_devig_spread | `0.24912` | `0.69138` |
| ensemble_market_anchored_spread | `0.24435` | `0.68183` |
| market_devig_ml | `0.22532` | `0.64394` |
| market_devig_totals | `0.25083` | `0.69480` |
| common_subset_raw_ml | `0.22355` | `0.65012` |
| common_subset_raw_totals | `0.25049` | `0.69449` |
| common_subset_calibrated_model_ml | `0.22300` | `0.64810` |
| common_subset_calibrated_model_totals | `0.25060` | `0.69471` |
| common_subset_market_anchored_ml | `0.22293` | `0.63985` |
| common_subset_market_anchored_totals | `0.24932` | `0.69179` |
| common_subset_ensemble_ml | `0.22300` | `0.64810` |
| common_subset_ensemble_totals | `0.25060` | `0.69471` |

## 4. Desempeño por Mercado (Total: 33 Apuestas Observadas | Banca: S/97.91 PEN)
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `22` | `54.5%` | `S/+0.37` | `+1.19%` | `n/d%` | `n/d` |
| `total_points` | `11` | `45.5%` | `S/-2.46` | `-18.12%` | `n/d%` | `n/d` |
| `spread` | `0` | `0.0%` | `S/+0.00` | `+0.00%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `20` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
