# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)

- **Última actualización**: `2026-11-21 09:58 (Hora Perú UTC-5)` (`2026-11-21T14:58:44Z`)
- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/98.03 PEN`** (`-1.97 PEN`)
- **ROI Actual**: `-3.98%` | **Yield Actual**: `-3.81%` | **CLV (vs cierre sin margen)**: `-2.79%` (N=32) | **Max Drawdown**: `9.00%` | **Apuestas en espera**: `1` (`S/2.13 PEN` reservados)
- **Motor Predictivo Activo**: `Ensemble (Elo + Ridge + LightGBM + Monte Carlo) anclado 70% al mercado sin margen`. Sin ventaja demostrada frente al mercado.
- **Modo de Apuesta Activo**: `Kelly Fraccional (25%) | Máx. 3 selecciones/jornada | EV >= 2.0%` | Solo cuotas observadas (nunca estimadas).
- **Alcance de métricas**: solo apuestas hechas con cuotas observadas en un mercado real (`v_observed_simulated_bets`).
- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)
- **Sistema de Aviso Automático**: `ACTIVO` *(aviso cuando se cumplan los criterios; cumplirlos solo habilita una revisión humana extendida, nunca dinero real automático)*.

---

## 🚦 1. Semáforo de Madurez de 8 Criterios y Graduación en 2 Niveles

### Estado Global: **🔴 EN FASE DE CALIBRACIÓN Y PAPER TRADING (2/8 CRITERIOS EN VERDE — NO USAR DINERO REAL AÚN)**
- **Progreso Muestra Total (Nivel 1)**: `[█░░░░░░░░░░░░░░░░░░░] 36 / 500 apuestas (7.2%)` — *Faltan **464** apuestas.*
- **Progreso Muestra 100% En Vivo (ESPN/OddsAPI)**: `[████░░░░░░░░░░░░░░░░] 36 / 200 en vivo (18.0%)` — *Tienes **1** apuestas reales en espera hoy.*

Para blindar tu capital contra rachas de suerte, el sistema evalúa **8 criterios cuantitativos estrictos** divididos en **2 niveles de graduación**:

| # | Criterio Cuantitativo de Auditoría | Estado Hoy | Valor Actual | Meta Nivel 1 (Piloto Micro-Banca 25%) | Meta Nivel 2 (Banca Completa 100%) |
| :-: | :--- | :---: | :--- | :--- | :--- |
| 1 | **Muestra total de apuestas liquidadas** | 🔴 PENDIENTE | `36 apuestas` | **>= 500 apuestas** | **>= 1,000 apuestas** |
| 2 | **Muestra 100% En Vivo (Pre-Partido Real)** | 🔴 PENDIENTE | `36 liquidadas (1 activas)` | **>= 200 en vivo** | **>= 500 en vivo** |
| 3 | **No peor que el Mercado sin margen ni que el Baseline (Brier & LogLoss)** | 🔴 PENDIENTE | `Modelo 0.2488 vs Mercado 0.2331 (N=45) | Baseline 0.2521` | **Modelo <= Mercado** | **Modelo <= Mercado** |
| 4 | **Error de Calibración por Tramos (ECE)** | 🟡 AJUSTANDO | `ECE 0.1866 (18.66%)` | **ECE <= 5.0%** | **ECE <= 3.5%** |
| 5 | **Rentabilidad Neta Positiva (ROI y Yield)** | 🔴 PENDIENTE | `ROI -3.98% / Yield -3.81%` | **ROI >= +2.0% / Yield >= +1.5%** | **ROI >= +3.5% (ambos mercados > 0%)** |
| 6 | **Control de Caída Máxima (Max Drawdown)** | ✅ VERDE | `Total 9.00% (En vivo: 9.00%)` | **MaxDD <= 15.0%** | **MaxDD <= 15.0%** |
| 7 | **Exclusión Estadística del Azar (Bootstrap CI)** | 🔴 PENDIENTE | `IC90 [-32.2%, +26.6%] / IC95 [-36.4%, +32.3%]` | **IC 90% lím. inf. > 0%** | **IC 95% lím. inf. > 0%** |
| 8 | **Cero Fuga Temporal, historial íntegro y ledger reconciliado** | ✅ VERDE | `Sin violaciones` | **0 violaciones** | **0 violaciones** |

> **Nota**: cumplir los criterios NO autoriza dinero real. Según AGENTS.md, el sistema opera exclusivamente en paper trading; los niveles solo habilitan una revisión humana extendida.

---

## 🏀 2. Mis Apuestas NBA Reales (ESPN / Line Shopping 25 Casas)

> ### 🏆 PICK ESTRELLA DEL DÍA (`2026-11-21` — 1 Solo Pick: Mayor Probabilidad de Acierto)
> - **Partido**: **Memphis Grizzlies @ Minnesota Timberwolves (MEM @ MIN)** (`2026-11-21 20:00 Hora Perú`)
> - **Pick Más Probable**: 🎯 **Gana Minnesota Timberwolves (MIN)** (Ganador (Moneyline)) @ **`1.448`** *(Pinnacle [LIVE_API])*
> - **Probabilidad de Acierto (Modelo Calibrado)**: 🔥 **`71.7%`** | **EV**: `+3.9%`
> - **Envío diario a tu correo**: `ACTIVO` *(1 solo correo diario vía GitHub Notification `@Drewks` con la selección de mayor EV entre las apuestas pendientes con cuotas observadas)*.

Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido, con vigilancia de movimiento en contra `CLV < -5.0%`):

| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Mejor Cuota (Casa) | Prob. Modelo | EV (%) | CLV (%) | Stake | Estado | Resultado / Ganancia |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |
| `2026-11-21 20:00` | **Memphis Grizzlies @ Minnesota Timberwolves (MEM @ MIN)** | Ganador (Moneyline) | **Gana Minnesota Timberwolves (MIN)** | **1.448** *(Pinnacle [LIVE_API])* | 71.7% | `+3.9%` | — | S/2.13 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-20 19:30` | **Indiana Pacers @ Cleveland Cavaliers (IND @ CLE)** | Ganador (Moneyline) | **Gana Cleveland Cavaliers (CLE)** | **1.457** *(Pinnacle [LIVE_API])* | 71.0% | `+3.4%` | `-1.31%` | S/1.81 | ✅ GANADA | S/+0.83 (HOME 128 - AWAY 119 (Total: 247)) |
| `2026-11-19 20:00` | **Portland Trail Blazers @ Milwaukee Bucks (POR @ MIL)** | Total Puntos (Over/Under) | **UNDER 229.5 (Portland Trail Blazers @ Milwaukee Bucks)** | **1.930** *(Matchbook)* | 54.4% | `+4.9%` | `-3.83%` | S/1.31 | ❌ PERDIDA | S/-1.31 (HOME 114 - AWAY 124 (Total: 238)) |
| `2026-11-18 19:00` | **Houston Rockets @ Indiana Pacers (HOU @ IND)** | Ganador (Moneyline) | **Gana Houston Rockets (HOU)** | **1.410** *(Pinnacle [LIVE_API])* | 72.7% | `+2.5%` | `+5.20%` | S/1.47 | ✅ GANADA | S/+0.60 (HOME 104 - AWAY 119 (Total: 223)) |
| `2026-11-16 20:00` | **Portland Trail Blazers @ Minnesota Timberwolves (POR @ MIN)** | Total Puntos (Over/Under) | **UNDER 227.5 (Portland Trail Blazers @ Minnesota Timberwolves)** | **1.962** *(Pinnacle [LIVE_API])* | 53.3% | `+4.6%` | `-3.77%` | S/1.14 | ✅ GANADA | S/+1.10 (HOME 106 - AWAY 98 (Total: 204)) |
| `2026-11-16 19:30` | **Philadelphia 76ers @ Brooklyn Nets (PHI @ BKN)** | Ganador (Moneyline) | **Gana Philadelphia 76ers (PHI)** | **1.442** *(Pinnacle [LIVE_API])* | 71.6% | `+3.3%` | `-2.00%` | S/1.78 | ✅ GANADA | S/+0.79 (HOME 123 - AWAY 135 (Total: 258)) |
| `2026-11-15 20:00` | **Atlanta Hawks @ Milwaukee Bucks (ATL @ MIL)** | Total Puntos (Over/Under) | **UNDER 234.5 (Atlanta Hawks @ Milwaukee Bucks)** | **1.926** *(Pinnacle [LIVE_API])* | 54.6% | `+5.2%` | `+2.37%` | S/1.30 | ✅ GANADA | S/+1.20 (HOME 106 - AWAY 113 (Total: 219)) |
| `2026-11-15 19:00` | **Houston Rockets @ Washington Wizards (HOU @ WAS)** | Ganador (Moneyline) | **Gana Houston Rockets (HOU)** | **1.330** *(Matchbook)* | 76.9% | `+2.3%` | `-1.27%` | S/1.60 | ✅ GANADA | S/+0.53 (HOME 119 - AWAY 147 (Total: 266)) |
| `2026-11-15 16:00` | **Los Angeles Lakers @ Phoenix Suns (LAL @ PHX)** | Ganador (Moneyline) | **Gana Los Angeles Lakers (LAL)** | **1.700** *(Betfair)* | 60.9% | `+3.5%` | `+2.09%` | S/1.18 | ✅ GANADA | S/+0.83 (HOME 123 - AWAY 131 (Total: 254)) |
| `2026-11-09 20:30` | **Denver Nuggets @ Houston Rockets (DEN @ HOU)** | Ganador (Moneyline) | **Gana Denver Nuggets (DEN)** | **3.370** *(DraftKings)* | 30.8% | `+3.8%` | — | S/1.12 | ❌ PERDIDA | S/-1.12 (HOME 110 - AWAY 100 (Total: 210)) |
| `2026-11-09 19:30` | **Memphis Grizzlies @ Toronto Raptors (MEM @ TOR)** | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | **1.641** *(Draft Kings)* | 63.3% | `+3.9%` | — | S/3.50 | ❌ PERDIDA | S/-3.50 (HOME 102 - AWAY 118 (Total: 220)) |
| `2026-11-09 19:00` | **Los Angeles Lakers @ Atlanta Hawks (LAL @ ATL)** | Total Puntos (Over/Under) | **UNDER 235.5 (Los Angeles Lakers @ Atlanta Hawks)** | **1.909** *(Draft Kings)* | 53.5% | `+2.1%` | `+2.18%` | S/2.00 | ❌ PERDIDA | S/-2.00 (HOME 114 - AWAY 124 (Total: 238)) |
| `2026-11-07 22:00` | **San Antonio Spurs @ Portland Trail Blazers (SAS @ POR)** | Total Puntos (Over/Under) | **UNDER 228.5 (San Antonio Spurs @ Portland Trail Blazers)** | **1.909** *(DraftKings)* | 53.5% | `+2.2%` | `-8.34%` | S/1.34 | ✅ GANADA | S/+1.22 (HOME 103 - AWAY 125 (Total: 228)) |
| `2026-11-06 22:00` | **San Antonio Spurs @ Sacramento Kings (SAS @ SAC)** | Total Puntos (Over/Under) | **UNDER 228.5 (San Antonio Spurs @ Sacramento Kings)** | **1.930** *(LowVig.ag)* | 53.2% | `+2.8%` | — | S/1.68 | ❌ PERDIDA | S/-1.68 (HOME 109 - AWAY 124 (Total: 233)) |
| `2026-11-06 20:00` | **Oklahoma City Thunder @ Memphis Grizzlies (OKC @ MEM)** | Ganador (Moneyline) | **Gana Oklahoma City Thunder (OKC)** | **1.606** *(DraftKings)* | 63.5% | `+2.0%` | `-3.30%` | S/1.96 | ✅ GANADA | S/+1.19 (HOME 97 - AWAY 128 (Total: 225)) |
| `2026-11-06 19:30` | **Philadelphia 76ers @ Cleveland Cavaliers (PHI @ CLE)** | Ganador (Moneyline) | **Gana Cleveland Cavaliers (CLE)** | **2.210** *(1xBet)* | 47.9% | `+5.9%` | `-4.12%` | S/1.36 | ✅ GANADA | S/+1.65 (HOME 119 - AWAY 95 (Total: 214)) |
| `2026-11-05 21:00` | **Orlando Magic @ Phoenix Suns (ORL @ PHX)** | Ganador (Moneyline) | **Gana Phoenix Suns (PHX)** | **1.910** *(Matchbook)* | 53.5% | `+2.2%` | `-2.25%` | S/1.39 | ✅ GANADA | S/+1.26 (HOME 117 - AWAY 104 (Total: 221)) |
| `2026-11-04 21:00` | **Toronto Raptors @ Denver Nuggets (TOR @ DEN)** | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | **2.900** *(Bovada)* | 37.2% | `+7.9%` | `-6.39%` | S/1.10 | ❌ PERDIDA | S/-1.10 (HOME 128 - AWAY 109 (Total: 237)) |
| `2026-11-04 20:00` | **Cleveland Cavaliers @ Oklahoma City Thunder (CLE @ OKC)** | Ganador (Moneyline) | **Gana Oklahoma City Thunder (OKC)** | **1.770** *(FanDuel)* | 58.5% | `+3.6%` | `-3.64%` | S/2.19 | ✅ GANADA | S/+1.69 (HOME 124 - AWAY 116 (Total: 240)) |
| `2026-11-04 19:00` | **Philadelphia 76ers @ Detroit Pistons (PHI @ DET)** | Ganador (Moneyline) | **Gana Detroit Pistons (DET)** | **1.810** *(Coolbet)* | 56.6% | `+2.5%` | `-3.65%` | S/1.57 | ❌ PERDIDA | S/-1.57 (HOME 106 - AWAY 112 (Total: 218)) |
| `2026-11-02 20:30` | **Boston Celtics @ Houston Rockets (BOS @ HOU)** | Total Puntos (Over/Under) | **OVER 219.5 (Boston Celtics @ Houston Rockets)** | **1.990** *(1xBet)* | 51.3% | `+2.1%` | `-3.71%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 109 - AWAY 93 (Total: 202)) |
| `2026-11-02 20:00` | **New Orleans Pelicans @ Memphis Grizzlies (NOP @ MEM)** | Ganador (Moneyline) | **Gana New Orleans Pelicans (NOP)** | **2.900** *(888sport)* | 36.3% | `+5.3%` | `-8.54%` | S/1.00 | ✅ GANADA | S/+1.90 (HOME 134 - AWAY 135 (Total: 269)) |
| `2026-11-02 19:30` | **Washington Wizards @ Orlando Magic (WAS @ ORL)** | Total Puntos (Over/Under) | **OVER 225.5 (Washington Wizards @ Orlando Magic)** | **1.990** *(1xBet)* | 51.8% | `+3.0%` | `-3.71%` | S/1.13 | ❌ PERDIDA | S/-1.13 (HOME 94 - AWAY 103 (Total: 197)) |
| `2026-11-01 21:00` | **Toronto Raptors @ Los Angeles Lakers (TOR @ LAL)** | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | **2.670** *(1xBet)* | 39.2% | `+4.7%` | `-3.75%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 131 - AWAY 125 (Total: 256)) |
| `2026-11-01 20:30` | **LA Clippers @ Golden State Warriors (LAC @ GSW)** | Ganador (Moneyline) | **Gana Golden State Warriors (GSW)** | **1.820** *(Betfair)* | 56.9% | `+3.6%` | `-1.72%` | S/1.41 | ✅ GANADA | S/+1.16 (HOME 124 - AWAY 112 (Total: 236)) |
| `2026-11-01 17:00` | **Brooklyn Nets @ Indiana Pacers (BKN @ IND)** | Ganador (Moneyline) | **Gana Indiana Pacers (IND)** | **1.630** *(Betfair)* | 63.9% | `+4.2%` | `-1.36%` | S/2.16 | ❌ PERDIDA | S/-2.16 (HOME 90 - AWAY 98 (Total: 188)) |
| `2026-10-31 19:00` | **Minnesota Timberwolves @ San Antonio Spurs (MIN @ SAS)** | Ganador (Moneyline) | **Gana Minnesota Timberwolves (MIN)** | **5.400** *(DraftKings)* | 20.8% | `+12.2%` | `-11.19%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 121 - AWAY 111 (Total: 232)) |
| `2026-10-31 19:00` | **Sacramento Kings @ Memphis Grizzlies (SAC @ MEM)** | Ganador (Moneyline) | **Gana Sacramento Kings (SAC)** | **4.400** *(DraftKings)* | 24.1% | `+6.1%` | `+5.04%` | S/1.04 | ❌ PERDIDA | S/-1.04 (HOME 136 - AWAY 105 (Total: 241)) |
| `2026-10-30 21:00` | **Denver Nuggets @ Phoenix Suns (DEN @ PHX)** | Ganador (Moneyline) | **Gana Phoenix Suns (PHX)** | **2.420** *(DraftKings)* | 56.4% | `+36.4%` | `-6.61%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 120 - AWAY 127 (Total: 247)) |
| `2026-10-30 21:00` | **Denver Nuggets @ Phoenix Suns (DEN @ PHX)** | Total Puntos (Over/Under) | **UNDER 230.5 (Denver Nuggets @ Phoenix Suns)** | **1.909** *(DraftKings)* | 66.3% | `+26.6%` | `-8.11%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 120 - AWAY 127 (Total: 247)) |
| `2026-10-30 19:00` | **Houston Rockets @ Dallas Mavericks (HOU @ DAL)** | Ganador (Moneyline) | **Gana Dallas Mavericks (DAL)** | **2.600** *(DraftKings)* | 49.9% | `+29.8%` | — | S/1.00 | ✅ GANADA | S/+1.60 (HOME 116 - AWAY 111 (Total: 227)) |
| `2026-10-29 21:00` | **Memphis Grizzlies @ Portland Trail Blazers (MEM @ POR)** | Total Puntos (Over/Under) | **UNDER 232.5 (Memphis Grizzlies @ Portland Trail Blazers)** | **1.910** *(DraftKings)* | 63.5% | `+21.2%` | `-6.62%` | S/1.00 | ✅ GANADA | S/+0.91 (HOME 103 - AWAY 124 (Total: 227)) |
| `2026-10-29 19:00` | **Sacramento Kings @ New Orleans Pelicans (SAC @ NOP)** | Total Puntos (Over/Under) | **UNDER 237.5 (Sacramento Kings @ New Orleans Pelicans)** | **1.950** *(Coolbet)* | 66.9% | `+30.4%` | `+2.59%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 132 - AWAY 120 (Total: 252)) |
| `2026-10-29 19:00` | **Sacramento Kings @ New Orleans Pelicans (SAC @ NOP)** | Ganador (Moneyline) | **Gana New Orleans Pelicans (NOP)** | **1.520** *(DraftKings)* | 71.7% | `+9.0%` | `-3.23%` | S/1.00 | ✅ GANADA | S/+0.52 (HOME 132 - AWAY 120 (Total: 252)) |
| `2026-10-28 21:30` | **Los Angeles Lakers @ LA Clippers (LAL @ LAC)** | Ganador (Moneyline) | **Gana LA Clippers (LAC)** | **1.970** *(Matchbook)* | 59.9% | `+17.9%` | `-1.25%` | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 87 - AWAY 103 (Total: 190)) |
| `2026-10-28 20:30` | **Oklahoma City Thunder @ Dallas Mavericks (OKC @ DAL)** | Total Puntos (Over/Under) | **UNDER 228.5 (Oklahoma City Thunder @ Dallas Mavericks)** | **1.920** *(GTbets)* | 57.0% | `+9.4%` | `-4.00%` | S/1.00 | ✅ GANADA | S/+0.92 (HOME 120 - AWAY 96 (Total: 216)) |
| `2026-10-28 20:30` | **Oklahoma City Thunder @ Dallas Mavericks (OKC @ DAL)** | Ganador (Moneyline) | **Gana Dallas Mavericks (DAL)** | **2.760** *(FanDuel)* | 49.8% | `+37.3%` | `-1.03%` | S/1.00 | ✅ GANADA | S/+1.76 (HOME 120 - AWAY 96 (Total: 216)) |

