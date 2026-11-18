---
date_generated: 2026-11-18T16:02:05Z
brier_score: 0.23680
log_loss: 0.67140
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.23680` (Baseline ingenuo: `0.24715`)
- **Log Loss combinado (ensemble calibrado)**: `0.67140` (Baseline ingenuo: `0.68846`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.23680` vs mercado `0.23808`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
