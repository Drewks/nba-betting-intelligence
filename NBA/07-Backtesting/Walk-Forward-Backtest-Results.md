---
date_generated: 2026-11-09T16:54:25Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 27
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-11-09T16:54:25Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/99.97 PEN`
- **Beneficio neto acumulado**: `S/-0.03 PEN`
- **Stakes liquidados totales**: `S/35.33 PEN`
- **Importe total apostado**: `S/40.45 PEN`
- **ROI**: `-0.10%`
- **Yield**: `-0.09%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `27` (Ganadas: `13`, Perdidas: `14`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.284`
- **Drawdown máximo**: `S/6.26 PEN` (`6.09%`)
- **Exposición máxima simultánea**: `S/10.34 PEN`
- **Closing Line Value (CLV) medio**: `+6.51%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 19 | 10 | 9 | 0 | S/+2.73 | +10.42% |
| `total_points` | 8 | 3 | 5 | 0 | S/-2.76 | -30.18% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.23377 | 0.66029 | — |
| `Modelo B (Elo)` | `moneyline` | 0.17625 | 0.53278 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.17625** | **0.53278** | 0.11026 |
| `Modelo E (LightGBM)` | `moneyline` | 0.18018 | 0.54035 | — |
| `Modelo A (Baseline)` | `total_points` | 0.26810 | 0.73371 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.25785** | **0.71195** | 0.16897 |
| `Modelo E (LightGBM)` | `total_points` | 0.25151 | 0.69622 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (10 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-31.45%, +25.47%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `80` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
