# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)

- **Última actualización**: `2026-11-09 01:28 (Hora Perú UTC-5)` (`2026-11-09T06:28:30Z`)
- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/103.63 PEN`** (`+3.63 PEN`)
- **ROI Actual**: `+9.24%` | **Yield Actual**: `+7.91%` | **CLV Promedio**: `+8.84%` | **Max Drawdown**: `6.09%` | **Apuestas en espera**: `3` (`S/6.62 PEN` reservados)
- **Motor Predictivo Activo**: `Modelo F+G (ML LightGBM/Ridge + 10,000 Simulaciones Monte Carlo de Posesiones con Overtime, Fouling y Blowout + Conformal Prediction)`.
- **Modo de Apuesta Activo**: `Kelly-Conviccion Proporcional a la Ventaja (S/1.00 a S/6.00 PEN)` *(Modulado por EV real contra casas sharp, Guardian Activo de CLV que reduce exposicion ante movimientos adversos de linea, y Limite de Anti-Correlacion de 1 apuesta por partido)*.
- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)
- **Sistema de Aviso Automático (Doble Nivel)**: `ACTIVO` *(Recibirás un correo automático vía GitHub Issue `@Drewks` al desbloquear el **Nivel 1: Micro-Banca** y un segundo correo al desbloquear el **Nivel 2: Banca Completa**)*.

---

## 🚦 1. Semáforo de Madurez de 8 Criterios y Graduación en 2 Niveles

### Estado Global: **🔴 EN FASE DE CALIBRACIÓN Y PAPER TRADING (4/8 CRITERIOS EN VERDE — NO USAR DINERO REAL AÚN)**
- **Progreso Muestra Total (Nivel 1)**: `[█░░░░░░░░░░░░░░░░░░░] 29 / 500 apuestas (5.8%)` — *Faltan **471** apuestas.*
- **Progreso Muestra 100% En Vivo (ESPN/OddsAPI)**: `[███░░░░░░░░░░░░░░░░░] 29 / 200 en vivo (14.5%)` — *Tienes **3** apuestas reales en espera hoy.*

Para blindar tu capital contra rachas de suerte, el sistema evalúa **8 criterios cuantitativos estrictos** divididos en **2 niveles de graduación**:

| # | Criterio Cuantitativo de Auditoría | Estado Hoy | Valor Actual | Meta Nivel 1 (Piloto Micro-Banca 25%) | Meta Nivel 2 (Banca Completa 100%) |
| :-: | :--- | :---: | :--- | :--- | :--- |
| 1 | **Muestra total de apuestas liquidadas** | 🔴 PENDIENTE | `29 apuestas` | **>= 500 apuestas** | **>= 1,000 apuestas** |
| 2 | **Muestra 100% En Vivo (Pre-Partido Real)** | 🔴 PENDIENTE | `29 liquidadas (3 activas)` | **>= 200 en vivo** | **>= 500 en vivo** |
| 3 | **Calibración mejor que el Baseline (Brier & LogLoss)** | ✅ VERDE | `Brier 0.2057 vs 0.2510` | **Brier/LogLoss <= Base** | **Brier/LogLoss <= Base** |
| 4 | **Error de Calibración por Tramos (ECE)** | 🟡 AJUSTANDO | `ECE 0.1682 (16.82%)` | **ECE <= 5.0%** | **ECE <= 3.5%** |
| 5 | **Rentabilidad Neta Positiva (ROI y Yield)** | ✅ VERDE | `ROI +9.24% / Yield +7.91%` | **ROI >= +2.0% / Yield >= +1.5%** | **ROI >= +3.5% (ambos mercados > 0%)** |
| 6 | **Control de Caída Máxima (Max Drawdown)** | ✅ VERDE | `Total 6.09% (En vivo: 6.09%)` | **MaxDD <= 15.0%** | **MaxDD <= 15.0%** |
| 7 | **Exclusión Estadística del Azar (Bootstrap CI)** | 🔴 PENDIENTE | `IC90 [-19.0%, +34.1%] / IC95 [-24.1%, +38.3%]` | **IC 90% lím. inf. > 0%** | **IC 95% lím. inf. > 0%** |
| 8 | **Cero Fuga Temporal (Anti-Leakage) y SQLite** | ✅ VERDE | `0 violaciones / 100% íntegro` | **0 violaciones** | **0 violaciones** |

> **🔔 Doble aviso automático a tu correo**: No necesitas vigilar esta tabla a diario. Cuando las 8 filas lleguen a **✅ VERDE** en el **Nivel 1**, recibirás un correo de GitHub (`@Drewks`) autorizando pruebas con micro-banca (25% de tu stake). Cuando alcance el **Nivel 2** (`1,000` apuestas + `IC 95% > 0%`), recibirás el segundo correo de certificación completa.

---

## 🏀 2. Mis Apuestas NBA Reales (ESPN / Line Shopping 25 Casas)

> ### 🏆 PICK ESTRELLA DEL DÍA (`2026-11-09` — 1 Solo Pick: Mayor Probabilidad de Acierto)
> - **Partido**: **Memphis Grizzlies @ Toronto Raptors (MEM @ TOR)** (`2026-11-09 19:30 Hora Perú`)
> - **Pick Más Probable**: 🎯 **Gana Toronto Raptors (TOR)** (Ganador (Moneyline)) @ **`1.641`** *(Draft Kings)*
> - **Probabilidad de Acierto (Modelo Calibrado)**: 🔥 **`63.3%`** | **EV**: `+3.9%`
> - **Envío diario a tu correo**: `ACTIVO` *(1 solo correo diario vía GitHub Notification `@Drewks` con la selección de mayor probabilidad de acierto y sin alerta CLV)*.

Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido, con vigilancia de movimiento en contra `CLV < -5.0%`):

| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Mejor Cuota (Casa) | Prob. Modelo | EV (%) | CLV (%) | Stake | Estado | Resultado / Ganancia |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |
| `2026-11-09 20:30` | **Denver Nuggets @ Houston Rockets (DEN @ HOU)** | Ganador (Moneyline) | **Gana Denver Nuggets (DEN)** | **3.370** *(DraftKings)* | 30.8% | `+3.8%` | — | S/1.12 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-09 19:30` | **Memphis Grizzlies @ Toronto Raptors (MEM @ TOR)** | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | **1.641** *(Draft Kings)* | 63.3% | `+3.9%` | — | S/3.50 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-09 19:00` | **Los Angeles Lakers @ Atlanta Hawks (LAL @ ATL)** | Total Puntos (Over/Under) | **UNDER 235.5 (Los Angeles Lakers @ Atlanta Hawks)** | **1.909** *(Draft Kings)* | 53.5% | `+2.1%` | — | S/2.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-08 21:00` | **New Orleans Pelicans @ LA Clippers (NOP @ LAC)** | Ganador (Moneyline) | **Gana LA Clippers (LAC)** | **1.917** *(1xBet Perú [T-6H Peru])* | 54.3% | `+4.0%` | `-5.57%` | S/2.00 | ✅ GANADA | S/+1.83 (HOME 139 - AWAY 123 (Total: 262)) |
| `2026-11-08 21:00` | **Miami Heat @ Sacramento Kings (MIA @ SAC)** | Ganador (Moneyline) | **Gana Miami Heat (MIA)** | **1.917** *(1xBet Perú [T-6H Peru])* | 53.5% | `+2.6%` | `+60.67%` | S/2.00 | ✅ GANADA | S/+1.83 (HOME 108 - AWAY 114 (Total: 222)) |
| `2026-11-07 22:00` | **San Antonio Spurs @ Portland Trail Blazers (SAS @ POR)** | Total Puntos (Over/Under) | **UNDER 228.5 (San Antonio Spurs @ Portland Trail Blazers)** | **1.909** *(DraftKings)* | 53.5% | `+2.2%` | — | S/1.34 | ✅ GANADA | S/+1.22 (HOME 103 - AWAY 125 (Total: 228)) |
| `2026-11-07 21:00` | **Houston Rockets @ Phoenix Suns (HOU @ PHX)** | Ganador (Moneyline) | **Gana Houston Rockets (HOU)** | **1.938** *(1xBet Perú [T-6H Peru])* | 54.0% | `+4.7%` | `+43.45%` | S/2.00 | ❌ PERDIDA | S/-2.00 (HOME 102 - AWAY 99 (Total: 201)) |
| `2026-11-07 20:30` | **Orlando Magic @ Golden State Warriors (ORL @ GSW)** | Ganador (Moneyline) | **Gana Golden State Warriors (GSW)** | **1.938** *(1xBet Perú [T-6H Peru])* | 54.5% | `+5.6%` | `+46.26%` | S/2.00 | ✅ GANADA | S/+1.88 (HOME 126 - AWAY 119 (Total: 245)) |
| `2026-11-06 22:00` | **San Antonio Spurs @ Sacramento Kings (SAS @ SAC)** | Total Puntos (Over/Under) | **UNDER 228.5 (San Antonio Spurs @ Sacramento Kings)** | **1.930** *(LowVig.ag)* | 53.2% | `+2.8%` | — | S/1.68 | ❌ PERDIDA | S/-1.68 (HOME 109 - AWAY 124 (Total: 233)) |
| `2026-11-06 20:00` | **Oklahoma City Thunder @ Memphis Grizzlies (OKC @ MEM)** | Ganador (Moneyline) | **Gana Oklahoma City Thunder (OKC)** | **1.606** *(DraftKings)* | 63.5% | `+2.0%` | `-0.86%` | S/1.96 | ✅ GANADA | S/+1.19 (HOME 97 - AWAY 128 (Total: 225)) |
| `2026-11-06 19:30` | **Philadelphia 76ers @ Cleveland Cavaliers (PHI @ CLE)** | Ganador (Moneyline) | **Gana Cleveland Cavaliers (CLE)** | **2.210** *(1xBet)* | 47.9% | `+5.9%` | — | S/1.36 | ✅ GANADA | S/+1.65 (HOME 119 - AWAY 95 (Total: 214)) |
| `2026-11-05 21:00` | **Orlando Magic @ Phoenix Suns (ORL @ PHX)** | Ganador (Moneyline) | **Gana Phoenix Suns (PHX)** | **1.910** *(Matchbook)* | 53.5% | `+2.2%` | — | S/1.39 | ✅ GANADA | S/+1.26 (HOME 117 - AWAY 104 (Total: 221)) |
| `2026-11-04 21:00` | **Toronto Raptors @ Denver Nuggets (TOR @ DEN)** | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | **2.900** *(Bovada)* | 37.2% | `+7.9%` | — | S/1.10 | ❌ PERDIDA | S/-1.10 (HOME 128 - AWAY 109 (Total: 237)) |
| `2026-11-04 20:00` | **Cleveland Cavaliers @ Oklahoma City Thunder (CLE @ OKC)** | Ganador (Moneyline) | **Gana Oklahoma City Thunder (OKC)** | **1.770** *(FanDuel)* | 58.5% | `+3.6%` | — | S/2.19 | ✅ GANADA | S/+1.69 (HOME 124 - AWAY 116 (Total: 240)) |
| `2026-11-04 19:00` | **Philadelphia 76ers @ Detroit Pistons (PHI @ DET)** | Ganador (Moneyline) | **Gana Detroit Pistons (DET)** | **1.810** *(Coolbet)* | 56.6% | `+2.5%` | — | S/1.57 | ❌ PERDIDA | S/-1.57 (HOME 106 - AWAY 112 (Total: 218)) |
| `2026-11-02 20:30` | **Boston Celtics @ Houston Rockets (BOS @ HOU)** | Total Puntos (Over/Under) | **OVER 219.5 (Boston Celtics @ Houston Rockets)** | **1.990** *(1xBet)* | 51.3% | `+2.1%` | — | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 109 - AWAY 93 (Total: 202)) |
| `2026-11-02 20:00` | **New Orleans Pelicans @ Memphis Grizzlies (NOP @ MEM)** | Ganador (Moneyline) | **Gana New Orleans Pelicans (NOP)** | **2.900** *(888sport)* | 36.3% | `+5.3%` | `-10.77%` | S/1.00 | ✅ GANADA | S/+1.90 (HOME 134 - AWAY 135 (Total: 269)) |
| `2026-11-02 19:30` | **Washington Wizards @ Orlando Magic (WAS @ ORL)** | Total Puntos (Over/Under) | **OVER 225.5 (Washington Wizards @ Orlando Magic)** | **1.990** *(1xBet)* | 51.8% | `+3.0%` | — | S/1.13 | ❌ PERDIDA | S/-1.13 (HOME 94 - AWAY 103 (Total: 197)) |
| `2026-11-01 21:00` | **Toronto Raptors @ Los Angeles Lakers (TOR @ LAL)** | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | **2.670** *(1xBet)* | 39.2% | `+4.7%` | `+10.79%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 131 - AWAY 125 (Total: 256)) |
| `2026-11-01 20:30` | **LA Clippers @ Golden State Warriors (LAC @ GSW)** | Ganador (Moneyline) | **Gana Golden State Warriors (GSW)** | **1.820** *(Betfair)* | 56.9% | `+3.6%` | `+0.00%` | S/1.41 | ✅ GANADA | S/+1.16 (HOME 124 - AWAY 112 (Total: 236)) |
| `2026-11-01 17:00` | **Brooklyn Nets @ Indiana Pacers (BKN @ IND)** | Ganador (Moneyline) | **Gana Indiana Pacers (IND)** | **1.630** *(Betfair)* | 63.9% | `+4.2%` | `+0.62%` | S/2.16 | ❌ PERDIDA | S/-2.16 (HOME 90 - AWAY 98 (Total: 188)) |
| `2026-10-31 19:00` | **Minnesota Timberwolves @ San Antonio Spurs (MIN @ SAS)** | Ganador (Moneyline) | **Gana Minnesota Timberwolves (MIN)** | **5.400** *(DraftKings)* | 20.8% | `+12.2%` | `+0.00%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 121 - AWAY 111 (Total: 232)) |
| `2026-10-31 19:00` | **Sacramento Kings @ Memphis Grizzlies (SAC @ MEM)** | Ganador (Moneyline) | **Gana Sacramento Kings (SAC)** | **4.400** *(DraftKings)* | 24.1% | `+6.1%` | `+14.29%` | S/1.04 | ❌ PERDIDA | S/-1.04 (HOME 136 - AWAY 105 (Total: 241)) |
| `2026-10-30 21:00` | **Denver Nuggets @ Phoenix Suns (DEN @ PHX)** | Ganador (Moneyline) | **Gana Phoenix Suns (PHX)** | **2.420** *(DraftKings)* | 56.4% | `+36.4%` | `-1.22%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 120 - AWAY 127 (Total: 247)) |
| `2026-10-30 21:00` | **Denver Nuggets @ Phoenix Suns (DEN @ PHX)** | Total Puntos (Over/Under) | **UNDER 230.5 (Denver Nuggets @ Phoenix Suns)** | **1.909** *(DraftKings)* | 66.3% | `+26.6%` | — | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 120 - AWAY 127 (Total: 247)) |
| `2026-10-30 19:00` | **Houston Rockets @ Dallas Mavericks (HOU @ DAL)** | Ganador (Moneyline) | **Gana Dallas Mavericks (DAL)** | **2.600** *(DraftKings)* | 49.9% | `+29.8%` | `-1.52%` | S/1.00 | ✅ GANADA | S/+1.60 (HOME 116 - AWAY 111 (Total: 227)) |
| `2026-10-29 21:00` | **Memphis Grizzlies @ Portland Trail Blazers (MEM @ POR)** | Total Puntos (Over/Under) | **UNDER 232.5 (Memphis Grizzlies @ Portland Trail Blazers)** | **1.910** *(DraftKings)* | 63.5% | `+21.2%` | `-2.17%` | S/1.00 | ✅ GANADA | S/+0.91 (HOME 103 - AWAY 124 (Total: 227)) |
| `2026-10-29 19:00` | **Sacramento Kings @ New Orleans Pelicans (SAC @ NOP)** | Total Puntos (Over/Under) | **UNDER 237.5 (Sacramento Kings @ New Orleans Pelicans)** | **1.950** *(Coolbet)* | 66.9% | `+30.4%` | — | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 132 - AWAY 120 (Total: 252)) |
| `2026-10-29 19:00` | **Sacramento Kings @ New Orleans Pelicans (SAC @ NOP)** | Ganador (Moneyline) | **Gana New Orleans Pelicans (NOP)** | **1.520** *(DraftKings)* | 71.7% | `+9.0%` | `+5.23%` | S/1.00 | ✅ GANADA | S/+0.52 (HOME 132 - AWAY 120 (Total: 252)) |
| `2026-10-28 21:30` | **Los Angeles Lakers @ LA Clippers (LAL @ LAC)** | Ganador (Moneyline) | **Gana LA Clippers (LAC)** | **1.970** *(Matchbook)* | 59.9% | `+17.9%` | `+0.00%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 87 - AWAY 103 (Total: 190)) |
| `2026-10-28 20:30` | **Oklahoma City Thunder @ Dallas Mavericks (OKC @ DAL)** | Ganador (Moneyline) | **Gana Dallas Mavericks (DAL)** | **2.760** *(FanDuel)* | 49.8% | `+37.3%` | `+0.00%` | S/1.00 | ✅ GANADA | S/+1.76 (HOME 120 - AWAY 96 (Total: 216)) |
| `2026-10-28 20:30` | **Oklahoma City Thunder @ Dallas Mavericks (OKC @ DAL)** | Total Puntos (Over/Under) | **UNDER 228.5 (Oklahoma City Thunder @ Dallas Mavericks)** | **1.920** *(GTbets)* | 57.0% | `+9.4%` | `+0.00%` | S/1.00 | ✅ GANADA | S/+0.92 (HOME 120 - AWAY 96 (Total: 216)) |

