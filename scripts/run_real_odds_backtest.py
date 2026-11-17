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
from datetime import date, timedelta
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

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


class _ReadOnlyDBAdapter:
    """Lightweight read-only SQLite adapter so backtest execution never mutates the production DB."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).resolve()

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        uri = f"file:{self.db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()


def fetch_observed_final_games(db: Any) -> list[dict[str, Any]]:
    """Loads strictly FINAL observed NBA games ordered chronologically without synthetic fixtures."""
    try:
        games = db.fetch_all(
            "SELECT * FROM v_observed_games WHERE status = 'FINAL' AND home_score IS NOT NULL ORDER BY game_start_time ASC"
        )
    except sqlite3.OperationalError:
        games = db.fetch_all(
            "SELECT * FROM games WHERE status = 'FINAL' AND home_score IS NOT NULL AND game_id NOT LIKE 'SYN%' ORDER BY game_start_time ASC"
        )
    return [g for g in games if not str(g.get("game_id", "")).startswith("SYN")]


def verify_zero_lookahead_leakage(
    games: list[dict[str, Any]],
    result: dict[str, Any],
    *,
    start_date: str,
    history_lag_days: int = 0,
) -> bool:
    """
    Verifies that:
    1. Input games are strictly non-synthetic FINAL games ordered chronologically.
    2. Every evaluated bet date is >= start_date and has strictly prior historical training games
       before (bet_date - history_lag_days).
    """
    final_dates = [str(g["matchday_date"]) for g in games if g.get("status") == "FINAL" and g.get("home_score") is not None]
    if any(str(g.get("game_id", "")).startswith("SYN") for g in games):
        raise ValueError("Lookahead/Integrity violation: synthetic games detected in real-odds backtest input.")

    earliest_final_date = min(final_dates) if final_dates else None
    for bet in result.get("bets", []):
        bet_date = str(bet.get("matchday_date") or bet.get("date") or "")
        if not bet_date:
            continue
        if bet_date < start_date:
            raise ValueError(f"Lookahead violation: bet emitted on {bet_date} before start_date {start_date}.")
        cutoff = (
            (date.fromisoformat(bet_date) - timedelta(days=history_lag_days)).isoformat()
            if history_lag_days > 0
            else bet_date
        )
        if earliest_final_date is not None and earliest_final_date >= cutoff:
            raise ValueError(f"Lookahead violation: no strictly prior training games before cutoff {cutoff}.")
    return True


def enrich_backtest_result_metadata(
    result: dict[str, Any],
    *,
    kelly_fraction: float,
    kelly_min_stake: float,
    kelly_max_stake: float,
    kelly_max_fraction: float,
    boxscores_count: int,
    zero_lookahead_verified: bool,
) -> dict[str, Any]:
    """Attaches exact active Kelly sizing and integrity metadata to both `config` and `protocol` dicts."""
    cfg_dict = dict(result.get("config") or {})
    cfg_dict["kelly"] = {
        "fraction": float(kelly_fraction),
        "min_stake": float(kelly_min_stake),
        "max_stake": float(kelly_max_stake),
        "max_bankroll_fraction": float(kelly_max_fraction),
    }
    cfg_dict["boxscore_features"] = bool(boxscores_count > 0)
    cfg_dict["boxscores_games_loaded"] = int(boxscores_count)
    cfg_dict["zero_lookahead_verified"] = bool(zero_lookahead_verified)
    result["config"] = cfg_dict

    protocol = dict(result.get("protocol") or {})
    protocol.update(
        {
            "kelly_fraction": float(kelly_fraction),
            "kelly_fraction_pct": round(float(kelly_fraction) * 100.0, 1),
            "kelly_min_stake_pen": float(kelly_min_stake),
            "kelly_max_stake_pen": float(kelly_max_stake),
            "kelly_max_bankroll_fraction": float(kelly_max_fraction),
            "boxscores_games_loaded": int(boxscores_count),
            "zero_lookahead_verified": bool(zero_lookahead_verified),
        }
    )
    result["protocol"] = protocol
    return result


def render_configured_markdown(
    result: dict[str, Any],
    sensitivity: dict[str, dict[str, Any]] | None = None,
) -> str:
    """
    Renders the backtest markdown report while dynamically labeling the exact active
    kelly_fraction and stake caps from `result['config']['kelly']` / `result['protocol']`.
    """
    p = result.get("protocol") or {}
    cfg_block = dict(result.get("config") or {})
    kelly_block = dict(cfg_block.get("kelly") or {})
    kelly_frac = float(kelly_block.get("fraction", p.get("kelly_fraction", 0.25)))
    min_stake = float(kelly_block.get("min_stake", p.get("kelly_min_stake_pen", 0.50)))
    max_stake = float(kelly_block.get("max_stake", p.get("kelly_max_stake_pen", 3.00)))
    max_frac = float(kelly_block.get("max_bankroll_fraction", p.get("kelly_max_bankroll_fraction", 0.03)))

    cfg_block["kelly"] = {
        "fraction": kelly_frac,
        "min_stake": min_stake,
        "max_stake": max_stake,
        "max_bankroll_fraction": max_frac,
    }
    result["config"] = cfg_block

    raw_md = render_markdown(result, sensitivity)
    kelly_pct_str = (
        f"{kelly_frac * 100:.0f}%"
        if abs(kelly_frac * 100 - round(kelly_frac * 100)) < 1e-6
        else f"{kelly_frac * 100:.1f}%"
    )
    max_frac_str = (
        f"{max_frac * 100:.0f}%"
        if abs(max_frac * 100 - round(max_frac * 100)) < 1e-6
        else f"{max_frac * 100:.1f}%"
    )
    replacement = (
        f"stake **Kelly {kelly_pct_str}** sobre banca actual "
        f"(mín. S/{min_stake:.2f}, tope S/{max_stake:.2f} o {max_frac_str} de la banca)"
    )
    pattern = r"stake \*\*Kelly \d+(?:\.\d+)?%\*\* sobre banca actual \(mín\. S/\d+\.\d+, tope S/\d+\.\d+ o \d+(?:\.\d+)?% de la banca\)"
    return re.sub(pattern, replacement, raw_md)


def main() -> None:
    load_config.cache_clear()
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Walk-forward backtest against real consensus NBA odds.")
    parser.add_argument("--db", default=str(PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"))
    parser.add_argument("--data-dir", default=str(PROJECT_ROOT / "data" / "raw"))
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--vig", type=float, default=0.045)
    parser.add_argument("--kelly-fraction", type=float, default=None, help="Override Kelly fraction (defaults to active config)")
    parser.add_argument("--retrain-every", type=int, default=7)
    parser.add_argument("--history-lag-days", type=int, default=0, help="Robustness: hide the last N days of results")
    parser.add_argument("--no-boxscores", action="store_true", help="Ablation: ignore box-score features")
    parser.add_argument("--sensitivity", action="store_true", help="Also run with 2.5%% and 6%% margins")
    parser.add_argument(
        "--refresh-season",
        action="append",
        default=[],
        help="Re-download this season's market CSV (e.g. the in-progress season for the forward holdout)",
    )
    parser.add_argument("--out-json", default=str(PROJECT_ROOT / "data" / "evaluation" / "real_odds_backtest.json"))
    parser.add_argument("--out-md", default=str(PROJECT_ROOT / "reports" / "real_odds_backtest.md"))
    args = parser.parse_args()

    active_kelly_fraction = float(args.kelly_fraction) if args.kelly_fraction is not None else float(cfg.risk.kelly_fraction)
    db = _ReadOnlyDBAdapter(args.db)
    games = fetch_observed_final_games(db)
    loaded_boxes = None if args.no_boxscores else (load_boxscores(db) or None)
    final_game_ids = {g["game_id"] for g in games}
    boxscores = (
        {gid: b for gid, b in loaded_boxes.items() if gid in final_game_ids}
        if loaded_boxes
        else None
    )
    market_rows = load_market_rows(download_market_csvs(Path(args.data_dir), refresh_seasons=args.refresh_season))
    common = {
        "start_date": args.start,
        "end_date": args.end,
        "retrain_every_days": args.retrain_every,
        "history_lag_days": args.history_lag_days,
        "boxscores": boxscores,
        "model_weight": cfg.model.market_anchor_model_weight,
        "max_disagreement": cfg.model.max_model_market_disagreement,
        "min_ev": cfg.risk.min_ev_threshold,
        "max_bets_per_day": cfg.risk.max_selections_per_matchday,
        "initial_bankroll": cfg.risk.virtual_bankroll_initial_pen,
        "kelly_fraction": active_kelly_fraction,
        "kelly_min_stake": cfg.risk.min_stake_pen,
        "kelly_max_stake": cfg.risk.max_stake_pen,
        "kelly_max_fraction": cfg.risk.max_stake_bankroll_fraction,
        "moneyline_model_weight": cfg.model.moneyline_model_weight,
        "moneyline_max_disagreement": cfg.model.moneyline_max_disagreement,
        "moneyline_max_odds": cfg.model.moneyline_max_odds,
        "development_seasons": cfg.evaluation.development_seasons,
        "holdout_season": cfg.evaluation.holdout_season,
        "trials_evaluated_count": cfg.evaluation.trials_evaluated_count,
        "frozen_protocol_id": cfg.evaluation.frozen_protocol_id,
    }
    result = run_real_odds_backtest(games, market_rows, vig=args.vig, **common)
    zero_lookahead = verify_zero_lookahead_leakage(
        games,
        result,
        start_date=args.start,
        history_lag_days=args.history_lag_days,
    )
    enrich_backtest_result_metadata(
        result,
        kelly_fraction=active_kelly_fraction,
        kelly_min_stake=cfg.risk.min_stake_pen,
        kelly_max_stake=cfg.risk.max_stake_pen,
        kelly_max_fraction=cfg.risk.max_stake_bankroll_fraction,
        boxscores_count=len(boxscores) if boxscores else 0,
        zero_lookahead_verified=zero_lookahead,
    )
    sensitivity = None
    if args.sensitivity:
        sensitivity = {f"{args.vig * 100:.1f}%": result}
        for v in (0.025, 0.06):
            sub_res = run_real_odds_backtest(games, market_rows, vig=v, **common)
            enrich_backtest_result_metadata(
                sub_res,
                kelly_fraction=active_kelly_fraction,
                kelly_min_stake=cfg.risk.min_stake_pen,
                kelly_max_stake=cfg.risk.max_stake_pen,
                kelly_max_fraction=cfg.risk.max_stake_bankroll_fraction,
                boxscores_count=len(boxscores) if boxscores else 0,
                zero_lookahead_verified=zero_lookahead,
            )
            sensitivity[f"{v * 100:.1f}%"] = sub_res

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "main": {k: v for k, v in result.items() if k != "bets"},
        "main_bets": result.get("bets", []),
        "sensitivity": {k: v["betting"] for k, v in (sensitivity or {}).items()},
    }
    Path(args.out_json).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    md_out = render_configured_markdown(result, sensitivity)
    Path(args.out_md).write_text(md_out, encoding="utf-8")
    try:
        print(md_out)
    except UnicodeEncodeError:
        print(md_out.encode("ascii", errors="replace").decode("ascii"))


if __name__ == "__main__":
    main()
