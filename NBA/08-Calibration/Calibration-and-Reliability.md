---
date_generated: 2026-11-03T02:38:49Z
brier_score: 0.235851
log_loss: 0.66528
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.23585` (Baseline: `0.26115`)
- **Log Loss combinado (Modelos C & D)**: `0.66528` (Baseline: `0.71798`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
