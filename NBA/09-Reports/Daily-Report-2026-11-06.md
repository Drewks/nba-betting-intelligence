---
date_generated: 2026-11-06T14:23:24Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-11-06
predictions_count: 20
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-06

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-11-06T14:23:24Z`
- **Jornada evaluada**: `2026-11-06`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `2`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `20`
- **Apuestas simuladas registradas en la jornada**: `1` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `19`
- **Resultados pendientes globales**: `3`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `MIA @ GSW` | `moneyline` | **AWAY** | — | 3.550 | 0.2817 | 0.3080 | +9.35% | `BetRivers (Best of 29 books)` |
| `ORL @ PHX` | `moneyline` | **HOME** | — | 1.910 | 0.5236 | 0.5352 | +2.23% | `Matchbook (Best of 29 books)` |
| `MIA @ GSW` | `moneyline` | **HOME** | — | 1.621 | 0.6169 | 0.6119 | -0.80% | `DraftKings` |
| `MIA @ GSW` | `moneyline` | **HOME** | — | 1.621 | 0.6169 | 0.6069 | -1.61% | `DraftKings` |
| `MIA @ GSW` | `moneyline` | **HOME** | — | 1.599 | 0.6255 | 0.6127 | -2.04% | `DraftKings` |
| `MIA @ GSW` | `total_points` | **UNDER** | 235.5 | 1.940 | 0.5155 | 0.5023 | -2.56% | `Matchbook (LineShop)` |
| `MIA @ GSW` | `total_points` | **OVER** | 235.5 | 1.877 | 0.5327 | 0.5186 | -2.65% | `DraftKings` |
| `MIA @ GSW` | `total_points` | **OVER** | 235.5 | 1.877 | 0.5327 | 0.5172 | -2.91% | `DraftKings` |
| `MIA @ GSW` | `total_points` | **OVER** | 235.5 | 1.877 | 0.5327 | 0.5172 | -2.91% | `DraftKings` |
| `ORL @ PHX` | `total_points` | **UNDER** | 224.0 | 1.930 | 0.5181 | 0.5018 | -3.16% | `Pinnacle (LineShop)` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261106_92B26B33` | `ESPN_401909936_2026-11-06_ORL_AT_PHX` | `moneyline` | **HOME** | 1.910 | 0.5352 | +2.23% | S/1.39 | `WON` | S/+1.26 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909937_2026-11-06_MIA_AT_GSW` (`moneyline` - `AWAY`): **NO_BET** [EXCESSIVE_LONGSHOT_VARIANCE] — Longshot odds 3.55 (> 3.50) require EV >= 15.0% (observed: 9.35%); skipped to protect bankroll.
- `ESPN_401909937_2026-11-06_MIA_AT_GSW` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -2.56% <= threshold 2.00%
- `ESPN_401909936_2026-11-06_ORL_AT_PHX` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -3.16% <= threshold 2.00%
- `ESPN_401909936_2026-11-06_ORL_AT_PHX` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -4.02% <= threshold 2.00%
- `ESPN_401909936_2026-11-06_ORL_AT_PHX` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -3.84% <= threshold 2.00%
- `ESPN_401909937_2026-11-06_MIA_AT_GSW` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -4.37% <= threshold 2.00%
- `ESPN_401909937_2026-11-06_MIA_AT_GSW` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -5.46% <= threshold 2.00%
- `ESPN_401909937_2026-11-06_MIA_AT_GSW` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -0.80% <= threshold 2.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
