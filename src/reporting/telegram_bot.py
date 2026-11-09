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
        except Exception:
            pass


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
        except Exception:
            pass

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
            f"🏀 *ALERTA +EV | NBA INTELLIGENCE V9*\n"
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
            f"🔥 *COMBINADA CORRELACIONADA (SGP {num_legs}-LEGS)*\n"
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
            f"🚨 *LÍNEA DESFASADA DETECTADA (STALE LINE)*\n"
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
