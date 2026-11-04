---
date_generated: 2026-11-04T02:43:19Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 17
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-11-04T02:43:19Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/97.44 PEN`
- **Beneficio neto acumulado**: `S/-2.56 PEN`
- **Stakes liquidados totales**: `S/18.74 PEN`
- **Importe total apostado**: `S/23.60 PEN`
- **ROI**: `-13.68%`
- **Yield**: `-10.86%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `17` (Ganadas: `7`, Perdidas: `10`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.456`
- **Drawdown máximo**: `S/6.20 PEN` (`6.04%`)
- **Exposición máxima simultánea**: `S/7.70 PEN`
- **Closing Line Value (CLV) medio**: `+1.17%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 11 | 5 | 6 | 0 | S/-0.26 | -2.09% |
| `total_points` | 6 | 2 | 4 | 0 | S/-2.30 | -37.52% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.23991 | 0.67275 | — |
| `Modelo B (Elo)` | `moneyline` | 0.19894 | 0.58171 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.19894** | **0.58171** | 0.13512 |
| `Modelo E (LightGBM)` | `moneyline` | 0.19894 | 0.58171 | — |
| `Modelo A (Baseline)` | `total_points` | 0.26966 | 0.73479 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.26387** | **0.72677** | 0.19072 |
| `Modelo E (LightGBM)` | `total_points` | 0.26387 | 0.72677 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (6 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-60.05%, +26.04%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `42` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `True`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `APROBAR PROMOCIÓN CONTROLADA`
