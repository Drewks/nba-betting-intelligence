# Backtest con cuotas reales (consenso de apertura/cierre, sin margen)

- Generado: `2026-11-09T18:37:58Z`
- Market data: minmaxxxer, 'NBA closing lines and ATS results' (HuggingFace), CC BY 4.0 — consensus no-vig opening/closing lines (median across bookmakers).
- Periodo de prueba desde `2025-01-01` | partidos con mercado emparejado: `2301`
- Reentrenamiento cada `7` días | margen supuesto `4.5%` | peso del modelo `0.3` | EV mínimo `5%`

## 1. Calidad probabilística fuera de muestra (todos los partidos)

| Serie | Mercado | N | Brier | LogLoss |
| :--- | :--- | ---: | ---: | ---: |
| `model_raw` | moneyline | 2301 | 0.20719 | 0.60104 |
| `model_calibrated` | moneyline | 2301 | 0.20711 | 0.60061 |
| `model_anchored_30_70` | moneyline | 2301 | 0.20124 | 0.58667 |
| `market_open` | moneyline | 2301 | 0.20108 | 0.58598 |
| `market_close` | moneyline | 2301 | 0.19684 | 0.57566 |
| `model_raw` | totals (línea de apertura) | 2301 | 0.25525 | 0.70482 |
| `model_calibrated` | totals (línea de apertura) | 2301 | 0.25311 | 0.70011 |
| `market_open_assumed_0.5` | totals (línea de apertura) | 2301 | 0.25000 | 0.69315 |
| `market_close_normal_approx` | totals (línea de apertura) | 2301 | 0.24324 | 0.67943 |

## 2. Apuestas simuladas (reglas de producción, precio de apertura)

- Apuestas: `104` (ganadas `25` / liquidadas `104`, push `0`)
- **Stake fijo S/1**: neto `S/-23.74` | ROI `-22.83%` | IC95 bootstrap `[-49.1429%, 5.4274%]` | MaxDD `30.61%`
- **Stake Kelly 25%** (S/0.50–S/3.00): banca final `S/81.03` | ROI `-21.94%` | stake medio `S/0.83` | MaxDD `24.91%`
- **CLV vs cierre sin margen**: media `-3.608%` | gana al cierre `0.3077` | IC95 `[-7.0871%, 0.2021%]`

| Grupo | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| :--- | ---: | ---: | ---: | ---: |
| mercado: `moneyline` | 104 | 25 | -22.83% [-49.1, 5.4] | -3.608% [-7.1, 0.2] |
| temporada: `2024-25` | 40 | 13 | -1.41% [-40.2, 48.6] | -7.854% [-12.7, -3.5] |
| temporada: `2025-26` | 62 | 12 | -34.15% [-66.0, 0.5] | -0.646% [-5.3, 4.5] |
| temporada: `2026-27` | 2 | 0 | -100.0% [-100.0, -100.0] | -10.536% [-15.7, -5.4] |

## 3. Sensibilidad al margen supuesto

| Margen | Mercado | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| ---: | :--- | ---: | ---: | ---: | ---: |
| 4.5% | `moneyline` | 104 | 25 | -22.83% [-49.1, 5.4] | -3.608% [-7.1, 0.2] |
| 2.5% | `moneyline` | 188 | 65 | 1.96% [-18.2, 22.7] | -1.493% [-4.2, 1.2] |
| 2.5% | `total_points` | 87 | 51 | 14.38% [-4.7, 34.6] | 4.911% [2.1, 8.0] |
| 6.0% | `moneyline` | 52 | 12 | -20.1% [-60.8, 26.3] | -2.774% [-7.6, 3.0] |

## 4. ¿El modelo anticipa el movimiento de línea? (todos los partidos, sin reglas de apuesta)

Correlación entre la discrepancia del modelo con la apertura y el movimiento apertura→cierre.

| Temporada | Mercado | N | Correlación [IC95] | Acierto de dirección |
| :--- | :--- | ---: | ---: | ---: |
| 2024-25 | moneyline | 830 | -0.006 [-0.077, +0.076] | 48.8% |
| 2024-25 | totals | 758 | +0.293 [+0.226, +0.356] | 58.4% |
| 2025-26 | moneyline | 1301 | +0.090 [+0.017, +0.178] | 52.8% |
| 2025-26 | totals | 1166 | +0.225 [+0.166, +0.284] | 56.7% |
| 2026-27 | moneyline | 143 | +0.402 [+0.274, +0.514] | 62.2% |
| 2026-27 | totals | 129 | +0.327 [+0.196, +0.464] | 64.3% |
| ALL | moneyline | 2274 | +0.071 [+0.014, +0.123] | 51.9% |
| ALL | totals | 2053 | +0.266 [+0.224, +0.304] | 57.8% |

## Supuestos
- Precio apostable = cuota justa de apertura / (1 + margen). La fuente publica probabilidades sin margen, no precios de casas.
- Totales: la línea principal de apertura es la más cercana a 50/50 (p=0.50); el cierre a esa línea se aproxima con un modelo normal (σ=18).
- Las features usan solo partidos que empezaron antes del primer partido de la jornada; los calibradores solo predicciones previas.
