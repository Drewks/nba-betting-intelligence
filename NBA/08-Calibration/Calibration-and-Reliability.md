---
date_generated: 2026-10-30T02:58:56Z
brier_score: 0.244814
log_loss: 0.683143
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.24481` (Baseline: `0.25046`)
- **Log Loss combinado (Modelos C & D)**: `0.68314` (Baseline: `0.69563`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
