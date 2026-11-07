---
date_generated: 2026-11-07T02:23:22Z
brier_score: 0.226223
log_loss: 0.642386
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.22622` (Baseline: `0.24224`)
- **Log Loss combinado (Modelos C & D)**: `0.64239` (Baseline: `0.67773`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
