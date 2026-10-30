---
date_generated: 2026-10-30T14:31:07Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 104
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-10-30T14:31:07Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/105.14 PEN`
- **Beneficio neto acumulado**: `S/+5.14 PEN`
- **Stakes liquidados totales**: `S/104.00 PEN`
- **Importe total apostado**: `S/107.00 PEN`
- **ROI**: `+4.95%`
- **Yield**: `+4.81%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `104` (Ganadas: `49`, Perdidas: `55`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.705`
- **Drawdown máximo**: `S/19.63 PEN` (`16.44%`)
- **Exposición máxima simultánea**: `S/6.00 PEN`
- **Closing Line Value (CLV) medio**: `+13.20%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 49 | 19 | 30 | 0 | S/-0.19 | -0.39% |
| `total_points` | 55 | 30 | 25 | 0 | S/+5.34 | +9.70% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.23783 | 0.66836 | — |
| `Modelo B (Elo)` | `moneyline` | 0.24014 | 0.67381 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.24014** | **0.67381** | 0.05158 |
| `Modelo E (LightGBM)` | `moneyline` | 0.24014 | 0.67381 | — |
| `Modelo A (Baseline)` | `total_points` | 0.26241 | 0.72145 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.24937** | **0.69221** | 0.07052 |
| `Modelo E (LightGBM)` | `total_points` | 0.24937 | 0.69221 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (35 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-19.04%, +29.29%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `171` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `True`
- **¿Supera al Baseline en Brier y Log Loss?**: `False`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
