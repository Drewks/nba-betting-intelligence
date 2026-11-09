# NBA Betting Intelligence — Quantitative Sports Analytics & Paper Trading Engine

Sistema cuantitativo de investigación probabilística, calibración estadística y **paper trading exclusivo (S/ 100.00 PEN virtual)** para la NBA.

> [!WARNING]
> **Aviso de Integridad y Riesgo**: entorno exclusivo de investigación y paper trading (S/ 100.00 PEN virtuales, stake fijo S/ 1.00, AGENTS.md).
> Muestra actual con cuotas observadas: **25 apuestas liquidadas, ROI ≈ 0%, IC 95% ≈ [-24%, +28%]**. No hay evidencia de ventaja.
> Confirmar un edge del 5% exige ~1,400 apuestas; uno del 2%, ~8,800. Por eso la métrica principal es el **CLV contra el cierre sin margen**.

---

## 🏛️ Estado actual: implementado vs. pendiente

| Componente | Estado | Detalle |
| :--- | :---: | :--- |
| Ingesta de cartelera y resultados (ESPN) | ✅ | Los resultados FINAL actualizan solo estado/marcador; nunca sobrescriben las features pre-partido. |
| Cuotas observadas (The Odds API / ESPN-DraftKings) | ✅ | Toda escritura pasa por `DatabaseManager.insert_odds_snapshot`, que exige `source_type` explícito. |
| Apuestas solo con cuotas observadas | ✅ | El ciclo lee `v_observed_odds_snapshots` (excluye cuarentena, DERIVED/SYNTHETIC y proveedores autogenerados). |
| Historial inmutable + detección de borrados | ✅ | Triggers SQLite + `audit_row_registry` append-only verificado por el auditor en cada ciclo. |
| Restauración del historial borrado el 2026-11-09 | ✅ | Migración `2026_11_09_003` (bundle con checksum en `data/recovery/`), cada acción en `audit_repairs`. |
| Gestión de riesgo | ✅ | Config única `config/model_config.yaml` validada contra AGENTS.md: stake S/1, máx. 3/jornada, EV > 5%. |
| Métricas y gates | ✅ | Fail-closed; el modelo se compara contra el **mercado sin margen** (gate 10), no solo contra el baseline ingenuo. |
| CLV | ✅ | `100·(cuota × p_cierre_sin_margen − 1)`, cierre Pinnacle preferido; valores > 15% se excluyen como error de datos. |
| Injury Sniper | 🟡 | Ancla en el mercado; solo cambios de estado NUEVOS (vs. snapshot previo) mueven la probabilidad. Tabla de impacto aún sin calibrar. |
| Casas peruanas (RETAbet, Betsson, ...) | ⚪ | No se capturan cuotas reales. El comparador solo produce **estimaciones**, que nunca se guardan ni se usan para apostar. |
| Player props / SGP / parlays | ⚪ | Desactivados: no hay líneas observadas y AGENTS.md prohíbe apuestas combinadas. |
| Backtest con cuotas históricas reales | ⚪ | Pendiente: el proyecto no almacena cuotas históricas de cierre. El backtest sintético NO es evidencia. |
| Hiperparámetros optimizados | ⚪ | El estudio Optuna anterior tenía fuga del resultado (inválido). Se usan priors sin ajustar hasta re-optimizar con holdout. |

---

## 📐 Reglas operativas

1. **Benchmark = mercado sin margen**: el modelo debe ser no peor que el mercado (Brier/LogLoss) en los mismos partidos.
2. **Cero EV negativo**: si EV ≤ 0 el stake es S/ 0.00. Stake fijo S/ 1.00 hasta tener evidencia de CLV positivo.
3. **Solo cuotas observadas**: ninguna cuota estimada, derivada o sintética puede generar una apuesta.
4. **Historial inmutable**: la base de datos solo la escribe el bot; los cambios de datos se hacen con migraciones auditadas (`src/storage/migrations.py`). El CI falla si un commit humano modifica `data/nba_intelligence.sqlite3`.

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
