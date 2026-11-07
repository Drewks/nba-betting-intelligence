---
name: nba-intelligence-ops
description: Guía operativa institucional para ejecutar, auditar, recalibrar y operar el sistema NBA Betting Intelligence (V8 Quantitative Syndicate: Ensemble Modelos A–G + Monte Carlo, Shin De-Vigging, Optuna 8-HP Walk-Forward, Venn-Abers Conformal Lower-Bound EV, Injury Sniper T-2H/T-30m, Player Props Engine, T-6H Peruvian Sportsbook Scraper con RETAbet/Betsson/Coolbet/Pinnacle, Obsidian DataviewJS Vault y GitHub Pages Auto-Deploy).
---

# NBA Betting Intelligence Operations Skill (`nba-intelligence-ops` — V8)

Utiliza este skill siempre que el usuario solicite ejecutar ciclos de predicción, liquidar apuestas reales de la NBA, auditar el bankroll virtual de **S/100.00 PEN**, escanear cuotas exactas T-6H en casas peruanas (RETAbet, Betsson, Coolbet, Apuesta Total, Doradobet, Te Apuesto, Inkabet, 1xBet, Pinnacle), detectar arbitraje/surebets o mantener la sincronización del Vault de Obsidian (`NBA/`) y GitHub Pages (`https://drewks.github.io/nba-betting-intelligence/`).

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

### D. Ejecutar el Motor de Player Props (PTS, REB, AST, PRA con Redistribución de Uso)
```bash
uv run python scripts/run_player_props.py
```

### E. Optimización Bayesiana Walk-Forward de 8 Hiperparámetros (Optuna TPE)
```bash
uv run python scripts/run_optuna_study.py
```

### F. Ejecutar la Suite Completa de 35 Pruebas Unitarias e Integración
```bash
uv run pytest -q
```

## 3. Reglas Inquebrantables de Gobernanza Cuantitativa
1. **Inmutabilidad SQLite**: Nunca deshabilites los triggers `BEFORE UPDATE` / `BEFORE DELETE` en `predictions` ni `simulated_bets`.
2. **Prevención de Fuga Temporal (Zero Data Leakage)**: Ningún modelo ni calibrador puede entrenarse con partidos cuyo `game_start_time >= cutoff_timestamp`.
3. **Gestión de Capital Convexo en Soles (PEN)**:
   - Asignación simultánea multi-partido mediante **Optimización de Portafolio Kelly (`optimize_simultaneous_kelly_portfolio` con SLSQP)** escalonada entre **S/1.00 PEN y S/6.00 PEN** por apuesta.
   - Máximo **1 apuesta por partido** (filtro anti-correlación entre `moneyline`, `spread` y `total_points`).
   - Bloqueo automático ante movimiento adverso de dinero profesional (**Adverse Sharp Steam Guard**: `steam_delta <= -4.5%`) o incertidumbre conformal excesiva (`conformal_width > 0.22`).
4. **Puertas de Salida (Sección 11)**: El sistema permanece en **Paper Trading** hasta superar las 7 puertas independientes auditadas por `nba_auditor` (`N >= 500` apuestas reales liquidadas y límite inferior del IC 95% Bootstrap > 0%).
