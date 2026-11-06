---
date_generated: 2026-11-06T22:34:56Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 21
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-11-06T22:34:56Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/97.72 PEN`
- **Beneficio neto acumulado**: `S/-2.28 PEN`
- **Stakes liquidados totales**: `S/24.99 PEN`
- **Importe total apostado**: `S/33.99 PEN`
- **ROI**: `-9.13%`
- **Yield**: `-6.72%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `21` (Ganadas: `9`, Perdidas: `12`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.388`
- **Drawdown máximo**: `S/6.26 PEN` (`6.09%`)
- **Exposición máxima simultánea**: `S/9.00 PEN`
- **Closing Line Value (CLV) medio**: `+1.17%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 15 | 7 | 8 | 0 | S/+0.02 | +0.09% |
| `total_points` | 6 | 2 | 4 | 0 | S/-2.30 | -37.52% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.23300 | 0.65881 | — |
| `Modelo B (Elo)` | `moneyline` | 0.19305 | 0.56880 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.19305** | **0.56880** | 0.13725 |
| `Modelo E (LightGBM)` | `moneyline` | 0.19305 | 0.56880 | — |
| `Modelo A (Baseline)` | `total_points` | 0.25148 | 0.69665 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.25939** | **0.71597** | 0.18768 |
| `Modelo E (LightGBM)` | `total_points` | 0.25939 | 0.71597 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (8 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-44.48%, +28.77%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `61` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `True`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `APROBAR PROMOCIÓN CONTROLADA`