### 🔍 2.A Radiografía de Apuestas Activas (¿Qué Está Apostando Hoy, Cuotas y Estadísticas Clave?)

#### 🎯 **Los Angeles Lakers @ Atlanta Hawks (LAL @ ATL)** — `2026-11-09 19:00 Hora Perú`
- **¿Qué está apostando el bot?**: **UNDER 235.5 (Los Angeles Lakers @ Atlanta Hawks)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`1.909`** en *Draft Kings* vs Cuota Justa del Modelo **`1.869`** *(Ventaja Matemática EV: `+2.13%`)*
- **Stake y Ganancia Potencial**: Stake **`S/2.00 PEN`** → Ganancia neta potencial: **`+S/1.82 PEN`** *(Retorno total: `S/3.82 PEN`)*
- **Probabilidades**: Modelo Calibrado **`53.5%`** vs Probabilidad Implícita Limpia Casa **`53.2%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `ATL -1.2 pts` | Total esperado **`229.8 pts`** *(Rango 80% Conformal: `207 – 253 pts` | Prob. Prórroga: `8.6%` | Prob. Paliza: `10.9%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `ATL 1537` vs `LAL 1607` | **Eficiencia Neta (Off/Def)**: `ATL (115.1/115.0)` vs `LAL (115.3/111.9)` (`Dif: -3.3 pts/100`)
  - **Ritmo (Pace)**: `99.7 posesiones` | **Descanso**: `ATL 2d` vs `LAL 2d` | **Viaje Geodésico (Millas Haversine)**: `Dif. +598 millas` (`0 husos horarios`)
