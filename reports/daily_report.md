---
date_generated: 2026-11-15T03:22:58Z
report_type: daily_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
period_evaluated: 2026-11-15
predictions_count: 43
observed_settled_bets: 28
observed_bankroll_pen: 93.47
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-15

## 1. Metadatos de Ejecución y Estado de Banca Observada
- **Fecha de generación (UTC)**: `2026-11-15T03:22:58Z`
- **Jornada evaluada**: `2026-11-15`
- **Versión de modelo activa**: `model_f_ensemble_v8` (Submodelos `model_b_elo_v8`, `model_c_point_margin_v8`, `model_d_total_points_v8`, `model_e_lightgbm_v8`, `model_g_ml_montecarlo_v8`)
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll observado liquidado actual**: **`S/93.47 PEN`** (`S/-6.53 PEN` en `28` apuestas observadas liquidadas)
- **Modo de apuesta activo**: `Kelly Fraccional (25%) | Máx. 3 selecciones/jornada | EV >= 2.0%`
- **Partidos evaluados**: `11`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `43`
- **Apuestas simuladas registradas en la jornada**: `1` (límite diario: 3, Kelly Fraccional (25%), EV >= 2.0%)
- **Decisiones NO_BET registradas**: `49`
- **Resultados pendientes globales**: `2`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `IND @ PHI` | `moneyline` | **HOME** | — | 1.390 | 0.7194 | 0.7486 | +4.05% | `Betano Perú [LIVE_API]` |
| `NYK @ TOR` | `total_points` | **UNDER** | 217.5 | 1.935 | 0.5169 | 0.5203 | +0.66% | `Pinnacle [LIVE_API]` |
| `NYK @ TOR` | `total_points` | **UNDER** | 217.5 | 1.935 | 0.5169 | 0.5196 | +0.53% | `Pinnacle [LIVE_API]` |
| `SAS @ UTA` | `total_points` | **UNDER** | 223.5 | 1.935 | 0.5169 | 0.5193 | +0.46% | `Pinnacle [LIVE_API]` |
| `SAS @ UTA` | `total_points` | **UNDER** | 223.5 | 1.910 | 0.5236 | 0.5257 | +0.41% | `Betano Perú [LIVE_API]` |
| `SAS @ UTA` | `total_points` | **UNDER** | 224.5 | 1.909 | 0.5238 | 0.5258 | +0.39% | `DraftKings` |
| `SAS @ UTA` | `moneyline` | **AWAY** | — | 1.070 | 0.9346 | 0.9360 | +0.15% | `Betano Perú [LIVE_API]` |
| `NYK @ TOR` | `moneyline` | **AWAY** | — | 1.600 | 0.6250 | 0.6234 | -0.26% | `Betano Perú [LIVE_API]` |
| `SAS @ UTA` | `spread` | **HOME** | 17.0 | 1.962 | 0.5098 | 0.4945 | -0.35% | `Pinnacle [LIVE_API]` |
| `SAS @ UTA` | `spread` | **HOME** | 17.0 | 1.962 | 0.5098 | 0.4945 | -0.35% | `Pinnacle [LIVE_API]` |

## 4. Apuestas Simuladas (Paper Trading — Banca Observada S/93.47 PEN en 28 Apuestas Liquidadas)

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261115_AC75427D` | `ESPN_401909985_2026-11-15_IND_AT_PHI` | `moneyline` | **HOME** | 1.390 | 0.7486 | +4.05% | S/2.43 | `PENDING` | PENDIENTE |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909985_2026-11-15_IND_AT_PHI` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -0.80% <= threshold 2.00%
- `ESPN_401909985_2026-11-15_IND_AT_PHI` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -1.88% <= threshold 2.00%
- `ESPN_401909985_2026-11-15_IND_AT_PHI` (`spread` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -6.45% <= threshold 2.00%
- `ESPN_401909985_2026-11-15_IND_AT_PHI` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -7.20% <= threshold 2.00%
- `ESPN_401909985_2026-11-15_IND_AT_PHI` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -7.21% <= threshold 2.00%
- `ESPN_401909985_2026-11-15_IND_AT_PHI` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -10.81% <= threshold 2.00%
- `ESPN_401909985_2026-11-15_IND_AT_PHI` (`spread` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -11.55% <= threshold 2.00%
- `ESPN_401909985_2026-11-15_IND_AT_PHI` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -25.97% <= threshold 2.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual inicial de **S/100.00 PEN** (bankroll observado liquidado actual: **S/93.47 PEN** en **28** apuestas observadas).
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
