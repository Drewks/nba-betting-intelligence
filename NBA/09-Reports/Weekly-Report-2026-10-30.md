---
date_generated: 2026-10-30T02:58:56Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 103
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-10-30T02:58:56Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/104.23 PEN`
- **Beneficio neto acumulado**: `S/+4.24 PEN`
- **Stakes liquidados totales**: `S/103.00 PEN`
- **Importe total apostado**: `S/107.00 PEN`
- **ROI**: `+4.11%`
- **Yield**: `+3.96%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `103` (Ganadas: `48`, Perdidas: `55`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.713`
- **Drawdown máximo**: `S/19.63 PEN` (`16.44%`)
- **Exposición máxima simultánea**: `S/6.00 PEN`
- **Closing Line Value (CLV) medio**: `+13.52%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 49 | 19 | 30 | 0 | S/-0.19 | -0.39% |
| `total_points` | 54 | 29 | 25 | 0 | S/+4.43 | +8.20% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.23760 | 0.66788 | — |
| `Modelo B (Elo)` | `moneyline` | 0.23958 | 0.67268 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.23958** | **0.67268** | 0.05529 |
| `Modelo E (LightGBM)` | `moneyline` | 0.23958 | 0.67268 | — |
| `Modelo A (Baseline)` | `total_points` | 0.26333 | 0.72338 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.25005** | **0.69361** | 0.06879 |
| `Modelo E (LightGBM)` | `total_points` | 0.25005 | 0.69361 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (35 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-19.81%, +28.65%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `170` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `True`
- **¿Supera al Baseline en Brier y Log Loss?**: `False`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
