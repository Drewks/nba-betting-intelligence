---
date_generated: 2026-11-09T06:28:30Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 29
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-11-09T06:28:30Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/103.63 PEN`
- **Beneficio neto acumulado**: `S/+3.63 PEN`
- **Stakes liquidados totales**: `S/39.33 PEN`
- **Importe total apostado**: `S/45.95 PEN`
- **ROI**: `+9.24%`
- **Yield**: `+7.91%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `29` (Ganadas: `15`, Perdidas: `14`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.259`
- **Drawdown máximo**: `S/6.26 PEN` (`6.09%`)
- **Exposición máxima simultánea**: `S/10.34 PEN`
- **Closing Line Value (CLV) medio**: `+8.84%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 21 | 12 | 9 | 0 | S/+6.39 | +21.19% |
| `total_points` | 8 | 3 | 5 | 0 | S/-2.76 | -30.18% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.22657 | 0.64557 | — |
| `Modelo B (Elo)` | `moneyline` | 0.15394 | 0.48450 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.15394** | **0.48450** | 0.16328 |
| `Modelo E (LightGBM)` | `moneyline` | 0.15394 | 0.48450 | — |
| `Modelo A (Baseline)` | `total_points` | 0.27545 | 0.74893 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.25741** | **0.70976** | 0.17311 |
| `Modelo E (LightGBM)` | `total_points` | 0.25741 | 0.70976 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (11 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-24.15%, +38.33%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `138` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `True`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `APROBAR PROMOCIÓN CONTROLADA`
