---
date_generated: 2026-11-09T16:54:27Z
brier_score: 0.217055
log_loss: 0.622362
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.21705` (Baseline: `0.25094`)
- **Log Loss combinado (Modelos C & D)**: `0.62236` (Baseline: `0.69700`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
