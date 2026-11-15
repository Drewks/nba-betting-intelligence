---
date_generated: 2026-11-15T02:13:54Z
brier_score: null
log_loss: null
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `n/d` (Baseline ingenuo: `0.25065`)
- **Log Loss combinado (ensemble calibrado)**: `n/d` (Baseline ingenuo: `0.69592`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `n/d` vs mercado `0.21527`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
