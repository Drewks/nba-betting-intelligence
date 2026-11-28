# Backtest con cuotas reales (consenso de apertura/cierre, sin margen)

- Generado: `2026-11-09T20:45:15Z`
- Market data: minmaxxxer, 'NBA closing lines and ATS results' (HuggingFace), CC BY 4.0 — consensus no-vig opening/closing lines (median across bookmakers).
- Periodo de prueba desde `2025-01-01` | partidos con mercado emparejado: `2301`
- Reentrenamiento cada `7` días | margen supuesto `2.5%` | peso del modelo `0.3` | EV mínimo `5%`

## 1. Calidad probabilística fuera de muestra (todos los partidos)

| Serie | Mercado | N | Brier | LogLoss |
| :--- | :--- | ---: | ---: | ---: |
| `model_raw` | moneyline | 2301 | 0.20619 | 0.59922 |
| `model_calibrated` | moneyline | 2301 | 0.20588 | 0.59778 |
| `model_anchored_30_70` | moneyline | 2301 | 0.20090 | 0.58571 |
| `market_open` | moneyline | 2301 | 0.20108 | 0.58598 |
| `market_close` | moneyline | 2301 | 0.19684 | 0.57566 |
| `model_raw` | totals (línea de apertura) | 2301 | 0.25646 | 0.70757 |
| `model_calibrated` | totals (línea de apertura) | 2301 | 0.25428 | 0.70272 |
| `market_open_assumed_0.5` | totals (línea de apertura) | 2301 | 0.25000 | 0.69315 |
| `market_close_normal_approx` | totals (línea de apertura) | 2301 | 0.24324 | 0.67943 |

## 2. Apuestas simuladas (reglas de producción, precio de apertura)

- Apuestas: `260` (ganadas `108` / liquidadas `260`, push `0`)
- **Stake fijo S/1**: neto `S/-7.78` | ROI `-2.99%` | IC95 bootstrap `[-17.9391%, 13.0631%]` | MaxDD `23.28%`
- **Stake Kelly 25%** (S/0.50–S/3.00): banca final `S/92.43` | ROI `-2.48%` | stake medio `S/1.17` | MaxDD `28.78%`
- **CLV vs cierre sin margen**: media `0.442%` | gana al cierre `0.4808` | IC95 `[-1.4616%, 2.1705%]`

| Grupo | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| :--- | ---: | ---: | ---: | ---: |
| mercado: `moneyline` | 162 | 60 | -2.12% [-21.8, 17.6] | -1.424% [-3.9, 0.9] |
| mercado: `total_points` | 98 | 48 | -4.43% [-22.7, 14.2] | 3.526% [0.5, 6.6] |
| temporada: `2024-25` | 90 | 34 | -9.28% [-36.6, 15.7] | 0.573% [-3.1, 4.5] |
| temporada: `2025-26` | 157 | 67 | -0.96% [-19.2, 17.9] | 0.042% [-2.2, 2.2] |
| temporada: `2026-27` | 13 | 7 | 15.96% [-30.9, 67.4] | 4.357% [-3.7, 11.5] |

## 4. ¿El modelo anticipa el movimiento de línea? (todos los partidos, sin reglas de apuesta)

Correlación entre la discrepancia del modelo con la apertura y el movimiento apertura→cierre.

| Temporada | Mercado | N | Correlación [IC95] | Acierto de dirección |
| :--- | :--- | ---: | ---: | ---: |
| 2024-25 | moneyline | 830 | +0.046 [-0.050, +0.143] | 52.2% |
| 2024-25 | totals | 758 | +0.283 [+0.218, +0.346] | 59.0% |
| 2025-26 | moneyline | 1301 | +0.150 [+0.069, +0.248] | 56.6% |
| 2025-26 | totals | 1166 | +0.179 [+0.120, +0.241] | 55.3% |
| 2026-27 | moneyline | 143 | +0.395 [+0.258, +0.511] | 61.5% |
| 2026-27 | totals | 129 | +0.242 [+0.106, +0.406] | 59.7% |
| ALL | moneyline | 2274 | +0.127 [+0.067, +0.183] | 55.3% |
| ALL | totals | 2053 | +0.234 [+0.191, +0.272] | 56.9% |

## Supuestos
- Precio apostable = cuota justa de apertura / (1 + margen). La fuente publica probabilidades sin margen, no precios de casas.
- Totales: la línea principal de apertura es la más cercana a 50/50 (p=0.50); el cierre a esa línea se aproxima con un modelo normal (σ=18).
- Las features usan solo partidos que empezaron antes del primer partido de la jornada; los calibradores solo predicciones previas.
