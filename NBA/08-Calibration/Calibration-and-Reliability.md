---
date_generated: 2026-11-17T00:16:29Z
brier_score: 0.15641
log_loss: 0.47997
---
# Seguimiento de Calibración Probabilística (`model_calibrator`)

- **Brier Score combinado (ensemble calibrado)**: `0.15641` (Baseline ingenuo: `0.24479`)
- **Log Loss combinado (ensemble calibrado)**: `0.47997` (Baseline ingenuo: `0.68366`)
- **Frente al mercado sin margen (mismos partidos)**: modelo `0.15641` vs mercado `0.17040`
- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.
