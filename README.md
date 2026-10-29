# NBA Betting Intelligence

Sistema cuantitativo multiagente de predicción, calibración y **paper trading exclusivo** para la NBA, coordinado secuencialmente por **Gemini Argon** en **Google Antigravity**.

> [!IMPORTANT]
> **Modo Exclusivo de Simulación**: Este sistema opera únicamente con un bankroll virtual de **S/100.00 PEN**. No realiza apuestas reales, depósitos ni transferencias, ni presupone que exista una ventaja rentable (`edge`).

## Arquitectura Multiagente (Colaboración Secuencial)

1. **`orchestrator`**: Coordinador principal del flujo de 12 etapas con control de errores (máximo 2 reintentos antes de intervención humana).
2. **`nba_data_scout`**: Ingestión mediante adaptadores intercambiables (`ESPNPublicAdapter`, `SportradarAdapter`, `NBAStatsAdapter`, `PlaywrightAuthorizedScraper`, `SyntheticFixtureAdapter`), normalización y validación estricta de timestamps (`available_at < game_start_time`).
3. **`visual_researcher`**: Verificación de estado de PixelRAG/Playwright, extracción documental y registro de confianza (`confidence_score`).
4. **`nba_quant`**: Modelos estadísticos A–E (`Baseline`, `Elo`, `PointMargin`, `TotalPoints` con covarianza, `LightGBM`), desvigado de cuotas (`de-vigging`) y cálculo de Valor Esperado (`EV = p * O - 1`).
5. **`paper_trading_manager`**: Gestión conservadora del bankroll virtual de S/100.00 PEN (stake S/1.00, máximo 3 selecciones por jornada, EV > 5%, registro de `NO_BET` y liquidación inmutable).
6. **`model_calibrator`**: Seguimiento de `Brier Score`, `Log Loss`, `ECE`, curvas de confiabilidad y calibración logística/isotónica mediante validación walk-forward.
7. **`nba_auditor`**: Auditoría independiente de fugas temporales, reconciliación contable, intervalos de confianza por `block bootstrap` y puertas de salida de simulación (mínimo 500 apuestas liquidadas).

## Ejecución Rápida

```powershell
# 1. Sincronizar entorno virtual Python 3.12 con uv
uv sync --extra dev --python 3.12

# 2. Ejecutar la suite completa de 15+ pruebas automatizadas
uv run pytest

# 3. Ejecutar el pipeline completo (walk-forward backtest + jornada en vivo + reportes + Obsidian)
uv run python scripts/run_pipeline.py
```
