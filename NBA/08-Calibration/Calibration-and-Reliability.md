---
date_generated: 2026-10-29T17:11:49Z
brier_score: 0.245277
log_loss: 0.684113
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.24528` (Baseline: `0.25022`)
- **Log Loss combinado (Modelos C & D)**: `0.68411` (Baseline: `0.69493`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
