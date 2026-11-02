---
date_generated: 2026-11-02T01:00:29Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 11
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-11-02T01:00:29Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/99.67 PEN`
- **Beneficio neto acumulado**: `S/-0.33 PEN`
- **Stakes liquidados totales**: `S/11.04 PEN`
- **Importe total apostado**: `S/18.74 PEN`
- **ROI**: `-2.99%`
- **Yield**: `-1.76%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `11` (Ganadas: `5`, Perdidas: `6`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.615`
- **Drawdown máximo**: `S/3.04 PEN` (`2.96%`)
- **Exposición máxima simultánea**: `S/7.70 PEN`
- **Closing Line Value (CLV) medio**: `+1.62%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 7 | 3 | 4 | 0 | S/-0.16 | -2.27% |
| `total_points` | 4 | 2 | 2 | 0 | S/-0.17 | -4.25% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.23771 | 0.66836 | — |
| `Modelo B (Elo)` | `moneyline` | 0.19302 | 0.56969 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.19302** | **0.56969** | 0.15963 |
| `Modelo E (LightGBM)` | `moneyline` | 0.19302 | 0.56969 | — |
| `Modelo A (Baseline)` | `total_points` | 0.29269 | 0.78488 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.28091** | **0.76578** | 0.28386 |
| `Modelo E (LightGBM)` | `total_points` | 0.28091 | 0.76578 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (4 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-62.39%, +38.67%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `23` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `True`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `APROBAR PROMOCIÓN CONTROLADA`
