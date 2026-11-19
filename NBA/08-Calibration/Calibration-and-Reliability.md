---
date_generated: 2026-11-19T16:07:23Z
brier_score: 0.25808
log_loss: 0.72484
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.25808` (Baseline ingenuo: `0.25102`)
- **Log Loss combinado (ensemble calibrado)**: `0.72484` (Baseline ingenuo: `0.69645`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.25808` vs mercado `0.24699`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
