---
date_generated: 2026-11-03T02:38:49Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 14
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-11-03T02:38:49Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/97.67 PEN`
- **Beneficio neto acumulado**: `S/-2.33 PEN`
- **Stakes liquidados totales**: `S/15.61 PEN`
- **Importe total apostado**: `S/18.74 PEN`
- **ROI**: `-14.95%`
- **Yield**: `-12.45%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `14` (Ganadas: `6`, Perdidas: `8`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.491`
- **Drawdown máximo**: `S/6.20 PEN` (`6.04%`)
- **Exposición máxima simultánea**: `S/7.70 PEN`
- **Closing Line Value (CLV) medio**: `+2.17%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 10 | 4 | 6 | 0 | S/-2.16 | -18.64% |
| `total_points` | 4 | 2 | 2 | 0 | S/-0.17 | -4.25% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.23874 | 0.67042 | — |
| `Modelo B (Elo)` | `moneyline` | 0.19618 | 0.57718 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.19618** | **0.57718** | 0.11803 |
| `Modelo E (LightGBM)` | `moneyline` | 0.19618 | 0.57718 | — |
| `Modelo A (Baseline)` | `total_points` | 0.28357 | 0.76555 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.27552** | **0.75338** | 0.24334 |
| `Modelo E (LightGBM)` | `total_points` | 0.27552 | 0.75338 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (5 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-67.58%, +33.80%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `27` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `True`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `APROBAR PROMOCIÓN CONTROLADA`
