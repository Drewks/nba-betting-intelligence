---
date_generated: 2026-11-14T13:49:32Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-11-14
predictions_count: 36
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-14

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-11-14T13:49:32Z`
- **Jornada evaluada**: `2026-11-14`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `9`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `36`
- **Apuestas simuladas registradas en la jornada**: `0` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `36`
- **Resultados pendientes globales**: `0`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `NYK @ IND` | `moneyline` | **AWAY** | — | 1.326 | 0.7543 | 0.7940 | +5.26% | `Pinnacle [LIVE_API]` |
| `MEM @ NOP` | `moneyline` | **HOME** | — | 2.400 | 0.4167 | 0.4361 | +4.66% | `Pinnacle [LIVE_API]` |
| `ATL @ CHI` | `total_points` | **UNDER** | 246.5 | 1.870 | 0.5349 | 0.5589 | +4.49% | `Pinnacle [LIVE_API]` |
| `GSW @ SAS` | `total_points` | **OVER** | 218.5 | 1.962 | 0.5098 | 0.5290 | +3.77% | `Pinnacle [LIVE_API]` |
| `CLE @ MIA` | `moneyline` | **AWAY** | — | 2.210 | 0.4525 | 0.4673 | +3.27% | `Pinnacle [LIVE_API]` |
| `NYK @ IND` | `total_points` | **UNDER** | 219.5 | 1.917 | 0.5215 | 0.5378 | +3.12% | `Pinnacle [LIVE_API]` |
| `OKC @ LAC` | `moneyline` | **HOME** | — | 3.370 | 0.2967 | 0.3001 | +1.12% | `Pinnacle [LIVE_API]` |
| `POR @ SAC` | `total_points` | **UNDER** | 230.0 | 1.926 | 0.5192 | 0.5216 | +0.46% | `Pinnacle [LIVE_API]` |
| `CLE @ MIA` | `total_points` | **UNDER** | 236.0 | 1.990 | 0.5025 | 0.5027 | +0.05% | `Pinnacle [LIVE_API]` |
| `UTA @ HOU` | `moneyline` | **HOME** | — | 1.089 | 0.9179 | 0.9180 | +0.02% | `Pinnacle [LIVE_API]` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| — | — | — | **NO BET** | — | — | — | S/0.00 | `NO_BET` | S/0.00 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909296_2026-11-14_NYK_AT_IND` (`moneyline` - `AWAY`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 15.1 pts (> 15); likely missing information, skipped.
- `ESPN_401909296_2026-11-14_NYK_AT_IND` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 3.12% <= threshold 5.00%
- `ESPN_401909297_2026-11-14_MIL_AT_ORL` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -0.54% <= threshold 5.00%
- `ESPN_401909297_2026-11-14_MIL_AT_ORL` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -1.30% <= threshold 5.00%
- `ESPN_401909297_2026-11-14_MIL_AT_ORL` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -4.34% <= threshold 5.00%
- `ESPN_401909297_2026-11-14_MIL_AT_ORL` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -8.33% <= threshold 5.00%
- `ESPN_401909296_2026-11-14_NYK_AT_IND` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -8.91% <= threshold 5.00%
- `ESPN_401909296_2026-11-14_NYK_AT_IND` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -16.64% <= threshold 5.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
