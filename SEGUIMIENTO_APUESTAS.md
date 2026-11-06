# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)

- **Última actualización**: `2026-11-06 09:23 (Hora Perú UTC-5)` (`2026-11-06T14:23:24Z`)
- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/97.72 PEN`** (`-2.28 PEN`)
- **ROI Actual**: `-9.13%` | **Yield Actual**: `-7.61%` | **CLV Promedio**: `+1.17%` | **Max Drawdown**: `6.09%` | **Apuestas en espera**: `3` (`S/5.00 PEN` reservados)
- **Motor Predictivo Activo**: `Modelo F+G (ML LightGBM/Ridge + 10,000 Simulaciones Monte Carlo de Posesiones con Overtime, Fouling y Blowout + Conformal Prediction)`.
- **Modo de Apuesta Activo**: `Kelly-Conviccion Proporcional a la Ventaja (S/1.00 a S/6.00 PEN)` *(Modulado por EV real contra casas sharp, Guardian Activo de CLV que reduce exposicion ante movimientos adversos de linea, y Limite de Anti-Correlacion de 1 apuesta por partido)*.
- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)
- **Sistema de Aviso Automático (Doble Nivel)**: `ACTIVO` *(Recibirás un correo automático vía GitHub Issue `@Drewks` al desbloquear el **Nivel 1: Micro-Banca** y un segundo correo al desbloquear el **Nivel 2: Banca Completa**)*.

---

## 🚦 1. Semáforo de Madurez de 8 Criterios y Graduación en 2 Niveles

### Estado Global: **🔴 EN FASE DE CALIBRACIÓN Y PAPER TRADING (3/8 CRITERIOS EN VERDE — NO USAR DINERO REAL AÚN)**
- **Progreso Muestra Total (Nivel 1)**: `[█░░░░░░░░░░░░░░░░░░░] 21 / 500 apuestas (4.2%)` — *Faltan **479** apuestas.*
- **Progreso Muestra 100% En Vivo (ESPN/OddsAPI)**: `[██░░░░░░░░░░░░░░░░░░] 21 / 200 en vivo (10.5%)` — *Tienes **3** apuestas reales en espera hoy.*

Para blindar tu capital contra rachas de suerte, el sistema evalúa **8 criterios cuantitativos estrictos** divididos en **2 niveles de graduación**:

| # | Criterio Cuantitativo de Auditoría | Estado Hoy | Valor Actual | Meta Nivel 1 (Piloto Micro-Banca 25%) | Meta Nivel 2 (Banca Completa 100%) |
| :-: | :--- | :---: | :--- | :--- | :--- |
| 1 | **Muestra total de apuestas liquidadas** | 🔴 PENDIENTE | `21 apuestas` | **>= 500 apuestas** | **>= 1,000 apuestas** |
| 2 | **Muestra 100% En Vivo (Pre-Partido Real)** | 🔴 PENDIENTE | `21 liquidadas (3 activas)` | **>= 200 en vivo** | **>= 500 en vivo** |
| 3 | **Calibración mejor que el Baseline (Brier & LogLoss)** | ✅ VERDE | `Brier 0.2262 vs 0.2422` | **Brier/LogLoss <= Base** | **Brier/LogLoss <= Base** |
| 4 | **Error de Calibración por Tramos (ECE)** | 🟡 AJUSTANDO | `ECE 0.1625 (16.25%)` | **ECE <= 5.0%** | **ECE <= 3.5%** |
| 5 | **Rentabilidad Neta Positiva (ROI y Yield)** | 🔴 PENDIENTE | `ROI -9.13% / Yield -7.61%` | **ROI >= +2.0% / Yield >= +1.5%** | **ROI >= +3.5% (ambos mercados > 0%)** |
| 6 | **Control de Caída Máxima (Max Drawdown)** | ✅ VERDE | `Total 6.09% (En vivo: 6.09%)` | **MaxDD <= 15.0%** | **MaxDD <= 15.0%** |
| 7 | **Exclusión Estadística del Azar (Bootstrap CI)** | 🔴 PENDIENTE | `IC90 [-37.7%, +22.4%] / IC95 [-44.5%, +28.8%]` | **IC 90% lím. inf. > 0%** | **IC 95% lím. inf. > 0%** |
| 8 | **Cero Fuga Temporal (Anti-Leakage) y SQLite** | ✅ VERDE | `0 violaciones / 100% íntegro` | **0 violaciones** | **0 violaciones** |

> **🔔 Doble aviso automático a tu correo**: No necesitas vigilar esta tabla a diario. Cuando las 8 filas lleguen a **✅ VERDE** en el **Nivel 1**, recibirás un correo de GitHub (`@Drewks`) autorizando pruebas con micro-banca (25% de tu stake). Cuando alcance el **Nivel 2** (`1,000` apuestas + `IC 95% > 0%`), recibirás el segundo correo de certificación completa.

---

## 🏀 2. Mis Apuestas NBA Reales (ESPN / Line Shopping 25 Casas)

> ### 🏆 PICK ESTRELLA DEL DÍA (`2026-11-06` — 1 Solo Pick: Mayor Probabilidad de Acierto)
> - **Partido**: **OKC @ MEM** (`2026-11-06 20:00 Hora Perú`)
> - **Pick Más Probable**: 🎯 **AWAY (OKC gana)** (Ganador (Moneyline)) @ **`1.606`** *(DraftKings)*
> - **Probabilidad de Acierto (Modelo Calibrado)**: 🔥 **`63.5%`** | **EV**: `+2.0%`
> - **Envío diario a tu correo**: `ACTIVO` *(1 solo correo diario vía GitHub Notification `@Drewks` con la selección de mayor probabilidad de acierto y sin alerta CLV)*.

Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido, con vigilancia de movimiento en contra `CLV < -5.0%`):

| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Mejor Cuota (Casa) | Prob. Modelo | EV (%) | CLV (%) | Stake | Estado | Resultado / Ganancia |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |
| `2026-11-06 22:00` | **SAS @ SAC** | Total Puntos (Over/Under) | **UNDER 228.5** | **1.930** *(LowVig.ag)* | 53.2% | `+2.8%` | — | S/1.68 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-06 20:00` | **OKC @ MEM** | Ganador (Moneyline) | **AWAY (OKC gana)** | **1.606** *(DraftKings)* | 63.5% | `+2.0%` | — | S/1.96 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-06 19:30` | **PHI @ CLE** | Ganador (Moneyline) | **HOME (CLE gana)** | **2.210** *(1xBet)* | 47.9% | `+5.9%` | — | S/1.36 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-11-05 21:00` | **ORL @ PHX** | Ganador (Moneyline) | **HOME (PHX gana)** | **1.910** *(Matchbook)* | 53.5% | `+2.2%` | — | S/1.39 | ✅ GANADA | S/+1.26 (HOME 117 - AWAY 104 (Total: 221)) |
| `2026-11-04 21:00` | **TOR @ DEN** | Ganador (Moneyline) | **AWAY (TOR gana)** | **2.900** *(Bovada)* | 37.2% | `+7.9%` | — | S/1.10 | ❌ PERDIDA | S/-1.10 (HOME 128 - AWAY 109 (Total: 237)) |
| `2026-11-04 20:00` | **CLE @ OKC** | Ganador (Moneyline) | **HOME (OKC gana)** | **1.770** *(FanDuel)* | 58.5% | `+3.6%` | — | S/2.19 | ✅ GANADA | S/+1.69 (HOME 124 - AWAY 116 (Total: 240)) |
| `2026-11-04 19:00` | **PHI @ DET** | Ganador (Moneyline) | **HOME (DET gana)** | **1.810** *(Coolbet)* | 56.6% | `+2.5%` | — | S/1.57 | ❌ PERDIDA | S/-1.57 (HOME 106 - AWAY 112 (Total: 218)) |
| `2026-11-02 20:30` | **BOS @ HOU** | Total Puntos (Over/Under) | **OVER 219.5** | **1.990** *(1xBet)* | 51.3% | `+2.1%` | — | S/1.00 | ❌ PERDIDA | S/-1.00 (HOME 109 - AWAY 93 (Total: 202)) |
| `2026-11-02 20:00` | **NOP @ MEM** | Ganador (Moneyline) | **AWAY (NOP gana)** | **2.900** *(888sport)* | 36.3% | `+5.3%` | `-10.77%` | S/1.00 | ✅ GANADA | S/+1.90 (HOME 134 - AWAY 135 (Total: 269)) |
| `2026-11-02 19:30` | **WAS @ ORL** | Total Puntos (Over/Under) | **OVER 225.5** | **1.990** *(1xBet)* | 51.8% | `+3.0%` | — | S/1.13 | ❌ PERDIDA | S/-1.13 (HOME 94 - AWAY 103 (Total: 197)) |
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

