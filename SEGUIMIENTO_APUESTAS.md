# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)

- **Última actualización**: `2026-11-08 20:59 (Hora Perú UTC-5)` (`2026-11-09T01:59:47Z`)
- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/104.29 PEN`** (`+4.29 PEN`)
- **ROI Actual**: `+3.52%` | **Yield Actual**: `+3.52%` | **CLV Promedio**: `+1.17%` | **Max Drawdown**: `0.00%` | **Apuestas en espera**: `3` (`S/5.12 PEN` reservados)
- **Motor Predictivo Activo**: `Modelo F+G (ML LightGBM/Ridge + 10,000 Simulaciones Monte Carlo de Posesiones con Overtime, Fouling y Blowout + Conformal Prediction)`.
- **Modo de Apuesta Activo**: `Kelly-Conviccion Proporcional a la Ventaja (S/1.00 a S/6.00 PEN)` *(Modulado por EV real contra casas sharp, Guardian Activo de CLV que reduce exposicion ante movimientos adversos de linea, y Limite de Anti-Correlacion de 1 apuesta por partido)*.
- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)
- **Sistema de Aviso Automático (Doble Nivel)**: `ACTIVO` *(Recibirás un correo automático vía GitHub Issue `@Drewks` al desbloquear el **Nivel 1: Micro-Banca** y un segundo correo al desbloquear el **Nivel 2: Banca Completa**)*.

---

## 🚦 1. Semáforo de Madurez de 8 Criterios y Graduación en 2 Niveles

### Estado Global: **🔴 EN FASE DE CALIBRACIÓN Y PAPER TRADING (6/8 CRITERIOS EN VERDE — NO USAR DINERO REAL AÚN)**
- **Progreso Muestra Total (Nivel 1)**: `[█████░░░░░░░░░░░░░░░] 122 / 500 apuestas (24.4%)` — *Faltan **378** apuestas.*
- **Progreso Muestra 100% En Vivo (ESPN/OddsAPI)**: `[░░░░░░░░░░░░░░░░░░░░] 0 / 200 en vivo (0.0%)` — *Tienes **3** apuestas reales en espera hoy.*

Para blindar tu capital contra rachas de suerte, el sistema evalúa **8 criterios cuantitativos estrictos** divididos en **2 niveles de graduación**:

| # | Criterio Cuantitativo de Auditoría | Estado Hoy | Valor Actual | Meta Nivel 1 (Piloto Micro-Banca 25%) | Meta Nivel 2 (Banca Completa 100%) |
| :-: | :--- | :---: | :--- | :--- | :--- |
| 1 | **Muestra total de apuestas liquidadas** | 🔴 PENDIENTE | `122 apuestas` | **>= 500 apuestas** | **>= 1,000 apuestas** |
| 2 | **Muestra 100% En Vivo (Pre-Partido Real)** | 🔴 PENDIENTE | `0 liquidadas (3 activas)` | **>= 200 en vivo** | **>= 500 en vivo** |
| 3 | **Calibración mejor que el Baseline (Brier & LogLoss)** | ✅ VERDE | `Brier 0.2437 vs 0.2508` | **Brier/LogLoss <= Base** | **Brier/LogLoss <= Base** |
| 4 | **Error de Calibración por Tramos (ECE)** | ✅ VERDE | `ECE 0.0250 (2.50%)` | **ECE <= 5.0%** | **ECE <= 3.5%** |
| 5 | **Rentabilidad Neta Positiva (ROI y Yield)** | ✅ VERDE | `ROI +3.52% / Yield +3.52%` | **ROI >= +2.0% / Yield >= +1.5%** | **ROI >= +3.5% (ambos mercados > 0%)** |
| 6 | **Control de Caída Máxima (Max Drawdown)** | ✅ VERDE | `Total 0.00% (En vivo: 0.00%)` | **MaxDD <= 15.0%** | **MaxDD <= 15.0%** |
| 7 | **Exclusión Estadística del Azar (Bootstrap CI)** | ✅ VERDE | `IC90 [+2.3%, +4.7%] / IC95 [+0.8%, +6.2%]` | **IC 90% lím. inf. > 0%** | **IC 95% lím. inf. > 0%** |
| 8 | **Cero Fuga Temporal (Anti-Leakage) y SQLite** | ✅ VERDE | `0 violaciones / 100% íntegro` | **0 violaciones** | **0 violaciones** |

> **🔔 Doble aviso automático a tu correo**: No necesitas vigilar esta tabla a diario. Cuando las 8 filas lleguen a **✅ VERDE** en el **Nivel 1**, recibirás un correo de GitHub (`@Drewks`) autorizando pruebas con micro-banca (25% de tu stake). Cuando alcance el **Nivel 2** (`1,000` apuestas + `IC 95% > 0%`), recibirás el segundo correo de certificación completa.

---

## 🏀 2. Mis Apuestas NBA Reales (ESPN / Line Shopping 25 Casas)

> ### 🏆 PICK ESTRELLA DEL DÍA (`2026-11-08` — 1 Solo Pick: Mayor Probabilidad de Acierto)
> - **Partido**: **Miami Heat @ Sacramento Kings (MIA @ SAC)** (`2026-11-08 21:00 Hora Perú`)
> - **Pick Más Probable**: 🎯 **Gana Miami Heat (MIA)** (Ganador (Moneyline)) @ **`1.917`** *(1xBet Perú [T-6H Peru])*
> - **Probabilidad de Acierto (Modelo Calibrado)**: 🔥 **`53.5%`** | **EV**: `+2.6%`
> - **Envío diario a tu correo**: `ACTIVO` *(1 solo correo diario vía GitHub Notification `@Drewks` con la selección de mayor probabilidad de acierto y sin alerta CLV)*.

Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido, con vigilancia de movimiento en contra `CLV < -5.0%`):

| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Mejor Cuota (Casa) | Prob. Modelo | EV (%) | CLV (%) | Stake | Estado | Resultado / Ganancia |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |
| `2026-11-09 20:30` | **Denver Nuggets @ Houston Rockets (DEN @ HOU)** | Ganador (Moneyline) | **Gana Denver Nuggets (DEN)** | **3.370** *(DraftKings)* | 30.8% | `+3.8%` | — | S/1.12 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-08 21:00` | **New Orleans Pelicans @ LA Clippers (NOP @ LAC)** | Ganador (Moneyline) | **Gana LA Clippers (LAC)** | **1.917** *(1xBet Perú [T-6H Peru])* | 54.3% | `+4.0%` | `-8.28%` | S/2.00 | ⚠️ ALERTA CLV | ⚠️ Movimiento brusco en contra (posible baja de última hora) |
| `2026-11-08 21:00` | **Miami Heat @ Sacramento Kings (MIA @ SAC)** | Ganador (Moneyline) | **Gana Miami Heat (MIA)** | **1.917** *(1xBet Perú [T-6H Peru])* | 53.5% | `+2.6%` | `+65.07%` | S/2.00 | ⏳ PENDIENTE | Esperando final del partido |
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

