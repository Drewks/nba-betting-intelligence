---
date_generated: 2026-11-20T22:16:18Z
report_type: daily_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
period_evaluated: 2026-11-20
predictions_count: 58
observed_settled_bets: 35
observed_bankroll_pen: 97.20
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-20

## 1. Metadatos de Ejecución y Estado de Banca Observada
- **Fecha de generación (UTC)**: `2026-11-20T22:16:18Z`
- **Jornada evaluada**: `2026-11-20`
- **Versión de modelo activa**: `model_f_ensemble_v8` (Submodelos `model_b_elo_v8`, `model_c_point_margin_v8`, `model_d_total_points_v8`, `model_e_lightgbm_v8`, `model_g_ml_montecarlo_v8`)
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll observado liquidado actual**: **`S/97.20 PEN`** (`S/-2.80 PEN` en `35` apuestas observadas liquidadas)
- **Modo de apuesta activo**: `Kelly Fraccional (25%) | Máx. 3 selecciones/jornada | EV >= 2.0%`
- **Partidos evaluados**: `4`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `58`
- **Apuestas simuladas registradas en la jornada**: `1` (límite diario: 3, Kelly Fraccional (25%), EV >= 2.0%)
- **Decisiones NO_BET registradas**: `57`
- **Resultados pendientes globales**: `1`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `GSW @ MEM` | `moneyline` | **AWAY** | — | 3.050 | 0.3279 | 0.3514 | +7.17% | `Pinnacle [LIVE_API]` |
| `GSW @ MEM` | `moneyline` | **AWAY** | — | 2.900 | 0.3448 | 0.3691 | +7.04% | `Pinnacle [LIVE_API]` |
| `POR @ MIL` | `total_points` | **UNDER** | 229.5 | 1.930 | 0.5181 | 0.5437 | +4.93% | `Matchbook (LineShop)` |
| `LAC @ SAS` | `spread` | **AWAY** | 16.0 | 1.971 | 0.5074 | 0.5159 | +4.24% | `Pinnacle [LIVE_API]` |
| `LAC @ SAS` | `spread` | **AWAY** | 16.0 | 1.943 | 0.5146 | 0.5209 | +3.79% | `Pinnacle [LIVE_API]` |
| `LAC @ SAS` | `spread` | **AWAY** | 15.5 | 1.962 | 0.5098 | 0.5267 | +3.31% | `Pinnacle [LIVE_API]` |
| `LAC @ SAS` | `spread` | **AWAY** | 15.5 | 1.926 | 0.5192 | 0.5334 | +2.72% | `Pinnacle [LIVE_API]` |
| `NYK @ MIN` | `total_points` | **UNDER** | 216.0 | 1.962 | 0.5098 | 0.5120 | +2.55% | `Pinnacle [LIVE_API]` |
| `LAC @ SAS` | `total_points` | **UNDER** | 225.0 | 2.020 | 0.4950 | 0.4951 | +2.23% | `Pinnacle [LIVE_API]` |
| `GSW @ MEM` | `total_points` | **OVER** | 224.5 | 1.970 | 0.5076 | 0.5159 | +1.63% | `Matchbook (LineShop)` |

## 4. Apuestas Simuladas (Paper Trading — Banca Observada S/97.20 PEN en 35 Apuestas Liquidadas)

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261120_E9FA8580` | `ESPN_401910020_2026-11-20_POR_AT_MIL` | `total_points` | **UNDER** | 1.930 | 0.5437 | +4.93% | S/1.31 | `LOST` | S/-1.31 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401910022_2026-11-20_LAC_AT_SAS` (`spread` - `AWAY`): **NO_BET** [CONFORMAL_UNCERTAINTY_TOO_WIDE] — Venn-Abers conformal prediction interval width 0.292 > 0.22; epistemic uncertainty too high.
- `ESPN_401910022_2026-11-20_LAC_AT_SAS` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.50% <= threshold 2.00%
- `ESPN_401910022_2026-11-20_LAC_AT_SAS` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.06% <= threshold 2.00%
- `ESPN_401910022_2026-11-20_LAC_AT_SAS` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -3.36% <= threshold 2.00%
- `ESPN_401910022_2026-11-20_LAC_AT_SAS` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -7.25% <= threshold 2.00%
- `ESPN_401910022_2026-11-20_LAC_AT_SAS` (`spread` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -8.48% <= threshold 2.00%
- `ESPN_401910022_2026-11-20_LAC_AT_SAS` (`spread` - `AWAY`): **NO_BET** [CONFORMAL_UNCERTAINTY_TOO_WIDE] — Venn-Abers conformal prediction interval width 0.292 > 0.22; epistemic uncertainty too high.
- `ESPN_401910022_2026-11-20_LAC_AT_SAS` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.62% <= threshold 2.00%

## 6. Evidencia de Ventaja (CLV y Holdout hacia Adelante)

| Mercado | Partidos (señales) | CLV medio | IC95 (t, por partido) | Veredicto | Kelly aplicado |
| :--- | ---: | ---: | :--- | :--- | ---: |
| `moneyline` | 9 (13) | +0.91% | [-1.80%, +3.62%] | `INSUFFICIENT_SAMPLE` | ×1.00 |
| `total_points` | 16 (27) | -2.62% | [-4.99%, -0.26%] | `NO_EDGE` | ×0.50 |

- **Holdout hacia adelante** (partidos desde `2026-11-15T00:00:00Z`, backtest `2026-11-18T01:49:56Z`): `14` partidos, `0` apuestas, ROI `n/d`, CLV `n/d`. Es la única evidencia fuera de muestra real.

## 7. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual inicial de **S/100.00 PEN** (bankroll observado liquidado actual: **S/97.20 PEN** en **35** apuestas observadas).
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
