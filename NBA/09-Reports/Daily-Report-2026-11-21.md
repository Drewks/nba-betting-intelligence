---
date_generated: 2026-11-21T03:13:45Z
report_type: daily_report
model_versions: [model_f_ensemble_v8, model_a_baseline_v1, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
period_evaluated: 2026-11-21
predictions_count: 164
observed_settled_bets: 36
observed_bankroll_pen: 98.03
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-21

## 1. Metadatos de Ejecución y Estado de Banca Observada
- **Fecha de generación (UTC)**: `2026-11-21T03:13:45Z`
- **Jornada evaluada**: `2026-11-21`
- **Versión de modelo activa**: `model_f_ensemble_v8` (Submodelos `model_b_elo_v8`, `model_c_point_margin_v8`, `model_d_total_points_v8`, `model_e_lightgbm_v8`, `model_g_ml_montecarlo_v8`)
- **Bankroll virtual inicial**: `S/100.00 PEN`
- **Bankroll observado liquidado actual**: **`S/98.03 PEN`** (`S/-1.97 PEN` en `36` apuestas observadas liquidadas)
- **Modo de apuesta activo**: `Kelly Fraccional (25%) | Máx. 3 selecciones/jornada | EV >= 2.0%`
- **Partidos evaluados**: `10`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `164`
- **Apuestas simuladas registradas en la jornada**: `1` (límite diario: 3, Kelly Fraccional (25%), EV >= 2.0%)
- **Decisiones NO_BET registradas**: `165`
- **Resultados pendientes globales**: `1`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `TOR @ DET` | `total_points` | **OVER** | 215.5 | 1.893 | 0.5283 | 0.5469 | +3.53% | `Pinnacle [LIVE_API]` |
| `IND @ CLE` | `moneyline` | **HOME** | — | 1.457 | 0.6865 | 0.7099 | +3.41% | `Pinnacle [LIVE_API]` |
| `TOR @ DET` | `total_points` | **OVER** | 216.5 | 1.980 | 0.5049 | 0.5203 | +3.03% | `Pinnacle [LIVE_API]` |
| `IND @ CLE` | `total_points` | **UNDER** | 234.5 | 1.926 | 0.5192 | 0.5343 | +2.91% | `Pinnacle [LIVE_API]` |
| `WAS @ CHI` | `moneyline` | **HOME** | — | 1.735 | 0.5763 | 0.5921 | +2.75% | `Pinnacle [LIVE_API]` |
| `PHX @ UTA` | `moneyline` | **AWAY** | — | 1.578 | 0.6337 | 0.6491 | +2.42% | `Pinnacle [LIVE_API]` |
| `WAS @ CHI` | `moneyline` | **HOME** | — | 1.781 | 0.5614 | 0.5748 | +2.38% | `Pinnacle [LIVE_API]` |
| `TOR @ DET` | `total_points` | **OVER** | 216.5 | 1.952 | 0.5122 | 0.5244 | +2.38% | `Pinnacle [LIVE_API]` |
| `HOU @ DEN` | `total_points` | **UNDER** | 226.5 | 1.971 | 0.5074 | 0.5191 | +2.32% | `Pinnacle [LIVE_API]` |
| `PHX @ UTA` | `moneyline` | **AWAY** | — | 1.556 | 0.6428 | 0.6571 | +2.21% | `Pinnacle [LIVE_API]` |

## 4. Apuestas Simuladas (Paper Trading — Banca Observada S/98.03 PEN en 36 Apuestas Liquidadas)

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261121_99EEB422` | `ESPN_401909307_2026-11-21_IND_AT_CLE` | `moneyline` | **HOME** | 1.457 | 0.7099 | +3.41% | S/1.81 | `WON` | S/+0.83 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909305_2026-11-21_CHA_AT_ATL` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -2.18% <= threshold 2.00%
- `ESPN_401909305_2026-11-21_CHA_AT_ATL` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -4.82% <= threshold 2.00%
- `ESPN_401909307_2026-11-21_IND_AT_CLE` (`total_points` - `UNDER`): **NO_BET** [KELLY_STAKE_BELOW_MINIMUM] — Fractional Kelly stake below S/1.00 (no material edge at 1.926); Kelly x0.50 by total_points CLV evidence NO_EDGE.
- `ESPN_401909311_2026-11-21_PHX_AT_UTA` (`moneyline` - `AWAY`): **NO_BET** [CONFORMAL_UNCERTAINTY_TOO_WIDE] — Venn-Abers conformal prediction interval width 0.233 > 0.22; epistemic uncertainty too high.
- `ESPN_401909308_2026-11-21_TOR_AT_DET` (`total_points` - `OVER`): **NO_BET** [KELLY_STAKE_BELOW_MINIMUM] — Fractional Kelly stake below S/1.00 (no material edge at 1.952); Kelly x0.50 by total_points CLV evidence NO_EDGE.
- `ESPN_401909309_2026-11-21_WAS_AT_CHI` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.82% <= threshold 2.00%
- `ESPN_401909307_2026-11-21_IND_AT_CLE` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.33% <= threshold 2.00%
- `ESPN_401909305_2026-11-21_CHA_AT_ATL` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.12% <= threshold 2.00%

## 6. Evidencia de Ventaja (CLV y Holdout hacia Adelante)

| Mercado | Partidos (señales) | CLV medio | IC95 (t, por partido) | Veredicto | Kelly aplicado |
| :--- | ---: | ---: | :--- | :--- | ---: |
| `moneyline` | 10 (14) | +0.69% | [-1.75%, +3.12%] | `INCONCLUSIVE` | ×1.00 |
| `total_points` | 18 (31) | -2.94% | [-5.06%, -0.81%] | `NO_EDGE` | ×0.50 |

- **Holdout hacia adelante** (partidos desde `2026-11-15T00:00:00Z`, backtest `2026-11-18T01:49:56Z`): `14` partidos, `0` apuestas, ROI `n/d`, CLV `n/d`. Es la única evidencia fuera de muestra real.

## 7. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual inicial de **S/100.00 PEN** (bankroll observado liquidado actual: **S/98.03 PEN** en **36** apuestas observadas).
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
