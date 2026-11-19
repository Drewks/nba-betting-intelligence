---
date_generated: 2026-11-19T04:29:28Z
brier_score: 0.25257
log_loss: 0.70192
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.25257` (Baseline ingenuo: `0.25003`)
- **Log Loss combinado (ensemble calibrado)**: `0.70192` (Baseline ingenuo: `0.69437`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.25257` vs mercado `0.24135`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
