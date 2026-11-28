"""
Interactive Telegram Bot Daemon Runner (`scripts/run_telegram_listener.py`).
Listens for user commands (/banca, /picks, /sgp, /cuotas, /partidos, /liquidar, /ayuda)
and sends instant contextual responses back to the user via Telegram.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.reporting.telegram_interactive import TelegramInteractiveListener

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ListenerRunner")


def main() -> None:
    parser = argparse.ArgumentParser(description="NBA Betting Intelligence Interactive Telegram Bot.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single polling cycle to process any pending messages and exit.",
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=25,
        help="Long polling timeout in seconds for Telegram getUpdates.",
    )
    parser.add_argument(
        "--test-cmd",
        type=str,
        default=None,
        help="Simulate an incoming slash-command locally (e.g., '/banca', '/picks') and print reply.",
    )
    parser.add_argument(
        "--supervise",
        action="store_true",
        help="Run under an internal supervisor that automatically restarts the listener on unexpected termination.",
    )
    args = parser.parse_args()

    if args.test_cmd:
        listener = TelegramInteractiveListener()
        print(f"\n--- SIMULANDO COMANDO: {args.test_cmd} ---")
        reply = listener.process_message(
            chat_id="5198335170",
            text=args.test_cmd,
            from_user={"first_name": "Andre", "username": "andbo06"},
        )
        print(reply)
        print("------------------------------------------\n")
        return

    if args.once:
        listener = TelegramInteractiveListener()
        print("[*] Ejecutando una única pasada de sondeo (getUpdates)...")
        count = listener.run_polling_cycle(timeout=min(5, args.poll_timeout))
        print(f"[OK] Ciclo completado. {count} mensajes procesados.")
        return

    if args.supervise:
        logger.info("🛡️ Modo Supervisor Activado: Auto-recuperación 24/7 en segundo plano.")
        consecutive_crashes = 0
        while True:
            try:
                listener = TelegramInteractiveListener()
                listener.start_polling_loop(poll_timeout=args.poll_timeout)
                break
            except KeyboardInterrupt:
                logger.info("Supervisor detenido manualmente por el usuario.")
                break
            except Exception as exc:
                consecutive_crashes += 1
                backoff = min(60, 5 * consecutive_crashes)
                logger.critical(
                    f"🚨 [WATCHDOG] Listener cayó con error: {exc}. Reiniciando en {backoff}s (Fallo #{consecutive_crashes})...",
                    exc_info=True,
                )
                time.sleep(backoff)
        return

    listener = TelegramInteractiveListener()
    listener.start_polling_loop(poll_timeout=args.poll_timeout)


if __name__ == "__main__":
    main()