### 🔍 2.A Radiografía de Apuestas Activas (¿Qué Está Apostando Hoy, Cuotas y Estadísticas Clave?)

#### 🎯 **PHI @ CLE** — `2026-11-06 19:30 Hora Perú`
- **¿Qué está apostando el bot?**: **Gana CLE (Local)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`2.210`** en *1xBet* vs Cuota Justa del Modelo **`2.088`** *(Ventaja Matemática EV: `+5.91%`)*
- **Stake y Ganancia Potencial**: Stake **`S/1.36 PEN`** → Ganancia neta potencial: **`+S/1.65 PEN`** *(Retorno total: `S/3.01 PEN`)*
- **Probabilidades**: Modelo Calibrado **`47.9%`** vs Probabilidad Implícita Limpia Casa **`43.2%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `CLE +0.6 pts` | Total esperado **`225.9 pts`** *(Rango 80% Conformal: `203 – 250 pts` | Prob. Prórroga: `9.7%` | Prob. Paliza: `10.1%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `CLE 1555` vs `PHI 1564` | **Eficiencia Neta (Off/Def)**: `CLE (115.6/113.9)` vs `PHI (113.3/111.2)` (`Dif: -0.4 pts/100`)
  - **Ritmo (Pace)**: `98.8 posesiones` | **Descanso**: `CLE 2d` vs `PHI 2d` | **Viaje Geodésico (Millas Haversine)**: `Dif. -859 millas` (`0 husos horarios`)
