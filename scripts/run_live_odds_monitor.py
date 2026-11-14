"""
CLI Runner for Real-Time Peruvian Odds Monitoring & Stale Line Arbitrage (`scripts/run_live_odds_monitor.py`).
Executes continuous or on-demand scraping across Peruvian sportsbooks (RETAbet, Betsson, Doradobet, Coolbet, Apuesta Total, Pinnacle)
and dispatches instant Telegram alerts for high-CLV latency lags and risk-free Surebets.
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

from src.ingestion.live_peru_scraper import LivePeruOddsScraper
from src.storage.db import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("PeruOddsCLI")


def print_comparison_table(results: list[dict]) -> None:
    """Prints a structured ASCII odds comparison table across Peruvian sportsbooks."""
    print("=" * 100)
    print("🇵🇪 MONITOR EN TIEMPO REAL — CUOTAS DE CASAS DE APUESTAS PERUANAS & COMPARADOR")
    print("=" * 100)

    if not results:
        print("[i] No se encontraron partidos activos programados en este instante.")
        print("    Ejecuta con --force para auditar partidos próximos de la cartelera.")
        print("=" * 100)
        return

    for res in results:
        print(f"\n🏀 PARTIDO: {res['matchup']} (ID: {res['game_id']})")
        print(f"   Tipoff: {res['game_start_time']} | Captura: {res['hora_captura_peru']}")
        best_h = res.get("best_home")
        best_a = res.get("best_away")
        if best_h and best_a:
            print(
                f"   🏆 MEJOR CUOTA OBSERVADA: Local: {best_h['odds']:.2f} ({best_h['book']}) | "
                f"Visita: {best_a['odds']:.2f} ({best_a['book']})"
            )
            print(f"   📊 Margen Sintético Combinado: {res['synthetic_margin_pct']:+.2f}% | Props Jugadores: {res.get('player_props_count', 0)}")
        else:
            print(f"   ℹ️ Cotización parcial (se requieren >=2 casas observadas para mejor cuota cruzada) | Props Jugadores: {res.get('player_props_count', 0)}")
        print("   " + "-" * 94)
        print("   {:<22} | {:<11} | {:<11} | {:<16} | {:<24}".format("Casa de Apuestas", "Cuota Local", "Cuota Visita", "Total O/U", "Fuente"))
        print("   " + "-" * 94)

        for _bid, q in res.get("quotes", {}).items():
            t_line = q.get("total_points_line")
            t_str = f"{t_line:.1f}" if isinstance(t_line, (int, float)) else "—"
            h_val = float(q.get("home_odds") or 0.0)
            a_val = float(q.get("away_odds") or 0.0)
            print(
                "   {:<22} | {:<11} | {:<11} | {:<16} | {:<24}".format(
                    str(q.get("book_name") or _bid)[:22],
                    f"{h_val:.2f}" if h_val > 1.0 else "—",
                    f"{a_val:.2f}" if a_val > 1.0 else "—",
                    t_str,
                    str(q.get("source") or "")[:24],
                )
            )
        print("   " + "-" * 94)

        # Print stale lines if detected
        stale = res.get("stale_lines", [])
        if stale:
            print("   🚨 LÍNEAS DESFASADAS DETECTADAS (+CLV):")
            for st in stale:
                print(f"      • {st['retail_bookmaker']}: Cuota {st['retail_odds']:.2f} vs Sharp {st['sharp_odds']:.2f} (CLV: +{st['expected_clv_pct']}%) -> Stake Sugerido: S/ {st['kelly_stake_pen']:.2f} PEN")

        # Print surebet if detected
        sb = res.get("surebet")
        if sb and sb.get("is_arbitrage"):
            print("   💰 ARBITRAJE LIBRE DE RIESGO (SUREBET):")
            print(f"      • {sb['book_a']} ({sb['odds_a']:.2f}) [S/ {sb['stake_a_pen']:.2f}] + {sb['book_b']} ({sb['odds_b']:.2f}) [S/ {sb['stake_b_pen']:.2f}]")
            print(f"      • Inversión: S/ {sb['total_staked_pen']:.2f} PEN | Ganancia Segura: +S/ {sb['guaranteed_net_profit_pen']:.2f} PEN (Margen: {sb['arb_margin_pct']}%)")

    print("\n" + "=" * 100)


def _print_source_diagnostics(scraper: LivePeruOddsScraper) -> None:
    diag = scraper.get_source_diagnostics()
    if not diag:
        return
    print("📡 ESTADO DE FUENTES PERUANAS & SHARP:")
    for key, info in diag.items():
        print(f"   • {key:<14}: {info['status']} ({info.get('events_count', 0)} eventos) {info.get('detail', '')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Live Peruvian Sportsbook Scraper and Arbitrage Monitor.")
    parser.add_argument("--once", action="store_true", help="Execute a single scan and exit")
    parser.add_argument("--poll-seconds", type=int, default=60, help="Polling interval in seconds for continuous mode (default: 60s)")
    parser.add_argument("--min-clv", type=float, default=4.0, help="Minimum CLV percentage for stale line alerts (default: 4.0%)")
    parser.add_argument("--force", action="store_true", help="Force scan across all upcoming scheduled games")
    parser.add_argument("--bankroll", type=float, default=100.0, help="Bankroll in PEN for sizing (default: 100.0)")
    parser.add_argument("--no-telegram", action="store_true", help="Disable Telegram alerts during scan")
    parser.add_argument("--db", default=str(PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"), help="Path to SQLite database")
    args = parser.parse_args()

    db_path = Path(args.db)
    db = DatabaseManager(db_path) if db_path.exists() else None

    scraper = LivePeruOddsScraper(
        db=db,
        min_clv_pct=args.min_clv,
        bankroll_pen=args.bankroll,
    )

    notify = not args.no_telegram

    if args.once:
        print("[*] Iniciando escaneo en vivo de casas de apuestas peruanas...")
        results = scraper.scan_and_alert_entire_slate(notify_telegram=notify, force_all=args.force)
        print_comparison_table(results)
        _print_source_diagnostics(scraper)
    else:
        print("=" * 80)
        print(f"🔄 INICIANDO MONITOR CONTINUO DE CUOTAS PERUANAS (Intervalo: {args.poll_seconds}s)")
        print(f"Canal de Alertas Telegram: {'ACTIVADO' if notify and scraper.bot.is_live else 'DESACTIVADO / DRY-RUN'}")
        print(f"Filtro Mínimo de CLV     : >= {args.min_clv:.1f}%")
        print("Presiona Ctrl+C para detener el monitor.")
        print("=" * 80)

        while True:
            try:
                results = scraper.scan_and_alert_entire_slate(notify_telegram=notify, force_all=args.force)
                print_comparison_table(results)
                time.sleep(args.poll_seconds)
            except KeyboardInterrupt:
                print("\n[!] Monitor detenido por el usuario.")
                break
            except Exception as exc:
                logger.error(f"Error en el ciclo de monitoreo: {exc}", exc_info=True)
                time.sleep(15)


if __name__ == "__main__":
    main()
