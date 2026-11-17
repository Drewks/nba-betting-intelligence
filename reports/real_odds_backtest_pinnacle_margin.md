# Backtest con cuotas reales (consenso de apertura/cierre, sin margen)

- Generado: `2026-11-17T00:36:48Z`
- Market data: minmaxxxer, 'NBA closing lines and ATS results' (HuggingFace), CC BY 4.0 — consensus no-vig opening/closing lines (median across bookmakers).
- Periodo de prueba desde `2025-01-01` | partidos con mercado emparejado: `2352`
- Reentrenamiento cada `7` días | margen supuesto `3.2%` | peso del modelo `0.3` | EV mínimo `2%` | tope cuota Moneyline `2.8`

## 1. Calidad probabilística fuera de muestra (todos los partidos)

| Serie | Mercado | N | Brier | LogLoss |
| :--- | :--- | ---: | ---: | ---: |
| `model_raw` | moneyline | 2352 | 0.20525 | 0.59701 |
| `model_calibrated` | moneyline | 2352 | 0.20483 | 0.59524 |
| `model_anchored_30_70` | moneyline | 2352 | 0.20013 | 0.58396 |
| `market_open` | moneyline | 2352 | 0.20047 | 0.58466 |
| `market_close` | moneyline | 2352 | 0.19641 | 0.57479 |
| `model_raw` | totals (línea de apertura) | 2352 | 0.25533 | 0.70490 |
| `model_calibrated` | totals (línea de apertura) | 2352 | 0.25329 | 0.70048 |
| `model_anchored_30_70` | totals (línea de apertura) | 2352 | 0.24926 | 0.69166 |
| `market_open_assumed_0.5` | totals (línea de apertura) | 2352 | 0.25000 | 0.69315 |
| `market_close_normal_approx` | totals (línea de apertura) | 2352 | 0.24351 | 0.67998 |

## 2. Apuestas simuladas (reglas de producción, precio de apertura)

- Apuestas: `321` (ganadas `177` / liquidadas `321`, push `0`)
- **Stake fijo S/1**: neto `S/+15.77` | ROI `4.91%` | IC95 bootstrap `[-6.2405%, 16.3309%]` | MaxDD `11.58%`
- **Stake Kelly 25%** (S/1.00–S/10.00): banca final `S/118.53` | ROI `4.38%` | stake medio `S/1.32` | MaxDD `14.28%`
- **CLV vs cierre sin margen**: media `1.968%` | gana al cierre `0.5607` | IC95 `[0.5669%, 3.4547%]`

| Grupo | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| :--- | ---: | ---: | ---: | ---: |
| mercado: `moneyline` | 131 | 82 | 16.54% [-0.7, 34.3] | 0.654% [-1.2, 2.6] |
| mercado: `total_points` | 190 | 95 | -3.1% [-17.2, 9.9] | 2.874% [0.9, 5.0] |
| temporada: `2024-25` | 105 | 53 | -3.32% [-20.8, 16.9] | 4.872% [1.8, 8.0] |
| temporada: `2025-26` | 185 | 111 | 14.37% [-1.4, 29.0] | 0.203% [-1.4, 1.8] |
| temporada: `2026-27` | 31 | 13 | -23.64% [-48.4, 7.7] | 2.669% [-0.8, 6.4] |

## 4. ¿El modelo anticipa el movimiento de línea? (todos los partidos, sin reglas de apuesta)

Correlación entre la discrepancia del modelo con la apertura y el movimiento apertura→cierre.

| Temporada | Mercado | N | Correlación [IC95] | Acierto de dirección |
| :--- | :--- | ---: | ---: | ---: |
| 2024-25 | moneyline | 830 | +0.047 [-0.044, +0.140] | 50.7% |
| 2024-25 | totals | 758 | +0.288 [+0.222, +0.349] | 58.3% |
| 2025-26 | moneyline | 1301 | +0.163 [+0.079, +0.259] | 56.2% |
| 2025-26 | totals | 1166 | +0.217 [+0.157, +0.277] | 55.9% |
| 2026-27 | moneyline | 194 | +0.327 [+0.180, +0.472] | 62.4% |
| 2026-27 | totals | 176 | +0.345 [+0.221, +0.450] | 61.9% |
| ALL | moneyline | 2325 | +0.134 [+0.071, +0.196] | 54.8% |
| ALL | totals | 2100 | +0.260 [+0.215, +0.299] | 57.3% |

## 5. Holdout Congelado, Corrección Múltiple y Pistas Shadow

- Protocolo congelado: `V8_FROZEN_2026_11_15` | Desarrollo (`2024-25,2025-26`): `2155` juegos, `290` bets, ROI `7.97%`, CLV `1.893%` | Holdout de temporada CONTAMINADO (visto en reportes previos al freeze) (`2026-27`): `197` juegos, `31` bets, ROI `-23.64%`
- **Holdout hacia adelante** (partidos desde `2026-11-15T00:00:00Z`, único fuera de muestra real): `14` juegos, `0` bets, ROI `None%`, CLV `None%`
- Pruebas múltiples (`trials=9`, Bonferroni): ROI p-raw=`0.18166`, p-bonf=`1.0` | CLV p-raw=`0.00319`, p-bonf=`0.02871`
- **Uncapped Shadow (1u sin mínimos ni tope diario)**: `1493` señales, ROI 1u `1.22%`, CLV medio `0.246%`
- **Totals CLV-Targeted (1u anticipación cierre, sin holdout en fit)**: `1658` bets, ROI 1u `2.39%`, CLV `0.312%`, pendiente final `7.73249` (`n=2155`)

## Supuestos
- Precio apostable = cuota justa de apertura / (1 + margen). La fuente publica probabilidades sin margen, no precios de casas.
- Totales: la línea principal de apertura es la más cercana a 50/50 (p=0.50); el cierre a esa línea se aproxima con un modelo normal (σ=18).
- Las features usan solo partidos que empezaron antes del primer partido de la jornada; los calibradores y el estimador de cierre solo observaciones previas en desarrollo.
