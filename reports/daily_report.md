---
date_generated: 2026-11-16T02:00:49Z
report_type: daily_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
period_evaluated: 2026-11-16
predictions_count: 142
observed_settled_bets: 29
observed_bankroll_pen: 94.30
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-16

## 1. Metadatos de Ejecución y Estado de Banca Observada
- **Fecha de generación (UTC)**: `2026-11-16T02:00:49Z`
- **Jornada evaluada**: `2026-11-16`
- **Versión de modelo activa**: `model_f_ensemble_v8` (Submodelos `model_b_elo_v8`, `model_c_point_margin_v8`, `model_d_total_points_v8`, `model_e_lightgbm_v8`, `model_g_ml_montecarlo_v8`)
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll observado liquidado actual**: **`S/94.30 PEN`** (`S/-5.70 PEN` en `29` apuestas observadas liquidadas)
- **Modo de apuesta activo**: `Kelly Fraccional (25%) | Máx. 3 selecciones/jornada | EV >= 2.0%`
- **Partidos evaluados**: `3`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `142`
- **Apuestas simuladas registradas en la jornada**: `2` (límite diario: 3, Kelly Fraccional (25%), EV >= 2.0%)
- **Decisiones NO_BET registradas**: `162`
- **Resultados pendientes globales**: `2`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `ATL @ MIL` | `total_points` | **UNDER** | 234.5 | 1.926 | 0.5192 | 0.5461 | +5.17% | `Pinnacle [LIVE_API]` |
| `ATL @ MIL` | `total_points` | **UNDER** | 232.0 | 1.943 | 0.5146 | 0.5163 | +2.50% | `Pinnacle [LIVE_API]` |
| `ATL @ MIL` | `total_points` | **UNDER** | 232.0 | 1.943 | 0.5146 | 0.5163 | +2.50% | `Pinnacle [LIVE_API]` |
| `ATL @ MIL` | `total_points` | **UNDER** | 232.0 | 1.943 | 0.5146 | 0.5163 | +2.50% | `Pinnacle [LIVE_API]` |
| `ATL @ MIL` | `total_points` | **UNDER** | 232.0 | 1.943 | 0.5146 | 0.5153 | +2.32% | `Pinnacle [LIVE_API]` |
| `HOU @ WAS` | `moneyline` | **AWAY** | — | 1.330 | 0.7519 | 0.7689 | +2.26% | `Matchbook (Best of 32 books)` |
| `ATL @ MIL` | `total_points` | **UNDER** | 232.0 | 1.943 | 0.5146 | 0.5143 | +2.13% | `Pinnacle [LIVE_API]` |
| `ATL @ MIL` | `total_points` | **UNDER** | 232.5 | 1.909 | 0.5238 | 0.5342 | +1.99% | `Draft Kings` |
| `ATL @ MIL` | `total_points` | **UNDER** | 232.5 | 1.909 | 0.5238 | 0.5320 | +1.56% | `DraftKings` |
| `HOU @ WAS` | `spread` | **AWAY** | -8.0 | 1.962 | 0.5098 | 0.5008 | +0.86% | `Pinnacle [LIVE_API]` |

## 4. Apuestas Simuladas (Paper Trading — Banca Observada S/94.30 PEN en 29 Apuestas Liquidadas)

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261116_26DB932D` | `ESPN_401909991_2026-11-16_HOU_AT_WAS` | `moneyline` | **AWAY** | 1.330 | 0.7689 | +2.26% | S/1.60 | `PENDING` | PENDIENTE |
| `BET_20261116_C719CA5F` | `ESPN_401909992_2026-11-16_ATL_AT_MIL` | `total_points` | **UNDER** | 1.926 | 0.5461 | +5.17% | S/1.30 | `PENDING` | PENDIENTE |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909991_2026-11-16_HOU_AT_WAS` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.16% <= threshold 2.00%
- `ESPN_401909991_2026-11-16_HOU_AT_WAS` (`spread` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -2.01% <= threshold 2.00%
- `ESPN_401909991_2026-11-16_HOU_AT_WAS` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -2.84% <= threshold 2.00%
- `ESPN_401909991_2026-11-16_HOU_AT_WAS` (`spread` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -3.64% <= threshold 2.00%
- `ESPN_401909991_2026-11-16_HOU_AT_WAS` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -3.70% <= threshold 2.00%
- `ESPN_401909991_2026-11-16_HOU_AT_WAS` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -3.74% <= threshold 2.00%
- `ESPN_401909991_2026-11-16_HOU_AT_WAS` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -5.35% <= threshold 2.00%
- `ESPN_401909991_2026-11-16_HOU_AT_WAS` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -17.36% <= threshold 2.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual inicial de **S/100.00 PEN** (bankroll observado liquidado actual: **S/94.30 PEN** en **29** apuestas observadas).
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
