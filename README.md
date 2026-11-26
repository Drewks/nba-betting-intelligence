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
| Historial inmutable + Manifiesto por ejecución | ✅ | Triggers SQLite, `audit_row_registry`, tabla append-only `run_manifests` (`commit_sha`, `config_hash`, versiones, calibradores, semillas) y `Shadow Signal Ledger` (`shadow_candidates`). |
| Restauración del historial borrado el 2026-11-09 | ✅ | Migración `2026_11_09_003` (bundle con checksum en `data/recovery/`), cada acción en `audit_repairs`. |
| Gestión de riesgo (`config/model_config.yaml`) | ✅ | Única fuente de verdad: **Kelly fraccional 25% (`kelly_fraction: 0.25`)**, **EV mínimo 2.0% (`min_ev_threshold: 0.02`)**, tope `S/ 10.00` (`max_stake_pen: 10.00`, máx. `10%` banca), mín. `S/ 1.00`, máx. `3` selecciones/jornada, máx. `30%` exposición. |
| Métricas, Holdout y Bonferroni | ✅ | Fail-closed; probabilidades separadas (`raw_model`, `calibrated_model`, `market_fair`, `market_anchored`), `holdout_season: 2026-27` intacto, corrección Bonferroni (`trials_evaluated_count: 11`) y estimador cronológico de cierre (`TotalsClosingEstimator`). |
| CLV & Shadow Signal Ledger | ✅ | `100·(cuota × p_cierre_sin_margen − 1)`, cierre Pinnacle preferido; todas las señales `+EV` (incluidas bloqueadas por `min_ev` / `min_stake` / tope diario) quedan en `shadow_candidates` (1u hipotética) sin tocar la banca S/100. |
| Injury Sniper | 🟡 | Ancla en el mercado; solo cambios de estado NUEVOS (vs. snapshot previo) mueven la probabilidad. Tabla de impacto aún sin calibrar. |
| Casas peruanas (`Betano` & `RETAbet`) | 🟡 | Política explícita `sources.peru_scraper_policy: PUBLIC_READONLY_JSON_API_NO_ANTIBOT_BYPASS`: solo JSON endpoints públicos de lectura sin evasión antibot Cloudflare/Shape; Playwright local desacoplado de GitHub Actions. |
| Player Props & Sub-Bankroll Combinadas | ⛔ | **Deshabilitado por configuración** (`allow_player_props_betting: false`, `allow_parlays: false` en `config/model_config.yaml`; módulo `src/prediction/props/` cuarentenado) — bloqueo fail-closed salvo habilitación explícita. |
| Asignación Híbrida (`evidence_guided` / `70%–30%`) | ✅ | Configurada en `config/model_config.yaml` (`hybrid_allocation.allocation_mode: evidence_guided`): limita a `1` selección/día los mercados en `NO_EDGE` permitiendo hasta `3`/día en mercados con evidencia activa o pendiente (`max_totals_per_matchday: 2`, `max_moneyline_per_matchday: 1` como respaldo en modo `static_caps`). |
| Backtest con cuotas históricas reales | ✅ | `scripts/run_real_odds_backtest.py`: walk-forward cronológico del modelo contra el consenso real de apertura/cierre (datos gratuitos CC BY 4.0) y holdout OOS sin ajuste previo. |
| Hiperparámetros optimizados | ⚪ | El estudio Optuna anterior tenía fuga del resultado (inválido). Se usan priors documentados en `config/model_config.yaml` hasta re-optimizar con holdout limpio. |

---

## 📐 Reglas operativas (`config/model_config.yaml` — vigencia `2026-11-14`)

> [!IMPORTANT]
> Todos los límites numéricos operativos se leen exclusivamente de [`config/model_config.yaml`](config/model_config.yaml) (`model.version_id: model_f_ensemble_v8`). Ninguna documentación ni reporte debe redefinir estos umbrales manualmente.

