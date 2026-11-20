---
date_generated: 2026-11-20T04:15:33Z
brier_score: 0.25253
log_loss: 0.71003
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.25253` (Baseline ingenuo: `0.25171`)
- **Log Loss combinado (ensemble calibrado)**: `0.71003` (Baseline ingenuo: `0.69797`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.25253` vs mercado `0.23961`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
