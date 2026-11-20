---
date_generated: 2026-11-20T04:15:31Z
report_type: weekly_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
run_manifest_id: RUN_20261120T041522Z_8FBABAD4
settled_predictions: 35
observed_bankroll_pen: 97.20
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)
- **Fecha generada (UTC)**: `2026-11-20T04:15:31Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual actual liquidado**: `S/97.20 PEN` (`35` apuestas observadas liquidadas)
- **Beneficio neto acumulado**: `S/-2.80 PEN`
- **ROI acumulado**: `-5.86%`
- **Win Rate**: `51.43%` (`18G - 17P`)
- **Apuestas liquidadas**: `35`
- **CLV medio**: `-2.84%`
- **Tasa de batir la línea de cierre (Beat CLV %)**: `19.4%`
- **Ratio de Sharpe simulado (anualizado)**: `n/d`
- **Máximo Drawdown**: `9.00%` (Límite de alerta: `15.00%`)

## 2. Incertidumbre Estadística (Block Bootstrap 95% CI)
- **ROI 95% CI**: `[-37.33%, 30.17%]`
- **Win Rate 95% CI**: `[n/d%, n/d%]`
- **CLV 95% CI**: `[n/d%, n/d%]`
- **Brier Score 95% CI**: `[n/d, n/d]`
- **Interpretación**: `Muestra insuficiente para inferencia bootstrap concluyente.`

## 3. Calibración y Comparación de Modelos (Fuera de Muestra)
| Modelo / Fuente | Brier Score | Log Loss |
|---|---|---|
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.25253` | `0.71003` |
| Modelo A (Baseline Histórico) | `0.25171` | `0.69797` |
| Mercado Sin Margen (Muestra común) | `0.23961` | `0.67159` |
| Modelo sobre Muestra Común | `0.25253` | `0.71003` |
| baseline_naive_ml | `0.23346` | `0.65964` |
| ensemble_calibrated_ml | `0.24221` | `0.70058` |
| baseline_naive_totals | `0.26995` | `0.73630` |
| ensemble_calibrated_totals | `0.26284` | `0.71948` |
| ensemble_raw_ml | `0.20217` | `0.59532` |
| ensemble_calibrated_model_ml | `0.24221` | `0.70058` |
| ensemble_market_anchored_ml | `0.19432` | `0.57120` |
| ensemble_raw_totals | `0.26295` | `0.71994` |
| ensemble_calibrated_model_totals | `0.26284` | `0.71948` |
| ensemble_market_anchored_totals | `0.25538` | `0.70578` |
| ensemble_raw_spread | `0.24682` | `0.68690` |
| ensemble_calibrated_model_spread | `0.24652` | `0.68627` |
| market_devig_spread | `0.24997` | `0.69309` |
| ensemble_market_anchored_spread | `0.24650` | `0.68613` |
| market_devig_ml | `0.22803` | `0.64764` |
| market_devig_totals | `0.25119` | `0.69554` |
| common_subset_raw_ml | `0.24353` | `0.70603` |
| common_subset_raw_totals | `0.26361` | `0.72106` |
| common_subset_calibrated_model_ml | `0.24221` | `0.70058` |
| common_subset_calibrated_model_totals | `0.26284` | `0.71948` |
| common_subset_market_anchored_ml | `0.23070` | `0.65709` |
| common_subset_market_anchored_totals | `0.25417` | `0.70152` |
| common_subset_ensemble_ml | `0.24221` | `0.70058` |
| common_subset_ensemble_totals | `0.26284` | `0.71948` |

## 4. Desempeño por Mercado (Total: 35 Apuestas Observadas | Banca: S/97.20 PEN)
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `23` | `56.5%` | `S/+0.97` | `+2.97%` | `n/d%` | `n/d` |
| `total_points` | `12` | `41.7%` | `S/-3.77` | `-25.32%` | `n/d%` | `n/d` |
| `spread` | `0` | `0.0%` | `S/+0.00` | `+0.00%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `36` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `False`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
