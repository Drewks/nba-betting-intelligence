"""
CLI Runner for Telegram Alerts Dispatcher (`scripts/run_telegram_alerts.py`):
Scans current +EV slate bets, correlated SGPs, and stale line opportunities,
and dispatches rich alerts to Telegram or local simulation logs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.reporting.telegram_bot import TelegramAlertBot
from src.storage.db import DatabaseManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatch Telegram alerts for +EV bets and SGPs.")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run simulation mode")
    parser.add_argument("--min-ev", type=float, default=3.5, help="Minimum EV percentage (default: 3.5)")
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"
    db = DatabaseManager(db_path)
    bot = TelegramAlertBot()

    if args.dry_run:
        bot.is_live = False

    print("=" * 80)
    print("📲 NBA BETTING INTELLIGENCE V9 - DISPATCHER DE ALERTAS TELEGRAM")
    print("=" * 80)
    print(f"Modo de Operación: {'EN VIVO (TELEGRAM BOT API)' if bot.is_live else 'SIMULACIÓN (DRY-RUN / LOCAL LOG)'}")
    print(f"Filtro Mínimo EV : >= {args.min_ev:.1f}%")
    print("-" * 80)

    dispatched_count = 0

    # 1. Check latest player props and SGPs
    props_file = PROJECT_ROOT / "data" / "evaluation" / "latest_player_props.json"
    if props_file.exists():
        try:
            props = json.loads(props_file.read_text(encoding="utf-8"))
            for p in props:
                ev = float(p.get("ev_pct") or 0.0)
                if ev < args.min_ev:
                    continue

                if p.get("type") == "RETABET_SGP" or "sgp_id" in p:
                    msg = bot.format_sgp_parlay_alert(p)
                elif p.get("type") == "HIGH_PROB_PARLAY" or "parlay_id" in p:
                    msg = bot.format_high_prob_parlay_alert(p)
                else:
                    msg = bot.format_single_bet_alert(p)

                bot.send_raw_message(msg)
                dispatched_count += 1
        except Exception as exc:
            print(f"Error procesando props: {exc}")

    # 2. Check pending bets in simulated_bets table with EV >= min_ev
    pending_bets = db.fetch_all(
        """
        SELECT b.bet_id, b.game_id, b.market, b.selection, b.decimal_odds, b.stake_pen,
               p.calibrated_probability, p.ev_pct, p.odds_provider
        FROM simulated_bets b
        LEFT JOIN predictions p ON b.prediction_id = p.prediction_id
        WHERE b.status = 'PENDING' AND COALESCE(p.ev_pct, 0.0) >= ?
        LIMIT 5
        """,
        (args.min_ev,),
    )
    for b in pending_bets:
        msg = bot.format_single_bet_alert(b)
        bot.send_raw_message(msg)
        dispatched_count += 1

    print(f"\n[OK] Alertas despachadas exitosamente: {dispatched_count}")
    print(f"Registro persistido en: {bot.alerts_log_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
