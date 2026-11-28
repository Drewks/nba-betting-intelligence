---
date_generated: 2026-11-28T15:52:54Z
---
# Catálogo de Modelos Cuantitativos (Modelos A–H)

1. **Modelo A (`model_a_baseline_v1`)**: Frecuencia histórica de victoria local y media/desviación de puntos totales.
2. **Modelo B (`model_b_elo_v8`)**: Sistema Elo secuencial con ajuste por localía (+65 Elo) y descanso (+12 Elo/día).
3. **Modelo C (`model_c_point_margin_v9`)**: Regresión RidgeCV sobre eficiencia ajustada Ridge/RAPM, `Offensive/Defensive Rating`, `Pace`, descanso y forma reciente.
4. **Modelo D (`model_d_total_points_v9`)**: Regresión Ridge de totales con ritmo exacto de 48 minutos, RAPM ofensivo/defensivo y **covarianza explícita entre marcadores** ($\text{Var}(H+A) = \text{Var}(H) + \text{Var}(A) + 2\text{Cov}(H,A)$).
5. **Modelo E (`model_e_lightgbm_v9`)**: `LightGBM` residual sobre priors lineales evaluado estrictamente fuera de muestra mediante validación walk-forward.
6. **Modelo F (`model_f_ensemble_v9`)**: Meta-Ensemble de Sindicato que combina Modelos B, C, D, E, G y H mediante apilamiento convexo walk-forward.
7. **Modelo G (`model_g_ml_montecarlo_v9`)**: **Simulador Híbrido ML + 10,000 Partidos Monte Carlo por Posesión** (modela `Q1–Q3`, desaceleración por `Blowout/Garbage-Time` en `Q4`, faltas intencionales en los últimos 90s `Clutch Fouling` y prórrogas iterativas `Overtime` + percentiles de simulación `[Q10, Q90]`).
8. **Modelo H (`model_h_ridge_rapm_v9`)**: Motor simultáneo Ridge multi-horizonte de eficiencia ajustada por calendario y RAPM de jugadores informado por priors causales.
