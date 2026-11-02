---
date_generated: 2026-11-02T02:45:49Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-11-02
predictions_count: 8
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-02

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-11-02T02:45:49Z`
- **Jornada evaluada**: `2026-11-02`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `2`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `8`
- **Apuestas simuladas registradas en la jornada**: `2` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `6`
- **Resultados pendientes globales**: `6`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `LAC @ GSW` | `total_points` | **OVER** | 221.0 | 1.930 | 0.5181 | 0.5615 | +8.36% | `LowVig.ag (LineShop)` |
| `TOR @ LAL` | `moneyline` | **AWAY** | — | 2.670 | 0.3745 | 0.3922 | +4.73% | `1xBet (Best of 21 books)` |
| `LAC @ GSW` | `moneyline` | **HOME** | — | 1.820 | 0.5495 | 0.5692 | +3.59% | `Betfair (Best of 31 books)` |
| `TOR @ LAL` | `total_points` | **UNDER** | 227.5 | 1.930 | 0.5181 | 0.5228 | +0.90% | `Pinnacle (LineShop)` |
| `TOR @ LAL` | `moneyline` | **HOME** | — | 1.590 | 0.6289 | 0.5990 | -4.76% | `Betfair (Best of 21 books)` |
| `LAC @ GSW` | `moneyline` | **AWAY** | — | 2.180 | 0.4587 | 0.4249 | -7.38% | `Betfair (Best of 31 books)` |
| `TOR @ LAL` | `total_points` | **OVER** | 227.5 | 1.950 | 0.5128 | 0.4726 | -7.83% | `Coolbet (LineShop)` |
| `LAC @ GSW` | `total_points` | **UNDER** | 221.0 | 1.970 | 0.5076 | 0.4340 | -14.49% | `Pinnacle (LineShop)` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261102_555C3423` | `ESPN_401909906_2026-11-02_TOR_AT_LAL` | `moneyline` | **AWAY** | 2.670 | 0.3922 | +4.73% | S/1.00 | `PENDING` | PENDIENTE |
| `BET_20261102_B4E13E3C` | `ESPN_401909905_2026-11-02_LAC_AT_GSW` | `moneyline` | **HOME** | 1.820 | 0.5692 | +3.59% | S/1.41 | `PENDING` | PENDIENTE |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909906_2026-11-02_TOR_AT_LAL` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.90% <= threshold 2.00%
- `ESPN_401909906_2026-11-02_TOR_AT_LAL` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -4.76% <= threshold 2.00%
- `ESPN_401909906_2026-11-02_TOR_AT_LAL` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -7.83% <= threshold 2.00%
- `ESPN_401909905_2026-11-02_LAC_AT_GSW` (`total_points` - `OVER`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 20.5 pts (> 15); likely missing information, skipped.
- `ESPN_401909905_2026-11-02_LAC_AT_GSW` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -7.38% <= threshold 2.00%
- `ESPN_401909905_2026-11-02_LAC_AT_GSW` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -14.49% <= threshold 2.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
