---
date_generated: 2026-10-29T00:50:51Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 98
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-10-29T00:50:51Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/103.03 PEN`
- **Beneficio neto acumulado**: `S/+3.04 PEN`
- **Stakes liquidados totales**: `S/98.00 PEN`
- **Importe total apostado**: `S/104.00 PEN`
- **ROI**: `+3.10%`
- **Yield**: `+2.92%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `98` (Ganadas: `45`, Perdidas: `53`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.748`
- **Drawdown máximo**: `S/19.63 PEN` (`16.44%`)
- **Exposición máxima simultánea**: `S/6.00 PEN`
- **Closing Line Value (CLV) medio**: `No disponible`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 46 | 17 | 29 | 0 | S/-1.47 | -3.20% |
| `total_points` | 52 | 28 | 24 | 0 | S/+4.51 | +8.67% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.23699 | 0.66664 | — |
| `Modelo B (Elo)` | `moneyline` | 0.24089 | 0.67549 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.24089** | **0.67549** | 0.05164 |
| `Modelo E (LightGBM)` | `moneyline` | 0.24089 | 0.67549 | — |
| `Modelo A (Baseline)` | `total_points` | 0.26368 | 0.72379 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.25015** | **0.69377** | 0.06429 |
| `Modelo E (LightGBM)` | `total_points` | 0.25015 | 0.69377 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (33 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-21.81%, +27.73%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `165` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `True`
- **¿Supera al Baseline en Brier y Log Loss?**: `False`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
