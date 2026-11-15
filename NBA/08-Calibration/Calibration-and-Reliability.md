---
date_generated: 2026-11-15T14:21:37Z
brier_score: 0.23715
log_loss: 0.66463
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.23715` (Baseline ingenuo: `0.25414`)
- **Log Loss combinado (ensemble calibrado)**: `0.66463` (Baseline ingenuo: `0.70336`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.21938` vs mercado `0.20683`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
