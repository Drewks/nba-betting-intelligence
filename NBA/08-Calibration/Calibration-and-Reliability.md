---
date_generated: 2026-11-15T03:30:37Z
brier_score: 0.23650
log_loss: 0.66311
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.23650` (Baseline ingenuo: `0.25427`)
- **Log Loss combinado (ensemble calibrado)**: `0.66311` (Baseline ingenuo: `0.70364`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.21922` vs mercado `0.20683`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
