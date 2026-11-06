---
name: nba-intelligence-ops
description: >-
  Runbook operativo y de auditoría cuantitativa para el sistema NBA Betting Intelligence V6.
  Activar cuando el usuario pida actualizar cuotas/partidos NBA, liquidar apuestas pendientes,
  regenerar el dashboard interactivo (reports/dashboard.html y SEGUIMIENTO_APUESTAS.md),
  ejecutar la suite de 27 tests anti-leakage o auditar el bankroll en S/ PEN.
---

# NBA Betting Intelligence V6 — Skill Operativo

## 1. Comandos Principales de Ejecución

Siempre ejecutar desde la raíz del repositorio (`C:\Users\faboa\.gemini\antigravity\scratch\nba-betting-intelligence`) usando `uv run`:

1. **Ciclo completo en la nube/local (`auto`: ingesta + liquidación + calibración + nuevas apuestas + dashboard)**:
   ```powershell
   uv run python scripts/run_cloud_cycle.py --mode auto
   ```
2. **Solo captura de cuotas pre-partido y emisión de selecciones (`pregame`)**:
   ```powershell
   uv run python scripts/run_cloud_cycle.py --mode pregame
   ```
3. **Solo liquidación de resultados oficiales y recalibración (`settle_and_calibrate`)**:
   ```powershell
   uv run python scripts/run_cloud_cycle.py --mode settle_and_calibrate
   ```
4. **Regeneración rápida (<5s) del Dashboard HTML y Markdown sin llamadas de red**:
   ```powershell
   uv run python -c "from pathlib import Path; from src.storage.db import DatabaseManager; from src.paper_trading.engine import PaperTradingEngine; from src.backtesting.backtester import WalkForwardBacktester; from src.reporting.reporter import export_bets_and_tracking_dashboard; root = Path('.'); db = DatabaseManager(root / 'data/nba_intelligence.sqlite3'); pe = PaperTradingEngine(db, initial_bankroll_pen=100.0, base_stake_pen=1.0, max_stake_pen=6.0, min_ev_threshold=0.02, dynamic_conviction_staking=True, exclude_synthetic=True); m = WalkForwardBacktester(db, pe).compute_comprehensive_metrics([]); export_bets_and_tracking_dashboard(db, m, root / 'data/apuestas_historial.csv', root / 'SEGUIMIENTO_APUESTAS.md')"
   ```
5. **Disparo remoto sin latencia hacia GitHub Actions (`workflow_dispatch`)**:
   ```powershell
   uv run python scripts/dispatch_cycle.py --mode pregame
   ```

## 2. Verificación e Integridad Anti-Leakage

- Ejecutar la suite completa de 27 pruebas unitarias y de integración:
  ```powershell
  uv run pytest tests/test_nba_intelligence.py -q
  ```
- Reglas inquebrantables:
  - Ninguna cuota con `captured_at >= game_start_time` puede usarse para calcular EV pre-partido.
  - Máximo 1 apuesta por partido (`Anti-Correlación`) y bloqueo automático ante `ADVERSE_SHARP_STEAM_MOVE` (`>= 2.5%` de movimiento implícito en contra).
