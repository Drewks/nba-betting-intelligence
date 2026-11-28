---
date_generated: 2026-11-28T15:52:54Z
model_versions: [model_f_ensemble_v9, model_b_elo_v8, model_c_point_margin_v9, model_d_total_points_v9, model_e_lightgbm_v9, model_g_ml_montecarlo_v9, model_h_ridge_rapm_v9]
---
# Historial Auditable de Predicciones

- Todas las predicciones están protegidas mediante triggers `BEFORE UPDATE` y `BEFORE DELETE` en SQLite (`data/nba_intelligence.sqlite3`).
- Prohibido sobrescribir predicciones o cuotas originales.
