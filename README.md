# NBA Betting Intelligence — Quantitative Sports Analytics & Paper Trading Engine

Sistema cuantitativo de investigación probabilística, calibración estadística y **paper trading exclusivo (S/ 100.00 PEN virtual)** para la NBA.

> [!WARNING]
> **Aviso de Integridad y Riesgo**: entorno exclusivo de investigación y paper trading (**S/ 100.00 PEN virtuales**, `config/model_config.yaml` como única fuente de verdad — política efectiva desde `2026-11-14`, versión de modelo `model_f_ensemble_v8`).
> Muestra histórica inicial con cuotas observadas: **25 apuestas liquidadas, ROI ≈ 0%, IC 95% ≈ [-24%, +28%]**. No hay evidencia de ventaja estadísticamente significativa.
> Confirmar un edge del 5% exige ~1,400 apuestas; uno del 2%, ~8,800. Por eso la métrica principal es el **CLV contra el cierre sin margen**.

---

## 🏛️ Estado actual: implementado vs. pendiente

| Componente | Estado | Detalle |
| :--- | :---: | :--- |
| Ingesta de cartelera y resultados (ESPN) | ✅ | Los resultados `FINAL` actualizan solo estado/marcador; nunca sobrescriben las features pre-partido. |
| Cuotas observadas (`ESPN` / `TheOddsAPI`) | ✅ | Toda escritura pasa por `DatabaseManager.insert_odds_snapshot` con `source_type='OBSERVED'` explícito. |
| Apuestas solo con cuotas observadas | ✅ | El ciclo lee `v_observed_odds_snapshots` (excluye cuarentena, `DERIVED`/`SYNTHETIC` y proveedores autogenerados). |
| Mercados pre-partido (`Moneyline`, `Total Points`, `Spread`) | ✅ | Soporte completo end-to-end (validación, consenso de-vig, calibración OOS por mercado, EV con push y liquidación). |
| Historial inmutable + Manifiesto por ejecución | ✅ | Triggers SQLite, `audit_row_registry` y tabla append-only `run_manifests` (`commit_sha`, `config_hash`, versiones, calibradores y semillas). |
| Restauración del historial borrado el 2026-11-09 | ✅ | Migración `2026_11_09_003` (bundle con checksum en `data/recovery/`), cada acción en `audit_repairs`. |
| Gestión de riesgo (`config/model_config.yaml`) | ✅ | Única fuente de verdad: **Kelly fraccional 25% (`kelly_fraction: 0.25`)**, **EV mínimo 2.0% (`min_ev_threshold: 0.02`)**, tope `S/ 10.00` (`max_stake_pen: 10.00`, máx. `10%` banca), mín. `S/ 1.00`, máx. `3` selecciones/jornada, máx. `30%` exposición. |
| Métricas y gates | ✅ | Fail-closed; probabilidades separadas (`raw_model`, `calibrated_model`, `market_fair`, `market_anchored`) y benchmark estricto contra mercado sin margen (gate 10). |
| CLV | ✅ | `100·(cuota × p_cierre_sin_margen − 1)`, cierre Pinnacle preferido; valores > 15% excluidos como anomalía de datos. |
| Injury Sniper | 🟡 | Ancla en el mercado; solo cambios de estado NUEVOS (vs. snapshot previo) mueven la probabilidad. Tabla de impacto aún sin calibrar. |
| Casas peruanas (`Betano` & `RETAbet`) | 🟡 | Parcial/Desacoplado del scheduler cloud: `LivePeruOddsScraper` consulta APIs públicas/sharp y el cosechador local Playwright (`scripts/harvest_local_peru_odds.py`) está explícitamente omitido en scheduler automático por protección anti-bot Cloudflare/Shape. |
| Player Props & Sub-Bankroll Combinadas | ⛔ | **Deshabilitado por configuración** (`allow_player_props_betting: false`, `allow_parlays: false` en `config/model_config.yaml`) — bloqueo fail-closed en motor, ledger y scheduler salvo habilitación explícita. |
| Asignación Híbrida (`70% Totales / 30% Moneyline`) | ✅ | Configurada en `config/model_config.yaml` (`hybrid_allocation`: máx. `2` Totales y `1` Moneyline por jornada dentro del tope de `3`). |
| Backtest con cuotas históricas reales | ✅ | `scripts/run_real_odds_backtest.py`: walk-forward cronológico del modelo contra el consenso real de apertura/cierre (datos gratuitos CC BY 4.0) y holdout OOS sin ajuste previo. |
| Hiperparámetros optimizados | ⚪ | El estudio Optuna anterior tenía fuga del resultado (inválido). Se usan priors documentados en `config/model_config.yaml` hasta re-optimizar con holdout limpio. |

