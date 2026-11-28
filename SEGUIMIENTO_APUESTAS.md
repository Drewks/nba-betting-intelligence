# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)

- **Última actualización**: `2026-11-28 10:52 (Hora Perú UTC-5)` (`2026-11-28T15:52:51Z`)
- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/96.80 PEN`** (`-3.20 PEN`)
- **ROI Actual**: `-5.74%` | **Yield Actual**: `-5.74%` | **CLV (vs cierre sin margen)**: `-2.60%` (N=36) | **Max Drawdown**: `9.00%` | **Apuestas en espera**: `0` (`S/0.00 PEN` reservados)
- **Motor Predictivo Activo**: `Ensemble (Elo + Ridge + LightGBM + Monte Carlo) anclado 70% al mercado sin margen`. Sin ventaja demostrada frente al mercado.
- **Modo de Apuesta Activo**: `Kelly Fraccional (25%) | Máx. 3 selecciones/jornada | EV >= 2.0%` | Solo cuotas observadas (nunca estimadas).
- **Alcance de métricas**: solo apuestas hechas con cuotas observadas en un mercado real (`v_observed_simulated_bets`).
- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)
- **Sistema de Aviso Automático**: `ACTIVO` *(aviso cuando se cumplan los criterios; cumplirlos solo habilita una revisión humana extendida, nunca dinero real automático)*.

---

## 🚦 1. Semáforo de Madurez de 8 Criterios y Graduación en 2 Niveles

### Estado Global: **🔴 EN FASE DE CALIBRACIÓN Y PAPER TRADING (3/8 CRITERIOS EN VERDE — NO USAR DINERO REAL AÚN)**
- **Progreso Muestra Total (Nivel 1)**: `[██░░░░░░░░░░░░░░░░░░] 40 / 500 apuestas (8.0%)` — *Faltan **460** apuestas.*
- **Progreso Muestra 100% En Vivo (ESPN/OddsAPI)**: `[████░░░░░░░░░░░░░░░░] 40 / 200 en vivo (20.0%)` — *Tienes **0** apuestas reales en espera hoy.*

Para blindar tu capital contra rachas de suerte, el sistema evalúa **8 criterios cuantitativos estrictos** divididos en **2 niveles de graduación**:

| # | Criterio Cuantitativo de Auditoría | Estado Hoy | Valor Actual | Meta Nivel 1 (Piloto Micro-Banca 25%) | Meta Nivel 2 (Banca Completa 100%) |
| :-: | :--- | :---: | :--- | :--- | :--- |
| 1 | **Muestra total de apuestas liquidadas** | 🔴 PENDIENTE | `40 apuestas` | **>= 500 apuestas** | **>= 1,000 apuestas** |
| 2 | **Muestra 100% En Vivo (Pre-Partido Real)** | 🔴 PENDIENTE | `40 liquidadas (0 activas)` | **>= 200 en vivo** | **>= 500 en vivo** |
| 3 | **No peor que el Mercado sin margen ni que el Baseline (Brier & LogLoss)** | ✅ VERDE | `Modelo 0.2249 vs Mercado 0.2281 (N=10) | Baseline 0.2729` | **Modelo <= Mercado** | **Modelo <= Mercado** |
| 4 | **Error de Calibración por Tramos (ECE)** | 🟡 AJUSTANDO | `ECE 0.3397 (33.97%)` | **ECE <= 5.0%** | **ECE <= 3.5%** |
| 5 | **Rentabilidad Neta Positiva (ROI y Yield)** | 🔴 PENDIENTE | `ROI -5.74% / Yield -5.74%` | **ROI >= +2.0% / Yield >= +1.5%** | **ROI >= +3.5% (ambos mercados > 0%)** |
| 6 | **Control de Caída Máxima (Max Drawdown)** | ✅ VERDE | `Total 9.00% (En vivo: 9.00%)` | **MaxDD <= 15.0%** | **MaxDD <= 15.0%** |
| 7 | **Exclusión Estadística del Azar (Bootstrap CI)** | 🔴 PENDIENTE | `IC90 [-31.6%, +21.8%] / IC95 [-36.3%, +26.2%]` | **IC 90% lím. inf. > 0%** | **IC 95% lím. inf. > 0%** |
| 8 | **Cero Fuga Temporal, historial íntegro y ledger reconciliado** | ✅ VERDE | `Sin violaciones` | **0 violaciones** | **0 violaciones** |

> **Nota**: cumplir los criterios NO autoriza dinero real. Según AGENTS.md, el sistema opera exclusivamente en paper trading; los niveles solo habilitan una revisión humana extendida.

---

## 🏀 2. Mis Apuestas NBA Reales (ESPN / TheOddsAPI Line Shopping)

Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido, con vigilancia de movimiento en contra `CLV < -5.0%`):

| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Mejor Cuota (Casa) | Prob. Modelo | EV (%) | CLV (%) | Stake | Estado | Resultado / Ganancia |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |
| `2026-11-27 20:30` | **Memphis Grizzlies @ Minnesota Timberwolves (MEM @ MIN)** | Ganador (Moneyline) | **Gana Minnesota Timberwolves (MIN)** | **1.633** *(Pinnacle [LIVE_API])* | 64.0% | `+4.5%` | `-5.50%` | S/1.74 | ❌ PERDIDA | S/-1.74 (HOME 109 - AWAY 114 (Total: 223)) |
| `2026-11-25 22:00` | **Sacramento Kings @ Golden State Warriors (SAC @ GSW)** | Ganador (Moneyline) | **Gana Golden State Warriors (GSW)** | **1.448** *(Pinnacle [LIVE_API])* | 70.7% | `+2.3%` | `+8.22%` | S/1.27 | ✅ GANADA | S/+0.57 (HOME 129 - AWAY 110 (Total: 239)) |
| `2026-11-23 19:00` | **Memphis Grizzlies @ Charlotte Hornets (MEM @ CHA)** | Ganador (Moneyline) | **Gana Charlotte Hornets (CHA)** | **2.300** *(Pinnacle [LIVE_API])* | 45.8% | `+5.3%` | `-4.08%` | S/1.01 | ❌ PERDIDA | S/-1.01 (HOME 111 - AWAY 117 (Total: 228)) |
| `2026-11-21 20:00` | **Memphis Grizzlies @ Minnesota Timberwolves (MEM @ MIN)** | Ganador (Moneyline) | **Gana Minnesota Timberwolves (MIN)** | **1.448** *(Pinnacle [LIVE_API])* | 71.7% | `+3.9%` | `-3.17%` | S/2.13 | ✅ GANADA | S/+0.96 (HOME 104 - AWAY 95 (Total: 199)) |
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

- Actualmente no hay apuestas pendientes en espera de inicio.

### 📋 2.B Cartelera Completa de Próximos Partidos: Cuotas, Estadísticas a Tomar en Cuenta y Veredicto

| Hora (UTC) | Partido | Cuotas Ganador (`Local / Visita`) | Proyección Modelo (`Margen / Total`) | Estadísticas Clave (`Elo`, `NetRtg`, `Descanso`) | ¿Qué Hace el Bot y Por Qué? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `2026-11-28T22:00:00Z` | **Washington Wizards @ Orlando Magic (WAS @ ORL)** | Local **2.540** / Visita **1.650** | **Margen -0.4 pts** (Local `46.6%`) · Total **218.8 pts** | Elo `1332.4/1471.0` · Net `-4.4` · Pace `98.0` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _HOME: EV -0.05% <= threshold 2.00%; HOME: EV -0.10% <= threshold 2.00%_ |
| `2026-11-28T23:00:00Z` | **Charlotte Hornets @ Brooklyn Nets (CHA @ BKN)** | Local **1.490** / Visita **3.250** | **Margen +8.4 pts** (Local `76.2%`) · Total **215.7 pts** | Elo `1449.0/1299.7` · Net `+4.0` · Pace `99.0` · Desc `+1d` | **SIN APUESTA (NO_BET)** — _HOME: EV 0.07% <= threshold 2.00%; HOME: EV -0.35% <= threshold 2.00%_ |
| `2026-11-29T01:00:00Z` | **Chicago Bulls @ Indiana Pacers (CHI @ IND)** | Local **1.840** / Visita **2.320** | **Margen +2.1 pts** (Local `59.7%`) · Total **235.3 pts** | Elo `1410.8/1347.9` · Net `+1.7` · Pace `98.7` · Desc `+2d` | **SIN APUESTA (NO_BET)** — _HOME: EV 0.32% <= threshold 2.00%; HOME: EV -0.57% <= threshold 2.00%_ |
| `2026-11-29T01:00:00Z` | **Milwaukee Bucks @ Oklahoma City Thunder (MIL @ OKC)** | Local **5.600** / Visita **1.220** | **Margen -11.2 pts** (Local `18.0%`) · Total **227.7 pts** | Elo `1313.9/1613.5` · Net `-10.6` · Pace `99.3` · Desc `-2d` | **SIN APUESTA (NO_BET)** — _UNDER: EV -2.27% <= threshold 2.00%; OVER: EV -3.37% <= threshold 2.00%_ |
| `2026-11-29T01:30:00Z` | **Houston Rockets @ Philadelphia 76ers (HOU @ PHI)** | Local **1.230** / Visita **5.550** | **Margen +11.5 pts** (Local `81.3%`) · Total **227.3 pts** | Elo `1629.3/1563.5` · Net `+5.5` · Pace `100.3` · Desc `+2d` | **SIN APUESTA (NO_BET)** — _OVER: EV 0.95% <= threshold 2.00%; OVER: EV -0.82% <= threshold 2.00%_ |
| `2026-11-29T20:30:00Z` | **Cleveland Cavaliers @ Miami Heat (CLE @ MIA)** | ⏳ *Sin cuotas publicadas* | **Margen +1.5 pts** (Local `56.9%`) · Total **238.8 pts** | Elo `1537.3/1546.0` · Net `-1.5` · Pace `100.7` · Desc `+2d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-29T21:00:00Z` | **Memphis Grizzlies @ Los Angeles Lakers (MEM @ LAL)** | ⏳ *Sin cuotas publicadas* | **Margen -2.3 pts** (Local `41.6%`) · Total **228.7 pts** | Elo `1513.6/1619.0` · Net `-1.1` · Pace `98.7` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-29T21:00:00Z` | **San Antonio Spurs @ Boston Celtics (SAS @ BOS)** | ⏳ *Sin cuotas publicadas* | **Margen +6.7 pts** (Local `71.0%`) · Total **211.6 pts** | Elo `1711.1/1634.4` · Net `+1.5` · Pace `97.2` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-29T22:00:00Z` | **Utah Jazz @ Phoenix Suns (UTA @ PHX)** | ⏳ *Sin cuotas publicadas* | **Margen -5.4 pts** (Local `32.5%`) · Total **223.8 pts** | Elo `1299.6/1520.6` · Net `-8.2` · Pace `97.9` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-29T23:00:00Z` | **Detroit Pistons @ Orlando Magic (DET @ ORL)** | ⏳ *Sin cuotas publicadas* | **Margen +6.7 pts** (Local `71.8%`) · Total **212.7 pts** | Elo `1639.3/1471.0` · Net `+5.0` · Pace `97.9` · Desc `-3d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-29T23:00:00Z` | **New York Knicks @ Atlanta Hawks (NYK @ ATL)** | ⏳ *Sin cuotas publicadas* | **Margen +5.4 pts** (Local `68.6%`) · Total **216.1 pts** | Elo `1678.3/1547.6` · Net `+4.9` · Pace `97.4` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-29T23:00:00Z` | **Toronto Raptors @ Denver Nuggets (TOR @ DEN)** | ⏳ *Sin cuotas publicadas* | **Margen -1.2 pts** (Local `46.2%`) · Total **223.5 pts** | Elo `1489.2/1567.5` · Net `-4.0` · Pace `98.9` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-29T23:00:00Z` | **Portland Trail Blazers @ New Orleans Pelicans (POR @ NOP)** | ⏳ *Sin cuotas publicadas* | **Margen +10.9 pts** (Local `81.7%`) · Total **230.9 pts** | Elo `1607.2/1375.5` · Net `+6.3` · Pace `99.6` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-30T01:30:00Z` | **Golden State Warriors @ LA Clippers (GSW @ LAC)** | ⏳ *Sin cuotas publicadas* | **Margen +2.6 pts** (Local `59.8%`) · Total **220.8 pts** | Elo `1461.0/1420.4` · Net `+0.2` · Pace `98.1` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-30T02:00:00Z` | **Sacramento Kings @ Minnesota Timberwolves (SAC @ MIN)** | ⏳ *Sin cuotas publicadas* | **Margen -13.6 pts** (Local `14.7%`) · Total **224.0 pts** | Elo `1292.6/1624.7` · Net `-12.4` · Pace `98.2` · Desc `+2d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |

---

## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)

| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |
| `BET_20261128_4D53638C` | `2026-11-28` | `Memphis Grizzlies @ Minnesota Timberwolves (MEM @ MIN)` | Ganador (Moneyline) | **Gana Minnesota Timberwolves (MIN)** | 1.633 | 64.0% | `+4.5%` | ❌ LOST | **S/-1.74** | `S/96.80` |
| `BET_20261126_9755EFE2` | `2026-11-26` | `Sacramento Kings @ Golden State Warriors (SAC @ GSW)` | Ganador (Moneyline) | **Gana Golden State Warriors (GSW)** | 1.448 | 70.7% | `+2.3%` | ✅ WON | **S/+0.57** | `S/98.54` |
| `BET_20261124_DC5A31F2` | `2026-11-24` | `Memphis Grizzlies @ Charlotte Hornets (MEM @ CHA)` | Ganador (Moneyline) | **Gana Charlotte Hornets (CHA)** | 2.300 | 45.8% | `+5.3%` | ❌ LOST | **S/-1.01** | `S/97.97` |
| `BET_20261122_082DCCDC` | `2026-11-22` | `Memphis Grizzlies @ Minnesota Timberwolves (MEM @ MIN)` | Ganador (Moneyline) | **Gana Minnesota Timberwolves (MIN)** | 1.448 | 71.7% | `+3.9%` | ✅ WON | **S/+0.96** | `S/98.98` |
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
