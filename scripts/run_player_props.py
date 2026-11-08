"""
CLI Runner for NBA Player Props Engine (`scripts/run_player_props.py`):
Scans upcoming games, factors in active injury reports, redistributes usage rates,
evaluates tactical defensive matchups (DvP) and game pace, and identifies +EV mispricings
across Points (PTS), Rebounds (REB), Assists (AST), 3PM, PRA, and RETAbet Perú SGP Parlays.
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.prediction.player_props import PLAYER_PROP_BASELINES, PlayerPropsEngine
from src.storage.db import DatabaseManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan and analyze NBA Player Props for +EV opportunities.")
    parser.add_argument("--min-ev", type=float, default=3.0, help="Minimum EV percentage (default: 3.0)")
    parser.add_argument("--bankroll", type=float, default=100.0, help="Current bankroll in PEN (default: 100.0)")
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"
    db = DatabaseManager(db_path)
    engine = PlayerPropsEngine(db=db, min_ev_threshold=args.min_ev / 100.0)

    print("=" * 80)
    print("🏀 NBA PLAYER PROPS & SGP QUANTITATIVE SCANNER (MOTOR V8 OFICIAL)")
    print("=" * 80)
    print(f"Banca Base         : S/ {args.bankroll:.2f} PEN")
    print(f"Filtro Minimo EV   : > {args.min_ev:.1f}%")
    print(f"Jugadores Mapeados : {len(PLAYER_PROP_BASELINES)} perfiles canónicos (30 equipos NBA)")
    print("-" * 80)

    from src.ingestion.roster_manager import sync_all_nba_rosters
    print("[*] Sincronizando plantillas oficiales de los 30 equipos NBA desde ESPN...")
    roster_map = sync_all_nba_rosters(db)
    print(f"[OK] {len(roster_map)} franquicias sincronizadas exitosamente.")

    # 1. Run dynamic slate scanner across all upcoming scheduled games
    all_picks = engine.generate_slate_prop_opportunities(
        bankroll_pen=args.bankroll,
        min_ev_pct=args.min_ev,
    )

    if not all_picks:
        print("\n[i] No hay partidos programados próximos en la pizarra activa.")
        print("[i] Se omiten props sintéticos o partidos pasados para garantizar integridad temporal total.")

    out_file = PROJECT_ROOT / "data" / "evaluation" / "latest_player_props.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(all_picks, indent=2, ensure_ascii=False), encoding="utf-8")

    indiv_picks = [p for p in all_picks if p.get("type") == "INDIVIDUAL_PROP" or "prop_id" in p]
    sgp_picks = [p for p in all_picks if p.get("type") == "RETABET_SGP" or "sgp_id" in p]

    if indiv_picks:
        print(f"\n[!] PROPS INDIVIDUALES +EV ({len(indiv_picks)} picks calificados):")
        print("=" * 80)
        for p in indiv_picks:
            m_badge = f" [vs {p.get('opponent_team') or 'NBA'} {p.get('matchup_tier', 'AVG')}]" if p.get('opponent_team') else ""
            print(f"  * {p['player_name']} ({p['team']}){m_badge} — {p['prop_category']} {p['selection']} {p['line_value']}")
            print(f"    Cuota Ofrecida    : {p['decimal_odds']:.2f} (Implícita: {((1.0/p['decimal_odds'])*100):.1f}%)")
            print(f"    Media Proyectada  : {p['projected_mean']:.1f} (Ventaja vs Línea: {p.get('line_diff', 0.0):+0.1f} pts / {p.get('line_diff_pct', 0.0):+0.1f}%)")
            print(f"    Prob. Modelo      : {p['model_prob'] * 100:.1f}% (Conformal CI: [{p['conformal_p_low'] * 100:.1f}%, {p['conformal_p_high'] * 100:.1f}%])")
            print(f"    Lower-Bound EV    : {p['ev_lower_bound_pct']:+.2f}% (Nominal EV: {p['ev_pct']:+.2f}%)")
            print(f"    Kelly Stake       : S/ {p['kelly_stake_pen']:.2f} PEN ({p['kelly_optimal_fraction'] * 100:.2f}%)")
            print(f"    Justificación     : {p['rationale']}\n")

    if sgp_picks:
        print(f"\n🇵🇪 CREA TU APUESTA — RETABET PERÚ SGP ({len(sgp_picks)} combinadas correlacionadas +EV):")
        print("=" * 80)
        for s in sgp_picks:
            print(f"  * [{s['bookmaker']}] {s['game_selection']} + {s['player_name']} {s['prop_category']} {s['prop_selection']} {s['prop_line']}")
            print(f"    Cuota RETAbet     : {s['offered_sgp_odds']:.2f} (Cuota Justa Modelo: {s['fair_sgp_odds']:.2f})")
            print(f"    Prob. Cópula      : {s['p_joint'] * 100:.1f}% (vs {s['p_independent'] * 100:.1f}% Independiente -> Boost: +{s['correlation_boost_pct']}%)")
            print(f"    Valor Esperado    : {s['ev_pct']:+.2f}% EV")
            print(f"    Kelly Stake       : S/ {s['kelly_stake_pen']:.2f} PEN")
            print(f"    Justificación     : {s['rationale']}\n")

    if not all_picks:
        print("  [i] No se encontraron desajustes de Player Props que superen el umbral de EV en este momento.")
    print("=" * 80)

    from src.paper_trading.engine import PaperTradingEngine
    pt_engine = PaperTradingEngine(db=db)
    pt_metrics = pt_engine.get_player_props_performance_metrics()
    print("\n" + "=" * 80)
    print("📈 SEGUIMIENTO AUDITADO DE PAPER TRADING (PROPS & SGP RETABET)")
    print("=" * 80)
    print(f"Banca Props Actual : S/ {pt_metrics['current_props_bankroll_pen']:.2f} PEN (P&L: {pt_metrics['total_net_profit_pen']:+.2f} PEN)")
    print(f"Tasa de Acierto    : {pt_metrics['win_rate_pct']:.1f}% ({pt_metrics['won_picks']} Ganadas / {pt_metrics['lost_picks']} Perdidas / {pt_metrics['push_picks']} Empates)")
    print(f"ROI Acumulado      : {pt_metrics['roi_pct']:+.2f}% | Total Apostado: S/ {pt_metrics['total_staked_pen']:.2f} PEN")
    print(f"Calibración Brier  : {pt_metrics['brier_score']:.4f} | Cobertura Conformal: {pt_metrics['conformal_coverage_pct']:.1f}%")
    print(f"Picks Totales      : {pt_metrics['total_picks']} ({pt_metrics['pending_picks']} en espera / {pt_metrics['settled_picks']} liquidados)")
    print("=" * 80)


if __name__ == "__main__":
    main()
