---
date_generated: 2026-11-10T14:07:26Z
report_type: weekly_report
model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]
settled_predictions: 28
simulation_only: true
---
# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence

## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)
- **Fecha de generación (UTC)**: `2026-11-10T14:07:26Z`
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll virtual liquidado actual**: `S/93.47 PEN`
- **Beneficio neto acumulado**: `S/-6.53 PEN`
- **Stakes liquidados totales**: `S/37.95 PEN`
- **Importe total apostado**: `S/37.95 PEN`
- **ROI**: `-17.21%`
- **Yield**: `-17.21%`
  - *Nota técnica*: ROI (net_profit / settled_stakes * 100) and Yield (net_profit / total_wagered * 100) are equivalent when all wagered bets are settled; they differ only while pending bets exist. VOID stakes are excluded (returned capital).
- **Selecciones liquidadas**: `28` (Ganadas: `12`, Perdidas: `16`, Push: `0`, Void: `0`)
- **Cuota decimal media**: `2.312`
- **Drawdown máximo**: `S/10.24 PEN` (`9.87%`)
- **Exposición máxima simultánea**: `S/10.34 PEN`
- **Closing Line Value (CLV) medio**: `-2.17%`

## 2. Rendimiento por Mercado

| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `moneyline` | 19 | 9 | 10 | 0 | S/-1.77 | -6.60% |
| `total_points` | 9 | 3 | 6 | 0 | S/-4.76 | -42.71% |

## 3. Calidad Probabilística Fuera de Muestra: Modelo vs. Baseline vs. Mercado

> El rival real es el **mercado sin margen** (mismas cuotas observadas). Superar al baseline ingenuo no prueba ventaja.

| Serie | Mercado | N | Brier (menor es mejor) | Log Loss (menor es mejor) | ECE |
| :--- | :--- | ---: | ---: | ---: | ---: |
| `Baseline ingenuo` | `moneyline` | 85 | 0.23131 | 0.65528 | — |
| `Ensemble (crudo)` | `moneyline` | 85 | 0.18019 | 0.53880 | — |
| `Ensemble final (calibrado + anclado 30/70 al mercado)` | `moneyline` | 85 | 0.17606 | 0.53038 | 0.08981 |
| `Mercado sin margen` | `moneyline` | 85 | 0.17861 | 0.53520 | — |
| `Baseline ingenuo` | `total_points` | 85 | 0.27027 | 0.73797 | — |
| `Ensemble final (calibrado + anclado 30/70 al mercado)` | `total_points` | 85 | 0.25763 | 0.71131 | 0.15404 |
| `Mercado sin margen` | `total_points` | 85 | 0.24881 | 0.69077 | — |

- **Modelo vs. mercado (mismos 85 partidos)**: Brier `0.21685` vs `0.21371` | LogLoss `0.62085` vs `0.61298`

## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)
- **Método**: `temporal_matchday_block_bootstrap` (11 bloques temporales)
- **Intervalo de Confianza 95% del ROI**: `[-55.10%, +25.28%]`
- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: `SÍ (No se puede descartar azar)`

## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)
- **Muestra OOS evaluada**: `85` partidos
- **Criterio de selección**: `OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)`
- **¿Supera al modelo vigente en Brier y Log Loss?**: `False`
- **¿Supera al Baseline en Brier y Log Loss?**: `True`
- **Recomendación de promoción**: `MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)`
