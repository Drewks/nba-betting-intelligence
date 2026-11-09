# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)

- **Última actualización**: `2026-11-09 18:48 (Hora Perú UTC-5)` (`2026-11-09T23:48:10Z`)
- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/100.09 PEN`** (`+0.09 PEN`)
- **ROI Actual**: `+0.28%` | **Yield Actual**: `+0.23%` | **CLV (vs cierre sin margen)**: `-2.17%` (N=13) | **Max Drawdown**: `7.56%` | **Apuestas en espera**: `3` (`S/6.62 PEN` reservados)
- **Motor Predictivo Activo**: `Ensemble (Elo + Ridge + LightGBM + Monte Carlo) anclado 70% al mercado sin margen`. Sin ventaja demostrada frente al mercado.
- **Modo de Apuesta Activo**: `Stake fijo S/1.00 PEN (AGENTS.md v1)` | Máx. 3 selecciones/jornada | EV > 5% | Solo cuotas observadas (nunca estimadas).
- **Alcance de métricas**: solo apuestas hechas con cuotas observadas en un mercado real (`v_observed_simulated_bets`).
- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)
- **Sistema de Aviso Automático**: `ACTIVO` *(aviso cuando se cumplan los criterios; cumplirlos solo habilita una revisión humana extendida, nunca dinero real automático)*.

---

## 🚦 1. Semáforo de Madurez de 8 Criterios y Graduación en 2 Niveles

### Estado Global: **🔴 EN FASE DE CALIBRACIÓN Y PAPER TRADING (2/8 CRITERIOS EN VERDE — NO USAR DINERO REAL AÚN)**
- **Progreso Muestra Total (Nivel 1)**: `[█░░░░░░░░░░░░░░░░░░░] 25 / 500 apuestas (5.0%)` — *Faltan **475** apuestas.*
- **Progreso Muestra 100% En Vivo (ESPN/OddsAPI)**: `[██░░░░░░░░░░░░░░░░░░] 25 / 200 en vivo (12.5%)` — *Tienes **3** apuestas reales en espera hoy.*

Para blindar tu capital contra rachas de suerte, el sistema evalúa **8 criterios cuantitativos estrictos** divididos en **2 niveles de graduación**:

| # | Criterio Cuantitativo de Auditoría | Estado Hoy | Valor Actual | Meta Nivel 1 (Piloto Micro-Banca 25%) | Meta Nivel 2 (Banca Completa 100%) |
| :-: | :--- | :---: | :--- | :--- | :--- |
| 1 | **Muestra total de apuestas liquidadas** | 🔴 PENDIENTE | `25 apuestas` | **>= 500 apuestas** | **>= 1,000 apuestas** |
| 2 | **Muestra 100% En Vivo (Pre-Partido Real)** | 🔴 PENDIENTE | `25 liquidadas (3 activas)` | **>= 200 en vivo** | **>= 500 en vivo** |
| 3 | **No peor que el Mercado sin margen ni que el Baseline (Brier & LogLoss)** | 🔴 PENDIENTE | `Modelo 0.2169 vs Mercado 0.2138 (N=77) | Baseline 0.2525` | **Modelo <= Mercado** | **Modelo <= Mercado** |
| 4 | **Error de Calibración por Tramos (ECE)** | 🟡 AJUSTANDO | `ECE 0.1380 (13.80%)` | **ECE <= 5.0%** | **ECE <= 3.5%** |
| 5 | **Rentabilidad Neta Positiva (ROI y Yield)** | 🔴 PENDIENTE | `ROI +0.28% / Yield +0.23%` | **ROI >= +2.0% / Yield >= +1.5%** | **ROI >= +3.5% (ambos mercados > 0%)** |
| 6 | **Control de Caída Máxima (Max Drawdown)** | ✅ VERDE | `Total 7.56% (En vivo: 7.56%)` | **MaxDD <= 15.0%** | **MaxDD <= 15.0%** |
| 7 | **Exclusión Estadística del Azar (Bootstrap CI)** | 🔴 PENDIENTE | `IC90 [-27.5%, +27.6%] / IC95 [-33.0%, +32.1%]` | **IC 90% lím. inf. > 0%** | **IC 95% lím. inf. > 0%** |
| 8 | **Cero Fuga Temporal, historial íntegro y ledger reconciliado** | ✅ VERDE | `Sin violaciones` | **0 violaciones** | **0 violaciones** |

> **Nota**: cumplir los criterios NO autoriza dinero real. Según AGENTS.md, el sistema opera exclusivamente en paper trading; los niveles solo habilitan una revisión humana extendida.

---

## 🏀 2. Mis Apuestas NBA Reales (ESPN / Line Shopping 25 Casas)

> ### 🏆 PICK ESTRELLA DEL DÍA (`2026-11-09` — 1 Solo Pick: Mayor Probabilidad de Acierto)
> - **Partido**: **Memphis Grizzlies @ Toronto Raptors (MEM @ TOR)** (`2026-11-09 19:30 Hora Perú`)
> - **Pick Más Probable**: 🎯 **Gana Toronto Raptors (TOR)** (Ganador (Moneyline)) @ **`1.641`** *(Draft Kings)*
> - **Probabilidad de Acierto (Modelo Calibrado)**: 🔥 **`63.3%`** | **EV**: `+3.9%`
> - **Envío diario a tu correo**: `ACTIVO` *(1 solo correo diario vía GitHub Notification `@Drewks` con la selección de mayor EV entre las apuestas pendientes con cuotas observadas)*.

Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido, con vigilancia de movimiento en contra `CLV < -5.0%`):

| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Mejor Cuota (Casa) | Prob. Modelo | EV (%) | CLV (%) | Stake | Estado | Resultado / Ganancia |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |
| `2026-11-09 20:30` | **Denver Nuggets @ Houston Rockets (DEN @ HOU)** | Ganador (Moneyline) | **Gana Denver Nuggets (DEN)** | **3.370** *(DraftKings)* | 30.8% | `+3.8%` | — | S/1.12 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-09 19:30` | **Memphis Grizzlies @ Toronto Raptors (MEM @ TOR)** | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | **1.641** *(Draft Kings)* | 63.3% | `+3.9%` | — | S/3.50 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-09 19:00` | **Los Angeles Lakers @ Atlanta Hawks (LAL @ ATL)** | Total Puntos (Over/Under) | **UNDER 235.5 (Los Angeles Lakers @ Atlanta Hawks)** | **1.909** *(Draft Kings)* | 53.5% | `+2.1%` | — | S/2.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-07 22:00` | **San Antonio Spurs @ Portland Trail Blazers (SAS @ POR)** | Total Puntos (Over/Under) | **UNDER 228.5 (San Antonio Spurs @ Portland Trail Blazers)** | **1.909** *(DraftKings)* | 53.5% | `+2.2%` | — | S/1.34 | ✅ GANADA | S/+1.22 (HOME 103 - AWAY 125 (Total: 228)) |
| `2026-11-06 22:00` | **San Antonio Spurs @ Sacramento Kings (SAS @ SAC)** | Total Puntos (Over/Under) | **UNDER 228.5 (San Antonio Spurs @ Sacramento Kings)** | **1.930** *(LowVig.ag)* | 53.2% | `+2.8%` | — | S/1.68 | ❌ PERDIDA | S/-1.68 (HOME 109 - AWAY 124 (Total: 233)) |
| `2026-11-06 20:00` | **Oklahoma City Thunder @ Memphis Grizzlies (OKC @ MEM)** | Ganador (Moneyline) | **Gana Oklahoma City Thunder (OKC)** | **1.606** *(DraftKings)* | 63.5% | `+2.0%` | `-1.74%` | S/1.96 | ✅ GANADA | S/+1.19 (HOME 97 - AWAY 128 (Total: 225)) |
| `2026-11-06 19:30` | **Philadelphia 76ers @ Cleveland Cavaliers (PHI @ CLE)** | Ganador (Moneyline) | **Gana Cleveland Cavaliers (CLE)** | **2.210** *(1xBet)* | 47.9% | `+5.9%` | — | S/1.36 | ✅ GANADA | S/+1.65 (HOME 119 - AWAY 95 (Total: 214)) |
| `2026-11-05 21:00` | **Orlando Magic @ Phoenix Suns (ORL @ PHX)** | Ganador (Moneyline) | **Gana Phoenix Suns (PHX)** | **1.910** *(Matchbook)* | 53.5% | `+2.2%` | — | S/1.39 | ✅ GANADA | S/+1.26 (HOME 117 - AWAY 104 (Total: 221)) |
| `2026-11-04 21:00` | **Toronto Raptors @ Denver Nuggets (TOR @ DEN)** | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | **2.900** *(Bovada)* | 37.2% | `+7.9%` | — | S/1.10 | ❌ PERDIDA | S/-1.10 (HOME 128 - AWAY 109 (Total: 237)) |
| `2026-11-04 20:00` | **Cleveland Cavaliers @ Oklahoma City Thunder (CLE @ OKC)** | Ganador (Moneyline) | **Gana Oklahoma City Thunder (OKC)** | **1.770** *(FanDuel)* | 58.5% | `+3.6%` | — | S/2.19 | ✅ GANADA | S/+1.69 (HOME 124 - AWAY 116 (Total: 240)) |
| `2026-11-04 19:00` | **Philadelphia 76ers @ Detroit Pistons (PHI @ DET)** | Ganador (Moneyline) | **Gana Detroit Pistons (DET)** | **1.810** *(Coolbet)* | 56.6% | `+2.5%` | — | S/1.57 | ❌ PERDIDA | S/-1.57 (HOME 106 - AWAY 112 (Total: 218)) |
| `2026-11-02 20:30` | **Boston Celtics @ Houston Rockets (BOS @ HOU)** | Total Puntos (Over/Under) | **OVER 219.5 (Boston Celtics @ Houston Rockets)** | **1.990** *(1xBet)* | 51.3% | `+2.1%` | — | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 109 - AWAY 93 (Total: 202)) |
| `2026-11-02 20:00` | **New Orleans Pelicans @ Memphis Grizzlies (NOP @ MEM)** | Ganador (Moneyline) | **Gana New Orleans Pelicans (NOP)** | **2.900** *(888sport)* | 36.3% | `+5.3%` | `-10.11%` | S/1.00 | ✅ GANADA | S/+1.90 (HOME 134 - AWAY 135 (Total: 269)) |
| `2026-11-02 19:30` | **Washington Wizards @ Orlando Magic (WAS @ ORL)** | Total Puntos (Over/Under) | **OVER 225.5 (Washington Wizards @ Orlando Magic)** | **1.990** *(1xBet)* | 51.8% | `+3.0%` | — | S/1.13 | ❌ PERDIDA | S/-1.13 (HOME 94 - AWAY 103 (Total: 197)) |
| `2026-11-01 21:00` | **Toronto Raptors @ Los Angeles Lakers (TOR @ LAL)** | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | **2.670** *(1xBet)* | 39.2% | `+4.7%` | `+9.90%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 131 - AWAY 125 (Total: 256)) |
| `2026-11-01 20:30` | **LA Clippers @ Golden State Warriors (LAC @ GSW)** | Ganador (Moneyline) | **Gana Golden State Warriors (GSW)** | **1.820** *(Betfair)* | 56.9% | `+3.6%` | `-1.72%` | S/1.41 | ✅ GANADA | S/+1.16 (HOME 124 - AWAY 112 (Total: 236)) |
| `2026-11-01 17:00` | **Brooklyn Nets @ Indiana Pacers (BKN @ IND)** | Ganador (Moneyline) | **Gana Indiana Pacers (IND)** | **1.630** *(Betfair)* | 63.9% | `+4.2%` | `-0.79%` | S/2.16 | ❌ PERDIDA | S/-2.16 (HOME 90 - AWAY 98 (Total: 188)) |
| `2026-10-31 19:00` | **Minnesota Timberwolves @ San Antonio Spurs (MIN @ SAS)** | Ganador (Moneyline) | **Gana Minnesota Timberwolves (MIN)** | **5.400** *(DraftKings)* | 20.8% | `+12.2%` | `-11.19%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 121 - AWAY 111 (Total: 232)) |
| `2026-10-31 19:00` | **Sacramento Kings @ Memphis Grizzlies (SAC @ MEM)** | Ganador (Moneyline) | **Gana Sacramento Kings (SAC)** | **4.400** *(DraftKings)* | 24.1% | `+6.1%` | `+5.04%` | S/1.04 | ❌ PERDIDA | S/-1.04 (HOME 136 - AWAY 105 (Total: 241)) |
| `2026-10-30 21:00` | **Denver Nuggets @ Phoenix Suns (DEN @ PHX)** | Ganador (Moneyline) | **Gana Phoenix Suns (PHX)** | **2.420** *(DraftKings)* | 56.4% | `+36.4%` | `-6.61%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 120 - AWAY 127 (Total: 247)) |
| `2026-10-30 21:00` | **Denver Nuggets @ Phoenix Suns (DEN @ PHX)** | Total Puntos (Over/Under) | **UNDER 230.5 (Denver Nuggets @ Phoenix Suns)** | **1.909** *(DraftKings)* | 66.3% | `+26.6%` | — | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 120 - AWAY 127 (Total: 247)) |
| `2026-10-30 19:00` | **Houston Rockets @ Dallas Mavericks (HOU @ DAL)** | Ganador (Moneyline) | **Gana Dallas Mavericks (DAL)** | **2.600** *(DraftKings)* | 49.9% | `+29.8%` | — | S/1.00 | ✅ GANADA | S/+1.60 (HOME 116 - AWAY 111 (Total: 227)) |
| `2026-10-29 21:00` | **Memphis Grizzlies @ Portland Trail Blazers (MEM @ POR)** | Total Puntos (Over/Under) | **UNDER 232.5 (Memphis Grizzlies @ Portland Trail Blazers)** | **1.910** *(DraftKings)* | 63.5% | `+21.2%` | `-6.67%` | S/1.00 | ✅ GANADA | S/+0.91 (HOME 103 - AWAY 124 (Total: 227)) |
| `2026-10-29 19:00` | **Sacramento Kings @ New Orleans Pelicans (SAC @ NOP)** | Ganador (Moneyline) | **Gana New Orleans Pelicans (NOP)** | **1.520** *(DraftKings)* | 71.7% | `+9.0%` | `+1.94%` | S/1.00 | ✅ GANADA | S/+0.52 (HOME 132 - AWAY 120 (Total: 252)) |
| `2026-10-29 19:00` | **Sacramento Kings @ New Orleans Pelicans (SAC @ NOP)** | Total Puntos (Over/Under) | **UNDER 237.5 (Sacramento Kings @ New Orleans Pelicans)** | **1.950** *(Coolbet)* | 66.9% | `+30.4%` | — | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 132 - AWAY 120 (Total: 252)) |
| `2026-10-28 21:30` | **Los Angeles Lakers @ LA Clippers (LAL @ LAC)** | Ganador (Moneyline) | **Gana LA Clippers (LAC)** | **1.970** *(Matchbook)* | 59.9% | `+17.9%` | `-1.25%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 87 - AWAY 103 (Total: 190)) |
| `2026-10-28 20:30` | **Oklahoma City Thunder @ Dallas Mavericks (OKC @ DAL)** | Ganador (Moneyline) | **Gana Dallas Mavericks (DAL)** | **2.760** *(FanDuel)* | 49.8% | `+37.3%` | `-1.03%` | S/1.00 | ✅ GANADA | S/+1.76 (HOME 120 - AWAY 96 (Total: 216)) |
| `2026-10-28 20:30` | **Oklahoma City Thunder @ Dallas Mavericks (OKC @ DAL)** | Total Puntos (Over/Under) | **UNDER 228.5 (Oklahoma City Thunder @ Dallas Mavericks)** | **1.920** *(GTbets)* | 57.0% | `+9.4%` | `-4.00%` | S/1.00 | ✅ GANADA | S/+0.92 (HOME 120 - AWAY 96 (Total: 216)) |

