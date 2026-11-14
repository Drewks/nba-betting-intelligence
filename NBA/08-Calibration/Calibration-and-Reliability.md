---
date_generated: 2026-11-14T13:49:33Z
brier_score: 0.21826
log_loss: 0.62318
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.21826` (Baseline ingenuo: `0.25065`)
- **Log Loss combinado (ensemble calibrado)**: `0.62318` (Baseline ingenuo: `0.69592`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.21826` vs mercado `0.21527`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
