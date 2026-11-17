---
date_generated: 2026-11-17T05:14:57Z
brier_score: 0.22205
log_loss: 0.63180
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.22205` (Baseline ingenuo: `0.24548`)
- **Log Loss combinado (ensemble calibrado)**: `0.63180` (Baseline ingenuo: `0.68480`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.22205` vs mercado `0.22590`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