### 🔍 2.A Radiografía de Apuestas Activas (¿Qué Está Apostando Hoy, Cuotas y Estadísticas Clave?)

#### 🎯 **Los Angeles Lakers @ Atlanta Hawks (LAL @ ATL)** — `2026-11-09 19:00 Hora Perú`
- **¿Qué está apostando el bot?**: **UNDER 235.5 (Los Angeles Lakers @ Atlanta Hawks)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`1.909`** en *Draft Kings* vs Cuota Justa del Modelo **`1.869`** *(Ventaja Matemática EV: `+2.13%`)*
- **Stake y Ganancia Potencial**: Stake **`S/2.00 PEN`** → Ganancia neta potencial: **`+S/1.82 PEN`** *(Retorno total: `S/3.82 PEN`)*
- **Probabilidades**: Modelo Calibrado **`53.5%`** vs Probabilidad Implícita Limpia Casa **`49.5%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `ATL -1.6 pts` | Total esperado **`228.5 pts`** *(Rango 80% Conformal: `206 – 252 pts` | Prob. Prórroga: `8.5%` | Prob. Paliza: `11.1%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `ATL 1537` vs `LAL 1607` | **Eficiencia Neta (Off/Def)**: `ATL (115.1/115.1)` vs `LAL (115.3/110.6)` (`Dif: -4.6 pts/100`)
  - **Ritmo (Pace)**: `100.1 posesiones` | **Descanso**: `ATL 2d` vs `LAL 2d` | **Viaje Geodésico (Millas Haversine)**: `Dif. +598 millas` (`0 husos horarios`)
