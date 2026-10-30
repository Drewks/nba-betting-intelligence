---
date_generated: 2026-10-30T23:26:32Z
brier_score: 0.244754
log_loss: 0.68301
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.24475` (Baseline: `0.25012`)
- **Log Loss combinado (Modelos C & D)**: `0.68301` (Baseline: `0.69490`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