#### 🎯 **New Orleans Pelicans @ LA Clippers (NOP @ LAC)** — `2026-11-08 21:00 Hora Perú`
- **¿Qué está apostando el bot?**: **Gana LA Clippers (LAC - Local)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`1.917`** en *1xBet Perú [T-6H Peru]* vs Cuota Justa del Modelo **`1.842`** *(Ventaja Matemática EV: `+4.03%`)*
- **Stake y Ganancia Potencial**: Stake **`S/2.00 PEN`** → Ganancia neta potencial: **`+S/1.83 PEN`** *(Retorno total: `S/3.83 PEN`)*
- **Probabilidades**: Modelo Calibrado **`54.3%`** vs Probabilidad Implícita Limpia Casa **`48.4%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `LAC +3.2 pts` | Total esperado **`227.4 pts`** *(Rango 80% Conformal: `205 – 250 pts` | Prob. Prórroga: `8.3%` | Prob. Paliza: `10.9%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `LAC 1470` vs `NOP 1431` | **Eficiencia Neta (Off/Def)**: `LAC (111.8/113.2)` vs `NOP (115.0/115.9)` (`Dif: -0.5 pts/100`)
  - **Ritmo (Pace)**: `99.7 posesiones` | **Descanso**: `LAC 4d` vs `NOP 2d` | **Viaje Geodésico (Millas Haversine)**: `Dif. +1674 millas` (`2 husos horarios`)
- **Por qué apostó el modelo**: _Visita (New Orleans Pelicans) viaja +1674 millas más · Eficiencia neta favorable (New Orleans Pelicans [NOP] +0.5 pts/100) · Cuota 1.917 en 1xBet Perú [T-6H Peru] supera la cuota justa del modelo (1.842)._

