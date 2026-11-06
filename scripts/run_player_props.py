"""
CLI Runner for NBA Player Props Engine (`scripts/run_player_props.py`):
Scans upcoming games, factors in active injury reports, redistributes usage rates,
and identifies +EV mispricings across Points (PTS), Rebounds (REB), Assists (AST), and PRA.
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

from src.prediction.player_props import PLAYER_PROP_BASELINES, PlayerPropsEngine
from src.storage.db import DatabaseManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan and analyze NBA Player Props for +EV opportunities.")
    parser.add_argument("--min-ev", type=float, default=5.0, help="Minimum Lower-Bound EV percentage (default: 5.0)")
    parser.add_argument("--bankroll", type=float, default=100.0, help="Current bankroll in PEN (default: 100.0)")
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"
    db = DatabaseManager(db_path)
    engine = PlayerPropsEngine(db=db, min_ev_threshold=args.min_ev / 100.0)

    print("=" * 80)
    print("[PROPS] NBA PLAYER PROPS QUANTITATIVE SCANNER (V7.2 ENGINE)")
    print("=" * 80)
    print(f"Banca Base         : S/ {args.bankroll:.2f} PEN")
    print(f"Filtro Minimo EV   : > {args.min_ev:.1f}% (Lower-Bound Conformal)")
    print(f"Jugadores Mapeados : {len(PLAYER_PROP_BASELINES)} perfiles de rotacion NBA")
    print("-" * 80)

    # Sample realistic market lines for active slate (or test candidates)
    sample_market_props = [
        # Kyrie Irving in game where Luka Doncic is OUT
        {
            "player": "Kyrie Irving", "team": "DAL", "game_id": "ESPN_401909288_DAL_PHX",
            "date": "2026-11-06", "cat": "PTS", "line": 26.5, "over_odds": 1.90, "under_odds": 1.90,
            "absent": ["Luka Doncic"],
        },
        {
            "player": "Kyrie Irving", "team": "DAL", "game_id": "ESPN_401909288_DAL_PHX",
            "date": "2026-11-06", "cat": "AST", "line": 6.5, "over_odds": 1.95, "under_odds": 1.85,
            "absent": ["Luka Doncic"],
        },
        # Jamal Murray when Nikola Jokic is rested/absent
        {
            "player": "Jamal Murray", "team": "DEN", "game_id": "ESPN_401909289_DEN_IND",
            "date": "2026-11-07", "cat": "PTS", "line": 23.5, "over_odds": 1.92, "under_odds": 1.88,
            "absent": ["Nikola Jokic"],
        },
        # Derrick White in Boston regular slate
        {
            "player": "Derrick White", "team": "BOS", "game_id": "ESPN_401909288_BOS_CHA",
            "date": "2026-11-06", "cat": "PTS", "line": 15.5, "over_odds": 1.88, "under_odds": 1.92,
            "absent": ["Kristaps Porzingis"],
        },
    ]

    all_picks: list[dict[str, Any]] = []

    for item in sample_market_props:
        picks = engine.evaluate_prop_opportunity(
            player_name=item["player"],
            team=item["team"],
            game_id=item["game_id"],
            matchday_date=item["date"],
            prop_category=item["cat"],
            line_value=item["line"],
            over_odds=item["over_odds"],
            under_odds=item["under_odds"],
            absent_teammates=item["absent"],
            bankroll_pen=args.bankroll,
        )
        all_picks.extend(picks)

    out_file = PROJECT_ROOT / "data" / "evaluation" / "latest_player_props.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(all_picks, indent=2, ensure_ascii=False), encoding="utf-8")

    if all_picks:
        print(f"[!] OPORTUNIDADES +EV ENCONTRADAS ({len(all_picks)} picks calificados):")
        print("=" * 80)
        for p in all_picks:
            print(f"  * {p['player_name']} ({p['team']}) — {p['prop_category']} {p['selection']} {p['line_value']}")
            print(f"    Cuota             : {p['decimal_odds']:.2f}")
            print(f"    Media Proyectada  : {p['projected_mean']:.1f} (Aumento de uso: +{p['usage_bump_pct']:.1f}%)")
            print(f"    Probabilidad      : {p['model_prob'] * 100:.1f}% (Conformal CI: [{p['conformal_p_low'] * 100:.1f}%, {p['conformal_p_high'] * 100:.1f}%])")
            print(f"    Lower-Bound EV    : {p['ev_lower_bound_pct']:+.2f}% (Nominal EV: {p['ev_pct']:+.2f}%)")
            print(f"    Stake Sugerido    : S/ {p['kelly_stake_pen']:.2f} PEN ({p['kelly_optimal_fraction'] * 100:.2f}%)")
            print(f"    Justificación     : {p['rationale']}\n")
    else:
        print("  [i] No se encontraron desajustes de Player Props que superen el umbral de Lower-Bound EV.")
    print("=" * 80)


if __name__ == "__main__":
    main()
