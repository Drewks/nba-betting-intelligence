# Backtest con cuotas reales — prueba de robustez: 1 día de rezago de información, margen 2.5%

- Generado: `2026-11-09T18:44:24Z`
- Market data: minmaxxxer, 'NBA closing lines and ATS results' (HuggingFace), CC BY 4.0 — consensus no-vig opening/closing lines (median across bookmakers).
- Periodo de prueba desde `2025-01-01` | partidos con mercado emparejado: `2301`
- Reentrenamiento cada `7` días | margen supuesto `2.5%` | peso del modelo `0.3` | EV mínimo `5%`

## 1. Calidad probabilística fuera de muestra (todos los partidos)

| Serie | Mercado | N | Brier | LogLoss |
| :--- | :--- | ---: | ---: | ---: |
| `model_raw` | moneyline | 2301 | 0.20732 | 0.60154 |
| `model_calibrated` | moneyline | 2301 | 0.20710 | 0.60079 |
| `model_anchored_30_70` | moneyline | 2301 | 0.20121 | 0.58665 |
| `market_open` | moneyline | 2301 | 0.20108 | 0.58598 |
| `market_close` | moneyline | 2301 | 0.19684 | 0.57566 |
| `model_raw` | totals (línea de apertura) | 2301 | 0.25646 | 0.70757 |
| `model_calibrated` | totals (línea de apertura) | 2301 | 0.25428 | 0.70272 |
| `market_open_assumed_0.5` | totals (línea de apertura) | 2301 | 0.25000 | 0.69315 |
| `market_close_normal_approx` | totals (línea de apertura) | 2301 | 0.24324 | 0.67943 |

## 2. Apuestas simuladas (reglas de producción, precio de apertura)

- Apuestas: `301` (ganadas `116` / liquidadas `301`, push `0`)
- **Stake fijo S/1**: neto `S/+3.71` | ROI `1.23%` | IC95 bootstrap `[-14.0819%, 17.3784%]` | MaxDD `31.10%`
- **Stake Kelly 25%** (S/0.50–S/3.00): banca final `S/97.98` | ROI `-0.53%` | stake medio `S/1.26` | MaxDD `31.75%`
- **CLV vs cierre sin margen**: media `0.037%` | gana al cierre `0.4352` | IC95 `[-1.8662%, 1.9448%]`

| Grupo | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| :--- | ---: | ---: | ---: | ---: |
| mercado: `moneyline` | 206 | 72 | 6.24% [-14.7, 28.0] | -1.652% [-4.3, 0.9] |
| mercado: `total_points` | 95 | 44 | -9.63% [-29.4, 9.9] | 3.7% [1.0, 6.4] |
| temporada: `2024-25` | 110 | 44 | 15.8% [-15.0, 46.4] | -1.001% [-4.3, 2.3] |
| temporada: `2025-26` | 177 | 62 | -12.09% [-32.0, 7.8] | 0.339% [-2.1, 3.1] |
| temporada: `2026-27` | 14 | 10 | 55.15% [10.4, 95.6] | 4.381% [-2.0, 10.6] |

## 4. ¿El modelo anticipa el movimiento de línea? (todos los partidos, sin reglas de apuesta)

Correlación entre la discrepancia del modelo con la apertura y el movimiento apertura→cierre.

| Temporada | Mercado | N | Correlación [IC95] | Acierto de dirección |
| :--- | :--- | ---: | ---: | ---: |
| 2024-25 | moneyline | 830 | -0.013 [-0.087, +0.075] | 47.7% |
| 2024-25 | totals | 758 | +0.283 [+0.218, +0.346] | 59.0% |
| 2025-26 | moneyline | 1301 | +0.084 [+0.009, +0.170] | 52.7% |
| 2025-26 | totals | 1166 | +0.179 [+0.120, +0.241] | 55.3% |
| 2026-27 | moneyline | 143 | +0.380 [+0.238, +0.500] | 59.4% |
| 2026-27 | totals | 129 | +0.242 [+0.106, +0.406] | 59.7% |
| ALL | moneyline | 2274 | +0.064 [+0.007, +0.117] | 51.3% |
| ALL | totals | 2053 | +0.234 [+0.191, +0.272] | 56.9% |

## Supuestos
- Precio apostable = cuota justa de apertura / (1 + margen). La fuente publica probabilidades sin margen, no precios de casas.
- Totales: la línea principal de apertura es la más cercana a 50/50 (p=0.50); el cierre a esa línea se aproxima con un modelo normal (σ=18).
- Las features usan solo partidos que empezaron antes del primer partido de la jornada; los calibradores solo predicciones previas.
