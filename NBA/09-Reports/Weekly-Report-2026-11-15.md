---
date_generated: 2026-11-15T03:30:36Z
report_type: weekly_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
run_manifest_id: RUN_20261115T033021Z_CCB4A639
settled_predictions: 28
observed_bankroll_pen: 93.47
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)
- **Fecha generada (UTC)**: `2026-11-15T03:30:36Z`
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
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.23650` | `0.66311` |
| Modelo A (Baseline Histórico) | `0.25427` | `0.70364` |
| Mercado Sin Margen (Muestra común) | `0.20683` | `0.59710` |
| Modelo sobre Muestra Común | `0.21922` | `0.62604` |
| baseline_naive_ml | `0.23653` | `0.66586` |
| ensemble_calibrated_ml | `0.20456` | `0.59514` |
| baseline_naive_totals | `0.27202` | `0.74142` |
| ensemble_calibrated_totals | `0.26844` | `0.73107` |
| ensemble_raw_ml | `0.20340` | `0.59122` |
| ensemble_calibrated_model_ml | `0.20456` | `0.59514` |
| ensemble_market_anchored_ml | `0.18295` | `0.54313` |
| ensemble_raw_totals | `0.25496` | `0.70313` |
| ensemble_calibrated_model_totals | `0.26844` | `0.73107` |
| ensemble_market_anchored_totals | `0.25361` | `0.70039` |
| market_devig_ml | `0.16442` | `0.50260` |
| market_devig_totals | `0.24923` | `0.69160` |
| common_subset_raw_ml | `0.16793` | `0.51174` |
| common_subset_raw_totals | `0.26651` | `0.72754` |
| common_subset_calibrated_model_ml | `0.17283` | `0.52654` |
| common_subset_calibrated_model_totals | `0.26561` | `0.72555` |
| common_subset_market_anchored_ml | `0.16527` | `0.50497` |
| common_subset_market_anchored_totals | `0.25263` | `0.69843` |
| common_subset_ensemble_ml | `0.17283` | `0.52654` |
| common_subset_ensemble_totals | `0.26561` | `0.72555` |

## 4. Desempeño por Mercado (Total: 28 Apuestas Observadas | Banca: S/93.47 PEN)
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `19` | `47.4%` | `S/-1.77` | `-6.60%` | `n/d%` | `n/d` |
| `total_points` | `9` | `33.3%` | `S/-4.76` | `-42.71%` | `n/d%` | `n/d` |
| `spread` | `0` | `0.0%` | `S/+0.00` | `+0.00%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `172` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
