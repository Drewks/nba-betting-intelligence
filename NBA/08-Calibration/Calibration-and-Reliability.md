---
date_generated: 2026-11-10T14:07:27Z
brier_score: 0.21685
log_loss: 0.62085
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.21685` (Baseline ingenuo: `0.25079`)
- **Log Loss combinado (ensemble calibrado)**: `0.62085` (Baseline ingenuo: `0.69663`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.21685` vs mercado `0.21371`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
