# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)

- **Última actualización**: `2026-10-30 14:52 (Hora Perú UTC-5)` (`2026-10-30T19:52:57Z`)
- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/105.14 PEN`** (`+5.14 PEN`)
- **ROI Actual**: `+4.95%` | **Yield Actual**: `+4.81%` | **CLV Promedio**: `+13.20%` | **Max Drawdown**: `16.44%` | **Apuestas en espera**: `3` (`S/3.00 PEN` reservados)
- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)
- **Sistema de Aviso Automático (Doble Nivel)**: `ACTIVO` *(Recibirás un correo automático vía GitHub Issue `@Drewks` al desbloquear el **Nivel 1: Micro-Banca** y un segundo correo al desbloquear el **Nivel 2: Banca Completa**)*.

---

## 🚦 1. Semáforo de Madurez de 8 Criterios y Graduación en 2 Niveles

### Estado Global: **🔴 EN FASE DE CALIBRACIÓN Y PAPER TRADING (3/8 CRITERIOS EN VERDE — NO USAR DINERO REAL AÚN)**
- **Progreso Muestra Total (Nivel 1)**: `[████░░░░░░░░░░░░░░░░] 104 / 500 apuestas (20.8%)` — *Faltan **396** apuestas.*
- **Progreso Muestra 100% En Vivo (ESPN/OddsAPI)**: `[█░░░░░░░░░░░░░░░░░░░] 6 / 200 en vivo (3.0%)` — *Tienes **3** apuestas reales en espera hoy.*

Para blindar tu capital contra rachas de suerte, el sistema evalúa **8 criterios cuantitativos estrictos** divididos en **2 niveles de graduación**:

| # | Criterio Cuantitativo de Auditoría | Estado Hoy | Valor Actual | Meta Nivel 1 (Piloto Micro-Banca 25%) | Meta Nivel 2 (Banca Completa 100%) |
| :-: | :--- | :---: | :--- | :--- | :--- |
| 1 | **Muestra total de apuestas liquidadas** | 🔴 PENDIENTE | `104 apuestas` | **>= 500 apuestas** | **>= 1,000 apuestas** |
| 2 | **Muestra 100% En Vivo (Pre-Partido Real)** | 🔴 PENDIENTE | `6 liquidadas (3 activas)` | **>= 200 en vivo** | **>= 500 en vivo** |
| 3 | **Calibración mejor que el Baseline (Brier & LogLoss)** | ✅ VERDE | `Brier 0.2448 vs 0.2501` | **Brier/LogLoss <= Base** | **Brier/LogLoss <= Base** |
| 4 | **Error de Calibración por Tramos (ECE)** | 🟡 AJUSTANDO | `ECE 0.0611 (6.11%)` | **ECE <= 5.0%** | **ECE <= 3.5%** |
| 5 | **Rentabilidad Neta Positiva (ROI y Yield)** | ✅ VERDE | `ROI +4.95% / Yield +4.81%` | **ROI >= +2.0% / Yield >= +1.5%** | **ROI >= +3.5% (ambos mercados > 0%)** |
| 6 | **Control de Caída Máxima (Max Drawdown)** | 🔴 PENDIENTE | `Total 16.44% (En vivo: 1.06%)` | **MaxDD <= 15.0%** | **MaxDD <= 15.0%** |
| 7 | **Exclusión Estadística del Azar (Bootstrap CI)** | 🔴 PENDIENTE | `IC90 [-15.8%, +25.6%] / IC95 [-19.0%, +29.3%]` | **IC 90% lím. inf. > 0%** | **IC 95% lím. inf. > 0%** |
| 8 | **Cero Fuga Temporal (Anti-Leakage) y SQLite** | ✅ VERDE | `0 violaciones / 100% íntegro` | **0 violaciones** | **0 violaciones** |

> **🔔 Doble aviso automático a tu correo**: No necesitas vigilar esta tabla a diario. Cuando las 8 filas lleguen a **✅ VERDE** en el **Nivel 1**, recibirás un correo de GitHub (`@Drewks`) autorizando pruebas con micro-banca (25% de tu stake). Cuando alcance el **Nivel 2** (`1,000` apuestas + `IC 95% > 0%`), recibirás el segundo correo de certificación completa.

---

## 🏀 2. Mis Apuestas NBA Reales (ESPN / Line Shopping 25 Casas)

Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido, con vigilancia de movimiento en contra `CLV < -5.0%`):

| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Mejor Cuota (Casa) | Prob. Modelo | EV (%) | CLV (%) | Stake | Estado | Resultado / Ganancia |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |
| `2026-10-30 21:00` | **DEN @ PHX** | Ganador (Moneyline) | **HOME (PHX gana)** | **2.420** *(DraftKings)* | 56.4% | `+36.4%` | `-1.22%` | S/1.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-10-30 21:00` | **DEN @ PHX** | Total Puntos (Over/Under) | **UNDER 230.5** | **1.909** *(DraftKings)* | 66.3% | `+26.6%` | — | S/1.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-10-30 19:00` | **HOU @ DAL** | Ganador (Moneyline) | **HOME (DAL gana)** | **2.600** *(DraftKings)* | 49.9% | `+29.8%` | `-11.86%` | S/1.00 | ⚠️ ALERTA CLV | ⚠️ Movimiento brusco en contra (posible baja de última hora) |
| `2026-10-29 21:00` | **MEM @ POR** | Total Puntos (Over/Under) | **UNDER 232.5** | **1.910** *(DraftKings)* | 63.5% | `+21.2%` | `-2.17%` | S/1.00 | ✅ GANADA | S/+0.91 (HOME 103 - AWAY 124 (Total: 227)) |
| `2026-10-29 19:00` | **SAC @ NOP** | Total Puntos (Over/Under) | **UNDER 237.5** | **1.950** *(Coolbet)* | 66.9% | `+30.4%` | — | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 132 - AWAY 120 (Total: 252)) |
| `2026-10-29 19:00` | **SAC @ NOP** | Ganador (Moneyline) | **HOME (NOP gana)** | **1.520** *(DraftKings)* | 71.7% | `+9.0%` | `+5.23%` | S/1.00 | ✅ GANADA | S/+0.52 (HOME 132 - AWAY 120 (Total: 252)) |
| `2026-10-28 21:30` | **LAL @ LAC** | Ganador (Moneyline) | **HOME (LAC gana)** | **1.970** *(Matchbook)* | 59.9% | `+17.9%` | — | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 87 - AWAY 103 (Total: 190)) |
| `2026-10-28 20:30` | **OKC @ DAL** | Ganador (Moneyline) | **HOME (DAL gana)** | **2.760** *(FanDuel)* | 49.8% | `+37.3%` | — | S/1.00 | ✅ GANADA | S/+1.76 (HOME 120 - AWAY 96 (Total: 216)) |
| `2026-10-28 20:30` | **OKC @ DAL** | Total Puntos (Over/Under) | **UNDER 228.5** | **1.920** *(GTbets)* | 57.0% | `+9.4%` | — | S/1.00 | ✅ GANADA | S/+0.92 (HOME 120 - AWAY 96 (Total: 216)) |

---

## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)

| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |
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
| `BET_20260212_A176DD2E` | `2026-02-12` | `CHI @ MIL` | Total Puntos (Over/Under) | **UNDER 232.0** | 1.966 | 57.1% | `+12.2%` | ✅ WON | **S/+0.97** | `S/102.80` |
| `BET_20260212_28B25D61` | `2026-02-12` | `MEM @ ATL` | Ganador (Moneyline) | **AWAY (MEM gana)** | 2.673 | 40.2% | `+7.5%` | ❌ LOST | **S/-1.00** | `S/101.80` |
| `BET_20260211_97E7A2F9` | `2026-02-11` | `LAL @ ATL` | Ganador (Moneyline) | **AWAY (LAL gana)** | 3.201 | 37.6% | `+20.3%` | ❌ LOST | **S/-1.00** | `S/104.83` |
| `BET_20260211_29B2E95F` | `2026-02-11` | `CHI @ LAC` | Total Puntos (Over/Under) | **UNDER 223.5** | 2.839 | 40.2% | `+14.1%` | ❌ LOST | **S/-1.00** | `S/103.83` |
| `BET_20260211_3BD20466` | `2026-02-11` | `CHI @ LAC` | Ganador (Moneyline) | **AWAY (CHI gana)** | 3.134 | 35.5% | `+11.2%` | ❌ LOST | **S/-1.00** | `S/102.83` |
| `BET_20260210_B7F7BD22` | `2026-02-10` | `SAC @ NYK` | Ganador (Moneyline) | **AWAY (SAC gana)** | 3.245 | 37.4% | `+21.3%` | ✅ WON | **S/+2.25** | `S/107.83` |
| `BET_20260210_4F35CF74` | `2026-02-10` | `POR @ DAL` | Total Puntos (Over/Under) | **UNDER 230.5** | 1.706 | 70.4% | `+20.1%` | ❌ LOST | **S/-1.00** | `S/106.83` |
| `BET_20260210_034AEF70` | `2026-02-10` | `MIA @ LAC` | Ganador (Moneyline) | **AWAY (MIA gana)** | 2.883 | 39.2% | `+13.1%` | ❌ LOST | **S/-1.00** | `S/105.83` |
