---
date_generated: 2026-11-12T21:50:29Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 28
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading)
- **Fecha generada (UTC)**: `2026-11-12T21:50:29Z`
- **Bankroll virtual inicial**: `S/ 100.00 PEN`
- **Bankroll virtual actual liquidado**: `S/ 93.47 PEN`
- **Beneficio neto acumulado**: `S/ -6.53 PEN`
- **ROI acumulado**: `-17.21%`
- **Win Rate**: `0.00%`
- **Apuestas liquidadas**: `28`
- **CLV medio**: `-2.17%`
- **Tasa de batir la línea de cierre (Beat CLV %)**: `n/d%`
- **Ratio de Sharpe simulado (anualizado)**: `n/d`
- **Máximo Drawdown**: `9.00%` (Límite de alerta: `15.00%`)

## 2. Incertidumbre Estadística (Block Bootstrap 95% CI)
- **ROI 95% CI**: `[n/d%, n/d%]`
- **Win Rate 95% CI**: `[n/d%, n/d%]`
- **CLV 95% CI**: `[n/d%, n/d%]`
- **Brier Score 95% CI**: `[n/d, n/d]`
- **Interpretación**: `Muestra insuficiente para inferencia bootstrap concluyente.`

## 3. Calibración y Comparación de Modelos (Fuera de Muestra)
| Modelo / Fuente | Brier Score | Log Loss |
|---|---|---|
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.21612` | `0.61888` |
| Modelo A (Baseline Histórico) | `0.25043` | `0.69571` |
| Mercado Sin Margen (Muestra común) | `0.21317` | `0.61147` |
| Modelo sobre Muestra Común | `0.21612` | `0.61888` |
| baseline_naive_ml | `0.23069` | `0.65403` |
| ensemble_calibrated_ml | `0.17482` | `0.52694` |
| baseline_naive_totals | `0.27017` | `0.73738` |
| ensemble_calibrated_totals | `0.25741` | `0.71081` |
| ensemble_raw_ml | `0.17849` | `0.53427` |
| market_devig_ml | `0.17750` | `0.53212` |
| market_devig_totals | `0.24884` | `0.69083` |

## 4. Desempeño por Mercado
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `0` | `0.0%` | `S/ -1.77` | `-6.60%` | `n/d%` | `n/d` |
| `total_points` | `0` | `0.0%` | `S/ -4.76` | `-42.71%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `87` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
