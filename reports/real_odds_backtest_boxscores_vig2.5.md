# Backtest con cuotas reales (consenso de apertura/cierre, sin margen)

- Generado: `2026-11-09T20:43:13Z`
- Market data: minmaxxxer, 'NBA closing lines and ATS results' (HuggingFace), CC BY 4.0 — consensus no-vig opening/closing lines (median across bookmakers).
- Periodo de prueba desde `2025-01-01` | partidos con mercado emparejado: `2301`
- Reentrenamiento cada `7` días | margen supuesto `2.5%` | peso del modelo `0.3` | EV mínimo `5%`

## 1. Calidad probabilística fuera de muestra (todos los partidos)

| Serie | Mercado | N | Brier | LogLoss |
| :--- | :--- | ---: | ---: | ---: |
| `model_raw` | moneyline | 2301 | 0.20583 | 0.59806 |
| `model_calibrated` | moneyline | 2301 | 0.20536 | 0.59625 |
| `model_anchored_30_70` | moneyline | 2301 | 0.20071 | 0.58519 |
| `market_open` | moneyline | 2301 | 0.20108 | 0.58598 |
| `market_close` | moneyline | 2301 | 0.19684 | 0.57566 |
| `model_raw` | totals (línea de apertura) | 2301 | 0.25525 | 0.70482 |
| `model_calibrated` | totals (línea de apertura) | 2301 | 0.25311 | 0.70011 |
| `market_open_assumed_0.5` | totals (línea de apertura) | 2301 | 0.25000 | 0.69315 |
| `market_close_normal_approx` | totals (línea de apertura) | 2301 | 0.24324 | 0.67943 |

## 2. Apuestas simuladas (reglas de producción, precio de apertura)

- Apuestas: `263` (ganadas `120` / liquidadas `263`, push `0`)
- **Stake fijo S/1**: neto `S/+16.11` | ROI `6.13%` | IC95 bootstrap `[-8.0747%, 20.8572%]` | MaxDD `13.22%`
- **Stake Kelly 25%** (S/0.50–S/3.00): banca final `S/132.23` | ROI `8.15%` | stake medio `S/1.5` | MaxDD `18.11%`
- **CLV vs cierre sin margen**: media `1.188%` | gana al cierre `0.4905` | IC95 `[-0.659%, 2.9953%]`

| Grupo | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| :--- | ---: | ---: | ---: | ---: |
| mercado: `moneyline` | 182 | 72 | 1.9% [-16.9, 20.0] | -0.482% [-2.7, 1.8] |
| mercado: `total_points` | 81 | 48 | 15.63% [-3.7, 35.8] | 4.939% [1.8, 8.1] |
| temporada: `2024-25` | 108 | 50 | 9.85% [-14.9, 32.4] | 2.554% [-0.8, 5.7] |
| temporada: `2025-26` | 146 | 67 | 5.52% [-14.2, 24.4] | -0.118% [-2.6, 2.2] |
| temporada: `2026-27` | 9 | 3 | -28.79% [-82.3, 35.8] | 5.972% [-3.4, 15.9] |

## 4. ¿El modelo anticipa el movimiento de línea? (todos los partidos, sin reglas de apuesta)

Correlación entre la discrepancia del modelo con la apertura y el movimiento apertura→cierre.

| Temporada | Mercado | N | Correlación [IC95] | Acierto de dirección |
| :--- | :--- | ---: | ---: | ---: |
| 2024-25 | moneyline | 830 | +0.036 [-0.054, +0.129] | 50.8% |
| 2024-25 | totals | 758 | +0.293 [+0.226, +0.356] | 58.4% |
| 2025-26 | moneyline | 1301 | +0.166 [+0.081, +0.262] | 56.5% |
| 2025-26 | totals | 1166 | +0.225 [+0.166, +0.284] | 56.7% |
| 2026-27 | moneyline | 143 | +0.418 [+0.273, +0.545] | 65.0% |
| 2026-27 | totals | 129 | +0.327 [+0.196, +0.464] | 64.3% |
| ALL | moneyline | 2274 | +0.133 [+0.070, +0.193] | 55.0% |
| ALL | totals | 2053 | +0.266 [+0.224, +0.304] | 57.8% |

## Supuestos
- Precio apostable = cuota justa de apertura / (1 + margen). La fuente publica probabilidades sin margen, no precios de casas.
- Totales: la línea principal de apertura es la más cercana a 50/50 (p=0.50); el cierre a esa línea se aproxima con un modelo normal (σ=18).
- Las features usan solo partidos que empezaron antes del primer partido de la jornada; los calibradores solo predicciones previas.
