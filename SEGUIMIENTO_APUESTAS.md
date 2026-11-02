# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)

- **Última actualización**: `2026-11-02 12:07 (Hora Perú UTC-5)` (`2026-11-02T17:07:43Z`)
- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/97.67 PEN`** (`-2.33 PEN`)
- **ROI Actual**: `-14.95%` | **Yield Actual**: `-12.45%` | **CLV Promedio**: `+2.17%` | **Max Drawdown**: `6.04%` | **Apuestas en espera**: `3` (`S/3.13 PEN` reservados)
- **Motor Predictivo Activo**: `Modelo F+G (ML LightGBM/Ridge + 10,000 Simulaciones Monte Carlo de Posesiones con Overtime, Fouling y Blowout + Conformal Prediction)`.
- **Modo de Apuesta Activo**: `Kelly-Conviccion Proporcional a la Ventaja (S/1.00 a S/6.00 PEN)` *(Modulado por EV real contra casas sharp, Guardian Activo de CLV que reduce exposicion ante movimientos adversos de linea, y Limite de Anti-Correlacion de 1 apuesta por partido)*.
- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)
- **Sistema de Aviso Automático (Doble Nivel)**: `ACTIVO` *(Recibirás un correo automático vía GitHub Issue `@Drewks` al desbloquear el **Nivel 1: Micro-Banca** y un segundo correo al desbloquear el **Nivel 2: Banca Completa**)*.

---

## 🚦 1. Semáforo de Madurez de 8 Criterios y Graduación en 2 Niveles

### Estado Global: **🔴 EN FASE DE CALIBRACIÓN Y PAPER TRADING (3/8 CRITERIOS EN VERDE — NO USAR DINERO REAL AÚN)**
- **Progreso Muestra Total (Nivel 1)**: `[█░░░░░░░░░░░░░░░░░░░] 14 / 500 apuestas (2.8%)` — *Faltan **486** apuestas.*
- **Progreso Muestra 100% En Vivo (ESPN/OddsAPI)**: `[█░░░░░░░░░░░░░░░░░░░] 14 / 200 en vivo (7.0%)` — *Tienes **3** apuestas reales en espera hoy.*

Para blindar tu capital contra rachas de suerte, el sistema evalúa **8 criterios cuantitativos estrictos** divididos en **2 niveles de graduación**:

| # | Criterio Cuantitativo de Auditoría | Estado Hoy | Valor Actual | Meta Nivel 1 (Piloto Micro-Banca 25%) | Meta Nivel 2 (Banca Completa 100%) |
| :-: | :--- | :---: | :--- | :--- | :--- |
| 1 | **Muestra total de apuestas liquidadas** | 🔴 PENDIENTE | `14 apuestas` | **>= 500 apuestas** | **>= 1,000 apuestas** |
| 2 | **Muestra 100% En Vivo (Pre-Partido Real)** | 🔴 PENDIENTE | `14 liquidadas (3 activas)` | **>= 200 en vivo** | **>= 500 en vivo** |
| 3 | **Calibración mejor que el Baseline (Brier & LogLoss)** | ✅ VERDE | `Brier 0.2359 vs 0.2612` | **Brier/LogLoss <= Base** | **Brier/LogLoss <= Base** |
| 4 | **Error de Calibración por Tramos (ECE)** | 🟡 AJUSTANDO | `ECE 0.1807 (18.07%)` | **ECE <= 5.0%** | **ECE <= 3.5%** |
| 5 | **Rentabilidad Neta Positiva (ROI y Yield)** | 🔴 PENDIENTE | `ROI -14.95% / Yield -12.45%` | **ROI >= +2.0% / Yield >= +1.5%** | **ROI >= +3.5% (ambos mercados > 0%)** |
| 6 | **Control de Caída Máxima (Max Drawdown)** | ✅ VERDE | `Total 6.04% (En vivo: 6.04%)` | **MaxDD <= 15.0%** | **MaxDD <= 15.0%** |
| 7 | **Exclusión Estadística del Azar (Bootstrap CI)** | 🔴 PENDIENTE | `IC90 [-56.4%, +30.4%] / IC95 [-67.6%, +33.8%]` | **IC 90% lím. inf. > 0%** | **IC 95% lím. inf. > 0%** |
| 8 | **Cero Fuga Temporal (Anti-Leakage) y SQLite** | ✅ VERDE | `0 violaciones / 100% íntegro` | **0 violaciones** | **0 violaciones** |

> **🔔 Doble aviso automático a tu correo**: No necesitas vigilar esta tabla a diario. Cuando las 8 filas lleguen a **✅ VERDE** en el **Nivel 1**, recibirás un correo de GitHub (`@Drewks`) autorizando pruebas con micro-banca (25% de tu stake). Cuando alcance el **Nivel 2** (`1,000` apuestas + `IC 95% > 0%`), recibirás el segundo correo de certificación completa.

---

## 🏀 2. Mis Apuestas NBA Reales (ESPN / Line Shopping 25 Casas)

> ### 🏆 PICK ESTRELLA DEL DÍA (`2026-11-02` — 1 Solo Pick: Mayor Probabilidad de Acierto)
> - **Partido**: **WAS @ ORL** (`2026-11-02 19:30 Hora Perú`)
> - **Pick Más Probable**: 🎯 **OVER 225.5** (Total Puntos (Over/Under)) @ **`1.990`** *(1xBet)*
> - **Probabilidad de Acierto (Modelo Calibrado)**: 🔥 **`51.8%`** | **EV**: `+3.0%`
> - **Envío diario a tu correo**: `ACTIVO` *(1 solo correo diario vía GitHub Notification `@Drewks` con la selección de mayor probabilidad de acierto y sin alerta CLV)*.

Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido, con vigilancia de movimiento en contra `CLV < -5.0%`):

| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Mejor Cuota (Casa) | Prob. Modelo | EV (%) | CLV (%) | Stake | Estado | Resultado / Ganancia |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |
| `2026-11-02 20:30` | **BOS @ HOU** | Total Puntos (Over/Under) | **OVER 219.5** | **1.990** *(1xBet)* | 51.3% | `+2.1%` | — | S/1.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-02 20:00` | **NOP @ MEM** | Ganador (Moneyline) | **AWAY (NOP gana)** | **2.900** *(888sport)* | 36.3% | `+5.3%` | `-10.77%` | S/1.00 | ⚠️ ALERTA CLV | ⚠️ Movimiento brusco en contra (posible baja de última hora) |
| `2026-11-02 19:30` | **WAS @ ORL** | Total Puntos (Over/Under) | **OVER 225.5** | **1.990** *(1xBet)* | 51.8% | `+3.0%` | — | S/1.13 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-01 21:00` | **TOR @ LAL** | Ganador (Moneyline) | **AWAY (TOR gana)** | **2.670** *(1xBet)* | 39.2% | `+4.7%` | `+10.79%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 131 - AWAY 125 (Total: 256)) |
| `2026-11-01 20:30` | **LAC @ GSW** | Ganador (Moneyline) | **HOME (GSW gana)** | **1.820** *(Betfair)* | 56.9% | `+3.6%` | `+0.00%` | S/1.41 | ✅ GANADA | S/+1.16 (HOME 124 - AWAY 112 (Total: 236)) |
| `2026-11-01 17:00` | **BKN @ IND** | Ganador (Moneyline) | **HOME (IND gana)** | **1.630** *(Betfair)* | 63.9% | `+4.2%` | `+0.62%` | S/2.16 | ❌ PERDIDA | S/-2.16 (HOME 90 - AWAY 98 (Total: 188)) |
| `2026-10-31 19:00` | **MIN @ SAS** | Ganador (Moneyline) | **AWAY (MIN gana)** | **5.400** *(DraftKings)* | 20.8% | `+12.2%` | `+0.00%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 121 - AWAY 111 (Total: 232)) |
| `2026-10-31 19:00` | **SAC @ MEM** | Ganador (Moneyline) | **AWAY (SAC gana)** | **4.400** *(DraftKings)* | 24.1% | `+6.1%` | `+14.29%` | S/1.04 | ❌ PERDIDA | S/-1.04 (HOME 136 - AWAY 105 (Total: 241)) |
| `2026-10-30 21:00` | **DEN @ PHX** | Ganador (Moneyline) | **HOME (PHX gana)** | **2.420** *(DraftKings)* | 56.4% | `+36.4%` | `-1.22%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 120 - AWAY 127 (Total: 247)) |
| `2026-10-30 21:00` | **DEN @ PHX** | Total Puntos (Over/Under) | **UNDER 230.5** | **1.909** *(DraftKings)* | 66.3% | `+26.6%` | — | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 120 - AWAY 127 (Total: 247)) |
| `2026-10-30 19:00` | **HOU @ DAL** | Ganador (Moneyline) | **HOME (DAL gana)** | **2.600** *(DraftKings)* | 49.9% | `+29.8%` | `-1.52%` | S/1.00 | ✅ GANADA | S/+1.60 (HOME 116 - AWAY 111 (Total: 227)) |
| `2026-10-29 21:00` | **MEM @ POR** | Total Puntos (Over/Under) | **UNDER 232.5** | **1.910** *(DraftKings)* | 63.5% | `+21.2%` | `-2.17%` | S/1.00 | ✅ GANADA | S/+0.91 (HOME 103 - AWAY 124 (Total: 227)) |
| `2026-10-29 19:00` | **SAC @ NOP** | Total Puntos (Over/Under) | **UNDER 237.5** | **1.950** *(Coolbet)* | 66.9% | `+30.4%` | — | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 132 - AWAY 120 (Total: 252)) |
| `2026-10-29 19:00` | **SAC @ NOP** | Ganador (Moneyline) | **HOME (NOP gana)** | **1.520** *(DraftKings)* | 71.7% | `+9.0%` | `+5.23%` | S/1.00 | ✅ GANADA | S/+0.52 (HOME 132 - AWAY 120 (Total: 252)) |
| `2026-10-28 21:30` | **LAL @ LAC** | Ganador (Moneyline) | **HOME (LAC gana)** | **1.970** *(Matchbook)* | 59.9% | `+17.9%` | `+0.00%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 87 - AWAY 103 (Total: 190)) |
| `2026-10-28 20:30` | **OKC @ DAL** | Ganador (Moneyline) | **HOME (DAL gana)** | **2.760** *(FanDuel)* | 49.8% | `+37.3%` | `+0.00%` | S/1.00 | ✅ GANADA | S/+1.76 (HOME 120 - AWAY 96 (Total: 216)) |
| `2026-10-28 20:30` | **OKC @ DAL** | Total Puntos (Over/Under) | **UNDER 228.5** | **1.920** *(GTbets)* | 57.0% | `+9.4%` | `+0.00%` | S/1.00 | ✅ GANADA | S/+0.92 (HOME 120 - AWAY 96 (Total: 216)) |

---

## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)

| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |
| `BET_20261102_555C3423` | `2026-11-02` | `TOR @ LAL` | Ganador (Moneyline) | **AWAY (TOR gana)** | 2.670 | 39.2% | `+4.7%` | ❌ LOST | **S/-1.00** | `S/96.51` |
| `BET_20261102_B4E13E3C` | `2026-11-02` | `LAC @ GSW` | Ganador (Moneyline) | **HOME (GSW gana)** | 1.820 | 56.9% | `+3.6%` | ✅ WON | **S/+1.16** | `S/97.67` |
| `BET_20261101_C66174F8` | `2026-11-01` | `BKN @ IND` | Ganador (Moneyline) | **HOME (IND gana)** | 1.630 | 63.9% | `+4.2%` | ❌ LOST | **S/-2.16** | `S/97.51` |
| `BET_20261101_3A37DB1F` | `2026-11-01` | `MIN @ SAS` | Ganador (Moneyline) | **AWAY (MIN gana)** | 5.400 | 20.8% | `+12.2%` | ❌ LOST | **S/-1.00** | `S/99.67` |
| `BET_20261101_B7BAE33B` | `2026-11-01` | `SAC @ MEM` | Ganador (Moneyline) | **AWAY (SAC gana)** | 4.400 | 24.1% | `+6.1%` | ❌ LOST | **S/-1.04** | `S/100.67` |
| `BET_20261031_B0C4035D` | `2026-10-31` | `DEN @ PHX` | Ganador (Moneyline) | **HOME (PHX gana)** | 2.420 | 56.4% | `+36.4%` | ❌ LOST | **S/-1.00** | `S/101.11` |
| `BET_20261031_90A3CA7F` | `2026-10-31` | `DEN @ PHX` | Total Puntos (Over/Under) | **UNDER 230.5** | 1.909 | 66.3% | `+26.6%` | ❌ LOST | **S/-1.00** | `S/101.71` |
| `BET_20261031_BAB6D884` | `2026-10-31` | `HOU @ DAL` | Ganador (Moneyline) | **HOME (DAL gana)** | 2.600 | 49.9% | `+29.8%` | ✅ WON | **S/+1.60** | `S/102.71` |
| `BET_20261030_A239BFAF` | `2026-10-30` | `MEM @ POR` | Total Puntos (Over/Under) | **UNDER 232.5** | 1.910 | 63.5% | `+21.2%` | ✅ WON | **S/+0.91** | `S/105.14` |
| `BET_20261030_26E1FE60` | `2026-10-30` | `SAC @ NOP` | Total Puntos (Over/Under) | **UNDER 237.5** | 1.950 | 66.9% | `+30.4%` | ❌ LOST | **S/-1.00** | `S/103.72` |
| `BET_20261030_0F72AE2C` | `2026-10-30` | `SAC @ NOP` | Ganador (Moneyline) | **HOME (NOP gana)** | 1.520 | 71.7% | `+9.0%` | ✅ WON | **S/+0.52** | `S/104.23` |
| `BET_20261029_82305F66` | `2026-10-29` | `LAL @ LAC` | Ganador (Moneyline) | **HOME (LAC gana)** | 1.970 | 59.9% | `+17.9%` | ❌ LOST | **S/-1.00** | `S/103.80` |
| `BET_20261029_748C9155` | `2026-10-29` | `OKC @ DAL` | Ganador (Moneyline) | **HOME (DAL gana)** | 2.760 | 49.8% | `+37.3%` | ✅ WON | **S/+1.76** | `S/104.80` |
| `BET_20261029_C23A720D` | `2026-10-29` | `OKC @ DAL` | Total Puntos (Over/Under) | **UNDER 228.5** | 1.920 | 57.0% | `+9.4%` | ✅ WON | **S/+0.92** | `S/104.72` |
| `BET_20260214_B0F1507E` | `2026-02-14` | `DET @ BOS` | Ganador (Moneyline) | **AWAY (DET gana)** | 3.743 | 37.7% | `+41.1%` | ✅ WON | **S/+2.74** | `S/104.03` |
| `BET_20260214_0B6BD1A0` | `2026-02-14` | `NYK @ CHI` | Total Puntos (Over/Under) | **UNDER 234.0** | 1.920 | 56.5% | `+8.5%` | ❌ LOST | **S/-1.00** | `S/103.03` |
| `BET_20260213_19395C1F` | `2026-02-13` | `CHA @ MIA` | Total Puntos (Over/Under) | **UNDER 232.5** | 1.962 | 61.9% | `+21.4%` | ❌ LOST | **S/-1.00** | `S/100.80` |
| `BET_20260213_0D8CC638` | `2026-02-13` | `POR @ HOU` | Total Puntos (Over/Under) | **UNDER 229.0** | 1.753 | 65.9% | `+15.6%` | ❌ LOST | **S/-1.00** | `S/99.80` |
| `BET_20260213_E3E2CE30` | `2026-02-13` | `SAS @ UTA` | Ganador (Moneyline) | **HOME (UTA gana)** | 2.491 | 45.4% | `+13.2%` | ✅ WON | **S/+1.49** | `S/101.29` |
| `BET_20260212_CC0CCA58` | `2026-02-12` | `MEM @ ATL` | Total Puntos (Over/Under) | **UNDER 228.5** | 2.271 | 50.5% | `+14.6%` | ❌ LOST | **S/-1.00** | `S/101.83` |
