# Backtest con cuotas reales (consenso de apertura/cierre, sin margen)

- Generado: `2026-11-14T14:38:50Z`
- Market data: minmaxxxer, 'NBA closing lines and ATS results' (HuggingFace), CC BY 4.0 — consensus no-vig opening/closing lines (median across bookmakers).
- Periodo de prueba desde `2025-01-01` | partidos con mercado emparejado: `2301`
- Reentrenamiento cada `7` días | margen supuesto `4.5%` | peso del modelo `0.3` | EV mínimo `2%`

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

- Apuestas: `91` (ganadas `45` / liquidadas `91`, push `0`)
- **Stake fijo S/1**: neto `S/-1.41` | ROI `-1.55%` | IC95 bootstrap `[-22.5645%, 19.8729%]` | MaxDD `8.99%`
- **Stake Kelly 25%** (S/1.00–S/10.00): banca final `S/98.03` | ROI `-2.0%` | stake medio `S/1.08` | MaxDD `9.92%`
- **CLV vs cierre sin margen**: media `1.369%` | gana al cierre `0.5275` | IC95 `[-1.4111%, 4.718%]`

| Grupo | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| :--- | ---: | ---: | ---: | ---: |
| mercado: `moneyline` | 47 | 22 | -3.05% [-33.2, 26.4] | -3.131% [-7.4, 0.8] |
| mercado: `total_points` | 44 | 23 | 0.04% [-26.1, 26.1] | 6.176% [2.0, 10.9] |
| temporada: `2024-25` | 40 | 19 | -5.35% [-38.6, 29.0] | 4.13% [-0.6, 8.9] |
| temporada: `2025-26` | 47 | 25 | 5.98% [-22.6, 35.3] | -1.779% [-5.8, 2.6] |
| temporada: `2026-27` | 4 | 1 | -52.15% [-100.0, -4.3] | 10.745% [-6.8, 34.1] |

## 3. Sensibilidad al margen supuesto

| Margen | Mercado | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| ---: | :--- | ---: | ---: | ---: | ---: |
| 4.5% | `moneyline` | 47 | 22 | -3.05% [-33.2, 26.4] | -3.131% [-7.4, 0.8] |
| 4.5% | `total_points` | 44 | 23 | 0.04% [-26.1, 26.1] | 6.176% [2.0, 10.9] |
| 2.5% | `moneyline` | 265 | 133 | 5.16% [-8.3, 18.8] | -0.406% [-2.0, 1.2] |
| 2.5% | `total_points` | 291 | 156 | 4.6% [-6.8, 14.5] | 2.175% [0.7, 3.8] |
| 6.0% | `moneyline` | 4 | 0 | -100.0% [-100.0, -100.0] | -6.348% [-21.0, 2.9] |

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
