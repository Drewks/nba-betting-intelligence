---
date_generated: 2026-11-09T01:59:45Z
brier_score: 0.208562
log_loss: 0.603919
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.20856` (Baseline: `0.24961`)
- **Log Loss combinado (Modelos C & D)**: `0.60392` (Baseline: `0.69453`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
