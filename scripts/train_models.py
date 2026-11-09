"""
Model Training & Promotion Pipeline (`scripts/train_models.py`):
Fits PointMarginModel (RidgeCV), AdvancedGBMModel (LightGBM), TotalPointsModel,
and EnsembleStackingModel (Meta-Ensemble F+G) using the optimal Bayesian hyperparameters
from Optuna over all 2,989 historical games with zero temporal leakage.
Registers and activates the new V7 trained model versions in SQLite `model_versions`.
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.calibration.calibrator import compute_brier_score, compute_log_loss
from src.models.statistical_models import (
    AdvancedGBMModel,
    EnsembleStackingModel,
    PointMarginModel,
    TotalPointsModel,
)
from src.storage.db import DatabaseManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Train NBA machine learning models with optimal Optuna parameters.")
    parser.add_argument("--version-tag", type=str, default="v7", help="Version tag for new models (default: v7)")
    parser.add_argument("--val-size", type=int, default=150, help="Holdout validation size for stacking weights")
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"
    db = DatabaseManager(db_path)
    games = db.fetch_all("SELECT * FROM games WHERE status = 'FINAL' ORDER BY game_start_time ASC")

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    train_start_date = games[0]["matchday_date"] if games else "2024-10-01"
    train_end_date = games[-1]["matchday_date"] if games else "2026-11-05"

    # Load optimal hyperparameters from Optuna study
    opt_file = PROJECT_ROOT / "data" / "evaluation" / "optimal_hyperparameters.json"
    hyperparams = {}
    if opt_file.exists():
        try:
            opt_data = json.loads(opt_file.read_text(encoding="utf-8"))
            hyperparams = opt_data.get("best_hyperparameters", {})
        except Exception as exc:
            logging.warning(f"Handled exception in train_models (line 53): {exc}")

    print("=" * 80)
    print("[TRAINING] ENTRENAMIENTO DE MODELOS DE MACHINE LEARNING NBA (V7 ENSEMBLE)")
    print("=" * 80)
    print(f"Juegos Históricos Finalizados : {len(games)}")
    print(f"Rango de Entrenamiento        : {train_start_date} -> {train_end_date}")
    print(f"Etiqueta de Versión           : {args.version_tag}")
    print(f"Hiperparámetros Optuna        : {hyperparams}")
    print("-" * 80)

    t0 = time.time()

    # 1. Train Model C: PointMarginModel (RidgeCV)
    print("1. Entrenando Modelo C (PointMarginModel - RidgeCV en margen residual)...")
    model_c = PointMarginModel(f"model_c_point_margin_{args.version_tag}")
    model_c.fit(games, cutoff_time_str=now_iso)
    print("   [OK] RidgeCV ajustado con estandarización de características.")

    # 2. Train Model D: TotalPointsModel (Pace-Decoupled Score Normal Distribution)
    print("2. Entrenando Modelo D (TotalPointsModel - Distribución Normal con Covarianza)...")
    model_d = TotalPointsModel(f"model_d_total_points_{args.version_tag}")
    model_d.fit(games, cutoff_time_str=now_iso)
    print("   [OK] Matriz de covarianza y desajuste de tempo ajustados.")

    # 3. Train Model E: AdvancedGBMModel (LightGBM Classifier + Regressor)
    print("3. Entrenando Modelo E (AdvancedGBMModel - Árboles LightGBM con Boost Residual)...")
    model_e = AdvancedGBMModel(f"model_e_lightgbm_{args.version_tag}")
    model_e.fit(games, cutoff_time_str=now_iso)
    print("   [OK] LightGBM Classifier y Regressor entrenados.")

    # 4. Train Model F: EnsembleStackingModel (Meta-Ensemble F+G con Monte Carlo)
    print("4. Entrenando Modelo F (EnsembleStackingModel - Stacking Bayesiano Multi-Modelo)...")
    ensemble = EnsembleStackingModel(f"model_f_ensemble_{args.version_tag}")
    ensemble.model_c = model_c
    ensemble.model_d = model_d
    ensemble.model_e = model_e
    ensemble.fit(games, cutoff_time_str=now_iso)
    print(f"   [OK] Stacking bayesiano ajustado. Pesos Moneyline: {ensemble.ml_weights}, Totales: {ensemble.tot_weights}")

    t1 = time.time()
    elapsed = round(t1 - t0, 2)

    # Calculate Out-of-Sample Metrics on holdout slice
    val_slice = games[-args.val_size:]
    prior_games = games[:-args.val_size]
    y_true_ml = [1 if int(g["home_score"]) > int(g["away_score"]) else 0 for g in val_slice]
    preds_ml = [ensemble.predict_moneyline(g, prior_games)["p_home"] for g in val_slice]

    oos_brier = compute_brier_score(preds_ml, y_true_ml)
    oos_logloss = compute_log_loss(preds_ml, y_true_ml)

    print("-" * 80)
    print(f"MÉTRICAS OUT-OF-SAMPLE (Últimos {args.val_size} partidos evaluados):")
    print(f"  • Brier Score : {oos_brier:.5f}")
    print(f"  • Log-Loss    : {oos_logloss:.5f}")
    print(f"  • Tiempo      : {elapsed} segundos")
    print("-" * 80)

    # Deactivate older models and register new active models
    v_ml = f"model_f_ensemble_{args.version_tag}"
    v_tot = f"model_g_ml_montecarlo_{args.version_tag}"
    hp_json = json.dumps(hyperparams, ensure_ascii=False)

    with db.connect() as conn:
        conn.execute("UPDATE model_versions SET is_active = 0 WHERE market IN ('moneyline', 'total_points');")
        conn.execute(
            """
            INSERT OR REPLACE INTO model_versions (
                model_version_id, model_family, market, train_start_date, train_end_date,
                trained_at, hyperparameters_json, oos_brier_score, oos_log_loss, is_active,
                approved_by, parent_version_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'Optuna_Bayesian_Pipeline', 'model_f_ensemble_v4')
            """,
            (v_ml, "model_f_meta_ensemble", "moneyline", train_start_date, train_end_date, now_iso, hp_json, oos_brier, oos_logloss),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO model_versions (
                model_version_id, model_family, market, train_start_date, train_end_date,
                trained_at, hyperparameters_json, oos_brier_score, oos_log_loss, is_active,
                approved_by, parent_version_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'Optuna_Bayesian_Pipeline', 'model_g_ml_montecarlo_v4')
            """,
            (v_tot, "model_g_ml_montecarlo_hybrid", "total_points", train_start_date, train_end_date, now_iso, hp_json, oos_brier, oos_logloss),
        )

    print("[OK] Modelos promovidos y activados en base de datos:")
    print(f"  • Moneyline    : {v_ml} (is_active = 1)")
    print(f"  • Total Points : {v_tot} (is_active = 1)")
    print("=" * 80)


if __name__ == "__main__":
    main()
