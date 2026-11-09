"""
CLI Script to run massive Optuna TPE Hyperparameter Optimization (`scripts/run_optuna_study.py`):
Tunes 6 key parameters across all historical NBA games (2,782 games) in strictly chronological order.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import sys
import time

import optuna

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtesting.hyperparameter_optimizer import (
    _simulate_parametric_ratings_and_preds,
)
from src.calibration.calibrator import compute_brier_score, compute_log_loss
from src.storage.db import DatabaseManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Run massive Optuna Bayesian walk-forward hyperparameter optimization.")
    parser.add_argument("--trials", type=int, default=1000, help="Number of trials (default: 1000)")
    parser.add_argument("--eval-slice", type=int, default=200, help="Out-of-sample evaluation slice size (default: 200)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for TPE sampler")
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"
    db = DatabaseManager(db_path)
    games = db.fetch_all("SELECT * FROM games WHERE status = 'FINAL' ORDER BY game_start_time ASC")

    print("=" * 80)
    print("[OPTUNA] OPTUNA BAYESIAN WALK-FORWARD HYPERPARAMETER OPTIMIZATION (TPE)")
    print("=" * 80)
    print(f"Total Historical Games : {len(games)}")
    print(f"Target Trials          : {args.trials}")
    print(f"Evaluation Slice Size  : {args.eval_slice} games (out-of-sample)")
    print("Objective Metric       : Minimize (Brier Score + 0.5 * Log-Loss)")
    print(f"Started At (UTC)       : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 80)

    # 1. Baseline calculation
    base_raw, base_anch, base_y = _simulate_parametric_ratings_and_preds(
        games=games,
        alpha_slow=0.045,
        alpha_fast=0.110,
        tempo_alpha_slow=0.055,
        tempo_alpha_fast=0.130,
        blowout_cap=28.0,
        market_model_weight=0.30,
        eval_slice_size=args.eval_slice,
    )
    base_brier = compute_brier_score(base_anch, base_y)
    base_logloss = compute_log_loss(base_anch, base_y)
    baseline_score = round(base_brier + 0.5 * base_logloss, 5)

    print("BASELINE SCORE (Default Priors):")
    print(f"  • Brier Score : {base_brier:.5f}")
    print(f"  • Log-Loss    : {base_logloss:.5f}")
    print(f"  • Total Score : {baseline_score:.5f}")
    print("-" * 80)
    print("[START] Ingesting trials into TPE Sampler...\n")

    sampler = optuna.samplers.TPESampler(seed=args.seed)
    study = optuna.create_study(direction="minimize", sampler=sampler)
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    t0 = time.time()
    last_print = t0
    best_so_far = baseline_score

    def objective(trial: optuna.Trial) -> float:
        nonlocal best_so_far, last_print

        alpha_slow = trial.suggest_float("alpha_slow", 0.015, 0.040, step=0.002)
        alpha_fast = trial.suggest_float("alpha_fast", 0.120, 0.190, step=0.005)
        tempo_alpha_slow = trial.suggest_float("tempo_alpha_slow", 0.020, 0.050, step=0.002)
        tempo_alpha_fast = trial.suggest_float("tempo_alpha_fast", 0.060, 0.110, step=0.005)
        blowout_cap = trial.suggest_float("blowout_cap", 22.0, 30.0, step=1.0)
        market_weight = trial.suggest_float("market_model_weight", 0.10, 0.25, step=0.01)
        spread_sigma = trial.suggest_float("spread_sigma", 10.2, 13.0, step=0.1)
        momentum_blend = trial.suggest_float("momentum_blend_weight", 0.75, 0.95, step=0.01)

        _, anch_preds, y_true = _simulate_parametric_ratings_and_preds(
            games=games,
            alpha_slow=alpha_slow,
            alpha_fast=alpha_fast,
            tempo_alpha_slow=tempo_alpha_slow,
            tempo_alpha_fast=tempo_alpha_fast,
            blowout_cap=blowout_cap,
            market_model_weight=market_weight,
            spread_sigma=spread_sigma,
            momentum_blend_weight=momentum_blend,
            eval_slice_size=args.eval_slice,
        )
        brier = compute_brier_score(anch_preds, y_true)
        logloss = compute_log_loss(anch_preds, y_true)
        val = round(brier + 0.5 * logloss, 5)

        num = trial.number + 1
        now = time.time()
        is_new_best = val < best_so_far

        if is_new_best:
            best_so_far = val
            imp = (baseline_score - best_so_far) / baseline_score * 100.0
            print(f"  [NEW BEST] [Trial {num:>4}/{args.trials}] NEW BEST: {best_so_far:.5f} ({imp:+.2f}%) | "
                  f"alpha_fast={alpha_fast:.3f}, alpha_slow={alpha_slow:.3f}, "
                  f"mkt_wt={market_weight:.2f}, blowout_cap={blowout_cap:.0f}")

        elif num % 100 == 0 or (now - last_print) >= 20.0:
            last_print = now
            elapsed = now - t0
            speed = num / elapsed
            rem = (args.trials - num) / speed if speed > 0 else 0
            imp = (baseline_score - best_so_far) / baseline_score * 100.0
            print(f"  [PROGRESS] [Trial {num:>4}/{args.trials}] ({speed:.1f} trials/s | ETA: {rem:.0f}s) - "
                  f"Current Best: {best_so_far:.5f} ({imp:+.2f}%)")

        return val

    study.optimize(objective, n_trials=args.trials)
    t1 = time.time()
    elapsed_total = round(t1 - t0, 2)

    best_val = float(study.best_value)
    best_params = study.best_params
    total_improvement = round(max(0.0, (baseline_score - best_val) / baseline_score) * 100.0, 2)

    # Evaluate best out of sample predictions
    _, best_anch, best_y = _simulate_parametric_ratings_and_preds(
        games=games,
        alpha_slow=best_params["alpha_slow"],
        alpha_fast=best_params["alpha_fast"],
        tempo_alpha_slow=best_params["tempo_alpha_slow"],
        tempo_alpha_fast=best_params["tempo_alpha_fast"],
        blowout_cap=best_params["blowout_cap"],
        market_model_weight=best_params["market_model_weight"],
        spread_sigma=best_params.get("spread_sigma", 11.6),
        momentum_blend_weight=best_params.get("momentum_blend_weight", 0.88),
        eval_slice_size=args.eval_slice,
    )
    final_brier = compute_brier_score(best_anch, best_y)
    final_logloss = compute_log_loss(best_anch, best_y)

    summary: dict[str, Any] = {
        "study_type": "OPTUNA_TPE_8_HYPERPARAMETERS_STUDY",
        "optimized_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_historical_games": len(games),
        "evaluation_slice_size": len(best_y),
        "trials_completed": len(study.trials),
        "elapsed_seconds": elapsed_total,
        "baseline": {
            "score": baseline_score,
            "brier_score": base_brier,
            "log_loss": base_logloss,
        },
        "optimized": {
            "score": best_val,
            "brier_score": final_brier,
            "log_loss": final_logloss,
            "improvement_pct": total_improvement,
        },
        "best_hyperparameters": best_params,
        "parameter_descriptions": {
            "alpha_slow": "Tasa de aprendizaje estructural de largo plazo para rating ofensivo/defensivo",
            "alpha_fast": "Tasa de aprendizaje de momentum reciente (rachas calientes/frías)",
            "tempo_alpha_slow": "Tasa de ajuste de ritmo base de posesiones",
            "tempo_alpha_fast": "Tasa de ajuste de ritmo de alta frecuencia",
            "blowout_cap": "Umbral de margen Huber para filtrar minutos basura en palizas",
            "market_model_weight": "Ponderación bayesiana del modelo vs consenso de mercado de apuestas",
            "spread_sigma": "Desviación típica del margen para conversión a probabilidad (CDF Normal)",
            "momentum_blend_weight": "Ponderación entre rating estructural base y momentum reciente",
        },
    }

    out_file = PROJECT_ROOT / "data" / "evaluation" / "optimal_hyperparameters.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 80)
    print("[COMPLETED] ESTUDIO MASIVO OPTUNA COMPLETADO CON ÉXITO")
    print("=" * 80)
    print(f"Trials Procesados       : {len(study.trials)}")
    print(f"Tiempo Total de Cómputo : {elapsed_total:.2f} s ({len(study.trials) / elapsed_total:.1f} trials/s)")
    print(f"Baseline Score          : {baseline_score:.5f} (Brier: {base_brier:.4f}, LogLoss: {base_logloss:.4f})")
    print(f"Score Optimizado        : {best_val:.5f} (Brier: {final_brier:.4f}, LogLoss: {final_logloss:.4f})")
    print(f"Mejora Porcentual       : +{total_improvement:.2f}%")
    print("-" * 80)
    print("[CONFIG] HIPERPARÁMETROS ÓPTIMOS ENCONTRADOS:")
    for k, v in best_params.items():
        print(f"  • {k:<22}: {v}")
    print("-" * 80)
    print(f"Persistido en: {out_file}")
    print("=" * 80)


if __name__ == "__main__":
    main()