---

## 📐 Reglas operativas (`config/model_config.yaml` — vigencia `2026-11-14`)

> [!IMPORTANT]
> Todos los límites numéricos operativos se leen exclusivamente de [`config/model_config.yaml`](config/model_config.yaml) (`model.version_id: model_f_ensemble_v8`). Ninguna documentación ni reporte debe redefinir estos umbrales manualmente.

1. **Benchmark = mercado sin margen**: la calibración del modelo (`raw_model_probability`, `calibrated_model_probability`) se compara contra `market_fair_probability` exactamente sobre los mismos partidos antes de cualquier anclaje (`market_anchor_model_weight: 0.30`).
2. **Política de Stake y EV mínimo**:
   - `kelly_fraction`: `0.25` (**25% Quarter-Kelly fraccional**).
   - `min_ev_threshold`: `0.02` (**EV mínimo ≥ 2.0%**; si `EV < 2.0%`, el stake es `S/ 0.00`).
   - Límites por apuesta y jornada: `min_stake_pen: 1.00`, `max_stake_pen: 10.00`, `max_stake_bankroll_fraction: 0.10`, `max_selections_per_matchday: 3`, `max_portfolio_exposure_pct: 0.30`.
   - `allow_player_props_betting`: `false` | `allow_parlays`: `false` (bloqueo fail-closed en código y DB).
3. **Solo cuotas observadas**: ninguna cuota estimada, derivada o sintética puede generar una apuesta (`betting_allowed_source_types: ["OBSERVED"]`).
4. **Historial inmutable**: la base de datos de producción solo se modifica mediante migraciones auditadas (`src/storage/migrations.py`) o por la automatización en nube. El CI falla si un Pull Request altera `data/nba_intelligence.sqlite3`.

---

## 🧪 Backtest con cuotas reales (gratis)

```powershell
# Clonar la base a un archivo temporal antes de experimentar (nunca mutar data/nba_intelligence.sqlite3 en local)
Copy-Item data/nba_intelligence.sqlite3 $env:TEMP/nba_audit_work.sqlite3
uv run python scripts/run_real_odds_backtest.py --db $env:TEMP/nba_audit_work.sqlite3 --sensitivity
```

- Datos: consenso sin margen de apertura y cierre (mediana de ~15–25 casas) publicado por **minmaxxxer** en HuggingFace
  (`nba-closing-lines-ats-2024-25`, `nba-closing-lines-ats-2025-26`, `nba-odds-2026-27`), licencia **CC BY 4.0**.
- Protocolo: evaluación walk-forward estrictamente cronológica; decide al precio de **apertura** con `config/model_config.yaml`
  y mide **CLV contra el cierre**, separando Brier/LogLoss/ECE en raw, calibrado, mercado y anclado.

## 🚀 Ejecución y Comandos

### 1. Entorno de Desarrollo y Verificación CI
```powershell
# Sincronizar dependencias en entorno virtual con uv
uv sync --extra dev --python 3.12

# Ejecutar análisis de calidad (Ruff), tipos estáticos (Mypy) y suite completa de pruebas
uv run ruff check src/ scripts/ tests/
uv run mypy src/
uv run pytest -v --tb=short
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