- **Por qué apostó el modelo**: _Visita (Los Angeles Lakers) viaja +598 millas más · Eficiencia neta favorable (Los Angeles Lakers [LAL] +3.3 pts/100) · Cuota 1.909 en Draft Kings supera la cuota justa del modelo (1.869)._

#### 🎯 **Memphis Grizzlies @ Toronto Raptors (MEM @ TOR)** — `2026-11-09 19:30 Hora Perú`
- **¿Qué está apostando el bot?**: **Gana Toronto Raptors (TOR - Local)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`1.641`** en *Draft Kings* vs Cuota Justa del Modelo **`1.580`** *(Ventaja Matemática EV: `+3.92%`)*
- **Stake y Ganancia Potencial**: Stake **`S/3.50 PEN`** → Ganancia neta potencial: **`+S/2.24 PEN`** *(Retorno total: `S/5.74 PEN`)*
- **Probabilidades**: Modelo Calibrado **`63.3%`** vs Probabilidad Implícita Limpia Casa **`54.7%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `TOR +5.1 pts` | Total esperado **`227.4 pts`** *(Rango 80% Conformal: `204 – 251 pts` | Prob. Prórroga: `8.5%` | Prob. Paliza: `11.8%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `TOR 1534` vs `MEM 1430` | **Eficiencia Neta (Off/Def)**: `TOR (113.2/112.4)` vs `MEM (114.2/116.3)` (`Dif: +2.9 pts/100`)
  - **Ritmo (Pace)**: `99.4 posesiones` | **Descanso**: `TOR 3d` vs `MEM 3d` | **Viaje Geodésico (Millas Haversine)**: `Dif. +386 millas` (`1 husos horarios`)
