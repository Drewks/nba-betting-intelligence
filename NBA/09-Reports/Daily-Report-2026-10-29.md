---
date_generated: 2026-10-29T00:29:39Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-10-29
predictions_count: 12
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-10-29

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-10-29T00:29:39Z`
- **Jornada evaluada**: `2026-10-29`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `3`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `12`
- **Apuestas simuladas registradas en la jornada**: `2` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `10`
- **Resultados pendientes globales**: `4`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `SAS @ UTA` | `moneyline` | **HOME** | — | 6.500 | 0.1538 | 0.3576 | +132.43% | `DraftKings` |
| `OKC @ DAL` | `moneyline` | **HOME** | — | 2.600 | 0.3846 | 0.4545 | +18.18% | `DraftKings` |
| `LAL @ LAC` | `moneyline` | **HOME** | — | 1.893 | 0.5283 | 0.5760 | +9.03% | `DraftKings` |
| `OKC @ DAL` | `total_points` | **UNDER** | 228.5 | 1.909 | 0.5238 | 0.5461 | +4.25% | `DraftKings` |
| `SAS @ UTA` | `total_points` | **UNDER** | 232.5 | 1.952 | 0.5122 | 0.5256 | +2.62% | `DraftKings` |
| `LAL @ LAC` | `total_points` | **UNDER** | 224.5 | 1.909 | 0.5238 | 0.5030 | -3.97% | `DraftKings` |
| `LAL @ LAC` | `total_points` | **OVER** | 224.5 | 1.909 | 0.5238 | 0.4970 | -5.12% | `DraftKings` |
| `SAS @ UTA` | `total_points` | **OVER** | 232.5 | 1.870 | 0.5349 | 0.4744 | -11.31% | `DraftKings` |
| `OKC @ DAL` | `total_points` | **OVER** | 228.5 | 1.909 | 0.5238 | 0.4539 | -13.34% | `DraftKings` |
| `OKC @ DAL` | `moneyline` | **AWAY** | — | 1.521 | 0.6575 | 0.5455 | -17.04% | `DraftKings` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261029_E0D6A661` | `ESPN_401909891_2026-10-29_OKC_AT_DAL` | `moneyline` | **HOME** | 2.600 | 0.4545 | +18.18% | S/1.00 | `PENDING` | PENDIENTE |
| `BET_20261029_D2645895` | `ESPN_401909892_2026-10-29_LAL_AT_LAC` | `moneyline` | **HOME** | 1.893 | 0.5760 | +9.03% | S/1.00 | `PENDING` | PENDIENTE |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909890_2026-10-29_SAS_AT_UTA` (`moneyline` - `HOME`): **NO_BET** [UNVERIFIED_INJURY_OR_LINEUP_OUTLIER] — Extreme EV (132.43%) indicates likely star injury/rest not in team-level features; skipped.
- `ESPN_401909891_2026-10-29_OKC_AT_DAL` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 4.25% <= threshold 5.00%
- `ESPN_401909890_2026-10-29_SAS_AT_UTA` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 2.62% <= threshold 5.00%
- `ESPN_401909890_2026-10-29_SAS_AT_UTA` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -11.31% <= threshold 5.00%
- `ESPN_401909891_2026-10-29_OKC_AT_DAL` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -13.34% <= threshold 5.00%
- `ESPN_401909891_2026-10-29_OKC_AT_DAL` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -17.04% <= threshold 5.00%
- `ESPN_401909890_2026-10-29_SAS_AT_UTA` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -27.73% <= threshold 5.00%
- `ESPN_401909892_2026-10-29_LAL_AT_LAC` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -3.97% <= threshold 5.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
