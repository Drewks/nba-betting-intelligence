---
date_generated: 2026-11-01T00:24:56Z
brier_score: 0.247228
log_loss: 0.691594
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.24723` (Baseline: `0.25699`)
- **Log Loss combinado (Modelos C & D)**: `0.69159` (Baseline: `0.70869`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