- **Por qué apostó el modelo**: _Eficiencia neta favorable (Toronto Raptors [TOR] +2.9 pts/100) · Cuota 1.641 en Draft Kings supera la cuota justa del modelo (1.580)._

#### 🎯 **Denver Nuggets @ Houston Rockets (DEN @ HOU)** — `2026-11-09 20:30 Hora Perú`
- **¿Qué está apostando el bot?**: **Gana Denver Nuggets (DEN - Visita)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`3.370`** en *DraftKings* vs Cuota Justa del Modelo **`3.247`** *(Ventaja Matemática EV: `+3.80%`)*
- **Stake y Ganancia Potencial**: Stake **`S/1.12 PEN`** → Ganancia neta potencial: **`+S/2.65 PEN`** *(Retorno total: `S/3.77 PEN`)*
- **Probabilidades**: Modelo Calibrado **`30.8%`** vs Probabilidad Implícita Limpia Casa **`25.8%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `HOU +3.4 pts` | Total esperado **`222.4 pts`** *(Rango 80% Conformal: `200 – 245 pts` | Prob. Prórroga: `8.5%` | Prob. Paliza: `10.7%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `HOU 1615` vs `DEN 1562` | **Eficiencia Neta (Off/Def)**: `HOU (113.2/108.6)` vs `DEN (116.0/113.8)` (`Dif: +2.5 pts/100`)
  - **Ritmo (Pace)**: `98.7 posesiones` | **Descanso**: `HOU 2d` vs `DEN 3d` | **Viaje Geodésico (Millas Haversine)**: `Dif. -149 millas` (`1 husos horarios`)
- **Por qué apostó el modelo**: _Ajuste de retorno de gira para Houston Rockets · Eficiencia neta favorable (Houston Rockets [HOU] +2.5 pts/100) · Cuota 3.370 en DraftKings supera la cuota justa del modelo (3.247)._

