---
date_generated: 2026-11-19T03:23:20Z
brier_score: 0.25681
log_loss: 0.71092
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.25681` (Baseline ingenuo: `0.25008`)
- **Log Loss combinado (ensemble calibrado)**: `0.71092` (Baseline ingenuo: `0.69448`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.25681` vs mercado `0.24501`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
