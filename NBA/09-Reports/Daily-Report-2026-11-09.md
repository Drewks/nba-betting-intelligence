---
date_generated: 2026-11-09T01:01:03Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-11-09
predictions_count: 34
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-09

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-11-09T01:01:03Z`
- **Jornada evaluada**: `2026-11-09`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `5`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `34`
- **Apuestas simuladas registradas en la jornada**: `2` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `32`
- **Resultados pendientes globales**: `3`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `UTA @ MIN` | `moneyline` | **HOME** | — | 1.917 | 0.5216 | 0.6166 | +18.20% | `1xBet Perú [T-6H Peru]` |
| `BOS @ MIL` | `moneyline` | **AWAY** | — | 1.917 | 0.5216 | 0.5841 | +11.96% | `1xBet Perú [T-6H Peru]` |
| `BKN @ DAL` | `moneyline` | **HOME** | — | 1.917 | 0.5216 | 0.5587 | +7.10% | `1xBet Perú [T-6H Peru]` |
| `NOP @ LAC` | `moneyline` | **HOME** | — | 1.917 | 0.5216 | 0.5427 | +4.03% | `1xBet Perú [T-6H Peru]` |
| `MIA @ SAC` | `moneyline` | **AWAY** | — | 1.917 | 0.5216 | 0.5353 | +2.62% | `1xBet Perú [T-6H Peru]` |
| `UTA @ MIN` | `total_points` | **OVER** | 222.5 | 1.909 | 0.5238 | 0.5243 | +0.10% | `Draft Kings` |
| `UTA @ MIN` | `total_points` | **OVER** | 222.5 | 1.909 | 0.5238 | 0.5243 | +0.09% | `DraftKings` |
| `UTA @ MIN` | `moneyline` | **HOME** | — | 1.143 | 0.8750 | 0.8717 | -0.37% | `Draft Kings` |
| `UTA @ MIN` | `moneyline` | **HOME** | — | 1.143 | 0.8750 | 0.8714 | -0.41% | `DraftKings` |
| `BKN @ DAL` | `moneyline` | **HOME** | — | 1.328 | 0.7531 | 0.7448 | -1.09% | `DraftKings` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261109_A985B0D3` | `ESPN_401909950_2026-11-09_NOP_AT_LAC` | `moneyline` | **HOME** | 1.917 | 0.5427 | +4.03% | S/2.00 | `PENDING` | PENDIENTE |
| `BET_20261109_0E342DCD` | `ESPN_401909951_2026-11-09_MIA_AT_SAC` | `moneyline` | **AWAY** | 1.917 | 0.5353 | +2.62% | S/2.00 | `PENDING` | PENDIENTE |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909947_2026-11-09_UTA_AT_MIN` (`moneyline` - `HOME`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 38.9 pts (> 15); likely missing information, skipped.
- `ESPN_401909949_2026-11-09_BOS_AT_MIL` (`moneyline` - `AWAY`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 28.0 pts (> 15); likely missing information, skipped.
- `ESPN_401909948_2026-11-09_BKN_AT_DAL` (`moneyline` - `HOME`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 19.6 pts (> 15); likely missing information, skipped.
- `ESPN_401909951_2026-11-09_MIA_AT_SAC` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -10.92% <= threshold 2.00%
- `ESPN_401909950_2026-11-09_NOP_AT_LAC` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -12.33% <= threshold 2.00%
- `ESPN_401909948_2026-11-09_BKN_AT_DAL` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -15.40% <= threshold 2.00%
- `ESPN_401909949_2026-11-09_BOS_AT_MIL` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -20.26% <= threshold 2.00%
- `ESPN_401909947_2026-11-09_UTA_AT_MIN` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -26.50% <= threshold 2.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
