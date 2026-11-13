---
date_generated: 2026-11-13T21:25:07Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-11-13
predictions_count: 8
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-13

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-11-13T21:25:07Z`
- **Jornada evaluada**: `2026-11-13`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `4`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `8`
- **Apuestas simuladas registradas en la jornada**: `0` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `8`
- **Resultados pendientes globales**: `0`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `CHA @ PHX` | `total_points` | **OVER** | 214.5 | 1.909 | 0.5238 | 0.5339 | +1.93% | `DraftKings` |
| `TOR @ PHI` | `total_points` | **UNDER** | 223.5 | 1.909 | 0.5238 | 0.5249 | +0.21% | `DraftKings` |
| `DAL @ MIN` | `total_points` | **UNDER** | 225.5 | 1.909 | 0.5238 | 0.5152 | -1.64% | `DraftKings` |
| `DET @ WAS` | `total_points` | **UNDER** | 221.5 | 1.909 | 0.5238 | 0.5137 | -1.92% | `DraftKings` |
| `DET @ WAS` | `total_points` | **OVER** | 221.5 | 1.909 | 0.5238 | 0.4863 | -7.17% | `DraftKings` |
| `DAL @ MIN` | `total_points` | **OVER** | 225.5 | 1.909 | 0.5238 | 0.4848 | -7.45% | `DraftKings` |
| `TOR @ PHI` | `total_points` | **OVER** | 223.5 | 1.909 | 0.5238 | 0.4751 | -9.30% | `DraftKings` |
| `CHA @ PHX` | `total_points` | **UNDER** | 214.5 | 1.909 | 0.5238 | 0.4661 | -11.02% | `DraftKings` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| — | — | — | **NO BET** | — | — | — | S/0.00 | `NO_BET` | S/0.00 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909976_2026-11-13_TOR_AT_PHI` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.21% <= threshold 5.00%
- `ESPN_401909977_2026-11-13_DET_AT_WAS` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -1.92% <= threshold 5.00%
- `ESPN_401909977_2026-11-13_DET_AT_WAS` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -7.17% <= threshold 5.00%
- `ESPN_401909976_2026-11-13_TOR_AT_PHI` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -9.30% <= threshold 5.00%
- `ESPN_401909978_2026-11-13_DAL_AT_MIN` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -1.64% <= threshold 5.00%
- `ESPN_401909978_2026-11-13_DAL_AT_MIN` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -7.45% <= threshold 5.00%
- `ESPN_401909979_2026-11-13_CHA_AT_PHX` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.93% <= threshold 5.00%
- `ESPN_401909979_2026-11-13_CHA_AT_PHX` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -11.02% <= threshold 5.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
