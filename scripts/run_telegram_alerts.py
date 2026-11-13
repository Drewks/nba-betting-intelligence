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

from src.reporting.telegram_bot import (
    DEFAULT_ALERT_STATE_PATH,
    TelegramAlertBot,
    dispatch_pending_bet_alerts,
    load_dispatched_alert_keys,
    save_dispatched_alert_keys,
)
from src.storage.db import DatabaseManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatch Telegram alerts for +EV bets and SGPs.")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run simulation mode")
    parser.add_argument("--min-ev", type=float, default=5.0, help="Minimum EV percentage (default: 5.0)")
    parser.add_argument(
        "--db",
        default=str(PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"),
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--state-path",
        default=str(DEFAULT_ALERT_STATE_PATH),
        help="Path to deduplicated Telegram alert ledger JSON",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    state_path = Path(args.state_path)
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
    sent_keys = load_dispatched_alert_keys(state_path)
    keys_updated = False

    # 1. Check latest player props and SGPs (deduplicated)
    props_file = PROJECT_ROOT / "data" / "evaluation" / "latest_player_props.json"
    if props_file.exists():
        try:
            props = json.loads(props_file.read_text(encoding="utf-8"))
            for p in props:
                ev = float(p.get("ev_pct") or 0.0)
                if ev < args.min_ev:
                    continue

                prop_id = (
                    p.get("sgp_id")
                    or p.get("parlay_id")
                    or p.get("prop_id")
                    or f"{p.get('game_id', '')}:{p.get('player_name', '')}:{p.get('stat_type', p.get('prop_category', ''))}:{p.get('selection', '')}"
                )
                prop_key = f"PROP:{prop_id}"
                if prop_key in sent_keys:
                    continue

                if p.get("type") == "RETABET_SGP" or "sgp_id" in p:
                    msg = bot.format_sgp_parlay_alert(p)
                elif p.get("type") == "HIGH_PROB_PARLAY" or "parlay_id" in p:
                    msg = bot.format_high_prob_parlay_alert(p)
                else:
                    msg = bot.format_single_bet_alert(p)

                if bot.send_raw_message(msg):
                    sent_keys.add(prop_key)
                    keys_updated = True
                    dispatched_count += 1
        except Exception as exc:
            print(f"Error procesando props: {exc}")

    should_persist = (not args.dry_run) and (bot.is_live or state_path != DEFAULT_ALERT_STATE_PATH)
    if keys_updated and should_persist:
        save_dispatched_alert_keys(sent_keys, state_path)

    # 2. Check pending bets in simulated_bets table with EV >= min_ev (deduplicated)
    dispatched_count += dispatch_pending_bet_alerts(
        bot,
        db,
        min_ev=args.min_ev,
        max_alerts=10,
        state_path=state_path,
        dry_run=args.dry_run,
    )

    print(f"\n[OK] Alertas despachadas exitosamente: {dispatched_count}")
    print(f"Registro persistido en: {bot.alerts_log_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
