"""
Modo Híbrido Asistido: Cosecha Local de Cuotas de Casas Peruanas (`scripts/harvest_local_peru_odds.py`).

Diseñado para ejecutarse localmente desde tu computadora en Perú (con IP residencial local),
superando los bloqueos geográficos y de Cloudflare que afectan a los servidores en la nube.

Capacidades:
1. Navegación automatizada con Playwright (modo headless o visible con `--headed`).
2. Interceptación de cuotas oficiales de RETAbet Perú y Betano Perú.
3. Emparejamiento automático con los partidos programados en `data/nba_intelligence.sqlite3`.
4. Registro de cuotas con procedencia estricta: `source_type='OBSERVED'`.
5. Escaneo instantáneo de valor (+EV) y arbitraje en Soles.

Uso:
  uv run python scripts/harvest_local_peru_odds.py                     # Modo automático silencioso
  uv run python scripts/harvest_local_peru_odds.py --headed           # Abre el navegador visible
  uv run python scripts/harvest_local_peru_odds.py --site retabet     # Solo RETAbet
  uv run python scripts/harvest_local_peru_odds.py --site betano      # Solo Betano
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.playwright_scraper import PeruPlaywrightScraper
from src.storage.db import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HarvestLocalPeruOdds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cosecha Local Asistida de Cuotas Peruanas (NBA)")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Ejecuta Chromium de forma visible para casas con Playwright",
    )
    parser.add_argument(
        "--include-playwright",
        action="store_true",
        help="Incluye RETAbet/Betano vía Playwright además de Te Apuesto/Pinnacle",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30000,
        help="Tiempo de espera máximo en milisegundos por casa (default: 30000)",
    )
    parser.add_argument(
        "--site",
        choices=["all", "teapuesto", "pinnacle", "retabet", "betano"],
        default="all",
        help="Casas a escanear: all, teapuesto, pinnacle, retabet, betano (default: all)",
    )
    parser.add_argument(
        "--db",
        default=str(PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"),
        help="Ruta a la base de datos SQLite",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extrae y muestra cuotas reales sin modificar la base de datos",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        logger.error("Base de datos no encontrada en %s", db_path)
        sys.exit(1)

    db = DatabaseManager(db_path)
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    print("\n" + "=" * 78)
    print("🇵🇪 COSECHA DE CUOTAS PERUANAS & BENCHMARK SHARP (NBA)")
    print(f"⏰ Hora UTC: {now_str} | Dry-Run: {'SÍ' if args.dry_run else 'NO'}")
    print("=" * 78)

    # 1. Obtener partidos programados para hoy / próximas jornadas
    scheduled_games = db.fetch_all(
        """
        SELECT game_id, matchday_date, home_team, away_team, game_start_time
        FROM games
        WHERE status = 'SCHEDULED' AND game_id NOT LIKE 'SYN%'
        ORDER BY game_start_time ASC
        LIMIT 20
        """
    )

    if not scheduled_games:
        print("ℹ️ No hay partidos en estado 'SCHEDULED' en la base de datos.")
        print("💡 Ejecuta primero: uv run python scripts/run_cloud_cycle.py --mode pregame")
        return

    print(f"\n📋 Cartelera Activa: {len(scheduled_games)} partidos programados:")
    for g in scheduled_games[:6]:
        print(f"  • {g['matchday_date']} | {g['away_team']} @ {g['home_team']} (ID: {g['game_id']})")
    if len(scheduled_games) > 6:
        print(f"  ... y {len(scheduled_games) - 6} partidos más.")

    # 2. Inicializar scraper
    headless_mode = not args.headed
    scraper = PeruPlaywrightScraper(db=db, timeout_ms=args.timeout, headless=headless_mode)

    all_harvested_quotes: list[dict[str, Any]] = []

    # Te Apuesto Perú (API pública directa — ML, Totales, Hándicap)
    if args.site in ("all", "teapuesto"):
        print("\n🌐 Consultando Te Apuesto Perú (NBA feed público)...")
        try:
            teapuesto_quotes = scraper.scrape_teapuesto_odds()
            print(f"  ✅ Te Apuesto Perú: {len(teapuesto_quotes)} cotizaciones reales extraídas.")
            all_harvested_quotes.extend(teapuesto_quotes)
        except Exception as exc:
            logger.warning("Fallo en Te Apuesto Perú: %s", exc)

    # Pinnacle Arcadia (Benchmark sharp público)
    if args.site in ("all", "pinnacle"):
        print("\n🌐 Consultando Pinnacle (Benchmark Sharp)...")
        try:
            pinnacle_quotes = scraper.scrape_pinnacle_odds()
            print(f"  ✅ Pinnacle: {len(pinnacle_quotes)} cotizaciones reales extraídas.")
            all_harvested_quotes.extend(pinnacle_quotes)
        except Exception as exc:
            logger.warning("Fallo en Pinnacle: %s", exc)

    # RETAbet / Betano (Playwright estándar; pueden devolver HTTP 403 WAF según IP)
    run_pw_books = args.include_playwright or args.headed or args.site in ("retabet", "betano")
    if run_pw_books and args.site in ("all", "retabet"):
        print("\n🌐 Conectando con RETAbet Perú vía Playwright...")
        try:
            retabet_quotes = scraper.scrape_retabet_odds()
            print(f"  ✅ RETAbet: {len(retabet_quotes)} cotizaciones extraídas.")
            all_harvested_quotes.extend(retabet_quotes)
        except Exception as exc:
            logger.warning("Fallo en RETAbet: %s", exc)

    if run_pw_books and args.site in ("all", "betano"):
        print("\n🌐 Conectando con Betano Perú vía Playwright...")
        try:
            betano_quotes = scraper.scrape_betano_odds()
            print(f"  ✅ Betano: {len(betano_quotes)} cotizaciones extraídas.")
            all_harvested_quotes.extend(betano_quotes)
        except Exception as exc:
            logger.warning("Fallo en Betano: %s", exc)

    # 3. Persistir en SQLite si hay cotizaciones reales (y no es --dry-run)
    if all_harvested_quotes:
        if args.dry_run:
            print(f"\n🧪 [DRY-RUN] {len(all_harvested_quotes)} cotizaciones listas (no insertadas en SQLite).")
        else:
            print(f"\n💾 Persistiendo {len(all_harvested_quotes)} cotizaciones en SQLite con procedencia OBSERVED...")
            saved_count = scraper.persist_scraped_quotes(all_harvested_quotes, scheduled_games)
            print(f"  ✨ {saved_count} cuotas emparejadas e insertadas con éxito en 'odds_snapshots'.")

        print("\n📊 Muestra de Cuotas Observadas:")
        for q in all_harvested_quotes[:12]:
            mkt_raw = q.get("market")
            mkt = "Moneyline" if mkt_raw == "moneyline" else (f"Spread {q.get('line_value')}" if mkt_raw == "spread" else f"Total {q.get('line_value')}")
            print(
                f"  • [{q.get('provider')}] {q.get('away_team')} @ {q.get('home_team')} | "
                f"{mkt} {q.get('selection')}: @{float(q.get('decimal_odds') or 0.0):.2f}"
            )
    else:
        print("\n⚠️ No se pudieron extraer cotizaciones en esta pasada.")
        print("💡 Si necesitas inspección local asistida con navegador, ejecuta:")
        print("   uv run python scripts/harvest_local_peru_odds.py --site retabet --headed")


    print("\n" + "=" * 78)
    print("✅ Proceso de Cosecha Asistida Finalizado.")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    main()
