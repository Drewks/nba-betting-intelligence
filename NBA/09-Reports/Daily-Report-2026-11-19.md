---
date_generated: 2026-11-19T22:41:46Z
report_type: daily_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
period_evaluated: 2026-11-19
predictions_count: 253
observed_settled_bets: 34
observed_bankroll_pen: 98.51
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-19

## 1. Metadatos de Ejecución y Estado de Banca Observada
- **Fecha de generación (UTC)**: `2026-11-19T22:41:46Z`
- **Jornada evaluada**: `2026-11-19`
- **Versión de modelo activa**: `model_f_ensemble_v8` (Submodelos `model_b_elo_v8`, `model_c_point_margin_v8`, `model_d_total_points_v8`, `model_e_lightgbm_v8`, `model_g_ml_montecarlo_v8`)
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll observado liquidado actual**: **`S/98.51 PEN`** (`S/-1.49 PEN` en `34` apuestas observadas liquidadas)
- **Modo de apuesta activo**: `Kelly Fraccional (25%) | Máx. 3 selecciones/jornada | EV >= 2.0%`
- **Partidos evaluados**: `12`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `253`
- **Apuestas simuladas registradas en la jornada**: `1` (límite diario: 3, Kelly Fraccional (25%), EV >= 2.0%)
- **Decisiones NO_BET registradas**: `253`
- **Resultados pendientes globales**: `1`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `GSW @ DAL` | `moneyline` | **AWAY** | — | 2.940 | 0.3401 | 0.3655 | +7.47% | `Pinnacle [LIVE_API]` |
| `GSW @ DAL` | `moneyline` | **AWAY** | — | 2.940 | 0.3401 | 0.3652 | +7.37% | `Pinnacle [LIVE_API]` |
| `GSW @ DAL` | `spread` | **AWAY** | 6.0 | 1.917 | 0.5215 | 0.5412 | +6.25% | `Pinnacle [LIVE_API]` |
| `GSW @ DAL` | `moneyline` | **AWAY** | — | 2.680 | 0.3731 | 0.3947 | +5.77% | `Pinnacle [LIVE_API]` |
| `GSW @ DAL` | `moneyline` | **AWAY** | — | 2.650 | 0.3774 | 0.3976 | +5.37% | `Pinnacle [LIVE_API]` |
| `GSW @ DAL` | `spread` | **AWAY** | 6.0 | 1.926 | 0.5192 | 0.5341 | +5.34% | `Pinnacle [LIVE_API]` |
| `UTA @ LAL` | `spread` | **HOME** | -10.0 | 1.926 | 0.5192 | 0.5329 | +5.12% | `Pinnacle [LIVE_API]` |
| `GSW @ DAL` | `spread` | **AWAY** | 4.5 | 1.980 | 0.5049 | 0.5272 | +4.41% | `Pinnacle [LIVE_API]` |
| `GSW @ DAL` | `spread` | **AWAY** | 4.5 | 1.971 | 0.5074 | 0.5289 | +4.24% | `Pinnacle [LIVE_API]` |
| `UTA @ LAL` | `spread` | **HOME** | -11.5 | 1.926 | 0.5192 | 0.5400 | +4.01% | `Pinnacle [LIVE_API]` |

## 4. Apuestas Simuladas (Paper Trading — Banca Observada S/98.51 PEN en 34 Apuestas Liquidadas)

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261119_776B4D10` | `ESPN_401910008_2026-11-19_HOU_AT_IND` | `moneyline` | **AWAY** | 1.410 | 0.7267 | +2.45% | S/1.47 | `WON` | S/+0.60 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401910009_2026-11-19_MIL_AT_MIA` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.96% <= threshold 2.00%
- `ESPN_401910008_2026-11-19_HOU_AT_IND` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.89% <= threshold 2.00%
- `ESPN_401910009_2026-11-19_MIL_AT_MIA` (`spread` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.78% <= threshold 2.00%
- `ESPN_401910007_2026-11-19_MEM_AT_CLE` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.48% <= threshold 2.00%
- `ESPN_401910007_2026-11-19_MEM_AT_CLE` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -1.65% <= threshold 2.00%
- `ESPN_401910009_2026-11-19_MIL_AT_MIA` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -1.90% <= threshold 2.00%
- `ESPN_401910007_2026-11-19_MEM_AT_CLE` (`spread` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -2.28% <= threshold 2.00%
- `ESPN_401910008_2026-11-19_HOU_AT_IND` (`spread` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -2.40% <= threshold 2.00%

## 6. Evidencia de Ventaja (CLV y Holdout hacia Adelante)

| Mercado | Partidos (señales) | CLV medio | IC95 (t, por partido) | Veredicto | Kelly aplicado |
| :--- | ---: | ---: | :--- | :--- | ---: |
| `moneyline` | 8 (11) | +1.01% | [-2.13%, +4.15%] | `INSUFFICIENT_SAMPLE` | ×1.00 |
| `total_points` | 13 (24) | -2.81% | [-5.70%, +0.08%] | `INCONCLUSIVE` | ×1.00 |

- **Holdout hacia adelante** (partidos desde `2026-11-15T00:00:00Z`, backtest `2026-11-18T01:49:56Z`): `14` partidos, `0` apuestas, ROI `n/d`, CLV `n/d`. Es la única evidencia fuera de muestra real.

## 7. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual inicial de **S/100.00 PEN** (bankroll observado liquidado actual: **S/98.51 PEN** en **34** apuestas observadas).
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
