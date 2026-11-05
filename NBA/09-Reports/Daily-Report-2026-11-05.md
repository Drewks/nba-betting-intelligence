---
date_generated: 2026-11-05T22:50:22Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-11-05
predictions_count: 56
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-05

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-11-05T22:50:22Z`
- **Jornada evaluada**: `2026-11-05`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `14`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `56`
- **Apuestas simuladas registradas en la jornada**: `3` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `53`
- **Resultados pendientes globales**: `2`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `MIA @ LAC` | `moneyline` | **HOME** | — | 2.700 | 0.3704 | 0.4208 | +13.62% | `Bovada (Best of 17 books)` |
| `LAL @ SAC` | `moneyline` | **HOME** | — | 6.660 | 0.1502 | 0.1638 | +9.10% | `1xBet (Best of 18 books)` |
| `MIN @ HOU` | `moneyline` | **AWAY** | — | 4.000 | 0.2500 | 0.2717 | +8.67% | `888sport (Best of 23 books)` |
| `TOR @ DEN` | `moneyline` | **AWAY** | — | 2.900 | 0.3448 | 0.3720 | +7.89% | `Bovada (Best of 23 books)` |
| `DAL @ SAS` | `moneyline` | **AWAY** | — | 7.000 | 0.1429 | 0.1529 | +7.06% | `Bovada (Best of 23 books)` |
| `CHA @ BKN` | `total_points` | **OVER** | 214.5 | 1.950 | 0.5128 | 0.5455 | +6.38% | `1xBet (LineShop)` |
| `ATL @ WAS` | `total_points` | **UNDER** | 234.5 | 1.920 | 0.5208 | 0.5535 | +6.28% | `GTbets (LineShop)` |
| `LAL @ SAC` | `total_points` | **UNDER** | 238.5 | 1.910 | 0.5236 | 0.5474 | +4.55% | `BetMGM (LineShop)` |
| `UTA @ NOP` | `moneyline` | **HOME** | — | 1.550 | 0.6452 | 0.6706 | +3.94% | `1xBet (Best of 25 books)` |
| `CLE @ OKC` | `moneyline` | **HOME** | — | 1.770 | 0.5650 | 0.5854 | +3.61% | `FanDuel (Best of 3 books)` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261105_63E8261D` | `ESPN_401909929_2026-11-05_CLE_AT_OKC` | `moneyline` | **HOME** | 1.770 | 0.5854 | +3.61% | S/2.19 | `WON` | S/+1.69 |
| `BET_20261105_11DC3E0B` | `ESPN_401909922_2026-11-05_PHI_AT_DET` | `moneyline` | **HOME** | 1.810 | 0.5663 | +2.51% | S/1.57 | `LOST` | S/-1.57 |
| `BET_20261105_A563FA74` | `ESPN_401909931_2026-11-05_TOR_AT_DEN` | `moneyline` | **AWAY** | 2.900 | 0.3720 | +7.89% | S/1.10 | `LOST` | S/-1.10 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909925_2026-11-05_CHA_AT_BKN` (`total_points` - `OVER`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 16.9 pts (> 15); likely missing information, skipped.
- `ESPN_401909930_2026-11-05_MIN_AT_HOU` (`moneyline` - `AWAY`): **NO_BET** [EXCESSIVE_LONGSHOT_VARIANCE] — Longshot odds 4.00 (> 3.50) require EV >= 15.0% (observed: 8.67%); skipped to protect bankroll.
- `ESPN_401909925_2026-11-05_CHA_AT_BKN` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.90% <= threshold 2.00%
- `ESPN_401909933_2026-11-05_DAL_AT_SAS` (`moneyline` - `AWAY`): **NO_BET** [EXCESSIVE_LONGSHOT_VARIANCE] — Longshot odds 7.00 (> 3.50) require EV >= 15.0% (observed: 7.06%); skipped to protect bankroll.
- `ESPN_401909933_2026-11-05_DAL_AT_SAS` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -0.37% <= threshold 2.00%
- `ESPN_401909929_2026-11-05_CLE_AT_OKC` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -0.49% <= threshold 2.00%
- `ESPN_401909922_2026-11-05_PHI_AT_DET` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -0.81% <= threshold 2.00%
- `ESPN_401909930_2026-11-05_MIN_AT_HOU` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -1.89% <= threshold 2.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
