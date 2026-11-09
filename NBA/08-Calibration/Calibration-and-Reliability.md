---
date_generated: 2026-11-09T23:48:11Z
brier_score: 0.21689
log_loss: 0.62112
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.21689` (Baseline ingenuo: `0.25252`)
- **Log Loss combinado (ensemble calibrado)**: `0.62112` (Baseline ingenuo: `0.70030`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.21689` vs mercado `0.21376`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
