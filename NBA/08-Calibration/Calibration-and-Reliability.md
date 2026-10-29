---
date_generated: 2026-10-29T00:50:51Z
brier_score: 0.24552
log_loss: 0.684632
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (Modelos C & D)**: `0.24552` (Baseline: `0.25034`)
- **Log Loss combinado (Modelos C & D)**: `0.68463` (Baseline: `0.69522`)
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
