---
name: nba-intelligence-ops
description: Guía operativa institucional para ejecutar, auditar, recalibrar y operar el sistema NBA Betting Intelligence (V8 Frozen Protocol: Dean Oliver Four Factors, Ensemble A-G, CLV Meta-Labeling, Venn-Abers Conformal Interval, Injury Sniper T-2H/T-30m, Public Read-Only Peru/Pinnacle Odds APIs sin antibot bypass, Shadow Signal Ledger, Obsidian Vault y GitHub Pages Auto-Deploy).
---

# NBA Betting Intelligence Operations Skill (`nba-intelligence-ops` — V8)

Utiliza este skill siempre que el usuario solicite ejecutar ciclos de predicción, liquidar apuestas reales de la NBA, auditar el bankroll virtual de **S/100.00 PEN**, sincronizar cuotas `OBSERVED` públicas sin bypass antibot (política `PUBLIC_READONLY_JSON_API_NO_ANTIBOT_BYPASS`) o mantener el Vault de Obsidian (`NBA/`), `origin/state-live` y GitHub Pages (`https://drewks.github.io/nba-betting-intelligence/`).

## 1. Arquitectura de Datos y Gobernanza (Cero Datos Sintéticos en Producción)
- **Fuente Primaria en Tiempo Real (`espn_real`)**: `ESPNPublicAdapter` consulta `site.api.espn.com` con enriquecimiento de boxscores en vivo, árbitros (`referee_total_adj`, `referee_hca_adj`) y regresión a la media de acierto triple (`3PT luck mean-reversion`).
- **Telemetría Oficial y Lesiones (`SportradarAdapter`)**: Conecta con **Sportradar NBA API v8** y **Synergy Basketball NBA API** + el monitor **Injury Sniper Dual-Window (`T-2H` y `T-30m`)** en `src/prediction/injury_sniper.py`.
- **Line Shopping Multi-Casa Internacional y Perú (`TheOddsAPIAdapter` + `peru_scraper.py` + `peru_sportsbooks.py`)**:
  - Escanea hasta 25+ casas globales y ancla las 9 principales casas que operan en Perú (reguladas por MINCETUR como **RETAbet**, **Betsson**, **Coolbet**, **Apuesta Total**, **Doradobet**, **Inkabet**, **Te Apuesto**, más **1xBet** y **Pinnacle Sharp**).
  - Calcula probabilidades justas mediante **Método de Shin (`devig_shin`)** y **Power Method (`devig_power`)** para corregir el *Favorite-Longshot Bias (FLB)*.
  - Detecta automáticamente **Arbitraje / Surebets** y oportunidades **+EV en Soles (`S/. PEN`)** con `detect_peru_market_inefficiencies()`.
  - Captura e inmutabiliza las cuotas exactas **6 horas antes del tipoff (`T_MINUS_6H_EXACT`)** en la tabla SQLite `peru_odds_t6h`.
- **Aislamiento Estricto**: `PaperTradingEngine` opera con `exclude_synthetic=True`.

## 2. Comandos Operativos Clave

### A. Ejecutar el Ciclo Completo de Producción (Ingesta, Predicción, Liquidación, Dashboard y Obsidian)
```bash
uv run python scripts/run_daily_cycle.py --adapter espn_real --cycle-mode auto
```

### B. Capturar Cuotas Exactas de Perú a T-6H (`peru_odds_t6h`) y Refrescar Dashboard
```bash
uv run python scripts/run_peru_odds_scraper.py
```

### C. Ejecutar el Monitor de Lesiones Pre-Partido (Injury Sniper T-2H / T-30m)
```bash
uv run python scripts/run_injury_sniper.py
```

### D. Módulo Exploratorio Cuarentenado (`src/prediction/props/`, deshabilitado en `model_config.yaml`)
```bash
uv run python scripts/run_player_props.py
```

### E. Sincronizar DB viva desde `origin/state-live` (sin tocar `main`)
```bash
uv run python scripts/sync_state_live.py --apply-migrations
```

### F. Ejecutar la Suite Completa de Pruebas (`ruff`, `mypy`, `pytest`)
```bash
uv run pytest -q
```

## 3. Reglas Inquebrantables de Gobernanza Cuantitativa
1. **Inmutabilidad SQLite y DB Provenance**: Nunca deshabilites los triggers `BEFORE UPDATE` / `BEFORE DELETE` en `predictions`, `simulated_bets` ni `shadow_candidates`. `origin/state-live` es la única DB viva de producción; `main` permanece congelada para CI.
2. **Prevención de Fuga Temporal (Zero Data Leakage)**: Ningún modelo ni calibrador puede entrenarse con partidos cuyo `game_start_time >= cutoff_timestamp`; `holdout_season: 2026-27` permanece intacto.
3. **Gestión de Capital Convexo en Soles (PEN) (`config/model_config.yaml`)**:
   - **Quarter Kelly fraccional (`kelly_fraction: 0.25`)**, **EV mínimo (`min_ev_threshold: 0.02`)**, escalonada entre **S/1.00 PEN y S/10.00 PEN** por selección (máx. 10% banca, máx. 3 selecciones/día, exposición ≤ 30%). `allow_parlays: false`, `allow_player_props_betting: false`, solo cuotas `OBSERVED`.
   - Máximo **1 apuesta por partido** en ledger oficial; señales `+EV` adicionales o filtradas por piso/tope quedan en **`shadow_candidates`** (1u hipotética).
   - Bloqueo automático ante movimiento adverso de dinero profesional (**Adverse Sharp Steam Guard**: `steam_delta <= -4.5%`) o incertidumbre conformal excesiva (`conformal_width > 0.22`).
4. **Puertas de Salida (Sección 11)**: El sistema permanece en **Paper Trading** hasta superar las **10 puertas independientes** auditadas por `nba_auditor` (`N >= 500` apuestas reales liquidadas, mercado sin margen `gate_10`, e IC 95% Block Bootstrap > 0%).