- **Por qué apostó el modelo**: _Visita (Los Angeles Lakers) viaja +598 millas más · Eficiencia neta favorable (Los Angeles Lakers [LAL] +4.6 pts/100) · Cuota 1.909 en Draft Kings supera la cuota justa del modelo (1.869)._

#### 🎯 **Memphis Grizzlies @ Toronto Raptors (MEM @ TOR)** — `2026-11-09 19:30 Hora Perú`
- **¿Qué está apostando el bot?**: **Gana Toronto Raptors (TOR - Local)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`1.641`** en *Draft Kings* vs Cuota Justa del Modelo **`1.580`** *(Ventaja Matemática EV: `+3.92%`)*
- **Stake y Ganancia Potencial**: Stake **`S/3.50 PEN`** → Ganancia neta potencial: **`+S/2.24 PEN`** *(Retorno total: `S/5.74 PEN`)*
- **Probabilidades**: Modelo Calibrado **`63.3%`** vs Probabilidad Implícita Limpia Casa **`53.5%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `TOR +4.8 pts` | Total esperado **`227.6 pts`** *(Rango 80% Conformal: `205 – 251 pts` | Prob. Prórroga: `8.6%` | Prob. Paliza: `11.6%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `TOR 1534` vs `MEM 1430` | **Eficiencia Neta (Off/Def)**: `TOR (113.0/112.9)` vs `MEM (114.2/116.4)` (`Dif: +2.3 pts/100`)
  - **Ritmo (Pace)**: `99.3 posesiones` | **Descanso**: `TOR 3d` vs `MEM 3d` | **Viaje Geodésico (Millas Haversine)**: `Dif. +386 millas` (`1 husos horarios`)
