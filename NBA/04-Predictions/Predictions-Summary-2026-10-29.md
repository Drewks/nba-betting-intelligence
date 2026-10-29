---
date_generated: 2026-10-29T01:05:27Z
model_versions: [model_c_point_margin_v1, model_d_total_points_v1]
---
# Historial Auditable de Predicciones

- Todas las predicciones están protegidas mediante triggers `BEFORE UPDATE` y `BEFORE DELETE` en SQLite (`data/nba_intelligence.sqlite3`).
- Prohibido sobrescribir predicciones o cuotas originales.