#### 🎯 **Miami Heat @ Sacramento Kings (MIA @ SAC)** — `2026-11-08 21:00 Hora Perú`
- **¿Qué está apostando el bot?**: **Gana Miami Heat (MIA - Visita)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`1.917`** en *1xBet Perú [T-6H Peru]* vs Cuota Justa del Modelo **`1.869`** *(Ventaja Matemática EV: `+2.62%`)*
- **Stake y Ganancia Potencial**: Stake **`S/2.00 PEN`** → Ganancia neta potencial: **`+S/1.83 PEN`** *(Retorno total: `S/3.83 PEN`)*
- **Probabilidades**: Modelo Calibrado **`53.5%`** vs Probabilidad Implícita Limpia Casa **`74.0%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `SAC -4.2 pts` | Total esperado **`234.9 pts`** *(Rango 80% Conformal: `212 – 259 pts` | Prob. Prórroga: `8.0%` | Prob. Paliza: `11.7%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `SAC 1350` vs `MIA 1472` | **Eficiencia Neta (Off/Def)**: `SAC (111.1/118.6)` vs `MIA (117.1/116.7)` (`Dif: -8.0 pts/100`)
  - **Ritmo (Pace)**: `100.7 posesiones` | **Descanso**: `SAC 2d` vs `MIA 3d` | **Viaje Geodésico (Millas Haversine)**: `Dif. +74 millas` (`0 husos horarios`)
- **Por qué apostó el modelo**: _Eficiencia neta favorable (Miami Heat [MIA] +8.0 pts/100) · Cuota 1.917 en 1xBet Perú [T-6H Peru] supera la cuota justa del modelo (1.869)._

#### 🎯 **Denver Nuggets @ Houston Rockets (DEN @ HOU)** — `2026-11-09 20:30 Hora Perú`
- **¿Qué está apostando el bot?**: **Gana Denver Nuggets (DEN - Visita)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`3.370`** en *DraftKings* vs Cuota Justa del Modelo **`3.247`** *(Ventaja Matemática EV: `+3.80%`)*
- **Stake y Ganancia Potencial**: Stake **`S/1.12 PEN`** → Ganancia neta potencial: **`+S/2.65 PEN`** *(Retorno total: `S/3.77 PEN`)*
- **Probabilidades**: Modelo Calibrado **`30.8%`** vs Probabilidad Implícita Limpia Casa **`28.5%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `HOU +3.4 pts` | Total esperado **`222.5 pts`** *(Rango 80% Conformal: `200 – 245 pts` | Prob. Prórroga: `8.5%` | Prob. Paliza: `10.7%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `HOU 1615` vs `DEN 1562` | **Eficiencia Neta (Off/Def)**: `HOU (113.2/108.7)` vs `DEN (116.0/113.8)` (`Dif: +2.3 pts/100`)
  - **Ritmo (Pace)**: `98.7 posesiones` | **Descanso**: `HOU 2d` vs `DEN 3d` | **Viaje Geodésico (Millas Haversine)**: `Dif. -149 millas` (`1 husos horarios`)
- **Por qué apostó el modelo**: _Ajuste de retorno de gira para Houston Rockets · Eficiencia neta favorable (Houston Rockets [HOU] +2.3 pts/100) · Cuota 3.370 en DraftKings supera la cuota justa del modelo (3.247)._

### 📋 2.B Cartelera Completa de Próximos Partidos: Cuotas, Estadísticas a Tomar en Cuenta y Veredicto

