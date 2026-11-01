---
date_generated: 2026-11-01T17:11:29Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-11-01
predictions_count: 24
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-01

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-11-01T17:11:29Z`
- **Jornada evaluada**: `2026-11-01`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `6`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `24`
- **Apuestas simuladas registradas en la jornada**: `3` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `21`
- **Resultados pendientes globales**: `2`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `MIN @ SAS` | `moneyline` | **AWAY** | — | 5.400 | 0.1852 | 0.2079 | +12.25% | `DraftKings` |
| `SAC @ MEM` | `moneyline` | **AWAY** | — | 4.400 | 0.2273 | 0.2412 | +6.12% | `DraftKings` |
| `BOS @ ORL` | `moneyline` | **HOME** | — | 3.300 | 0.3030 | 0.3204 | +5.73% | `Betfair (Best of 27 books)` |
| `CLE @ MIL` | `total_points` | **UNDER** | 236.5 | 1.909 | 0.5238 | 0.5464 | +4.31% | `DraftKings` |
| `BKN @ IND` | `moneyline` | **HOME** | — | 1.630 | 0.6135 | 0.6390 | +4.15% | `Betfair (Best of 26 books)` |
| `CLE @ MIL` | `moneyline` | **HOME** | — | 3.850 | 0.2597 | 0.2602 | +0.19% | `DraftKings` |
| `OKC @ HOU` | `moneyline` | **AWAY** | — | 2.200 | 0.4545 | 0.4527 | -0.41% | `DraftKings` |
| `BKN @ IND` | `total_points` | **OVER** | 230.5 | 1.930 | 0.5181 | 0.5160 | -0.42% | `Pinnacle (LineShop)` |
| `MIN @ SAS` | `total_points` | **UNDER** | 225.5 | 1.893 | 0.5283 | 0.5254 | -0.55% | `DraftKings` |
| `OKC @ HOU` | `total_points` | **OVER** | 218.5 | 1.870 | 0.5349 | 0.5190 | -2.97% | `DraftKings` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261101_B7BAE33B` | `ESPN_401909899_2026-11-01_SAC_AT_MEM` | `moneyline` | **AWAY** | 4.400 | 0.2412 | +6.12% | S/1.04 | `LOST` | S/-1.04 |
| `BET_20261101_3A37DB1F` | `ESPN_401909901_2026-11-01_MIN_AT_SAS` | `moneyline` | **AWAY** | 5.400 | 0.2079 | +12.25% | S/1.00 | `LOST` | S/-1.00 |
| `BET_20261101_C66174F8` | `ESPN_401909904_2026-11-01_BKN_AT_IND` | `moneyline` | **HOME** | 1.630 | 0.6390 | +4.15% | S/2.16 | `PENDING` | PENDIENTE |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909900_2026-11-01_CLE_AT_MIL` (`total_points` - `UNDER`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 15.5 pts (> 15); likely missing information, skipped.
- `ESPN_401909900_2026-11-01_CLE_AT_MIL` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.19% <= threshold 2.00%
- `ESPN_401909899_2026-11-01_SAC_AT_MEM` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -3.21% <= threshold 2.00%
- `ESPN_401909899_2026-11-01_SAC_AT_MEM` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -5.73% <= threshold 2.00%
- `ESPN_401909900_2026-11-01_CLE_AT_MIL` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -13.40% <= threshold 2.00%
- `ESPN_401909900_2026-11-01_CLE_AT_MIL` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -5.47% <= threshold 2.00%
- `ESPN_401909899_2026-11-01_SAC_AT_MEM` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -6.87% <= threshold 2.00%
- `ESPN_401909902_2026-11-01_OKC_AT_HOU` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -0.41% <= threshold 2.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
