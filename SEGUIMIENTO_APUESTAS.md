# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración

- **Última actualización**: `2026-10-28 19:29 (Hora Perú UTC-5)` (`2026-10-29T00:29:39Z`)
- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/106.00 PEN`** (`+6.00 PEN`)
- **ROI Actual**: `+6.45%` | **Yield Actual**: `+6.18%` | **Apuestas en espera**: `4` (`S/4.00 PEN` reservados)
- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)

---

## 🚦 1. ¿Cuándo Terminar la Calibración y Evaluar Uso con Dinero Real?

### Estado Global: **🔴 EN FASE DE CALIBRACIÓN Y PAPER TRADING (NO USAR DINERO REAL AÚN)**
**Progreso de Muestra Mínima**: `[████░░░░░░░░░░░░░░░░] 93 / 500 apuestas liquidadas (18.6%)` — *Faltan **407** apuestas liquidadas.*

Para considerar que la calibración ha finalizado con evidencia estadística rigurosa, **las 6 luces del semáforo deben estar en VERDE (✅) al mismo tiempo**:

| # | Criterio para Salir de Simulación | Estado Hoy | Valor Actual | Meta Requerida |
| :-: | :--- | :---: | :--- | :--- |
| 1 | **Muestra mínima de apuestas liquidadas** | 🔴 PENDIENTE | `93 apuestas` | **>= 500 apuestas liquidadas** |
| 2 | **Calibración mejor que el Baseline (Brier & LogLoss)** | 🟡 AJUSTANDO | `Brier 0.2463 vs 0.2452` | **Brier y LogLoss <= Baseline** |
| 3 | **Rentabilidad Neta Positiva (ROI y Yield > 0%)** | ✅ VERDE | `ROI +6.45% / Yield +6.18%` | **> +0.00%** |
| 4 | **Intervalo de Confianza 95% excluye el azar (> 0%)** | 🔴 PENDIENTE | `[-17.30%, +32.62%]` | **Límite inferior > +0.00%** |
| 5 | **Cero Fuga de Información (Anti-Leakage)** | ✅ VERDE | `0 violaciones` | **0 violaciones** |
| 6 | **Contabilidad e Inmutabilidad SQLite Verificadas** | ✅ VERDE | `100% reconciliado` | **Reconciliado sin errores** |

> **Regla práctica**: Con un ritmo de ~2 a 3 apuestas diarias durante la temporada NBA, el sistema alcanzará las **500 apuestas reales liquidadas** de forma automática. Solo cuando las 6 filas de arriba marquen **✅ VERDE**, tendrás evidencia estadística de que el modelo supera al margen de la casa.

---

## 🏀 2. Mis Apuestas NBA Reales (ESPN / Cuotas Reales DraftKings)

Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido):

| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Cuota (DraftKings) | Prob. Modelo | EV (%) | Stake | Estado | Resultado / Ganancia |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |
| `2026-10-29 21:00` | **MEM @ POR** | Total Puntos (Over/Under) | **UNDER 232.5** | **1.909** | 60.4% | `+15.3%` | S/1.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-10-29 21:00` | **MEM @ POR** | Ganador (Moneyline) | **AWAY (MEM gana)** | **3.050** | 34.7% | `+5.7%` | S/1.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-10-28 21:30` | **LAL @ LAC** | Ganador (Moneyline) | **HOME (LAC gana)** | **1.893** | 57.6% | `+9.0%` | S/1.00 | ⏳ PENDIENTE | Esperando final del partido |
| `2026-10-28 20:30` | **OKC @ DAL** | Ganador (Moneyline) | **HOME (DAL gana)** | **2.600** | 45.5% | `+18.2%` | S/1.00 | ⏳ PENDIENTE | Esperando final del partido |

---

## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)

| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |
| `BET_20260214_8437475C` | `2026-02-14` | `DET @ BOS` | Ganador (Moneyline) | **AWAY (DET gana)** | 3.743 | 36.4% | `+36.3%` | ✅ WON | **S/+2.74** | `S/107.00` |
| `BET_20260214_ECF9B753` | `2026-02-14` | `NYK @ CHI` | Total Puntos (Over/Under) | **UNDER 234.0** | 1.920 | 56.1% | `+7.8%` | ❌ LOST | **S/-1.00** | `S/106.00` |
| `BET_20260213_568F3E83` | `2026-02-13` | `POR @ HOU` | Total Puntos (Over/Under) | **UNDER 229.0** | 1.753 | 62.5% | `+9.6%` | ❌ LOST | **S/-1.00** | `S/106.25` |
| `BET_20260213_868D7861` | `2026-02-13` | `CHA @ MIA` | Total Puntos (Over/Under) | **UNDER 232.5** | 1.962 | 55.7% | `+9.2%` | ❌ LOST | **S/-1.00** | `S/105.25` |
| `BET_20260213_195195D1` | `2026-02-13` | `SAS @ UTA` | Total Puntos (Over/Under) | **UNDER 225.0** | 2.095 | 51.5% | `+7.8%` | ❌ LOST | **S/-1.00** | `S/104.25` |
| `BET_20260212_B2F03812` | `2026-02-12` | `MEM @ ATL` | Total Puntos (Over/Under) | **UNDER 228.5** | 2.271 | 51.6% | `+17.2%` | ❌ LOST | **S/-1.00** | `S/105.70` |
| `BET_20260212_EAF22F91` | `2026-02-12` | `CHI @ MIL` | Total Puntos (Over/Under) | **UNDER 232.0** | 1.966 | 54.3% | `+6.8%` | ✅ WON | **S/+0.97** | `S/106.66` |
| `BET_20260212_D4D24539` | `2026-02-12` | `CHI @ MIL` | Ganador (Moneyline) | **HOME (MIL gana)** | 1.590 | 66.1% | `+5.1%` | ✅ WON | **S/+0.59** | `S/107.25` |
| `BET_20260211_98A22DD8` | `2026-02-11` | `NYK @ OKC` | Ganador (Moneyline) | **AWAY (NYK gana)** | 1.448 | 78.8% | `+14.1%` | ❌ LOST | **S/-1.00** | `S/108.70` |
| `BET_20260211_602904B3` | `2026-02-11` | `LAL @ ATL` | Ganador (Moneyline) | **AWAY (LAL gana)** | 3.201 | 34.7% | `+11.2%` | ❌ LOST | **S/-1.00** | `S/107.70` |
| `BET_20260211_EA2C38B9` | `2026-02-11` | `MIN @ IND` | Total Puntos (Over/Under) | **UNDER 223.5** | 2.235 | 48.7% | `+8.9%` | ❌ LOST | **S/-1.00** | `S/106.70` |
| `BET_20260210_66668329` | `2026-02-10` | `SAC @ NYK` | Ganador (Moneyline) | **AWAY (SAC gana)** | 3.245 | 35.2% | `+14.1%` | ✅ WON | **S/+2.25** | `S/109.17` |
| `BET_20260210_10F4552A` | `2026-02-10` | `POR @ DAL` | Total Puntos (Over/Under) | **UNDER 230.5** | 1.706 | 64.8% | `+10.6%` | ❌ LOST | **S/-1.00** | `S/108.17` |
| `BET_20260210_AEE7C7E3` | `2026-02-10` | `MIN @ IND` | Ganador (Moneyline) | **HOME (IND gana)** | 2.522 | 42.2% | `+6.6%` | ✅ WON | **S/+1.52** | `S/109.70` |
| `BET_20260209_7C07C268` | `2026-02-09` | `ATL @ SAS` | Total Puntos (Over/Under) | **UNDER 230.0** | 1.951 | 60.0% | `+17.0%` | ✅ WON | **S/+0.95** | `S/106.58` |
| `BET_20260209_788A4CFF` | `2026-02-09` | `CHI @ PHI` | Ganador (Moneyline) | **AWAY (CHI gana)** | 2.634 | 43.2% | `+13.9%` | ❌ LOST | **S/-1.00** | `S/105.58` |
| `BET_20260209_50FC8164` | `2026-02-09` | `POR @ MEM` | Total Puntos (Over/Under) | **UNDER 224.0** | 2.347 | 47.2% | `+10.8%` | ✅ WON | **S/+1.35** | `S/106.93` |
| `BET_20260208_408B2081` | `2026-02-08` | `BOS @ MEM` | Total Puntos (Over/Under) | **UNDER 228.0** | 1.996 | 55.2% | `+10.2%` | ❌ LOST | **S/-1.00** | `S/105.68` |
| `BET_20260208_93745628` | `2026-02-08` | `CHA @ HOU` | Total Puntos (Over/Under) | **UNDER 230.5** | 1.947 | 55.1% | `+7.3%` | ✅ WON | **S/+0.95** | `S/106.63` |
| `BET_20260208_964B1513` | `2026-02-08` | `MIN @ BKN` | Total Puntos (Over/Under) | **OVER 218.5** | 2.263 | 46.5% | `+5.3%` | ❌ LOST | **S/-1.00** | `S/105.63` |
