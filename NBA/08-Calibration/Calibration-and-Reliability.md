---
date_generated: 2026-11-13T21:25:08Z
brier_score: 0.21612
log_loss: 0.61888
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.21612` (Baseline ingenuo: `0.25043`)
- **Log Loss combinado (ensemble calibrado)**: `0.61888` (Baseline ingenuo: `0.69571`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.21612` vs mercado `0.21317`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