### 📋 2.B Cartelera Completa de Próximos Partidos: Cuotas, Estadísticas a Tomar en Cuenta y Veredicto

| Hora (Perú) | Partido (`Visita @ Local`) | Cuotas Ganador (`Local / Visita`) | Línea Total (`O/U`) | Proyección Modelo (`Margen / Total`) | Estadísticas Clave (`Elo`, `NetRtg`, `Descanso`, `Viaje`) | ¿Qué Hace el Bot y Por Qué? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `2026-11-09 19:00` | **Los Angeles Lakers @ Atlanta Hawks (LAL @ ATL)** | Local **2.170** / Visita **1.910** *(Draft Kings)* | **235.5** (`O 1.91` / `U 1.91`) | **LAL -1.2 pts** (Prob Local `47.3%`) · Total **229.8 pts** | Elo `1537/1607` · Net `-3.3` · Pace `99.7` · Desc `2d/2d` · Viaje `+598 mi` | **🎯 APOSTADO: UNDER 235.5 (Los Angeles Lakers @ Atlanta Hawks) @ 1.909 (Draft Kings) | Stake S/2.00 (EV +2.13%)** — _Visita (Los Angeles Lakers) viaja +598 millas más · Eficiencia neta favorable (Los Angeles Lakers [LAL] +3.3 pts/100) · Cuota 1.909 en Draft Kings supera la cuota justa del modelo (1.869)._ |
| `2026-11-09 19:00` | **Cleveland Cavaliers @ Charlotte Hornets (CLE @ CHA)** | Local **3.840** / Visita **1.910** *(Draft Kings)* | **215.5** (`O 1.89` / `U 1.94`) | **CLE -2.9 pts** (Prob Local `43.1%`) · Total **220.7 pts** | Elo `1465/1564` · Net `-6.5` · Pace `98.3` · Desc `3d/2d` · Viaje `+436 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-09 19:00` | **Washington Wizards @ Detroit Pistons (WAS @ DET)** | Local **1.910** / Visita **4.610** *(Pinnacle [LIVE_SCRAPER])* | **218.5** (`O 1.91` / `U 1.91`) | **DET -14.4 pts** (Prob Local `88.9%`) · Total **220.5 pts** | Elo `1638/1344` · Net `+12.0` · Pace `98.1` · Desc `2d/2d` · Viaje `+909 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-09 19:30` | **Memphis Grizzlies @ Toronto Raptors (MEM @ TOR)** | Local **1.910** / Visita **2.310** *(Pinnacle [LIVE_SCRAPER])* | **230.5** (`O 1.93` / `U 1.89`) | **TOR -5.1 pts** (Prob Local `69.0%`) · Total **227.4 pts** | Elo `1534/1430` · Net `+2.9` · Pace `99.4` · Desc `3d/3d` · Viaje `+386 mi` | **🎯 APOSTADO: Gana Toronto Raptors (TOR - Local) @ 1.641 (Draft Kings) | Stake S/3.50 (EV +3.92%)** — _Eficiencia neta favorable (Toronto Raptors [TOR] +2.9 pts/100) · Cuota 1.641 en Draft Kings supera la cuota justa del modelo (1.580)._ |
| `2026-11-09 20:00` | **Indiana Pacers @ Dallas Mavericks (IND @ DAL)** | Local **1.910** / Visita **2.420** *(Pinnacle [LIVE_SCRAPER])* | **222.5** (`O 1.91` / `U 1.91`) | **DAL -4.1 pts** (Prob Local `64.9%`) · Total **222.7 pts** | Elo `1442/1353` · Net `+3.9` · Pace `98.7` · Desc `1d/3d` · Viaje `+764 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-09 20:30` | **Denver Nuggets @ Houston Rockets (DEN @ HOU)** | Local **1.344** / Visita **3.860** *(Draft Kings)* | **217.5** (`O 1.91` / `U 1.91`) | **HOU -3.4 pts** (Prob Local `62.7%`) · Total **222.4 pts** | Elo `1615/1562` · Net `+2.5` · Pace `98.7` · Desc `2d/3d` · Viaje `-149 mi` | **🎯 APOSTADO: Gana Denver Nuggets (DEN - Visita) @ 3.370 (DraftKings) | Stake S/1.12 (EV +3.80%)** — _Ajuste de retorno de gira para Houston Rockets · Eficiencia neta favorable (Houston Rockets [HOU] +2.5 pts/100) · Cuota 3.370 en DraftKings supera la cuota justa del modelo (3.247)._ |
| `2026-11-09 21:00` | **San Antonio Spurs @ Phoenix Suns (SAS @ PHX)** | Local **3.820** / Visita **1.360** *(Draft Kings)* | **228.5** (`O 1.93` / `U 1.91`) | **SAS -5.7 pts** (Prob Local `30.6%`) · Total **224.8 pts** | Elo `1484/1697` · Net `-7.2` · Pace `99.3` · Desc `2d/2d` · Viaje `+1006 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-09 22:00` | **New Orleans Pelicans @ Golden State Warriors (NOP @ GSW)** | Local **1.910** / Visita **4.000** *(Pinnacle [LIVE_SCRAPER])* | **231.5** (`O 1.91` / `U 1.91`) | **GSW -7.8 pts** (Prob Local `75.0%`) · Total **231.2 pts** | Elo `1514/1421` · Net `+4.0` · Pace `100.4` · Desc `2d/1d` · Viaje `+348 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-10 19:30` | **Milwaukee Bucks @ New York Knicks (MIL @ NYK)** | Local **1.910** / Visita **1.910** *(Pinnacle [LIVE_SCRAPER])* | Línea est. `228.5` | **NYK -14.8 pts** (Prob Local `89.6%`) · Total **219.3 pts** | Elo `1668/1349` · Net `+12.0` · Pace `98.4` · Desc `3d/2d` · Viaje `+329 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-10 20:00` | **Boston Celtics @ Philadelphia 76ers (BOS @ PHI)** | Local **1.917** / Visita **1.917** *(Draft Kings)* | **215.5** (`O 1.94` / `U 1.88`) | **BOS -1.7 pts** (Prob Local `46.8%`) · Total **217.0 pts** | Elo `1553/1626` · Net `-4.9` · Pace `98.2` · Desc `3d/2d` · Viaje `+27 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-10 21:00` | **LA Clippers @ Phoenix Suns (LAC @ PHX)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **PHX -3.1 pts** (Prob Local `60.1%`) · Total **226.4 pts** | Elo `1484/1480` · Net `+1.8` · Pace `100.1` · Desc `3d/2d` · Viaje `+362 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-10 21:00` | **Miami Heat @ Utah Jazz (MIA @ UTA)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **MIA -5.9 pts** (Prob Local `31.4%`) · Total **232.0 pts** | Elo `1294/1479` · Net `-8.9` · Pace `99.4` · Desc `2d/2d` · Viaje `-452 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-10 22:00` | **Orlando Magic @ Sacramento Kings (ORL @ SAC)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **ORL -3.2 pts** (Prob Local `38.4%`) · Total **223.9 pts** | Elo `1343/1479` · Net `-4.1` · Pace `99.3` · Desc `2d/3d` · Viaje `+74 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-10 23:00` | **Oklahoma City Thunder @ Portland Trail Blazers (OKC @ POR)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **OKC -3.8 pts** (Prob Local `38.3%`) · Total **221.8 pts** | Elo `1535/1671` · Net `-6.6` · Pace `99.0` · Desc `3d/3d` · Viaje `+1485 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 19:00` | **Washington Wizards @ Indiana Pacers (WAS @ IND)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **IND -3.3 pts** (Prob Local `60.5%`) · Total **223.0 pts** | Elo `1353/1344` · Net `+2.4` · Pace `98.4` · Desc `5d/4d` · Viaje `+688 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 19:00` | **Cleveland Cavaliers @ New York Knicks (CLE @ NYK)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **NYK -5.7 pts** (Prob Local `70.1%`) · Total **220.5 pts** | Elo `1668/1564` · Net `+4.0` · Pace `98.3` · Desc `4d/4d` · Viaje `+0 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 19:00` | **Boston Celtics @ Toronto Raptors (BOS @ TOR)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **BOS -3.0 pts** (Prob Local `42.7%`) · Total **219.7 pts** | Elo `1534/1626` · Net `-6.2` · Pace `99.1` · Desc `5d/3d` · Viaje `+0 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 20:00` | **San Antonio Spurs @ Chicago Bulls (SAS @ CHI)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **SAS -10.4 pts** (Prob Local `18.5%`) · Total **232.8 pts** | Elo `1364/1697` · Net `-13.0` · Pace `100.0` · Desc `4d/4d` · Viaje `+1752 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 20:00` | **Denver Nuggets @ Memphis Grizzlies (DEN @ MEM)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **DEN -2.7 pts** (Prob Local `40.6%`) · Total **228.7 pts** | Elo `1430/1562` · Net `-4.5` · Pace `98.9` · Desc `5d/5d` · Viaje `+384 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 20:00` | **Los Angeles Lakers @ Milwaukee Bucks (LAL @ MIL)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **LAL -7.8 pts** (Prob Local `24.4%`) · Total **227.0 pts** | Elo `1349/1607` · Net `-9.0` · Pace `99.8` · Desc `3d/4d` · Viaje `+252 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 20:00` | **Brooklyn Nets @ New Orleans Pelicans (BKN @ NOP)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **NOP -6.1 pts** (Prob Local `70.3%`) · Total **226.4 pts** | Elo `1421/1331` · Net `+4.5` · Pace `99.7` · Desc `3d/3d` · Viaje `-1232 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 21:00` | **Orlando Magic @ Utah Jazz (ORL @ UTA)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **ORL -3.6 pts** (Prob Local `36.0%`) · Total **223.5 pts** | Elo `1294/1479` · Net `-5.6` · Pace `98.3` · Desc `3d/4d` · Viaje `-387 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 21:30` | **Golden State Warriors @ Houston Rockets (GSW @ HOU)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **HOU -5.6 pts** (Prob Local `69.9%`) · Total **222.1 pts** | Elo `1615/1514` · Net `+3.5` · Pace `99.4` · Desc `4d/4d` · Viaje `+627 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 22:00` | **Oklahoma City Thunder @ Portland Trail Blazers (OKC @ POR)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **OKC -3.9 pts** (Prob Local `38.1%`) · Total **221.8 pts** | Elo `1535/1671` · Net `-6.6` · Pace `99.0` · Desc `4d/4d` · Viaje `+1485 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |

---

## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)

| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |
| `BET_20261109_A985B0D3` | `2026-11-09` | `New Orleans Pelicans @ LA Clippers (NOP @ LAC)` | Ganador (Moneyline) | **Gana LA Clippers (LAC)** | 1.917 | 54.3% | `+4.0%` | ✅ WON | **S/+1.83** | `S/101.80` |
| `BET_20261109_0E342DCD` | `2026-11-09` | `Miami Heat @ Sacramento Kings (MIA @ SAC)` | Ganador (Moneyline) | **Gana Miami Heat (MIA)** | 1.917 | 53.5% | `+2.6%` | ✅ WON | **S/+1.83** | `S/103.63` |
| `BET_20261108_2DE83152` | `2026-11-08` | `San Antonio Spurs @ Portland Trail Blazers (SAS @ POR)` | Total Puntos (Over/Under) | **UNDER 228.5 (San Antonio Spurs @ Portland Trail Blazers)** | 1.909 | 53.5% | `+2.2%` | ✅ WON | **S/+1.22** | `S/103.00` |
| `BET_20261108_557A18AF` | `2026-11-08` | `Houston Rockets @ Phoenix Suns (HOU @ PHX)` | Ganador (Moneyline) | **Gana Houston Rockets (HOU)** | 1.938 | 54.0% | `+4.7%` | ❌ LOST | **S/-2.00** | `S/101.78` |
| `BET_20261108_458792F8` | `2026-11-08` | `Orlando Magic @ Golden State Warriors (ORL @ GSW)` | Ganador (Moneyline) | **Gana Golden State Warriors (GSW)** | 1.938 | 54.5% | `+5.6%` | ✅ WON | **S/+1.88** | `S/103.78` |
| `BET_20261107_7EA0942D` | `2026-11-07` | `San Antonio Spurs @ Sacramento Kings (SAS @ SAC)` | Total Puntos (Over/Under) | **UNDER 228.5 (San Antonio Spurs @ Sacramento Kings)** | 1.930 | 53.2% | `+2.8%` | ❌ LOST | **S/-1.68** | `S/98.87` |
| `BET_20261107_7C4523D5` | `2026-11-07` | `Oklahoma City Thunder @ Memphis Grizzlies (OKC @ MEM)` | Ganador (Moneyline) | **Gana Oklahoma City Thunder (OKC)** | 1.606 | 63.5% | `+2.0%` | ✅ WON | **S/+1.19** | `S/100.55` |
| `BET_20261107_CB5E045A` | `2026-11-07` | `Philadelphia 76ers @ Cleveland Cavaliers (PHI @ CLE)` | Ganador (Moneyline) | **Gana Cleveland Cavaliers (CLE)** | 2.210 | 47.9% | `+5.9%` | ✅ WON | **S/+1.65** | `S/99.36` |
| `BET_20261106_92B26B33` | `2026-11-06` | `Orlando Magic @ Phoenix Suns (ORL @ PHX)` | Ganador (Moneyline) | **Gana Phoenix Suns (PHX)** | 1.910 | 53.5% | `+2.2%` | ✅ WON | **S/+1.26** | `S/97.72` |
| `BET_20261105_A563FA74` | `2026-11-05` | `Toronto Raptors @ Denver Nuggets (TOR @ DEN)` | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | 2.900 | 37.2% | `+7.9%` | ❌ LOST | **S/-1.10** | `S/96.45` |
| `BET_20261105_63E8261D` | `2026-11-05` | `Cleveland Cavaliers @ Oklahoma City Thunder (CLE @ OKC)` | Ganador (Moneyline) | **Gana Oklahoma City Thunder (OKC)** | 1.770 | 58.5% | `+3.6%` | ✅ WON | **S/+1.69** | `S/99.12` |
| `BET_20261105_11DC3E0B` | `2026-11-05` | `Philadelphia 76ers @ Detroit Pistons (PHI @ DET)` | Ganador (Moneyline) | **Gana Detroit Pistons (DET)** | 1.810 | 56.6% | `+2.5%` | ❌ LOST | **S/-1.57** | `S/97.55` |
| `BET_20261103_06657F1C` | `2026-11-03` | `Boston Celtics @ Houston Rockets (BOS @ HOU)` | Total Puntos (Over/Under) | **OVER 219.5 (Boston Celtics @ Houston Rockets)** | 1.990 | 51.3% | `+2.1%` | ❌ LOST | **S/-1.00** | `S/97.44` |
| `BET_20261103_EF0858D0` | `2026-11-03` | `New Orleans Pelicans @ Memphis Grizzlies (NOP @ MEM)` | Ganador (Moneyline) | **Gana New Orleans Pelicans (NOP)** | 2.900 | 36.3% | `+5.3%` | ✅ WON | **S/+1.90** | `S/98.44` |
| `BET_20261103_E59224AE` | `2026-11-03` | `Washington Wizards @ Orlando Magic (WAS @ ORL)` | Total Puntos (Over/Under) | **OVER 225.5 (Washington Wizards @ Orlando Magic)** | 1.990 | 51.8% | `+3.0%` | ❌ LOST | **S/-1.13** | `S/96.54` |
| `BET_20261102_555C3423` | `2026-11-02` | `Toronto Raptors @ Los Angeles Lakers (TOR @ LAL)` | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | 2.670 | 39.2% | `+4.7%` | ❌ LOST | **S/-1.00** | `S/96.51` |
| `BET_20261102_B4E13E3C` | `2026-11-02` | `LA Clippers @ Golden State Warriors (LAC @ GSW)` | Ganador (Moneyline) | **Gana Golden State Warriors (GSW)** | 1.820 | 56.9% | `+3.6%` | ✅ WON | **S/+1.16** | `S/97.67` |
| `BET_20261101_C66174F8` | `2026-11-01` | `Brooklyn Nets @ Indiana Pacers (BKN @ IND)` | Ganador (Moneyline) | **Gana Indiana Pacers (IND)** | 1.630 | 63.9% | `+4.2%` | ❌ LOST | **S/-2.16** | `S/97.51` |
| `BET_20261101_3A37DB1F` | `2026-11-01` | `Minnesota Timberwolves @ San Antonio Spurs (MIN @ SAS)` | Ganador (Moneyline) | **Gana Minnesota Timberwolves (MIN)** | 5.400 | 20.8% | `+12.2%` | ❌ LOST | **S/-1.00** | `S/99.67` |
| `BET_20261101_B7BAE33B` | `2026-11-01` | `Sacramento Kings @ Memphis Grizzlies (SAC @ MEM)` | Ganador (Moneyline) | **Gana Sacramento Kings (SAC)** | 4.400 | 24.1% | `+6.1%` | ❌ LOST | **S/-1.04** | `S/100.67` |

---

## 🎯 4. Seguimiento Oficial de Paper Trading — Player Props & SGP RETAbet V8

- **Banca Virtual de Props**: `S/100.00 PEN` (Inicial) → **`S/79.35 PEN`** (`-20.65 PEN`)
- **Tasa de Acierto (Win Rate)**: **`45.2%`** (`19G - 23P - 0E`)
- **ROI Acumulado en Props**: **`-14.05%`** | **Total Apostado**: `S/147.00 PEN`
- **Brier Score (Calibración)**: `0.2780` | **Cobertura Conformal**: `45.2%`
- **Total de Picks Registrados**: `259` (`144` en espera / `115` liquidados)

### 📊 Desglose de Rendimiento por Categoría de Prop

| Categoría | Liquidadas | Ganadas | Perdidas | Acierto (%) | Total Apostado (S/) | Beneficio Neto (S/) | ROI (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **PTS** | 10 | 0 | 6 | `0.0%` | S/21.00 | **S/-21.00** | `-100.0%` |
| **REB** | 8 | 5 | 0 | `100.0%` | S/17.50 | **S/+15.75** | `+90.0%` |
| **AST** | 16 | 3 | 11 | `21.4%` | S/49.00 | **S/-29.05** | `-59.3%` |
| **PRA** | 16 | 3 | 6 | `33.3%` | S/31.50 | **S/-11.55** | `-36.7%` |
| **3PM** | 36 | 8 | 0 | `100.0%` | S/28.00 | **S/+25.20** | `+90.0%` |
| **SGP** | 29 | 0 | 0 | `0.0%` | S/0.00 | **S/+0.00** | `+0.0%` |

### 📜 Últimas Apuestas de Props Liquidadas (Auditoría Inmutable)

| Fecha | Partido | Jugador / Combinada | Mercado | Selección | Línea | Cuota | Stat Real | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: | :---: | ---: | ---: |
| `2026-11-09` | `ESPN_401909950_2026-11-09_NOP_AT_LAC` | **Jordan Poole** | 3PM | UNDER | `3.5` | `1.90` | `0.0` | ✅ WON | **S/+3.15** | `S/76.20` |
| `2026-11-09` | `ESPN_401909951_2026-11-09_MIA_AT_SAC` | **Zach LaVine** | 3PM | UNDER | `3.5` | `1.90` | `1.0` | ✅ WON | **S/+3.15** | `S/79.35` |
| `2026-11-09` | `ESPN_401909947_2026-11-09_UTA_AT_MIN` | **LaMelo Ball** | PTS | OVER | `28.5` | `1.90` | `24.0` | ❌ LOST | **S/-3.50** | `S/67.45` |
| `2026-11-09` | `ESPN_401909947_2026-11-09_UTA_AT_MIN` | **LaMelo Ball** | PRA | OVER | `41.5` | `1.90` | `32.0` | ❌ LOST | **S/-3.50** | `S/63.95` |
| `2026-11-09` | `ESPN_401909947_2026-11-09_UTA_AT_MIN` | **Keyonte George** | AST | UNDER | `6.5` | `1.90` | `8.0` | ❌ LOST | **S/-3.50** | `S/60.45` |
| `2026-11-09` | `ESPN_401909949_2026-11-09_BOS_AT_MIL` | **Tyler Herro** | 3PM | UNDER | `3.5` | `1.90` | `1.0` | ✅ WON | **S/+3.15** | `S/63.60` |
| `2026-11-09` | `ESPN_401909949_2026-11-09_BOS_AT_MIL` | **Myles Turner** | REB | UNDER | `7.5` | `1.90` | `5.0` | ✅ WON | **S/+3.15** | `S/66.75` |
| `2026-11-09` | `ESPN_401909950_2026-11-09_NOP_AT_LAC` | **Jordan Poole** | 3PM | UNDER | `3.5` | `1.90` | `0.0` | ✅ WON | **S/+3.15** | `S/69.90` |
| `2026-11-09` | `ESPN_401909951_2026-11-09_MIA_AT_SAC` | **Zach LaVine** | 3PM | UNDER | `3.5` | `1.90` | `1.0` | ✅ WON | **S/+3.15** | `S/73.05` |
| `2026-11-09` | `ESPN_401909947_2026-11-09_UTA_AT_MIN` | **Keyonte George** | AST | UNDER | `6.5` | `1.90` | `8.0` | ❌ LOST | **S/-3.50** | `S/58.35` |
| `2026-11-09` | `ESPN_401909949_2026-11-09_BOS_AT_MIL` | **Tyler Herro** | 3PM | UNDER | `3.5` | `1.90` | `1.0` | ✅ WON | **S/+3.15** | `S/61.50` |
| `2026-11-09` | `ESPN_401909949_2026-11-09_BOS_AT_MIL` | **Myles Turner** | REB | UNDER | `7.5` | `1.90` | `5.0` | ✅ WON | **S/+3.15** | `S/64.65` |
| `2026-11-09` | `ESPN_401909950_2026-11-09_NOP_AT_LAC` | **Jordan Poole** | 3PM | UNDER | `3.5` | `1.90` | `0.0` | ✅ WON | **S/+3.15** | `S/67.80` |
| `2026-11-09` | `ESPN_401909951_2026-11-09_MIA_AT_SAC` | **Zach LaVine** | 3PM | UNDER | `3.5` | `1.90` | `1.0` | ✅ WON | **S/+3.15** | `S/70.95` |
| `2026-11-09` | `ESPN_401909947_2026-11-09_UTA_AT_MIN` | **LaMelo Ball** | PTS | OVER | `28.5` | `1.90` | `24.0` | ❌ LOST | **S/-3.50** | `S/65.35` |
