---
date_generated: 2026-11-08T13:32:38Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-11-08
predictions_count: 104
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-08

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-11-08T13:32:38Z`
- **Jornada evaluada**: `2026-11-08`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `8`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `104`
- **Apuestas simuladas registradas en la jornada**: `3` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `101`
- **Resultados pendientes globales**: `2`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `WAS @ OKC` | `moneyline` | **HOME** | — | 1.938 | 0.5160 | 0.6156 | +19.30% | `1xBet Perú [T-6H Peru]` |
| `BKN @ ATL` | `moneyline` | **HOME** | — | 1.938 | 0.5160 | 0.5846 | +13.29% | `1xBet Perú [T-6H Peru]` |
| `PHI @ CHI` | `moneyline` | **HOME** | — | 3.680 | 0.2717 | 0.2897 | +6.59% | `Draft Kings` |
| `PHI @ CHI` | `total_points` | **UNDER** | 238.5 | 1.909 | 0.5238 | 0.5568 | +6.30% | `DraftKings` |
| `PHI @ CHI` | `moneyline` | **HOME** | — | 3.633 | 0.2753 | 0.2920 | +6.09% | `1xBet Perú [T-6H Peru]` |
| `PHI @ CHI` | `total_points` | **UNDER** | 238.5 | 1.885 | 0.5305 | 0.5616 | +5.86% | `DraftKings` |
| `PHI @ CHI` | `total_points` | **UNDER** | 238.5 | 1.885 | 0.5305 | 0.5616 | +5.86% | `Draft Kings` |
| `PHI @ CHI` | `total_points` | **UNDER** | 238.5 | 1.885 | 0.5305 | 0.5615 | +5.85% | `DraftKings` |
| `PHI @ CHI` | `moneyline` | **HOME** | — | 4.120 | 0.2427 | 0.2569 | +5.83% | `DraftKings` |
| `ORL @ GSW` | `moneyline` | **HOME** | — | 1.938 | 0.5160 | 0.5449 | +5.61% | `1xBet Perú [T-6H Peru]` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261108_458792F8` | `ESPN_401909942_2026-11-08_ORL_AT_GSW` | `moneyline` | **HOME** | 1.938 | 0.5449 | +5.61% | S/2.00 | `WON` | S/+1.88 |
| `BET_20261108_557A18AF` | `ESPN_401909943_2026-11-08_HOU_AT_PHX` | `moneyline` | **AWAY** | 1.938 | 0.5400 | +4.65% | S/2.00 | `LOST` | S/-2.00 |
| `BET_20261108_2DE83152` | `ESPN_401909944_2026-11-08_SAS_AT_POR` | `total_points` | **UNDER** | 1.909 | 0.5352 | +2.17% | S/1.34 | `WON` | S/+1.22 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909941_2026-11-08_WAS_AT_OKC` (`moneyline` - `HOME`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 38.5 pts (> 15); likely missing information, skipped.
- `ESPN_401909939_2026-11-08_BKN_AT_ATL` (`moneyline` - `HOME`): **NO_BET** [MODEL_MARKET_DISAGREEMENT] — Model differs from de-vigged market by 28.2 pts (> 15); likely missing information, skipped.
- `ESPN_401909944_2026-11-08_SAS_AT_POR` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.83% <= threshold 2.00%
- `ESPN_401909940_2026-11-08_NYK_AT_CLE` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 0.80% <= threshold 2.00%
- `ESPN_401909940_2026-11-08_NYK_AT_CLE` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -7.00% <= threshold 2.00%
- `ESPN_401909944_2026-11-08_SAS_AT_POR` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -8.03% <= threshold 2.00%
- `ESPN_401909943_2026-11-08_HOU_AT_PHX` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -10.85% <= threshold 2.00%
- `ESPN_401909942_2026-11-08_ORL_AT_GSW` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -11.81% <= threshold 2.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