### 🔍 2.A Radiografía de Apuestas Activas (¿Qué Está Apostando Hoy, Cuotas y Estadísticas Clave?)

#### 🎯 **Minnesota Timberwolves @ Memphis Grizzlies (MIN @ MEM)** — `2026-11-22T01:00:00Z UTC`
- **¿Qué está apostando el bot?**: **Victoria Minnesota Timberwolves** en *Pinnacle [LIVE_API]*
- **Cuota Tomada vs Cuota Justa**: **`1.448`** vs Cuota Justa **`1.390`** *(Ventaja Matemática EV: `+3.90%`)*
- **Stake y Ganancia Potencial**: Stake **`S/2.13 PEN`** → Ganancia neta potencial: **`+S/0.96 PEN`**
- **Probabilidades**: Modelo Calibrado **`71.7%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `+5.8 pts` | Total esperado **`225.2 pts`** *(Intervalo Simulación 80% [Q10–Q90]: `203 – 248 pts` | Prob. Prórroga: `7.6%` | Prob. Paliza: `12.0%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `MIN 1616.4` vs `MEM 1489.7` | **Eficiencia Neta (Off/Def)**: `MIN (113.1/108.8)` vs `MEM (117.1/116.1)` (`Dif: +3.3 pts/100`)
  - **Ritmo (Pace)**: `98.6 posesiones` | **Descanso**: Dif `+0d` | **Viaje Geodésico**: `Dif. +701 millas`