1. **Benchmark = mercado sin margen**: la calibración del modelo (`raw_model_probability`, `calibrated_model_probability`) se compara contra `market_fair_probability` exactamente sobre los mismos partidos antes del anclaje dinámico al mercado (`market_anchor_schedule` con decaimiento apertura→cierre; peso base `market_anchor_model_weight: 0.30`).
2. **Política de Stake, EV mínimo y Cuota de APIs**:
   - `kelly_fraction`: `0.25` (**25% Quarter-Kelly fraccional**).
   - `min_ev_threshold`: `0.02` (**EV mínimo ≥ 2.0%**; si `EV < 2.0%`, el stake es `S/ 0.00`).
   - Límites por apuesta y jornada: `min_stake_pen: 1.00`, `max_stake_pen: 10.00`, `max_stake_bankroll_fraction: 0.10`, `max_selections_per_matchday: 3`, `max_portfolio_exposure_pct: 0.30`.
   - `allow_player_props_betting`: `false` | `allow_parlays`: `false` (bloqueo fail-closed en código y DB).
   - Conservación de cuota TheOddsAPI: `the_odds_api_regions: eu`, `the_odds_api_markets: h2h,totals`, caché en proceso `300s` (omitiendo días ya `FINAL` y ciclos `settle`).
3. **Solo cuotas observadas**: ninguna cuota estimada, derivada o sintética puede generar una apuesta (`betting_allowed_source_types: ["OBSERVED"]`).
4. **Fuente única de verdad DB (`state-live` vs `main`) e inmutabilidad**:
   - `origin/state-live:data/nba_intelligence.sqlite3.gz` es la **única fuente de verdad viva de producción** (actualizada por `.github/workflows/nba_cloud_automation.yml`).
   - Se guarda comprimida con `gzip -6 -n` porque GitHub rechaza archivos de más de 100 MB (el 2026-11-24 la base ocupaba 59.9 MB y crecía ~14 MB por semana; comprimida, 7.9 MB). Cada workflow la descomprime en `data/nba_intelligence.sqlite3` y se detiene si `PRAGMA integrity_check` no devuelve `ok` ([`src/storage/state_live.py`](src/storage/state_live.py)).
   - `data/nba_intelligence.sqlite3` en `main` permanece congelada como línea base de CI (`.github/workflows/ci.yml` falla si un PR modifica ese archivo).
   - Para extraer (descomprimir) e inspeccionar la DB viva en local sin ensuciar `main`, ejecuta:
     ```powershell
     uv run python scripts/sync_state_live.py --apply-migrations
     ```

---

## 🔒 Regla de merge a `main`

Todo PR exige el check `Lint, Type Check & Pytest Suite` en verde sobre la rama actualizada **y** todos los hilos de revisión resueltos (ruleset de `main`); además se espera a que termine la revisión automática de Codex antes de mergear. Si un PR cambia parámetros de decisión de `config/model_config.yaml`, no se dispara manualmente el ciclo de producción el mismo día.

---

## 🧪 Backtest con cuotas reales (gratis)

```powershell
# Clonar la base viva desde state-live a un archivo temporal antes de experimentar (nunca mutar main)
uv run python scripts/sync_state_live.py --out $env:TEMP/nba_audit_work.sqlite3 --apply-migrations
uv run python scripts/run_real_odds_backtest.py --db $env:TEMP/nba_audit_work.sqlite3 --sensitivity
```

- Datos: consenso sin margen de apertura y cierre (mediana de ~15–25 casas) publicado por **minmaxxxer** en HuggingFace
  (`nba-closing-lines-ats-2024-25`, `nba-closing-lines-ats-2025-26`, `nba-odds-2026-27`), licencia **CC BY 4.0**.
- Protocolo: evaluación walk-forward estrictamente cronológica; decide al precio de **apertura** con `config/model_config.yaml`
  y mide **CLV contra el cierre**, separando Brier/LogLoss/ECE en raw, calibrado, mercado y anclado.
- Misma política que producción: cada decisión pasa por `evaluate_scheduled_market_opportunity` (calendario
  `market_anchor_schedule`, steam) y por las guardas de `config.execution`. La fuente no fecha la apertura: se asume
  publicada al menos `horizon_hours` antes del inicio (pesos de apertura) y el steam es 0 (el cierre sería información futura).

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
