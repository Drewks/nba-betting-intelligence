---
date_generated: 2026-11-09T06:28:34Z
brier_score: 0.205676
log_loss: 0.597132
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.20568` (Baseline: `0.25101`)
- **Log Loss combinado (Modelos C & D)**: `0.59713` (Baseline: `0.69725`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
