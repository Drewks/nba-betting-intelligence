"""
CLI for walk-forward hyperparameter optimization (`scripts/run_optuna_study.py`).

Tunes rating hyperparameters on a validation window and decides adoption on an untouched holdout
window (see OptunaWalkForwardOptimizer). The output is a REPORT: parameters are never applied
automatically; a human must review the holdout result and update config/model_config.yaml.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtesting.hyperparameter_optimizer import OptunaWalkForwardOptimizer
from src.storage.db import DatabaseManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward hyperparameter optimization with a final holdout.")
    parser.add_argument("--trials", type=int, default=300)
    parser.add_argument("--eval-slice", type=int, default=300, help="Validation window size (games)")
    parser.add_argument("--holdout", type=int, default=300, help="Untouched final holdout size (games)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=str(PROJECT_ROOT / "data" / "evaluation" / "optimal_hyperparameters.json"))
    args = parser.parse_args()

    db = DatabaseManager(PROJECT_ROOT / "data" / "nba_intelligence.sqlite3")
    games = [
        g
        for g in db.fetch_all("SELECT * FROM games WHERE status = 'FINAL' ORDER BY game_start_time ASC")
        if not str(g["game_id"]).startswith("SYN")
    ]
    summary = OptunaWalkForwardOptimizer(db=db, seed=args.seed).optimize(
        games=games,
        n_trials=args.trials,
        eval_slice_size=args.eval_slice,
        holdout_size=args.holdout,
        output_json_path=args.out,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