- **Por qué apostó el modelo**: _Ajuste de retorno de gira incluido · Eficiencia neta favorable (PHI +0.4 pts/100) · Cuota 2.210 en 1xBet supera la cuota justa del modelo (2.088)._

#### 🎯 **OKC @ MEM** — `2026-11-06 20:00 Hora Perú`
- **¿Qué está apostando el bot?**: **Gana OKC (Visita)** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`1.606`** en *DraftKings* vs Cuota Justa del Modelo **`1.575`** *(Ventaja Matemática EV: `+2.03%`)*
- **Stake y Ganancia Potencial**: Stake **`S/1.96 PEN`** → Ganancia neta potencial: **`+S/1.19 PEN`** *(Retorno total: `S/3.15 PEN`)*
- **Probabilidades**: Modelo Calibrado **`63.5%`** vs Probabilidad Implícita Limpia Casa **`60.0%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `MEM -5.1 pts` | Total esperado **`224.3 pts`** *(Rango 80% Conformal: `202 – 248 pts` | Prob. Prórroga: `8.2%` | Prob. Paliza: `11.6%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `MEM 1440` vs `OKC 1658` | **Eficiencia Neta (Off/Def)**: `MEM (114.7/115.9)` vs `OKC (114.2/109.6)` (`Dif: -5.7 pts/100`)
  - **Ritmo (Pace)**: `99.0 posesiones` | **Descanso**: `MEM 2d` vs `OKC 2d` | **Viaje Geodésico (Millas Haversine)**: `Dif. +421 millas` (`0 husos horarios`)
- **Por qué apostó el modelo**: _Visita (OKC) viaja +421 millas más · Eficiencia neta favorable (OKC +5.7 pts/100) · Cuota 1.606 en DraftKings supera la cuota justa del modelo (1.575)._

#### 🎯 **SAS @ SAC** — `2026-11-06 22:00 Hora Perú`
- **¿Qué está apostando el bot?**: **UNDER 228.5** en el mercado `Moneyline (Ganador)`
- **Cuota Tomada vs Cuota Justa**: **`1.930`** en *LowVig.ag* vs Cuota Justa del Modelo **`1.880`** *(Ventaja Matemática EV: `+2.77%`)*
- **Stake y Ganancia Potencial**: Stake **`S/1.68 PEN`** → Ganancia neta potencial: **`+S/1.56 PEN`** *(Retorno total: `S/3.24 PEN`)*
- **Probabilidades**: Modelo Calibrado **`53.2%`** vs Probabilidad Implícita Limpia Casa **`89.5%`**
- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `SAC -10.9 pts` | Total esperado **`225.5 pts`** *(Rango 80% Conformal: `204 – 248 pts` | Prob. Prórroga: `5.6%` | Prob. Paliza: `17.4%`)*
- **Estadísticas Clave Tomadas en Cuenta**:
  - **Rating Elo**: `SAC 1354` vs `SAS 1680` | **Eficiencia Neta (Off/Def)**: `SAC (111.2/118.2)` vs `SAS (115.7/108.8)` (`Dif: -13.9 pts/100`)
  - **Ritmo (Pace)**: `99.1 posesiones` | **Descanso**: `SAC 2d` vs `SAS 2d` | **Viaje Geodésico (Millas Haversine)**: `Dif. +1459 millas` (`2 husos horarios`)
- **Por qué apostó el modelo**: _Visita (SAS) viaja +1459 millas más · Eficiencia neta favorable (SAS +13.9 pts/100) · Cuota 1.930 en LowVig.ag supera la cuota justa del modelo (1.880)._

