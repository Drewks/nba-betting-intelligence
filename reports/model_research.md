# Investigación de mejora del modelo (2026-11-09)

Datos: 2,624 partidos (dic-2024 → nov-2026) con predicción fuera de muestra del modelo y consenso real
de mercado (apertura y cierre sin margen, CC BY 4.0, minmaxxxer/HuggingFace). Evaluación walk-forward.

## 1. Diagnóstico
- Los componentes del ensemble (Elo, margen, LightGBM, Monte Carlo) dan Brier 0.2074–0.2080: usan la
  misma información (marcadores pasados), así que combinarlos no aporta.
- Frente al mercado de apertura (Brier 0.2011) el modelo antiguo no añadía información en moneyline:
  el peso óptimo del modelo era ~0.1 (con 0.3 empeoraba el log-loss).
- Error del margen (RMSE): modelo 14.51 | spread de apertura 14.25 | cierre 13.96.
- Totales: el modelo anticipa el movimiento de línea (correlación +0.27), pero el acierto over/under
  a la línea de apertura es 52–55%, cerca del punto de equilibrio.

## 2. Mejora implementada: box scores reales de ESPN (gratis)
Posesiones reales, Four Factors reales y puntos/minutos de jugadores habituales ausentes en el
último partido del equipo (`src/features/boxscore_features.py`), como ajuste del ensemble.

| Backtest real (2,301 partidos) | Brier modelo calibrado | Brier anclado 30/70 | Mercado apertura | Corr. con movimiento de línea ML |
| :--- | ---: | ---: | ---: | ---: |
| Antes (sin box scores) | 0.20711 | 0.20124 | 0.20108 | +0.071 |
| Con box scores | **0.20536** | **0.20071** | 0.20108 | **+0.133** |
| Con box scores, 1 día de rezago de información | 0.20588 | 0.20090 | 0.20108 | +0.127 |

- La mejora del modelo es real y sobrevive al rezago de un día.
- El modelo anclado queda al nivel del mercado de apertura (diferencia dentro del ruido): todavía
  **no hay ventaja demostrada en moneyline** (CLV de apuestas −0.5% [−2.7, +1.8]).
- Los box scores no mejoran los totales (probado; no se integró).

## 3. Qué falta para superar al mercado
1. Disponibilidad real en el momento de decidir (reporte oficial de lesiones) en vez del proxy
   "no jugó el último partido"; es lo que explica la brecha apertura → cierre.
2. Valor por jugador (on/off o plus-minus ajustado) en lugar de puntos por partido.
3. Totales en apertura: es donde hay señal de CLV (+3.5% a +4.9%); necesita más muestra.
