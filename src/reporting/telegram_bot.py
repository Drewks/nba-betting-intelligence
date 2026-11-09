"""
V9 Phase 4: Telegram & Webhook Interactive Alert Dispatcher (src/reporting/telegram_bot.py).
Formats and sends instant notifications in Soles (S/. PEN) for +EV Bets, Correlated SGPs,
and Stale Lines on Peruvian sportsbooks (RETAbet, Betsson, Doradobet, Coolbet).
Supports live Telegram Bot API and graceful dry-run simulation mode.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


def _load_dotenv_if_present() -> None:
    """Loads local .env file into os.environ if present without overwriting existing env vars."""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                cleaned = line.strip()
                if cleaned and not cleaned.startswith("#") and "=" in cleaned:
                    k, v = cleaned.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'").strip('"')
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception as exc:
            logging.warning(f"Handled exception in telegram_bot (line 35): {exc}")


_load_dotenv_if_present()


class TelegramAlertBot:
    """
    Automated Telegram notification dispatcher for NBA Betting Intelligence.
    Operates in live mode when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set,
    or dry-run simulation mode with local JSON ledger tracking.
    """

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        alerts_log_path: Path | str = "data/evaluation/latest_telegram_alerts.json",
    ) -> None:
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self.alerts_log_path = Path(alerts_log_path)
        self.is_live = bool(self.bot_token and self.chat_id)

    def send_raw_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Sends raw markdown message via Telegram Bot API or logs locally in dry-run mode."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not self.is_live:
            logger.info(f"[TELEGRAM DRY-RUN SIMULATION] Message:\n{text}")
            self._persist_alert_log({"text": text, "sent_at": now_str, "mode": "DRY_RUN"})
            return True

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                success = (resp.status == 200)
                self._persist_alert_log({"text": text, "sent_at": now_str, "mode": "LIVE_TELEGRAM"})
                return success
        except Exception as exc:
            logger.warning(f"Failed to deliver Telegram notification: {exc}")
            return False

    def _persist_alert_log(self, record: dict[str, Any]) -> None:
        """Appends alert to local inspection ledger."""
        try:
            self.alerts_log_path.parent.mkdir(parents=True, exist_ok=True)
            existing = []
            if self.alerts_log_path.exists():
                try:
                    existing = json.loads(self.alerts_log_path.read_text(encoding="utf-8"))
                except Exception:
                    existing = []
            existing.append(record)
            # Keep last 50 alerts
            self.alerts_log_path.write_text(json.dumps(existing[-50:], indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logging.warning(f"Handled exception in telegram_bot (line 99): {exc}")

    def format_single_bet_alert(self, bet: dict[str, Any]) -> str:
        """Formats a standard +EV moneyline or totals pick into actionable Telegram markdown."""
        game_id = bet.get("game_id", "NBA Game")
        mkt = bet.get("market", "").upper()
        sel = bet.get("selection", "").upper()
        odds = float(bet.get("decimal_odds_used") or bet.get("decimal_odds") or 1.90)
        prob = float(bet.get("calibrated_probability") or bet.get("model_prob") or 0.55) * 100.0
        ev = float(bet.get("ev_pct") or 0.0)
        stake = float(bet.get("stake_pen") or bet.get("kelly_stake_pen") or 1.00)
        book = bet.get("odds_provider") or bet.get("bookmaker") or "RETAbet Perú"

        msg = (
            f"🎯 *[PICK PRINCIPAL] (70% Totales / 30% Moneyline)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 *Partido:* `{game_id}`\n"
            f"🎯 *Mercado:* `{mkt}` | *Selección:* *{sel}*\n"
            f"💰 *Casa Sugerida:* *{book}*\n"
            f"📈 *Cuota:* `{odds:.2f}` (Prob. Modelo: `{prob:.1f}%`)\n"
            f"⚡ *Valor Esperado (EV):* `+{ev:.1f}%`\n"
            f"💵 *Stake Sugerido:* *S/ {stake:.2f} PEN*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 _Copia el pick directamente en tu app de {book}_"
        )
        return msg

    def format_sgp_parlay_alert(self, sgp: dict[str, Any]) -> str:
        """Formats a multi-leg Correlated Same-Game Parlay into actionable Telegram markdown."""
        num_legs = sgp.get("num_legs", len(sgp.get("legs", []))) or 2
        odds = float(sgp.get("offered_sgp_odds", 3.50))
        p_joint = float(sgp.get("p_joint", 0.25)) * 100.0
        p_indep = float(sgp.get("p_independent", 0.18)) * 100.0
        boost = float(sgp.get("correlation_boost_pct", 25.0))
        ev = float(sgp.get("ev_pct", 15.0))
        stake = float(sgp.get("kelly_stake_pen", 2.00))

        legs_text = ""
        for i, leg in enumerate(sgp.get("legs", []), 1):
            p_n = leg.get("player_name", leg.get("team", f"Leg {i}"))
            cat = leg.get("category", "")
            sel = leg.get("selection", "")
            line = leg.get("line", "")
            legs_text += f"  {i}. {p_n} {cat} {sel} {line}\n"

        if not legs_text:
            legs_text = f"  • {sgp.get('player_name', 'Player')} + {sgp.get('game_selection', 'Selection')}\n"

        msg = (
            f"🔥 *[COMBO ALPHA S/50] (SGP Cópulas Correlacionadas {num_legs}-Legs)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 *Crea tu Apuesta (RETAbet / Betsson Perú)*\n"
            f"📋 *Selecciones:*\n{legs_text}"
            f"📊 *Prob. Cópula:* `{p_joint:.1f}%` (vs `{p_indep:.1f}%` indep.)\n"
            f"🚀 *Impulso de Correlación:* `+{boost:.1f}%`\n"
            f"📈 *Cuota Ofrecida:* `{odds:.2f}` (Justa: `{sgp.get('fair_sgp_odds', 0.0):.2f}`)\n"
            f"⚡ *Valor Esperado (EV):* `+{ev:.1f}%`\n"
            f"💵 *Stake Sugerido:* *S/ {stake:.2f} PEN*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ _Apostar con moderación y gestión de banca en Soles._"
        )
        return msg

    def format_high_prob_parlay_alert(self, parlay: dict[str, Any]) -> str:
        """Formats a High-Probability Lock Builder Parlay (Pure Alpha Mode)."""
        parlay.get("num_legs", len(parlay.get("legs", [])))
        strat = parlay.get("strategy", "SAME_GAME_ANCHOR")
        strat_label = "Mismo Partido (SGP)" if strat == "SAME_GAME_ANCHOR" else "Cruzada Multi-Partido"
        book = parlay.get("bookmaker", "RETAbet / Betsson Perú")
        odds = float(parlay.get("decimal_odds") or parlay.get("offered_sgp_odds") or 2.30)
        win_p = float(parlay.get("win_probability_pct") or (float(parlay.get("p_joint", 0.65)) * 100.0))
        ev = float(parlay.get("ev_pct", 25.0))
        stake = float(parlay.get("stake_pen") or parlay.get("kelly_stake_pen") or 8.50)

        legs_text = ""
        for i, leg in enumerate(parlay.get("legs", []), 1):
            desc = leg.get("desc") or leg.get("selection") or f"Leg {i}"
            leg_p = float(leg.get("prob", 0.80)) * 100.0
            leg_odds = float(leg.get("odds", 1.28))
            legs_text += f"  {i}. {desc} @ `{leg_odds:.2f}` (Prob: `{leg_p:.1f}%`)\n"

        msg = (
            f"🔥 *[COMBO ALPHA S/50] (Parlay de Alta Consistencia)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 *Estrategia:* *{strat_label}*\n"
            f"🏦 *Casa Sugerida:* *{book}*\n"
            f"📋 *Selecciones de Alta Consistencia:*\n{legs_text}"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *Probabilidad de Acierto:* *{win_p:.1f}%*\n"
            f"💰 *Cuota Combinada:* `{odds:.2f}`\n"
            f"⚡ *Valor Esperado (EV):* `+{ev:.1f}%`\n"
            f"💵 *Stake Alfa Sugerido:* *S/ {stake:.2f} PEN*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 _Eventos de máxima probabilidad multiplicados para óptimo rendimiento._"
        )
        return msg

    def format_stale_line_alert(self, stale: dict[str, Any]) -> str:
        """Formats a fast-breaking stale line latency opportunity."""
        retail_book = stale.get("retail_provider", "RETAbet Perú")
        sharp_book = stale.get("sharp_provider", "Pinnacle")
        sel = stale.get("selection", "")
        r_odds = float(stale.get("retail_offered_odds", 1.90))
        sharp_odds = float(stale.get("sharp_fair_odds", 1.70))
        clv = float(stale.get("expected_clv_pct", 8.0))
        stake = float(stale.get("kelly_stake_pen", 3.00))

        msg = (
            f"⚡ *[ARBITRAJE / STALE LINE PERÚ]*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ *{retail_book} mantiene cuota desactualizada!*\n"
            f"🎯 *Selección:* *{sel}*\n"
            f"🏦 *Cuota en {retail_book}:* `{r_odds:.2f}`\n"
            f"📉 *Cuota Sharp ({sharp_book}):* `{sharp_odds:.2f}`\n"
            f"💎 *Ventaja CLV Esperada:* `+{clv:.1f}%`\n"
            f"💵 *Stake Sugerido:* *S/ {stake:.2f} PEN*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ _Aprovechar antes de que el bookmaker actualice la línea._"
        )
        return msg

    def format_surebet_alert(self, surebet: dict[str, Any]) -> str:
        """Formats a risk-free cross-bookmaker surebet arbitrage opportunity in Soles."""
        b_a = surebet.get("book_a", "Casa A")
        sel_a = surebet.get("selection_a", "HOME")
        odds_a = float(surebet.get("odds_a", 2.10))
        stake_a = float(surebet.get("stake_a_pen", 50.0))

        b_b = surebet.get("book_b", "Casa B")
        sel_b = surebet.get("selection_b", "AWAY")
        odds_b = float(surebet.get("odds_b", 2.05))
        stake_b = float(surebet.get("stake_b_pen", 50.0))

        tot_invest = float(surebet.get("total_staked_pen", 100.0))
        guaranteed_pnl = float(surebet.get("guaranteed_net_profit_pen", surebet.get("guaranteed_pnl_pen", 4.50)))
        margin = float(surebet.get("arb_margin_pct", surebet.get("arbitrage_margin_pct", 4.5)))

        msg = (
            f"💰 *ARBITRAJE LIBRE DE RIESGO (SUREBET PERÚ)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ *Retorno Matemático Garantizado!*\n"
            f"🏦 *Apuesta 1:* {b_a}\n"
            f"  • Selección: *{sel_a}* @ `{odds_a:.2f}`\n"
            f"  • Inversión: *S/ {stake_a:.2f} PEN*\n"
            f"🏦 *Apuesta 2:* {b_b}\n"
            f"  • Selección: *{sel_b}* @ `{odds_b:.2f}`\n"
            f"  • Inversión: *S/ {stake_b:.2f} PEN*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 *Inversión Total:* `S/ {tot_invest:.2f} PEN`\n"
            f"📈 *Margen de Arbitraje:* `+{margin:.2f}%`\n"
            f"🏆 *Beneficio Neto Seguro:* *+S/ {guaranteed_pnl:.2f} PEN*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ _Colocar ambas apuestas simultáneamente antes de que se ajusten las líneas._"
        )
        return msg

    def format_daily_settlement_report(
        self,
        matchday_date: str,
        settled_bets: list[dict[str, Any]],
        settled_props: list[dict[str, Any]],
        current_bankroll_pen: float,
        initial_bankroll_pen: float = 100.0,
        peak_bankroll_pen: float | None = None,
        cppi_multiplier: float = 1.0,
        parlay_bankroll_state: dict[str, Any] | None = None,
        settled_parlays: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Formats comprehensive end-of-day settlement summary in Soles (S/. PEN).
        Displays won/lost counts, daily net profit, win rate %, updated bankroll,
        and CPPI capital preservation shield status.
        """
        all_items = settled_bets + settled_props
        total_count = len(all_items)
        if total_count == 0:
            return (
                f"🌙 *RESUMEN DIARIO DE LIQUIDACIÓN | NBA INTELLIGENCE*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📅 *Fecha:* `{matchday_date}`\n"
                f"ℹ️ _No hubo apuestas ni props pendientes de liquidar en esta jornada._\n"
                f"💰 *Bankroll Actual:* `S/ {current_bankroll_pen:.2f} PEN`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )

        won_count = sum(1 for x in all_items if str(x.get("status")).upper() == "WON")
        lost_count = sum(1 for x in all_items if str(x.get("status")).upper() == "LOST")
        push_count = sum(1 for x in all_items if str(x.get("status")).upper() == "PUSH")

        daily_profit = sum(float(x.get("net_profit_pen") or 0.0) for x in all_items)
        total_staked = sum(float(x.get("stake_pen") or x.get("stake") or 0.0) for x in all_items)
        win_rate = (won_count / max(1, won_count + lost_count)) * 100.0
        daily_roi = (daily_profit / max(0.01, total_staked)) * 100.0

        pnl_symbol = "📈" if daily_profit >= 0 else "📉"
        pnl_sign = "+" if daily_profit >= 0 else ""

        peak = peak_bankroll_pen or max(initial_bankroll_pen, current_bankroll_pen)
        cppi_floor = peak * 0.85

        items_detail = ""
        for i, item in enumerate(all_items[:8], 1):
            st = str(item.get("status")).upper()
            icon = "✅" if st == "WON" else ("❌" if st == "LOST" else "⏸️")
            pnl_item = float(item.get("net_profit_pen") or 0.0)
            sign_item = "+" if pnl_item >= 0 else ""
            desc = item.get("player_name") or f"{item.get('game_id', 'Game')} {item.get('market', '')} {item.get('selection', '')}"
            cat = item.get("prop_category") or ""
            line = item.get("line_value") or ""
            sel = item.get("selection") or ""
            target = f"{cat} {sel} {line}".strip()
            detail_line = f"  {i}. {icon} {desc} {target} ({sign_item}S/ {pnl_item:.2f})\n"
            items_detail += detail_line

        if total_count > 8:
            items_detail += f"  ... y {total_count - 8} selecciones más.\n"

        parlay_section = ""
        if parlay_bankroll_state:
            p_bal = float(parlay_bankroll_state.get("settled_bankroll_pen") or 50.0)
            p_profit = float(parlay_bankroll_state.get("cumulative_net_profit_pen") or 0.0)
            p_roi = float(parlay_bankroll_state.get("roi_pct") or 0.0)
            p_sign = "+" if p_profit >= 0 else ""
            p_sym = "🟢" if p_profit >= 0 else "🔴"
            s_parlays = settled_parlays or []
            p_detail = ""
            for sp in s_parlays:
                s_icon = "✅" if sp.get("status") == "WON" else ("❌" if sp.get("status") == "LOST" else "⏸️")
                p_detail += f"    • {s_icon} `{sp.get('parlay_id')}`: {sp.get('summary', '')} ({sp.get('net_profit_pen', 0):+.2f} PEN)\n"

            parlay_section = (
                f"\n🔥 *Sub-Bankroll Combinadas (S/ 50.00 PEN — Alpha Lab):*\n"
                f"  • Saldo Liquidado: *S/ {p_bal:.2f} PEN*\n"
                f"  • {p_sym} PnL Acumulado: `{p_sign}S/ {p_profit:.2f} PEN` ({p_sign}{p_roi:.1f}% ROI)\n"
            )
            if p_detail:
                parlay_section += f"  • Combinadas Resueltas Hoy:\n{p_detail}"

        msg = (
            f"🌙 *RESUMEN DIARIO DE LIQUIDACIÓN | NBA INTELLIGENCE*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 *Jornada:* `{matchday_date}`\n"
            f"💰 *Bankroll Principal:* `S/ {current_bankroll_pen:.2f} PEN` (Pico: `S/ {peak:.2f}`)\n"
            f"🛡️ *Escudo CPPI:* `{cppi_multiplier * 100:.1f}%` (Piso 85%: `S/ {cppi_floor:.2f} PEN`)\n\n"
            f"📊 *Balance de la Jornada (Banca Principal):*\n"
            f"  • Total Selecciones: `{total_count}`\n"
            f"  • {won_count} Ganadas ✅ | {lost_count} Perdidas ❌ | {push_count} PUSH ⏸️\n"
            f"  • *Win Rate:* `{win_rate:.1f}%`\n"
            f"  • {pnl_symbol} *Resultado Neto:* `{pnl_sign}S/ {daily_profit:.2f} PEN` (ROI: `{pnl_sign}{daily_roi:.1f}%`)\n\n"
            f"📋 *Desglose de Resultados (Banca Principal):*\n{items_detail}"
            f"{parlay_section}"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔒 _Historial y balance auditado e inmutable en SQLite (Dual Bankroll: S/100 + S/50)._"
        )
        return msg
