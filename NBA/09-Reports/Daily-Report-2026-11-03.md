---
date_generated: 2026-11-03T18:04:08Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-11-03
predictions_count: 60
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-03

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-11-03T18:04:08Z`
- **Jornada evaluada**: `2026-11-03`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `15`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `60`
- **Apuestas simuladas registradas en la jornada**: `3` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `57`
- **Resultados pendientes globales**: `2`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `WAS @ ORL` | `moneyline` | **HOME** | — | 1.830 | 0.5464 | 0.5919 | +8.32% | `DraftKings (Best of 22 books)` |
| `TOR @ LAC` | `total_points` | **OVER** | 220.5 | 1.926 | 0.5192 | 0.5493 | +5.78% | `DraftKings` |
| `NOP @ MEM` | `moneyline` | **AWAY** | — | 2.900 | 0.3448 | 0.3630 | +5.28% | `888sport (Best of 20 books)` |
| `DET @ CHA` | `total_points` | **OVER** | 209.5 | 1.920 | 0.5208 | 0.5455 | +4.73% | `GTbets (LineShop)` |
| `CHI @ PHI` | `total_points` | **UNDER** | 238.5 | 1.910 | 0.5236 | 0.5471 | +4.50% | `DraftKings (LineShop)` |
| `DET @ CHA` | `moneyline` | **AWAY** | — | 1.630 | 0.6135 | 0.6390 | +4.16% | `FanDuel (Best of 22 books)` |
| `WAS @ ORL` | `total_points` | **OVER** | 225.5 | 1.990 | 0.5025 | 0.5178 | +3.04% | `1xBet (LineShop)` |
| `BOS @ HOU` | `total_points` | **OVER** | 219.5 | 1.990 | 0.5025 | 0.5131 | +2.11% | `1xBet (LineShop)` |
| `PHX @ GSW` | `total_points` | **OVER** | 227.5 | 1.930 | 0.5181 | 0.5265 | +1.61% | `Unibet (NL) (LineShop)` |
| `NOP @ MEM` | `total_points` | **UNDER** | 235.5 | 1.920 | 0.5208 | 0.5270 | +1.18% | `GTbets (LineShop)` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261103_E59224AE` | `ESPN_401909911_2026-11-03_WAS_AT_ORL` | `total_points` | **OVER** | 1.990 | 0.5178 | +3.04% | S/1.13 | `LOST` | S/-1.13 |
| `BET_20261103_EF0858D0` | `ESPN_401909914_2026-11-03_NOP_AT_MEM` | `moneyline` | **AWAY** | 2.900 | 0.3630 | +5.28% | S/1.00 | `WON` | S/+1.90 |
| `BET_20261103_06657F1C` | `ESPN_401909916_2026-11-03_BOS_AT_HOU` | `total_points` | **OVER** | 1.990 | 0.5131 | +2.11% | S/1.00 | `LOST` | S/-1.00 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909911_2026-11-03_WAS_AT_ORL` (`moneyline` - `HOME`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 23.2 pts (> 15); likely missing information, skipped.
- `ESPN_401909908_2026-11-03_DET_AT_CHA` (`moneyline` - `AWAY`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 16.5 pts (> 15); likely missing information, skipped.
- `ESPN_401909908_2026-11-03_DET_AT_CHA` (`total_points` - `OVER`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 15.2 pts (> 15); likely missing information, skipped.
- `ESPN_401909912_2026-11-03_CHI_AT_PHI` (`total_points` - `UNDER`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 15.7 pts (> 15); likely missing information, skipped.
- `ESPN_401909914_2026-11-03_NOP_AT_MEM` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.18% <= threshold 2.00%
- `ESPN_401909915_2026-11-03_MIL_AT_MIN` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.51% <= threshold 2.00%
- `ESPN_401909907_2026-11-03_OKC_AT_CLE` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.93% <= threshold 2.00%
- `ESPN_401909915_2026-11-03_MIL_AT_MIN` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.45% <= threshold 2.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
