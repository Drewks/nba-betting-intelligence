---
date_generated: 2026-11-21T14:58:46Z
brier_score: 0.24885
log_loss: 0.69822
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.24885` (Baseline ingenuo: `0.25207`)
- **Log Loss combinado (ensemble calibrado)**: `0.69822` (Baseline ingenuo: `0.69883`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.24885` vs mercado `0.23308`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
