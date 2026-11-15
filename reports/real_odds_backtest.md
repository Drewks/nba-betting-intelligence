# Backtest con cuotas reales (consenso de apertura/cierre, sin margen)

- Generado: `2026-11-15T02:03:10Z`
- Market data: minmaxxxer, 'NBA closing lines and ATS results' (HuggingFace), CC BY 4.0 — consensus no-vig opening/closing lines (median across bookmakers).
- Periodo de prueba desde `2025-01-01` | partidos con mercado emparejado: `2301`
- Reentrenamiento cada `7` días | margen supuesto `4.5%` | peso del modelo `0.3` | EV mínimo `2%` | tope cuota Moneyline `2.8`

## 1. Calidad probabilística fuera de muestra (todos los partidos)

| Serie | Mercado | N | Brier | LogLoss |
| :--- | :--- | ---: | ---: | ---: |
| `model_raw` | moneyline | 2301 | 0.20579 | 0.59814 |
| `model_calibrated` | moneyline | 2301 | 0.20533 | 0.59628 |
| `model_anchored_30_70` | moneyline | 2301 | 0.20071 | 0.58521 |
| `market_open` | moneyline | 2301 | 0.20108 | 0.58598 |
| `market_close` | moneyline | 2301 | 0.19684 | 0.57566 |
| `model_raw` | totals (línea de apertura) | 2301 | 0.25511 | 0.70447 |
| `model_calibrated` | totals (línea de apertura) | 2301 | 0.25314 | 0.70019 |
| `model_anchored_30_70` | totals (línea de apertura) | 2301 | 0.24919 | 0.69152 |
| `market_open_assumed_0.5` | totals (línea de apertura) | 2301 | 0.25000 | 0.69315 |
| `market_close_normal_approx` | totals (línea de apertura) | 2301 | 0.24324 | 0.67943 |

## 2. Apuestas simuladas (reglas de producción, precio de apertura)

- Apuestas: `102` (ganadas `53` / liquidadas `102`, push `0`)
- **Stake fijo S/1**: neto `S/+2.12` | ROI `2.08%` | IC95 bootstrap `[-17.243%, 21.0443%]` | MaxDD `6.35%`
- **Stake Kelly 25%** (S/1.00–S/10.00): banca final `S/101.32` | ROI `1.17%` | stake medio `S/1.11` | MaxDD `7.09%`
- **CLV vs cierre sin margen**: media `1.399%` | gana al cierre `0.4804` | IC95 `[-0.9977%, 3.8902%]`

| Grupo | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| :--- | ---: | ---: | ---: | ---: |
| mercado: `moneyline` | 45 | 27 | 20.8% [-10.4, 51.4] | 0.215% [-3.3, 3.6] |
| mercado: `total_points` | 57 | 26 | -12.7% [-36.2, 14.2] | 2.333% [-1.3, 6.1] |
| temporada: `2024-25` | 34 | 19 | 11.76% [-24.2, 47.5] | 4.928% [0.3, 9.9] |
| temporada: `2025-26` | 63 | 33 | 1.05% [-24.6, 25.2] | -0.827% [-3.7, 1.9] |
| temporada: `2026-27` | 5 | 1 | -50.83% [-100.0, 84.4] | 5.443% [-3.7, 25.7] |

## 3. Sensibilidad al margen supuesto

| Margen | Mercado | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| ---: | :--- | ---: | ---: | ---: | ---: |
| 4.5% | `moneyline` | 45 | 27 | 20.8% [-10.4, 51.4] | 0.215% [-3.3, 3.6] |
| 4.5% | `total_points` | 57 | 26 | -12.7% [-36.2, 14.2] | 2.333% [-1.3, 6.1] |
| 2.5% | `moneyline` | 188 | 106 | 7.81% [-7.9, 22.3] | 0.619% [-1.1, 2.3] |
| 2.5% | `total_points` | 253 | 132 | 1.8% [-10.4, 13.6] | 2.684% [1.0, 4.4] |

## 4. ¿El modelo anticipa el movimiento de línea? (todos los partidos, sin reglas de apuesta)

Correlación entre la discrepancia del modelo con la apertura y el movimiento apertura→cierre.

| Temporada | Mercado | N | Correlación [IC95] | Acierto de dirección |
| :--- | :--- | ---: | ---: | ---: |
| 2024-25 | moneyline | 830 | +0.047 [-0.044, +0.140] | 50.7% |
| 2024-25 | totals | 758 | +0.288 [+0.222, +0.349] | 58.3% |
| 2025-26 | moneyline | 1301 | +0.163 [+0.079, +0.259] | 56.2% |
| 2025-26 | totals | 1166 | +0.217 [+0.157, +0.277] | 55.9% |
| 2026-27 | moneyline | 143 | +0.412 [+0.269, +0.539] | 65.0% |
| 2026-27 | totals | 129 | +0.325 [+0.194, +0.468] | 63.6% |
| ALL | moneyline | 2274 | +0.135 [+0.075, +0.194] | 54.8% |
| ALL | totals | 2053 | +0.260 [+0.218, +0.298] | 57.3% |

## Supuestos
- Precio apostable = cuota justa de apertura / (1 + margen). La fuente publica probabilidades sin margen, no precios de casas.
- Totales: la línea principal de apertura es la más cercana a 50/50 (p=0.50); el cierre a esa línea se aproxima con un modelo normal (σ=18).
- Las features usan solo partidos que empezaron antes del primer partido de la jornada; los calibradores solo predicciones previas.
