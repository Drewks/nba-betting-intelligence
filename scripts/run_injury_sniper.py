"""
CLI Entry point for the NBA Injury Sniper Dual-Window Monitor (`scripts/run_injury_sniper.py`):
Executes pregame monitoring scans at T-2h (Injury Report) and T-30m (Starting Five confirmation).
Can be scheduled via cron, GitHub Actions workflow, or Antigravity `/schedule`.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.prediction.injury_sniper import InjurySniperMonitor
from src.storage.db import DatabaseManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NBA Injury Sniper Dual-Window Monitor (T-2h & T-30m).")
    parser.add_argument(
        "--mode",
        choices=["auto", "2h", "30m", "force"],
        default="auto",
        help="Scan mode: 'auto' (checks active windows), '2h' (only T-2h), '30m' (only T-30m), 'force' (evaluates all scheduled games)",
    )
    parser.add_argument(
        "--ref-time",
        type=str,
        default=None,
        help="Optional ISO reference time UTC (e.g., '2026-11-06T00:30:00Z') for simulation/backtesting.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without modifying database or placing virtual bets.",
    )
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"
    db = DatabaseManager(db_path)
    sniper = InjurySniperMonitor(db=db)

    ref_dt = None
    if args.ref_time:
        ref_dt = datetime.fromisoformat(args.ref_time.replace("Z", "+00:00"))

    force_all = args.mode == "force"
    res = sniper.scan_pregame_slate(reference_time_utc=ref_dt, force_scan_all=force_all)

    # Save output summary
    out_dir = PROJECT_ROOT / "data" / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "latest_sniper_scan.json"
    out_file.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 80)
    print("[NBA] BETTING INTELLIGENCE V7.1 - INJURY SNIPER DUAL-WINDOW MONITOR")
    print("=" * 80)
    print(f"Scanned at (UTC)        : {res['scanned_at_utc']}")
    print(f"Total Scheduled Games   : {res['total_scheduled']}")
    print(f"Games in Window T-2h    : {res['games_in_2h_window']}")
    print(f"Games in Window T-30m   : {res['games_in_30m_window']}")
    print(f"Total Sniper Alerts     : {res['total_alerts_emitted']}")
    print("-" * 80)

    for g in res["games"]:
        status_tag = f"[{g['window']}]"
        if g["monitored"]:
            status_tag += " [*] ACTIVE MONITOR"
        print(f"  * {g['matchup']:<22} | Tip-off: {g['game_start_time']} | T-{g['minutes_to_tipoff']:>5.0f}m | {status_tag}")

    if res["alerts"]:
        print("\n" + "=" * 80)
        print("[!] ACTIONABLE SNIPER ALERTS (+EV & CONFORMAL VALIDATED):")
        print("=" * 80)
        for a in res["alerts"]:
            print(f"  >> [{a['window_type']} T-{a['minutes_to_tipoff']:.0f}m] {a['selection']} on {a['target_team']} vs {a['opponent_team']}")
            print(f"     Bookmaker Odds : {a['decimal_odds']:.2f}")
            print(f"     Adjusted Prob  : {a['point_prob'] * 100:.1f}% (Conformal 90% CI: [{a['conformal_p_low'] * 100:.1f}%, {a['conformal_p_high'] * 100:.1f}%])")
            print(f"     Lower-Bound EV : {a['ev_lower_bound_pct']:+.2f}% (Nominal EV: {a['ev_pct']:+.2f}%)")
            print(f"     Kelly Stake    : S/ {a['kelly_stake_pen']:.2f} PEN ({a['kelly_optimal_fraction'] * 100:.2f}%)")
            print(f"     Rationale      : {a['rational']}\n")
    else:
        print("\n  [i] No injury mispricings exceeding the +5.0% Lower-Bound EV hurdle detected in current window.")
    print("=" * 80)


if __name__ == "__main__":
    main()
