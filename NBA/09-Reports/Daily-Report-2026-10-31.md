---
date_generated: 2026-10-31T01:01:10Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-10-31
predictions_count: 28
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-10-31

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-10-31T01:01:10Z`
- **Jornada evaluada**: `2026-10-31`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `8`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `28`
- **Apuestas simuladas registradas en la jornada**: `3` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `25`
- **Resultados pendientes globales**: `6`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `POR @ UTA` | `moneyline` | **HOME** | — | 3.220 | 0.3106 | 0.5183 | +66.88% | `Marathon Bet (Best of 22 books)` |
| `IND @ MIA` | `total_points` | **UNDER** | 239.5 | 1.909 | 0.5238 | 0.8460 | +61.50% | `DraftKings` |
| `ATL @ NOP` | `moneyline` | **HOME** | — | 2.560 | 0.3906 | 0.5527 | +41.50% | `Marathon Bet (Best of 21 books)` |
| `DEN @ PHX` | `moneyline` | **HOME** | — | 2.420 | 0.4132 | 0.5638 | +36.44% | `DraftKings` |
| `ATL @ NOP` | `total_points` | **UNDER** | 238.5 | 1.960 | 0.5102 | 0.6640 | +30.14% | `GTbets (LineShop)` |
| `HOU @ DAL` | `moneyline` | **HOME** | — | 2.600 | 0.3846 | 0.4992 | +29.78% | `DraftKings` |
| `DEN @ PHX` | `total_points` | **UNDER** | 230.5 | 1.909 | 0.5238 | 0.6633 | +26.62% | `DraftKings` |
| `LAC @ MIN` | `total_points` | **UNDER** | 221.5 | 1.909 | 0.5238 | 0.6356 | +21.34% | `DraftKings` |
| `POR @ UTA` | `total_points` | **UNDER** | 233.5 | 1.880 | 0.5319 | 0.6315 | +18.71% | `BetRivers (LineShop)` |
| `LAL @ GSW` | `total_points` | **UNDER** | 234.5 | 1.893 | 0.5283 | 0.6267 | +18.63% | `DraftKings` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261031_B0C4035D` | `ESPN_401909286_2026-10-31_DEN_AT_PHX` | `moneyline` | **HOME** | 2.420 | 0.5638 | +36.44% | S/1.00 | `PENDING` | PENDIENTE |
| `BET_20261031_BAB6D884` | `ESPN_401909283_2026-10-31_HOU_AT_DAL` | `moneyline` | **HOME** | 2.600 | 0.4992 | +29.78% | S/1.00 | `PENDING` | PENDIENTE |
| `BET_20261031_90A3CA7F` | `ESPN_401909286_2026-10-31_DEN_AT_PHX` | `total_points` | **UNDER** | 1.909 | 0.6633 | +26.62% | S/1.00 | `PENDING` | PENDIENTE |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909282_2026-10-31_IND_AT_MIA` (`total_points` - `UNDER`): **NO_BET** [UNVERIFIED_INJURY_OR_LINEUP_OUTLIER] — Extreme EV (61.50%) indicates likely star injury/rest not in team-level features; skipped.
- `ESPN_401909284_2026-10-31_LAC_AT_MIN` (`total_points` - `UNDER`): **NO_BET** [MATCHDAY_CAP_REACHED] — Matchday cap of 3 selections reached
- `ESPN_401909285_2026-10-31_LAL_AT_GSW` (`total_points` - `UNDER`): **NO_BET** [MATCHDAY_CAP_REACHED] — Matchday cap of 3 selections reached
- `ESPN_401909285_2026-10-31_LAL_AT_GSW` (`moneyline` - `HOME`): **NO_BET** [MATCHDAY_CAP_REACHED] — Matchday cap of 3 selections reached
- `ESPN_401909284_2026-10-31_LAC_AT_MIN` (`moneyline` - `HOME`): **NO_BET** [MATCHDAY_CAP_REACHED] — Matchday cap of 3 selections reached
- `ESPN_401909282_2026-10-31_IND_AT_MIA` (`moneyline` - `AWAY`): **NO_BET** [MATCHDAY_CAP_REACHED] — Matchday cap of 3 selections reached
- `ESPN_401909283_2026-10-31_HOU_AT_DAL` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.19% <= threshold 5.00%
- `ESPN_401909282_2026-10-31_IND_AT_MIA` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -9.67% <= threshold 5.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
