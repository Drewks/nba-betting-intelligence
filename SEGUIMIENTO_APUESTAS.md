# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)

- **Última actualización**: `2026-11-18 11:02 (Hora Perú UTC-5)` (`2026-11-18T16:02:02Z`)
- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/97.91 PEN`** (`-2.09 PEN`)
- **ROI Actual**: `-4.65%` | **Yield Actual**: `-4.50%` | **CLV (vs cierre sin margen)**: `-3.08%` (N=29) | **Max Drawdown**: `9.00%` | **Apuestas en espera**: `1` (`S/1.47 PEN` reservados)
- **Motor Predictivo Activo**: `Ensemble (Elo + Ridge + LightGBM + Monte Carlo) anclado 70% al mercado sin margen`. Sin ventaja demostrada frente al mercado.
- **Modo de Apuesta Activo**: `Kelly Fraccional (25%) | Máx. 3 selecciones/jornada | EV >= 2.0%` | Solo cuotas observadas (nunca estimadas).
- **Alcance de métricas**: solo apuestas hechas con cuotas observadas en un mercado real (`v_observed_simulated_bets`).
- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)
- **Sistema de Aviso Automático**: `ACTIVO` *(aviso cuando se cumplan los criterios; cumplirlos solo habilita una revisión humana extendida, nunca dinero real automático)*.

---

## 🚦 1. Semáforo de Madurez de 8 Criterios y Graduación en 2 Niveles

### Estado Global: **🔴 EN FASE DE CALIBRACIÓN Y PAPER TRADING (2/8 CRITERIOS EN VERDE — NO USAR DINERO REAL AÚN)**
- **Progreso Muestra Total (Nivel 1)**: `[█░░░░░░░░░░░░░░░░░░░] 33 / 500 apuestas (6.6%)` — *Faltan **467** apuestas.*
- **Progreso Muestra 100% En Vivo (ESPN/OddsAPI)**: `[███░░░░░░░░░░░░░░░░░] 33 / 200 en vivo (16.5%)` — *Tienes **1** apuestas reales en espera hoy.*

Para blindar tu capital contra rachas de suerte, el sistema evalúa **8 criterios cuantitativos estrictos** divididos en **2 niveles de graduación**:

| # | Criterio Cuantitativo de Auditoría | Estado Hoy | Valor Actual | Meta Nivel 1 (Piloto Micro-Banca 25%) | Meta Nivel 2 (Banca Completa 100%) |
| :-: | :--- | :---: | :--- | :--- | :--- |
| 1 | **Muestra total de apuestas liquidadas** | 🔴 PENDIENTE | `33 apuestas` | **>= 500 apuestas** | **>= 1,000 apuestas** |
| 2 | **Muestra 100% En Vivo (Pre-Partido Real)** | 🔴 PENDIENTE | `33 liquidadas (1 activas)` | **>= 200 en vivo** | **>= 500 en vivo** |
| 3 | **No peor que el Mercado sin margen ni que el Baseline (Brier & LogLoss)** | 🔴 PENDIENTE | `Modelo 0.2368 vs Mercado 0.2381 (N=20) | Baseline 0.2472` | **Modelo <= Mercado** | **Modelo <= Mercado** |
| 4 | **Error de Calibración por Tramos (ECE)** | 🟡 AJUSTANDO | `ECE 0.2665 (26.65%)` | **ECE <= 5.0%** | **ECE <= 3.5%** |
| 5 | **Rentabilidad Neta Positiva (ROI y Yield)** | 🔴 PENDIENTE | `ROI -4.65% / Yield -4.50%` | **ROI >= +2.0% / Yield >= +1.5%** | **ROI >= +3.5% (ambos mercados > 0%)** |
| 6 | **Control de Caída Máxima (Max Drawdown)** | ✅ VERDE | `Total 9.00% (En vivo: 9.00%)` | **MaxDD <= 15.0%** | **MaxDD <= 15.0%** |
| 7 | **Exclusión Estadística del Azar (Bootstrap CI)** | 🔴 PENDIENTE | `IC90 [-33.8%, +26.3%] / IC95 [-40.2%, +30.6%]` | **IC 90% lím. inf. > 0%** | **IC 95% lím. inf. > 0%** |
| 8 | **Cero Fuga Temporal, historial íntegro y ledger reconciliado** | ✅ VERDE | `Sin violaciones` | **0 violaciones** | **0 violaciones** |

> **Nota**: cumplir los criterios NO autoriza dinero real. Según AGENTS.md, el sistema opera exclusivamente en paper trading; los niveles solo habilitan una revisión humana extendida.

---

## 🏀 2. Mis Apuestas NBA Reales (ESPN / Line Shopping 25 Casas)

> ### 🏆 PICK ESTRELLA DEL DÍA (`2026-11-18` — 1 Solo Pick: Mayor Probabilidad de Acierto)
> - **Partido**: **Houston Rockets @ Indiana Pacers (HOU @ IND)** (`2026-11-18 19:00 Hora Perú`)
> - **Pick Más Probable**: 🎯 **Gana Houston Rockets (HOU)** (Ganador (Moneyline)) @ **`1.410`** *(Pinnacle [LIVE_API])*
> - **Probabilidad de Acierto (Modelo Calibrado)**: 🔥 **`72.7%`** | **EV**: `+2.5%`
> - **Envío diario a tu correo**: `ACTIVO` *(1 solo correo diario vía GitHub Notification `@Drewks` con la selección de mayor EV entre las apuestas pendientes con cuotas observadas)*.

Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido, con vigilancia de movimiento en contra `CLV < -5.0%`):

| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Mejor Cuota (Casa) | Prob. Modelo | EV (%) | CLV (%) | Stake | Estado | Resultado / Ganancia |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |
| `2026-11-18 19:00` | **Houston Rockets @ Indiana Pacers (HOU @ IND)** | Ganador (Moneyline) | **Gana Houston Rockets (HOU)** | **1.410** *(Pinnacle [LIVE_API])* | 72.7% | `+2.5%` | — | S/1.47 | ⏳ PENDIENTE | Esperando final del partido |
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

#### 🎯 **Indiana Pacers @ Houston Rockets (IND @ HOU)** — `2026-11-19T00:00:00Z UTC`
- **¿Qué está apostando el bot?**: **Victoria Houston Rockets** en *Pinnacle [LIVE_API]*
- **Cuota Tomada vs Cuota Justa**: **`1.410`** vs Cuota Justa **`1.380`** *(Ventaja Matemática EV: `+2.50%`)*
- **Stake y Ganancia Potencial**: Stake **`S/1.47 PEN`** → Ganancia neta potencial: **`+S/0.60 PEN`**
- **Probabilidades**: Modelo Calibrado **`72.7%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `-6.8 pts` | Total esperado **`222.6 pts`** *(Intervalo Simulación 80% [Q10–Q90]: `200 – 246 pts` | Prob. Prórroga: `7.6%` | Prob. Paliza: `13.5%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `IND 1360.5` vs `HOU 1621.6` | **Eficiencia Neta (Off/Def)**: `IND (111.8/116.1)` vs `HOU (114.1/109.4)` (`Dif: -9.0 pts/100`)
  - **Ritmo (Pace)**: `98.7 posesiones` | **Descanso**: Dif `+2d` | **Viaje Geodésico**: `Dif. +443 millas`
- **Por qué apostó el modelo**: _El modelo proyecta una probabilidad de éxito del 72.7% frente a una cuota de 1.41 (valor esperado positivo del +2.5% con stake calculado de S/ 1.47 PEN)._

### 📋 2.B Cartelera Completa de Próximos Partidos: Cuotas, Estadísticas a Tomar en Cuenta y Veredicto

| Hora (UTC) | Partido | Cuotas Ganador (`Local / Visita`) | Proyección Modelo (`Margen / Total`) | Estadísticas Clave (`Elo`, `NetRtg`, `Descanso`) | ¿Qué Hace el Bot y Por Qué? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `2026-11-19T00:00:00Z` | **Cleveland Cavaliers @ Memphis Grizzlies (CLE @ MEM)** | Local **1.570** / Visita **2.820** | **Margen +4.6 pts** (Local `68.3%`) · Total **234.3 pts** | Elo `1565.7/1466.3` · Net `+1.6` · Pace `100.5` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _HOME: EV 0.90% <= threshold 2.00%; UNDER: EV -0.62% <= threshold 2.00%_ |
| `2026-11-19T00:00:00Z` | **Indiana Pacers @ Houston Rockets (IND @ HOU)** | Local **3.600** / Visita **1.440** | **Margen -6.8 pts** (Local `26.2%`) · Total **222.6 pts** | Elo `1360.5/1621.6` · Net `-9.0` · Pace `98.7` · Desc `+2d` | **APUESTA DETECTADA: Victoria Houston Rockets @ 1.41 en Pinnacle [LIVE_API]** — _El modelo proyecta una probabilidad de éxito del 72.7% frente a una cuota de 1.41 (valor esperado positivo del +2.5% con stake calculado de S/ 1.47 PEN)._ |
| `2026-11-19T00:00:00Z` | **Miami Heat @ Milwaukee Bucks (MIA @ MIL)** | Local **1.170** / Visita **6.800** | **Margen +10.3 pts** (Local `81.4%`) · Total **232.7 pts** | Elo `1532.8/1324.2` · Net `+9.4` · Pace `99.7` · Desc `-1d` | **SIN APUESTA (NO_BET)** — _UNDER: EV 1.28% <= threshold 2.00%; AWAY: EV 0.06% <= threshold 2.00%_ |
| `2026-11-19T00:00:00Z` | **Orlando Magic @ Philadelphia 76ers (ORL @ PHI)** | Local **2.140** / Visita **1.940** | **Margen -0.5 pts** (Local `49.3%`) · Total **222.0 pts** | Elo `1507.5/1552.6` · Net `-2.5` · Pace `99.5` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _HOME: EV 1.50% <= threshold 2.00%; HOME: EV -0.87% <= threshold 2.00%_ |
| `2026-11-19T00:30:00Z` | **Brooklyn Nets @ Chicago Bulls (BKN @ CHI)** | Local **1.760** / Visita **2.300** | **Margen +0.5 pts** (Local `51.5%`) · Total **234.9 pts** | Elo `1323.1/1379.4` · Net `-1.3` · Pace `101.3` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _UNDER: Fractional Kelly stake below S/1.00 (no material edge at 1.910).; AWAY: EV 0.98% <= threshold 2.00%_ |
| `2026-11-19T00:30:00Z` | **Toronto Raptors @ Washington Wizards (TOR @ WAS)** | Local **1.440** / Visita **3.500** | **Margen +7.8 pts** (Local `76.5%`) · Total **230.2 pts** | Elo `1494.1/1299.3` · Net `+6.9` · Pace `100.4` · Desc `-1d` | **SIN APUESTA (NO_BET)** — _OVER: EV 1.09% <= threshold 2.00%; HOME: EV 0.43% <= threshold 2.00%_ |
| `2026-11-19T01:00:00Z` | **New Orleans Pelicans @ Detroit Pistons (NOP @ DET)** | Local **3.450** / Visita **1.420** | **Margen -5.4 pts** (Local `29.7%`) · Total **227.4 pts** | Elo `1385.3/1639.6` · Net `-8.1` · Pace `100.2` · Desc `+1d` | **SIN APUESTA (NO_BET)** — _HOME: EV 0.04% <= threshold 2.00%; HOME: EV -0.13% <= threshold 2.00%_ |
| `2026-11-19T01:00:00Z` | **Oklahoma City Thunder @ Atlanta Hawks (OKC @ ATL)** | Local **1.430** / Visita **3.350** | **Margen +7.1 pts** (Local `74.1%`) · Total **223.4 pts** | Elo `1652.2/1512.0` · Net `+5.5` · Pace `99.2` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _UNDER: Fractional Kelly stake below S/1.00 (no material edge at 2.010).; HOME: EV 0.52% <= threshold 2.00%_ |
| `2026-11-19T01:00:00Z` | **Dallas Mavericks @ Golden State Warriors (DAL @ GSW)** | Local **1.560** / Visita **2.980** | **Margen +0.1 pts** (Local `49.1%`) · Total **225.8 pts** | Elo `1423.0/1494.1` · Net `-0.3` · Pace `98.7` · Desc `+2d` | **SIN APUESTA (NO_BET)** — _AWAY: Matchday cap of 1 moneyline pick(s) reached (70/30 hybrid allocation); AWAY: Venn-Abers conformal prediction interval width 0.300 > 0.22; epistemic uncertainty too high._ |
| `2026-11-19T02:30:00Z` | **Denver Nuggets @ Boston Celtics (DEN @ BOS)** | Local **2.280** / Visita **1.780** | **Margen -0.7 pts** (Local `48.4%`) · Total **218.3 pts** | Elo `1563.2/1652.1` · Net `-4.2` · Pace `98.0` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _HOME: EV 1.50% <= threshold 2.00%; HOME: EV 0.58% <= threshold 2.00%_ |
| `2026-11-19T03:00:00Z` | **Los Angeles Lakers @ Utah Jazz (LAL @ UTA)** | Local **1.270** / Visita **4.600** | **Margen +15.6 pts** (Local `91.1%`) · Total **227.9 pts** | Elo `1637.0/1300.4` · Net `+13.0` · Pace `99.5` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _HOME: Venn-Abers conformal prediction interval width 0.293 > 0.22; epistemic uncertainty too high.; HOME: Venn-Abers conformal prediction interval width 0.286 > 0.22; epistemic uncertainty too high._ |
| `2026-11-19T03:00:00Z` | **Sacramento Kings @ Phoenix Suns (SAC @ PHX)** | Local **3.300** / Visita **1.460** | **Margen -5.6 pts** (Local `31.0%`) · Total **228.0 pts** | Elo `1306.1/1514.0` · Net `-8.5` · Pace `100.1` · Desc `+1d` | **SIN APUESTA (NO_BET)** — _HOME: EV -1.14% <= threshold 2.00%; OVER: EV -1.80% <= threshold 2.00%_ |
| `2026-11-20T01:00:00Z` | **Memphis Grizzlies @ Golden State Warriors (MEM @ GSW)** | ⏳ *Sin cuotas publicadas* | **Margen +2.7 pts** (Local `57.2%`) · Total **228.6 pts** | Elo `1466.3/1494.1` · Net `+2.3` · Pace `99.2` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-20T01:00:00Z` | **Milwaukee Bucks @ Portland Trail Blazers (MIL @ POR)** | ⏳ *Sin cuotas publicadas* | **Margen -6.6 pts** (Local `27.4%`) · Total **223.3 pts** | Elo `1324.2/1570.6` · Net `-9.1` · Pace `99.3` · Desc `+2d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-20T01:00:00Z` | **Minnesota Timberwolves @ New York Knicks (MIN @ NYK)** | ⏳ *Sin cuotas publicadas* | **Margen +0.5 pts** (Local `52.1%`) · Total **212.0 pts** | Elo `1622.4/1669.0` · Net `-1.4` · Pace `97.6` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |
| `2026-11-20T01:00:00Z` | **San Antonio Spurs @ LA Clippers (SAS @ LAC)** | ⏳ *Sin cuotas publicadas* | **Margen +11.8 pts** (Local `85.4%`) · Total **221.9 pts** | Elo `1708.4/1450.5` · Net `+9.4` · Pace `99.4` · Desc `+0d` | **SIN APUESTA (NO_BET)** — _Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado (>= 2.0% EV) para justificar una entrada segura._ |

---

## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)

| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |
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
| `BET_20261103_EF0858D0` | `2026-11-03` | `New Orleans Pelicans @ Memphis Grizzlies (NOP @ MEM)` | Ganador (Moneyline) | **Gana New Orleans Pelicans (NOP)** | 2.900 | 36.3% | `+5.3%` | ✅ WON | **S/+1.90** | `S/98.44` |
| `BET_20261103_E59224AE` | `2026-11-03` | `Washington Wizards @ Orlando Magic (WAS @ ORL)` | Total Puntos (Over/Under) | **OVER 225.5 (Washington Wizards @ Orlando Magic)** | 1.990 | 51.8% | `+3.0%` | ❌ LOST | **S/-1.13** | `S/96.54` |
| `BET_20261102_555C3423` | `2026-11-02` | `Toronto Raptors @ Los Angeles Lakers (TOR @ LAL)` | Ganador (Moneyline) | **Gana Toronto Raptors (TOR)** | 2.670 | 39.2% | `+4.7%` | ❌ LOST | **S/-1.00** | `S/97.67` |

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
