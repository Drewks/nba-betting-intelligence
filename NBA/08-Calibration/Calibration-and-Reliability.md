---
date_generated: 2026-11-21T04:15:59Z
brier_score: 0.25285
log_loss: 0.70830
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.25285` (Baseline ingenuo: `0.25281`)
- **Log Loss combinado (ensemble calibrado)**: `0.70830` (Baseline ingenuo: `0.70037`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.25285` vs mercado `0.23659`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
