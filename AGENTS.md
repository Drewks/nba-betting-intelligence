# NBA Betting Intelligence — Multi-Agent Governance & Rules (`AGENTS.md`)

Este repositorio implementa un sistema cuantitativo multiagente de predicción, calibración y **paper trading exclusivo** para la NBA, coordinado secuencialmente por un **Orquestador Multiagente Python** (`src/orchestrator.py` / `scripts/run_cloud_cycle.py`) con trazabilidad auditable y ejecución continua en GitHub Actions.

## 1. Principios Inquebrantables de Operación

1. **Simulación Estricta (Paper Trading Exclusivo)**:
   - El sistema opera exclusivamente con un bankroll virtual inicial de **S/100.00 PEN** (`100.00 PEN`).
   - Está terminantemente prohibido conectarse a casas de apuestas para colocar apuestas reales, depósitos, retiros o transferencias.
2. **Colaboración Secuencial**:
   - Los agentes especializados (`nba_data_scout`, `visual_researcher`, `nba_quant`, `paper_trading_manager`, `model_calibrator`, `nba_auditor`) nunca deben ejecutarse en paralelo sobre el mismo lote de decisión.
   - El coordinador (`orchestrator`) espera la entrega validada de cada fase antes de invocar al siguiente agente, con un máximo de **2 reintentos controlados** ante fallos antes de escalar a intervención humana.
3. **Integridad Temporal (Cero Fuga de Información / No Lookahead Bias)**:
   - Ninguna característica (`feature`), cuota (`odds`), parámetro de modelo (`model_weights`) ni curva de calibración puede utilizar información con `timestamp >= game_start_time`.
4. **Inmutabilidad del Historial**:
   - Las predicciones emitidas, las cuotas capturadas al momento de la decisión y las apuestas simuladas (incluyendo decisiones `NO_BET`) son inmutables tras su registro en SQLite.
   - Nunca se eliminan predicciones perdedoras ni se alteran cuotas retrospectivamente.
5. **Escepticismo Estadístico**:
   - No se presupone ventaja rentable (`edge`).
   - La selección y promoción de modelos se basa en métricas fuera de muestra (`Brier Score`, `Log Loss`, curvas de confiabilidad, incertidumbre por `block bootstrap`) y nunca únicamente en el ROI histórico.

## 2. Catálogo de Agentes Especializados

- [`orchestrator`](.agents/agents/orchestrator.md): Coordinador principal del flujo de 12 pasos, control de errores y consolidación.
- [`nba_data_scout`](.agents/agents/nba_data_scout.md): Ingestión mediante adaptadores intercambiables, normalización y validación temporal/estructural.
- [`visual_researcher`](.agents/agents/visual_researcher.md): Inspección documental/visual (con verificación de estado de PixelRAG/Playwright) y registro de confianza.
- [`nba_quant`](.agents/agents/nba_quant.md): Modelos estadísticos A–E (`Baseline`, `Elo`, `PointMargin`, `TotalPoints` con covarianza, `LightGBM`), de-vigging y cálculo de EV.
- [`paper_trading_manager`](.agents/agents/paper_trading_manager.md): Gestión del bankroll virtual de S/100 PEN con sizing conservador calibrado en [`config/model_config.yaml`](config/model_config.yaml) (Kelly fraccional activo **25%**, con techo duro normativo de **50%**; S/1.00–S/10.00 y máx. 10% de la banca por selección; stake 0 si EV < **2.0%**; máx. 3 selecciones/jornada; exposición pendiente ≤ 30%). Combinadas/SGP y player props están **deshabilitados** por política operativa (`allow_parlays: false`, `allow_player_props_betting: false`, solo cuotas `OBSERVED`); existe además un **Shadow Signal Ledger** (`shadow_candidates`, 1u sin piso de Kelly ni tope diario) para medir CLV y EV real potencial sin contaminar métricas ni bankroll oficial. La rama `origin/state-live` es la única fuente viva de producción (`data/nba_intelligence.sqlite3` en `main` es el fixture base congelado para CI).
- [`model_calibrator`](.agents/agents/model_calibrator.md): Seguimiento de Brier Score, Log Loss, calibración logística/isotónica y promoción walk-forward.
- [`nba_auditor`](.agents/agents/nba_auditor.md): Auditoría independiente de fugas temporales, reconciliación contable, intervalos de confianza y puertas de validación (500 apuestas mínimas).
