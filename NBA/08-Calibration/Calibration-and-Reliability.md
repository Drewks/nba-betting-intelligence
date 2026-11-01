---
date_generated: 2026-11-01T17:11:29Z
brier_score: 0.236967
log_loss: 0.667733
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.23697` (Baseline: `0.26520`)
- **Log Loss combinado (Modelos C & D)**: `0.66773` (Baseline: `0.72662`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