| Hora (Perú) | Partido (`Visita @ Local`) | Cuotas Ganador (`Local / Visita`) | Línea Total (`O/U`) | Proyección Modelo (`Margen / Total`) | Estadísticas Clave (`Elo`, `NetRtg`, `Descanso`, `Viaje`) | ¿Qué Hace el Bot y Por Qué? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `2026-11-08 19:00` | **Utah Jazz @ Minnesota Timberwolves (UTA @ MIN)** | Local **1.957** / Visita **6.040** *(Pinnacle (Perú Sharp) [T-6H Peru])* | **222.5** (`O 1.91` / `U 1.91`) | **MIN -13.7 pts** (Prob Local `88.7%`) · Total **226.8 pts** | Elo `1617/1296` · Net `+10.8` · Pace `98.4` · Desc `2d/2d` · Viaje `-190 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-08 19:30` | **Brooklyn Nets @ Dallas Mavericks (BKN @ DAL)** | Local **1.957** / Visita **3.480** *(Pinnacle (Perú Sharp) [T-6H Peru])* | **223.5** (`O 1.93` / `U 1.89`) | **DAL -7.2 pts** (Prob Local `73.9%`) · Total **220.2 pts** | Elo `1433/1340` · Net `+3.4` · Pace `98.9` · Desc `2d/1d` · Viaje `+720 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-08 20:00` | **Boston Celtics @ Milwaukee Bucks (BOS @ MIL)** | Local **6.510** / Visita **1.957** *(Draft Kings)* | **221.5** (`O 1.94` / `U 1.89`) | **BOS -8.3 pts** (Prob Local `23.8%`) · Total **221.0 pts** | Elo `1356/1619` · Net `-10.2` · Pace `99.2` · Desc `2d/2d` · Viaje `+660 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-08 21:00` | **New Orleans Pelicans @ LA Clippers (NOP @ LAC)** | Local **2.090** / Visita **1.957** *(Draft Kings)* | **226.5** (`O 1.93` / `U 1.94`) | **LAC -3.2 pts** (Prob Local `63.6%`) · Total **227.4 pts** | Elo `1470/1431` · Net `-0.5` · Pace `99.7` · Desc `4d/2d` · Viaje `+1674 mi` | **🎯 APOSTADO: Gana LA Clippers (LAC - Local) @ 1.917 (1xBet Perú [T-6H Peru]) | Stake S/2.00 (EV +4.03%)** — _Visita (New Orleans Pelicans) viaja +1674 millas más · Eficiencia neta favorable (New Orleans Pelicans [NOP] +0.5 pts/100) · Cuota 1.917 en 1xBet Perú [T-6H Peru] supera la cuota justa del modelo (1.842)._ |
| `2026-11-08 21:00` | **Miami Heat @ Sacramento Kings (MIA @ SAC)** | Local **5.580** / Visita **1.957** *(Draft Kings)* | **236.5** (`O 1.94` / `U 1.89`) | **MIA -4.2 pts** (Prob Local `38.7%`) · Total **234.9 pts** | Elo `1350/1472` · Net `-8.0` · Pace `100.7` · Desc `2d/3d` · Viaje `+74 mi` | **🎯 APOSTADO: Gana Miami Heat (MIA - Visita) @ 1.917 (1xBet Perú [T-6H Peru]) | Stake S/2.00 (EV +2.62%)** — _Eficiencia neta favorable (Miami Heat [MIA] +8.0 pts/100) · Cuota 1.917 en 1xBet Perú [T-6H Peru] supera la cuota justa del modelo (1.869)._ |
| `2026-11-09 19:00` | **Los Angeles Lakers @ Atlanta Hawks (LAL @ ATL)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **LAL -1.2 pts** (Prob Local `47.3%`) · Total **229.9 pts** | Elo `1537/1607` · Net `-3.3` · Pace `99.7` · Desc `2d/2d` · Viaje `+598 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-09 19:00` | **Cleveland Cavaliers @ Charlotte Hornets (CLE @ CHA)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **CLE -2.7 pts** (Prob Local `43.4%`) · Total **220.7 pts** | Elo `1465/1564` · Net `-5.9` · Pace `98.3` · Desc `3d/2d` · Viaje `+436 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-09 19:00` | **Washington Wizards @ Detroit Pistons (WAS @ DET)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **DET -14.2 pts** (Prob Local `88.8%`) · Total **220.6 pts** | Elo `1638/1344` · Net `+11.4` · Pace `98.1` · Desc `2d/2d` · Viaje `+909 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-09 19:30` | **Memphis Grizzlies @ Toronto Raptors (MEM @ TOR)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **TOR -4.5 pts** (Prob Local `68.1%`) · Total **227.5 pts** | Elo `1534/1430` · Net `+1.5` · Pace `99.4` · Desc `3d/3d` · Viaje `+386 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-09 20:00` | **Indiana Pacers @ Dallas Mavericks (IND @ DAL)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **DAL -5.4 pts** (Prob Local `68.7%`) · Total **223.3 pts** | Elo `1433/1353` · Net `+3.3` · Pace `98.7` · Desc `3d/3d` · Viaje `+764 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-09 20:30` | **Denver Nuggets @ Houston Rockets (DEN @ HOU)** | Local **1.344** / Visita **3.370** *(Draft Kings)* | **217.5** (`O 1.91` / `U 1.91`) | **HOU -3.4 pts** (Prob Local `62.5%`) · Total **222.5 pts** | Elo `1615/1562` · Net `+2.3` · Pace `98.7` · Desc `2d/3d` · Viaje `-149 mi` | **🎯 APOSTADO: Gana Denver Nuggets (DEN - Visita) @ 3.370 (DraftKings) | Stake S/1.12 (EV +3.80%)** — _Ajuste de retorno de gira para Houston Rockets · Eficiencia neta favorable (Houston Rockets [HOU] +2.3 pts/100) · Cuota 3.370 en DraftKings supera la cuota justa del modelo (3.247)._ |
| `2026-11-09 21:00` | **San Antonio Spurs @ Phoenix Suns (SAS @ PHX)** | Local **3.300** / Visita **1.356** *(Draft Kings)* | **226.5** (`O 1.91` / `U 1.91`) | **SAS -5.8 pts** (Prob Local `30.4%`) · Total **224.8 pts** | Elo `1484/1697` · Net `-7.5` · Pace `99.3` · Desc `2d/2d` · Viaje `+1006 mi` | **🛡️ NO APOSTAR (Pass)** — _Cuotas eficientes: la probabilidad del modelo está alineada con las casas (sin ventaja EV suficiente)._ |
| `2026-11-09 22:00` | **New Orleans Pelicans @ Golden State Warriors (NOP @ GSW)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **GSW -4.9 pts** (Prob Local `67.9%`) · Total **230.1 pts** | Elo `1514/1431` · Net `+2.4` · Pace `100.1` · Desc `2d/3d` · Viaje `+1920 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-10 19:30` | **Milwaukee Bucks @ New York Knicks (MIL @ NYK)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **NYK -13.9 pts** (Prob Local `88.5%`) · Total **219.7 pts** | Elo `1668/1356` · Net `+11.8` · Pace `98.5` · Desc `3d/4d` · Viaje `+329 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-10 20:00` | **Boston Celtics @ Philadelphia 76ers (BOS @ PHI)** | Local **1.917** / Visita **1.917** *(Draft Kings)* | **215.5** (`O 1.94` / `U 1.88`) | **BOS -2.1 pts** (Prob Local `45.3%`) · Total **217.5 pts** | Elo `1553/1619` · Net `-4.5` · Pace `98.3` · Desc `3d/4d` · Viaje `-219 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-10 21:00` | **LA Clippers @ Phoenix Suns (LAC @ PHX)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **PHX -3.3 pts** (Prob Local `60.9%`) · Total **224.8 pts** | Elo `1484/1470` · Net `+2.1` · Pace `99.8` · Desc `3d/6d` · Viaje `+362 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-10 21:00` | **Miami Heat @ Utah Jazz (MIA @ UTA)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **MIA -4.6 pts** (Prob Local `35.2%`) · Total **233.8 pts** | Elo `1296/1472` · Net `-8.5` · Pace `99.7` · Desc `4d/5d` · Viaje `-401 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-10 22:00` | **Orlando Magic @ Sacramento Kings (ORL @ SAC)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **ORL -2.6 pts** (Prob Local `40.8%`) · Total **225.2 pts** | Elo `1350/1479` · Net `-4.2` · Pace `99.5` · Desc `4d/3d` · Viaje `+74 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-10 23:00` | **Oklahoma City Thunder @ Portland Trail Blazers (OKC @ POR)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **OKC -3.8 pts** (Prob Local `38.3%`) · Total **221.8 pts** | Elo `1535/1671` · Net `-6.6` · Pace `99.0` · Desc `3d/3d` · Viaje `+1485 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 19:00` | **Washington Wizards @ Indiana Pacers (WAS @ IND)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **IND -3.3 pts** (Prob Local `60.5%`) · Total **223.1 pts** | Elo `1353/1344` · Net `+2.5` · Pace `98.4` · Desc `5d/4d` · Viaje `+688 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 19:00` | **Cleveland Cavaliers @ New York Knicks (CLE @ NYK)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **NYK -5.7 pts** (Prob Local `70.1%`) · Total **220.6 pts** | Elo `1668/1564` · Net `+4.0` · Pace `98.3` · Desc `4d/4d` · Viaje `+0 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 19:00` | **Boston Celtics @ Toronto Raptors (BOS @ TOR)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **BOS -2.7 pts** (Prob Local `43.2%`) · Total **220.2 pts** | Elo `1534/1619` · Net `-5.6` · Pace `99.2` · Desc `5d/5d` · Viaje `+156 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 20:00` | **San Antonio Spurs @ Chicago Bulls (SAS @ CHI)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **SAS -10.6 pts** (Prob Local `18.3%`) · Total **232.9 pts** | Elo `1364/1697` · Net `-13.3` · Pace `100.0` · Desc `4d/4d` · Viaje `+1752 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 20:00` | **Denver Nuggets @ Memphis Grizzlies (DEN @ MEM)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **DEN -2.8 pts** (Prob Local `40.5%`) · Total **228.8 pts** | Elo `1430/1562` · Net `-4.7` · Pace `98.9` · Desc `5d/5d` · Viaje `+384 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 20:00` | **Los Angeles Lakers @ Milwaukee Bucks (LAL @ MIL)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **LAL -7.6 pts** (Prob Local `25.1%`) · Total **227.5 pts** | Elo `1356/1607` · Net `-8.7` · Pace `99.8` · Desc `5d/4d` · Viaje `+252 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 20:00` | **Brooklyn Nets @ New Orleans Pelicans (BKN @ NOP)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **NOP -5.9 pts** (Prob Local `70.2%`) · Total **224.8 pts** | Elo `1431/1340` · Net `+4.4` · Pace `99.4` · Desc `5d/4d` · Viaje `+425 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 21:00` | **Orlando Magic @ Utah Jazz (ORL @ UTA)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **ORL -3.6 pts** (Prob Local `36.3%`) · Total **224.2 pts** | Elo `1296/1479` · Net `-5.6` · Pace `98.5` · Desc `5d/4d` · Viaje `-401 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 21:30` | **Golden State Warriors @ Houston Rockets (GSW @ HOU)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **HOU -5.5 pts** (Prob Local `69.7%`) · Total **222.2 pts** | Elo `1615/1514` · Net `+3.3` · Pace `99.4` · Desc `4d/4d` · Viaje `+627 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 22:00` | **Oklahoma City Thunder @ Portland Trail Blazers (OKC @ POR)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **OKC -3.9 pts** (Prob Local `38.1%`) · Total **221.8 pts** | Elo `1535/1671` · Net `-6.6` · Pace `99.0` · Desc `4d/4d` · Viaje `+1485 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |

---

## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)

| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |
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
| `BET_20261031_B0C4035D` | `2026-10-31` | `Denver Nuggets @ Phoenix Suns (DEN @ PHX)` | Ganador (Moneyline) | **Gana Phoenix Suns (PHX)** | 2.420 | 56.4% | `+36.4%` | ❌ LOST | **S/-1.00** | `S/101.11` |
| `BET_20261031_90A3CA7F` | `2026-10-31` | `Denver Nuggets @ Phoenix Suns (DEN @ PHX)` | Total Puntos (Over/Under) | **UNDER 230.5 (Denver Nuggets @ Phoenix Suns)** | 1.909 | 66.3% | `+26.6%` | ❌ LOST | **S/-1.00** | `S/101.71` |

---

## 🎯 4. Seguimiento Oficial de Paper Trading — Player Props & SGP RETAbet V8

- **Banca Virtual de Props**: `S/100.00 PEN` (Inicial) → **`S/86.35 PEN`** (`-13.65 PEN`)
- **Tasa de Acierto (Win Rate)**: **`42.9%`** (`9G - 12P - 0E`)
- **ROI Acumulado en Props**: **`-18.57%`** | **Total Apostado**: `S/73.50 PEN`
- **Brier Score (Calibración)**: `0.2766` | **Cobertura Conformal**: `42.9%`
- **Total de Picks Registrados**: `254` (`160` en espera / `94` liquidados)

### 📊 Desglose de Rendimiento por Categoría de Prop

| Categoría | Liquidadas | Ganadas | Perdidas | Acierto (%) | Total Apostado (S/) | Beneficio Neto (S/) | ROI (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **PTS** | 8 | 0 | 4 | `0.0%` | S/14.00 | **S/-14.00** | `-100.0%` |
| **REB** | 6 | 3 | 0 | `100.0%` | S/10.50 | **S/+9.45** | `+90.0%` |
| **AST** | 9 | 3 | 4 | `42.9%` | S/24.50 | **S/-4.55** | `-18.6%` |
| **PRA** | 14 | 3 | 4 | `42.9%` | S/24.50 | **S/-4.55** | `-18.6%` |
| **3PM** | 28 | 0 | 0 | `0.0%` | S/0.00 | **S/+0.00** | `+0.0%` |
| **SGP** | 29 | 0 | 0 | `0.0%` | S/0.00 | **S/+0.00** | `+0.0%` |

### 📜 Últimas Apuestas de Props Liquidadas (Auditoría Inmutable)

| Fecha | Partido | Jugador / Combinada | Mercado | Selección | Línea | Cuota | Stat Real | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: | :---: | ---: | ---: |
| `2026-11-08` | `ESPN_401909941_2026-11-08_WAS_AT_OKC` | **Shai Gilgeous-Alexander** | PTS | OVER | `30.5` | `1.90` | `0.0` | VOID | **S/+0.00** | `S/87.40` |
| `2026-11-08` | `ESPN_401909941_2026-11-08_WAS_AT_OKC` | **Shai Gilgeous-Alexander** | PRA | OVER | `42.5` | `1.90` | `0.0` | VOID | **S/+0.00** | `S/87.40` |
| `2026-11-08` | `ESPN_401909941_2026-11-08_WAS_AT_OKC` | **Jalen Williams** | PRA | OVER | `28.5` | `1.90` | `0.0` | VOID | **S/+0.00** | `S/87.40` |
| `2026-11-08` | `ESPN_401909941_2026-11-08_WAS_AT_OKC` | **Jordan Poole** | 3PM | UNDER | `3.5` | `1.90` | `0.0` | VOID | **S/+0.00** | `S/87.40` |
| `2026-11-08` | `ESPN_401909942_2026-11-08_ORL_AT_GSW` | **Stephen Curry** | PTS | UNDER | `27.5` | `1.90` | `41.0` | ❌ LOST | **S/-3.50** | `S/83.90` |
| `2026-11-08` | `ESPN_401909942_2026-11-08_ORL_AT_GSW` | **Stephen Curry** | PRA | UNDER | `37.5` | `1.90` | `53.0` | ❌ LOST | **S/-3.50** | `S/80.40` |
| `2026-11-08` | `ESPN_401909942_2026-11-08_ORL_AT_GSW` | **Draymond Green** | AST | UNDER | `6.5` | `1.90` | `13.0` | ❌ LOST | **S/-3.50** | `S/76.90` |
| `2026-11-08` | `ESPN_401909942_2026-11-08_ORL_AT_GSW` | **Draymond Green** | REB | UNDER | `7.5` | `1.90` | `6.0` | ✅ WON | **S/+3.15** | `S/80.05` |
| `2026-11-08` | `ESPN_401909942_2026-11-08_ORL_AT_GSW` | **Draymond Green** | PRA | UNDER | `22.5` | `1.90` | `21.0` | ✅ WON | **S/+3.15** | `S/83.20` |
| `2026-11-08` | `ESPN_401909942_2026-11-08_ORL_AT_GSW` | **Buddy Hield** | 3PM | UNDER | `3.5` | `1.90` | `0.0` | VOID | **S/+0.00** | `S/83.20` |
| `2026-11-08` | `ESPN_401909942_2026-11-08_ORL_AT_GSW` | **Jalen Suggs** | 3PM | UNDER | `2.5` | `1.90` | `0.0` | VOID | **S/+0.00** | `S/83.20` |
| `2026-11-08` | `ESPN_401909943_2026-11-08_HOU_AT_PHX` | **Devin Booker** | AST | UNDER | `7.5` | `1.90` | `3.0` | ✅ WON | **S/+3.15** | `S/86.35` |
| `2026-11-08` | `ESPN_401909943_2026-11-08_HOU_AT_PHX` | **Jusuf Nurkic** | REB | UNDER | `10.5` | `1.90` | `0.0` | VOID | **S/+0.00** | `S/86.35` |
| `2026-11-08` | `ESPN_401909944_2026-11-08_SAS_AT_POR` | **Anfernee Simons** | 3PM | UNDER | `3.5` | `1.90` | `0.0` | VOID | **S/+0.00** | `S/86.35` |
| `2026-11-08` | `ESPN_401909945_2026-11-08_PHI_AT_CHI` | **Zach LaVine** | 3PM | UNDER | `3.5` | `1.90` | `0.0` | VOID | **S/+0.00** | `S/86.35` |
