---
date_generated: 2026-10-30T19:52:57Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-10-30
predictions_count: 32
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-10-30

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-10-30T19:52:57Z`
- **Jornada evaluada**: `2026-10-30`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `8`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `32`
- **Apuestas simuladas registradas en la jornada**: `3` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `29`
- **Resultados pendientes globales**: `3`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `DET @ BKN` | `moneyline` | **HOME** | — | 3.100 | 0.3226 | 0.5039 | +56.20% | `DraftKings` |
| `NYK @ PHI` | `total_points` | **UNDER** | 228.5 | 1.909 | 0.5238 | 0.7844 | +49.74% | `DraftKings` |
| `MEM @ POR` | `moneyline` | **AWAY** | — | 3.540 | 0.2825 | 0.4206 | +48.88% | `1xBet (Best of 23 books)` |
| `CHI @ BOS` | `total_points` | **UNDER** | 233.5 | 1.952 | 0.5122 | 0.6719 | +31.19% | `DraftKings` |
| `CLE @ ATL` | `total_points` | **UNDER** | 237.5 | 1.980 | 0.5051 | 0.6612 | +30.91% | `Pinnacle (LineShop)` |
| `SAC @ NOP` | `total_points` | **UNDER** | 237.5 | 1.950 | 0.5128 | 0.6685 | +30.37% | `Coolbet (LineShop)` |
| `MEM @ POR` | `total_points` | **UNDER** | 232.5 | 1.910 | 0.5236 | 0.6347 | +21.23% | `DraftKings (LineShop)` |
| `ORL @ TOR` | `total_points` | **UNDER** | 224.5 | 1.909 | 0.5238 | 0.6232 | +18.97% | `DraftKings` |
| `CHA @ WAS` | `moneyline` | **HOME** | — | 1.909 | 0.5238 | 0.6050 | +15.50% | `DraftKings` |
| `NYK @ PHI` | `moneyline` | **HOME** | — | 2.000 | 0.5000 | 0.5693 | +13.86% | `DraftKings` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261030_26E1FE60` | `ESPN_401909894_2026-10-30_SAC_AT_NOP` | `total_points` | **UNDER** | 1.950 | 0.6685 | +30.37% | S/1.00 | `LOST` | S/-1.00 |
| `BET_20261030_0F72AE2C` | `ESPN_401909894_2026-10-30_SAC_AT_NOP` | `moneyline` | **HOME** | 1.520 | 0.7168 | +8.96% | S/1.00 | `WON` | S/+0.52 |
| `BET_20261030_A239BFAF` | `ESPN_401909895_2026-10-30_MEM_AT_POR` | `total_points` | **UNDER** | 1.910 | 0.6347 | +21.23% | S/1.00 | `WON` | S/+0.91 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909894_2026-10-30_SAC_AT_NOP` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -23.83% <= threshold 5.00%
- `ESPN_401909894_2026-10-30_SAC_AT_NOP` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -36.03% <= threshold 5.00%
- `ESPN_401909895_2026-10-30_MEM_AT_POR` (`moneyline` - `AWAY`): **NO_BET** [UNVERIFIED_INJURY_OR_LINEUP_OUTLIER] — Extreme EV (48.88%) indicates likely star injury/rest not in team-level features; skipped.
- `ESPN_401909895_2026-10-30_MEM_AT_POR` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -18.88% <= threshold 5.00%
- `ESPN_401909895_2026-10-30_MEM_AT_POR` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -29.50% <= threshold 5.00%
- `ESPN_401909893_2026-10-30_CLE_AT_ATL` (`total_points` - `UNDER`): **NO_BET** [MATCHDAY_CAP_REACHED] — Matchday cap of 3 selections reached
- `ESPN_401909893_2026-10-30_CLE_AT_ATL` (`moneyline` - `HOME`): **NO_BET** [MATCHDAY_CAP_REACHED] — Matchday cap of 3 selections reached
- `ESPN_401909893_2026-10-30_CLE_AT_ATL` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -13.01% <= threshold 5.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
