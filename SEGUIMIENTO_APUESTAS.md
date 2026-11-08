# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)

- **Última actualización**: `2026-11-08 01:41 (Hora Perú UTC-5)` (`2026-11-08T06:41:06Z`)
- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/104.29 PEN`** (`+4.29 PEN`)
- **ROI Actual**: `+3.52%` | **Yield Actual**: `+3.52%` | **CLV Promedio**: `+1.17%` | **Max Drawdown**: `0.00%` | **Apuestas en espera**: `3` (`S/9.34 PEN` reservados)
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

> ### 🏆 PICK ESTRELLA DEL DÍA (`2026-11-07` — 1 Solo Pick: Mayor Probabilidad de Acierto)
> - **Partido**: **Orlando Magic @ Golden State Warriors (ORL @ GSW)** (`2026-11-07 20:30 Hora Perú`)
> - **Pick Más Probable**: 🎯 **Gana Golden State Warriors (GSW)** (Ganador (Moneyline)) @ **`1.938`** *(1xBet Perú [T-6H Peru])*
> - **Probabilidad de Acierto (Modelo Calibrado)**: 🔥 **`54.5%`** | **EV**: `+5.6%`
> - **Envío diario a tu correo**: `ACTIVO` *(1 solo correo diario vía GitHub Notification `@Drewks` con la selección de mayor probabilidad de acierto y sin alerta CLV)*.

Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido, con vigilancia de movimiento en contra `CLV < -5.0%`):

| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Mejor Cuota (Casa) | Prob. Modelo | EV (%) | CLV (%) | Stake | Estado | Resultado / Ganancia |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |
| `2026-11-08 21:00` | **New Orleans Pelicans @ LA Clippers (NOP @ LAC)** | Ganador (Moneyline) | **Gana LA Clippers (LAC)** | **1.917** *(1xBet Perú [T-6H Peru])* | 54.3% | `+4.0%` | — | S/2.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-08 21:00` | **Miami Heat @ Sacramento Kings (MIA @ SAC)** | Ganador (Moneyline) | **Gana Miami Heat (MIA)** | **1.917** *(1xBet Perú [T-6H Peru])* | 53.5% | `+2.6%` | — | S/2.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-07 22:00` | **San Antonio Spurs @ Portland Trail Blazers (SAS @ POR)** | Total Puntos (Over/Under) | **UNDER 228.5 (San Antonio Spurs @ Portland Trail Blazers)** | **1.909** *(DraftKings)* | 53.5% | `+2.2%` | — | S/1.34 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-07 21:00` | **Houston Rockets @ Phoenix Suns (HOU @ PHX)** | Ganador (Moneyline) | **Gana Houston Rockets (HOU)** | **1.938** *(1xBet Perú [T-6H Peru])* | 54.0% | `+4.7%` | `+43.45%` | S/2.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-07 20:30` | **Orlando Magic @ Golden State Warriors (ORL @ GSW)** | Ganador (Moneyline) | **Gana Golden State Warriors (GSW)** | **1.938** *(1xBet Perú [T-6H Peru])* | 54.5% | `+5.6%` | `+46.26%` | S/2.00 | ⏳ PENDIENTE | Esperando final del partido |
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

#### 🎯 **Orlando Magic @ Golden State Warriors (ORL @ GSW)** — `2026-11-07 20:30 Hora Perú`
- **¿Qué está apostando el bot?**: **Gana Golden State Warriors (GSW - Local)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`1.938`** en *1xBet Perú [T-6H Peru]* vs Cuota Justa del Modelo **`1.835`** *(Ventaja Matemática EV: `+5.61%`)*
- **Stake y Ganancia Potencial**: Stake **`S/2.00 PEN`** → Ganancia neta potencial: **`+S/1.88 PEN`** *(Retorno total: `S/3.88 PEN`)*
- **Probabilidades**: Modelo Calibrado **`54.5%`** vs Probabilidad Implícita Limpia Casa **`63.6%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `GSW +3.9 pts` | Total esperado **`221.8 pts`** *(Rango 80% Conformal: `199 – 245 pts` | Prob. Prórroga: `9.0%` | Prob. Paliza: `11.1%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `GSW 1507` vs `ORL 1486` | **Eficiencia Neta (Off/Def)**: `GSW (114.1/113.2)` vs `ORL (111.0/112.3)` (`Dif: +2.1 pts/100`)
  - **Ritmo (Pace)**: `99.4 posesiones` | **Descanso**: `GSW 2d` vs `ORL 2d` | **Viaje Geodésico (Millas Haversine)**: `Dif. +651 millas` (`1 husos horarios`)
- **Por qué apostó el modelo**: _Visita (Orlando Magic) viaja +651 millas más · Eficiencia neta favorable (Golden State Warriors [GSW] +2.1 pts/100) · Cuota 1.938 en 1xBet Perú [T-6H Peru] supera la cuota justa del modelo (1.835)._

#### 🎯 **Houston Rockets @ Phoenix Suns (HOU @ PHX)** — `2026-11-07 21:00 Hora Perú`
- **¿Qué está apostando el bot?**: **Gana Houston Rockets (HOU - Visita)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`1.938`** en *1xBet Perú [T-6H Peru]* vs Cuota Justa del Modelo **`1.852`** *(Ventaja Matemática EV: `+4.65%`)*
- **Stake y Ganancia Potencial**: Stake **`S/2.00 PEN`** → Ganancia neta potencial: **`+S/1.88 PEN`** *(Retorno total: `S/3.88 PEN`)*
- **Probabilidades**: Modelo Calibrado **`54.0%`** vs Probabilidad Implícita Limpia Casa **`64.1%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `PHX -4.0 pts` | Total esperado **`224.7 pts`** *(Rango 80% Conformal: `202 – 248 pts` | Prob. Prórroga: `8.6%` | Prob. Paliza: `11.3%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `PHX 1477` vs `HOU 1622` | **Eficiencia Neta (Off/Def)**: `PHX (113.3/113.6)` vs `HOU (113.4/109.2)` (`Dif: -4.5 pts/100`)
  - **Ritmo (Pace)**: `99.9 posesiones` | **Descanso**: `PHX 2d` vs `HOU 3d` | **Viaje Geodésico (Millas Haversine)**: `Dif. +1015 millas` (`1 husos horarios`)
- **Por qué apostó el modelo**: _Visita (Houston Rockets) viaja +1015 millas más · Eficiencia neta favorable (Houston Rockets [HOU] +4.5 pts/100) · Cuota 1.938 en 1xBet Perú [T-6H Peru] supera la cuota justa del modelo (1.852)._

#### 🎯 **San Antonio Spurs @ Portland Trail Blazers (SAS @ POR)** — `2026-11-07 22:00 Hora Perú`
- **¿Qué está apostando el bot?**: **UNDER 228.5 (San Antonio Spurs @ Portland Trail Blazers)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`1.909`** en *DraftKings* vs Cuota Justa del Modelo **`1.869`** *(Ventaja Matemática EV: `+2.17%`)*
- **Stake y Ganancia Potencial**: Stake **`S/1.34 PEN`** → Ganancia neta potencial: **`+S/1.22 PEN`** *(Retorno total: `S/2.56 PEN`)*
- **Probabilidades**: Modelo Calibrado **`53.5%`** vs Probabilidad Implícita Limpia Casa **`59.2%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `POR -3.2 pts` | Total esperado **`222.8 pts`** *(Rango 80% Conformal: `201 – 245 pts` | Prob. Prórroga: `8.5%` | Prob. Paliza: `10.3%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `POR 1548` vs `SAS 1684` | **Eficiencia Neta (Off/Def)**: `POR (114.4/112.7)` vs `SAS (115.5/109.2)` (`Dif: -4.7 pts/100`)
  - **Ritmo (Pace)**: `99.0 posesiones` | **Descanso**: `POR 1d` vs `SAS 1d` | **Viaje Geodésico (Millas Haversine)**: `Dif. -343 millas` (`0 husos horarios`)
- **Por qué apostó el modelo**: _Ajuste de retorno de gira para Portland Trail Blazers · Eficiencia neta favorable (San Antonio Spurs [SAS] +4.7 pts/100) · Cuota 1.909 en DraftKings supera la cuota justa del modelo (1.869)._

#### 🎯 **New Orleans Pelicans @ LA Clippers (NOP @ LAC)** — `2026-11-08 21:00 Hora Perú`
- **¿Qué está apostando el bot?**: **Gana LA Clippers (LAC - Local)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`1.917`** en *1xBet Perú [T-6H Peru]* vs Cuota Justa del Modelo **`1.842`** *(Ventaja Matemática EV: `+4.03%`)*
- **Stake y Ganancia Potencial**: Stake **`S/2.00 PEN`** → Ganancia neta potencial: **`+S/1.83 PEN`** *(Retorno total: `S/3.83 PEN`)*
- **Probabilidades**: Modelo Calibrado **`54.3%`** vs Probabilidad Implícita Limpia Casa **`49.5%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `LAC +3.2 pts` | Total esperado **`227.1 pts`** *(Rango 80% Conformal: `205 – 250 pts` | Prob. Prórroga: `8.3%` | Prob. Paliza: `10.9%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `LAC 1470` vs `NOP 1431` | **Eficiencia Neta (Off/Def)**: `LAC (111.8/113.2)` vs `NOP (115.0/115.9)` (`Dif: -0.5 pts/100`)
  - **Ritmo (Pace)**: `99.7 posesiones` | **Descanso**: `LAC 4d` vs `NOP 2d` | **Viaje Geodésico (Millas Haversine)**: `Dif. +1674 millas` (`2 husos horarios`)
- **Por qué apostó el modelo**: _Visita (New Orleans Pelicans) viaja +1674 millas más · Eficiencia neta favorable (New Orleans Pelicans [NOP] +0.5 pts/100) · Cuota 1.917 en 1xBet Perú [T-6H Peru] supera la cuota justa del modelo (1.842)._

#### 🎯 **Miami Heat @ Sacramento Kings (MIA @ SAC)** — `2026-11-08 21:00 Hora Perú`
- **¿Qué está apostando el bot?**: **Gana Miami Heat (MIA - Visita)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`1.917`** en *1xBet Perú [T-6H Peru]* vs Cuota Justa del Modelo **`1.869`** *(Ventaja Matemática EV: `+2.62%`)*
- **Stake y Ganancia Potencial**: Stake **`S/2.00 PEN`** → Ganancia neta potencial: **`+S/1.83 PEN`** *(Retorno total: `S/3.83 PEN`)*
- **Probabilidades**: Modelo Calibrado **`53.5%`** vs Probabilidad Implícita Limpia Casa **`65.5%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `SAC -3.7 pts` | Total esperado **`234.6 pts`** *(Rango 80% Conformal: `212 – 258 pts` | Prob. Prórroga: `8.1%` | Prob. Paliza: `11.6%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `SAC 1350` vs `MIA 1472` | **Eficiencia Neta (Off/Def)**: `SAC (111.3/118.4)` vs `MIA (116.9/116.9)` (`Dif: -7.0 pts/100`)
  - **Ritmo (Pace)**: `100.7 posesiones` | **Descanso**: `SAC 2d` vs `MIA 3d` | **Viaje Geodésico (Millas Haversine)**: `Dif. +74 millas` (`0 husos horarios`)
- **Por qué apostó el modelo**: _Eficiencia neta favorable (Miami Heat [MIA] +7.0 pts/100) · Cuota 1.917 en 1xBet Perú [T-6H Peru] supera la cuota justa del modelo (1.869)._

### 📋 2.B Cartelera Completa de Próximos Partidos: Cuotas, Estadísticas a Tomar en Cuenta y Veredicto

| Hora (Perú) | Partido (`Visita @ Local`) | Cuotas Ganador (`Local / Visita`) | Línea Total (`O/U`) | Proyección Modelo (`Margen / Total`) | Estadísticas Clave (`Elo`, `NetRtg`, `Descanso`, `Viaje`) | ¿Qué Hace el Bot y Por Qué? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `2026-11-07 17:00` | **Denver Nuggets @ Indiana Pacers (DEN @ IND)** | Local **3.852** / Visita **1.957** *(RETAbet Perú [T-6H Peru])* | **229.5** (`O 1.94` / `U 1.95`) | **DEN -5.6 pts** (Prob Local `30.8%`) · Total **225.9 pts** | Elo `1360/1556` · Net `-6.7` · Pace `98.8` · Desc `2d/2d` · Viaje `+615 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-07 19:30` | **Brooklyn Nets @ Atlanta Hawks (BKN @ ATL)** | Local **1.957** / Visita **3.417** *(Pinnacle (Perú Sharp) [T-6H Peru])* | **227.5** (`O 1.95` / `U 1.94`) | **ATL -7.0 pts** (Prob Local `75.5%`) · Total **222.5 pts** | Elo `1535/1342` · Net `+6.0` · Pace `99.0` · Desc `1d/3d` · Viaje `+746 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-07 20:00` | **New York Knicks @ Cleveland Cavaliers (NYK @ CLE)** | Local **2.790** / Visita **1.957** *(Draft Kings)* | **225.5** (`O 1.94` / `U 1.95`) | **NYK -2.8 pts** (Prob Local `40.6%`) · Total **221.3 pts** | Elo `1573/1659` · Net `-2.5` · Pace `98.5` · Desc `1d/3d` · Viaje `+404 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-07 20:00` | **Washington Wizards @ Oklahoma City Thunder (WAS @ OKC)** | Local **1.957** / Visita **5.560** *(Pinnacle (Perú Sharp) [T-6H Peru])* | **220.5** (`O 1.95` / `U 1.96`) | **OKC -14.4 pts** (Prob Local `89.4%`) · Total **222.5 pts** | Elo `1668/1347` · Net `+11.9` · Pace `98.8` · Desc `1d/1d` · Viaje `+333 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-07 20:30` | **Orlando Magic @ Golden State Warriors (ORL @ GSW)** | Local **1.957** / Visita **3.420** *(Pinnacle (Perú Sharp) [T-6H Peru])* | **222.5** (`O 1.91` / `U 1.94`) | **GSW -3.9 pts** (Prob Local `62.8%`) · Total **221.8 pts** | Elo `1507/1486` · Net `+2.1` · Pace `99.4` · Desc `2d/2d` · Viaje `+651 mi` | **🎯 APOSTADO: Gana Golden State Warriors (GSW - Local) @ 1.938 (1xBet Perú [T-6H Peru]) | Stake S/2.00 (EV +5.61%)** — _Visita (Orlando Magic) viaja +651 millas más · Eficiencia neta favorable (Golden State Warriors [GSW] +2.1 pts/100) · Cuota 1.938 en 1xBet Perú [T-6H Peru] supera la cuota justa del modelo (1.835)._ |
| `2026-11-07 21:00` | **Houston Rockets @ Phoenix Suns (HOU @ PHX)** | Local **3.490** / Visita **1.957** *(Draft Kings)* | **224.5** (`O 1.95` / `U 1.94`) | **HOU -4.0 pts** (Prob Local `36.1%`) · Total **224.7 pts** | Elo `1477/1622` · Net `-4.5` · Pace `99.9` · Desc `2d/3d` · Viaje `+1015 mi` | **🎯 APOSTADO: Gana Houston Rockets (HOU - Visita) @ 1.938 (1xBet Perú [T-6H Peru]) | Stake S/2.00 (EV +4.65%)** — _Visita (Houston Rockets) viaja +1015 millas más · Eficiencia neta favorable (Houston Rockets [HOU] +4.5 pts/100) · Cuota 1.938 en 1xBet Perú [T-6H Peru] supera la cuota justa del modelo (1.852)._ |
| `2026-11-07 22:00` | **San Antonio Spurs @ Portland Trail Blazers (SAS @ POR)** | Local **2.834** / Visita **1.957** *(RETAbet Perú [T-6H Peru])* | **226.5** (`O 1.94` / `U 1.95`) | **SAS -3.2 pts** (Prob Local `38.7%`) · Total **222.8 pts** | Elo `1548/1684` · Net `-4.7` · Pace `99.0` · Desc `1d/1d` · Viaje `-343 mi` | **🎯 APOSTADO: UNDER 228.5 (San Antonio Spurs @ Portland Trail Blazers) @ 1.909 (DraftKings) | Stake S/1.34 (EV +2.17%)** — _Ajuste de retorno de gira para Portland Trail Blazers · Eficiencia neta favorable (San Antonio Spurs [SAS] +4.7 pts/100) · Cuota 1.909 en DraftKings supera la cuota justa del modelo (1.869)._ |
| `2026-11-08 15:30` | **Philadelphia 76ers @ Chicago Bulls (PHI @ CHI)** | Local **4.120** / Visita **1.315** *(DraftKings)* | **238.5** (`O 1.94` / `U 1.91`) | **PHI -3.7 pts** (Prob Local `38.5%`) · Total **229.4 pts** | Elo `1370/1547` · Net `-8.1` · Pace `99.4` · Desc `3d/1d` · Viaje `-404 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-08 18:00` | **Los Angeles Lakers @ Detroit Pistons (LAL @ DET)** | Local **1.758** / Visita **2.550** *(Draft Kings)* | **222.5** (`O 1.94` / `U 1.91`) | **DET -6.3 pts** (Prob Local `71.1%`) · Total **220.1 pts** | Elo `1647/1597` · Net `+1.8` · Pace `98.7` · Desc `3d/1d` · Viaje `+1980 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-08 19:00` | **Utah Jazz @ Minnesota Timberwolves (UTA @ MIN)** | Local **1.957** / Visita **5.430** *(Pinnacle (Perú Sharp) [T-6H Peru])* | **223.5** (`O 1.94` / `U 1.89`) | **MIN -14.6 pts** (Prob Local `89.4%`) · Total **226.8 pts** | Elo `1617/1296` · Net `+12.9` · Pace `98.4` · Desc `2d/2d` · Viaje `-190 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-08 19:30` | **Brooklyn Nets @ Dallas Mavericks (BKN @ DAL)** | Local **1.957** / Visita **4.200** *(Pinnacle (Perú Sharp) [T-6H Peru])* | **219.5** (`O 1.91` / `U 1.91`) | **DAL -5.8 pts** (Prob Local `69.4%`) · Total **220.0 pts** | Elo `1433/1342` · Net `+5.1` · Pace `98.8` · Desc `2d/4d` · Viaje `+1372 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-08 20:00` | **Boston Celtics @ Milwaukee Bucks (BOS @ MIL)** | Local **5.730** / Visita **1.957** *(DraftKings)* | **222.5** (`O 1.91` / `U 1.91`) | **BOS -9.1 pts** (Prob Local `22.8%`) · Total **220.8 pts** | Elo `1356/1619` · Net `-12.2` · Pace `99.2` · Desc `2d/2d` · Viaje `+660 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-08 21:00` | **New Orleans Pelicans @ LA Clippers (NOP @ LAC)** | Local **2.000** / Visita **1.957** *(DraftKings)* | **230.5** (`O 1.91` / `U 1.93`) | **LAC -3.2 pts** (Prob Local `63.6%`) · Total **227.1 pts** | Elo `1470/1431` · Net `-0.5` · Pace `99.7` · Desc `4d/2d` · Viaje `+1674 mi` | **🎯 APOSTADO: Gana LA Clippers (LAC - Local) @ 1.917 (1xBet Perú [T-6H Peru]) | Stake S/2.00 (EV +4.03%)** — _Visita (New Orleans Pelicans) viaja +1674 millas más · Eficiencia neta favorable (New Orleans Pelicans [NOP] +0.5 pts/100) · Cuota 1.917 en 1xBet Perú [T-6H Peru] supera la cuota justa del modelo (1.842)._ |
| `2026-11-08 21:00` | **Miami Heat @ Sacramento Kings (MIA @ SAC)** | Local **3.710** / Visita **1.957** *(DraftKings)* | **238.5** (`O 1.94` / `U 1.94`) | **MIA -3.7 pts** (Prob Local `39.4%`) · Total **234.6 pts** | Elo `1350/1472` · Net `-7.0` · Pace `100.7` · Desc `2d/3d` · Viaje `+74 mi` | **🎯 APOSTADO: Gana Miami Heat (MIA - Visita) @ 1.917 (1xBet Perú [T-6H Peru]) | Stake S/2.00 (EV +2.62%)** — _Eficiencia neta favorable (Miami Heat [MIA] +7.0 pts/100) · Cuota 1.917 en 1xBet Perú [T-6H Peru] supera la cuota justa del modelo (1.869)._ |
| `2026-11-09 19:00` | **Los Angeles Lakers @ Atlanta Hawks (LAL @ ATL)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **LAL -1.0 pts** (Prob Local `48.3%`) · Total **228.7 pts** | Elo `1535/1597` · Net `-3.9` · Pace `99.5` · Desc `3d/3d` · Viaje `+1934 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-09 19:00` | **Cleveland Cavaliers @ Charlotte Hornets (CLE @ CHA)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **CLE -4.0 pts** (Prob Local `39.3%`) · Total **221.2 pts** | Elo `1465/1573` · Net `-6.8` · Pace `98.5` · Desc `3d/3d` · Viaje `+436 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-09 19:00` | **Washington Wizards @ Detroit Pistons (WAS @ DET)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **DET -13.5 pts** (Prob Local `88.0%`) · Total **221.8 pts** | Elo `1647/1347` · Net `+11.3` · Pace `98.3` · Desc `5d/3d` · Viaje `+598 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-09 19:30` | **Memphis Grizzlies @ Toronto Raptors (MEM @ TOR)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **TOR -4.5 pts** (Prob Local `68.1%`) · Total **227.2 pts** | Elo `1534/1430` · Net `+1.5` · Pace `99.4` · Desc `3d/3d` · Viaje `+386 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-09 20:00` | **Indiana Pacers @ Dallas Mavericks (IND @ DAL)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **DAL -5.1 pts** (Prob Local `67.9%`) · Total **223.7 pts** | Elo `1433/1360` · Net `+3.0` · Pace `98.8` · Desc `3d/5d` · Viaje `+420 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-09 20:30` | **Denver Nuggets @ Houston Rockets (DEN @ HOU)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **HOU -4.3 pts** (Prob Local `66.2%`) · Total **224.4 pts** | Elo `1622/1556` · Net `+1.5` · Pace `99.0` · Desc `5d/5d` · Viaje `+880 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-09 21:00` | **San Antonio Spurs @ Phoenix Suns (SAS @ PHX)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **SAS -5.2 pts** (Prob Local `31.3%`) · Total **225.6 pts** | Elo `1477/1684` · Net `-6.0` · Pace `99.5` · Desc `4d/3d` · Viaje `+635 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-09 22:00` | **New Orleans Pelicans @ Golden State Warriors (NOP @ GSW)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **GSW -5.2 pts** (Prob Local `68.7%`) · Total **229.3 pts** | Elo `1507/1431` · Net `+2.3` · Pace `100.0` · Desc `4d/3d` · Viaje `+1920 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |

---

## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)

| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |
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
| `BET_20261031_BAB6D884` | `2026-10-31` | `Houston Rockets @ Dallas Mavericks (HOU @ DAL)` | Ganador (Moneyline) | **Gana Dallas Mavericks (DAL)** | 2.600 | 49.9% | `+29.8%` | ✅ WON | **S/+1.60** | `S/102.71` |
| `BET_20261030_A239BFAF` | `2026-10-30` | `Memphis Grizzlies @ Portland Trail Blazers (MEM @ POR)` | Total Puntos (Over/Under) | **UNDER 232.5 (Memphis Grizzlies @ Portland Trail Blazers)** | 1.910 | 63.5% | `+21.2%` | ✅ WON | **S/+0.91** | `S/105.14` |
| `BET_20261030_26E1FE60` | `2026-10-30` | `Sacramento Kings @ New Orleans Pelicans (SAC @ NOP)` | Total Puntos (Over/Under) | **UNDER 237.5 (Sacramento Kings @ New Orleans Pelicans)** | 1.950 | 66.9% | `+30.4%` | ❌ LOST | **S/-1.00** | `S/103.72` |

---

## 🎯 4. Seguimiento Oficial de Paper Trading — Player Props & SGP RETAbet V8

- **Banca Virtual de Props**: `S/100.00 PEN` (Inicial) → **`S/100.00 PEN`** (`+0.00 PEN`)
- **Tasa de Acierto (Win Rate)**: **`0.0%`** (`0G - 0P - 0E`)
- **ROI Acumulado en Props**: **`+0.00%`** | **Total Apostado**: `S/0.00 PEN`
- **Brier Score (Calibración)**: `0.0000` | **Cobertura Conformal**: `100.0%`
- **Total de Picks Registrados**: `168` (`168` en espera / `0` liquidados)

### 📊 Desglose de Rendimiento por Categoría de Prop

| Categoría | Liquidadas | Ganadas | Perdidas | Acierto (%) | Total Apostado (S/) | Beneficio Neto (S/) | ROI (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