- **Por qué apostó el modelo**: _Eficiencia neta favorable (Toronto Raptors [TOR] +2.3 pts/100) · Cuota 1.641 en Draft Kings supera la cuota justa del modelo (1.580)._

#### 🎯 **Denver Nuggets @ Houston Rockets (DEN @ HOU)** — `2026-11-09 20:30 Hora Perú`
- **¿Qué está apostando el bot?**: **Gana Denver Nuggets (DEN - Visita)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`3.370`** en *DraftKings* vs Cuota Justa del Modelo **`3.247`** *(Ventaja Matemática EV: `+3.80%`)*
- **Stake y Ganancia Potencial**: Stake **`S/1.12 PEN`** → Ganancia neta potencial: **`+S/2.65 PEN`** *(Retorno total: `S/3.77 PEN`)*
- **Probabilidades**: Modelo Calibrado **`30.8%`** vs Probabilidad Implícita Limpia Casa **`29.0%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `HOU +3.2 pts` | Total esperado **`221.8 pts`** *(Rango 80% Conformal: `200 – 244 pts` | Prob. Prórroga: `8.6%` | Prob. Paliza: `10.5%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `HOU 1615` vs `DEN 1562` | **Eficiencia Neta (Off/Def)**: `HOU (113.2/108.0)` vs `DEN (116.1/113.0)` (`Dif: +2.1 pts/100`)
  - **Ritmo (Pace)**: `98.3 posesiones` | **Descanso**: `HOU 2d` vs `DEN 3d` | **Viaje Geodésico (Millas Haversine)**: `Dif. -149 millas` (`1 husos horarios`)
