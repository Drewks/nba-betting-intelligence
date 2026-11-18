---
date_generated: 2026-11-18T04:41:52Z
report_type: weekly_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
run_manifest_id: RUN_20261118T044143Z_436ABF6D
settled_predictions: 33
observed_bankroll_pen: 97.91
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)
- **Fecha generada (UTC)**: `2026-11-18T04:41:52Z`
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
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.22603` | `0.64396` |
| Modelo A (Baseline Histórico) | `0.24786` | `0.68993` |
| Mercado Sin Margen (Muestra común) | `0.23656` | `0.66643` |
| Modelo sobre Muestra Común | `0.22603` | `0.64396` |
| baseline_naive_ml | `0.23055` | `0.65378` |
| ensemble_calibrated_ml | `0.20451` | `0.59931` |
| baseline_naive_totals | `0.26516` | `0.72607` |
| ensemble_calibrated_totals | `0.24755` | `0.68861` |
| ensemble_raw_ml | `0.18951` | `0.56098` |
| ensemble_calibrated_model_ml | `0.20451` | `0.59931` |
| ensemble_market_anchored_ml | `0.18600` | `0.55202` |
| ensemble_raw_totals | `0.26019` | `0.71440` |
| ensemble_calibrated_model_totals | `0.24755` | `0.68861` |
| ensemble_market_anchored_totals | `0.25475` | `0.70482` |
| ensemble_raw_spread | `0.22934` | `0.65146` |
| ensemble_calibrated_model_spread | `0.22950` | `0.65180` |
| market_devig_spread | `0.24888` | `0.69091` |
| ensemble_market_anchored_spread | `0.24203` | `0.67718` |
| market_devig_ml | `0.22088` | `0.63525` |
| market_devig_totals | `0.25223` | `0.69762` |
| common_subset_raw_ml | `0.20466` | `0.59926` |
| common_subset_raw_totals | `0.24680` | `0.68709` |
| common_subset_calibrated_model_ml | `0.20451` | `0.59931` |
| common_subset_calibrated_model_totals | `0.24755` | `0.68861` |
| common_subset_market_anchored_ml | `0.21438` | `0.62155` |
| common_subset_market_anchored_totals | `0.24899` | `0.69114` |
| common_subset_ensemble_ml | `0.20451` | `0.59931` |
| common_subset_ensemble_totals | `0.24755` | `0.68861` |

## 4. Desempeño por Mercado (Total: 33 Apuestas Observadas | Banca: S/97.91 PEN)
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `22` | `54.5%` | `S/+0.37` | `+1.19%` | `n/d%` | `n/d` |
| `total_points` | `11` | `45.5%` | `S/-2.46` | `-18.12%` | `n/d%` | `n/d` |
| `spread` | `0` | `0.0%` | `S/+0.00` | `+0.00%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `18` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
