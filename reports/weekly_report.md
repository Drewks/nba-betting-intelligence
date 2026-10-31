---
date_generated: 2026-10-31T21:31:48Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 9
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-10-31T21:31:48Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/101.71 PEN`
- **Beneficio neto acumulado**: `S/+1.71 PEN`
- **Stakes liquidados totales**: `S/9.00 PEN`
- **Importe total apostado**: `S/11.04 PEN`
- **ROI**: `+19.00%`
- **Yield**: `+15.49%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `9` (Ganadas: `5`, Perdidas: `4`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.107`
- **Drawdown máximo**: `S/1.08 PEN` (`1.06%`)
- **Exposición máxima simultánea**: `S/6.00 PEN`
- **Closing Line Value (CLV) medio**: `+0.05%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 5 | 3 | 2 | 0 | S/+1.88 | +37.60% |
| `total_points` | 4 | 2 | 2 | 0 | S/-0.17 | -4.25% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.24416 | 0.68153 | — |
| `Modelo B (Elo)` | `moneyline` | 0.20616 | 0.59884 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.20616** | **0.59884** | 0.21973 |
| `Modelo E (LightGBM)` | `moneyline` | 0.20616 | 0.59884 | — |
| `Modelo A (Baseline)` | `total_points` | 0.26981 | 0.73585 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.28830** | **0.78435** | 0.38872 |
| `Modelo E (LightGBM)` | `total_points` | 0.28830 | 0.78435 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (3 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-13.33%, +56.00%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `17` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `True`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `APROBAR PROMOCIÓN CONTROLADA`