- **Por qué apostó el modelo**: _Ajuste de retorno de gira para Houston Rockets · Eficiencia neta favorable (Houston Rockets [HOU] +2.1 pts/100) · Cuota 3.370 en DraftKings supera la cuota justa del modelo (3.247)._

### 📋 2.B Cartelera Completa de Próximos Partidos: Cuotas, Estadísticas a Tomar en Cuenta y Veredicto

| Hora (Perú) | Partido (`Visita @ Local`) | Cuotas Ganador (`Local / Visita`) | Línea Total (`O/U`) | Proyección Modelo (`Margen / Total`) | Estadísticas Clave (`Elo`, `NetRtg`, `Descanso`, `Viaje`) | ¿Qué Hace el Bot y Por Qué? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `2026-11-09 19:00` | **Los Angeles Lakers @ Atlanta Hawks (LAL @ ATL)** | Local **2.170** / Visita **2.210** *(Draft Kings)* | **237.5** (`O 1.94` / `U 1.94`) | **LAL -1.6 pts** (Prob Local `46.5%`) · Total **228.5 pts** | Elo `1537/1607` · Net `-4.6` · Pace `100.1` · Desc `2d/2d` · Viaje `+598 mi` | **🎯 APOSTADO: UNDER 235.5 (Los Angeles Lakers @ Atlanta Hawks) @ 1.909 (Draft Kings) | Stake S/2.00 (EV +2.13%)** — _Visita (Los Angeles Lakers) viaja +598 millas más · Eficiencia neta favorable (Los Angeles Lakers [LAL] +4.6 pts/100) · Cuota 1.909 en Draft Kings supera la cuota justa del modelo (1.869)._ |
| `2026-11-09 19:00` | **Cleveland Cavaliers @ Charlotte Hornets (CLE @ CHA)** | Local **3.840** / Visita **1.297** *(Draft Kings)* | **215.5** (`O 1.91` / `U 1.94`) | **CLE -3.3 pts** (Prob Local `42.2%`) · Total **219.3 pts** | Elo `1465/1564` · Net `-7.8` · Pace `98.5` · Desc `3d/2d` · Viaje `+436 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-09 19:00` | **Washington Wizards @ Detroit Pistons (WAS @ DET)** | Local **1.243** / Visita **4.760** *(Draft Kings)* | **218.5** (`O 1.91` / `U 1.94`) | **DET -14.4 pts** (Prob Local `89.0%`) · Total **219.1 pts** | Elo `1638/1344` · Net `+12.7` · Pace `97.9` · Desc `2d/2d` · Viaje `+909 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-09 19:30` | **Memphis Grizzlies @ Toronto Raptors (MEM @ TOR)** | Local **2.010** / Visita **2.310** *(Draft Kings)* | **229.5** (`O 1.94` / `U 1.91`) | **TOR -4.8 pts** (Prob Local `68.6%`) · Total **227.6 pts** | Elo `1534/1430` · Net `+2.3` · Pace `99.3` · Desc `3d/3d` · Viaje `+386 mi` | **🎯 APOSTADO: Gana Toronto Raptors (TOR - Local) @ 1.641 (Draft Kings) | Stake S/3.50 (EV +3.92%)** — _Eficiencia neta favorable (Toronto Raptors [TOR] +2.3 pts/100) · Cuota 1.641 en Draft Kings supera la cuota justa del modelo (1.580)._ |
| `2026-11-09 20:00` | **Indiana Pacers @ Dallas Mavericks (IND @ DAL)** | Local **1.621** / Visita **2.600** *(DraftKings)* | **227.5** (`O 1.95` / `U 1.94`) | **DAL -4.4 pts** (Prob Local `65.5%`) · Total **223.0 pts** | Elo `1442/1353` · Net `+5.3` · Pace `97.2` · Desc `1d/3d` · Viaje `+764 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-09 20:30` | **Denver Nuggets @ Houston Rockets (DEN @ HOU)** | Local **1.578** / Visita **3.860** *(Draft Kings)* | **223.5** (`O 1.93` / `U 1.93`) | **HOU -3.2 pts** (Prob Local `62.4%`) · Total **221.8 pts** | Elo `1615/1562` · Net `+2.1` · Pace `98.3` · Desc `2d/3d` · Viaje `-149 mi` | **🎯 APOSTADO: Gana Denver Nuggets (DEN - Visita) @ 3.370 (DraftKings) | Stake S/1.12 (EV +3.80%)** — _Ajuste de retorno de gira para Houston Rockets · Eficiencia neta favorable (Houston Rockets [HOU] +2.1 pts/100) · Cuota 3.370 en DraftKings supera la cuota justa del modelo (3.247)._ |
| `2026-11-09 21:00` | **San Antonio Spurs @ Phoenix Suns (SAS @ PHX)** | Local **3.960** / Visita **1.356** *(Draft Kings)* | **226.5** (`O 1.94` / `U 1.91`) | **SAS -5.6 pts** (Prob Local `30.5%`) · Total **224.1 pts** | Elo `1484/1697` · Net `-7.5` · Pace `100.0` · Desc `2d/2d` · Viaje `+1006 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-09 22:00` | **New Orleans Pelicans @ Golden State Warriors (NOP @ GSW)** | Local **1.265** / Visita **5.260** *(Draft Kings)* | **232.5** (`O 1.95` / `U 1.91`) | **GSW -7.5 pts** (Prob Local `74.7%`) · Total **232.9 pts** | Elo `1514/1421` · Net `+3.7` · Pace `100.2` · Desc `2d/1d` · Viaje `+348 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-10 19:30` | **Milwaukee Bucks @ New York Knicks (MIL @ NYK)** | Local **1.089** / Visita **8.100** *(Draft Kings)* | **219.5** (`O 1.88` / `U 1.94`) | **NYK -15.9 pts** (Prob Local `90.4%`) · Total **218.9 pts** | Elo `1668/1349` · Net `+15.4` · Pace `98.5` · Desc `3d/2d` · Viaje `+329 mi` | **🛡️ NO APOSTAR (Pass)** — _Cuotas eficientes: la probabilidad del modelo está alineada con las casas (sin ventaja EV suficiente)._ |
| `2026-11-10 20:00` | **Boston Celtics @ Philadelphia 76ers (BOS @ PHI)** | Local **1.917** / Visita **1.917** *(Draft Kings)* | **215.5** (`O 1.94` / `U 1.94`) | **BOS -1.4 pts** (Prob Local `47.2%`) · Total **215.4 pts** | Elo `1553/1626` · Net `-4.8` · Pace `98.2` · Desc `3d/2d` · Viaje `+27 mi` | **🛡️ NO APOSTAR (Pass)** — _Cuotas eficientes: la probabilidad del modelo está alineada con las casas (sin ventaja EV suficiente)._ |
| `2026-11-10 21:00` | **LA Clippers @ Phoenix Suns (LAC @ PHX)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **PHX -2.9 pts** (Prob Local `59.9%`) · Total **227.2 pts** | Elo `1484/1480` · Net `+1.6` · Pace `100.5` · Desc `3d/2d` · Viaje `+362 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-10 21:00` | **Miami Heat @ Utah Jazz (MIA @ UTA)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **MIA -5.5 pts** (Prob Local `31.8%`) · Total **233.1 pts** | Elo `1294/1479` · Net `-8.5` · Pace `98.0` · Desc `2d/2d` · Viaje `-452 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-10 22:00` | **Orlando Magic @ Sacramento Kings (ORL @ SAC)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **ORL -3.3 pts** (Prob Local `38.4%`) · Total **224.3 pts** | Elo `1343/1479` · Net `-4.5` · Pace `98.8` · Desc `2d/3d` · Viaje `+74 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-10 23:00` | **Oklahoma City Thunder @ Portland Trail Blazers (OKC @ POR)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **OKC -3.6 pts** (Prob Local `38.6%`) · Total **220.2 pts** | Elo `1535/1671` · Net `-6.4` · Pace `99.2` · Desc `3d/3d` · Viaje `+1485 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 19:00` | **Washington Wizards @ Indiana Pacers (WAS @ IND)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **IND -2.7 pts** (Prob Local `59.5%`) · Total **223.0 pts** | Elo `1353/1344` · Net `+1.2` · Pace `97.0` · Desc `5d/4d` · Viaje `+688 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 19:00` | **Cleveland Cavaliers @ New York Knicks (CLE @ NYK)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **NYK -5.8 pts** (Prob Local `70.4%`) · Total **219.2 pts** | Elo `1668/1564` · Net `+4.5` · Pace `98.7` · Desc `4d/4d` · Viaje `+0 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 19:00` | **Boston Celtics @ Toronto Raptors (BOS @ TOR)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **BOS -1.6 pts** (Prob Local `44.9%`) · Total **219.6 pts** | Elo `1534/1626` · Net `-3.8` · Pace `99.3` · Desc `5d/3d` · Viaje `+0 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 20:00` | **San Antonio Spurs @ Chicago Bulls (SAS @ CHI)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **SAS -11.3 pts** (Prob Local `17.5%`) · Total **233.2 pts** | Elo `1364/1697` · Net `-15.2` · Pace `100.5` · Desc `4d/4d` · Viaje `+1752 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 20:00` | **Denver Nuggets @ Memphis Grizzlies (DEN @ MEM)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **DEN -3.6 pts** (Prob Local `39.1%`) · Total **228.3 pts** | Elo `1430/1562` · Net `-6.8` · Pace `98.1` · Desc `5d/5d` · Viaje `+384 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 20:00` | **Los Angeles Lakers @ Milwaukee Bucks (LAL @ MIL)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **LAL -8.9 pts** (Prob Local `23.0%`) · Total **226.9 pts** | Elo `1349/1607` · Net `-11.7` · Pace `99.8` · Desc `3d/4d` · Viaje `+252 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 20:00` | **Brooklyn Nets @ New Orleans Pelicans (BKN @ NOP)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **NOP -6.0 pts** (Prob Local `70.3%`) · Total **227.5 pts** | Elo `1421/1331` · Net `+4.5` · Pace `99.7` · Desc `3d/3d` · Viaje `-1232 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 21:00` | **Orlando Magic @ Utah Jazz (ORL @ UTA)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **ORL -3.8 pts** (Prob Local `35.6%`) · Total **222.5 pts** | Elo `1294/1479` · Net `-6.3` · Pace `97.5` · Desc `3d/4d` · Viaje `-387 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 21:30` | **Golden State Warriors @ Houston Rockets (GSW @ HOU)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **HOU -5.8 pts** (Prob Local `70.2%`) · Total **222.8 pts** | Elo `1615/1514` · Net `+4.1` · Pace `99.2` · Desc `4d/4d` · Viaje `+627 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-11 22:00` | **Oklahoma City Thunder @ Portland Trail Blazers (OKC @ POR)** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **OKC -3.2 pts** (Prob Local `39.1%`) · Total **220.2 pts** | Elo `1535/1671` · Net `-5.3` · Pace `99.2` · Desc `4d/4d` · Viaje `+1485 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |

---

## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)

| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |
| `BET_20261108_2DE83152` | `2026-11-08` | `San Antonio Spurs @ Portland Trail Blazers (SAS @ POR)` | Total Puntos (Over/Under) | **UNDER 228.5 (San Antonio Spurs @ Portland Trail Blazers)** | 1.909 | 53.5% | `+2.2%` | ✅ WON | **S/+1.22** | `S/103.00` |
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

---

## 🎯 4. Seguimiento Oficial de Paper Trading — Player Props & SGP RETAbet V8

- **Banca Virtual de Props**: `S/100.00 PEN` (Inicial) → **`S/86.35 PEN`** (`-13.65 PEN`)
- **Tasa de Acierto (Win Rate)**: **`42.9%`** (`9G - 12P - 0E`)
- **ROI Acumulado en Props**: **`-18.57%`** | **Total Apostado**: `S/73.50 PEN`
- **Brier Score (Calibración)**: `0.2766` | **Cobertura Conformal**: `42.9%`
- **Total de Picks Registrados**: `345` (`0` en espera / `345` liquidados)

### 📊 Desglose de Rendimiento por Categoría de Prop

| Categoría | Liquidadas | Ganadas | Perdidas | Acierto (%) | Total Apostado (S/) | Beneficio Neto (S/) | ROI (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **PTS** | 21 | 0 | 4 | `0.0%` | S/14.00 | **S/-14.00** | `-100.0%` |
| **REB** | 16 | 3 | 0 | `100.0%` | S/10.50 | **S/+9.45** | `+90.0%` |
| **AST** | 40 | 3 | 4 | `42.9%` | S/24.50 | **S/-4.55** | `-18.6%` |
| **PRA** | 60 | 3 | 4 | `42.9%` | S/24.50 | **S/-4.55** | `-18.6%` |
| **3PM** | 88 | 0 | 0 | `0.0%` | S/0.00 | **S/+0.00** | `+0.0%` |
| **SGP** | 120 | 0 | 0 | `0.0%` | S/0.00 | **S/+0.00** | `+0.0%` |

### 📜 Últimas Apuestas de Props Liquidadas (Auditoría Inmutable)

| Fecha | Partido | Jugador / Combinada | Mercado | Selección | Línea | Cuota | Stat Real | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: | :---: | ---: | ---: |
| `2026-11-11` | `ESPN_401909961_2026-11-11_BOS_AT_PHI` | **Joel Embiid** | PRA | UNDER | `49.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-11` | `ESPN_401909961_2026-11-11_BOS_AT_PHI` | **LeBron James** | AST | UNDER | `8.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-11` | `ESPN_401909961_2026-11-11_BOS_AT_PHI` | **LeBron James** | PRA | UNDER | `40.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-11` | `ESPN_401909961_2026-11-11_BOS_AT_PHI` | **Anfernee Simons** | 3PM | UNDER | `3.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-11` | `ESPN_401909962_2026-11-11_LAC_AT_PHX` | **Gradey Dick** | 3PM | UNDER | `2.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-11` | `ESPN_401909963_2026-11-11_MIA_AT_UTA` | **Keyonte George** | AST | UNDER | `6.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-11` | `ESPN_401909963_2026-11-11_MIA_AT_UTA` | **Giannis Antetokounmpo** | PRA | OVER | `49.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-11` | `ESPN_401909964_2026-11-11_ORL_AT_SAC` | **Zach LaVine** | 3PM | UNDER | `3.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-11` | `ESPN_401909964_2026-11-11_ORL_AT_SAC` | **Zach LaVine** | PRA | UNDER | `35.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-11` | `ESPN_401909964_2026-11-11_ORL_AT_SAC` | **Keegan Murray** | PRA | UNDER | `23.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-11` | `ESPN_401909965_2026-11-11_OKC_AT_POR` | **Damian Lillard** | 3PM | UNDER | `3.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-11` | `ESPN_401909965_2026-11-11_OKC_AT_POR` | **Ja Morant** | AST | UNDER | `8.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-11` | `ESPN_401909965_2026-11-11_OKC_AT_POR` | **Jared McCain** | 3PM | UNDER | `2.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-12` | `ESPN_401909966_2026-11-12_WAS_AT_IND` | **Kelly Oubre Jr.** | PRA | OVER | `21.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
| `2026-11-12` | `ESPN_401909966_2026-11-12_WAS_AT_IND` | **Pascal Siakam** | PTS | OVER | `21.5` | `1.90` | — | VOID | **S/+0.00** | `S/100.00` |
