---
date_generated: 2026-10-31T17:02:35Z
brier_score: 0.251328
log_loss: 0.700378
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.25133` (Baseline: `0.25959`)
- **Log Loss combinado (Modelos C & D)**: `0.70038` (Baseline: `0.71404`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
