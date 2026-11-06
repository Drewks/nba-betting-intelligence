---
date_generated: 2026-11-06T01:59:47Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 20
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-11-06T01:59:47Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/96.45 PEN`
- **Beneficio neto acumulado**: `S/-3.55 PEN`
- **Stakes liquidados totales**: `S/23.60 PEN`
- **Importe total apostado**: `S/29.99 PEN`
- **ROI**: `-15.03%`
- **Yield**: `-11.83%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `20` (Ganadas: `8`, Perdidas: `12`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.412`
- **Drawdown máximo**: `S/6.26 PEN` (`6.09%`)
- **Exposición máxima simultánea**: `S/7.70 PEN`
- **Closing Line Value (CLV) medio**: `+1.17%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 14 | 6 | 8 | 0 | S/-1.25 | -7.14% |
| `total_points` | 6 | 2 | 4 | 0 | S/-2.30 | -37.52% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.23790 | 0.66871 | — |
| `Modelo B (Elo)` | `moneyline` | 0.19642 | 0.57498 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.19642** | **0.57498** | 0.13114 |
| `Modelo E (LightGBM)` | `moneyline` | 0.19642 | 0.57498 | — |
| `Modelo A (Baseline)` | `total_points` | 0.25865 | 0.71148 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.25901** | **0.71557** | 0.15859 |
| `Modelo E (LightGBM)` | `total_points` | 0.25901 | 0.71557 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (7 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-52.56%, +19.70%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `56` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `True`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `APROBAR PROMOCIÓN CONTROLADA`
