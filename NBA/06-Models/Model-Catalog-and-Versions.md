---
date_generated: 2026-10-29T01:05:27Z
---
# Catálogo de Modelos Cuantitativos (Modelos A–E)

1. **Modelo A (`model_a_baseline_v1`)**: Frecuencia histórica de victoria local y media/desviación de puntos totales.
2. **Modelo B (`model_b_elo_v1`)**: Sistema Elo secuencial con ajuste por localía (+65 Elo) y descanso (+12 Elo/día).
3. **Modelo C (`model_c_point_margin_v1`)**: Regresión Ridge sobre `Offensive Rating`, `Defensive Rating`, `Net Rating`, `Pace`, descanso y forma reciente.
4. **Modelo D (`model_d_total_points_v1`)**: Distribución normal con **covarianza explícita entre marcadores** ($\text{Var}(H+A) = \text{Var}(H) + \text{Var}(A) + 2\text{Cov}(H,A)$).
5. **Modelo E (`model_e_lightgbm_v1`)**: `LightGBM` evaluado estrictamente fuera de muestra mediante validación walk-forward.
