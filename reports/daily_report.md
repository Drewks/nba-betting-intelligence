---
date_generated: 2026-11-18T03:43:39Z
report_type: daily_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
period_evaluated: 2026-11-18
predictions_count: 106
observed_settled_bets: 33
observed_bankroll_pen: 97.91
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-18

## 1. Metadatos de Ejecución y Estado de Banca Observada
- **Fecha de generación (UTC)**: `2026-11-18T03:43:39Z`
- **Jornada evaluada**: `2026-11-18`
- **Versión de modelo activa**: `model_f_ensemble_v8` (Submodelos `model_b_elo_v8`, `model_c_point_margin_v8`, `model_d_total_points_v8`, `model_e_lightgbm_v8`, `model_g_ml_montecarlo_v8`)
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll observado liquidado actual**: **`S/97.91 PEN`** (`S/-2.09 PEN` en `33` apuestas observadas liquidadas)
- **Modo de apuesta activo**: `Kelly Fraccional (25%) | Máx. 3 selecciones/jornada | EV >= 2.0%`
- **Partidos evaluados**: `5`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `106`
- **Apuestas simuladas registradas en la jornada**: `0` (límite diario: 3, Kelly Fraccional (25%), EV >= 2.0%)
- **Decisiones NO_BET registradas**: `110`
- **Resultados pendientes globales**: `1`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `UTA @ LAC` | `moneyline` | **HOME** | — | 1.454 | 0.6875 | 0.7276 | +5.83% | `Pinnacle [LIVE_API]` |
| `UTA @ LAC` | `moneyline` | **HOME** | — | 1.461 | 0.6846 | 0.7236 | +5.71% | `Pinnacle [LIVE_API]` |
| `UTA @ LAC` | `moneyline` | **HOME** | — | 1.450 | 0.6894 | 0.7270 | +5.45% | `Pinnacle [LIVE_API]` |
| `POR @ MIN` | `total_points` | **UNDER** | 225.0 | 1.980 | 0.5049 | 0.5219 | +5.42% | `Pinnacle [LIVE_API]` |
| `UTA @ LAC` | `moneyline` | **HOME** | — | 1.435 | 0.6970 | 0.7344 | +5.37% | `Pinnacle [LIVE_API]` |
| `UTA @ LAC` | `spread` | **HOME** | -6.0 | 1.990 | 0.5025 | 0.5141 | +4.84% | `Pinnacle [LIVE_API]` |
| `UTA @ LAC` | `spread` | **HOME** | -6.0 | 1.952 | 0.5122 | 0.5221 | +4.48% | `Pinnacle [LIVE_API]` |
| `UTA @ LAC` | `spread` | **HOME** | -6.0 | 1.962 | 0.5098 | 0.5189 | +4.32% | `Pinnacle [LIVE_API]` |
| `UTA @ LAC` | `spread` | **HOME** | -6.0 | 1.917 | 0.5215 | 0.5286 | +3.89% | `Pinnacle [LIVE_API]` |
| `POR @ MIN` | `moneyline` | **HOME** | — | 1.725 | 0.5798 | 0.5982 | +3.17% | `Pinnacle [LIVE_API]` |

## 4. Apuestas Simuladas (Paper Trading — Banca Observada S/97.91 PEN en 33 Apuestas Liquidadas)

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| — | — | — | **NO BET** | — | — | — | S/0.00 | `NO_BET` | S/0.00 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401910006_2026-11-18_UTA_AT_LAC` (`moneyline` - `HOME`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 18.5 pts (> 15); likely missing information, skipped.
- `ESPN_401910006_2026-11-18_UTA_AT_LAC` (`spread` - `HOME`): **NO_BET** [CONFORMAL_UNCERTAINTY_TOO_WIDE] — Venn-Abers conformal prediction interval width 0.292 > 0.22; epistemic uncertainty too high.
- `ESPN_401910002_2026-11-18_NYK_AT_TOR` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.47% <= threshold 2.00%
- `ESPN_401910004_2026-11-18_DET_AT_SAS` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.42% <= threshold 2.00%
- `ESPN_401910004_2026-11-18_DET_AT_SAS` (`spread` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.02% <= threshold 2.00%
- `ESPN_401910005_2026-11-18_CHA_AT_LAL` (`spread` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -0.41% <= threshold 2.00%
- `ESPN_401910004_2026-11-18_DET_AT_SAS` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -0.61% <= threshold 2.00%
- `ESPN_401910002_2026-11-18_NYK_AT_TOR` (`spread` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -1.00% <= threshold 2.00%

## 6. Evidencia de Ventaja (CLV y Holdout hacia Adelante)

| Mercado | Partidos (señales) | CLV medio | IC95 (t, por partido) | Veredicto | Kelly aplicado |
| :--- | ---: | ---: | :--- | :--- | ---: |
| `moneyline` | 6 (6) | +0.12% | [-3.96%, +4.19%] | `INSUFFICIENT_SAMPLE` | ×1.00 |
| `total_points` | 7 (13) | -4.48% | [-7.08%, -1.89%] | `INSUFFICIENT_SAMPLE` | ×1.00 |

- **Holdout hacia adelante** (partidos desde `2026-11-15T00:00:00Z`, backtest `2026-11-18T01:49:56Z`): `14` partidos, `0` apuestas, ROI `n/d`, CLV `n/d`. Es la única evidencia fuera de muestra real.

## 7. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual inicial de **S/100.00 PEN** (bankroll observado liquidado actual: **S/97.91 PEN** en **33** apuestas observadas).
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
