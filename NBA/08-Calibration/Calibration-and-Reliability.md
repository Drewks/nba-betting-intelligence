---
date_generated: 2026-10-29T00:29:39Z
brier_score: 0.246272
log_loss: 0.68576
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.24627` (Baseline: `0.24522`)
- **Log Loss combinado (Modelos C & D)**: `0.68576` (Baseline: `0.68354`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
