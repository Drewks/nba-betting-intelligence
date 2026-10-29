---
date_generated: 2026-10-29T00:23:32Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-10-29
predictions_count: 28
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-10-29

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-10-29T00:23:32Z`
- **Jornada evaluada**: `2026-10-29`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `7`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `28`
- **Apuestas simuladas registradas en la jornada**: `3` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `25`
- **Resultados pendientes globales**: `8`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `SAS @ UTA` | `moneyline` | **HOME** | — | 5.700 | 0.1754 | 0.5947 | +238.95% | `DraftKings` |
| `HOU @ MIL` | `moneyline` | **HOME** | — | 3.700 | 0.2703 | 0.6085 | +125.13% | `DraftKings` |
| `DEN @ NOP` | `total_points` | **UNDER** | 240.5 | 1.926 | 0.5192 | 0.9233 | +77.83% | `DraftKings` |
| `NYK @ CHI` | `total_points` | **UNDER** | 232.5 | 1.909 | 0.5238 | 0.8406 | +60.47% | `DraftKings` |
| `NYK @ CHI` | `moneyline` | **HOME** | — | 3.250 | 0.3077 | 0.4860 | +57.96% | `DraftKings` |
| `OKC @ DAL` | `moneyline` | **HOME** | — | 2.700 | 0.3704 | 0.5418 | +46.27% | `DraftKings` |
| `DEN @ NOP` | `moneyline` | **HOME** | — | 2.500 | 0.4000 | 0.5609 | +40.22% | `DraftKings` |
| `GSW @ MIN` | `total_points` | **UNDER** | 227.5 | 1.952 | 0.5122 | 0.6019 | +17.51% | `DraftKings` |
| `LAL @ LAC` | `moneyline` | **HOME** | — | 1.893 | 0.5283 | 0.6093 | +15.34% | `DraftKings` |
| `LAL @ LAC` | `total_points` | **OVER** | 224.5 | 1.909 | 0.5238 | 0.5568 | +6.29% | `DraftKings` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261029_8C50AADC` | `ESPN_401909887_2026-10-29_HOU_AT_MIL` | `moneyline` | **HOME** | 3.700 | 0.6085 | +125.13% | S/1.00 | `PENDING` | PENDIENTE |
| `BET_20261029_76C79ACD` | `ESPN_401909889_2026-10-29_DEN_AT_NOP` | `total_points` | **UNDER** | 1.926 | 0.9233 | +77.83% | S/1.00 | `PENDING` | PENDIENTE |
| `BET_20261029_AA270B6E` | `ESPN_401909890_2026-10-29_SAS_AT_UTA` | `moneyline` | **HOME** | 5.700 | 0.5947 | +238.95% | S/1.00 | `PENDING` | PENDIENTE |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909886_2026-10-29_NYK_AT_CHI` (`total_points` - `UNDER`): **NO_BET** [MATCHDAY_CAP_REACHED] — Matchday cap of 3 selections reached
- `ESPN_401909886_2026-10-29_NYK_AT_CHI` (`moneyline` - `HOME`): **NO_BET** [MATCHDAY_CAP_REACHED] — Matchday cap of 3 selections reached
- `ESPN_401909889_2026-10-29_DEN_AT_NOP` (`moneyline` - `HOME`): **NO_BET** [MATCHDAY_CAP_REACHED] — Matchday cap of 3 selections reached
- `ESPN_401909888_2026-10-29_GSW_AT_MIN` (`total_points` - `UNDER`): **NO_BET** [MATCHDAY_CAP_REACHED] — Matchday cap of 3 selections reached
- `ESPN_401909888_2026-10-29_GSW_AT_MIN` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 4.17% <= threshold 5.00%
- `ESPN_401909887_2026-10-29_HOU_AT_MIL` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -2.63% <= threshold 5.00%
- `ESPN_401909887_2026-10-29_HOU_AT_MIL` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -6.28% <= threshold 5.00%
- `ESPN_401909888_2026-10-29_GSW_AT_MIN` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -15.63% <= threshold 5.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
