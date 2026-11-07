---
date_generated: 2026-11-07T00:18:44Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-11-07
predictions_count: 162
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-07

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-11-07T00:18:44Z`
- **Jornada evaluada**: `2026-11-07`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `10`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `162`
- **Apuestas simuladas registradas en la jornada**: `3` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `159`
- **Resultados pendientes globales**: `5`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `BOS @ CHA` | `moneyline` | **HOME** | — | 3.950 | 0.2532 | 0.2886 | +14.00% | `Bovada (Best of 29 books)` |
| `BOS @ CHA` | `moneyline` | **HOME** | — | 4.500 | 0.2222 | 0.2510 | +12.95% | `Betfair (Best of 30 books)` |
| `SAS @ SAC` | `moneyline` | **HOME** | — | 9.020 | 0.1109 | 0.1236 | +11.52% | `Pinnacle (Best of 21 books)` |
| `DEN @ IND` | `moneyline` | **AWAY** | — | 1.938 | 0.5160 | 0.5630 | +9.11% | `1xBet Perú [T-6H Peru]` |
| `POR @ LAL` | `total_points` | **UNDER** | 233.5 | 1.950 | 0.5128 | 0.5574 | +8.69% | `1xBet (LineShop)` |
| `POR @ LAL` | `total_points` | **UNDER** | 233.5 | 1.950 | 0.5128 | 0.5571 | +8.64% | `1xBet (LineShop)` |
| `POR @ LAL` | `total_points` | **UNDER** | 233.5 | 1.943 | 0.5146 | 0.5559 | +8.03% | `DraftKings` |
| `TOR @ MIL` | `moneyline` | **HOME** | — | 4.070 | 0.2457 | 0.2603 | +5.96% | `1xBet (Best of 23 books)` |
| `PHI @ CLE` | `moneyline` | **HOME** | — | 2.210 | 0.4525 | 0.4792 | +5.91% | `1xBet (Best of 21 books)` |
| `POR @ LAL` | `total_points` | **UNDER** | 231.5 | 2.000 | 0.5000 | 0.5272 | +5.43% | `Pinnacle (LineShop)` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261107_CB5E045A` | `ESPN_401909289_2026-11-07_PHI_AT_CLE` | `moneyline` | **HOME** | 2.210 | 0.4792 | +5.91% | S/1.36 | `PENDING` | PENDIENTE |
| `BET_20261107_7C4523D5` | `ESPN_401909291_2026-11-07_OKC_AT_MEM` | `moneyline` | **AWAY** | 1.606 | 0.6352 | +2.03% | S/1.96 | `PENDING` | PENDIENTE |
| `BET_20261107_7EA0942D` | `ESPN_401909295_2026-11-07_SAS_AT_SAC` | `total_points` | **UNDER** | 1.930 | 0.5325 | +2.77% | S/1.68 | `PENDING` | PENDIENTE |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909292_2026-11-07_TOR_AT_MIL` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.20% <= threshold 2.00%
- `ESPN_401909295_2026-11-07_SAS_AT_SAC` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.53% <= threshold 2.00%
- `ESPN_401909295_2026-11-07_SAS_AT_SAC` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -2.42% <= threshold 2.00%
- `ESPN_401909292_2026-11-07_TOR_AT_MIL` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -0.38% <= threshold 2.00%
- `ESPN_401909289_2026-11-07_PHI_AT_CLE` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -0.64% <= threshold 2.00%
- `ESPN_401909293_2026-11-07_MIN_AT_NOP` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -1.29% <= threshold 2.00%
- `ESPN_401909293_2026-11-07_MIN_AT_NOP` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -4.39% <= threshold 2.00%
- `ESPN_401909293_2026-11-07_MIN_AT_NOP` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -3.10% <= threshold 2.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