### 📋 2.B Cartelera Completa de Próximos Partidos: Cuotas, Estadísticas a Tomar en Cuenta y Veredicto

| Hora (Perú) | Partido (`Visita @ Local`) | Cuotas Ganador (`Local / Visita`) | Línea Total (`O/U`) | Proyección Modelo (`Margen / Total`) | Estadísticas Clave (`Elo`, `NetRtg`, `Descanso`, `Viaje`) | ¿Qué Hace el Bot y Por Qué? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `2026-11-06 19:00` | **WAS @ ATL** | Local **1.430** / Visita **3.550** *(Betfair)* | **228.5** (`O 1.95` / `U 1.93`) | **ATL -8.5 pts** (Prob Local `78.3%`) · Total **225.7 pts** | Elo `1532/1350` · Net `+6.9` · Pace `98.5` · Desc `2d/2d` · Viaje `+0 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-06 19:00` | **BOS @ CHA** | Local **3.950** / Visita **1.330** *(Bovada)* | **208.0** (`O 1.94` / `U 1.95`) | **BOS -4.8 pts** (Prob Local `36.8%`) · Total **214.1 pts** | Elo `1481/1604` · Net `-7.9` · Pace `98.1` · Desc `2d/2d` · Viaje `+190 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-06 19:30` | **PHI @ CLE** | Local **2.380** / Visita **1.810** *(Betfair)* | **230.5** (`O 1.99` / `U 2.01`) | **CLE -0.6 pts** (Prob Local `53.3%`) · Total **225.9 pts** | Elo `1555/1564` · Net `-0.4` · Pace `98.8` · Desc `2d/2d` · Viaje `-859 mi` | **🎯 APOSTADO: Gana CLE (Local) @ 2.210 (1xBet) | Stake S/1.36 (EV +5.91%)** — _Ajuste de retorno de gira incluido · Eficiencia neta favorable (PHI +0.4 pts/100) · Cuota 2.210 en 1xBet supera la cuota justa del modelo (2.088)._ |
| `2026-11-06 20:00` | **UTA @ DAL** | Local **1.410** / Visita **3.500** *(DraftKings)* | **226.5** (`O 1.96` / `U 2.02`) | **DAL -7.9 pts** (Prob Local `75.1%`) · Total **229.3 pts** | Elo `1428/1301` · Net `+6.4` · Pace `99.0` · Desc `2d/2d` · Viaje `+191 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-06 20:00` | **OKC @ MEM** | Local **2.510** / Visita **1.670** *(Marathon Bet)* | **225.5** (`O 1.95` / `U 1.95`) | **OKC -5.1 pts** (Prob Local `30.7%`) · Total **224.3 pts** | Elo `1440/1658` · Net `-5.7` · Pace `99.0` · Desc `2d/2d` · Viaje `+421 mi` | **🎯 APOSTADO: Gana OKC (Visita) @ 1.606 (DraftKings) | Stake S/1.96 (EV +2.03%)** — _Visita (OKC) viaja +421 millas más · Eficiencia neta favorable (OKC +5.7 pts/100) · Cuota 1.606 en DraftKings supera la cuota justa del modelo (1.575)._ |
| `2026-11-06 20:00` | **TOR @ MIL** | Local **4.070** / Visita **1.450** *(1xBet)* | **231.0** (`O 1.98` / `U 1.98`) | **TOR -4.6 pts** (Prob Local `34.6%`) · Total **226.1 pts** | Elo `1364/1526` · Net `-6.1` · Pace `99.8` · Desc `2d/2d` · Viaje `+57 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-06 20:00` | **MIN @ NOP** | Local **2.630** / Visita **1.640** *(BetRivers)* | **229.5** (`O 1.95` / `U 2.01`) | **MIN -4.3 pts** (Prob Local `34.3%`) · Total **228.3 pts** | Elo `1436/1612` · Net `-5.4` · Pace `99.5` · Desc `2d/2d` · Viaje `+317 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-06 22:00` | **POR @ LAL** | Local **1.781** / Visita **2.360** *(DraftKings)* | **232.0** (`O 1.93` / `U 2.00`) | **LAL -4.0 pts** (Prob Local `64.0%`) · Total **225.4 pts** | Elo `1592/1554` · Net `+2.3` · Pace `99.3` · Desc `2d/2d` · Viaje `-3 mi` | **🛡️ NO APOSTAR (Pass)** — _Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)._ |
| `2026-11-06 22:00` | **SAS @ SAC** | Local **9.500** / Visita **1.111** *(Marathon Bet)* | **229.5** (`O 2.00` / `U 2.07`) | **SAS -10.9 pts** (Prob Local `17.9%`) · Total **225.5 pts** | Elo `1354/1680` · Net `-13.9` · Pace `99.1` · Desc `2d/2d` · Viaje `+1459 mi` | **🎯 APOSTADO: UNDER 228.5 @ 1.930 (LowVig.ag) | Stake S/1.68 (EV +2.77%)** — _Visita (SAS) viaja +1459 millas más · Eficiencia neta favorable (SAS +13.9 pts/100) · Cuota 1.930 en LowVig.ag supera la cuota justa del modelo (1.880)._ |
| `2026-11-07 17:00` | **DEN @ IND** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **DEN -6.2 pts** (Prob Local `30.0%`) · Total **225.9 pts** | Elo `1360/1556` · Net `-8.1` · Pace `98.8` · Desc `2d/2d` · Viaje `+615 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-07 19:30` | **BKN @ ATL** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **ATL -8.1 pts** (Prob Local `78.3%`) · Total **221.3 pts** | Elo `1532/1342` · Net `+5.1` · Pace `98.7` · Desc `3d/3d` · Viaje `+203 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-07 20:00` | **NYK @ CLE** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **NYK -2.1 pts** (Prob Local `42.9%`) · Total **222.5 pts** | Elo `1555/1659` · Net `-3.5` · Pace `98.6` · Desc `3d/3d` · Viaje `-546 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-07 20:00` | **WAS @ OKC** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **OKC -13.2 pts** (Prob Local `88.1%`) · Total **222.5 pts** | Elo `1658/1350` · Net `+10.7` · Pace `98.6` · Desc `3d/3d` · Viaje `+1150 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-07 20:30` | **ORL @ GSW** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **GSW -5.0 pts** (Prob Local `64.6%`) · Total **221.8 pts** | Elo `1507/1486` · Net `+4.5` · Pace `99.4` · Desc `2d/2d` · Viaje `+651 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-07 21:00` | **HOU @ PHX** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **HOU -4.4 pts** (Prob Local `35.5%`) · Total **224.8 pts** | Elo `1477/1621` · Net `-5.4` · Pace `99.9` · Desc `2d/3d` · Viaje `+1015 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |
| `2026-11-07 22:00` | **SAS @ POR** | ⏳ *Sin cuotas publicadas* | Línea est. `228.5` | **SAS -2.6 pts** (Prob Local `40.7%`) · Total **223.0 pts** | Elo `1554/1680` · Net `-4.3` · Pace `98.7` · Desc `3d/3d` · Viaje `+714 mi` | **⏳ SIN CUOTAS AÚN** — _Las casas de apuestas aún no publican línea pre-partido verificada._ |

---

## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)

| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |
| `BET_20261106_92B26B33` | `2026-11-06` | `ORL @ PHX` | Ganador (Moneyline) | **HOME (PHX gana)** | 1.910 | 53.5% | `+2.2%` | ✅ WON | **S/+1.26** | `S/97.72` |
| `BET_20261105_A563FA74` | `2026-11-05` | `TOR @ DEN` | Ganador (Moneyline) | **AWAY (TOR gana)** | 2.900 | 37.2% | `+7.9%` | ❌ LOST | **S/-1.10** | `S/96.45` |
| `BET_20261105_63E8261D` | `2026-11-05` | `CLE @ OKC` | Ganador (Moneyline) | **HOME (OKC gana)** | 1.770 | 58.5% | `+3.6%` | ✅ WON | **S/+1.69** | `S/99.12` |
| `BET_20261105_11DC3E0B` | `2026-11-05` | `PHI @ DET` | Ganador (Moneyline) | **HOME (DET gana)** | 1.810 | 56.6% | `+2.5%` | ❌ LOST | **S/-1.57** | `S/97.55` |
| `BET_20261103_06657F1C` | `2026-11-03` | `BOS @ HOU` | Total Puntos (Over/Under) | **OVER 219.5** | 1.990 | 51.3% | `+2.1%` | ❌ LOST | **S/-1.00** | `S/97.44` |
| `BET_20261103_EF0858D0` | `2026-11-03` | `NOP @ MEM` | Ganador (Moneyline) | **AWAY (NOP gana)** | 2.900 | 36.3% | `+5.3%` | ✅ WON | **S/+1.90** | `S/98.44` |
| `BET_20261103_E59224AE` | `2026-11-03` | `WAS @ ORL` | Total Puntos (Over/Under) | **OVER 225.5** | 1.990 | 51.8% | `+3.0%` | ❌ LOST | **S/-1.13** | `S/96.54` |
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
