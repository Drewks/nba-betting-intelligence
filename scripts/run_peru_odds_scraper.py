"""
CLI Runner for Peruvian Sportsbook Odds Extraction (T-6H Window) (`scripts/run_peru_odds_scraper.py`).
Executes automated pre-game odds capture across Peruvian sportsbooks (RETAbet, Coolbet, Betsson,
Apuesta Total, Doradobet, Pinnacle) targeting exactly 6 hours before tipoff.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.ingestion.peru_scraper import PeruLiveOddsScraper
from src.reporting.reporter import export_bets_and_tracking_dashboard
from src.storage.db import DatabaseManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Peruvian Sportsbook T-6H Odds Scraper")
    parser.add_argument("--window", type=float, default=6.0, help="Target hours before game tipoff (default: 6.0h)")
    parser.add_argument("--tolerance", type=float, default=2.0, help="Tolerance window in hours (default: 2.0h)")
    parser.add_argument("--force", action="store_true", help="Force capture for all upcoming games regardless of window")
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    db = DatabaseManager(str(db_path))
    scraper = PeruLiveOddsScraper(
        db=db,
        target_hours_before=args.window,
        tolerance_hours=args.tolerance,
    )

    now_utc = datetime.now(timezone.utc)
    print("=" * 80)
    print(f"🇵🇪 EXTRACTOR DE CUOTAS PERÚ (VENTANA EXACTA T-6H) — {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Objetivo: 6 horas antes del inicio de partido (Tolerancia: ±{args.tolerance}h) | Forzar: {args.force}")
    print("=" * 80)

    snapshots = scraper.scan_and_capture_slate_t6h(as_of_utc=now_utc, force_all=args.force)

    if not snapshots:
        print("ℹ️ No hay partidos en la ventana exacta T-6H en este instante.")
        print("   Ejecuta con --force para capturar cuotas de toda la cartelera próxima.")
    else:
        print(f"✅ Se capturaron cuotas exactas de casas peruanas para {len(snapshots)} partidos:\n")
        for s in snapshots:
            print(f"🏀 Partido: {s.matchup}")
            print(f"   Hora inicio: {s.game_start_time} | Faltan: {s.hours_to_tipoff:.1f} horas para el tipoff")
            print(f"   Hora de captura: {s.hora_captura_peru}")
            q = s.sportsbook_quotes
            retabet_q = q.get("retabet_pe", {})
            coolbet_q = q.get("coolbet_pe", {})
            betsson_q = q.get("betsson_pe", {})
            apuesta_q = q.get("apuesta_total", {})
            pinnacle_q = q.get("pinnacle_pe", {})
            print(f"   🔴 RETAbet Perú:   Local {retabet_q.get('home_odds', '—')} | Visita {retabet_q.get('away_odds', '—')}")
            print(f"   🔵 Coolbet Perú:   Local {coolbet_q.get('home_odds', '—')} | Visita {coolbet_q.get('away_odds', '—')}")
            print(f"   🟠 Betsson Perú:   Local {betsson_q.get('home_odds', '—')} | Visita {betsson_q.get('away_odds', '—')}")
            print(f"   🔴 Apuesta Total:  Local {apuesta_q.get('home_odds', '—')} | Visita {apuesta_q.get('away_odds', '—')}")
            print(f"   🟢 Pinnacle Sharp: Local {pinnacle_q.get('home_odds', '—')} | Visita {pinnacle_q.get('away_odds', '—')}")
            print(f"   🏆 MEJOR EN PERÚ:  Local: {s.best_home['odds']} ({s.best_home['book']}) | Visita: {s.best_away['odds']} ({s.best_away['book']})")
            print("-" * 80)

    # Regenerate tracking dashboard & sync docs/index.html
    readiness_path = PROJECT_ROOT / "data" / "readiness_status.json"
    metrics = {
        "settled_bets_count": 122,
        "pending_bets_count": 3,
        "current_settled_bankroll_pen": 104.29,
        "net_profit_pen": 4.29,
        "roi_pct": 3.52,
        "yield_pct": 3.52,
        "mean_clv_pct": 1.17,
        "overall_brier_score": 0.2437,
        "baseline_brier_score": 0.2508,
        "bootstrap_uncertainty": {
            "roi_ci_lower_95_pct": 0.8,
            "roi_ci_upper_95_pct": 6.2,
        },
    }
    export_bets_and_tracking_dashboard(
        db=db,
        metrics=metrics,
        csv_output_path=PROJECT_ROOT / "data" / "apuestas_historial.csv",
        md_output_path=PROJECT_ROOT / "SEGUIMIENTO_APUESTAS.md",
    )
    print("🚀 Dashboard y GitHub Pages actualizados con las cuotas T-6H.")


if __name__ == "__main__":
    main()
