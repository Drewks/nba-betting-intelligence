---
date_generated: 2026-10-29T00:23:32Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 93
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-10-29T00:23:32Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/106.00 PEN`
- **Beneficio neto acumulado**: `S/+6.00 PEN`
- **Stakes liquidados totales**: `S/93.00 PEN`
- **Importe total apostado**: `S/101.00 PEN`
- **ROI**: `+6.45%`
- **Yield**: `+5.94%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist.
- **Selecciones liquidadas**: `93` (Ganadas: `46`, Perdidas: `47`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.462`
- **Drawdown máximo**: `S/9.43 PEN` (`9.43%`)
- **Exposición máxima simultánea**: `S/8.00 PEN`
- **Closing Line Value (CLV) medio**: `No disponible`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 36 | 19 | 17 | 0 | S/+7.11 | +19.75% |
| `total_points` | 57 | 27 | 30 | 0 | S/-1.12 | -1.96% |

## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)

| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: |
| `Modelo A (Baseline)` | `moneyline` | 0.24044 | 0.67394 | — |
| `Modelo B (Elo)` | `moneyline` | 0.24227 | 0.67770 | — |
| `Modelo C (Point Margin)` | `moneyline` | **0.24227** | **0.67770** | 0.08288 |
| `Modelo E (LightGBM)` | `moneyline` | 0.24227 | 0.67770 | — |
| `Modelo A (Baseline)` | `total_points` | 0.25000 | 0.69315 | — |
| `Modelo D (Total Points + Cov)` | `total_points` | **0.25027** | **0.69382** | 0.05480 |
| `Modelo E (LightGBM)` | `total_points` | 0.25027 | 0.69382 | — |

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (33 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-17.30%, +32.62%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `165` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS (never ROI alone)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `True`
- **¿Supera al Baseline en Brier y Log Loss?**: `False`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
