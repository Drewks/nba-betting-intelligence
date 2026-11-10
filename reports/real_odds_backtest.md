# Backtest con cuotas reales (consenso de apertura/cierre, sin margen)

- Generado: `2026-11-10T02:18:46Z`
- Market data: minmaxxxer, 'NBA closing lines and ATS results' (HuggingFace), CC BY 4.0 — consensus no-vig opening/closing lines (median across bookmakers).
- Periodo de prueba desde `2025-01-01` | partidos con mercado emparejado: `2301`
- Reentrenamiento cada `7` días | margen supuesto `4.5%` | peso del modelo `0.3` | EV mínimo `5%`

## 1. Calidad probabilística fuera de muestra (todos los partidos)

| Serie | Mercado | N | Brier | LogLoss |
| :--- | :--- | ---: | ---: | ---: |
| `model_raw` | moneyline | 2301 | 0.20761 | 0.60277 |
| `model_calibrated` | moneyline | 2301 | 0.20724 | 0.60140 |
| `model_anchored_30_70` | moneyline | 2301 | 0.20122 | 0.58669 |
| `market_open` | moneyline | 2301 | 0.20108 | 0.58598 |
| `market_close` | moneyline | 2301 | 0.19684 | 0.57566 |
| `model_raw` | totals (línea de apertura) | 2301 | 0.25525 | 0.70482 |
| `model_calibrated` | totals (línea de apertura) | 2301 | 0.25311 | 0.70011 |
| `market_open_assumed_0.5` | totals (línea de apertura) | 2301 | 0.25000 | 0.69315 |
| `market_close_normal_approx` | totals (línea de apertura) | 2301 | 0.24324 | 0.67943 |

## 2. Apuestas simuladas (reglas de producción, precio de apertura)

- Apuestas: `91` (ganadas `22` / liquidadas `91`, push `0`)
- **Stake fijo S/1**: neto `S/-13.39` | ROI `-14.71%` | IC95 bootstrap `[-46.0377%, 19.1132%]` | MaxDD `23.22%`
- **Stake Kelly 25%** (S/1.00–S/10.00): banca final `S/66.52` | ROI `-21.72%` | stake medio `S/1.69` | MaxDD `39.69%`
- **CLV vs cierre sin margen**: media `-6.65%` | gana al cierre `0.2308` | IC95 `[-9.5346%, -3.6412%]`

| Grupo | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| :--- | ---: | ---: | ---: | ---: |
| mercado: `moneyline` | 91 | 22 | -14.71% [-46.0, 19.1] | -6.65% [-9.5, -3.6] |
| temporada: `2024-25` | 37 | 13 | 22.37% [-30.9, 80.6] | -8.955% [-13.6, -4.3] |
| temporada: `2025-26` | 51 | 9 | -36.59% [-75.3, 6.2] | -5.153% [-8.5, -0.8] |
| temporada: `2026-27` | 3 | 0 | -100.0% [-100.0, -100.0] | -3.679% [-10.6, 4.9] |

## 4. ¿El modelo anticipa el movimiento de línea? (todos los partidos, sin reglas de apuesta)

Correlación entre la discrepancia del modelo con la apertura y el movimiento apertura→cierre.

| Temporada | Mercado | N | Correlación [IC95] | Acierto de dirección |
| :--- | :--- | ---: | ---: | ---: |
| 2024-25 | moneyline | 830 | +0.011 [-0.065, +0.102] | 49.3% |
| 2024-25 | totals | 758 | +0.293 [+0.226, +0.356] | 58.4% |
| 2025-26 | moneyline | 1301 | +0.081 [+0.008, +0.161] | 51.8% |
| 2025-26 | totals | 1166 | +0.225 [+0.166, +0.284] | 56.7% |
| 2026-27 | moneyline | 143 | +0.398 [+0.265, +0.526] | 59.4% |
| 2026-27 | totals | 129 | +0.327 [+0.196, +0.464] | 64.3% |
| ALL | moneyline | 2274 | +0.074 [+0.018, +0.127] | 51.4% |
| ALL | totals | 2053 | +0.266 [+0.224, +0.304] | 57.8% |

## Supuestos
- Precio apostable = cuota justa de apertura / (1 + margen). La fuente publica probabilidades sin margen, no precios de casas.
- Totales: la línea principal de apertura es la más cercana a 50/50 (p=0.50); el cierre a esa línea se aproxima con un modelo normal (σ=18).
- Las features usan solo partidos que empezaron antes del primer partido de la jornada; los calibradores solo predicciones previas.
