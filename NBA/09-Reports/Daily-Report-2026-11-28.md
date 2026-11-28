---
date_generated: 2026-11-28T15:52:51Z
report_type: daily_report
model_versions: [model_f_ensemble_v9, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v9, model_d_total_points_v9, model_e_lightgbm_v9, model_g_ml_montecarlo_v9, model_h_ridge_rapm_v9]
period_evaluated: 2026-11-28
predictions_count: 283
observed_settled_bets: 40
observed_bankroll_pen: 96.80
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-28

## 1. Metadatos de Ejecución y Estado de Banca Observada
- **Fecha de generación (UTC)**: `2026-11-28T15:52:51Z`
- **Jornada evaluada**: `2026-11-28`
- **Versión de modelo activa**: `model_f_ensemble_v9` (Submodelos `model_b_elo_v8`, `model_c_point_margin_v9`, `model_d_total_points_v9`, `model_e_lightgbm_v9`, `model_g_ml_montecarlo_v9`, `model_h_ridge_rapm_v9`)
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll observado liquidado actual**: **`S/96.80 PEN`** (`S/-3.20 PEN` en `40` apuestas observadas liquidadas)
- **Modo de apuesta activo**: `Kelly Fraccional (25%) | Máx. 3 selecciones/jornada | EV >= 2.0%`
- **Partidos evaluados**: `13`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `283`
- **Apuestas simuladas registradas en la jornada**: `1` (límite diario: 3, Kelly Fraccional (25%), EV >= 2.0%)
- **Decisiones NO_BET registradas**: `335`
- **Resultados pendientes globales**: `0`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `LAL @ SAS` | `total_points` | **UNDER** | 224.5 | 2.090 | 0.4785 | 0.5041 | +5.36% | `Marathon Bet (LineShop)` |
| `MEM @ MIN` | `moneyline` | **HOME** | — | 1.633 | 0.6124 | 0.6399 | +4.48% | `Pinnacle [LIVE_API]` |
| `ATL @ BOS` | `moneyline` | **AWAY** | — | 4.260 | 0.2347 | 0.2430 | +3.53% | `Pinnacle [LIVE_API]` |
| `MIL @ DET` | `spread` | **HOME** | -8.5 | 1.917 | 0.5215 | 0.5364 | +2.85% | `Pinnacle [LIVE_API]` |
| `MEM @ MIN` | `total_points` | **OVER** | 220.5 | 1.930 | 0.5181 | 0.5307 | +2.42% | `1xBet (LineShop)` |
| `PHI @ IND` | `total_points` | **UNDER** | 234.5 | 1.930 | 0.5181 | 0.5298 | +2.25% | `1xBet (LineShop)` |
| `GSW @ POR` | `moneyline` | **AWAY** | — | 3.530 | 0.2833 | 0.2895 | +2.19% | `Pinnacle [LIVE_API]` |
| `MIA @ NYK` | `total_points` | **OVER** | 222.5 | 2.000 | 0.5000 | 0.5109 | +2.19% | `Marathon Bet (LineShop)` |
| `MIA @ NYK` | `moneyline` | **HOME** | — | 1.610 | 0.6212 | 0.6336 | +2.00% | `Pinnacle [LIVE_API]` |
| `BKN @ TOR` | `total_points` | **OVER** | 220.0 | 1.935 | 0.5169 | 0.5152 | +1.74% | `Pinnacle [LIVE_API]` |

## 4. Apuestas Simuladas (Paper Trading — Banca Observada S/96.80 PEN en 40 Apuestas Liquidadas)

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261128_4D53638C` | `ESPN_401909331_2026-11-28_MEM_AT_MIN` | `moneyline` | **HOME** | 1.633 | 0.6399 | +4.48% | S/1.74 | `LOST` | S/-1.74 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909328_2026-11-28_PHI_AT_IND` (`total_points` - `UNDER`): **NO_BET** [KELLY_STAKE_BELOW_MINIMUM] — Fractional Kelly stake below S/1.00 (no material edge at 1.930); Kelly x0.50 by total_points CLV evidence NO_EDGE.
- `ESPN_401909334_2026-11-28_DEN_AT_UTA` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -0.19% <= threshold 2.00%
- `ESPN_401909330_2026-11-28_ATL_AT_BOS` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -0.68% <= threshold 2.00%
- `ESPN_401909326_2026-11-28_MIA_AT_NYK` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -2.92% <= threshold 2.00%
- `ESPN_401909326_2026-11-28_MIA_AT_NYK` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -3.63% <= threshold 2.00%
- `ESPN_401909330_2026-11-28_ATL_AT_BOS` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -6.32% <= threshold 2.00%
- `ESPN_401909334_2026-11-28_DEN_AT_UTA` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -6.81% <= threshold 2.00%
- `ESPN_401909328_2026-11-28_PHI_AT_IND` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -9.25% <= threshold 2.00%

## 6. Evidencia de Ventaja (CLV y Holdout hacia Adelante)

| Mercado | Partidos (señales) | CLV medio | IC95 (t, por partido) | Veredicto | Kelly aplicado |
| :--- | ---: | ---: | :--- | :--- | ---: |
| `moneyline` | 20 (26) | -1.23% | [-3.56%, +1.11%] | `INCONCLUSIVE` | ×1.00 |
| `total_points` | 29 (43) | -3.21% | [-4.90%, -1.52%] | `NO_EDGE` | ×0.50 |

- **Holdout hacia adelante** (partidos desde `2026-11-15T00:00:00Z`, backtest `2026-11-23T23:44:43Z`): `65` partidos, `0` apuestas, ROI `n/d`, CLV `n/d`. Es la única evidencia fuera de muestra real.

## 7. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual inicial de **S/100.00 PEN** (bankroll observado liquidado actual: **S/96.80 PEN** en **40** apuestas observadas).
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
