---
date_generated: 2026-11-08T21:29:31Z
brier_score: 0.204994
log_loss: 0.59651
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.20499` (Baseline: `0.24941`)
- **Log Loss combinado (Modelos C & D)**: `0.59651` (Baseline: `0.69407`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
