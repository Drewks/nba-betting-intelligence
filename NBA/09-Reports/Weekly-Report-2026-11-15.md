---
date_generated: 2026-11-15T07:11:49Z
report_type: weekly_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
run_manifest_id: RUN_20261115T071103Z_AF543226
settled_predictions: 28
observed_bankroll_pen: 93.47
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)
- **Fecha generada (UTC)**: `2026-11-15T07:11:49Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual actual liquidado**: `S/93.47 PEN` (`28` apuestas observadas liquidadas)
- **Beneficio neto acumulado**: `S/-6.53 PEN`
- **ROI acumulado**: `-17.21%`
- **Win Rate**: `42.86%` (`12G - 16P`)
- **Apuestas liquidadas**: `28`
- **CLV medio**: `-3.68%`
- **Tasa de batir la línea de cierre (Beat CLV %)**: `4.0%`
- **Ratio de Sharpe simulado (anualizado)**: `n/d`
- **Máximo Drawdown**: `9.00%` (Límite de alerta: `15.00%`)

## 2. Incertidumbre Estadística (Block Bootstrap 95% CI)
- **ROI 95% CI**: `[-55.10%, 25.28%]`
- **Win Rate 95% CI**: `[n/d%, n/d%]`
- **CLV 95% CI**: `[n/d%, n/d%]`
- **Brier Score 95% CI**: `[n/d, n/d]`
- **Interpretación**: `Muestra insuficiente para inferencia bootstrap concluyente.`

## 3. Calibración y Comparación de Modelos (Fuera de Muestra)
| Modelo / Fuente | Brier Score | Log Loss |
|---|---|---|
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.23715` | `0.66463` |
| Modelo A (Baseline Histórico) | `0.25414` | `0.70336` |
| Mercado Sin Margen (Muestra común) | `0.20683` | `0.59710` |
| Modelo sobre Muestra Común | `0.21938` | `0.62642` |
| baseline_naive_ml | `0.23632` | `0.66545` |
| ensemble_calibrated_ml | `0.20620` | `0.59890` |
| baseline_naive_totals | `0.27196` | `0.74126` |
| ensemble_calibrated_totals | `0.26810` | `0.73037` |
| ensemble_raw_ml | `0.20487` | `0.59439` |
| ensemble_calibrated_model_ml | `0.20620` | `0.59890` |
| ensemble_market_anchored_ml | `0.18285` | `0.54293` |
| ensemble_raw_totals | `0.25500` | `0.70322` |
| ensemble_calibrated_model_totals | `0.26810` | `0.73037` |
| ensemble_market_anchored_totals | `0.25355` | `0.70025` |
| market_devig_ml | `0.16442` | `0.50260` |
| market_devig_totals | `0.24923` | `0.69160` |
| common_subset_raw_ml | `0.16790` | `0.51157` |
| common_subset_raw_totals | `0.26657` | `0.72768` |
| common_subset_calibrated_model_ml | `0.17309` | `0.52716` |
| common_subset_calibrated_model_totals | `0.26567` | `0.72568` |
| common_subset_market_anchored_ml | `0.16537` | `0.50518` |
| common_subset_market_anchored_totals | `0.25265` | `0.69846` |
| common_subset_ensemble_ml | `0.17309` | `0.52716` |
| common_subset_ensemble_totals | `0.26567` | `0.72568` |

## 4. Desempeño por Mercado (Total: 28 Apuestas Observadas | Banca: S/93.47 PEN)
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `19` | `47.4%` | `S/-1.77` | `-6.60%` | `n/d%` | `n/d` |
| `total_points` | `9` | `33.3%` | `S/-4.76` | `-42.71%` | `n/d%` | `n/d` |
| `spread` | `0` | `0.0%` | `S/+0.00` | `+0.00%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `173` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
