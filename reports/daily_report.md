---
date_generated: 2026-11-17T04:30:05Z
report_type: daily_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
period_evaluated: 2026-11-17
predictions_count: 48
observed_settled_bets: 33
observed_bankroll_pen: 97.91
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-17

## 1. Metadatos de Ejecución y Estado de Banca Observada
- **Fecha de generación (UTC)**: `2026-11-17T04:30:05Z`
- **Jornada evaluada**: `2026-11-17`
- **Versión de modelo activa**: `model_f_ensemble_v8` (Submodelos `model_b_elo_v8`, `model_c_point_margin_v8`, `model_d_total_points_v8`, `model_e_lightgbm_v8`, `model_g_ml_montecarlo_v8`)
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll observado liquidado actual**: **`S/97.91 PEN`** (`S/-2.09 PEN` en `33` apuestas observadas liquidadas)
- **Modo de apuesta activo**: `Kelly Fraccional (25%) | Máx. 3 selecciones/jornada | EV >= 2.0%`
- **Partidos evaluados**: `8`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `48`
- **Apuestas simuladas registradas en la jornada**: `2` (límite diario: 3, Kelly Fraccional (25%), EV >= 2.0%)
- **Decisiones NO_BET registradas**: `46`
- **Resultados pendientes globales**: `0`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `GSW @ NOP` | `total_points` | **OVER** | 224.0 | 1.971 | 0.5074 | 0.5338 | +7.16% | `Pinnacle [LIVE_API]` |
| `POR @ MIN` | `total_points` | **UNDER** | 227.5 | 1.962 | 0.5098 | 0.5330 | +4.56% | `Pinnacle [LIVE_API]` |
| `PHI @ BKN` | `total_points` | **UNDER** | 228.0 | 1.926 | 0.5192 | 0.5305 | +4.24% | `Pinnacle [LIVE_API]` |
| `POR @ MIN` | `moneyline` | **HOME** | — | 1.787 | 0.5595 | 0.5806 | +3.77% | `Pinnacle [LIVE_API]` |
| `PHI @ BKN` | `moneyline` | **AWAY** | — | 1.442 | 0.6932 | 0.7160 | +3.29% | `Pinnacle [LIVE_API]` |
| `PHX @ DEN` | `total_points` | **UNDER** | 230.0 | 2.030 | 0.4926 | 0.4967 | +2.89% | `Pinnacle [LIVE_API]` |
| `PHX @ DEN` | `spread` | **AWAY** | 9.5 | 2.040 | 0.4902 | 0.5029 | +2.58% | `Pinnacle [LIVE_API]` |
| `GSW @ NOP` | `moneyline` | **AWAY** | — | 1.667 | 0.6000 | 0.6106 | +1.77% | `Pinnacle [LIVE_API]` |
| `HOU @ MIA` | `total_points` | **UNDER** | 233.0 | 1.980 | 0.5049 | 0.4999 | +1.09% | `Pinnacle [LIVE_API]` |
| `POR @ MIN` | `spread` | **HOME** | -2.0 | 1.935 | 0.5169 | 0.5066 | +0.64% | `Pinnacle [LIVE_API]` |

## 4. Apuestas Simuladas (Paper Trading — Banca Observada S/97.91 PEN en 33 Apuestas Liquidadas)

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261117_4680E990` | `ESPN_401909999_2026-11-17_POR_AT_MIN` | `total_points` | **UNDER** | 1.962 | 0.5330 | +4.56% | S/1.14 | `WON` | S/+1.10 |
| `BET_20261117_00CA0272` | `ESPN_401909997_2026-11-17_PHI_AT_BKN` | `moneyline` | **AWAY** | 1.442 | 0.7160 | +3.29% | S/1.78 | `WON` | S/+0.79 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909994_2026-11-17_ORL_AT_BOS` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -3.60% <= threshold 2.00%
- `ESPN_401909994_2026-11-17_ORL_AT_BOS` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -6.82% <= threshold 2.00%
- `ESPN_401909994_2026-11-17_ORL_AT_BOS` (`spread` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -8.65% <= threshold 2.00%
- `ESPN_401909994_2026-11-17_ORL_AT_BOS` (`spread` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -9.85% <= threshold 2.00%
- `ESPN_401909994_2026-11-17_ORL_AT_BOS` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -11.17% <= threshold 2.00%
- `ESPN_401909994_2026-11-17_ORL_AT_BOS` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -23.30% <= threshold 2.00%
- `ESPN_401909999_2026-11-17_POR_AT_MIN` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -2.09% <= threshold 2.00%
- `ESPN_401910000_2026-11-17_GSW_AT_NOP` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -2.33% <= threshold 2.00%

## 6. Evidencia de Ventaja (CLV y Holdout hacia Adelante)

| Mercado | Partidos (señales) | CLV medio | IC95 (t, por partido) | Veredicto | Kelly aplicado |
| :--- | ---: | ---: | :--- | :--- | ---: |
| `moneyline` | 10 (12) | -2.70% | [-5.32%, -0.08%] | `NO_EDGE` | ×0.50 |
| `spread` | 6 (6) | -2.71% | [-3.05%, -2.37%] | `INSUFFICIENT_SAMPLE` | ×1.00 |
| `total_points` | 10 (29) | -3.25% | [-3.57%, -2.94%] | `NO_EDGE` | ×0.50 |

- **Holdout hacia adelante** (partidos desde `2026-11-15T00:00:00Z`, backtest `2026-11-16T23:38:07Z`): `11` partidos, `0` apuestas, ROI `n/d`, CLV `n/d`. Es la única evidencia fuera de muestra real.

## 7. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual inicial de **S/100.00 PEN** (bankroll observado liquidado actual: **S/97.91 PEN** en **33** apuestas observadas).
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
