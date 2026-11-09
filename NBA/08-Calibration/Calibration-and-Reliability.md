---
date_generated: 2026-11-08T23:59:51Z
brier_score: 0.204929
log_loss: 0.596347
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.20493` (Baseline: `0.25095`)
- **Log Loss combinado (Modelos C & D)**: `0.59635` (Baseline: `0.69735`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