- **Por qué apostó el modelo**: _El modelo proyecta una probabilidad de éxito del 71.7% frente a una cuota de 1.45 (valor esperado positivo del +3.9% con stake calculado de S/ 2.13 PEN)._

### 📋 2.B Cartelera Completa de Próximos Partidos: Cuotas, Estadísticas a Tomar en Cuenta y Veredicto

| Hora (UTC) | Partido | Cuotas Ganador (`Local / Visita`) | Proyección Modelo (`Margen / Total`) | Estadísticas Clave (`Elo`, `NetRtg`, `Descanso`) | ¿Qué Hace el Bot y Por Qué? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `2026-11-21T18:00:00Z` | **Philadelphia 76ers @ Milwaukee Bucks (PHI @ MIL)** | Local **1.220** / Visita **6.200** | **Margen +12.1 pts** (Local `85.8%`) · Total **227.9 pts** | Elo `1560.0/1317.5` · Net `+8.9` · Pace `100.4` · Desc `+1d` | **SIN APUESTA (NO_BET)** — _HOME: EV -0.76% <= threshold 2.00%; HOME: EV -1.39% <= threshold 2.00%_ |
| `2026-11-22T00:30:00Z` | **New York Knicks @ Portland Trail Blazers (NYK @ POR)** | Local **1.540** / Visita **2.900** | **Margen +5.9 pts** (Local `70.1%`) · Total **216.6 pts** | Elo `1674.9/1574.5` · Net `+5.2` · Pace `99.0` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _HOME: EV 1.08% <= threshold 2.00%; HOME: EV -1.58% <= threshold 2.00%_ |
| `2026-11-22T01:00:00Z` | **Dallas Mavericks @ LA Clippers (DAL @ LAC)** | Local **1.520** / Visita **2.900** | **Margen +3.2 pts** (Local `60.6%`) · Total **229.7 pts** | Elo `1442.1/1447.8` · Net `+1.1` · Pace `99.8` · Desc `+1d` | **SIN APUESTA (NO_BET)** — _AWAY: EV 1.24% <= threshold 2.00%; UNDER: EV -0.66% <= threshold 2.00%_ |
| `2026-11-22T01:00:00Z` | **Minnesota Timberwolves @ Memphis Grizzlies (MIN @ MEM)** | Local **1.500** / Visita **3.050** | **Margen +5.8 pts** (Local `71.9%`) · Total **225.2 pts** | Elo `1616.4/1489.7` · Net `+3.3` · Pace `98.6` · Desc `+0d` | **APUESTA DETECTADA: Victoria Minnesota Timberwolves @ 1.45 en Pinnacle [LIVE_API]** — _El modelo proyecta una probabilidad de éxito del 71.7% frente a una cuota de 1.45 (valor esperado positivo del +3.9% con stake calculado de S/ 2.13 PEN)._ |
| `2026-11-22T01:00:00Z` | **San Antonio Spurs @ New Orleans Pelicans (SAS @ NOP)** | Local **1.090** / Visita **11.250** | **Margen +15.7 pts** (Local `91.3%`) · Total **226.9 pts** | Elo `1711.1/1377.2` · Net `+11.2` · Pace `99.6` · Desc `+1d` | **SIN APUESTA (NO_BET)** — _AWAY: EV 0.31% <= threshold 2.00%; UNDER: EV -0.52% <= threshold 2.00%_ |
| `2026-11-22T03:00:00Z` | **Sacramento Kings @ Boston Celtics (SAC @ BOS)** | Local **7.200** / Visita **1.160** | **Margen -13.5 pts** (Local `12.9%`) · Total **218.5 pts** | Elo `1295.2/1645.4` · Net `-14.6` · Pace `98.3` · Desc `-2d` | **SIN APUESTA (NO_BET)** — _AWAY: EV -2.00% <= threshold 2.00%; OVER: EV -2.90% <= threshold 2.00%_ |
| `2026-11-22T20:30:00Z` | **Atlanta Hawks @ Detroit Pistons (ATL @ DET)** | ⏳ *Sin cuotas publicadas* | **Margen -0.9 pts** (Local `46.1%`) · Total **223.3 pts** | Elo `1530.6/1638.4` · Net `-3.3` · Pace `99.8` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-22T23:00:00Z` | **Miami Heat @ Oklahoma City Thunder (MIA @ OKC)** | ⏳ *Sin cuotas publicadas* | **Margen +0.6 pts** (Local `50.8%`) · Total **232.1 pts** | Elo `1535.6/1644.2` · Net `-3.3` · Pace `100.3` · Desc `+2d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-23T00:00:00Z` | **Washington Wizards @ Orlando Magic (WAS @ ORL)** | ⏳ *Sin cuotas publicadas* | **Margen -4.9 pts** (Local `32.4%`) · Total **222.6 pts** | Elo `1316.3/1502.8` · Net `-5.9` · Pace `98.1` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-23T00:00:00Z` | **Chicago Bulls @ Denver Nuggets (CHI @ DEN)** | ⏳ *Sin cuotas publicadas* | **Margen -5.3 pts** (Local `32.0%`) · Total **233.0 pts** | Elo `1392.2/1578.9` · Net `-7.7` · Pace `99.2` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-23T00:00:00Z` | **Utah Jazz @ Dallas Mavericks (UTA @ DAL)** | ⏳ *Sin cuotas publicadas* | **Margen -3.5 pts** (Local `38.3%`) · Total **224.8 pts** | Elo `1311.0/1442.1` · Net `-6.1` · Pace `97.0` · Desc `-2d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-23T01:00:00Z` | **New York Knicks @ Indiana Pacers (NYK @ IND)** | ⏳ *Sin cuotas publicadas* | **Margen +14.0 pts** (Local `89.4%`) · Total **217.1 pts** | Elo `1674.9/1350.8` · Net `+11.2` · Pace `97.8` · Desc `+1d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-23T01:30:00Z` | **Golden State Warriors @ Boston Celtics (GSW @ BOS)** | ⏳ *Sin cuotas publicadas* | **Margen -7.2 pts** (Local `28.6%`) · Total **216.1 pts** | Elo `1458.9/1645.4` · Net `-10.6` · Pace `98.2` · Desc `-1d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |

