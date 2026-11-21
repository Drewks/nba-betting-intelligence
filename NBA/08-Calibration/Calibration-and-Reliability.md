---
date_generated: 2026-11-21T03:13:47Z
brier_score: 0.25318
log_loss: 0.71018
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.25318` (Baseline ingenuo: `0.25346`)
- **Log Loss combinado (ensemble calibrado)**: `0.71018` (Baseline ingenuo: `0.70174`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.25318` vs mercado `0.23815`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
