---
date_generated: 2026-10-31T01:30:10Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 6
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-10-31T01:30:10Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/102.11 PEN`
- **Beneficio neto acumulado**: `S/+2.11 PEN`
- **Stakes liquidados totales**: `S/6.00 PEN`
- **Importe total apostado**: `S/10.04 PEN`
- **ROI**: `+35.17%`
- **Yield**: `+21.02%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `6` (Ganadas: `4`, Perdidas: `2`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.005`
- **Drawdown máximo**: `S/1.08 PEN` (`1.06%`)
- **Exposición máxima simultánea**: `S/6.00 PEN`
- **Closing Line Value (CLV) medio**: `+1.53%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 3 | 2 | 1 | 0 | S/+1.28 | +42.67% |
| `total_points` | 3 | 2 | 1 | 0 | S/+0.83 | +27.67% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.26070 | 0.71471 | — |
| `Modelo B (Elo)` | `moneyline` | 0.21952 | 0.62758 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.21952** | **0.62758** | 0.31114 |
| `Modelo E (LightGBM)` | `moneyline` | 0.21952 | 0.62758 | — |
| `Modelo A (Baseline)` | `total_points` | 0.24794 | 0.69023 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.22786** | **0.64919** | 0.24197 |
| `Modelo E (LightGBM)` | `total_points` | 0.22786 | 0.64919 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (2 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[+14.33%, +56.00%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `NO`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `6` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `True`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `APROBAR PROMOCIÓN CONTROLADA`
