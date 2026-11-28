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
import inspect
import json
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
from src.config import load_config
from src.ingestion.live_peru_scraper import LivePeruOddsScraper
from src.prediction.injury_sniper import InjurySniperMonitor
from src.prediction.player_props import PlayerPropsEngine
from src.reporting.telegram_bot import (
    DEFAULT_ALERT_STATE_PATH,
    TelegramAlertBot,
    dispatch_pending_bet_alerts,
    format_injury_sniper_alert,
    format_slate_status_summary,
    load_dispatched_alert_keys,
    save_dispatched_alert_keys,
)
from src.paper_trading.engine import build_production_engine
from src.paper_trading.parlay_engine import ParlayTradingEngine
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

    def __init__(
        self,
        db_path: Path | str | None = None,
        alert_state_path: Path | str | None = None,
    ) -> None:
        self.db_path = Path(db_path or (PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"))
        self.db = DatabaseManager(self.db_path)
        self.bot = TelegramAlertBot()
        self.alert_state_path = Path(alert_state_path or DEFAULT_ALERT_STATE_PATH)
        self.paper_engine = build_production_engine(self.db)
        self.parlay_engine = ParlayTradingEngine(self.db)

    def _snapshot_observed_quote_counts(self) -> dict[str, int]:
        """Count persisted observed quotes grouped by provider without failing on test mocks."""
        try:
            rows = self.db.fetch_all(
                "SELECT provider, COUNT(*) AS cnt FROM v_observed_odds_snapshots GROUP BY provider"
            )
            counts: dict[str, int] = {}
            for row in rows or []:
                if isinstance(row, dict) and row.get("provider"):
                    counts[str(row["provider"])] = int(row.get("cnt") or 0)
            return counts
        except Exception:
            return {}

    @staticmethod
    def _diff_quote_counts(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
        """Compute newly persisted quotes per provider since cycle start."""
        diff: dict[str, int] = {}
        for prov, cnt_after in after.items():
            delta = int(cnt_after) - int(before.get(prov, 0))
            if delta > 0:
                diff[prov] = delta
        return diff

    def run_peru_playwright_odds_harvest(self) -> int:
        """
        Reports Peruvian Playwright scraping availability for the automated scheduler.
        Automated cloud runs skip direct Betano/RETAbet DOM scraping due to Cloudflare/Shape
        anti-bot enforcement (use scripts/harvest_local_peru_odds.py in an interactive local browser session).
        """
        logger.info(
            "SKIPPED_SOURCE [peru_playwright_scraper]: desacoplado del scheduler automático por "
            "protección anti-bot Cloudflare/Shape (cosecha local vía scripts/harvest_local_peru_odds.py)."
        )
        return 0

    def execute_morning_cycle(self) -> dict[str, Any]:
        """
        Ventana 1: 10:00 AM PET (Apertura de Mercado)
        - Ingesta los partidos de la jornada desde ESPN y cuotas observadas.
        - Calcula ratings de equipo y características pre-partido.
        - Genera predicciones y apuestas paper filtradas según config/model_config.yaml.
        - Reporta explícitamente sources_executed, sources_skipped y new_quotes_persisted_by_source.
        """
        now_pet = get_peru_time()
        logger.info(f"🌅 INICIANDO VENTANA MATUTINA (10:00 AM PET) — Hora actual: {now_pet.strftime('%Y-%m-%d %H:%M:%S PET')}")
        quotes_before = self._snapshot_observed_quote_counts()
        sources_executed: list[str] = []
        sources_skipped: dict[str, str] = {}

        # 1. Run incremental cycle in pregame mode first (ingests slate games into DB)
        res_cycle = run_incremental_cloud_cycle(mode="pregame")
        sources_executed.append("espn_public_adapter")
        if isinstance(res_cycle, dict) and (res_cycle.get("sources_info") or {}).get("sportradar_api", {}).get("available"):
            sources_executed.append("sportradar_api")
        sources_executed.append("live_peru_odds_scraper")

        # 2. Local Playwright harvester (explicitly skipped in cloud automation when returning 0)
        playwright_quotes = int(self.run_peru_playwright_odds_harvest() or 0)
        if playwright_quotes > 0:
            sources_executed.append("peru_playwright_scraper")
        else:
            sources_skipped["peru_playwright_scraper"] = (
                "skipped_decoupled_cloudflare_local_only: use scripts/harvest_local_peru_odds.py"
            )

        # 3. Fail-closed Props & Parlays gate driven strictly by config/model_config.yaml
        risk_cfg = load_config().risk
        today_matchday_str = now_pet.strftime("%Y-%m-%d")
        props_list: list[dict[str, Any]] = []
        placed_parlays: list[dict[str, Any]] = []

        if risk_cfg.allow_player_props_betting or risk_cfg.allow_parlays:
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
            if risk_cfg.allow_player_props_betting:
                sources_executed.append("player_props_engine")
            else:
                sources_skipped["player_props_betting"] = "disabled_by_config (allow_player_props_betting=false)"

            if risk_cfg.allow_parlays:
                placed_parlays = self.parlay_engine.record_candidate_parlays(
                    candidates=props_list,
                    matchday_date=today_matchday_str,
                    allow_parlays=True,
                )
                sources_executed.append("parlay_engine")
                if placed_parlays:
                    logger.info(f"🔥 [SUB-BANKROLL] {len(placed_parlays)} combinadas reservadas automáticamente en la banca S/50.")
            else:
                sources_skipped["parlays_sub_bankroll"] = "disabled_by_config (allow_parlays=false)"
        else:
            sources_skipped["player_props_betting"] = "disabled_by_config (allow_player_props_betting=false)"
            sources_skipped["parlays_sub_bankroll"] = "disabled_by_config (allow_parlays=false)"

        # 3b. Dispatch fresh alerts to Telegram (deduplicated)
        dispatched_count = 0
        if self.bot.is_live:
            sources_executed.append("telegram_bot")
            dispatched_count += dispatch_pending_bet_alerts(
                self.bot,
                self.db,
                min_ev=None,
                max_alerts=10,
                state_path=self.alert_state_path,
            )
            sent_keys = load_dispatched_alert_keys(self.alert_state_path)
            keys_changed = False
            if risk_cfg.allow_player_props_betting or risk_cfg.allow_parlays:
                for p in props_list or []:
                    ev_val = float(p.get("ev_pct") or 0.0)
                    if ev_val < 3.5:
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
                        msg = self.bot.format_sgp_parlay_alert(p)
                    else:
                        msg = self.bot.format_single_bet_alert(p)
                    if self.bot.send_raw_message(msg):
                        sent_keys.add(prop_key)
                        keys_changed = True
                        dispatched_count += 1

            if dispatched_count == 0:
                summary_key = f"SLATE_SUMMARY:{today_matchday_str}"
                if summary_key not in sent_keys:
                    pending_row = self.db.fetch_one(
                        "SELECT COUNT(*) AS cnt FROM simulated_bets WHERE status = 'PENDING'"
                    )
                    pending_cnt = int((pending_row or {}).get("cnt") or 0)
                    summary_msg = format_slate_status_summary(res_cycle, pending_count=pending_cnt)
                    if self.bot.send_raw_message(summary_msg):
                        sent_keys.add(summary_key)
                        keys_changed = True

            if keys_changed:
                save_dispatched_alert_keys(sent_keys, self.alert_state_path)
            logger.info(f"📲 [TELEGRAM] {dispatched_count} alertas matutinas despachadas a tu chat.")
        else:
            sources_skipped["telegram_bot"] = "not_configured_or_dry_run"

        quotes_after = self._snapshot_observed_quote_counts()
        new_quotes_by_source = self._diff_quote_counts(quotes_before, quotes_after)

        try:
            self.db.checkpoint(truncate=True)
        except Exception as cp_exc:
            logger.warning(f"Database checkpoint warning: {cp_exc}")

        logger.info(
            "SOURCES_TELEMETRY [MORNING] executed=%s skipped=%s new_quotes_persisted_by_source=%s",
            sources_executed,
            sources_skipped,
            new_quotes_by_source,
        )

        return {
            "status": "COMPLETED",
            "window": "MORNING",
            "executed_at_pet": now_pet.strftime("%Y-%m-%dT%H:%M:%S"),
            "props_found": len(props_list),
            "placed_parlays_count": len(placed_parlays),
            "alerts_dispatched": dispatched_count,
            "sources_executed": sources_executed,
            "sources_skipped": sources_skipped,
            "new_quotes_persisted_by_source": new_quotes_by_source,
            "cycle_summary": res_cycle,
        }

    def execute_sniper_cycle(self) -> dict[str, Any]:
        """
        Ventana 2: 05:30 PM PET (Injury Sniper & Líneas Desfasadas)
        - Monitorea reportes oficiales de lesiones T-2h y confirmación de quintetos T-30m.
        - Escanea líneas observadas con fuente sharp sin asumir ejecución Playwright en nube.
        - Despacha alertas urgentes si se detecta valor tardío.
        """
        now_pet = get_peru_time()
        logger.info(f"🎯 INICIANDO VENTANA INJURY SNIPER (05:30 PM PET) — Hora actual: {now_pet.strftime('%Y-%m-%d %H:%M:%S PET')}")
        quotes_before = self._snapshot_observed_quote_counts()
        sources_executed: list[str] = ["injury_sniper_monitor"]
        sources_skipped: dict[str, str] = {}

        playwright_quotes = int(self.run_peru_playwright_odds_harvest() or 0)
        if playwright_quotes > 0:
            sources_executed.append("peru_playwright_scraper")
        else:
            sources_skipped["peru_playwright_scraper"] = (
                "skipped_decoupled_cloudflare_local_only: use scripts/harvest_local_peru_odds.py"
            )

        sniper = InjurySniperMonitor(db=self.db)
        sniper_res = sniper.scan_pregame_slate(force_scan_all=False)

        alerts_sent = 0
        if self.bot.is_live and sniper_res.get("alerts"):
            sources_executed.append("telegram_bot")
            sent_keys = load_dispatched_alert_keys(self.alert_state_path)
            keys_changed = False
            for alert in sniper_res["alerts"]:
                alert_id = alert.get("alert_id") or f"{alert.get('game_id', '')}:{alert.get('selection', '')}"
                sniper_key = f"SNIPER:{alert_id}"
                if sniper_key in sent_keys:
                    continue
                msg = format_injury_sniper_alert(alert)
                if self.bot.send_raw_message(msg):
                    sent_keys.add(sniper_key)
                    keys_changed = True
                    alerts_sent += 1
            if keys_changed:
                save_dispatched_alert_keys(sent_keys, self.alert_state_path)
            logger.info(f"📲 [TELEGRAM] {alerts_sent} alertas de Injury Sniper enviadas a tu chat.")
        elif not self.bot.is_live:
            sources_skipped["telegram_bot"] = "not_configured_or_dry_run"

        # Escaneo en tiempo real de cuotas observadas (Stale Lines & Arbitraje Surebet)
        live_res: dict[str, Any] = {}
        try:
            live_scraper = LivePeruOddsScraper(db=self.db)
            scan_params = inspect.signature(live_scraper.scan_and_alert_entire_slate).parameters
            if "include_player_props" in scan_params:
                scan_rows = live_scraper.scan_and_alert_entire_slate(
                    notify_telegram=True,
                    include_player_props=bool(load_config().risk.allow_player_props_betting),
                )
            else:
                scan_rows = live_scraper.scan_and_alert_entire_slate(notify_telegram=True)
            sources_executed.append("live_peru_odds_scraper")
            live_res = {
                "games_scanned": len(scan_rows),
                "stale_lines_found": sum(len(r.get("stale_lines") or []) for r in scan_rows),
                "surebets_found": sum(1 for r in scan_rows if r.get("surebet")),
                "observed_quotes": sum(int(r.get("observed_quotes_count") or 0) for r in scan_rows),
            }
            alerts_sent += live_res["stale_lines_found"] + live_res["surebets_found"]
            logger.info(f"📊 [LIVE ODDS] {live_res['games_scanned']} partidos con benchmark sharp observado escaneados.")
        except Exception as exc:
            sources_skipped["live_peru_odds_scraper"] = f"error: {exc}"
            logger.warning(f"Error escaneando cuotas en vivo en el scheduler: {exc}")

        # 3. Re-evaluar ciclo pregame / Paper Trading con las líneas frescas recién ingresadas
        pregame_res: dict[str, Any] = {}
        try:
            cycle_params = inspect.signature(run_incremental_cloud_cycle).parameters
            if "db_path" in cycle_params:
                pregame_res = run_incremental_cloud_cycle(mode="pregame", db_path=self.db.db_path) or {}
            else:
                pregame_res = run_incremental_cloud_cycle(mode="pregame") or {}
            sources_executed.append("pregame_paper_trading")
        except Exception as exc:
            sources_skipped["pregame_paper_trading"] = f"error: {exc}"
            logger.warning(f"Error ejecutando ciclo pregame tras Sniper en el scheduler: {exc}")

        # 4. Despachar alertas Telegram para nuevas apuestas PENDING >= min_ev configurado (deduplicadas)
        if self.bot.is_live:
            try:
                if "telegram_bot" not in sources_executed:
                    sources_executed.append("telegram_bot")
                alerts_sent += dispatch_pending_bet_alerts(
                    self.bot,
                    self.db,
                    min_ev=None,
                    max_alerts=10,
                    state_path=self.alert_state_path,
                )
            except Exception as exc:
                sources_skipped["telegram_bot"] = f"error: {exc}"
                logger.warning(f"Error despachando alertas de apuestas tras Sniper: {exc}")

        quotes_after = self._snapshot_observed_quote_counts()
        new_quotes_by_source = self._diff_quote_counts(quotes_before, quotes_after)

        try:
            self.db.checkpoint(truncate=True)
        except Exception as cp_exc:
            logger.warning(f"Database checkpoint warning: {cp_exc}")

        logger.info(
            "SOURCES_TELEMETRY [SNIPER] executed=%s skipped=%s new_quotes_persisted_by_source=%s",
            sources_executed,
            sources_skipped,
            new_quotes_by_source,
        )

        return {
            "status": "COMPLETED",
            "window": "SNIPER",
            "executed_at_pet": now_pet.strftime("%Y-%m-%dT%H:%M:%S"),
            "sniper_results": sniper_res,
            "live_odds_results": live_res,
            "pregame_results": pregame_res,
            "alerts_dispatched": alerts_sent,
            "sources_executed": sources_executed,
            "sources_skipped": sources_skipped,
            "new_quotes_persisted_by_source": new_quotes_by_source,
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
        quotes_before = self._snapshot_observed_quote_counts()

        # 1. Run incremental cycle in settle_and_calibrate mode
        settle_res = run_incremental_cloud_cycle(mode="settle_and_calibrate")
        sources_executed = ["espn_public_adapter"]
        sources_skipped: dict[str, str] = {
            "peru_playwright_scraper": "skipped_in_settlement_window",
            "live_peru_odds_scraper": "skipped_in_settlement_window",
        }

        # 2. Extract settled bets and props today
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

        # 2c. Settle pending Parlays in S/50 Sub-Bankroll
        pending_parlays = self.db.fetch_all("SELECT * FROM parlay_bets WHERE status = 'PENDING'")
        parlay_boxscores: dict[str, dict[str, dict[str, float]]] = {}
        if pending_parlays:
            from src.ingestion.adapters import ESPNPublicAdapter
            espn_adapter = ESPNPublicAdapter(timeout_seconds=10)
            for p_row in pending_parlays:
                try:
                    p_legs = json.loads(p_row["legs_json"])
                    for pl in p_legs:
                        pgid = pl.get("game_id")
                        if pgid and pgid not in parlay_boxscores and pgid != "CROSS_SLATE":
                            ev_id = pgid.replace("ESPN_", "").split("_")[0]
                            b_stats = espn_adapter.fetch_player_boxscores(ev_id)
                            if b_stats:
                                parlay_boxscores[pgid] = b_stats
                except Exception as exc:
                    logger.debug(f"Error preparing boxscores for parlay settlement: {exc}")

        now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        settled_parlays = self.parlay_engine.settle_pending_parlays(
            game_boxscores=parlay_boxscores,
            settled_at=now_utc_str,
        )
        parlay_state = self.parlay_engine.get_bankroll_state()

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
            parlay_bankroll_state=parlay_state,
            settled_parlays=settled_parlays,
        )

        if self.bot.is_live:
            self.bot.send_raw_message(report_msg)
            logger.info("📲 [TELEGRAM] Resumen diario de liquidación enviado exitosamente a tu chat.")
        else:
            logger.info(f"ℹ️ [TELEGRAM DRY-RUN]:\n{report_msg}")

        total_settled_count = len(settled_today) + len(settled_props_today) + len(settled_parlays)
        round_pnl = (
            sum(float(b.get("net_profit_pen") or 0.0) for b in settled_today)
            + sum(float(p.get("net_profit_pen") or 0.0) for p in settled_props_today)
            + sum(float(pl.get("pnl_pen") or 0.0) for pl in settled_parlays)
        )

        quotes_after = self._snapshot_observed_quote_counts()
        new_quotes_by_source = self._diff_quote_counts(quotes_before, quotes_after)

        try:
            self.db.checkpoint(truncate=True)
        except Exception as cp_exc:
            logger.warning(f"Database checkpoint warning: {cp_exc}")

        return {
            "status": "COMPLETED",
            "window": "SETTLEMENT",
            "matchday_date": today_str,
            "executed_at_pet": now_pet.strftime("%Y-%m-%dT%H:%M:%S"),
            "settled_count": total_settled_count,
            "settled_bets_count": len(settled_today),
            "settled_props_count": len(settled_props_today),
            "settled_parlays_count": len(settled_parlays),
            "daily_pnl_pen": round(round_pnl, 2),
            "settled_bankroll_pen": curr_br,
            "current_bankroll_pen": curr_br,
            "cppi_multiplier": cppi_mult,
            "sources_executed": sources_executed,
            "sources_skipped": sources_skipped,
            "new_quotes_persisted_by_source": new_quotes_by_source,
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
