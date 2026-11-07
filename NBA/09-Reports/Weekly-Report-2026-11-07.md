---
date_generated: 2026-11-07T16:38:41Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 24
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-11-07T16:38:41Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/98.87 PEN`
- **Beneficio neto acumulado**: `S/-1.13 PEN`
- **Stakes liquidados totales**: `S/29.99 PEN`
- **Importe total apostado**: `S/35.33 PEN`
- **ROI**: `-3.76%`
- **Yield**: `-3.20%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `24` (Ganadas: `11`, Perdidas: `13`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.329`
- **Drawdown máximo**: `S/6.26 PEN` (`6.09%`)
- **Exposición máxima simultánea**: `S/10.34 PEN`
- **Closing Line Value (CLV) medio**: `+1.03%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 17 | 9 | 8 | 0 | S/+2.85 | +12.85% |
| `total_points` | 7 | 2 | 5 | 0 | S/-3.98 | -50.96% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.23172 | 0.65617 | — |
| `Modelo B (Elo)` | `moneyline` | 0.16290 | 0.50561 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.16290** | **0.50561** | 0.17894 |
| `Modelo E (LightGBM)` | `moneyline` | 0.16290 | 0.50561 | — |
| `Modelo A (Baseline)` | `total_points` | 0.26459 | 0.72786 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.26003** | **0.71567** | 0.16947 |
| `Modelo E (LightGBM)` | `total_points` | 0.26003 | 0.71567 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (9 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-39.29%, +28.12%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `101` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `True`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `APROBAR PROMOCIÓN CONTROLADA`
