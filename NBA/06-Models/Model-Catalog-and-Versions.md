---
date_generated: 2026-10-30T23:26:32Z
---
# Catálogo de Modelos Cuantitativos (Modelos A–G)

1. **Modelo A (`model_a_baseline_v1`)**: Frecuencia histórica de victoria local y media/desviación de puntos totales.
2. **Modelo B (`model_b_elo_v2`)**: Sistema Elo secuencial con ajuste por localía (+65 Elo) y descanso (+12 Elo/día).
3. **Modelo C (`model_c_point_margin_v2`)**: Regresión Ridge sobre `Offensive Rating`, `Defensive Rating`, `Net Rating`, `Pace`, descanso y forma reciente.
4. **Modelo D (`model_d_total_points_v2`)**: Distribución normal con **covarianza explícita entre marcadores** ($\text{Var}(H+A) = \text{Var}(H) + \text{Var}(A) + 2\text{Cov}(H,A)$).
5. **Modelo E (`model_e_lightgbm_v2`)**: `LightGBM` evaluado estrictamente fuera de muestra mediante validación walk-forward.
6. **Modelo F (`model_f_ensemble_v2`)**: Meta-Ensemble de Sindicato que combina Modelos B, C, D, E y G en escala log-odds con incertidumbre Conformal.
7. **Modelo G (`model_g_ml_montecarlo_v2`)**: **Simulador Híbrido ML + 10,000 Partidos Monte Carlo por Posesión** (modela `Q1–Q3`, desaceleración por `Blowout/Garbage-Time` en `Q4`, faltas intencionales en los últimos 90s `Clutch Fouling` y prórrogas `Overtime OT1/OT2` + intervalos `Conformal Prediction [Q10, Q90]`).
