---
date_generated: 2026-11-15T02:13:53Z
report_type: weekly_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
run_manifest_id: n/d
settled_predictions: 28
observed_bankroll_pen: 93.47
simulation_only: true
---
# Informe Semanal de Rendimiento y Validación Fuera de Muestra

## 1. Métricas Clave de Desempeño (Paper Trading — Cuotas Observadas)
- **Fecha generada (UTC)**: `2026-11-15T02:13:53Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual actual liquidado**: `S/93.47 PEN` (`28` apuestas observadas liquidadas)
- **Beneficio neto acumulado**: `S/-6.53 PEN`
- **ROI acumulado**: `-17.21%`
- **Win Rate**: `42.86%` (`12G - 16P`)
- **Apuestas liquidadas**: `28`
- **CLV medio**: `-2.17%`
- **Tasa de batir la línea de cierre (Beat CLV %)**: `23.1%`
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
| **Ensemble Ponderado (Modelos B+C+D+E)** | `n/d` | `n/d` |
| Modelo A (Baseline Histórico) | `0.25065` | `0.69592` |
| Mercado Sin Margen (Muestra común) | `0.21527` | `0.61571` |
| Modelo sobre Muestra Común | `n/d` | `n/d` |
| baseline_naive_ml | `0.22896` | `0.65049` |
| baseline_naive_totals | `0.27234` | `0.74134` |
| ensemble_raw_ml | `0.18666` | `0.55380` |
| ensemble_market_anchored_ml | `0.18068` | `0.53899` |
| ensemble_raw_totals | `0.26270` | `0.71952` |
| ensemble_market_anchored_totals | `0.25583` | `0.70738` |
| market_devig_ml | `0.18224` | `0.54170` |
| market_devig_totals | `0.24829` | `0.68972` |
| common_subset_raw_ml | `0.18666` | `0.55380` |
| common_subset_raw_totals | `0.26270` | `0.71952` |
| common_subset_market_anchored_ml | `0.18068` | `0.53899` |
| common_subset_market_anchored_totals | `0.25583` | `0.70738` |

## 4. Desempeño por Mercado (Total: 28 Apuestas Observadas | Banca: S/93.47 PEN)
| Mercado | Apuestas | Win Rate | Beneficio Neto (PEN) | ROI (%) | CLV Medio (%) | Brier Score |
|---|---|---|---|---|---|---|
| `moneyline` | `19` | `47.4%` | `S/-1.77` | `-6.60%` | `n/d%` | `n/d` |
| `total_points` | `9` | `33.3%` | `S/-4.76` | `-42.71%` | `n/d%` | `n/d` |
| `spread` | `0` | `0.0%` | `S/+0.00` | `+0.00%` | `n/d%` | `n/d` |

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `0` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `False`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
