---
date_generated: 2026-11-16T02:00:51Z
brier_score: 0.16617
log_loss: 0.50140
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.16617` (Baseline ingenuo: `0.24614`)
- **Log Loss combinado (ensemble calibrado)**: `0.50140` (Baseline ingenuo: `0.68643`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.16617` vs mercado `0.17913`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