---

## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)

| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |
| `BET_20261121_99EEB422` | `2026-11-21` | `Indiana Pacers @ Cleveland Cavaliers (IND @ CLE)` | Ganador (Moneyline) | **Gana Cleveland Cavaliers (CLE)** | 1.457 | 71.0% | `+3.4%` | ✅ WON | **S/+0.83** | `S/98.03` |
| `BET_20261120_E9FA8580` | `2026-11-20` | `Portland Trail Blazers @ Milwaukee Bucks (POR @ MIL)` | Total Puntos (Over/Under) | **UNDER 229.5 (Portland Trail Blazers @ Milwaukee Bucks)** | 1.930 | 54.4% | `+4.9%` | ❌ LOST | **S/-1.31** | `S/97.20` |
| `BET_20261119_776B4D10` | `2026-11-19` | `Houston Rockets @ Indiana Pacers (HOU @ IND)` | Ganador (Moneyline) | **Gana Houston Rockets (HOU)** | 1.410 | 72.7% | `+2.5%` | ✅ WON | **S/+0.60** | `S/98.51` |
| `BET_20261117_4680E990` | `2026-11-17` | `Portland Trail Blazers @ Minnesota Timberwolves (POR @ MIN)` | Total Puntos (Over/Under) | **UNDER 227.5 (Portland Trail Blazers @ Minnesota Timberwolves)** | 1.962 | 53.3% | `+4.6%` | ✅ WON | **S/+1.10** | `S/97.91` |
| `BET_20261117_00CA0272` | `2026-11-17` | `Philadelphia 76ers @ Brooklyn Nets (PHI @ BKN)` | Ganador (Moneyline) | **Gana Philadelphia 76ers (PHI)** | 1.442 | 71.6% | `+3.3%` | ✅ WON | **S/+0.79** | `S/96.81` |
| `BET_20261116_C719CA5F` | `2026-11-16` | `Atlanta Hawks @ Milwaukee Bucks (ATL @ MIL)` | Total Puntos (Over/Under) | **UNDER 234.5 (Atlanta Hawks @ Milwaukee Bucks)** | 1.926 | 54.6% | `+5.2%` | ✅ WON | **S/+1.20** | `S/96.03` |
| `BET_20261116_26DB932D` | `2026-11-16` | `Houston Rockets @ Washington Wizards (HOU @ WAS)` | Ganador (Moneyline) | **Gana Houston Rockets (HOU)** | 1.330 | 76.9% | `+2.3%` | ✅ WON | **S/+0.53** | `S/94.82` |
| `BET_20261115_3890004C` | `2026-11-15` | `Los Angeles Lakers @ Phoenix Suns (LAL @ PHX)` | Ganador (Moneyline) | **Gana Los Angeles Lakers (LAL)** | 1.700 | 60.9% | `+3.5%` | ✅ WON | **S/+0.83** | `S/94.30` |
| `BET_20261110_60276AD1` | `2026-11-10` | `Denver Nuggets @ Houston Rockets (DEN @ HOU)` | Ganador (Moneyline) | **Gana Denver Nuggets (DEN)** | 3.370 | 30.8% | `+3.8%` | ❌ LOST | **S/-1.12** | `S/93.47` |
| `BET_20261110_A565DE31` | `2026-11-10` | `Memphis Grizzlies @ Toronto Raptors (MEM @ TOR)` | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | 1.641 | 63.3% | `+3.9%` | ❌ LOST | **S/-3.50** | `S/94.59` |
| `BET_20261110_E8F6F562` | `2026-11-10` | `Los Angeles Lakers @ Atlanta Hawks (LAL @ ATL)` | Total Puntos (Over/Under) | **UNDER 235.5 (Los Angeles Lakers @ Atlanta Hawks)** | 1.909 | 53.5% | `+2.1%` | ❌ LOST | **S/-2.00** | `S/98.09` |
| `BET_20261108_2DE83152` | `2026-11-08` | `San Antonio Spurs @ Portland Trail Blazers (SAS @ POR)` | Total Puntos (Over/Under) | **UNDER 228.5 (San Antonio Spurs @ Portland Trail Blazers)** | 1.909 | 53.5% | `+2.2%` | ✅ WON | **S/+1.22** | `S/100.09` |
| `BET_20261107_7EA0942D` | `2026-11-07` | `San Antonio Spurs @ Sacramento Kings (SAS @ SAC)` | Total Puntos (Over/Under) | **UNDER 228.5 (San Antonio Spurs @ Sacramento Kings)** | 1.930 | 53.2% | `+2.8%` | ❌ LOST | **S/-1.68** | `S/98.87` |
| `BET_20261107_7C4523D5` | `2026-11-07` | `Oklahoma City Thunder @ Memphis Grizzlies (OKC @ MEM)` | Ganador (Moneyline) | **Gana Oklahoma City Thunder (OKC)** | 1.606 | 63.5% | `+2.0%` | ✅ WON | **S/+1.19** | `S/100.55` |
| `BET_20261107_CB5E045A` | `2026-11-07` | `Philadelphia 76ers @ Cleveland Cavaliers (PHI @ CLE)` | Ganador (Moneyline) | **Gana Cleveland Cavaliers (CLE)** | 2.210 | 47.9% | `+5.9%` | ✅ WON | **S/+1.65** | `S/99.36` |
| `BET_20261106_92B26B33` | `2026-11-06` | `Orlando Magic @ Phoenix Suns (ORL @ PHX)` | Ganador (Moneyline) | **Gana Phoenix Suns (PHX)** | 1.910 | 53.5% | `+2.2%` | ✅ WON | **S/+1.26** | `S/97.72` |
| `BET_20261105_A563FA74` | `2026-11-05` | `Toronto Raptors @ Denver Nuggets (TOR @ DEN)` | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | 2.900 | 37.2% | `+7.9%` | ❌ LOST | **S/-1.10** | `S/96.45` |
| `BET_20261105_63E8261D` | `2026-11-05` | `Cleveland Cavaliers @ Oklahoma City Thunder (CLE @ OKC)` | Ganador (Moneyline) | **Gana Oklahoma City Thunder (OKC)** | 1.770 | 58.5% | `+3.6%` | ✅ WON | **S/+1.69** | `S/97.55` |
| `BET_20261105_11DC3E0B` | `2026-11-05` | `Philadelphia 76ers @ Detroit Pistons (PHI @ DET)` | Ganador (Moneyline) | **Gana Detroit Pistons (DET)** | 1.810 | 56.6% | `+2.5%` | ❌ LOST | **S/-1.57** | `S/95.87` |
| `BET_20261103_06657F1C` | `2026-11-03` | `Boston Celtics @ Houston Rockets (BOS @ HOU)` | Total Puntos (Over/Under) | **OVER 219.5 (Boston Celtics @ Houston Rockets)** | 1.990 | 51.3% | `+2.1%` | ❌ LOST | **S/-1.00** | `S/97.44` |

