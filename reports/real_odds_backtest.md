# Backtest con cuotas reales (consenso de apertura/cierre, sin margen)

- Generado: `2026-11-23T23:44:43Z`
- Market data: minmaxxxer, 'NBA closing lines and ATS results' (HuggingFace), CC BY 4.0 — consensus no-vig opening/closing lines (median across bookmakers).
- Periodo de prueba desde `2025-01-01` | partidos con mercado emparejado: `2403`
- Reentrenamiento cada `7` días | margen supuesto `4.5%` | peso del modelo `0.3` | EV mínimo `2%` | tope cuota Moneyline `2.8`

## 1. Calidad probabilística fuera de muestra (todos los partidos)

| Serie | Mercado | N | Brier | LogLoss |
| :--- | :--- | ---: | ---: | ---: |
| `model_raw` | moneyline | 2403 | 0.20611 | 0.59927 |
| `model_calibrated` | moneyline | 2403 | 0.20565 | 0.59737 |
| `model_anchored_30_70` | moneyline | 2403 | 0.20091 | 0.58579 |
| `market_open` | moneyline | 2403 | 0.20122 | 0.58639 |
| `market_close` | moneyline | 2403 | 0.19730 | 0.57683 |
| `model_raw` | totals (línea de apertura) | 2403 | 0.25536 | 0.70494 |
| `model_calibrated` | totals (línea de apertura) | 2403 | 0.25332 | 0.70052 |
| `model_anchored_30_70` | totals (línea de apertura) | 2403 | 0.24929 | 0.69173 |
| `market_open_assumed_0.5` | totals (línea de apertura) | 2403 | 0.25000 | 0.69315 |
| `market_close_normal_approx` | totals (línea de apertura) | 2403 | 0.24333 | 0.67963 |

## 2. Apuestas simuladas (reglas de producción, precio de apertura)

- Apuestas: `103` (ganadas `54` / liquidadas `103`, push `0`)
- **Stake fijo S/1**: neto `S/+2.73` | ROI `2.65%` | IC95 bootstrap `[-16.7483%, 22.3276%]` | MaxDD `6.35%`
- **Stake Kelly 25%** (S/1.00–S/10.00): banca final `S/101.93` | ROI `1.69%` | stake medio `S/1.11` | MaxDD `7.09%`
- **CLV vs cierre sin margen**: media `1.342%` | gana al cierre `0.4757` | IC95 `[-0.9982%, 3.8315%]`

| Grupo | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| :--- | ---: | ---: | ---: | ---: |
| mercado: `moneyline` | 46 | 28 | 21.67% [-7.9, 52.3] | 0.112% [-3.2, 3.5] |
| mercado: `total_points` | 57 | 26 | -12.7% [-36.2, 14.2] | 2.333% [-1.3, 6.1] |
| temporada: `2024-25` | 34 | 19 | 11.76% [-24.2, 47.5] | 4.928% [0.3, 9.9] |
| temporada: `2025-26` | 63 | 33 | 1.05% [-24.6, 25.2] | -0.827% [-3.7, 1.9] |
| temporada: `2026-27` | 6 | 2 | -32.27% [-100.0, 79.6] | 3.784% [-4.0, 20.0] |

## 3. Sensibilidad al margen supuesto

| Margen | Mercado | Apuestas | Ganadas | ROI stake fijo [IC95] | CLV medio [IC95] |
| ---: | :--- | ---: | ---: | ---: | ---: |
| 4.5% | `moneyline` | 46 | 28 | 21.67% [-7.9, 52.3] | 0.112% [-3.2, 3.5] |
| 4.5% | `total_points` | 57 | 26 | -12.7% [-36.2, 14.2] | 2.333% [-1.3, 6.1] |
| 2.5% | `moneyline` | 202 | 116 | 7.76% [-7.0, 22.2] | 0.568% [-1.0, 2.2] |
| 2.5% | `total_points` | 258 | 135 | 2.1% [-8.8, 14.3] | 2.681% [1.2, 4.3] |

## 4. ¿El modelo anticipa el movimiento de línea? (todos los partidos, sin reglas de apuesta)

Correlación entre la discrepancia del modelo con la apertura y el movimiento apertura→cierre.

| Temporada | Mercado | N | Correlación [IC95] | Acierto de dirección |
| :--- | :--- | ---: | ---: | ---: |
| 2024-25 | moneyline | 830 | +0.047 [-0.044, +0.140] | 50.7% |
| 2024-25 | totals | 758 | +0.288 [+0.222, +0.349] | 58.3% |
| 2025-26 | moneyline | 1301 | +0.163 [+0.079, +0.259] | 56.2% |
| 2025-26 | totals | 1166 | +0.217 [+0.157, +0.277] | 55.9% |
| 2026-27 | moneyline | 245 | +0.297 [+0.148, +0.435] | 60.8% |
| 2026-27 | totals | 222 | +0.328 [+0.226, +0.422] | 60.4% |
| ALL | moneyline | 2376 | +0.134 [+0.071, +0.196] | 54.8% |
| ALL | totals | 2146 | +0.260 [+0.217, +0.302] | 57.2% |

## 5. Holdout Congelado, Corrección Múltiple y Pistas Shadow

- Protocolo congelado: `V8_FROZEN_2026_11_15` | Desarrollo (`2024-25,2025-26`): `2155` juegos, `97` bets, ROI `4.81%`, CLV `1.19%` | Holdout de temporada CONTAMINADO (visto en reportes previos al freeze) (`2026-27`): `248` juegos, `6` bets, ROI `-32.27%`
- **Holdout hacia adelante** (partidos desde `2026-11-15T00:00:00Z`, único fuera de muestra real): `65` juegos, `0` bets, ROI `None%`, CLV `None%`
- Pruebas múltiples (`trials=11`, Bonferroni): ROI p-raw=`0.394547`, p-bonf=`1.0` | CLV p-raw=`0.153072`, p-bonf=`1.0`
- **Uncapped Shadow (1u sin mínimos ni tope diario)**: `960` señales, ROI 1u `-1.11%`, CLV medio `-0.784%`
- **Totals CLV-Targeted (1u anticipación cierre, sin holdout en fit)**: `1683` bets, ROI 1u `0.98%`, CLV `-0.951%`, pendiente final `7.73249` (`n=2155`)

## Supuestos
- Precio apostable = cuota justa de apertura / (1 + margen). La fuente publica probabilidades sin margen, no precios de casas.
- Totales: la línea principal de apertura es la más cercana a 50/50 (p=0.50); el cierre a esa línea se aproxima con un modelo normal (σ=18).
- Las features usan solo partidos que empezaron antes del primer partido de la jornada; los calibradores y el estimador de cierre solo observaciones previas en desarrollo.
