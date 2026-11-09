# NBA Betting Intelligence — Quantitative Sports Analytics & Paper Trading Engine

Sistema cuantitativo de investigación probabilística, calibración estadística y **paper trading exclusivo (S/ 100.00 PEN virtual)** para la NBA.

> [!WARNING]
> **Aviso de Integridad y Riesgo**:
> Este sistema opera exclusivamente como un entorno de investigación y paper trading sin dinero real. Ninguna métrica aquí presentada garantiza rentabilidad futura. La muestra observada actual es de **25 apuestas reales con cuotas observadas** con un retorno neto de **+S/ 0.09 PEN (ROI +0.28%)** y un intervalo de confianza al 95% de **[-24.0%, +28.0%]**, lo que indica que estadísticamente **no se puede descartar la ausencia de ventaja (azar)**. Se requieren al menos 500 a 1,400 apuestas observadas para confirmar significancia estadística.

---

## 🏛️ Estado Actual del Sistema: Implementado vs. Planificado

Siguiendo la auditoría de integridad técnica, separamos de manera estricta lo que está verificado en producción frente a lo que permanece en desarrollo o requiere suscripciones comerciales de pago:

| Componente | Estado | Descripción Técnica |
| :--- | :---: | :--- |
| **Ingesta de Cartelera & Resultados** | ✅ Operativo | Ingesta oficial de partidos, marcadores y estados vía ESPN Public API (sin costo). |
| **Cuotas de Mercado Observadas** | ✅ Operativo | Ingesta de cuotas pre-partido reales de casas de referencia (The Odds API / DraftKings, Pinnacle, etc.). |
| **Cuarentena de Cuotas Sintéticas** | ✅ Operativo | Tabla `quarantined_odds` y vistas `v_observed_*` que aíslan y excluyen cuotas no observadas o simuladas. |
| **Gestión de Riesgo & Kelly Estricto** | ✅ Operativo | Stakes limitados a **S/ 1.00 - S/ 2.00 PEN (1-2% banca)**, umbral EV $\ge 5\%$. Si EV $\le 0$, el stake es estrictamente **S/ 0.00 PEN**. |
| **Prevención de Fuga Temporal** | ✅ Operativo | Triggers SQLite inmutables (`prevent_prediction_update`, `prevent_settled_bet_tampering`) y validación pre-tipoff. |
| **Automatización Cloud & Concurrencia** | ✅ Operativo | GitHub Actions (Python 3.12 + Astral `uv`) en 4 ventanas diarias PET, con bloqueo `concurrency: nba-pipeline-execution`. |
| **Interfaz Telegram Interactiva** | ✅ Operativo | Bot interactivo (`@notideclau_bot`) con botonera táctil (`[💰 Mi Banca]`, `[🎯 Picks +EV]`, `[⚡ Cuotas Perú]`, etc.) y lista de control de acceso estricta. |
| **Web Scraping en Vivo de Casas Perú** | 🟡 Heurístico / Mock | Modelado de cuotas locales y comparación Shin; requiere proxies rotativos residenciales y scrapers activos por casa. |
| **Liquidación Automática de Player Props** | 🟡 En Desarrollo | Requiere parser de boxscores individuales por jugador; los props se evalúan únicamente cuando existen cuotas observadas. |
| **Sportradar Synergy Enterprise** | ⚪ Planificado | Requiere licencia comercial corporativa; actualmente opera con datos públicos y priors de posesión. |

---

## 📐 Principios Cuantitativos y Reglas Operativas

1. **Benchmark de Mercado Sharp (Pinnacle De-Vigged)**:
   * El rival del modelo no es un baseline ingenuo sino la línea de cierre de mercado libre de margen calculada mediante el algoritmo de Shin.
   * La métrica reina es el **CLV en espacio de probabilidad** frente al cierre *sharp*:
     $$\text{CLV}_{prob} = P_{modelo} - P_{sharp\_cierre}$$

2. **Cero Tolerancia a Valores Negativos de EV**:
   * A diferencia de sistemas heurísticos, si el valor esperado unitario $\text{EV} \le 0$, la asignación de capital es estrictamente **S/ 0.00 PEN**.
   * Se prohíben multiplicadores arbitrarios en apuestas combinadas y límites mínimos artificiales de cuota.

3. **Tope de Exposición de Portafolio**:
   * La exposición simultánea máxima en toda la cartelera del día no puede exceder el **20% de la banca liquidada**.

4. **Predicción Conformal Adaptativa (Venn-Abers)**:
   * Intervalos $[p_0, p_1]$ adaptativos con cobertura estadística calibrada para modelar la incertidumbre epistémica de cada partido.

---

## 🚀 Ejecución y Comandos

### 1. Entorno de Desarrollo
```powershell
# Sincronizar dependencias en entorno virtual con uv
uv sync --extra dev --python 3.12

# Correr la suite completa de 50 pruebas automatizadas
uv run pytest -q

# Ejecutar análisis de calidad y formateo con ruff
uv run ruff check src/
```

### 2. Ejecutar Ciclo Manual
```powershell
# Ciclo de apertura matutina (10:15 AM PET)
uv run python scripts/run_automated_scheduler.py --run-now morning

# Ciclo nocturno de liquidación con ESPN (01:45 AM PET)
uv run python scripts/run_automated_scheduler.py --run-now settle
```

### 3. Bot Interactivo de Telegram
```powershell
# Iniciar listener interactivo de Telegram
uv run python scripts/run_telegram_listener.py
```

---

## 📊 Seguimiento y Auditoría
* Panel de seguimiento en tiempo real: [`SEGUIMIENTO_APUESTAS.md`](SEGUIMIENTO_APUESTAS.md)
* Historial de apuestas en CSV: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)
* Dashboard público en GitHub Pages: [nba-betting-intelligence](https://drewks.github.io/nba-betting-intelligence/)
