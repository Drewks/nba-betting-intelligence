"""
CLI Runner for Peruvian Sportsbook Odds Extraction (T-6H Window) (`scripts/run_peru_odds_scraper.py`).
Executes automated pre-game odds capture across Peruvian sportsbooks (RETAbet, Coolbet, Betsson,
Apuesta Total, Doradobet, Pinnacle) targeting exactly 6 hours before tipoff.
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception as exc:
        logging.warning(f"Handled exception in run_peru_odds_scraper (line 21): {exc}")

from src.backtesting.backtester import WalkForwardBacktester
from src.ingestion.live_peru_scraper import LivePeruOddsScraper
from src.ingestion.peru_scraper import PeruLiveOddsScraper
from src.paper_trading.engine import build_production_engine
from src.reporting.reporter import export_bets_and_tracking_dashboard
from src.storage.db import DatabaseManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Peruvian Sportsbook Live & T-6H Odds Scraper")
    parser.add_argument("--window", type=float, default=6.0, help="Target hours before game tipoff (default: 6.0h)")
    parser.add_argument("--tolerance", type=float, default=2.0, help="Tolerance window in hours (default: 2.0h)")
    parser.add_argument("--force", action="store_true", help="Force capture for all upcoming games regardless of window")
    parser.add_argument("--db", default=str(PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"), help="Path to SQLite database")
    parser.add_argument("--dry-run", action="store_true", help="Read slate and live feeds without mutating SQLite or CSV/MD exports")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    db = DatabaseManager(str(db_path))
    live_scraper = LivePeruOddsScraper(db=None if args.dry_run else db)
    scraper = PeruLiveOddsScraper(
        db=db,
        target_hours_before=args.window,
        tolerance_hours=args.tolerance,
    )

    now_utc = datetime.now(timezone.utc)
    print("=" * 80)
    print(f"🇵🇪 EXTRACTOR DE CUOTAS PERÚ (LIVE API + T-6H) — {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Ventana T-6H (±{args.tolerance}h) | Forzar: {args.force} | Dry-Run: {'SÍ' if args.dry_run else 'NO'}")
    print("=" * 80)

    if args.dry_run:
        scheduled = db.fetch_all(
            "SELECT game_id, home_team, away_team, game_start_time FROM games WHERE status = 'SCHEDULED' AND game_id NOT LIKE 'SYN%' ORDER BY game_start_time ASC LIMIT 15"
        )
        live_results = [
            live_scraper.collect_slate_odds(
                game_id=g["game_id"],
                home_team=g["home_team"],
                away_team=g["away_team"],
                game_start_time=g["game_start_time"],
                as_of_utc=now_utc,
            )
            for g in scheduled
        ]
    else:
        live_results = live_scraper.scan_and_alert_entire_slate(notify_telegram=False, force_all=args.force)

    live_count = sum(int(r.get("observed_quotes_count") or 0) for r in live_results)
    print(f"📡 Cotizaciones reales observadas en vivo (Te Apuesto / Betano / Pinnacle): {live_count} registros en {len(live_results)} partidos.")
    for key, info in live_scraper.get_source_diagnostics().items():
        print(f"   • {key}: {info['status']} ({info.get('events_count', 0)} eventos)")

    snapshots = scraper.scan_and_capture_slate_t6h(as_of_utc=now_utc, force_all=args.force)

    if not snapshots:
        print("ℹ️ No hay partidos en la ventana exacta T-6H en este instante.")
        print("   Ejecuta con --force para capturar cuotas de toda la cartelera próxima.")
    else:
        print(f"ℹ️ Comparativa ESTIMADA T-6H (complementaria) para {len(snapshots)} partidos con benchmark Pinnacle observado:\n")
        for s in snapshots:
            print(f"🏀 Partido: {s.matchup}")
            print(f"   Hora inicio: {s.game_start_time} | Faltan: {s.hours_to_tipoff:.1f} horas para el tipoff")
            print(f"   Hora de captura: {s.hora_captura_peru}")
            q = s.sportsbook_quotes
            retabet_q = q.get("retabet_pe", {})
            betano_q = q.get("betano_pe", {})
            betsson_q = q.get("betsson_pe", {})
            teapuesto_q = q.get("te_apuesto", {})
            pinnacle_q = q.get("pinnacle_pe", {})  # benchmark observado (copiado), el resto son estimaciones
            print(f"   🔴 RETAbet Perú:   Local {retabet_q.get('home_odds', '—')} | Visita {retabet_q.get('away_odds', '—')}")
            print(f"   🟠 Betano Perú:    Local {betano_q.get('home_odds', '—')} | Visita {betano_q.get('away_odds', '—')}")
            print(f"   🟠 Betsson Perú:   Local {betsson_q.get('home_odds', '—')} | Visita {betsson_q.get('away_odds', '—')}")
            print(f"   🟡 Te Apuesto:     Local {teapuesto_q.get('home_odds', '—')} | Visita {teapuesto_q.get('away_odds', '—')}")
            print(f"   🟢 Pinnacle Sharp: Local {pinnacle_q.get('home_odds', '—')} | Visita {pinnacle_q.get('away_odds', '—')}")
            print(f"   🏆 MEJOR EN PERÚ:  Local: {s.best_home['odds']} ({s.best_home['book']}) | Visita: {s.best_away['odds']} ({s.best_away['book']})")
            print("-" * 80)

    if not args.dry_run:
        from src.config import load_config

        # Regenerate tracking dashboard with metrics COMPUTED from the database (never hardcoded),
        # strictly isolated to the configured active model version.
        metrics = WalkForwardBacktester(db, build_production_engine(db)).compute_comprehensive_metrics(
            model_comparison_records=[],
            model_version_id=load_config().model.version_id,
        )
        export_bets_and_tracking_dashboard(
            db=db,
            metrics=metrics,
            csv_output_path=PROJECT_ROOT / "data" / "apuestas_historial.csv",
            md_output_path=PROJECT_ROOT / "SEGUIMIENTO_APUESTAS.md",
        )
        print("🚀 Dashboard regenerado con métricas calculadas desde la base de datos.")


if __name__ == "__main__":
    main()
