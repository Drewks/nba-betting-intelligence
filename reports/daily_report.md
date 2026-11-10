---
date_generated: 2026-11-10T14:07:26Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-11-10
predictions_count: 60
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-10

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-11-10T14:07:26Z`
- **Jornada evaluada**: `2026-11-10`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `8`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `60`
- **Apuestas simuladas registradas en la jornada**: `3` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `57`
- **Resultados pendientes globales**: `0`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `CLE @ CHA` | `moneyline` | **HOME** | — | 3.820 | 0.2618 | 0.2951 | +12.74% | `Draft Kings` |
| `CLE @ CHA` | `moneyline` | **HOME** | — | 3.840 | 0.2604 | 0.2828 | +8.61% | `Draft Kings` |
| `MEM @ TOR` | `moneyline` | **HOME** | — | 1.641 | 0.6094 | 0.6332 | +3.92% | `Draft Kings` |
| `DEN @ HOU` | `moneyline` | **AWAY** | — | 3.370 | 0.2967 | 0.3080 | +3.80% | `DraftKings` |
| `WAS @ DET` | `moneyline` | **HOME** | — | 1.243 | 0.8043 | 0.8222 | +2.23% | `Draft Kings` |
| `LAL @ ATL` | `total_points` | **UNDER** | 235.5 | 1.909 | 0.5238 | 0.5350 | +2.13% | `Draft Kings` |
| `WAS @ DET` | `moneyline` | **HOME** | — | 1.214 | 0.8239 | 0.8385 | +1.77% | `Draft Kings` |
| `CLE @ CHA` | `total_points` | **OVER** | 215.5 | 1.885 | 0.5305 | 0.5363 | +1.10% | `Draft Kings` |
| `DEN @ HOU` | `total_points` | **OVER** | 217.5 | 1.909 | 0.5238 | 0.5290 | +1.00% | `DraftKings` |
| `NOP @ GSW` | `moneyline` | **AWAY** | — | 5.260 | 0.1901 | 0.1898 | -0.18% | `Draft Kings` |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| `BET_20261110_60276AD1` | `ESPN_401909957_2026-11-10_DEN_AT_HOU` | `moneyline` | **AWAY** | 3.370 | 0.3080 | +3.80% | S/1.12 | `LOST` | S/-1.12 |
| `BET_20261110_A565DE31` | `ESPN_401909955_2026-11-10_MEM_AT_TOR` | `moneyline` | **HOME** | 1.641 | 0.6332 | +3.92% | S/3.50 | `LOST` | S/-3.50 |
| `BET_20261110_E8F6F562` | `ESPN_401909952_2026-11-10_LAL_AT_ATL` | `total_points` | **UNDER** | 1.909 | 0.5350 | +2.13% | S/2.00 | `LOST` | S/-2.00 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)
- `ESPN_401909957_2026-11-10_DEN_AT_HOU` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV 1.00% <= threshold 2.00%
- `ESPN_401909958_2026-11-10_SAS_AT_PHX` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -5.00% <= threshold 2.00%
- `ESPN_401909958_2026-11-10_SAS_AT_PHX` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -2.42% <= threshold 2.00%
- `ESPN_401909958_2026-11-10_SAS_AT_PHX` (`total_points` - `OVER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -6.67% <= threshold 2.00%
- `ESPN_401909958_2026-11-10_SAS_AT_PHX` (`moneyline` - `AWAY`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -3.44% <= threshold 2.00%
- `ESPN_401909957_2026-11-10_DEN_AT_HOU` (`total_points` - `UNDER`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -10.09% <= threshold 2.00%
- `ESPN_401909957_2026-11-10_DEN_AT_HOU` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -7.02% <= threshold 2.00%
- `ESPN_401909958_2026-11-10_SAS_AT_PHX` (`moneyline` - `HOME`): **NO_BET** [EV_BELOW_THRESHOLD] — EV -5.00% <= threshold 2.00%

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
