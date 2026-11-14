# Backtest con cuotas reales (consenso de apertura/cierre, sin margen)

- Generado: `2026-11-14T16:58:27Z`
- Market data: minmaxxxer, 'NBA closing lines and ATS results' (HuggingFace), CC BY 4.0 — consensus no-vig opening/closing lines (median across bookmakers).
- Periodo de prueba desde `2025-01-01` | partidos con mercado emparejado: `2301`
- Reentrenamiento cada `7` días | margen supuesto `4.5%` | peso del modelo `0.3` | EV mínimo `2%` | tope cuota Moneyline `2.8`

## 1. Calidad probabilística fuera de muestra (todos los partidos)

| Serie | Mercado | N | Brier | LogLoss |
| :--- | :--- | ---: | ---: | ---: |
| `model_raw` | moneyline | 2301 | 0.20583 | 0.59825 |
| `model_calibrated` | moneyline | 2301 | 0.20533 | 0.59621 |
| `model_anchored_30_70` | moneyline | 2301 | 0.20070 | 0.58518 |
| `market_open` | moneyline | 2301 | 0.20108 | 0.58598 |
| `market_close` | moneyline | 2301 | 0.19684 | 0.57566 |
| `model_raw` | totals (línea de apertura) | 2301 | 0.25518 | 0.70464 |
| `model_calibrated` | totals (línea de apertura) | 2301 | 0.25316 | 0.70025 |
| `market_open_assumed_0.5` | totals (línea de apertura) | 2301 | 0.25000 | 0.69315 |
| `market_close_normal_approx` | totals (línea de apertura) | 2301 | 0.24324 | 0.67943 |

## 2. Apuestas simuladas (reglas de producción, precio de apertura)

- Apuestas: `116` (ganadas `64` / liquidadas `116`, push `0`)
- **Stake fijo S/1**: neto `S/+9.49` | ROI `8.18%` | IC95 bootstrap `[-11.0218%, 28.2767%]` | MaxDD `7.02%`
- **Stake Kelly 25%** (S/1.00–S/10.00): banca final `S/109.22` | ROI `6.92%` | stake medio `S/1.15` | MaxDD `8.48%`
- **CLV vs cierre sin margen**: media `2.613%` | gana al cierre `0.5086` | IC95 `[-0.0034%, 5.3792%]`

| Grupo | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| :--- | ---: | ---: | ---: | ---: |
| mercado: `moneyline` | 55 | 32 | 16.81% [-11.6, 44.7] | 0.636% [-2.6, 3.8] |
| mercado: `total_points` | 61 | 32 | 0.4% [-23.4, 24.4] | 4.395% [0.6, 8.3] |
| temporada: `2024-25` | 37 | 24 | 26.27% [-4.2, 54.4] | 7.736% [2.9, 12.9] |
| temporada: `2025-26` | 72 | 38 | 3.33% [-20.4, 28.4] | -0.662% [-3.6, 2.2] |
| temporada: `2026-27` | 7 | 2 | -37.53% [-100.0, 47.5] | 9.217% [-0.4, 22.9] |

## 3. Sensibilidad al margen supuesto

| Margen | Mercado | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| ---: | :--- | ---: | ---: | ---: | ---: |
| 4.5% | `moneyline` | 55 | 32 | 16.81% [-11.6, 44.7] | 0.636% [-2.6, 3.8] |
| 4.5% | `total_points` | 61 | 32 | 0.4% [-23.4, 24.4] | 4.395% [0.6, 8.3] |
| 2.5% | `moneyline` | 181 | 104 | 7.66% [-8.4, 23.4] | 1.0% [-0.7, 2.8] |
| 2.5% | `total_points` | 236 | 119 | -1.61% [-13.4, 10.6] | 2.611% [0.9, 4.3] |

## 4. ¿El modelo anticipa el movimiento de línea? (todos los partidos, sin reglas de apuesta)

Correlación entre la discrepancia del modelo con la apertura y el movimiento apertura→cierre.

| Temporada | Mercado | N | Correlación [IC95] | Acierto de dirección |
| :--- | :--- | ---: | ---: | ---: |
| 2024-25 | moneyline | 830 | +0.048 [-0.043, +0.141] | 50.6% |
| 2024-25 | totals | 758 | +0.289 [+0.222, +0.350] | 58.3% |
| 2025-26 | moneyline | 1301 | +0.163 [+0.079, +0.259] | 56.4% |
| 2025-26 | totals | 1166 | +0.217 [+0.157, +0.278] | 55.9% |
| 2026-27 | moneyline | 143 | +0.418 [+0.274, +0.545] | 65.0% |
| 2026-27 | totals | 129 | +0.326 [+0.196, +0.469] | 64.3% |
| ALL | moneyline | 2274 | +0.136 [+0.075, +0.195] | 54.8% |
| ALL | totals | 2053 | +0.261 [+0.218, +0.298] | 57.3% |

## Supuestos
- Precio apostable = cuota justa de apertura / (1 + margen). La fuente publica probabilidades sin margen, no precios de casas.
- Totales: la línea principal de apertura es la más cercana a 50/50 (p=0.50); el cierre a esa línea se aproxima con un modelo normal (σ=18).
- Las features usan solo partidos que empezaron antes del primer partido de la jornada; los calibradores solo predicciones previas.
