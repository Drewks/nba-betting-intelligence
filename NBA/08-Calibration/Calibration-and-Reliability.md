---
date_generated: 2026-11-04T14:40:04Z
brier_score: 0.231403
log_loss: 0.654242
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.23140` (Baseline: `0.25478`)
- **Log Loss combinado (Modelos C & D)**: `0.65424` (Baseline: `0.70377`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
