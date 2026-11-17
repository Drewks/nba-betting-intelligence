---
date_generated: 2026-11-17T04:30:05Z
report_type: weekly_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
run_manifest_id: RUN_20261117T042951Z_54906000
settled_predictions: 33
observed_bankroll_pen: 97.91
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)
- **Fecha generada (UTC)**: `2026-11-17T04:30:05Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual actual liquidado**: `S/97.91 PEN` (`33` apuestas observadas liquidadas)
- **Beneficio neto acumulado**: `S/-2.09 PEN`
- **ROI acumulado**: `-4.65%`
- **Win Rate**: `51.52%` (`17G - 16P`)
- **Apuestas liquidadas**: `33`
- **CLV medio**: `-3.34%`
- **Tasa de batir la línea de cierre (Beat CLV %)**: `6.7%`
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
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.22205` | `0.63180` |
| Modelo A (Baseline Histórico) | `0.24548` | `0.68480` |
| Mercado Sin Margen (Muestra común) | `0.22590` | `0.64121` |
| Modelo sobre Muestra Común | `0.22205` | `0.63180` |
| baseline_naive_ml | `0.22961` | `0.65185` |
| ensemble_calibrated_ml | `0.18615` | `0.55368` |
| baseline_naive_totals | `0.26134` | `0.71775` |
| ensemble_calibrated_totals | `0.25794` | `0.70992` |
| ensemble_raw_ml | `0.18660` | `0.55365` |
| ensemble_calibrated_model_ml | `0.18615` | `0.55368` |
| ensemble_market_anchored_ml | `0.18247` | `0.54350` |
| ensemble_raw_totals | `0.26196` | `0.71804` |
| ensemble_calibrated_model_totals | `0.25794` | `0.70992` |
| ensemble_market_anchored_totals | `0.25537` | `0.70610` |
| ensemble_raw_spread | `0.22902` | `0.65092` |
| ensemble_calibrated_model_spread | `0.22902` | `0.65092` |
| market_devig_spread | `0.24846` | `0.69006` |
| ensemble_market_anchored_spread | `0.24273` | `0.67860` |
| market_devig_ml | `0.19980` | `0.58527` |
| market_devig_totals | `0.25200` | `0.69715` |
| common_subset_raw_ml | `0.18621` | `0.55267` |
| common_subset_raw_totals | `0.25726` | `0.70854` |
| common_subset_calibrated_model_ml | `0.18615` | `0.55368` |
| common_subset_calibrated_model_totals | `0.25794` | `0.70992` |
| common_subset_market_anchored_ml | `0.19391` | `0.57240` |
| common_subset_market_anchored_totals | `0.25238` | `0.69794` |
| common_subset_ensemble_ml | `0.18615` | `0.55368` |
| common_subset_ensemble_totals | `0.25794` | `0.70992` |

## 4. Desempeño por Mercado (Total: 33 Apuestas Observadas | Banca: S/97.91 PEN)
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `22` | `54.5%` | `S/+0.37` | `+1.19%` | `n/d%` | `n/d` |
| `total_points` | `11` | `45.5%` | `S/-2.46` | `-18.12%` | `n/d%` | `n/d` |
| `spread` | `0` | `0.0%` | `S/+0.00` | `+0.00%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `15` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
