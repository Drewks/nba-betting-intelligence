---
date_generated: 2026-11-28T15:52:51Z
report_type: weekly_report
model_versions: [model_f_ensemble_v9, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v9, model_d_total_points_v9, model_e_lightgbm_v9, model_g_ml_montecarlo_v9, model_h_ridge_rapm_v9]
run_manifest_id: RUN_20261128T155240Z_51BB6A77
settled_predictions: 40
observed_bankroll_pen: 96.80
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)
- **Fecha generada (UTC)**: `2026-11-28T15:52:51Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual actual liquidado**: `S/96.80 PEN` (`40` apuestas observadas liquidadas)
- **Beneficio neto acumulado**: `S/-3.20 PEN`
- **ROI acumulado**: `-5.74%`
- **Win Rate**: `52.50%` (`21G - 19P`)
- **Apuestas liquidadas**: `40`
- **CLV medio**: `-2.60%`
- **Tasa de batir la línea de cierre (Beat CLV %)**: `19.4%`
- **Ratio de Sharpe simulado (anualizado)**: `n/d`
- **Máximo Drawdown**: `9.00%` (Límite de alerta: `15.00%`)

## 2. Incertidumbre Estadística (Block Bootstrap 95% CI)
- **ROI 95% CI**: `[-36.27%, 26.20%]`
- **Win Rate 95% CI**: `[n/d%, n/d%]`
- **CLV 95% CI**: `[n/d%, n/d%]`
- **Brier Score 95% CI**: `[n/d, n/d]`
- **Interpretación**: `Muestra insuficiente para inferencia bootstrap concluyente.`

## 3. Calibración y Comparación de Modelos (Fuera de Muestra)
| Modelo / Fuente | Brier Score | Log Loss |
|---|---|---|
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.22486` | `0.63834` |
| Modelo A (Baseline Histórico) | `0.27292` | `0.74132` |
| Mercado Sin Margen (Muestra común) | `0.22807` | `0.64593` |
| Modelo sobre Muestra Común | `0.22486` | `0.63834` |
| baseline_naive_ml | `0.24377` | `0.68050` |
| ensemble_calibrated_ml | `0.20796` | `0.60003` |
| baseline_naive_totals | `0.30207` | `0.80214` |
| ensemble_calibrated_totals | `0.24176` | `0.67666` |
| ensemble_raw_ml | `0.20767` | `0.59771` |
| ensemble_calibrated_model_ml | `0.20796` | `0.60003` |
| ensemble_market_anchored_ml | `0.20605` | `0.59845` |
| ensemble_raw_totals | `0.23437` | `0.66119` |
| ensemble_calibrated_model_totals | `0.24176` | `0.67666` |
| ensemble_market_anchored_totals | `0.24477` | `0.68268` |
| ensemble_raw_spread | `0.24887` | `0.69055` |
| ensemble_calibrated_model_spread | `0.24991` | `0.69254` |
| market_devig_spread | `0.24790` | `0.68895` |
| ensemble_market_anchored_spread | `0.24504` | `0.68322` |
| market_devig_ml | `0.20620` | `0.59883` |
| market_devig_totals | `0.24994` | `0.69303` |
| common_subset_raw_ml | `0.20767` | `0.59771` |
| common_subset_raw_totals | `0.23437` | `0.66119` |
| common_subset_calibrated_model_ml | `0.20796` | `0.60003` |
| common_subset_calibrated_model_totals | `0.24176` | `0.67666` |
| common_subset_market_anchored_ml | `0.20605` | `0.59845` |
| common_subset_market_anchored_totals | `0.24477` | `0.68268` |
| common_subset_ensemble_ml | `0.20796` | `0.60003` |
| common_subset_ensemble_totals | `0.24176` | `0.67666` |

## 4. Desempeño por Mercado (Total: 40 Apuestas Observadas | Banca: S/96.80 PEN)
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `28` | `57.1%` | `S/+0.58` | `+1.41%` | `n/d%` | `n/d` |
| `total_points` | `12` | `41.7%` | `S/-3.77` | `-25.32%` | `n/d%` | `n/d` |
| `spread` | `0` | `0.0%` | `S/+0.00` | `+0.00%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `10` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
