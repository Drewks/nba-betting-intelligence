"""
CLI: walk-forward backtest of the production model against REAL historical market prices.

Free data (CC BY 4.0): consensus no-vig opening/closing NBA lines published on HuggingFace by
`minmaxxxer` (see src/backtesting/real_odds_backtest.py for the protocol and assumptions).

Usage:
  uv run python scripts/run_real_odds_backtest.py                 # 2025-01-01 onwards, margin 4.5%
  uv run python scripts/run_real_odds_backtest.py --start 2024-12-01 --vig 0.03
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtesting.real_odds_backtest import (
    download_market_csvs,
    load_market_rows,
    render_markdown,
    run_real_odds_backtest,
)
from src.config import load_config
from src.ingestion.boxscores import load_boxscores
from src.storage.db import DatabaseManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward backtest against real consensus NBA odds.")
    parser.add_argument("--db", default=str(PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"))
    parser.add_argument("--data-dir", default=str(PROJECT_ROOT / "data" / "raw"))
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--vig", type=float, default=0.045)
    parser.add_argument("--retrain-every", type=int, default=7)
    parser.add_argument("--history-lag-days", type=int, default=0, help="Robustness: hide the last N days of results")
    parser.add_argument("--no-boxscores", action="store_true", help="Ablation: ignore box-score features")
    parser.add_argument("--sensitivity", action="store_true", help="Also run with 2.5%% and 6%% margins")
    parser.add_argument("--out-json", default=str(PROJECT_ROOT / "data" / "evaluation" / "real_odds_backtest.json"))
    parser.add_argument("--out-md", default=str(PROJECT_ROOT / "reports" / "real_odds_backtest.md"))
    args = parser.parse_args()

    cfg = load_config()
    db = DatabaseManager(args.db)
    games = db.fetch_all("SELECT * FROM games ORDER BY game_start_time ASC")
    boxscores = None if args.no_boxscores else (load_boxscores(db) or None)
    market_rows = load_market_rows(download_market_csvs(Path(args.data_dir)))
    common = {
        "start_date": args.start,
        "end_date": args.end,
        "retrain_every_days": args.retrain_every,
        "history_lag_days": args.history_lag_days,
        "boxscores": boxscores,
        "model_weight": cfg.model.market_anchor_model_weight,
        "min_ev": cfg.risk.min_ev_threshold,
        "max_bets_per_day": cfg.risk.max_selections_per_matchday,
        "initial_bankroll": cfg.risk.virtual_bankroll_initial_pen,
        "kelly_fraction": cfg.risk.kelly_fraction,
        "kelly_min_stake": cfg.risk.min_stake_pen,
        "kelly_max_stake": cfg.risk.max_stake_pen,
        "kelly_max_fraction": cfg.risk.max_stake_bankroll_fraction,
    }
    result = run_real_odds_backtest(games, market_rows, vig=args.vig, **common)
    sensitivity = None
    if args.sensitivity:
        sensitivity = {f"{args.vig * 100:.1f}%": result}
        for v in (0.025, 0.06):
            sensitivity[f"{v * 100:.1f}%"] = run_real_odds_backtest(games, market_rows, vig=v, **common)

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "main": {k: v for k, v in result.items() if k != "bets"},
        "main_bets": result.get("bets", []),
        "sensitivity": {k: v["betting"] for k, v in (sensitivity or {}).items()},
    }
    Path(args.out_json).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    md_out = render_markdown(result, sensitivity)
    Path(args.out_md).write_text(md_out, encoding="utf-8")
    try:
        print(md_out)
    except UnicodeEncodeError:
        print(md_out.encode("ascii", errors="replace").decode("ascii"))


if __name__ == "__main__":
    main()
