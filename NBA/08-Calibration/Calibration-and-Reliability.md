---
date_generated: 2026-11-15T03:23:04Z
brier_score: 0.23434
log_loss: 0.65609
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.23434` (Baseline ingenuo: `0.25485`)
- **Log Loss combinado (ensemble calibrado)**: `0.65609` (Baseline ingenuo: `0.70485`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.21774` vs mercado `0.20683`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
