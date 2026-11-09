"""
Automated Daily Lifecycle Scheduler & Nightly Settlement Dispatcher (`scripts/run_automated_scheduler.py`).
Controls the 3 daily execution windows aligned with Peru Time (America/Lima / UTC-5):
  1. 10:00 AM PET (15:00 UTC) - Apertura de Mercado: Ingesta matutina, modelos pre-partido, props y SGPs -> Telegram.
  2. 05:30 PM PET (22:30 UTC) - Injury Sniper & Stale Lines: Ventana T-2h/T-30m y líneas desfasadas retail -> Telegram.
  3. 11:30 PM PET (04:30 UTC) - Liquidación Nocturna Automática: Ingesta de boxscores, liquidación de apuestas/props,
                                actualización CPPI y despacho del Resumen Diario a Telegram.

Supports running as a continuous background daemon, or executing specific windows on demand (--run-now).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import logging
from pathlib import Path
from typing import Any
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from scripts.run_cloud_cycle import run_incremental_cloud_cycle
from src.ingestion.live_peru_scraper import LivePeruOddsScraper
from src.prediction.injury_sniper import InjurySniperMonitor
from src.prediction.player_props import PlayerPropsEngine
from src.reporting.telegram_bot import TelegramAlertBot
from src.paper_trading.engine import PaperTradingEngine
from src.storage.db import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("Scheduler")

# Timezone: Peru Time is UTC-5 all year (no daylight saving time)
PERU_OFFSET = timezone(timedelta(hours=-5))


def get_peru_time() -> datetime:
    """Returns the current localized datetime in Peru Time (UTC-5)."""
    return datetime.now(timezone.utc).astimezone(PERU_OFFSET)


class NBADailyScheduler:
    """
    Automated Lifecycle Coordinator for NBA Betting Intelligence.
    Executes and coordinates the 3 daily syndicate workflows in Peru Time.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or (PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"))
        self.db = DatabaseManager(self.db_path)
        self.bot = TelegramAlertBot()
        self.paper_engine = PaperTradingEngine(
            db=self.db,
            initial_bankroll_pen=100.00,
            base_stake_pen=1.00,
            max_stake_pen=2.00,
            min_ev_threshold=0.05,
            dynamic_conviction_staking=True,
            enable_cppi_shield=True,
            staking_mode="CONSERVATIVE",
            exclude_synthetic=True,
        )

    def execute_morning_cycle(self) -> dict[str, Any]:
        """
        Ventana 1: 10:00 AM PET (Apertura de Mercado)
        - Ingesta los partidos de la jornada desde ESPN.
        - Calcula ratings de equipo y características pre-partido.
        - Genera predicciones de moneyline y totales.
        - Escanea proposiciones de jugador (Props) y Same-Game Parlays (RETAbet/Betsson).
        - Despacha las mejores oportunidades +EV a Telegram.
        """
        now_pet = get_peru_time()
        logger.info(f"🌅 INICIANDO VENTANA MATUTINA (10:00 AM PET) — Hora actual: {now_pet.strftime('%Y-%m-%d %H:%M:%S PET')}")

        # 1. Run incremental cycle in pregame mode
        res_cycle = run_incremental_cloud_cycle(mode="pregame")

        # 2. Run player props & SGP slate generator
        props_engine = PlayerPropsEngine(db=self.db, min_ev_threshold=0.03)
        now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        slate_games = self.db.fetch_all(
            """
            SELECT * FROM games
            WHERE status = 'SCHEDULED'
              AND game_start_time > ?
              AND game_id NOT LIKE 'SYN%'
            ORDER BY game_start_time ASC
            LIMIT 15
            """,
            (now_utc_str,),
        )
        props_list = props_engine.generate_slate_prop_opportunities(
            slate_games=slate_games,
            bankroll_pen=self.paper_engine.get_bankroll_state()["settled_bankroll_pen"],
            min_ev_pct=3.0,
        )

        # 3. Dispatch fresh alerts to Telegram
        dispatched_count = 0
        if self.bot.is_live and props_list:
            for p in props_list:
                ev_val = float(p.get("ev_pct") or 0.0)
                if ev_val >= 3.5:
                    if p.get("type") == "RETABET_SGP" or "sgp_id" in p:
                        msg = self.bot.format_sgp_parlay_alert(p)
                    else:
                        msg = self.bot.format_single_bet_alert(p)
                    self.bot.send_raw_message(msg)
                    dispatched_count += 1
            logger.info(f"📲 [TELEGRAM] {dispatched_count} alertas matutinas despachadas a tu chat.")

        return {
            "status": "COMPLETED",
            "window": "MORNING",
            "executed_at_pet": now_pet.strftime("%Y-%m-%dT%H:%M:%S"),
            "props_found": len(props_list),
            "alerts_dispatched": dispatched_count,
            "cycle_summary": res_cycle,
        }

    def execute_sniper_cycle(self) -> dict[str, Any]:
        """
        Ventana 2: 05:30 PM PET (Injury Sniper & Líneas Desfasadas)
        - Monitorea reportes oficiales de lesiones T-2h y confirmación de quintetos T-30m.
        - Detecta líneas desfasadas en bookmakers peruanos.
        - Despacha alertas urgentes si se detecta valor tardío.
        """
        now_pet = get_peru_time()
        logger.info(f"🎯 INICIANDO VENTANA INJURY SNIPER (05:30 PM PET) — Hora actual: {now_pet.strftime('%Y-%m-%d %H:%M:%S PET')}")

        sniper = InjurySniperMonitor(db=self.db)
        sniper_res = sniper.scan_pregame_slate(force_scan_all=False)

        alerts_sent = 0
        if self.bot.is_live and sniper_res.get("alerts_emitted"):
            for alert in sniper_res["alerts_emitted"]:
                msg = (
                    f"🚨 *ALERTA INJURY SNIPER (T-2H / T-30M)*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📍 *Partido:* `{alert.get('game_id')}`\n"
                    f"⚠️ *Baja Detectada:* {alert.get('absent_star', 'Jugador Estrella')}\n"
                    f"📈 *Impacto en Sinergia:* `{alert.get('net_penalty', 0.0):+.1f} pts`\n"
                    f"🎯 *Pick Generado:* *{alert.get('selection')}* @ `{alert.get('decimal_odds', 1.90):.2f}`\n"
                    f"⚡ *EV Lower-Bound:* `+{alert.get('ev_lower_bound_pct', 0.0):.1f}%`\n"
                    f"💵 *Stake Sugerido:* *S/ {alert.get('stake_pen', 2.00):.2f} PEN*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━"
                )
                self.bot.send_raw_message(msg)
                alerts_sent += 1
            logger.info(f"📲 [TELEGRAM] {alerts_sent} alertas de Injury Sniper enviadas a tu chat.")

        # Escaneo en tiempo real de cuotas peruanas (Stale Lines & Arbitraje Surebet)
        live_res: dict[str, Any] = {}
        try:
            live_scraper = LivePeruOddsScraper(db=self.db)
            live_res = live_scraper.scan_and_alert_entire_slate(min_clv_pct=4.0, max_alerts=3)
            alerts_sent += int(live_res.get("stale_lines_found", 0)) + int(live_res.get("surebets_found", 0))
            logger.info(f"📊 [LIVE ODDS] {live_res.get('games_scanned', 0)} partidos escaneados para casas peruanas.")
        except Exception as exc:
            logger.warning(f"Error escaneando cuotas en vivo en el scheduler: {exc}")

        return {
            "status": "COMPLETED",
            "window": "SNIPER",
            "executed_at_pet": now_pet.strftime("%Y-%m-%dT%H:%M:%S"),
            "sniper_results": sniper_res,
            "live_odds_results": live_res,
            "alerts_dispatched": alerts_sent,
        }

    def execute_nightly_settlement_cycle(self) -> dict[str, Any]:
        """
        Ventana 3: 11:30 PM PET (Liquidación Nocturna Automática)
        - Ingesta resultados finales y boxscores oficiales de ESPN.
        - Liquida apuestas de moneyline, totales y spreads pendientes.
        - Liquida proposiciones de jugador (Props) y Same-Game Parlays (SGPs).
        - Reconcilia el ledger bancario y calcula el multiplicador CPPI.
        - Despacha a Telegram el Resumen Diario de Rendimiento detallado.
        """
        now_pet = get_peru_time()
        today_str = now_pet.strftime("%Y-%m-%d")
        logger.info(f"🌙 INICIANDO VENTANA DE LIQUIDACIÓN NOCTURNA (11:30 PM PET) — Jornada: {today_str}")

        # 1. Run incremental cycle in settle_and_calibrate mode
        settle_res = run_incremental_cloud_cycle(mode="settle_and_calibrate")

        # 2. Extract settled bets and props
        # now_utc = datetime.now(timezone.utc)
        # now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Fetch settled bets today
        settled_today = self.db.fetch_all(
            """
            SELECT bet_id, game_id, market, selection, decimal_odds, stake_pen, status, net_profit_pen, settled_at
            FROM simulated_bets
            WHERE status IN ('WON', 'LOST', 'PUSH')
              AND settled_at >= datetime('now', '-24 hours')
            ORDER BY settled_at DESC
            """
        )

        settled_props_today = self.db.fetch_all(
            """
            SELECT prop_id, game_id, player_name, prop_category, line_value, selection, decimal_odds, stake_pen, status, net_profit_pen, settled_at
            FROM player_prop_picks
            WHERE status IN ('WON', 'LOST', 'PUSH')
              AND settled_at >= datetime('now', '-24 hours')
            ORDER BY settled_at DESC
            """
        )

        curr_br = self.paper_engine.get_bankroll_state()["settled_bankroll_pen"]
        cppi_mult = self.paper_engine.compute_cppi_multiplier(curr_br)
        peak_row = self.db.fetch_one("SELECT MAX(bankroll_after_pen) AS max_br FROM simulated_bets WHERE bankroll_after_pen IS NOT NULL")
        peak_val = max(100.0, float(peak_row["max_br"] or 100.0) if peak_row else 100.0, curr_br)

        # 3. Format and dispatch Telegram Daily Settlement Report
        report_msg = self.bot.format_daily_settlement_report(
            matchday_date=today_str,
            settled_bets=settled_today,
            settled_props=settled_props_today,
            current_bankroll_pen=curr_br,
            initial_bankroll_pen=100.00,
            peak_bankroll_pen=peak_val,
            cppi_multiplier=cppi_mult,
        )

        if self.bot.is_live:
            self.bot.send_raw_message(report_msg)
            logger.info("📲 [TELEGRAM] Resumen diario de liquidación enviado exitosamente a tu chat.")
        else:
            logger.info(f"ℹ️ [TELEGRAM DRY-RUN]:\n{report_msg}")

        return {
            "status": "COMPLETED",
            "window": "SETTLEMENT",
            "matchday_date": today_str,
            "executed_at_pet": now_pet.strftime("%Y-%m-%dT%H:%M:%S"),
            "settled_bets_count": len(settled_today),
            "settled_props_count": len(settled_props_today),
            "settled_bankroll_pen": curr_br,
            "cppi_multiplier": cppi_mult,
            "cycle_summary": settle_res,
        }

    def run_daemon(self, poll_interval_seconds: int = 60) -> None:
        """
        Runs the daemon loop checking Peru Time every minute:
        - Executes morning cycle at 10:00 PET.
        - Executes injury sniper cycle at 17:30 PET.
        - Executes nightly settlement cycle at 23:30 PET.
        """
        logger.info("=" * 80)
        logger.info("🕒 NBA BETTING INTELLIGENCE — AUTOMATED DAILY SCHEDULER")
        logger.info("=" * 80)
        logger.info("Zona Horaria         : Perú Time (America/Lima / UTC-5)")
        logger.info(f"Hora Actual en Lima  : {get_peru_time().strftime('%Y-%m-%d %H:%M:%S PET')}")
        logger.info(f"Estado Telegram Bot  : {'EN VIVO (TELEGRAM BOT API)' if self.bot.is_live else 'DRY-RUN / LOCAL'}")
        logger.info("Ventanas Programadas : 10:15 PET (Apertura) | 17:15 PET (Sniper T-2H) | 18:35 PET (Pre-Tipoff) | 01:45 PET (Liquidación)")
        logger.info("=" * 80)

        executed_today: set[tuple[str, str]] = set()

        while True:
            try:
                now_pet = get_peru_time()
                today_str = now_pet.strftime("%Y-%m-%d")
                hour = now_pet.hour
                minute = now_pet.minute

                # 1. Morning Window: 10:15 - 10:25 PET
                if hour == 10 and 15 <= minute < 25 and (today_str, "morning") not in executed_today:
                    self.execute_morning_cycle()
                    executed_today.add((today_str, "morning"))

                # 2. Injury Sniper T-2H: 17:15 - 17:25 PET
                elif hour == 17 and 15 <= minute < 25 and (today_str, "sniper_t2h") not in executed_today:
                    self.execute_sniper_cycle()
                    executed_today.add((today_str, "sniper_t2h"))

                # 3. Pre-Tipoff T-25m: 18:35 - 18:45 PET
                elif hour == 18 and 35 <= minute < 45 and (today_str, "sniper_pre") not in executed_today:
                    self.execute_sniper_cycle()
                    executed_today.add((today_str, "sniper_pre"))

                # 4. Night Settlement Window: 01:45 - 01:55 PET
                elif hour == 1 and 45 <= minute < 55 and (today_str, "settle") not in executed_today:
                    self.execute_nightly_settlement_cycle()
                    executed_today.add((today_str, "settle"))

                time.sleep(poll_interval_seconds)
            except KeyboardInterrupt:
                logger.info("Deteniendo el daemon de automatización (solicitado por usuario).")
                break
            except Exception as exc:
                logger.error(f"Error en el ciclo del daemon: {exc}", exc_info=True)
                time.sleep(30)


def main() -> None:
    parser = argparse.ArgumentParser(description="NBA Betting Intelligence Automated Lifecycle Scheduler (Peru Time).")
    parser.add_argument(
        "--run-now",
        choices=["morning", "sniper", "settle", "all"],
        default=None,
        help="Execute a specific window immediately without waiting for schedule.",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously as a background daemon checking Peru Time every minute.",
    )
    args = parser.parse_args()

    scheduler = NBADailyScheduler()

    if args.run_now:
        mode = args.run_now
        print(f"[*] Ejecutando inmediatamente ventana: {mode.upper()} en hora de Perú...")
        if mode == "morning":
            scheduler.execute_morning_cycle()
        elif mode == "sniper":
            scheduler.execute_sniper_cycle()
        elif mode == "settle":
            scheduler.execute_nightly_settlement_cycle()
        elif mode == "all":
            print("--- 1. Apertura Matutina ---")
            scheduler.execute_morning_cycle()
            print("--- 2. Injury Sniper ---")
            scheduler.execute_sniper_cycle()
            print("--- 3. Liquidación Nocturna ---")
            scheduler.execute_nightly_settlement_cycle()
        print(f"[OK] Ventana {mode.upper()} completada con éxito.")
    else:
        # Default: start daemon
        scheduler.run_daemon()


if __name__ == "__main__":
    main()
