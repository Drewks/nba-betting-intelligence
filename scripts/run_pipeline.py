"""CLI entry point to execute the complete sequential NBA Betting Intelligence pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestrator import Orchestrator


def main() -> None:
    db_path = PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"
    if db_path.exists():
        db_path.unlink()

    orchestrator = Orchestrator(
        db_path=db_path,
        reports_dir=PROJECT_ROOT / "reports",
        obsidian_vault_dir=PROJECT_ROOT / "NBA",
        max_retries=2,
    )
    result = orchestrator.run_full_pipeline(include_live_espn=True)

    summary_out = {
        "run_id": result["run_id"],
        "sources_info": result["sources_info"],
        "visual_context": result["visual_context"],
        "financial_and_statistical_summary": {
            "initial_bankroll_pen": result["backtest_metrics"]["initial_bankroll_pen"],
            "current_settled_bankroll_pen": result["backtest_metrics"]["current_settled_bankroll_pen"],
            "net_profit_pen": result["backtest_metrics"]["net_profit_pen"],
            "roi_pct": result["backtest_metrics"]["roi_pct"],
            "yield_pct": result["backtest_metrics"]["yield_pct"],
            "settled_bets_count": result["backtest_metrics"]["settled_bets_count"],
            "pending_bets_count": result["backtest_metrics"]["pending_bets_count"],
            "won_count": result["backtest_metrics"]["won_count"],
            "lost_count": result["backtest_metrics"]["lost_count"],
            "push_count": result["backtest_metrics"]["push_count"],
            "max_drawdown_pen": result["backtest_metrics"]["max_drawdown_pen"],
            "overall_brier_score": result["backtest_metrics"]["overall_brier_score"],
            "baseline_brier_score": result["backtest_metrics"]["baseline_brier_score"],
            "overall_log_loss": result["backtest_metrics"]["overall_log_loss"],
            "baseline_log_loss": result["backtest_metrics"]["baseline_log_loss"],
            "bootstrap_uncertainty": result["backtest_metrics"]["bootstrap_uncertainty"],
        },
        "audit_verdict": result["audit_result"]["exit_gates_evaluation"]["recommendation"],
        "reports_info": result["reports_info"],
    }

    eval_out_path = PROJECT_ROOT / "data" / "evaluation" / "latest_run_summary.json"
    eval_out_path.write_text(json.dumps(summary_out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary_out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
