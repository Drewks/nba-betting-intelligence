---
date_generated: 2026-10-31T01:30:11Z
brier_score: 0.223689
log_loss: 0.638387
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.22369` (Baseline: `0.25432`)
- **Log Loss combinado (Modelos C & D)**: `0.63839` (Baseline: `0.70247`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
