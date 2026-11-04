---
date_generated: 2026-11-04T22:42:58Z
report_type: daily_report
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
period_evaluated: 2026-11-04
predictions_count: 0
simulation_only: true
---
# Informe Diario NBA Betting Intelligence — 2026-11-04

## 1. Metadatos de Ejecución
- **Fecha de generación (UTC)**: `2026-11-04T22:42:58Z`
- **Jornada evaluada**: `2026-11-04`
- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)
- **Partidos evaluados**: `0`
- **Partidos descartados por falta de datos/cuotas**: `0`
- **Predicciones emitidas**: `0`
- **Apuestas simuladas registradas en la jornada**: `0` (límite diario: 3, stake máx: S/1.00 PEN)
- **Decisiones NO_BET registradas**: `0`
- **Resultados pendientes globales**: `3`

## 2. Partidos Descartados por Falta de Datos o Cuotas
- Ningún partido descartado por falta de variables esenciales en el lote validado.

## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)

| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |

## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes

| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |
| — | — | — | **NO BET** | — | — | — | S/0.00 | `NO_BET` | S/0.00 |

## 5. Registro de Decisiones NO_BET (Muestra de Control)

## 6. Limitaciones Documentadas
- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.
- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.
