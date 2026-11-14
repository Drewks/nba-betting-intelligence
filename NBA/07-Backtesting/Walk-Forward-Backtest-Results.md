---
date_generated: 2026-11-14T13:49:32Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 28
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading)
- **Fecha generada (UTC)**: `2026-11-14T13:49:32Z`
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
| **Ensemble Ponderado (Modelos B+C+D+E)** | `0.21826` | `0.62318` |
| Modelo A (Baseline Histórico) | `0.25065` | `0.69592` |
| Mercado Sin Margen (Muestra común) | `0.21527` | `0.61571` |
| Modelo sobre Muestra Común | `0.21826` | `0.62318` |
| baseline_naive_ml | `0.22896` | `0.65049` |
| ensemble_calibrated_ml | `0.18068` | `0.53899` |
| baseline_naive_totals | `0.27234` | `0.74134` |
| ensemble_calibrated_totals | `0.25583` | `0.70738` |
| ensemble_raw_ml | `0.18666` | `0.55380` |
| market_devig_ml | `0.18224` | `0.54170` |
| market_devig_totals | `0.24829` | `0.68972` |

## 4. Desempeño por Mercado
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `0` | `0.0%` | `S/ -1.77` | `-6.60%` | `n/d%` | `n/d` |
| `total_points` | `0` | `0.0%` | `S/ -4.76` | `-42.71%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `96` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
