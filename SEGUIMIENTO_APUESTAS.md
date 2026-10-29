# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración

- **Última actualización**: `2026-10-28 19:50 (Hora Perú UTC-5)` (`2026-10-29T00:50:51Z`)
- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/103.03 PEN`** (`+3.04 PEN`)
- **ROI Actual**: `+3.10%` | **Yield Actual**: `+2.92%` | **Apuestas en espera**: `6` (`S/6.00 PEN` reservados)
- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)

---

## 🚦 1. ¿Cuándo Terminar la Calibración y Evaluar Uso con Dinero Real?

### Estado Global: **🔴 EN FASE DE CALIBRACIÓN Y PAPER TRADING (NO USAR DINERO REAL AÚN)**
**Progreso de Muestra Mínima**: `[████░░░░░░░░░░░░░░░░] 98 / 500 apuestas liquidadas (19.6%)` — *Faltan **402** apuestas liquidadas.*

Para considerar que la calibración ha finalizado con evidencia estadística rigurosa, **las 6 luces del semáforo deben estar en VERDE (✅) al mismo tiempo**:

| # | Criterio para Salir de Simulación | Estado Hoy | Valor Actual | Meta Requerida |
| :-: | :--- | :---: | :--- | :--- |
| 1 | **Muestra mínima de apuestas liquidadas** | 🔴 PENDIENTE | `98 apuestas` | **>= 500 apuestas liquidadas** |
| 2 | **Calibración mejor que el Baseline (Brier & LogLoss)** | ✅ VERDE | `Brier 0.2455 vs 0.2503` | **Brier y LogLoss <= Baseline** |
| 3 | **Rentabilidad Neta Positiva (ROI y Yield > 0%)** | ✅ VERDE | `ROI +3.10% / Yield +2.92%` | **> +0.00%** |
| 4 | **Intervalo de Confianza 95% excluye el azar (> 0%)** | 🔴 PENDIENTE | `[-21.81%, +27.73%]` | **Límite inferior > +0.00%** |
| 5 | **Cero Fuga de Información (Anti-Leakage)** | ✅ VERDE | `0 violaciones` | **0 violaciones** |
| 6 | **Contabilidad e Inmutabilidad SQLite Verificadas** | ✅ VERDE | `100% reconciliado` | **Reconciliado sin errores** |

> **Regla práctica**: Con un ritmo de ~2 a 3 apuestas diarias durante la temporada NBA, el sistema alcanzará las **500 apuestas reales liquidadas** de forma automática. Solo cuando las 6 filas de arriba marquen **✅ VERDE**, tendrás evidencia estadística de que el modelo supera al margen de la casa.

---

## 🏀 2. Mis Apuestas NBA Reales (ESPN / Cuotas Reales DraftKings)

Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido):

| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Cuota (DraftKings) | Prob. Modelo | EV (%) | Stake | Estado | Resultado / Ganancia |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |
| `2026-10-29 21:00` | **MEM @ POR** | Total Puntos (Over/Under) | **UNDER 232.5** | **1.910** | 63.5% | `+21.2%` | S/1.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-10-29 19:00` | **SAC @ NOP** | Total Puntos (Over/Under) | **UNDER 237.5** | **1.950** | 66.9% | `+30.4%` | S/1.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-10-29 19:00` | **SAC @ NOP** | Ganador (Moneyline) | **HOME (NOP gana)** | **1.520** | 71.7% | `+9.0%` | S/1.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-10-28 21:30` | **LAL @ LAC** | Ganador (Moneyline) | **HOME (LAC gana)** | **1.970** | 59.9% | `+17.9%` | S/1.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-10-28 20:30` | **OKC @ DAL** | Ganador (Moneyline) | **HOME (DAL gana)** | **2.760** | 49.8% | `+37.3%` | S/1.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-10-28 20:30` | **OKC @ DAL** | Total Puntos (Over/Under) | **UNDER 228.5** | **1.920** | 57.0% | `+9.4%` | S/1.00 | ⏳ PENDIENTE | Esperando final del partido |

---

## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)

| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |
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
| `BET_20260209_33E87E96` | `2026-02-09` | `CHI @ PHI` | Ganador (Moneyline) | **AWAY (CHI gana)** | 2.634 | 50.1% | `+32.1%` | ❌ LOST | **S/-1.00** | `S/105.64` |
| `BET_20260209_5535032F` | `2026-02-09` | `ATL @ SAS` | Total Puntos (Over/Under) | **UNDER 230.0** | 1.951 | 65.8% | `+28.4%` | ✅ WON | **S/+0.95** | `S/106.59` |
| `BET_20260209_5A87E96F` | `2026-02-09` | `DEN @ DAL` | Total Puntos (Over/Under) | **UNDER 228.5** | 1.677 | 66.2% | `+11.1%` | ❌ LOST | **S/-1.00** | `S/105.59` |
| `BET_20260208_CF293761` | `2026-02-08` | `MIN @ BKN` | Total Puntos (Over/Under) | **OVER 218.5** | 2.263 | 51.6% | `+16.8%` | ❌ LOST | **S/-1.00** | `S/108.64` |
| `BET_20260208_87C665CD` | `2026-02-08` | `IND @ LAC` | Ganador (Moneyline) | **AWAY (IND gana)** | 3.742 | 30.4% | `+13.9%` | ❌ LOST | **S/-1.00** | `S/107.64` |
| `BET_20260208_6F0968B4` | `2026-02-08` | `BOS @ MEM` | Total Puntos (Over/Under) | **UNDER 228.0** | 1.996 | 56.8% | `+13.4%` | ❌ LOST | **S/-1.00** | `S/106.64` |
