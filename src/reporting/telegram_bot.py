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
        """Appends alert to local inspection ledger (skipped for repo default path during pytest)."""
        if os.environ.get("PYTEST_CURRENT_TEST") and self.alerts_log_path == Path("data/evaluation/latest_telegram_alerts.json"):
            return
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
        mkt = str(
            bet.get("market") or bet.get("market_type") or bet.get("stat_type") or "PICK"
        ).upper()
        raw_sel = str(
            bet.get("selection") or bet.get("side") or bet.get("player_name") or ""
        ).upper()
        line_val = bet.get("line_value")
        if line_val is not None and str(line_val) not in raw_sel:
            sel = f"{raw_sel} {line_val}".strip()
        else:
            sel = raw_sel
        odds_raw = (
            bet.get("decimal_odds_used")
            if bet.get("decimal_odds_used") is not None
            else bet.get("decimal_odds")
        )
        odds_str = f"{float(odds_raw):.2f}" if odds_raw is not None and float(odds_raw) > 1.0 else "N/A"
        prob_raw = (
            bet.get("calibrated_probability")
            if bet.get("calibrated_probability") is not None
            else (
                bet.get("model_prob")
                if bet.get("model_prob") is not None
                else bet.get("estimated_prob")
            )
        )
        prob_str = f"{float(prob_raw) * 100.0:.1f}%" if prob_raw is not None else "N/A"
        if bet.get("ev_pct") is not None:
            ev = float(bet["ev_pct"])
        elif bet.get("estimated_ev") is not None:
            ev = float(bet["estimated_ev"]) * 100.0
        else:
            ev = 0.0
        stake = float(bet.get("stake_pen") or bet.get("kelly_stake_pen") or 0.0)
        book = bet.get("odds_provider") or bet.get("bookmaker") or "Casa Peruana / Market"

        msg = (
            f"🎯 *[PICK PRINCIPAL] (70% Totales / 30% Moneyline)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 *Partido:* `{game_id}`\n"
            f"🎯 *Mercado:* `{mkt}` | *Selección:* *{sel}*\n"
            f"💰 *Casa Sugerida:* *{book}*\n"
            f"📈 *Cuota:* `{odds_str}` (Prob. Modelo: `{prob_str}`)\n"
            f"⚡ *Valor Esperado (EV):* `+{ev:.1f}%`\n"
            f"💵 *Stake Sugerido:* *S/ {stake:.2f} PEN*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 _Registra este pick revisando la cuota vigente en {book}_"
        )
        return msg

    def format_sgp_parlay_alert(self, sgp: dict[str, Any]) -> str:
        """Formats a multi-leg Correlated Same-Game Parlay into actionable Telegram markdown."""
        num_legs = sgp.get("num_legs", len(sgp.get("legs", []))) or 2
        odds_raw = sgp.get("offered_sgp_odds") or sgp.get("decimal_odds")
        odds_str = f"{float(odds_raw):.2f}" if odds_raw is not None and float(odds_raw) > 1.0 else "N/A"
        p_joint_raw = sgp.get("p_joint")
        p_joint_str = f"{float(p_joint_raw) * 100.0:.1f}%" if p_joint_raw is not None else "N/A"
        p_indep_raw = sgp.get("p_independent")
        p_indep_str = f"{float(p_indep_raw) * 100.0:.1f}%" if p_indep_raw is not None else "N/A"
        boost = float(sgp.get("correlation_boost_pct") or 0.0)
        ev = float(sgp.get("ev_pct") or 0.0)
        stake = float(sgp.get("kelly_stake_pen") or sgp.get("stake_pen") or 0.0)

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
            f"📊 *Prob. Cópula:* `{p_joint_str}` (vs `{p_indep_str}` indep.)\n"
            f"🚀 *Impulso de Correlación:* `+{boost:.1f}%`\n"
            f"📈 *Cuota Ofrecida:* `{odds_str}` (Justa: `{sgp.get('fair_sgp_odds', 0.0):.2f}`)\n"
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
        odds_raw = parlay.get("decimal_odds") or parlay.get("offered_sgp_odds")
        odds_str = f"{float(odds_raw):.2f}" if odds_raw is not None and float(odds_raw) > 1.0 else "N/A"
        win_p_raw = parlay.get("win_probability_pct") if parlay.get("win_probability_pct") is not None else (float(parlay.get("p_joint", 0.0)) * 100.0 if parlay.get("p_joint") is not None else None)
        win_p_str = f"{float(win_p_raw):.1f}%" if win_p_raw is not None else "N/A"
        ev = float(parlay.get("ev_pct") or 0.0)
        stake = float(parlay.get("stake_pen") or parlay.get("kelly_stake_pen") or 0.0)

        legs_text = ""
        for i, leg in enumerate(parlay.get("legs", []), 1):
            desc = leg.get("desc") or leg.get("selection") or f"Leg {i}"
            leg_p_raw = leg.get("prob")
            leg_p_str = f"{float(leg_p_raw) * 100.0:.1f}%" if leg_p_raw is not None else "N/A"
            leg_odds_raw = leg.get("odds")
            leg_odds_str = f"{float(leg_odds_raw):.2f}" if leg_odds_raw is not None and float(leg_odds_raw) > 1.0 else "N/A"
            legs_text += f"  {i}. {desc} @ `{leg_odds_str}` (Prob: `{leg_p_str}`)\n"

        msg = (
            f"🔥 *[COMBO ALPHA S/50] (Parlay de Alta Consistencia)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 *Estrategia:* *{strat_label}*\n"
            f"🏦 *Casa Sugerida:* *{book}*\n"
            f"📋 *Selecciones de Alta Consistencia:*\n{legs_text}"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *Probabilidad de Acierto:* *{win_p_str}*\n"
            f"💰 *Cuota Combinada:* `{odds_str}`\n"
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
        r_odds_raw = stale.get("retail_offered_odds") or stale.get("retail_odds")
        r_odds_str = f"{float(r_odds_raw):.2f}" if r_odds_raw is not None and float(r_odds_raw) > 1.0 else "N/A"
        sharp_odds_raw = stale.get("sharp_fair_odds") or stale.get("sharp_odds")
        sharp_odds_str = f"{float(sharp_odds_raw):.2f}" if sharp_odds_raw is not None and float(sharp_odds_raw) > 1.0 else "N/A"
        clv = float(stale.get("expected_clv_pct") or stale.get("clv_pct") or 0.0)
        stake = float(stale.get("kelly_stake_pen") or stale.get("stake_pen") or 0.0)

        msg = (
            f"⚡ *[ARBITRAJE / STALE LINE PERÚ]*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ *{retail_book} mantiene cuota desactualizada!*\n"
            f"🎯 *Selección:* *{sel}*\n"
            f"🏦 *Cuota en {retail_book}:* `{r_odds_str}`\n"
            f"📉 *Cuota Sharp ({sharp_book}):* `{sharp_odds_str}`\n"
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
        odds_a_raw = surebet.get("odds_a")
        odds_a_str = f"{float(odds_a_raw):.2f}" if odds_a_raw is not None and float(odds_a_raw) > 1.0 else "N/A"
        stake_a = float(surebet.get("stake_a_pen") or 0.0)

        b_b = surebet.get("book_b", "Casa B")
        sel_b = surebet.get("selection_b", "AWAY")
        odds_b_raw = surebet.get("odds_b")
        odds_b_str = f"{float(odds_b_raw):.2f}" if odds_b_raw is not None and float(odds_b_raw) > 1.0 else "N/A"
        stake_b = float(surebet.get("stake_b_pen") or 0.0)

        tot_invest = float(surebet.get("total_staked_pen") or (stake_a + stake_b))
        guaranteed_pnl = float(surebet.get("guaranteed_net_profit_pen") or surebet.get("guaranteed_pnl_pen") or 0.0)
        margin = float(surebet.get("arb_margin_pct") or surebet.get("arbitrage_margin_pct") or 0.0)

        msg = (
            f"💰 *ARBITRAJE LIBRE DE RIESGO (SUREBET PERÚ)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ *Retorno Matemático Garantizado!*\n"
            f"🏦 *Apuesta 1:* {b_a}\n"
            f"  • Selección: *{sel_a}* @ `{odds_a_str}`\n"
            f"  • Inversión: *S/ {stake_a:.2f} PEN*\n"
            f"🏦 *Apuesta 2:* {b_b}\n"
            f"  • Selección: *{sel_b}* @ `{odds_b_str}`\n"
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


DEFAULT_ALERT_STATE_PATH = Path("data/evaluation/dispatched_telegram_alerts.json")


def load_dispatched_alert_keys(state_path: Path = DEFAULT_ALERT_STATE_PATH) -> set[str]:
    """Loads previously sent Telegram alert keys to prevent duplicate notifications."""
    if not state_path.exists():
        return set()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x) for x in data if x}
        if isinstance(data, dict) and isinstance(data.get("keys"), list):
            return {str(x) for x in data["keys"] if x}
    except Exception:
        return set()
    return set()


def save_dispatched_alert_keys(
    keys: set[str],
    state_path: Path = DEFAULT_ALERT_STATE_PATH,
    *,
    max_entries: int = 500,
) -> None:
    """Persists bounded set of dispatched Telegram alert keys."""
    if os.environ.get("PYTEST_CURRENT_TEST") and state_path == DEFAULT_ALERT_STATE_PATH:
        return
    try:
        ordered = sorted(keys)[-max_entries:]
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps({"keys": ordered}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning(f"No se pudo guardar ledger de alertas Telegram: {exc}")


def format_slate_status_summary(cycle_res: dict[str, Any], *, pending_count: int = 0) -> str:
    """Formats a concise daily slate status summary when no new +EV picks meet thresholds."""
    mode = str(cycle_res.get("mode", "pregame")).upper()
    preds = int(cycle_res.get("predictions_generated") or cycle_res.get("candidates_evaluated") or 0)
    raw_bets = cycle_res.get("bets_placed")
    if raw_bets is None:
        raw_bets = cycle_res.get("new_bets_placed_in_cycle")
    bets_new = int(raw_bets or 0)
    bankroll_info = cycle_res.get("bankroll_state") or {}
    equity = float(bankroll_info.get("settled_bankroll_pen", 0.0) or 0.0)
    return (
        f"📋 *REPORTE DE JORNADA NBA ({mode})*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔎 *Mercados evaluados:* `{preds}`\n"
        f"✅ *Apuestas +EV nuevas (>=5%):* `{bets_new}` (Pendientes: `{pending_count}`)\n"
        f"💼 *Banca Liquidada:* *S/ {equity:.2f} PEN*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ _Disciplina activa: sin picks forzado cuando el mercado no ofrece ventaja estadística._"
    )


def format_injury_sniper_alert(alert: dict[str, Any]) -> str:
    """Formats an InjurySniperMonitor alert into actionable Telegram markdown."""
    odds_val = alert.get("decimal_odds")
    odds_str = f"{float(odds_val):.2f}" if odds_val is not None and float(odds_val) > 1.0 else "N/A"
    transitions = alert.get("transitions") or []
    if transitions and isinstance(transitions, list):
        parts = [
            f"{t.get('player_name', 'Jugador')} ({t.get('team', '?')} → {t.get('new_status', 'OUT')})"
            for t in transitions[:3]
            if isinstance(t, dict)
        ]
        injury_summary = ", ".join(parts) if parts else str(alert.get("absent_star") or "Baja reportada")
    else:
        injury_summary = str(alert.get("absent_star") or "Baja reportada")

    shift_raw: Any = alert.get("synergy_shift")
    if shift_raw is None:
        shift_raw = alert.get("net_penalty")
    synergy_shift = float(shift_raw) if isinstance(shift_raw, (int, float, str)) else 0.0

    ev_raw: Any = alert.get("ev_lower_bound_pct")
    ev_lb = float(ev_raw) if isinstance(ev_raw, (int, float, str)) else 0.0

    stake_raw: Any = alert.get("kelly_stake_pen")
    if stake_raw is None:
        stake_raw = alert.get("stake_pen")
    stake_pen = float(stake_raw) if isinstance(stake_raw, (int, float, str)) else 0.0

    rational = str(alert.get("rational") or "").strip()
    rational_line = f"\n📝 *Detalle:* {rational}" if rational else ""

    return (
        f"🚨 *ALERTA INJURY SNIPER (T-2H / T-30M)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 *Partido:* `{alert.get('game_id', 'NBA')}`\n"
        f"⚠️ *Baja Detectada:* {injury_summary}\n"
        f"📈 *Impacto en Sinergia:* `{synergy_shift:+.1f} pts`\n"
        f"🎯 *Pick Generado:* *{alert.get('selection', 'N/A')}* @ `{odds_str}`\n"
        f"⚡ *EV Lower-Bound:* `+{ev_lb:.1f}%`\n"
        f"💵 *Stake Sugerido:* *S/ {stake_pen:.2f} PEN*{rational_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )


def dispatch_pending_bet_alerts(
    bot: TelegramAlertBot,
    db: Any,
    *,
    min_ev: float = 5.0,
    max_alerts: int = 5,
    state_path: Path = DEFAULT_ALERT_STATE_PATH,
    dry_run: bool = False,
) -> int:
    """Dispatches newly created PENDING +EV simulated bets without duplicating sent bet_ids."""
    pending_bets = db.fetch_all(
        """
        SELECT b.bet_id, b.game_id, b.matchday_date, b.market, b.selection, b.line_value,
               b.decimal_odds, b.estimated_prob, b.estimated_ev, b.stake_pen,
               p.calibrated_probability, p.ev_pct, p.odds_provider
        FROM simulated_bets b
        LEFT JOIN predictions p ON b.prediction_id = p.prediction_id
        WHERE b.status = 'PENDING'
          AND COALESCE(p.ev_pct, COALESCE(b.estimated_ev, 0.0) * 100.0) >= ?
        ORDER BY b.emitted_at DESC
        LIMIT ?
        """,
        (float(min_ev), int(max_alerts)),
    )
    sent_keys = load_dispatched_alert_keys(state_path)
    dispatched = 0
    for b in pending_bets:
        bet_key = f"BET:{b['bet_id']}"
        if bet_key in sent_keys:
            continue
        msg = bot.format_single_bet_alert(b)
        if bot.send_raw_message(msg):
            sent_keys.add(bet_key)
            dispatched += 1
    should_persist = (not dry_run) and (bot.is_live or state_path != DEFAULT_ALERT_STATE_PATH)
    if dispatched > 0 and should_persist:
        save_dispatched_alert_keys(sent_keys, state_path)
    return dispatched
