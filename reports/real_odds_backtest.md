# Backtest con cuotas reales (consenso de apertura/cierre, sin margen)

- Generado: `2026-11-13T01:11:13Z`
- Market data: minmaxxxer, 'NBA closing lines and ATS results' (HuggingFace), CC BY 4.0 — consensus no-vig opening/closing lines (median across bookmakers).
- Periodo de prueba desde `2025-01-01` | partidos con mercado emparejado: `2301`
- Reentrenamiento cada `7` días | margen supuesto `4.5%` | peso del modelo `0.3` | EV mínimo `5%`

## 1. Calidad probabilística fuera de muestra (todos los partidos)

| Serie | Mercado | N | Brier | LogLoss |
| :--- | :--- | ---: | ---: | ---: |
| `model_raw` | moneyline | 2301 | 0.20583 | 0.59806 |
| `model_calibrated` | moneyline | 2301 | 0.20536 | 0.59626 |
| `model_anchored_30_70` | moneyline | 2301 | 0.20071 | 0.58519 |
| `market_open` | moneyline | 2301 | 0.20108 | 0.58598 |
| `market_close` | moneyline | 2301 | 0.19684 | 0.57566 |
| `model_raw` | totals (línea de apertura) | 2301 | 0.25525 | 0.70482 |
| `model_calibrated` | totals (línea de apertura) | 2301 | 0.25311 | 0.70011 |
| `market_open_assumed_0.5` | totals (línea de apertura) | 2301 | 0.25000 | 0.69315 |
| `market_close_normal_approx` | totals (línea de apertura) | 2301 | 0.24324 | 0.67943 |

## 2. Apuestas simuladas (reglas de producción, precio de apertura)

- Apuestas: `81` (ganadas `28` / liquidadas `81`, push `0`)
- **Stake fijo S/1**: neto `S/-1.96` | ROI `-2.42%` | IC95 bootstrap `[-32.4807%, 27.2807%]` | MaxDD `12.22%`
- **Stake Kelly 50%** (S/1.00–S/10.00): banca final `S/93.09` | ROI `-4.63%` | stake medio `S/1.84` | MaxDD `22.56%`
- **CLV vs cierre sin margen**: media `-2.412%` | gana al cierre `0.3333` | IC95 `[-6.1119%, 1.3624%]`

| Grupo | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| :--- | ---: | ---: | ---: | ---: |
| mercado: `moneyline` | 81 | 28 | -2.42% [-32.5, 27.3] | -2.412% [-6.1, 1.4] |
| temporada: `2024-25` | 32 | 12 | 5.15% [-40.1, 51.5] | -4.193% [-9.5, 1.1] |
| temporada: `2025-26` | 46 | 15 | -6.67% [-46.6, 36.2] | -2.231% [-6.9, 2.4] |
| temporada: `2026-27` | 3 | 1 | -18.04% [-100.0, 145.9] | 13.798% [2.3, 34.1] |

## 3. Sensibilidad al margen supuesto

| Margen | Mercado | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| ---: | :--- | ---: | ---: | ---: | ---: |
| 4.5% | `moneyline` | 81 | 28 | -2.42% [-32.5, 27.3] | -2.412% [-6.1, 1.4] |
| 2.5% | `moneyline` | 182 | 72 | 1.9% [-16.9, 20.0] | -0.554% [-2.7, 1.6] |
| 2.5% | `total_points` | 81 | 48 | 15.63% [-3.7, 35.8] | 4.939% [1.8, 8.1] |
| 6.0% | `moneyline` | 39 | 10 | -24.6% [-64.3, 17.8] | -4.114% [-9.7, 1.0] |

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
