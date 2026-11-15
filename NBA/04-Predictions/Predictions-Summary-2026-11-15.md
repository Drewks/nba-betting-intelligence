---
date_generated: 2026-11-15T04:04:28Z
model_versions: [model_f_ensemble_v8, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]
---
# Historial Auditable de Predicciones

- Todas las predicciones están protegidas mediante triggers `BEFORE UPDATE` y `BEFORE DELETE` en SQLite (`data/nba_intelligence.sqlite3`).
- Prohibido sobrescribir predicciones o cuotas originales.
