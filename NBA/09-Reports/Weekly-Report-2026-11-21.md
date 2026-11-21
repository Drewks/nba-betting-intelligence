---
date_generated: 2026-11-21T14:58:44Z
report_type: weekly_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
run_manifest_id: RUN_20261121T145837Z_D39EFC1C
settled_predictions: 36
observed_bankroll_pen: 98.03
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)
- **Fecha generada (UTC)**: `2026-11-21T14:58:44Z`
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
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.24885` | `0.69822` |
| Modelo A (Baseline Histórico) | `0.25207` | `0.69883` |
| Mercado Sin Margen (Muestra común) | `0.23308` | `0.65682` |
| Modelo sobre Muestra Común | `0.24885` | `0.69822` |
| baseline_naive_ml | `0.23310` | `0.65889` |
| ensemble_calibrated_ml | `0.22909` | `0.66538` |
| baseline_naive_totals | `0.27105` | `0.73876` |
| ensemble_calibrated_totals | `0.26861` | `0.73105` |
| ensemble_raw_ml | `0.20054` | `0.59071` |
| ensemble_calibrated_model_ml | `0.22909` | `0.66538` |
| ensemble_market_anchored_ml | `0.19256` | `0.56712` |
| ensemble_raw_totals | `0.26478` | `0.72360` |
| ensemble_calibrated_model_totals | `0.26861` | `0.73105` |
| ensemble_market_anchored_totals | `0.25564` | `0.70618` |
| ensemble_raw_spread | `0.24711` | `0.68747` |
| ensemble_calibrated_model_spread | `0.24685` | `0.68692` |
| market_devig_spread | `0.24844` | `0.69003` |
| ensemble_market_anchored_spread | `0.24549` | `0.68411` |
| market_devig_ml | `0.21554` | `0.61927` |
| market_devig_totals | `0.25061` | `0.69437` |
| common_subset_raw_ml | `0.23014` | `0.66944` |
| common_subset_raw_totals | `0.26921` | `0.73230` |
| common_subset_calibrated_model_ml | `0.22909` | `0.66538` |
| common_subset_calibrated_model_totals | `0.26861` | `0.73105` |
| common_subset_market_anchored_ml | `0.21792` | `0.62713` |
| common_subset_market_anchored_totals | `0.25522` | `0.70362` |
| common_subset_ensemble_ml | `0.22909` | `0.66538` |
| common_subset_ensemble_totals | `0.26861` | `0.73105` |

## 4. Desempeño por Mercado (Total: 36 Apuestas Observadas | Banca: S/98.03 PEN)
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `24` | `58.3%` | `S/+1.80` | `+5.20%` | `n/d%` | `n/d` |
| `total_points` | `12` | `41.7%` | `S/-3.77` | `-25.32%` | `n/d%` | `n/d` |
| `spread` | `0` | `0.0%` | `S/+0.00` | `+0.00%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `45` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `False`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