---

## 🎯 4. Seguimiento Oficial de Paper Trading — Player Props & SGP RETAbet V8

- **Banca Virtual de Props**: `S/100.00 PEN` (Inicial) → **`S/86.35 PEN`** (`-13.65 PEN`)
- **Tasa de Acierto (Win Rate)**: **`42.9%`** (`9G - 12P - 0E`)
- **ROI Acumulado en Props**: **`-18.57%`** | **Total Apostado (Resueltas)**: `S/73.50 PEN`
- **Brier Score (Calibración)**: `0.2766` | **LogLoss**: `0.7475` | **Accuracy (`p>=0.5`)**: `42.9%` | **Cobertura Empírica Intervalos Venn-Abers**: `28.6%`
- **Total de Picks Registrados**: `345` (`0` en espera / `21` resueltas verificadas / `324` anuladas `VOID` con impacto `S/0.00 PEN`)

### 📊 Desglose de Rendimiento por Categoría de Prop

| Categoría | Resueltas | Ganadas | Perdidas | Anuladas (VOID) | Acierto (%) | Total Apostado (S/) | Beneficio Neto (S/) | ROI (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **PTS** | 4 | 0 | 4 | 17 | `0.0%` | S/14.00 | **S/-14.00** | `-100.0%` |
| **REB** | 3 | 3 | 0 | 13 | `100.0%` | S/10.50 | **S/+9.45** | `+90.0%` |
| **AST** | 7 | 3 | 4 | 33 | `42.9%` | S/24.50 | **S/-4.55** | `-18.6%` |
| **PRA** | 7 | 3 | 4 | 53 | `42.9%` | S/24.50 | **S/-4.55** | `-18.6%` |
| **3PM** | 0 | 0 | 0 | 88 | `0.0%` | S/0.00 | **S/+0.00** | `+0.0%` |
| **SGP** | 0 | 0 | 0 | 120 | `0.0%` | S/0.00 | **S/+0.00** | `+0.0%` |

### 📜 Últimas Apuestas de Props Liquidadas (Auditoría Inmutable)

> **Nota de Transparencia de Auditoría**: Existen **324 registros históricos en estado `VOID` (anulados)** procedentes de ciclos sintéticos previos sin verificación de boxscore oficial (impacto financiero **`S/0.00 PEN`**). La tabla inferior muestra **exclusivamente las 21 apuestas de props con resultado oficial resuelto (`WON`, `LOST`, `PUSH`)**.

| Fecha | Partido | Jugador / Combinada | Mercado | Selección | Línea | Cuota | Stat Real | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: | :---: | ---: | ---: |
| `2026-11-08` | Houston Rockets @ Phoenix Suns (HOU @ PHX) | **Devin Booker** | AST | UNDER | `7.5` | `1.90` | `3.0` | ✅ WON | **S/+3.15** | `S/86.35` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Stephen Curry** | PTS | UNDER | `27.5` | `1.90` | `41.0` | ❌ LOST | **S/-3.50** | `S/83.20` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Stephen Curry** | PRA | UNDER | `37.5` | `1.90` | `53.0` | ❌ LOST | **S/-3.50** | `S/86.70` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Draymond Green** | REB | UNDER | `7.5` | `1.90` | `6.0` | ✅ WON | **S/+3.15** | `S/90.20` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Draymond Green** | PRA | UNDER | `22.5` | `1.90` | `21.0` | ✅ WON | **S/+3.15** | `S/87.05` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Draymond Green** | AST | UNDER | `6.5` | `1.90` | `13.0` | ❌ LOST | **S/-3.50** | `S/83.90` |
| `2026-11-08` | Houston Rockets @ Phoenix Suns (HOU @ PHX) | **Devin Booker** | AST | UNDER | `7.5` | `1.90` | `3.0` | ✅ WON | **S/+3.15** | `S/87.40` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Stephen Curry** | PTS | UNDER | `27.5` | `1.90` | `41.0` | ❌ LOST | **S/-3.50** | `S/84.25` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Stephen Curry** | PRA | UNDER | `37.5` | `1.90` | `53.0` | ❌ LOST | **S/-3.50** | `S/87.75` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Draymond Green** | REB | UNDER | `7.5` | `1.90` | `6.0` | ✅ WON | **S/+3.15** | `S/91.25` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Draymond Green** | PRA | UNDER | `22.5` | `1.90` | `21.0` | ✅ WON | **S/+3.15** | `S/88.10` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Draymond Green** | AST | UNDER | `6.5` | `1.90` | `13.0` | ❌ LOST | **S/-3.50** | `S/84.95` |
| `2026-11-08` | Houston Rockets @ Phoenix Suns (HOU @ PHX) | **Devin Booker** | AST | UNDER | `7.5` | `1.90` | `3.0` | ✅ WON | **S/+3.15** | `S/88.45` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Stephen Curry** | PTS | UNDER | `27.5` | `1.90` | `41.0` | ❌ LOST | **S/-3.50** | `S/85.30` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Stephen Curry** | PRA | UNDER | `37.5` | `1.90` | `53.0` | ❌ LOST | **S/-3.50** | `S/88.80` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Draymond Green** | REB | UNDER | `7.5` | `1.90` | `6.0` | ✅ WON | **S/+3.15** | `S/92.30` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Draymond Green** | PRA | UNDER | `22.5` | `1.90` | `21.0` | ✅ WON | **S/+3.15** | `S/89.15` |
| `2026-11-08` | Orlando Magic @ Golden State Warriors (ORL @ GSW) | **Draymond Green** | AST | UNDER | `6.5` | `1.90` | `13.0` | ❌ LOST | **S/-3.50** | `S/86.00` |
| `2026-11-08` | Washington Wizards @ Oklahoma City Thunder (WAS @ OKC) | **Shai Gilgeous-Alexander** | PTS | OVER | `30.5` | `1.90` | `30.0` | ❌ LOST | **S/-3.50** | `S/89.50` |
| `2026-11-08` | Washington Wizards @ Oklahoma City Thunder (WAS @ OKC) | **Shai Gilgeous-Alexander** | PRA | OVER | `42.5` | `1.90` | `41.0` | ❌ LOST | **S/-3.50** | `S/93.00` |
