---
date_generated: 2026-11-09T23:48:10Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 25
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-11-09T23:48:10Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/100.09 PEN`
- **Beneficio neto acumulado**: `S/+0.09 PEN`
- **Stakes liquidados totales**: `S/31.33 PEN`
- **Importe total apostado**: `S/37.95 PEN`
- **ROI**: `+0.28%`
- **Yield**: `+0.23%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist. VOID stakes are excluded (returned capital).
- **Selecciones liquidadas**: `25` (Ganadas: `12`, Perdidas: `13`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.312`
- **Drawdown máximo**: `S/7.84 PEN` (`7.56%`)
- **Exposición máxima simultánea**: `S/10.34 PEN`
- **Closing Line Value (CLV) medio**: `-2.17%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 17 | 9 | 8 | 0 | S/+2.85 | +12.85% |
| `total_points` | 8 | 3 | 5 | 0 | S/-2.76 | -30.18% |

## 3. Calidad Probabilística Fuera de Muestra: Modelo vs. Baseline vs. Mercado

> El rival real es el **mercado sin margen** (mismas cuotas observadas). Superar al baseline ingenuo no prueba ventaja.

| Serie | Mercado | N | Brier (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: | ---: |
| `Baseline ingenuo` | `moneyline` | 77 | 0.23285 | 0.65839 | — |
| `Ensemble (crudo)` | `moneyline` | 77 | 0.17971 | 0.53796 | — |
| `Ensemble final (calibrado + anclado 30/70 al mercado)` | `moneyline` | 77 | 0.17558 | 0.52950 | 0.10562 |
| `Mercado sin margen` | `moneyline` | 77 | 0.17828 | 0.53418 | — |
| `Baseline ingenuo` | `total_points` | 77 | 0.27218 | 0.74220 | — |
| `Ensemble final (calibrado + anclado 30/70 al mercado)` | `total_points` | 77 | 0.25820 | 0.71275 | 0.17029 |
| `Mercado sin margen` | `total_points` | 77 | 0.24923 | 0.69160 | — |

- **Modelo vs. mercado (mismos 77 partidos)**: Brier `0.21689` vs `0.21376` | LogLoss `0.62112` vs `0.61289`

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (10 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-33.01%, +32.07%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `77` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
