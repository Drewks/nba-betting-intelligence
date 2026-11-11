# Backtest con cuotas reales (consenso de apertura/cierre, sin margen)

- Generado: `2026-11-11T22:54:07Z`
- Market data: minmaxxxer, 'NBA closing lines and ATS results' (HuggingFace), CC BY 4.0 — consensus no-vig opening/closing lines (median across bookmakers).
- Periodo de prueba desde `2025-01-01` | partidos con mercado emparejado: `2301`
- Reentrenamiento cada `7` días | margen supuesto `4.5%` | peso del modelo `0.3` | EV mínimo `5%`

## 1. Calidad probabilística fuera de muestra (todos los partidos)

| Serie | Mercado | N | Brier | LogLoss |
| :--- | :--- | ---: | ---: | ---: |
| `model_raw` | moneyline | 2301 | 0.20673 | 0.60083 |
| `model_calibrated` | moneyline | 2301 | 0.20646 | 0.59967 |
| `model_anchored_30_70` | moneyline | 2301 | 0.20096 | 0.58596 |
| `market_open` | moneyline | 2301 | 0.20108 | 0.58598 |
| `market_close` | moneyline | 2301 | 0.19684 | 0.57566 |
| `model_raw` | totals (línea de apertura) | 2301 | 0.25525 | 0.70482 |
| `model_calibrated` | totals (línea de apertura) | 2301 | 0.25311 | 0.70011 |
| `market_open_assumed_0.5` | totals (línea de apertura) | 2301 | 0.25000 | 0.69315 |
| `market_close_normal_approx` | totals (línea de apertura) | 2301 | 0.24324 | 0.67943 |

## 2. Apuestas simuladas (reglas de producción, precio de apertura)

- Apuestas: `92` (ganadas `35` / liquidadas `92`, push `0`)
- **Stake fijo S/1**: neto `S/+9.49` | ROI `10.32%` | IC95 bootstrap `[-20.6842%, 41.5812%]` | MaxDD `11.46%`
- **Stake Kelly 50%** (S/1.00–S/10.00): banca final `S/116.05` | ROI `9.32%` | stake medio `S/1.87` | MaxDD `20.16%`
- **CLV vs cierre sin margen**: media `-1.1%` | gana al cierre `0.3913` | IC95 `[-4.3802%, 2.2763%]`

| Grupo | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| :--- | ---: | ---: | ---: | ---: |
| mercado: `moneyline` | 92 | 35 | 10.32% [-20.7, 41.6] | -1.1% [-4.4, 2.3] |
| temporada: `2024-25` | 32 | 12 | 5.15% [-40.1, 51.5] | -4.193% [-9.5, 1.1] |
| temporada: `2025-26` | 54 | 19 | 7.62% [-32.7, 50.5] | -0.517% [-4.9, 4.0] |
| temporada: `2026-27` | 6 | 4 | 62.12% [-52.3, 144.1] | 10.146% [-1.5, 21.2] |

## 4. ¿El modelo anticipa el movimiento de línea? (todos los partidos, sin reglas de apuesta)

Correlación entre la discrepancia del modelo con la apertura y el movimiento apertura→cierre.

| Temporada | Mercado | N | Correlación [IC95] | Acierto de dirección |
| :--- | :--- | ---: | ---: | ---: |
| 2024-25 | moneyline | 830 | +0.036 [-0.054, +0.129] | 50.8% |
| 2024-25 | totals | 758 | +0.293 [+0.226, +0.356] | 58.4% |
| 2025-26 | moneyline | 1301 | +0.124 [+0.060, +0.208] | 53.5% |
| 2025-26 | totals | 1166 | +0.225 [+0.166, +0.284] | 56.7% |
| 2026-27 | moneyline | 143 | +0.415 [+0.277, +0.536] | 61.5% |
| 2026-27 | totals | 129 | +0.327 [+0.196, +0.464] | 64.3% |
| ALL | moneyline | 2274 | +0.110 [+0.054, +0.160] | 53.0% |
| ALL | totals | 2053 | +0.266 [+0.224, +0.304] | 57.8% |

## Supuestos
- Precio apostable = cuota justa de apertura / (1 + margen). La fuente publica probabilidades sin margen, no precios de casas.
- Totales: la línea principal de apertura es la más cercana a 50/50 (p=0.50); el cierre a esa línea se aproxima con un modelo normal (σ=18).
- Las features usan solo partidos que empezaron antes del primer partido de la jornada; los calibradores solo predicciones previas.
