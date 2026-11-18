---
date_generated: 2026-11-18T04:41:54Z
brier_score: 0.22603
log_loss: 0.64396
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.22603` (Baseline ingenuo: `0.24786`)
- **Log Loss combinado (ensemble calibrado)**: `0.64396` (Baseline ingenuo: `0.68993`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.22603` vs mercado `0.23656`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
