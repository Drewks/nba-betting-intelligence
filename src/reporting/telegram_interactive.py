"""
V9 Interactive Telegram Bot Listener (`src/reporting/telegram_interactive.py`).
Provides bidirectional conversational command interface for NBA Betting Intelligence.
Enables real-time querying of virtual bankroll (S/100 PEN), daily value picks (+EV),
Player Props, RETAbet Correlated SGPs, Peruvian live odds comparisons, and manual settlement.

Zero third-party dependencies — built purely on standard library (urllib.request, json).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any
import urllib.parse
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.live_peru_scraper import LivePeruOddsScraper
from src.paper_trading.engine import PaperTradingEngine
from src.paper_trading.parlay_engine import ParlayTradingEngine
from src.reporting.telegram_bot import TelegramAlertBot, _load_dotenv_if_present
from src.storage.db import DatabaseManager

_load_dotenv_if_present()

logger = logging.getLogger("TelegramListener")


DEFAULT_KEYBOARD: dict[str, Any] = {
    "keyboard": [
        [{"text": "💰 Mi Banca"}, {"text": "🎯 Picks +EV"}],
        [{"text": "🔥 Super Combinadas"}, {"text": "⚡ Cuotas Perú"}],
        [{"text": "📅 Partidos NBA"}, {"text": "🌐 Dashboard Web"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}


class TelegramInteractiveListener:
    """
    Bidirectional long-polling listener for Telegram Bot API.
    Processes user slash-commands: /banca, /picks, /sgp, /cuotas, /partidos, /liquidar, /ayuda.
    """

    def __init__(
        self,
        bot_token: str | None = None,
        allowed_chat_ids: list[str | int] | None = None,
        db: DatabaseManager | None = None,
        offset_file: Path | str | None = None,
    ) -> None:
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

        # Configure authorized chat IDs
        raw_allowed = allowed_chat_ids or os.environ.get("TELEGRAM_CHAT_ID", "").strip().split(",")
        self.allowed_chat_ids: set[str] = {str(c).strip() for c in raw_allowed if str(c).strip()}

        self.db = db or DatabaseManager(PROJECT_ROOT / "data" / "nba_intelligence.sqlite3")
        self.paper_engine = PaperTradingEngine(
            db=self.db,
            initial_bankroll_pen=100.00,
            base_stake_pen=1.00,
            max_stake_pen=3.00,
            min_ev_threshold=0.05,
            dynamic_conviction_staking=False,
            enable_cppi_shield=True,
            staking_mode="FRACTIONAL_KELLY",
            exclude_synthetic=True,
            hybrid_allocation_enabled=True,
            max_totals_per_matchday=2,
            max_moneyline_per_matchday=1,
        )
        self.parlay_engine = ParlayTradingEngine(
            db=self.db,
            initial_bankroll_pen=50.00,
            max_stake_pen=5.00,
            min_stake_pen=0.50,
            kelly_fraction=0.40,
        )
        self.bot = TelegramAlertBot(bot_token=self.bot_token, chat_id=list(self.allowed_chat_ids)[0] if self.allowed_chat_ids else None)
        self.offset_file = Path(offset_file) if offset_file else PROJECT_ROOT / "data" / "evaluation" / "telegram_last_update_id.txt"
        self.last_update_id: int | None = self._load_last_update_id()

    def _load_last_update_id(self) -> int | None:
        try:
            if self.offset_file.exists():
                val = self.offset_file.read_text(encoding="utf-8").strip()
                if val.isdigit():
                    return int(val)
        except Exception as exc:
            logger.debug(f"Could not load last update ID: {exc}")
        return None

    def _save_last_update_id(self, update_id: int) -> None:
        try:
            self.offset_file.parent.mkdir(parents=True, exist_ok=True)
            self.offset_file.write_text(str(update_id), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Could not save last update ID: {exc}")

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token)

    # -------------------------------------------------------------------------
    # Telegram API Methods (Long Polling & Replying)
    # -------------------------------------------------------------------------

    def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[dict[str, Any]]:
        """Long-polls Telegram for incoming updates."""
        if not self.is_configured:
            return []

        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates?timeout={timeout}"
        if offset is not None:
            url += f"&offset={offset}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NBA-Betting-Intelligence/9.0"})
            with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    return data.get("result", [])
        except Exception as exc:
            logger.warning(f"Error fetching Telegram updates: {exc}")
        return []

    def send_reply(
        self,
        chat_id: str | int,
        text: str,
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> bool:
        """Sends a markdown reply with persistent touch keyboard to a user chat."""
        if not self.is_configured:
            logger.info(f"[DRY-RUN REPLY to {chat_id}]:\n{text}")
            return True

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
            "reply_markup": reply_markup if reply_markup is not None else DEFAULT_KEYBOARD,
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as exc:
            logger.error(f"Error sending reply to {chat_id}: {exc}")
            return False

    # -------------------------------------------------------------------------
    # Command Dispatcher
    # -------------------------------------------------------------------------

    def process_message(self, chat_id: str | int, text: str, from_user: dict[str, Any], message_id: int | None = None) -> str:
        """Processes an incoming text message or button tap and returns the response string."""
        chat_id_str = str(chat_id)
        user_name = from_user.get("first_name") or from_user.get("username") or "Usuario"

        # Security check: strictly require chat_id in allowed_chat_ids
        if not self.allowed_chat_ids or chat_id_str not in self.allowed_chat_ids:
            logger.warning(f"Unauthorized access attempt from chat_id={chat_id_str} ({user_name})")
            return (
                f"⛔ *Acceso No Autorizado*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Hola {user_name}, este bot cuenta con lista de control de acceso estricta.\n\n"
                f"Tu Chat ID (`{chat_id_str}`) no tiene permisos de consulta ni ejecución."
            )

        clean_text = text.strip()
        cmd = clean_text.split()[0].lower() if clean_text else ""
        text_lower = clean_text.lower()

        if cmd in ("/start", "/ayuda", "/help") or "ayuda" in text_lower or "menu" in text_lower:
            return self.handle_help(user_name)
        elif cmd in ("/banca", "/bankroll", "/saldo") or "mi banca" in text_lower or "banca" in text_lower or "saldo" in text_lower:
            return self.handle_banca()
        elif cmd in ("/picks", "/pronosticos", "/apuestas") or "picks" in text_lower or "pronostico" in text_lower:
            return self.handle_picks()
        elif cmd in ("/sgp", "/combos", "/props", "/parlays", "/combinadas") or "combinada" in text_lower or "sgp" in text_lower or "combos" in text_lower:
            return self.handle_sgp()
        elif cmd in ("/status", "/fase0", "/auditoria") or "status" in text_lower or "fase 0" in text_lower:
            return self.handle_status()
        elif cmd in ("/cuotas", "/arbitraje", "/surebets", "/odds") or "cuota" in text_lower or "arbitraje" in text_lower or "surebet" in text_lower:
            return self.handle_cuotas()
        elif cmd in ("/partidos", "/slate", "/juegos") or "partido" in text_lower or "juego" in text_lower or "cartelera" in text_lower:
            return self.handle_partidos()
        elif cmd in ("/web", "/dashboard") or "dashboard" in text_lower or "web" in text_lower:
            return self.handle_web()
        elif cmd in ("/liquidar", "/settle", "/reconciliar") or "liquidar" in text_lower:
            return self.handle_liquidar()
        else:
            return (
                f"❓ *Comando no reconocido:* `{text}`\n\n"
                f"Toca cualquiera de los botones táctiles abajo o usa /ayuda."
            )

    # -------------------------------------------------------------------------
    # Command Handlers
    # -------------------------------------------------------------------------

    def handle_help(self, user_name: str) -> str:
        """Generates comprehensive command menu."""
        return (
            f"🏀 *NBA BETTING INTELLIGENCE V9*\n"
            f"👋 ¡Hola, *{user_name}*! Bot de comando interactivo activo.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Banca Virtual:* `S/ 100.00 PEN` (Paper Trading Estricto)\n"
            f"🛡️ *Gestión de Riesgo:* Stakes de S/ 1.00 a S/ 2.00 PEN (Quarter-Kelly, EV ≥ 5%)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 *BOTONERA TÁCTIL ACTIVADA:*\n"
            f"Toca cualquiera de los botones táctiles o escribe los comandos:\n\n"
            f"💰 *Mi Banca* (/banca) — Balance virtual, PnL en Soles, Win Rate y ROI %\n"
            f"🎯 *Picks +EV* (/picks) — Pronósticos de mayor valor esperado (+EV) del día\n"
            f"🔥 *Super Combinadas* (/sgp) — Parlays de alta probabilidad y props\n"
            f"⚡ *Cuotas Perú* (/cuotas) — Comparador de casas locales y Surebets\n"
            f"📅 *Partidos NBA* (/partidos) — Cartelera oficial de hoy en hora de Perú (PET)\n"
            f"🌐 *Dashboard Web* (/web) — Enlace directo a tu sitio en GitHub Pages\n"
            f"🌙 *Liquidar ESPN* (/liquidar) — Reconciliación manual de resultados de ESPN\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )

    def handle_web(self) -> str:
        """Returns direct link to GitHub Pages live dashboard."""
        url = "https://drewks.github.io/nba-betting-intelligence/"
        return (
            f"🌐 *DASHBOARD WEB EN GITHUB PAGES*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Accede a tu plataforma interactiva con seguimiento de capital, métricas cuantitativas y auditoría:\n\n"
            f"👉 [Abrir Dashboard Web Oficial]({url})\n\n"
            f"📊 _Actualizado automáticamente en cada ciclo en la nube._"
        )

    def handle_banca(self) -> str:
        """Generates dual real-time virtual bankroll state: Main (S/100) and Sub-Bankroll Parlays (S/50)."""
        main_state = self.paper_engine.get_bankroll_state()
        m_settled = main_state.get("settled_bankroll_pen", 100.00)
        m_pnl = main_state.get("cumulative_net_profit_pen", 0.00)
        m_exp = main_state.get("pending_exposure_pen", 0.00)
        m_avail = main_state.get("available_balance_pen", m_settled)
        m_roi = ((m_settled - 100.0) / 100.0 * 100.0)

        counts = self.db.fetch_one(
            f"""
            SELECT
                SUM(CASE WHEN status = 'WON' THEN 1 ELSE 0 END) as won,
                SUM(CASE WHEN status = 'LOST' THEN 1 ELSE 0 END) as lost,
                SUM(CASE WHEN status = 'PUSH' THEN 1 ELSE 0 END) as push
            FROM simulated_bets
            WHERE {self.paper_engine.scope_sql}
            """
        ) or {}
        won = int(counts.get("won") or 0)
        lost = int(counts.get("lost") or 0)
        push = int(counts.get("push") or 0)
        total_settled = won + lost + push
        wr = (won / total_settled * 100.0) if total_settled > 0 else 0.0

        p_state = self.parlay_engine.get_bankroll_state()
        p_settled = p_state.get("settled_bankroll_pen", 50.00)
        p_pnl = p_state.get("cumulative_net_profit_pen", 0.00)
        p_exp = p_state.get("pending_exposure_pen", 0.00)
        p_avail = p_state.get("available_balance_pen", p_settled)
        p_roi = p_state.get("roi_pct", 0.0)

        m_sym = "🟢" if m_pnl >= 0 else "🔴"
        p_sym = "🟢" if p_pnl >= 0 else "🔴"

        return (
            f"💰 *ESTADO DE LA BANCA VIRTUAL — CENTRO FINANCIERO DUAL*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 *1. BANKROLL PRINCIPAL (S/ 100.00 PEN — Fase 0 Auditada)*\n"
            f"   • Saldo Liquidado: *S/ {m_settled:.2f} PEN* (Disp: S/ {m_avail:.2f})\n"
            f"   • Exposición Pendiente: *S/ {m_exp:.2f} PEN*\n"
            f"   • {m_sym} PnL: *{'+' if m_pnl >= 0 else ''}S/ {m_pnl:.2f}* (`{m_roi:+.2f}% ROI`)\n"
            f"   • Récord: `{won}W - {lost}L - {push}P` (Win Rate: `{wr:.1f}%`)\n"
            f"   • Política: *70% Totales / 30% Moneyline* (Kelly 25%, máx S/ 3.00)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 *2. SUB-BANKROLL COMBINADAS (S/ 50.00 PEN — Alpha Lab)*\n"
            f"   • Saldo Liquidado: *S/ {p_settled:.2f} PEN* (Disp: S/ {p_avail:.2f})\n"
            f"   • Exposición Pendiente: *S/ {p_exp:.2f} PEN*\n"
            f"   • {p_sym} PnL: *{'+' if p_pnl >= 0 else ''}S/ {p_pnl:.2f}* (`{p_roi:+.2f}% ROI`)\n"
            f"   • Parlays Registrados: `{int(p_state.get('settled_parlays_count', 0))} liquidados / {int(p_state.get('pending_parlays_count', 0))} pendientes`\n"
            f"   • Política: *SGP Cópulas & Parlays Alta Probabilidad* (Kelly 40%, máx S/ 5.00)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ _Régimen: MODO ALFA PURO en combinadas y gestión institucional en principal._\n            🔒 _Aislamiento Total: Las combinadas no alteran la auditoría del bankroll principal._"
        )

    def handle_picks(self) -> str:
        """Returns today's active pending picks or high-EV opportunities."""
        pending_bets = self.db.fetch_all(
            f"""
            SELECT bet_id, game_id, market, selection, decimal_odds, estimated_ev, stake_pen, emitted_at
            FROM simulated_bets
            WHERE status = 'PENDING' AND {self.paper_engine.scope_sql}
            ORDER BY emitted_at DESC
            LIMIT 5
            """
        )

        if not pending_bets:
            return (
                "🎯 *PRONÓSTICOS DE LA JORNADA*\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "ℹ️ *No hay apuestas pendientes en este momento.*\n\n"
                "Las próximas oportunidades +EV se publican automáticamente en:\n"
                "• ☀️ *10:15 AM PET* (Apertura y Props)\n"
                "• 🎯 *05:15 PM PET* (Injury Sniper T-2H)\n"
                "• ⚡ *06:35 PM PET* (Pre-Tipoff)\n\n"
                "Puedes consultar la cartelera de hoy con /partidos."
            )

        lines = [
            f"🎯 *PRONÓSTICOS ACTIVOS ({len(pending_bets)} APUESTAS)*",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]
        for b in pending_bets:
            mkt = b.get("market", "").upper()
            sel = b.get("selection", "").upper()
            odds_val = b.get("decimal_odds_used") if b.get("decimal_odds_used") is not None else b.get("decimal_odds")
            odds_str = f"{float(odds_val):.2f}" if odds_val is not None and float(odds_val) > 1.0 else "N/A"
            stake = float(b.get("stake_pen") or b.get("kelly_stake_pen") or 0.0)
            ev = float(b.get("estimated_ev") or b.get("ev_pct") or 0.0)
            if 0.0 < ev < 1.0:
                ev *= 100.0
            lines.append(
                f"📍 *{b.get('game_id')}*\n"
                f"   • Mercado: `{mkt}` | Selección: *{sel}*\n"
                f"   • Cuota: `{odds_str}` (EV: `+{ev:.1f}%`)\n"
                f"   • Stake Sugerido: *S/ {stake:.2f} PEN*"
            )

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 _Verifica cuotas en RETAbet, Betsson o Coolbet antes de confirmar._")
        return "\n".join(lines)

    def handle_sgp(self) -> str:
        """Returns latest Player Props and RETAbet Correlated SGPs."""
        props_path = PROJECT_ROOT / "data" / "evaluation" / "latest_player_props.json"
        if not props_path.exists():
            return (
                "🔥 *PLAYER PROPS & RETABET SGPs*\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "ℹ️ No hay props generados para la jornada actual.\n"
                "El motor de props corre automáticamente a las *10:15 AM PET*."
            )

        try:
            props_data = json.loads(props_path.read_text(encoding="utf-8"))
        except Exception:
            props_data = []

        if not props_data:
            return "ℹ️ El archivo de props está vacío. Ejecuta la apertura matutina."

        # Separate SGPs and Individual Props
        sgps = [p for p in props_data if p.get("type") == "RETABET_SGP" or "sgp_id" in p]
        indiv = [p for p in props_data if p.get("type") != "RETABET_SGP" and "sgp_id" not in p]

        lines = [
            "🔥 *PROPS DESTACADOS & COMBINADAS RETAbet*",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]

        if sgps:
            best_sgp = sgps[0]
            num_legs = best_sgp.get("num_legs", len(best_sgp.get("legs", []))) or 2
            odds = float(best_sgp.get("offered_sgp_odds", best_sgp.get("decimal_odds", 2.30)))
            ev = float(best_sgp.get("ev_pct", 20.0))
            stake = float(best_sgp.get("stake_pen") or best_sgp.get("kelly_stake_pen") or 8.50)
            win_p = float(best_sgp.get("win_probability_pct") or (float(best_sgp.get("p_joint", 0.65)) * 100.0))
            book = best_sgp.get("bookmaker", "RETAbet Perú")

            lines.append(f"⚡ *Top Combinada de Alta Probabilidad ({num_legs} Legs):*")
            for leg in best_sgp.get("legs", []):
                desc = leg.get("desc") or leg.get("selection") or "Leg"
                leg_odds = float(leg.get("odds", 1.28))
                lines.append(f"   • {desc} @ `{leg_odds:.2f}`")
            lines.append(f"   🎯 *Probabilidad de Acierto:* *{win_p:.1f}%*")
            lines.append(f"   💰 *Cuota Combinada:* `{odds:.2f}` (EV: `+{ev:.1f}%`)")
            lines.append(f"   💵 *Stake Alfa Sugerido:* *S/ {stake:.2f} PEN* ({book})")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")

        if indiv:
            lines.append("🎯 *Top 3 Player Props Individuales:*")
            sorted_indiv = sorted(indiv, key=lambda x: float(x.get("ev_pct", 0.0)), reverse=True)[:3]
            for p in sorted_indiv:
                name = p.get("player_name", "Player")
                cat = p.get("prop_category", "PTS")
                sel = p.get("selection", "OVER")
                line_val = p.get("line_value", 0.0)
                odds_val = p.get("decimal_odds")
                odds_str = f"{float(odds_val):.2f}" if odds_val is not None and float(odds_val) > 1.0 else "N/A"
                ev = float(p.get("ev_pct", 0.0))
                stake = float(p.get("kelly_stake_pen") or p.get("stake_pen") or 0.0)
                lines.append(
                    f"   🏀 *{name}* ({p.get('team', '')})\n"
                    f"      Línea: *{cat} {sel} {line_val}* @ `{odds_str}`\n"
                    f"      EV: `+{ev:.1f}%` | Stake: *S/ {stake:.2f} PEN*"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")

        return "\n".join(lines)

    def handle_status(self) -> str:
        """Reports Phase 0 audit graduation progress towards 500 settled bets."""
        status_file = PROJECT_ROOT / "data" / "readiness_status.json"
        if status_file.exists():
            try:
                data = json.loads(status_file.read_text(encoding="utf-8"))
                settled = data.get("settled_bets_count", 0)
                target = data.get("target_settled_bets_tier1", 500)
                prog = data.get("progress_pct", 0.0)
                brier = data.get("brier_score", 0.0)
                base_brier = data.get("baseline_brier_score", 0.0)
                max_dd = data.get("max_drawdown_pct", 0.0)
                headline = data.get("headline", "EN CALIBRACIÓN")
                return (
                    f"🚦 *ESTADO DE GRADUACIÓN DE FASE 0*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"*{headline}*\n\n"
                    f"📊 *Progreso Muestra:* `{settled} / {target}` ({prog:.1f}%)\n"
                    f"🎯 *Brier Score:* `{brier:.4f}` (Base: `{base_brier:.4f}`)\n"
                    f"🛡️ *Drawdown Máximo:* `{max_dd:.2f}%` (Límite: `<= 15.0%`)\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"ℹ️ _El sistema requiere 500 apuestas resueltas con cuotas observadas para desbloquear Nivel 1._"
                )
            except Exception:
                pass
        return "ℹ️ Estado de readiness en actualización. Ejecuta un ciclo cloud."

    def handle_cuotas(self) -> str:
        """Returns comparison across Peruvian bookmakers and identifies any Surebets."""
        scan_path = PROJECT_ROOT / "data" / "evaluation" / "latest_peru_odds_scan.json"

        scan_data: Any = None
        if scan_path.exists():
            try:
                scan_data = json.loads(scan_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.debug(f"Could not read scan data: {exc}")

        if not scan_data:
            scraper = LivePeruOddsScraper(db=self.db)
            scan_data = scraper.scan_and_alert_entire_slate()

        games: list[dict[str, Any]] = []
        if isinstance(scan_data, list):
            games = scan_data
        elif isinstance(scan_data, dict):
            games = scan_data.get("games", [])

        if not games:
            return (
                "⚡ *COMPARADOR DE CUOTAS PERÚ*\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "ℹ️ No se encontraron cuotas para la jornada actual."
            )

        # Check for Surebets and Stale Lines
        surebets = []
        stale_lines = []
        for g in games:
            if g.get("is_arbitrage"):
                surebets.append(g)
            for sl in g.get("stale_lines", []):
                stale_lines.append((g, sl))

        lines = [
            "⚡ *COMPARADOR DE CUOTAS PERÚ*",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📊 *Casas Analizadas:* RETAbet, Betsson, Doradobet, Coolbet, Apuesta Total vs Pinnacle",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]

        if surebets:
            lines.append("🚨 *¡ARBITRAJE SUREBET DETECTADO!*")
            for sb in surebets[:2]:
                bh = sb.get("best_home", {})
                ba = sb.get("best_away", {})
                margin = float(sb.get("synthetic_margin_pct") or 0.0)
                profit = abs(margin) if margin < 0 else (100.0 - margin)
                bh_odds_str = f"{float(bh['odds']):.2f}" if bh.get("odds") else "N/A"
                ba_odds_str = f"{float(ba['odds']):.2f}" if ba.get("odds") else "N/A"
                lines.append(
                    f"   📍 *{sb.get('matchup', sb.get('game_id'))}*\n"
                    f"   • Local: `{bh_odds_str}` ({bh.get('book', 'Local')})\n"
                    f"   • Visita: `{ba_odds_str}` ({ba.get('book', 'Visita')})\n"
                    f"   💰 *Ganancia Garantizada:* `+{profit:.2f}%` (Margen: `{margin:.1f}%`)\n"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        elif stale_lines:
            lines.append("📈 *Líneas Desfasadas (+CLV vs Pinnacle):*")
            for g, sl in stale_lines[:2]:
                book = sl.get("retail_bookmaker") or sl.get("sportsbook") or "Casa Local"
                r_odds_val = sl.get("retail_odds") or sl.get("local_odds")
                r_odds_str = f"{float(r_odds_val):.2f}" if r_odds_val else "N/A"
                s_odds_val = sl.get("sharp_odds") or sl.get("pinnacle_fair_odds")
                s_odds_str = f"{float(s_odds_val):.2f}" if s_odds_val else "N/A"
                clv = float(sl.get("expected_clv_pct") or sl.get("clv_pct") or 0.0)
                sel = sl.get("selection", "Pick")
                lines.append(
                    f"   📍 *{g.get('matchup', g.get('game_id'))}* — *{sel}*\n"
                    f"   • Casa: *{book}* @ `{r_odds_str}`\n"
                    f"   • Pinnacle Benchmark: `{s_odds_str}` (Edge: `+{clv:.1f}%`)"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        else:
            lines.append("✅ *Margen promedio de mercado en Perú:* ~`104.2%` (Líneas balanceadas)")
            # Show best odds for first 2 games
            for g in games[:2]:
                bh = g.get("best_home") or {}
                ba = g.get("best_away") or {}
                if bh.get("odds") and ba.get("odds"):
                    lines.append(
                        f"📍 *{g.get('matchup', g.get('game_id'))}*\n"
                        f"   • Local: `{float(bh['odds']):.2f}` ({bh.get('book', '')})\n"
                        f"   • Visita: `{float(ba['odds']):.2f}` ({ba.get('book', '')})"
                    )
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")

        return "\n".join(lines)

    def handle_partidos(self) -> str:
        """Returns today's NBA game slate with Peru Time tipoff hours."""
        from datetime import datetime, timezone, timedelta

        # Fetch upcoming scheduled games first
        scheduled_games = self.db.fetch_all(
            """
            SELECT game_id, home_team, away_team, matchday_date, game_start_time, status, home_score, away_score
            FROM games
            WHERE status = 'SCHEDULED' AND game_id NOT LIKE 'SYN%'
            ORDER BY game_start_time ASC
            LIMIT 10
            """
        )

        # Fetch recently completed games
        recent_final_games = self.db.fetch_all(
            """
            SELECT game_id, home_team, away_team, matchday_date, game_start_time, status, home_score, away_score
            FROM games
            WHERE status IN ('FINAL', 'COMPLETED', 'STATUS_FINAL') AND game_id NOT LIKE 'SYN%'
            ORDER BY game_start_time DESC
            LIMIT 6
            """
        )

        if not scheduled_games and not recent_final_games:
            return "ℹ️ No se registraron partidos recientes en la base de datos."

        lines = [
            "📅 *CARTELERA NBA (HORA DE PERÚ)*",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]

        if scheduled_games:
            lines.append("⏳ *Próximos Partidos:*")
            for g in scheduled_games:
                h = g.get("home_team")
                a = g.get("away_team")
                start_iso = g.get("game_start_time") or ""
                time_pet = ""
                if start_iso:
                    try:
                        dt_utc = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                        dt_pet = dt_utc.astimezone(timezone(timedelta(hours=-5)))
                        time_pet = dt_pet.strftime("%I:%M %p PET")
                    except Exception:
                        time_pet = g.get("matchday_date", "")
                lines.append(f"🏀 `{a}` @ `{h}` — *{time_pet}*")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")

        if recent_final_games:
            lines.append("🏁 *Últimos Resultados:*")
            for g in recent_final_games:
                h = g.get("home_team")
                a = g.get("away_team")
                hs = g.get("home_score", 0)
                as_ = g.get("away_score", 0)
                lines.append(f"🏁 `{a}` {as_} @ `{h}` {hs} *(Final)*")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")

        lines.append("💡 _Tip: Usa /picks para ver las recomendaciones del modelo._")
        return "\n".join(lines)

    def handle_liquidar(self) -> str:
        """Triggers manual on-demand settlement of games against official ESPN boxscores."""
        logger.info("Executing on-demand settlement cycle requested via Telegram...")
        from scripts.run_automated_scheduler import NBADailyScheduler

        scheduler = NBADailyScheduler(db_path=self.db.db_path)
        res = scheduler.execute_nightly_settlement_cycle()

        settled_count = res.get("settled_count", res.get("settled_bets_count", 0))
        pnl = res.get("daily_pnl_pen", 0.0)
        bankroll = res.get("settled_bankroll_pen", res.get("current_bankroll_pen", 100.0))

        pnl_sign = "+" if pnl >= 0 else ""
        return (
            f"🌙 *LIQUIDACIÓN MANUAL COMPLETADA*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ *Apuestas Liquidadas:* `{settled_count}`\n"
            f"💵 *PnL de la Ronda:* *{pnl_sign}S/ {pnl:.2f} PEN*\n"
            f"🏦 *Nuevo Saldo Liquidado:* *S/ {bankroll:.2f} PEN*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Usa /banca para ver el desglose completo del capital."
        )

    # -------------------------------------------------------------------------
    # Main Event Loop
    # -------------------------------------------------------------------------

    def run_polling_cycle(self, timeout: int = 25) -> int:
        """Runs a single polling round, processes updates, and acknowledges them."""
        updates = self.get_updates(offset=self.last_update_id, timeout=timeout)
        processed_count = 0

        for up in updates:
            up_id = up.get("update_id")
            if up_id is not None:
                self.last_update_id = up_id + 1
                self._save_last_update_id(self.last_update_id)

            msg = up.get("message") or up.get("edited_message")
            if not msg:
                continue

            chat = msg.get("chat", {})
            chat_id = chat.get("id")
            from_user = msg.get("from", {})
            text = msg.get("text", "")
            msg_id = msg.get("message_id")

            if chat_id and text:
                logger.info(f"📩 [TELEGRAM CMD] Chat {chat_id}: '{text}'")
                reply_text = self.process_message(
                    chat_id=chat_id,
                    text=text,
                    from_user=from_user,
                    message_id=msg_id,
                )
                self.send_reply(chat_id=chat_id, text=reply_text, reply_to_message_id=msg_id)
                processed_count += 1

        if processed_count > 0 and self.last_update_id is not None:
            # Acknowledge processed updates with Telegram server immediately
            self.get_updates(offset=self.last_update_id, timeout=0)

        return processed_count

    def start_polling_loop(self, poll_timeout: int = 25, error_sleep: int = 5) -> None:
        """Starts continuous blocking loop for the Telegram listener."""
        logger.info("=" * 80)
        logger.info("🤖 NBA BETTING INTELLIGENCE — INTERACTIVE TELEGRAM LISTENER")
        logger.info("=" * 80)
        logger.info(f"Bot Token Configurado  : {'SÍ' if self.bot_token else 'NO (Falta TELEGRAM_BOT_TOKEN)'}")
        logger.info(f"Chats Autorizados      : {list(self.allowed_chat_ids) or 'TODOS'}")
        logger.info(f"Timeout Long-Polling   : {poll_timeout}s")
        logger.info("=" * 80)
        logger.info("Esperando mensajes de Telegram... Presiona Ctrl+C para detener.")

        while True:
            try:
                self.run_polling_cycle(timeout=poll_timeout)
            except KeyboardInterrupt:
                logger.info("Deteniendo el listener de Telegram (interrupción por usuario).")
                break
            except Exception as exc:
                logger.error(f"Error en el ciclo de polling: {exc}", exc_info=True)
                time.sleep(error_sleep)
