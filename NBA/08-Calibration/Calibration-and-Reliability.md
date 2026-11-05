---
date_generated: 2026-11-05T22:44:01Z
brier_score: 0.227718
log_loss: 0.645276
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.22772` (Baseline: `0.24924`)
- **Log Loss combinado (Modelos C & D)**: `0.64528` (Baseline: `0.69205`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
