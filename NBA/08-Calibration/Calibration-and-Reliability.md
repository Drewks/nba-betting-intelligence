---
date_generated: 2026-11-28T15:52:54Z
brier_score: 0.22486
log_loss: 0.63834
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.22486` (Baseline ingenuo: `0.27292`)
- **Log Loss combinado (ensemble calibrado)**: `0.63834` (Baseline ingenuo: `0.74132`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.22486` vs mercado `0.22807`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
