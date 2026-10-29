---
date_generated: 2026-10-29T00:44:24Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-10-29
predictions_count: 12
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-10-29

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-10-29T00:44:24Z`
- **Jornada evaluada**: `2026-10-29`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `3`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `12`
- **Apuestas simuladas registradas en la jornada**: `3` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `9`
- **Resultados pendientes globales**: `6`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `SAS @ UTA` | `moneyline` | **HOME** | — | 7.350 | 0.1361 | 0.3297 | +142.35% | `1xBet (Best of 32 books)` |
| `OKC @ DAL` | `moneyline` | **HOME** | — | 2.760 | 0.3623 | 0.4976 | +37.34% | `FanDuel (Best of 32 books)` |
| `LAL @ LAC` | `moneyline` | **HOME** | — | 1.970 | 0.5076 | 0.5985 | +17.91% | `Matchbook (Best of 32 books)` |
| `OKC @ DAL` | `total_points` | **UNDER** | 228.5 | 1.920 | 0.5208 | 0.5698 | +9.40% | `GTbets (LineShop)` |
| `SAS @ UTA` | `total_points` | **UNDER** | 233.0 | 1.940 | 0.5155 | 0.5267 | +2.18% | `Pinnacle (LineShop)` |
| `LAL @ LAC` | `total_points` | **OVER** | 224.5 | 1.960 | 0.5102 | 0.5127 | +0.49% | `Matchbook (LineShop)` |
| `LAL @ LAC` | `total_points` | **UNDER** | 224.5 | 1.990 | 0.5025 | 0.4873 | -3.03% | `Matchbook (LineShop)` |
| `SAS @ UTA` | `total_points` | **OVER** | 233.0 | 1.940 | 0.5155 | 0.4733 | -8.18% | `Coolbet (LineShop)` |
| `OKC @ DAL` | `total_points` | **OVER** | 228.5 | 2.000 | 0.5000 | 0.4302 | -13.95% | `Pinnacle (LineShop)` |
| `LAL @ LAC` | `moneyline` | **AWAY** | — | 2.020 | 0.4950 | 0.4015 | -18.90% | `Unibet (NL) (Best of 32 books)` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261029_748C9155` | `ESPN_401909891_2026-10-29_OKC_AT_DAL` | `moneyline` | **HOME** | 2.760 | 0.4976 | +37.34% | S/1.00 | `PENDING` | PENDIENTE |
| `BET_20261029_82305F66` | `ESPN_401909892_2026-10-29_LAL_AT_LAC` | `moneyline` | **HOME** | 1.970 | 0.5985 | +17.91% | S/1.00 | `PENDING` | PENDIENTE |
| `BET_20261029_C23A720D` | `ESPN_401909891_2026-10-29_OKC_AT_DAL` | `total_points` | **UNDER** | 1.920 | 0.5698 | +9.40% | S/1.00 | `PENDING` | PENDIENTE |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909890_2026-10-29_SAS_AT_UTA` (`moneyline` - `HOME`): **NO_BET** [UNVERIFIED_INJURY_OR_LINEUP_OUTLIER] — Extreme EV (142.35%) indicates likely star injury/rest not in team-level features; skipped.
- `ESPN_401909890_2026-10-29_SAS_AT_UTA` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 2.18% <= threshold 5.00%
- `ESPN_401909892_2026-10-29_LAL_AT_LAC` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.49% <= threshold 5.00%
- `ESPN_401909892_2026-10-29_LAL_AT_LAC` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -3.03% <= threshold 5.00%
- `ESPN_401909890_2026-10-29_SAS_AT_UTA` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -8.18% <= threshold 5.00%
- `ESPN_401909891_2026-10-29_OKC_AT_DAL` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -13.95% <= threshold 5.00%
- `ESPN_401909892_2026-10-29_LAL_AT_LAC` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -18.90% <= threshold 5.00%
- `ESPN_401909891_2026-10-29_OKC_AT_DAL` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -21.13% <= threshold 5.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
