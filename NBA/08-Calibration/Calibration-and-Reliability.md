---
date_generated: 2026-11-07T13:13:07Z
brier_score: 0.211465
log_loss: 0.610637
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.21146` (Baseline: `0.24815`)
- **Log Loss combinado (Modelos C & D)**: `0.61064` (Baseline: `0.69202`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
