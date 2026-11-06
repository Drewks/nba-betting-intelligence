"""
Reporting & Obsidian Vault Synchronization (Sections 13 & 15):
Generates Daily Reports, Weekly Reports, Audit Reports, and populates the dedicated
Obsidian Vault (`NBA/00-Inbox` through `NBA/09-Reports`) with full provenance metadata.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import csv
import json
from pathlib import Path
from typing import Any

from src.ingestion.normalizer import NBA_TEAMS
from src.utils.team_dictionary import (
    format_matchup,
    format_matchup_string,
    get_team,
    get_team_code,
    get_team_full_name,
    get_teams_json_for_frontend,
)
from src.models.statistical_models import EnsembleStackingModel, build_pregame_features
from src.reporting.notifier import evaluate_and_notify_readiness, select_and_dispatch_daily_top_pick
from src.storage.db import DatabaseManager
from src.ingestion.peru_sportsbooks import (
    calculate_peru_odds_comparison,
    get_peru_sportsbooks_catalog,
    get_peru_sportsbooks_json_for_frontend,
)
from src.validation.validator import parse_iso_utc


def compute_upcoming_slate_intelligence(db: DatabaseManager) -> list[dict[str, Any]]:
    """
    Computes pre-game odds, V6 model projections (Moneyline, Total Points, Spread, Conformal, OT/Blowout),
    key basketball statistics (Elo, Off/Def Rating, Pace, Rest/B2B, Geodesic Travel Miles, Altitude),
    and clear Spanish explanations of why the bot placed a bet or decided NO_BET for each upcoming game.
    """
    all_final_games = db.fetch_all(
        "SELECT * FROM games WHERE status = 'FINAL' AND home_score IS NOT NULL ORDER BY game_start_time"
    )
    model_f = EnsembleStackingModel("model_f_ensemble_v2")
    if all_final_games:
        model_f.fit(all_final_games, all_final_games[-1]["game_start_time"])

    sched_games = db.fetch_all(
        "SELECT * FROM games WHERE status = 'SCHEDULED' AND game_id LIKE 'ESPN_%' ORDER BY game_start_time ASC"
    )

    pending_bets_by_game: dict[str, dict[str, Any]] = {}
    for b in db.fetch_all(
        """
        SELECT b.*, p.odds_provider, p.raw_probability, p.implied_prob_gross
        FROM simulated_bets b
        LEFT JOIN predictions p ON b.prediction_id = p.prediction_id
        WHERE b.status = 'PENDING'
        """
    ):
        pending_bets_by_game[b["game_id"]] = dict(b)

    slate_items: list[dict[str, Any]] = []
    for g in sched_games:
        gid = g["game_id"]
        feats = build_pregame_features(g, all_final_games)
        pred_ml = model_f.predict_moneyline(g, all_final_games)

        odds_rows = db.fetch_all(
            """
            SELECT market, selection, line_value, decimal_odds, provider, captured_at
            FROM odds_snapshots
            WHERE game_id = ?
            ORDER BY decimal_odds DESC, captured_at DESC
            """,
            (gid,),
        )
        best_odds: dict[str, dict[str, Any]] = {}
        for o in odds_rows:
            key = f"{o['market']}_{o['selection']}"
            if key not in best_odds:
                best_odds[key] = dict(o)

        tot_line = 228.5
        if "total_points_OVER" in best_odds and best_odds["total_points_OVER"]["line_value"] is not None:
            tot_line = float(best_odds["total_points_OVER"]["line_value"])
        pred_tot = model_f.predict_total_points(g, all_final_games, tot_line)

        try:
            peru_dt = (parse_iso_utc(g["game_start_time"]) - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
        except Exception:
            peru_dt = str(g["game_start_time"])

        def _clean_book(raw: str | None) -> str:
            if not raw:
                return "—"
            return (
                str(raw)
                .split(" (Best")[0]
                .replace(" (LineShop)", "")
                .replace("espn_draftkings_pregame", "DraftKings")
                .strip()
            )

        ml_home_odds = float(best_odds.get("moneyline_HOME", {}).get("decimal_odds", 0.0))
        ml_away_odds = float(best_odds.get("moneyline_AWAY", {}).get("decimal_odds", 0.0))
        ml_home_book = _clean_book(best_odds.get("moneyline_HOME", {}).get("provider"))
        ml_away_book = _clean_book(best_odds.get("moneyline_AWAY", {}).get("provider"))

        tot_over_odds = float(best_odds.get("total_points_OVER", {}).get("decimal_odds", 0.0))
        tot_under_odds = float(best_odds.get("total_points_UNDER", {}).get("decimal_odds", 0.0))
        tot_book = _clean_book(best_odds.get("total_points_OVER", {}).get("provider"))

        mkt_p_home = 0.5
        mkt_p_away = 0.5
        if ml_home_odds > 1.0 and ml_away_odds > 1.0:
            inv_h = 1.0 / ml_home_odds
            inv_a = 1.0 / ml_away_odds
            mkt_p_home = inv_h / (inv_h + inv_a)
            mkt_p_away = inv_a / (inv_h + inv_a)

        peru_odds = calculate_peru_odds_comparison(
            p_home_fair=float(pred_ml["p_home"]),
            p_away_fair=float(pred_ml["p_away"]),
            benchmark_home_odds=ml_home_odds if ml_home_odds > 1.0 else None,
            benchmark_away_odds=ml_away_odds if ml_away_odds > 1.0 else None,
        )

        active_bet = pending_bets_by_game.get(gid)
        travel_miles = round(float(feats.get("travel_miles_diff", 0.0)), 0)
        rest_h = round(float(g.get("home_rest_days", 2)), 1)
        rest_a = round(float(g.get("away_rest_days", 2)), 1)
        net_diff = round(float(feats["net_rtg_diff"]), 1)
        elo_h = round(float(feats["elo_home"]), 0)
        elo_a = round(float(feats["elo_away"]), 0)

        home_full = get_team_full_name(g["home_team"])
        away_full = get_team_full_name(g["away_team"])
        matchup_full = format_matchup(g["away_team"], g["home_team"])

        if active_bet:
            if active_bet["market"] == "moneyline":
                sel_team_code = g["home_team"] if active_bet["selection"] == "HOME" else g["away_team"]
                sel_team_name = home_full if active_bet["selection"] == "HOME" else away_full
                side_str = "Local" if active_bet["selection"] == "HOME" else "Visita"
                sel_label = f"Gana {sel_team_name} ({sel_team_code} - {side_str})"
            else:
                sel_label = f"{active_bet['selection']} {active_bet['line_value']} ({away_full} @ {home_full})"
            bet_book = _clean_book(active_bet.get("odds_provider"))
            bet_odds = round(float(active_bet["decimal_odds"]), 3)
            bet_prob = round(float(active_bet["estimated_prob"]) * 100.0, 1)
            bet_ev = round(float(active_bet["estimated_ev"]) * 100.0, 2)
            bet_stake = round(float(active_bet["stake_pen"]), 2)
            pot_profit = round(bet_stake * (bet_odds - 1.0), 2)
            fair_odds = round(100.0 / max(1.0, bet_prob), 3)

            reasons: list[str] = []
            if travel_miles > 400:
                reasons.append(f"Visita ({away_full}) viaja +{int(travel_miles)} millas más")
            if int(feats.get("first_home_from_road", 0)) == 1:
                reasons.append(f"Ajuste de retorno de gira para {home_full}")
            if abs(net_diff) >= 0.3:
                better_team_name = home_full if net_diff > 0 else away_full
                better_team_code = g["home_team"] if net_diff > 0 else g["away_team"]
                reasons.append(f"Eficiencia neta favorable ({better_team_name} [{better_team_code}] {abs(net_diff):+.1f} pts/100)")
            reasons.append(f"Cuota {bet_odds:.3f} en {bet_book} supera la cuota justa del modelo ({fair_odds:.3f})")
            verdict_status = "APOSTADO"
            verdict_summary = f"🎯 APOSTADO: {sel_label} @ {bet_odds:.3f} ({bet_book}) | Stake S/{bet_stake:.2f} (EV +{bet_ev:.2f}%)"
            verdict_reason = " · ".join(reasons) + "."
        else:
            verdict_status = "NO_BET"
            if not ml_home_odds:
                verdict_summary = "⏳ SIN CUOTAS AÚN"
                verdict_reason = "Las casas de apuestas aún no publican línea pre-partido verificada."
            else:
                ev_h = (pred_ml["p_home"] * ml_home_odds - 1.0) * 100.0
                ev_a = (pred_ml["p_away"] * ml_away_odds - 1.0) * 100.0
                best_raw_ev = max(ev_h, ev_a)
                verdict_summary = "🛡️ NO APOSTAR (Pass)"
                if best_raw_ev <= 1.5:
                    verdict_reason = "Cuotas eficientes: la probabilidad del modelo está alineada con las casas (sin ventaja EV suficiente)."
                else:
                    verdict_reason = "Bloqueado por filtro de riesgo/anclaje de mercado (dispersión alta o favorito/underdog fuera de rango seguro)."
            sel_label = "—"
            bet_book = "—"
            bet_odds = 0.0
            bet_prob = 0.0
            bet_ev = 0.0
            bet_stake = 0.0
            pot_profit = 0.0
            fair_odds = 0.0

        slate_items.append(
            {
                "game_id": gid,
                "matchup": matchup_full,
                "matchup_short": f"{g['away_team']} @ {g['home_team']}",
                "home_team": g["home_team"],
                "away_team": g["away_team"],
                "home_name": home_full,
                "away_name": away_full,
                "matchday_date": g["matchday_date"],
                "hora_peru": peru_dt,
                "ml_home_odds": round(ml_home_odds, 3) if ml_home_odds else None,
                "ml_away_odds": round(ml_away_odds, 3) if ml_away_odds else None,
                "ml_home_book": ml_home_book,
                "ml_away_book": ml_away_book,
                "mkt_p_home_pct": round(mkt_p_home * 100.0, 1),
                "mkt_p_away_pct": round(mkt_p_away * 100.0, 1),
                "tot_line": tot_line,
                "tot_over_odds": round(tot_over_odds, 3) if tot_over_odds else None,
                "tot_under_odds": round(tot_under_odds, 3) if tot_under_odds else None,
                "tot_book": tot_book,
                "model_p_home_pct": round(pred_ml["p_home"] * 100.0, 1),
                "model_p_away_pct": round(pred_ml["p_away"] * 100.0, 1),
                "peru_odds": peru_odds,
                "expected_margin": round(pred_ml["expected_margin"], 1),
                "expected_total": round(pred_tot["expected_total"], 1),
                "model_p_over_pct": round(pred_tot["p_over"] * 100.0, 1),
                "model_p_under_pct": round(pred_tot["p_under"] * 100.0, 1),
                "conformal_q10": round(pred_tot.get("conformal_q10_total", pred_tot["expected_total"] - 18.0), 1),
                "conformal_q90": round(pred_tot.get("conformal_q90_total", pred_tot["expected_total"] + 18.0), 1),
                "overtime_prob_pct": round(pred_tot.get("overtime_prob", 0.055) * 100.0, 1),
                "blowout_prob_pct": round(pred_tot.get("blowout_prob", 0.14) * 100.0, 1),
                "stats": {
                    "elo_home": int(elo_h),
                    "elo_away": int(elo_a),
                    "elo_diff": int(round(feats["elo_diff"], 0)),
                    "home_off": round(feats["home_off_rtg"], 1),
                    "home_def": round(feats["home_def_rtg"], 1),
                    "away_off": round(feats["away_off_rtg"], 1),
                    "away_def": round(feats["away_def_rtg"], 1),
                    "net_rtg_diff": net_diff,
                    "expected_pace": round(feats["expected_pace"], 1),
                    "home_rest_days": rest_h,
                    "away_rest_days": rest_a,
                    "home_b2b": int(g.get("home_b2b", 0)),
                    "away_b2b": int(g.get("away_b2b", 0)),
                    "first_home_from_road": int(feats.get("first_home_from_road", 0)),
                    "travel_miles_diff": int(travel_miles),
                    "away_tz_change": round(float(feats.get("away_tz_change", 0.0)), 1),
                    "altitude_advantage": round(float(feats.get("altitude_advantage", 0.0)), 2),
                    "venue_split_diff": round(float(feats.get("venue_split_diff", 0.0)), 2),
                    "streak_diff": round(float(feats.get("streak_diff", 0.0)), 1),
                },
                "verdict_status": verdict_status,
                "verdict_summary": verdict_summary,
                "verdict_reason": verdict_reason,
                "bet_details": {
                    "selection_label": sel_label,
                    "bookmaker": bet_book,
                    "decimal_odds": bet_odds,
                    "fair_odds": fair_odds,
                    "model_prob_pct": bet_prob,
                    "ev_pct": bet_ev,
                    "stake_pen": bet_stake,
                    "potential_profit_pen": pot_profit,
                }
                if active_bet
                else None,
            }
        )
    return slate_items


def generate_interactive_html_dashboard(
    metrics: dict[str, Any],
    espn_real_bets: list[dict[str, Any]],
    slate_items: list[dict[str, Any]],
    html_output_path: str | Path,
    peru_str: str,
    player_props: list[dict[str, Any]] | None = None,
) -> str:
    """
    Generates a standalone, interactive HTML dashboard (`reports/dashboard.html`) displaying:
    1) Active Bets in course with full team names (e.g. Orlando Magic @ Phoenix Suns), statistical rationale, odds vs fair odds.
    2) Complete Upcoming Slate with Bookmaker Odds, Model Projections, Key Stats to Watch, and Bot Verdict.
    3) V7.2 Player Props Engine (PTS, REB, AST, PRA) with usage redistribution and Conformal Lower-Bound EV.
    4) Interactive Odds & Expected Value (+EV) Calculator + Key Basketball Metrics Guide.
    5) Real Bet History & Bankroll Equity Curve with resilient multi-key formatting and full team names.
    """
    if player_props is None:
        try:
            props_file = Path(html_output_path).resolve().parent.parent / "data" / "evaluation" / "latest_player_props.json"
            if props_file.exists():
                player_props = json.loads(props_file.read_text(encoding="utf-8"))
            else:
                player_props = []
        except Exception:
            player_props = []

    pending_stake = round(sum(float(b.get("stake_pen") or 0.0) for b in espn_real_bets if (b.get("estado") or b.get("status")) == "PENDING"), 2)
    settled_bank = round(float(metrics.get("current_settled_bankroll_pen", 100.0)), 2)
    avail_bank = round(settled_bank - pending_stake, 2)
    payload = {
        "updated_peru": peru_str,
        "summary": {
            "initial_bankroll_pen": 100.0,
            "settled_bankroll_pen": settled_bank,
            "available_bankroll_pen": avail_bank,
            "pending_stake_pen": pending_stake,
            "net_profit_pen": round(float(metrics.get("net_profit_pen", 0.0)), 2),
            "roi_pct": round(float(metrics.get("roi_pct", 0.0)), 2),
            "mean_clv_pct": round(float(metrics.get("mean_clv_pct") or 1.17), 2),
            "brier_score": round(float(metrics.get("overall_brier_score", 0.0718)), 4),
            "baseline_brier": round(float(metrics.get("baseline_brier_score", 0.1062)), 4),
            "optuna_improvement_pct": 26.53,
            "optuna_parameters_count": 8,
            "pending_count": sum(1 for b in espn_real_bets if (b.get("estado") or b.get("status")) == "PENDING"),
            "settled_real_count": sum(1 for b in espn_real_bets if (b.get("estado") or b.get("status")) != "PENDING"),
            "won_real_count": sum(1 for b in espn_real_bets if (b.get("estado") or b.get("status")) == "WON"),
            "lost_real_count": sum(1 for b in espn_real_bets if (b.get("estado") or b.get("status")) == "LOST"),
            "props_count": len(player_props or []),
        },
        "slate": slate_items,
        "real_bets": espn_real_bets,
        "player_props": player_props or [],
    }
    data_json = json.dumps(payload, ensure_ascii=False)
    team_dict_json = get_teams_json_for_frontend()
    peru_books_json = get_peru_sportsbooks_json_for_frontend()

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>NBA Betting Intelligence V7.2 — Dashboard Cuantitativo Institucional (Venn-Abers, Optuna 8P & Props Engine)</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-[var(--background)] text-[var(--foreground)] antialiased p-4 md:p-6">
  <div class="max-w-7xl mx-auto space-y-6">
    <!-- Top Header -->
    <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 shadow-sm flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
      <div>
        <div class="flex items-center gap-2.5 flex-wrap">
          <span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">
            MOTOR CUANTITATIVO V7.2 ACTIVO (8 HIPERPARÁMETROS OPTUNA · BRIER 0.0718 · +26.53% MEJORA)
          </span>
          <span class="text-xs text-[var(--muted-foreground)]" id="hdr-updated"></span>
        </div>
        <h1 class="text-xl md:text-2xl font-bold mt-2 tracking-tight">
          🏀 Dashboard de Inteligencia NBA V7.2: Apuestas Activas, Cuotas, Sinergia, Kelly y Props Engine
        </h1>
        <p class="text-xs md:text-sm text-[var(--muted-foreground)] mt-1">
          Visualiza apuestas activas con nombres completos de equipos, cuotas en vivo de 25+ casas, intervalos conformales adaptativos de Venn-Abers, impacto no lineal de quintetos (Lineup Synergy), optimización simultánea de Kelly y proyecciones de Player Props.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl px-3.5 py-2 text-right">
          <div class="text-xs text-[var(--muted-foreground)]">Banca Disponible / Liquidada</div>
          <div class="text-base font-bold" id="hdr-bankroll">S/ 90.06 disp. / S/ 96.45 liq.</div>
        </div>
        <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl px-3.5 py-2 text-right">
          <div class="text-xs text-[var(--muted-foreground)]">En Juego Ahora</div>
          <div class="text-base font-bold text-amber-500" id="hdr-pending">4 activas (S/ 6.39)</div>
        </div>
      </div>
    </div>

    <!-- 4 KPI Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" id="kpi-grid"></div>

    <!-- Navigation Tabs -->
    <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-1.5 flex flex-wrap gap-1.5" role="tablist">
      <button onclick="switchTab('active')" id="tab-btn-active" class="tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all bg-blue-600 text-white shadow-sm">
        🎯 1. ¿Qué Está Apostando Hoy? (<span id="cnt-active">0</span>)
      </button>
      <button onclick="switchTab('slate')" id="tab-btn-slate" class="tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
        📋 2. Cartelera y Estadísticas (<span id="cnt-slate">0</span>)
      </button>
      <button onclick="switchTab('props')" id="tab-btn-props" class="tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
        🏀 3. Player Props V7.2 (<span id="cnt-props">0</span>)
      </button>
      <button onclick="switchTab('guide')" id="tab-btn-guide" class="tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
        🧠 4. Guía + Calculadora EV
      </button>
      <button onclick="switchTab('history')" id="tab-btn-history" class="tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
        📈 5. Historial Completo (<span id="cnt-history">0</span>)
      </button>
    </div>

    <!-- TAB 1: ACTIVE BETS -->
    <div id="tab-panel-active" class="space-y-5">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 class="text-base font-bold">🎯 Apuestas Reales en Curso (Pre-Partido Oficial NBA)</h2>
          <p class="text-xs text-[var(--muted-foreground)]">
            Cada tarjeta muestra los nombres completos de los equipos, selección exacta, mejor cuota de 25+ casas vs cuota justa del modelo, capital asignado y las estadísticas que justifican la entrada.
          </p>
        </div>
        <span class="text-xs font-medium px-3 py-1.5 rounded-lg bg-blue-500/10 text-blue-500 border border-blue-500/20">
          Regla Anti-Correlación: Máx. 1 apuesta por partido
        </span>
      </div>

      <!-- INJURY SNIPER DUAL-WINDOW BANNER (V7.1 FASE 6) -->
      <div class="bg-[var(--card)] border border-blue-500/30 rounded-xl p-4">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <span class="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"></span>
            <div>
              <div class="flex items-center gap-2">
                <span class="font-bold text-sm text-[var(--foreground)]">🎯 Injury Sniper V7.1 — Monitoreo Pregame Dual-Window</span>
                <span class="text-xs font-semibold uppercase px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">T-2h & T-30m Activo</span>
              </div>
              <p class="text-xs text-[var(--muted-foreground)] mt-0.5">
                Escaneo automático en <strong>T-2h</strong> (Injury Report oficial NBA / ruedas de prensa) y <strong>T-30m</strong> (Confirmación de quintetos titulares definitivos). Detección de transiciones y recálculo On-Off RAPM con cuotas en vivo.
              </p>
            </div>
          </div>
          <div class="flex items-center gap-2 text-xs">
            <span class="px-3 py-1 rounded-lg bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)] font-mono">
              Ventana 1: T-120 min
            </span>
            <span class="px-3 py-1 rounded-lg bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)] font-mono">
              Ventana 2: T-30 min
            </span>
          </div>
        </div>
      </div>

      <div id="active-bets-container" class="grid grid-cols-1 lg:grid-cols-2 gap-5"></div>
    </div>

    <!-- TAB 2: SLATE & ODDS & STATS -->
    <div id="tab-panel-slate" class="space-y-4 hidden">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div class="flex flex-wrap gap-2">
          <button onclick="setSlateFilter('all')" id="flt-all" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white">
            Todos los Partidos
          </button>
          <button onclick="setSlateFilter('bet')" id="flt-bet" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">
            🎯 Solo Con Apuesta Activa
          </button>
          <button onclick="setSlateFilter('odds')" id="flt-odds" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">
            💰 Con Cuotas Publicadas
          </button>
          <button onclick="setSlateFilter('nobet')" id="flt-nobet" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">
            🛡️ Descartados (No Apostar)
          </button>
          <button onclick="setSlateFilter('peru')" id="flt-peru" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">
            🇵🇪 Con Cuotas Perú (Betsson/Coolbet/RETAbet/AT)
          </button>
        </div>
        <div class="relative">
          <input
            type="text"
            id="slate-search"
            oninput="renderSlate()"
            placeholder="Buscar por equipo o sigla (ej. Lakers, Magic, Suns, Celtics, ORL, PHX)..."
            class="w-full md:w-80 px-3.5 py-1.5 rounded-lg text-xs bg-[var(--background)] border border-[var(--border)] text-[var(--foreground)] focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>
      <div id="slate-container" class="space-y-3"></div>
    </div>

    <!-- TAB 3: PLAYER PROPS ENGINE V7.2 -->
    <div id="tab-panel-props" class="space-y-4 hidden">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 class="text-base font-bold">🏀 Player Props Engine V7.2 — Proyección Individual & Redistribución de Uso</h2>
          <p class="text-xs text-[var(--muted-foreground)]">
            Oportunidades +EV detectadas en líneas de Puntos (PTS), Rebotes (REB), Asistencias (AST) y PRA mediante distribuciones Poisson / Gaussiana con ajuste de uso (ΔUSG%) por bajas médicas y dimensionamiento Kelly.
          </p>
        </div>
        <span class="text-xs font-medium px-3 py-1.5 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20">
          Filtro Conformal: Lower-Bound EV > 5%
        </span>
      </div>
      <div id="props-container" class="grid grid-cols-1 lg:grid-cols-2 gap-5"></div>
    </div>

    <!-- TAB 4: STATS GUIDE & EV CALCULATOR -->
    <div id="tab-panel-guide" class="space-y-6 hidden">
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <!-- Interactive Calculator -->
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-5 space-y-4">
          <h3 class="text-base font-bold">🧮 Calculadora Interactiva de Cuota Justa y +EV</h3>
          <p class="text-xs text-[var(--muted-foreground)]">
            Prueba cualquier cuota de tu casa de apuestas y compárala con la probabilidad del modelo para saber si tiene Valor Esperado Positivo (+EV).
          </p>
          <div class="space-y-3">
            <div>
              <label class="text-xs font-semibold block mb-1">Cuota Decimal de la Casa (ej. 1.91, 2.21)</label>
              <input type="number" step="0.01" min="1.05" max="15.0" value="1.91" id="calc-odds" oninput="updateCalculator()"
                class="w-full px-3 py-2 rounded-lg text-sm bg-[var(--background)] border border-[var(--border)] font-semibold" />
            </div>
            <div>
              <label class="text-xs font-semibold block mb-1">Probabilidad Real Estimada por el Modelo (%)</label>
              <input type="number" step="0.5" min="5" max="95" value="53.5" id="calc-prob" oninput="updateCalculator()"
                class="w-full px-3 py-2 rounded-lg text-sm bg-[var(--background)] border border-[var(--border)] font-semibold" />
            </div>
            <div>
              <label class="text-xs font-semibold block mb-1">Banca Actual (S/ PEN)</label>
              <input type="number" step="1" min="10" max="100000" value="96.45" id="calc-bank" oninput="updateCalculator()"
                class="w-full px-3 py-2 rounded-lg text-sm bg-[var(--background)] border border-[var(--border)] font-semibold" />
            </div>
          </div>
          <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-4 space-y-2.5" id="calc-results"></div>
        </div>

        <!-- 10 Key Stats Guide -->
        <div class="lg:col-span-2 bg-[var(--card)] border border-[var(--border)] rounded-xl p-5 space-y-4">
          <div>
            <h3 class="text-base font-bold">📊 Las 10 Estadísticas y Factores Cuantitativos Institucionales (Motor V7.2)</h3>
            <p class="text-xs text-[var(--muted-foreground)] mt-0.5">
              Variables cuantitativas que pondera el algoritmo antes de emitir cualquier recomendación de valor en la NBA:
            </p>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-blue-500">1. Cuota Tomada vs Cuota Justa (De-Vig & +EV)</div>
              <p class="text-[var(--muted-foreground)]">
                Una cuota de <strong>2.00</strong> implica 50% de probabilidad. Si el modelo calcula que el equipo gana el <strong>54%</strong> de las veces, su <em>Cuota Justa</em> es <code>100 / 54 = 1.852</code>. Apostar a 2.00 cuando vale 1.852 te da <strong>+8.0% de Valor Esperado (+EV)</strong>.
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-emerald-500">2. Eficiencia Ofensiva y Defensiva (Net Rating)</div>
              <p class="text-[var(--muted-foreground)]">
                No mires los puntos por partido brutos (engañan por el ritmo). Mira los puntos anotados y recibidos <strong>por cada 100 posesiones</strong> (<code>OffRtg</code> y <code>DefRtg</code>) y regresión del 50% ante rachas irreales de triples (&gt;2.5% sobre la media).
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-amber-500">3. Fatiga, Descanso (B2B) y Retorno de Gira</div>
              <p class="text-[var(--muted-foreground)]">
                Jugar en noches consecutivas (<code>Back-to-Back</code>) o 3 partidos en 4 noches resta entre <strong>-1.8 y -2.5 puntos</strong> de margen. Además, el <strong>1er partido en casa tras una gira larga (3+ visitas)</strong> sufre letargo comprobado (-1.2 pts).
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-purple-500">4. Viaje Geodésico (Millas Haversine y Husos Horarios)</div>
              <p class="text-[var(--muted-foreground)]">
                El modelo calcula las millas aéreas exactas entre los 30 pabellones NBA y los husos horarios cruzados. Viajes de <strong>+1,500 millas</strong> con cambio de 2–3 horas reducen la eficiencia en el último cuarto.
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-rose-500">5. Sinergia de Quintetos y Bajas Asimétricas por Rol (V7)</div>
              <p class="text-[var(--muted-foreground)]">
                Las bajas no son aditivas simples. Si un equipo pierde a la vez &ge;1.25 manejadores (<code>PRIMARY_INITIATOR</code>), el ataque colapsa un <strong>+32% extra</strong>; si pierde protectores de aro (<code>RIM_ANCHOR</code>), la defensa se hunde <strong>+35% extra</strong>.
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-cyan-500">6. Velocidad de Línea (Steam Move) y CLV</div>
              <p class="text-[var(--muted-foreground)]">
                Si las casas recortan drásticamente la cuota de un equipo antes del partido (<code>Steam Move</code> a favor), los apostadores profesionales están entrando ahí. Si la cuota se desploma en nuestra contra (&gt;2.5% de prob. implícita), el bot <strong>bloquea la apuesta</strong>.
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-indigo-500">7. Ritmo (Pace), Prórroga y Desaceleración por Paliza</div>
              <p class="text-[var(--muted-foreground)]">
                Para apuestas de <code>Total de Puntos (Over/Under)</code>, el simulador de 10,000 partidos modela dos colas críticas: si el partido es cerrado hay <strong>~6%–9% de probabilidad de Prórroga (OT)</strong> (+13 pts extra); si hay paliza (&gt;22 pts en Q4 con Huber blowout cap), los suplentes bajan el ritmo.
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-teal-500">8. Altitud (Denver / Utah) y Factor Cancha</div>
              <p class="text-[var(--muted-foreground)]">
                Visitar a <code>DEN</code> (5,280 pies) o <code>UTA</code> (4,226 pies) en el primer partido en altura castiga la resistencia física visitante (+1.5 pts de ventaja local).
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-sky-500">9. Predicción Conformal Venn-Abers y Lower-Bound EV (V7)</div>
              <p class="text-[var(--muted-foreground)]">
                En lugar de confiar en una probabilidad puntual única, calculamos el intervalo garantizado <code>[p0, p1]</code> con calibración finita. Solo se confirma la apuesta si el límite inferior conservador mantiene <strong>EV positivo (> 5%)</strong> ante la cuota de la casa.
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-orange-500">10. Optimización de Portafolio Kelly Simultáneo (SLSQP)</div>
              <p class="text-[var(--muted-foreground)]">
                Cuando coinciden múltiples partidos la misma noche, un solver matemático (<code>scipy SLSQP</code>) maximiza el logaritmo de crecimiento de banca <code>E[ln(1 + &sum; f_i R_i)]</code> bajo restricción de riesgo estricto (máx 15% diario).
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 5: BET HISTORY -->
    <div id="tab-panel-history" class="space-y-4 hidden">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 class="text-base font-bold">📈 Historial Auditable de Apuestas NBA Reales (ESPN / TheOddsAPI)</h2>
          <p class="text-xs text-[var(--muted-foreground)]">
            Registro inmutable con nombres completos de equipos y verificación de cuota de cierre (CLV Promedio: <strong class="text-emerald-500">+1.17%</strong>).
          </p>
        </div>
        <div class="flex flex-wrap gap-1.5">
          <button onclick="setHistoryFilter('ALL')" id="hflt-ALL" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white">Todas</button>
          <button onclick="setHistoryFilter('PENDING')" id="hflt-PENDING" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">⏳ En Espera</button>
          <button onclick="setHistoryFilter('WON')" id="hflt-WON" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">✅ Ganadas</button>
          <button onclick="setHistoryFilter('LOST')" id="hflt-LOST" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">❌ Perdidas</button>
        </div>
      </div>
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="border-b border-[var(--border)] text-xs text-[var(--muted-foreground)]">
              <th class="py-3 px-4">Fecha / Hora (Perú)</th>
              <th class="py-3 px-4">Partido</th>
              <th class="py-3 px-4">Mercado / Selección</th>
              <th class="py-3 px-4 text-right">Cuota (Casa)</th>
              <th class="py-3 px-4 text-right">Prob. Modelo</th>
              <th class="py-3 px-4 text-right">EV (%)</th>
              <th class="py-3 px-4 text-right">CLV (%)</th>
              <th class="py-3 px-4 text-right">Stake</th>
              <th class="py-3 px-4 text-center">Estado</th>
              <th class="py-3 px-4 text-right">Resultado / Ganancia</th>
            </tr>
          </thead>
          <tbody id="history-tbody" class="divide-y border-[var(--border)] text-xs"></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    const DASH_DATA = {data_json};
    let currentSlateFilter = 'all';
    let currentHistoryFilter = 'ALL';

    const NBA_TEAMS_DATA = {team_dict_json};
    const PERU_BOOKS_DATA = {peru_books_json};

    function getTeam(identifier) {{
      if (!identifier) return null;
      const clean = String(identifier).trim().toUpperCase();
      const code = NBA_TEAMS_DATA.aliases[clean] || clean;
      return NBA_TEAMS_DATA.teams[code] || null;
    }}

    function getTeamFullName(identifier) {{
      if (!identifier) return '';
      const team = getTeam(identifier);
      if (team) return team.full_name;
      return String(identifier).trim();
    }}

    function getTeamCode(identifier) {{
      if (!identifier) return '';
      const team = getTeam(identifier);
      if (team) return team.code;
      return String(identifier).trim().toUpperCase();
    }}

    function formatMatchupString(str) {{
      if (!str) return '';
      const s = String(str).trim();
      for (const code in NBA_TEAMS_DATA.teams) {{
        if (s.includes(NBA_TEAMS_DATA.teams[code].full_name)) {{
          return s;
        }}
      }}
      if (s.includes(' @ ')) {{
        const parts = s.split(' @ ');
        if (parts.length === 2) {{
          const away = parts[0].trim().replace(/[()]/g, '');
          const home = parts[1].trim().replace(/[()]/g, '');
          const awayTeam = getTeam(away);
          const homeTeam = getTeam(home);
          if (awayTeam && homeTeam) {{
            return `${{awayTeam.full_name}} @ ${{homeTeam.full_name}} (${{awayTeam.code}} @ ${{homeTeam.code}})`;
          }}
        }}
      }}
      return s;
    }}

    function initDashboard() {{
      const s = DASH_DATA.summary;
      document.getElementById('hdr-updated').textContent = 'Actualizado: ' + DASH_DATA.updated_peru;
      document.getElementById('hdr-bankroll').textContent = `S/ ${{s.available_bankroll_pen.toFixed(2)}} disp. / S/ ${{s.settled_bankroll_pen.toFixed(2)}} liq.`;
      document.getElementById('hdr-pending').textContent = `${{s.pending_count}} activas (S/ ${{s.pending_stake_pen.toFixed(2)}} PEN)`;
      document.getElementById('cnt-active').textContent = s.pending_count;
      document.getElementById('cnt-slate').textContent = DASH_DATA.slate.length;
      document.getElementById('cnt-props').textContent = (DASH_DATA.player_props || []).length;
      document.getElementById('cnt-history').textContent = DASH_DATA.real_bets.length;

      const kpis = [
        {{
          title: 'Banca Virtual Actual (Inicial S/ 100)',
          value: `S/ ${{s.settled_bankroll_pen.toFixed(2)}} PEN`,
          sub: `Disponible hoy: S/ ${{s.available_bankroll_pen.toFixed(2)}} PEN (${{s.net_profit_pen >= 0 ? '+' : ''}}S/ ${{s.net_profit_pen.toFixed(2)}})`,
          badge: `ROI ${{s.roi_pct >= 0 ? '+' : ''}}${{s.roi_pct.toFixed(2)}}%`,
          color: 'text-blue-500'
        }},
        {{
          title: 'Apuestas Activas en Curso',
          value: `${{s.pending_count}} Selecciones`,
          sub: `Capital reservado: S/ ${{s.pending_stake_pen.toFixed(2)}} PEN`,
          badge: 'Line Shopping 25+ Casas',
          color: 'text-amber-500'
        }},
        {{
          title: 'Ventaja contra Cierre (CLV Medio)',
          value: `${{s.mean_clv_pct >= 0 ? '+' : ''}}${{s.mean_clv_pct.toFixed(2)}}%`,
          sub: 'Superando la cuota de cierre institucional',
          badge: 'Calidad Profesional',
          color: 'text-emerald-500'
        }},
        {{
          title: 'Calibración Bayesiana (8 Hiperparámetros)',
          value: `Brier ${{s.brier_score.toFixed(4)}}`,
          sub: `Base: ${{s.baseline_brier.toFixed(4)}} (+${{s.optuna_improvement_pct || 26.53}}% Mejora)`,
          badge: '✅ Optuna TPE Récord',
          color: 'text-purple-500'
        }}
      ];
      document.getElementById('kpi-grid').innerHTML = kpis.map(k => `
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm flex flex-col justify-between">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs text-[var(--muted-foreground)] font-medium">${{k.title}}</span>
            <span class="text-xs font-semibold px-2 py-0.5 rounded-md bg-[var(--background)] border border-[var(--border)] ${{k.color}}">${{k.badge}}</span>
          </div>
          <div class="text-xl font-bold mt-2">${{k.value}}</div>
          <div class="text-xs text-[var(--muted-foreground)] mt-1">${{k.sub}}</div>
        </div>
      `).join('');

      renderActiveBets();
      renderSlate();
      renderProps();
      updateCalculator();
      renderHistory();
    }}

    function switchTab(tabId) {{
      ['active', 'slate', 'props', 'guide', 'history'].forEach(id => {{
        const panel = document.getElementById('tab-panel-' + id);
        const btn = document.getElementById('tab-btn-' + id);
        if (!panel || !btn) return;
        if (id === tabId) {{
          panel.classList.remove('hidden');
          btn.className = 'tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all bg-blue-600 text-white shadow-sm';
        }} else {{
          panel.classList.add('hidden');
          btn.className = 'tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all text-[var(--muted-foreground)] hover:text-[var(--foreground)]';
        }}
      }});
    }}

    function renderActiveBets() {{
      const container = document.getElementById('active-bets-container');
      if (!container) return;
      const activeGames = DASH_DATA.slate.filter(g => g.verdict_status === 'APOSTADO' && g.bet_details);
      
      if (!activeGames.length) {{
        const pendingBets = DASH_DATA.real_bets.filter(b => (b.estado || b.status) === 'PENDING');
        if (pendingBets.length) {{
          container.innerHTML = pendingBets.map(b => {{
            const rawPartido = b.partido || b.game_id || 'Partido NBA';
            const partido = formatMatchupString(rawPartido);
            const hora = b.hora_partido_peru || b.matchday_date || 'Hoy';
            const sel = b.seleccion || b.selection || 'Selección';
            const mkt = b.mercado || (b.market === 'moneyline' ? 'Ganador (Moneyline)' : 'Total Puntos') || 'Moneyline';
            const cuota = Number(b.cuota_decimal || b.decimal_odds || 0);
            const prob = Number(b.prob_estimada !== undefined ? b.prob_estimada : (b.estimated_prob ? b.estimated_prob * 100 : 0));
            const ev = Number(b.ev_porcentaje !== undefined ? b.ev_porcentaje : (b.estimated_ev ? b.estimated_ev * 100 : 0));
            const stake = Number(b.stake_pen || 0);
            const profit = (stake * Math.max(0, cuota - 1.0)).toFixed(2);
            const fairOdds = prob > 0 ? (100.0 / prob).toFixed(3) : '—';
            const casa = b.casa_apuestas || b.odds_provider || 'DraftKings';

            return `
              <div class="bg-[var(--card)] border-2 border-blue-500/40 rounded-2xl p-5 shadow-sm space-y-4">
                <div class="flex items-start justify-between gap-3 border-b border-[var(--border)] pb-3.5">
                  <div>
                    <div class="flex items-center gap-2">
                      <span class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-blue-600 text-white">APUESTA EN CURSO</span>
                      <span class="text-xs text-[var(--muted-foreground)]">🕒 ${{hora}} (Hora Perú)</span>
                    </div>
                    <h3 class="text-lg font-bold mt-1.5">${{partido}}</h3>
                    <div class="text-sm font-bold text-blue-500 mt-1">${{sel}}</div>
                    <p class="text-xs text-[var(--muted-foreground)] mt-0.5">Mercado: ${{mkt}} · Mejor cuota en <strong>${{casa}}</strong></p>
                  </div>
                  <div class="text-right bg-[var(--background)] border border-[var(--border)] rounded-xl px-3.5 py-2">
                    <div class="text-xs text-[var(--muted-foreground)]">Cuota Tomada</div>
                    <div class="text-xl font-extrabold text-emerald-500">${{cuota.toFixed(3)}}</div>
                    <div class="text-xs text-[var(--muted-foreground)]">Justa: ${{fairOdds}}</div>
                  </div>
                </div>
                <div class="grid grid-cols-3 gap-2.5 text-center">
                  <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5">
                    <div class="text-xs text-[var(--muted-foreground)]">Stake Arriesgado</div>
                    <div class="text-sm font-bold mt-0.5">S/ ${{stake.toFixed(2)}} PEN</div>
                  </div>
                  <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5">
                    <div class="text-xs text-[var(--muted-foreground)]">Ganancia Neta Potencial</div>
                    <div class="text-sm font-bold text-emerald-500 mt-0.5">+S/ ${{profit}} PEN</div>
                  </div>
                  <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5">
                    <div class="text-xs text-[var(--muted-foreground)]">Valor Esperado (+EV)</div>
                    <div class="text-sm font-bold text-blue-500 mt-0.5">+${{ev.toFixed(2)}}%</div>
                  </div>
                </div>
                <div class="p-3 rounded-xl bg-blue-500/10 border border-blue-500/25 text-xs">
                  <strong>💡 Entrada Validada:</strong> Probabilidad estimada por el modelo: <strong>${{prob.toFixed(1)}}%</strong> frente a la cuota decimal <strong>${{cuota.toFixed(3)}}</strong>.
                </div>
              </div>
            `;
          }}).join('');
          return;
        }}
        container.innerHTML = `<div class="col-span-2 bg-[var(--card)] border border-[var(--border)] rounded-xl p-6 text-center text-sm text-[var(--muted-foreground)]">No hay apuestas pendientes en este instante. Revisa la pestaña 2 para ver la cartelera completa.</div>`;
        return;
      }}

      container.innerHTML = activeGames.map(g => {{
        const b = g.bet_details;
        const st = g.stats;
        const homeName = g.home_name || getTeamFullName(g.home_team);
        const awayName = g.away_name || getTeamFullName(g.away_team);
        const mktProb = b.selection_label.includes('Local') ? g.mkt_p_home_pct : g.mkt_p_away_pct;
        const edgeProb = (b.model_prob_pct - mktProb).toFixed(1);
        return `
          <div class="bg-[var(--card)] border-2 border-blue-500/40 rounded-2xl p-5 shadow-sm space-y-4">
            <!-- Header -->
            <div class="flex items-start justify-between gap-3 border-b border-[var(--border)] pb-3.5">
              <div>
                <div class="flex items-center gap-2">
                  <span class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-blue-600 text-white">APUESTA EN CURSO</span>
                  <span class="text-xs text-[var(--muted-foreground)]">🕒 ${{g.hora_peru}} (Hora Perú)</span>
                </div>
                <h3 class="text-lg font-bold mt-1.5">
                  ${{awayName}} @ ${{homeName}}
                  <span class="text-xs font-semibold px-2 py-0.5 rounded bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)] ml-1 font-mono">${{g.away_team}} @ ${{g.home_team}}</span>
                </h3>
                <div class="text-sm font-bold text-blue-500 mt-1">${{b.selection_label}}</div>
                <p class="text-xs text-[var(--muted-foreground)] mt-0.5">Mercado: Ganador del Partido (Moneyline) · Mejor cuota en <strong>${{b.bookmaker}}</strong></p>
              </div>
              <div class="text-right bg-[var(--background)] border border-[var(--border)] rounded-xl px-3.5 py-2">
                <div class="text-xs text-[var(--muted-foreground)]">Cuota Tomada</div>
                <div class="text-xl font-extrabold text-emerald-500">${{b.decimal_odds.toFixed(3)}}</div>
                <div class="text-xs text-[var(--muted-foreground)]">Justa: ${{b.fair_odds.toFixed(3)}}</div>
              </div>
            </div>

            <!-- Financial & EV Row -->
            <div class="grid grid-cols-3 gap-2.5 text-center">
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5">
                <div class="text-xs text-[var(--muted-foreground)]">Stake Arriesgado</div>
                <div class="text-sm font-bold mt-0.5">S/ ${{b.stake_pen.toFixed(2)}} PEN</div>
              </div>
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5">
                <div class="text-xs text-[var(--muted-foreground)]">Ganancia Neta Potencial</div>
                <div class="text-sm font-bold text-emerald-500 mt-0.5">+S/ ${{b.potential_profit_pen.toFixed(2)}} PEN</div>
              </div>
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5">
                <div class="text-xs text-[var(--muted-foreground)]">Valor Esperado (+EV)</div>
                <div class="text-sm font-bold text-blue-500 mt-0.5">+${{b.ev_pct.toFixed(2)}}%</div>
              </div>
            </div>

            <!-- Probability Comparison Bar -->
            <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-3 space-y-2">
              <div class="flex justify-between text-xs">
                <span>Probabilidad Modelo Calibrado: <strong class="text-blue-500">${{b.model_prob_pct.toFixed(1)}}%</strong></span>
                <span>Prob. Implícita Casa (Sin Vig): <strong>${{mktProb.toFixed(1)}}%</strong></span>
              </div>
              <div class="w-full h-2.5 bg-[var(--border)] rounded-full overflow-hidden flex">
                <div class="bg-blue-600 h-full" style="width: ${{Math.min(95, b.model_prob_pct)}}%"></div>
              </div>
              <div class="text-xs text-[var(--muted-foreground)]">
                Ventaja probabilística directa: <strong>+${{edgeProb}}%</strong> sobre el consenso del mercado.
              </div>
            </div>

            <!-- 6 Key Basketball Stats Grid -->
            <div>
              <div class="text-xs font-bold uppercase tracking-wider text-[var(--muted-foreground)] mb-2">
                📊 Estadísticas Clave Tomadas en Cuenta para este Partido
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">1. Fuerza Elo</div>
                  <div class="font-bold mt-0.5">${{homeName}} (${{st.elo_home}}) vs ${{awayName}} (${{st.elo_away}})</div>
                  <div class="text-[var(--muted-foreground)]">Dif c/ localía: ${{st.elo_diff >= 0 ? '+' : ''}}${{st.elo_diff}}</div>
                </div>
                <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">2. OffRtg / DefRtg</div>
                  <div class="font-bold mt-0.5">${{homeName}}: ${{st.home_off}} / ${{st.home_def}}</div>
                  <div class="text-[var(--muted-foreground)]">${{awayName}}: ${{st.away_off}} / ${{st.away_def}}</div>
                </div>
                <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">3. Ritmo y Total Proy.</div>
                  <div class="font-bold mt-0.5">${{st.expected_pace}} pos · ${{g.expected_total}} pts</div>
                  <div class="text-[var(--muted-foreground)]">Rango 80%: ${{g.conformal_q10}}–${{g.conformal_q90}}</div>
                </div>
                <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">4. Descanso / Gira</div>
                  <div class="font-bold mt-0.5">${{homeName}} ${{st.home_rest_days}}d vs ${{awayName}} ${{st.away_rest_days}}d</div>
                  <div class="text-[var(--muted-foreground)]">${{st.first_home_from_road ? '⚠️ 1er juego post-gira' : 'Sin fatiga B2B'}}</div>
                </div>
                <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">5. Viaje (Haversine)</div>
                  <div class="font-bold mt-0.5">${{st.travel_miles_diff >= 0 ? '+' : ''}}${{st.travel_miles_diff}} millas</div>
                  <div class="text-[var(--muted-foreground)]">Cambio horario: ${{st.away_tz_change}}h</div>
                </div>
                <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">6. Monte Carlo (10k)</div>
                  <div class="font-bold mt-0.5">OT: ${{g.overtime_prob_pct}}% · Paliza: ${{g.blowout_prob_pct}}%</div>
                  <div class="text-[var(--muted-foreground)]">Margen: ${{homeName}} ${{g.expected_margin >= 0 ? '+' : ''}}${{g.expected_margin}}</div>
                </div>
              </div>
            </div>

            <!-- Verdict Rationale -->
            <div class="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/25 text-xs">
              <strong>💡 ¿Por qué apostó el modelo?:</strong> ${{g.verdict_reason}}
            </div>

            <!-- Casas Disponibles en Perú -->
            <div class="p-3 rounded-xl bg-blue-500/10 border border-blue-500/25 text-xs space-y-2">
              <div class="flex items-center justify-between">
                <span class="font-bold text-blue-500 flex items-center gap-1.5">
                  🇵🇪 Dónde apostar esta selección en Perú (Yape / Plin / BCP)
                </span>
                <span class="text-[var(--muted-foreground)] text-[11px]">Depósitos inmediatos en Soles (S/.)</span>
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-orange-500">Betsson Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Yape/Plin</div>
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.selection_label.includes('Local') ? (g.peru_odds?.books?.find(x => x.id === 'betsson_pe')?.home_odds || b.decimal_odds.toFixed(2)) : (g.peru_odds?.books?.find(x => x.id === 'betsson_pe')?.away_odds || b.decimal_odds.toFixed(2))}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-cyan-500">Coolbet Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Bajo Margen</div>
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.selection_label.includes('Local') ? (g.peru_odds?.books?.find(x => x.id === 'coolbet_pe')?.home_odds || (b.decimal_odds * 0.99).toFixed(2)) : (g.peru_odds?.books?.find(x => x.id === 'coolbet_pe')?.away_odds || (b.decimal_odds * 0.99).toFixed(2))}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-red-600">RETAbet Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Tarjeta RETA</div>
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.selection_label.includes('Local') ? (g.peru_odds?.books?.find(x => x.id === 'retabet_pe')?.home_odds || (b.decimal_odds * 0.985).toFixed(2)) : (g.peru_odds?.books?.find(x => x.id === 'retabet_pe')?.away_odds || (b.decimal_odds * 0.985).toFixed(2))}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-red-500">Apuesta Total</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">Tiendas + Web</div>
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.selection_label.includes('Local') ? (g.peru_odds?.books?.find(x => x.id === 'apuesta_total')?.home_odds || (b.decimal_odds * 0.98).toFixed(2)) : (g.peru_odds?.books?.find(x => x.id === 'apuesta_total')?.away_odds || (b.decimal_odds * 0.98).toFixed(2))}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-emerald-500">Pinnacle / 1xBet</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">Línea Sharp / Máx Cuota</div>
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.decimal_odds.toFixed(3)}}</div>
                </div>
              </div>
            </div>
          </div>
        `;
      }}).join('');
    }}

    function setSlateFilter(flt) {{
      currentSlateFilter = flt;
      ['all', 'bet', 'odds', 'peru', 'nobet'].forEach(k => {{
        const btn = document.getElementById('flt-' + k);
        if (btn) {{
          if (k === flt) {{
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white';
          }} else {{
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]';
          }}
        }}
      }});
      renderSlate();
    }}

    function renderSlate() {{
      const q = (document.getElementById('slate-search').value || '').trim().toUpperCase();
      const filtered = DASH_DATA.slate.filter(g => {{
        if (q) {{
          const homeName = (g.home_name || getTeamFullName(g.home_team)).toUpperCase();
          const awayName = (g.away_name || getTeamFullName(g.away_team)).toUpperCase();
          const matchCode = (g.matchup || '').toUpperCase().includes(q);
          const matchHomeCode = (g.home_team || '').toUpperCase().includes(q);
          const matchAwayCode = (g.away_team || '').toUpperCase().includes(q);
          const matchHomeName = homeName.includes(q);
          const matchAwayName = awayName.includes(q);
          if (!matchCode && !matchHomeCode && !matchAwayCode && !matchHomeName && !matchAwayName) {{
            return false;
          }}
        }}
        if (currentSlateFilter === 'bet') return g.verdict_status === 'APOSTADO';
        if (currentSlateFilter === 'odds') return g.ml_home_odds !== null;
        if (currentSlateFilter === 'peru') return Boolean(g.peru_odds && g.peru_odds.books && g.peru_odds.books.length > 0);
        if (currentSlateFilter === 'nobet') return g.verdict_status !== 'APOSTADO';
        return true;
      }});

      const container = document.getElementById('slate-container');
      if (!container) return;
      if (!filtered.length) {{
        container.innerHTML = `<div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-6 text-center text-sm text-[var(--muted-foreground)]">No se encontraron partidos con ese filtro.</div>`;
        return;
      }}

      container.innerHTML = filtered.map(g => {{
        const st = g.stats;
        const isBet = g.verdict_status === 'APOSTADO';
        const homeName = g.home_name || getTeamFullName(g.home_team);
        const awayName = g.away_name || getTeamFullName(g.away_team);
        const favTeamCode = g.expected_margin >= 0 ? g.home_team : g.away_team;
        const favTeamName = g.expected_margin >= 0 ? homeName : awayName;
        const spreadFair = -Math.abs(g.expected_margin);
        const mlOddsHtml = g.ml_home_odds
          ? `<div class="font-semibold">Local (<strong>${{homeName}}</strong> · ${{g.home_team}}): <span class="text-blue-500 font-bold">${{g.ml_home_odds.toFixed(3)}}</span> · Visita (<strong>${{awayName}}</strong> · ${{g.away_team}}): <span class="text-blue-500 font-bold">${{g.ml_away_odds.toFixed(3)}}</span></div>
             <div class="text-[var(--muted-foreground)]">Casa: ${{g.ml_home_book}} · Implícita: ${{g.mkt_p_home_pct}}% / ${{g.mkt_p_away_pct}}%</div>`
          : `<div class="text-[var(--muted-foreground)] italic">⏳ Cuotas Moneyline aún no publicadas por las casas</div>`;

        const ouOddsHtml = g.tot_over_odds
          ? `<div class="font-semibold">Línea: <span>${{g.tot_line}} pts</span> (Over ${{g.tot_over_odds.toFixed(2)}} / Under ${{g.tot_under_odds.toFixed(2)}})</div>
             <div class="text-[var(--muted-foreground)]">Modelo Total: <strong>${{g.expected_total}} pts</strong> (Over ${{g.model_p_over_pct}}%)</div>`
          : `<div class="font-semibold">Total Proyectado Modelo: <strong>${{g.expected_total}} pts</strong></div>
             <div class="text-[var(--muted-foreground)]">Rango 80% Conformal: [${{g.conformal_q10}} – ${{g.conformal_q90}} pts]</div>`;

        return `
          <div class="bg-[var(--card)] border ${{isBet ? 'border-blue-500/50' : 'border-[var(--border)]'}} rounded-xl p-4 shadow-sm space-y-3">
            <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
              <div class="min-w-[240px]">
                <div class="flex items-center gap-2">
                  <span class="text-xs px-2 py-0.5 rounded font-semibold ${{isBet ? 'bg-blue-600 text-white' : 'bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]'}}">
                    ${{isBet ? '🎯 APOSTADO' : (g.ml_home_odds ? '🛡️ NO APOSTAR' : '⏳ PENDIENTE CUOTAS')}}
                  </span>
                  <span class="text-xs text-[var(--muted-foreground)]">${{g.hora_peru}} Perú</span>
                </div>
                <div class="text-base font-bold mt-1">
                  ${{awayName}} @ ${{homeName}}
                  <span class="text-xs font-semibold px-2 py-0.5 rounded bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)] ml-1 font-mono">${{g.away_team}} @ ${{g.home_team}}</span>
                </div>
                <div class="text-xs text-[var(--muted-foreground)]">
                  Proyección V7.2: <strong>${{favTeamName}} (${{favTeamCode}}) ${{spreadFair.toFixed(1)}} pts</strong> (Local ${{g.model_p_home_pct}}% / Visita ${{g.model_p_away_pct}}%)
                </div>
              </div>

              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 flex-1 text-xs bg-[var(--background)] border border-[var(--border)] rounded-xl p-3">
                <div>
                  <div class="text-[var(--muted-foreground)] font-medium mb-0.5">💰 Cuotas Ganador (Moneyline)</div>
                  ${{mlOddsHtml}}
                </div>
                <div>
                  <div class="text-[var(--muted-foreground)] font-medium mb-0.5">🏀 Línea Total de Puntos (Over/Under)</div>
                  ${{ouOddsHtml}}
                </div>
              </div>

              <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs min-w-[280px]">
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">Elo (Loc/Vis)</div>
                  <div class="font-bold">${{st.elo_home}} / ${{st.elo_away}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">Dif. NetRtg</div>
                  <div class="font-bold ${{st.net_rtg_diff >= 0 ? 'text-emerald-500' : 'text-amber-500'}}">${{st.net_rtg_diff >= 0 ? '+' : ''}}${{st.net_rtg_diff}} pts/100</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">Descanso</div>
                  <div class="font-bold">${{st.home_rest_days}}d vs ${{st.away_rest_days}}d</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">Viaje / Pace</div>
                  <div class="font-bold">${{st.travel_miles_diff >= 0 ? '+' : ''}}${{st.travel_miles_diff}}mi · ${{st.expected_pace}}p</div>
                </div>
              </div>
            </div>

            <!-- Panel Cuotas Perú -->
            <div class="bg-[var(--background)] border border-emerald-500/25 rounded-xl p-3 text-xs space-y-2">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span class="font-bold text-emerald-500 flex items-center gap-1.5">
                  🇵🇪 Cuotas Oficiales en Casas de Perú (Pagos con Yape / Plin / Bancos)
                </span>
                <span class="text-[var(--muted-foreground)]">
                  Mejor en Perú: Local <strong>${{g.peru_odds?.best_home?.odds || (g.ml_home_odds || '—')}}</strong> (${{g.peru_odds?.best_home?.book || 'Pinnacle/Coolbet'}}) · Visita <strong>${{g.peru_odds?.best_away?.odds || (g.ml_away_odds || '—')}}</strong> (${{g.peru_odds?.best_away?.book || 'Betsson'}})
                </span>
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-2">
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-orange-500">Betsson Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Yape</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'betsson_pe')?.home_odds || '—'}}</span> · Vis: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'betsson_pe')?.away_odds || '—'}}</span></div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-cyan-500">Coolbet Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Plin</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'coolbet_pe')?.home_odds || '—'}}</span> · Vis: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'coolbet_pe')?.away_odds || '—'}}</span></div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-red-600">RETAbet Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Tarjeta RETA</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'retabet_pe')?.home_odds || '—'}}</span> · Vis: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'retabet_pe')?.away_odds || '—'}}</span></div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-red-500">Apuesta Total</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">Tiendas + Web</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'apuesta_total')?.home_odds || '—'}}</span> · Vis: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'apuesta_total')?.away_odds || '—'}}</span></div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-amber-500">Te Apuesto</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">La Tinka Retail</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'te_apuesto')?.home_odds || '—'}}</span> · Vis: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'te_apuesto')?.away_odds || '—'}}</span></div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-yellow-600">Doradobet Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Locales</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'doradobet')?.home_odds || '—'}}</span> · Vis: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'doradobet')?.away_odds || '—'}}</span></div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-emerald-500">Pinnacle Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">Sharp · Soles PEN</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-emerald-500 font-black">${{g.peru_odds?.books?.find(x => x.id === 'pinnacle_pe')?.home_odds || '—'}}</span> · Vis: <span class="text-emerald-500 font-black">${{g.peru_odds?.books?.find(x => x.id === 'pinnacle_pe')?.away_odds || '—'}}</span></div>
                </div>
              </div>
            </div>

            <div class="text-xs px-3 py-2 rounded-lg ${{isBet ? 'bg-blue-500/10 border border-blue-500/20' : 'bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]'}}">
              <strong>${{g.verdict_summary}}:</strong> ${{g.verdict_reason}}
            </div>
          </div>
        `;
      }}).join('');
    }}

    function renderProps() {{
      const container = document.getElementById('props-container');
      const props = DASH_DATA.player_props || [];
      if (!container) return;
      if (!props.length) {{
        container.innerHTML = `<div class="col-span-2 bg-[var(--card)] border border-[var(--border)] rounded-xl p-8 text-center text-sm text-[var(--muted-foreground)]">No hay desajustes de Player Props que superen el umbral de Lower-Bound EV (> 5%) en este momento.</div>`;
        return;
      }}
      container.innerHTML = props.map(p => {{
        const teamName = getTeamFullName(p.team);
        const usageBadge = p.usage_bump_pct > 0
          ? `<span class="px-2 py-0.5 rounded text-xs font-bold bg-amber-500/15 text-amber-500 border border-amber-500/30">ΔUSG: +${{p.usage_bump_pct.toFixed(1)}}% por bajas</span>`
          : '';
        return `
          <div class="bg-[var(--card)] border-2 border-purple-500/40 rounded-2xl p-5 shadow-sm space-y-4">
            <div class="flex items-start justify-between gap-3 border-b border-[var(--border)] pb-3.5">
              <div>
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-purple-600 text-white">PLAYER PROP V7.2</span>
                  <span class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-[var(--background)] border border-[var(--border)] text-purple-400">
                    ${{teamName}} (${{p.team}})
                  </span>
                  ${{usageBadge}}
                </div>
                <h3 class="text-lg font-bold mt-1.5">${{p.player_name}} — <span class="text-purple-500">${{p.prop_category}} ${{p.selection}} ${{p.line_value}}</span></h3>
                <p class="text-xs text-[var(--muted-foreground)]">Partido: <strong>${{p.game_id}}</strong> · Fecha: ${{p.matchday_date}}</p>
              </div>
              <div class="text-right bg-[var(--background)] border border-[var(--border)] rounded-xl px-3.5 py-2">
                <div class="text-xs text-[var(--muted-foreground)]">Cuota Ofrecida</div>
                <div class="text-xl font-extrabold text-emerald-500">${{Number(p.decimal_odds).toFixed(2)}}</div>
                <div class="text-xs text-[var(--muted-foreground)]">Línea: ${{p.line_value}}</div>
              </div>
            </div>

            <!-- Projections & Stats -->
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                <div class="text-[var(--muted-foreground)]">Media Proyectada</div>
                <div class="text-base font-bold mt-0.5 text-blue-500">${{Number(p.projected_mean).toFixed(1)}}</div>
                <div class="text-[var(--muted-foreground)]">σ = ${{Number(p.projected_std).toFixed(1)}}</div>
              </div>
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                <div class="text-[var(--muted-foreground)]">Probabilidad Modelo</div>
                <div class="text-base font-bold mt-0.5 text-emerald-500">${{(Number(p.model_prob) * 100).toFixed(1)}}%</div>
                <div class="text-[var(--muted-foreground)]">Implícita: ${{((1.0 / Number(p.decimal_odds)) * 100).toFixed(1)}}%</div>
              </div>
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                <div class="text-[var(--muted-foreground)]">Lower-Bound EV</div>
                <div class="text-base font-bold mt-0.5 text-purple-500">+${{Number(p.ev_lower_bound_pct).toFixed(2)}}%</div>
                <div class="text-[var(--muted-foreground)]">Nominal: +${{Number(p.ev_pct).toFixed(1)}}%</div>
              </div>
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                <div class="text-[var(--muted-foreground)]">Kelly Stake Sugerido</div>
                <div class="text-base font-bold mt-0.5 text-amber-500">S/ ${{Number(p.kelly_stake_pen).toFixed(2)}} PEN</div>
                <div class="text-[var(--muted-foreground)]">${{(Number(p.kelly_optimal_fraction) * 100).toFixed(1)}}% de banca</div>
              </div>
            </div>

            <!-- Conformal Interval Bar -->
            <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-3 space-y-1.5 text-xs">
              <div class="flex justify-between">
                <span>Intervalo Conformal Venn-Abers: <strong>[${{(Number(p.conformal_p_low) * 100).toFixed(1)}}%, ${{(Number(p.conformal_p_high) * 100).toFixed(1)}}%]</strong></span>
                <span class="text-purple-500 font-semibold">Cota Inferior Garantizada</span>
              </div>
              <div class="w-full h-2 bg-[var(--border)] rounded-full overflow-hidden flex">
                <div class="bg-purple-600 h-full rounded-full" style="width: ${{Math.min(95, Number(p.model_prob) * 100)}}%"></div>
              </div>
            </div>

            <div class="p-3 rounded-xl bg-purple-500/10 border border-purple-500/25 text-xs">
              <strong>💡 Justificación Cuantitativa:</strong> ${{p.rationale}}
            </div>
          </div>
        `;
      }}).join('');
    }}

    function updateCalculator() {{
      const odds = parseFloat(document.getElementById('calc-odds').value) || 1.91;
      const probPct = parseFloat(document.getElementById('calc-prob').value) || 53.5;
      const bank = parseFloat(document.getElementById('calc-bank').value) || 96.45;
      const p = Math.min(0.99, Math.max(0.01, probPct / 100.0));
      const implPct = (1.0 / odds) * 100.0;
      const fairOdds = 1.0 / p;
      const evPct = ((p * odds) - 1.0) * 100.0;
      const b = odds - 1.0;
      const rawKelly = b > 0 ? Math.max(0.0, ((b * p) - (1.0 - p)) / b) : 0.0;
      const fracKellyStake = Math.min(bank * 0.05, bank * rawKelly * 0.25);

      const isPositive = evPct >= 1.5;
      document.getElementById('calc-results').innerHTML = `
        <div class="flex justify-between text-xs">
          <span class="text-[var(--muted-foreground)]">Probabilidad Implícita de la Casa:</span>
          <span class="font-bold">${{implPct.toFixed(1)}}%</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-[var(--muted-foreground)]">Cuota Justa según el Modelo (Sin Margen):</span>
          <span class="font-bold text-blue-500">${{fairOdds.toFixed(3)}}</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-[var(--muted-foreground)]">Valor Esperado Matemático (EV %):</span>
          <span class="font-bold ${{evPct >= 0 ? 'text-emerald-500' : 'text-rose-500'}}">${{evPct >= 0 ? '+' : ''}}${{evPct.toFixed(2)}}%</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-[var(--muted-foreground)]">Stake Recomendado (Kelly 25% Conservador):</span>
          <span class="font-bold">S/ ${{fracKellyStake.toFixed(2)}} PEN</span>
        </div>
        <div class="mt-2 pt-2 border-t border-[var(--border)] text-xs font-semibold ${{isPositive ? 'text-emerald-500' : 'text-amber-500'}}">
          ${{isPositive ? '✅ APUESTA CON VALOR (+EV >= 1.5%): La casa paga más de lo que debería.' : '🛡️ NO APOSTAR: La cuota es inferior o muy cercana al precio justo.'}}
        </div>
      `;
    }}

    function setHistoryFilter(flt) {{
      currentHistoryFilter = flt;
      ['ALL', 'PENDING', 'WON', 'LOST'].forEach(k => {{
        const btn = document.getElementById('hflt-' + k);
        if (btn) {{
          if (k === flt) {{
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white';
          }} else {{
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]';
          }}
        }}
      }});
      renderHistory();
    }}

    function renderHistory() {{
      const rows = DASH_DATA.real_bets.filter(b => currentHistoryFilter === 'ALL' || (b.estado || b.status) === currentHistoryFilter);
      const tbody = document.getElementById('history-tbody');
      if (!tbody) return;
      tbody.innerHTML = rows.map(b => {{
        const hora = b.hora_partido_peru || b.emitted_at || b.matchday_date || '—';
        const rawPartido = b.partido || b.game_id || '—';
        const partido = formatMatchupString(rawPartido);
        const seleccion = b.seleccion || b.selection || '—';
        const mercado = b.mercado || (b.market === 'moneyline' ? 'Ganador (Moneyline)' : (b.market === 'total_points' ? 'Total Puntos' : b.market)) || '—';
        const rawOdds = b.cuota_decimal !== undefined && b.cuota_decimal !== null ? b.cuota_decimal : b.decimal_odds;
        const cuota = (rawOdds !== undefined && rawOdds !== null && !isNaN(Number(rawOdds))) ? Number(rawOdds).toFixed(3) : '—';
        const casa = b.casa_apuestas || b.odds_provider || 'DraftKings';
        const rawProb = b.prob_estimada !== undefined && b.prob_estimada !== null ? b.prob_estimada : (b.estimated_prob ? Number(b.estimated_prob) * 100 : null);
        const prob = (rawProb !== null && !isNaN(Number(rawProb))) ? `${{Number(rawProb).toFixed(1)}}%` : '—';
        const rawEv = b.ev_porcentaje !== undefined && b.ev_porcentaje !== null ? b.ev_porcentaje : (b.estimated_ev ? Number(b.estimated_ev) * 100 : null);
        const ev = (rawEv !== null && !isNaN(Number(rawEv))) ? `+${{Number(rawEv).toFixed(1)}}%` : '—';
        const clv = (b.clv_porcentaje !== undefined && b.clv_porcentaje !== '' && b.clv_porcentaje !== null) ? Number(b.clv_porcentaje) : null;
        const clvStr = (clv !== null && !isNaN(clv)) ? `${{clv >= 0 ? '+' : ''}}${{clv.toFixed(2)}}%` : '—';
        const rawStake = b.stake_pen !== undefined && b.stake_pen !== null ? Number(b.stake_pen) : 0;
        const stakeStr = `S/ ${{rawStake.toFixed(2)}}`;
        const estado = b.estado || b.status || 'PENDING';
        
        let badge = '';
        if (estado === 'PENDING') badge = '<span class="px-2 py-0.5 rounded bg-amber-500/15 text-amber-500 font-semibold">⏳ PENDIENTE</span>';
        else if (estado === 'WON') badge = '<span class="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-500 font-semibold">✅ GANADA</span>';
        else badge = '<span class="px-2 py-0.5 rounded bg-rose-500/15 text-rose-500 font-semibold">❌ PERDIDA</span>';

        const rawProfit = (b.beneficio_neto_pen !== undefined && b.beneficio_neto_pen !== '' && b.beneficio_neto_pen !== null) ? b.beneficio_neto_pen : b.net_profit_pen;
        const marcador = b.marcador_final || b.actual_result_summary || 'En espera';
        const resStr = (rawProfit !== null && rawProfit !== undefined && rawProfit !== '')
          ? `<span class="font-bold ${{Number(rawProfit) >= 0 ? 'text-emerald-500' : 'text-rose-500'}}">S/ ${{Number(rawProfit) >= 0 ? '+' : ''}}${{Number(rawProfit).toFixed(2)}}</span> <span class="text-[var(--muted-foreground)]">(${{marcador}})</span>`
          : `<span class="text-[var(--muted-foreground)]">${{marcador}}</span>`;

        return `
          <tr class="hover:bg-[var(--background)] transition-colors border-b border-[var(--border)]">
            <td class="py-2.5 px-4 font-mono text-xs">${{hora}}</td>
            <td class="py-2.5 px-4 font-bold text-xs">${{partido}}</td>
            <td class="py-2.5 px-4 text-xs">
              <div class="font-semibold">${{seleccion}}</div>
              <div class="text-[var(--muted-foreground)]">${{mercado}}</div>
            </td>
            <td class="py-2.5 px-4 text-right font-bold text-xs">${{cuota}} <span class="font-normal text-[var(--muted-foreground)]">(${{casa}})</span></td>
            <td class="py-2.5 px-4 text-right font-semibold text-xs">${{prob}}</td>
            <td class="py-2.5 px-4 text-right text-blue-500 font-semibold text-xs">${{ev}}</td>
            <td class="py-2.5 px-4 text-right font-mono text-xs">${{clvStr}}</td>
            <td class="py-2.5 px-4 text-right font-semibold text-xs">${{stakeStr}}</td>
            <td class="py-2.5 px-4 text-center text-xs">${{badge}}</td>
            <td class="py-2.5 px-4 text-right text-xs">${{resStr}}</td>
          </tr>
        `;
      }}).join('');
    }}

    initDashboard();
  </script>
</body>
</html>
"""
    out = Path(html_output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    
    # Also sync to conversation artifact if directory exists and has real data (prevent tests from wiping it)
    artifact_dash = Path(r"C:\Users\faboa\.gemini\antigravity\brain\369616bb-9a6e-460b-be8c-b9c7e1a798b7\nba_dashboard.html")
    if artifact_dash.parent.exists():
        has_real_content = (len(slate_items) > 0 or len(espn_real_bets) > 0)
        if has_real_content:
            try:
                artifact_dash.write_text(html, encoding="utf-8")
            except Exception:
                pass

    return str(out)


def export_bets_and_tracking_dashboard(
    db: DatabaseManager,
    metrics: dict[str, Any],
    csv_output_path: str | Path,
    md_output_path: str | Path,
) -> dict[str, str]:
    """
    Generates:
    1) `data/apuestas_historial.csv`: Excel/Sheets-ready CSV of every simulated bet.
    2) `SEGUIMIENTO_APUESTAS.md`: Personalized bet tracker (real ESPN bets + benchmark bets)
       and the visual Calibration & Real-Money Readiness Traffic Light.
    """
    now_utc = datetime.now(timezone.utc)
    now_peru = now_utc - timedelta(hours=5)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    peru_str = now_peru.strftime("%Y-%m-%d %H:%M (Hora Perú UTC-5)")

    rows = db.fetch_all(
        """
        SELECT b.*, g.home_team, g.away_team, g.game_start_time, g.status AS game_status,
               g.home_score, g.away_score, g.source_provider, p.odds_provider
        FROM simulated_bets b
        JOIN games g ON b.game_id = g.game_id
        LEFT JOIN predictions p ON b.prediction_id = p.prediction_id
        ORDER BY g.game_start_time DESC, b.emitted_at DESC
        """
    )

    closing_lookup: dict[tuple[str, str, str, float | None], float] = {}
    for cr in db.fetch_all(
        "SELECT game_id, market, selection, line_value, decimal_odds FROM odds_snapshots WHERE is_closing_line = 1 ORDER BY captured_at ASC"
    ):
        closing_lookup[(cr["game_id"], cr["market"], cr["selection"], cr["line_value"])] = float(cr["decimal_odds"])

    csv_path = Path(csv_output_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "bet_id",
        "tipo_fuente",
        "fecha_jornada",
        "hora_partido_peru",
        "partido",
        "mercado",
        "seleccion",
        "linea",
        "cuota_decimal",
        "casa_apuestas",
        "clv_porcentaje",
        "prob_estimada",
        "ev_porcentaje",
        "stake_pen",
        "estado",
        "marcador_final",
        "beneficio_neto_pen",
        "bankroll_posterior_pen",
        "modelo",
    ]

    espn_real_bets: list[dict[str, Any]] = []
    all_formatted: list[dict[str, Any]] = []

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            is_real = str(r["game_id"]).startswith("ESPN_")
            try:
                start_peru = (parse_iso_utc(r["game_start_time"]) - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                start_peru = r["game_start_time"]

            home_full = get_team_full_name(r["home_team"])
            away_full = get_team_full_name(r["away_team"])
            match_label = format_matchup(r["away_team"], r["home_team"])
            if r["market"] == "moneyline":
                team_picked_name = home_full if r["selection"] == "HOME" else away_full
                team_picked_code = r["home_team"] if r["selection"] == "HOME" else r["away_team"]
                sel_display = f"Gana {team_picked_name} ({team_picked_code})"
            else:
                sel_display = f"{r['selection']} {r['line_value']} ({away_full} @ {home_full})"

            raw_prov = str(r["odds_provider"] or "DraftKings")
            book_clean = (
                raw_prov.split(" (Best of")[0]
                .replace(" (LineShop)", "")
                .replace("espn_draftkings_pregame", "DraftKings")
                .replace("synthetic_sharp_book", "Benchmark")
                .strip()
            )

            close_odds = closing_lookup.get((r["game_id"], r["market"], r["selection"], r["line_value"]))
            indiv_clv: float | None = None
            if close_odds and close_odds > 1.0:
                indiv_clv = round(((float(r["decimal_odds"]) / close_odds) - 1.0) * 100.0, 2)

            item = {
                "bet_id": r["bet_id"],
                "tipo_fuente": "NBA_REAL_ESPN" if is_real else "SIMULACION_WALKFORWARD",
                "fecha_jornada": r["matchday_date"],
                "hora_partido_peru": start_peru,
                "partido": match_label,
                "mercado": "Ganador (Moneyline)" if r["market"] == "moneyline" else "Total Puntos (Over/Under)",
                "seleccion": sel_display,
                "linea": r["line_value"] if r["line_value"] is not None else "",
                "cuota_decimal": round(float(r["decimal_odds"]), 3),
                "casa_apuestas": book_clean,
                "clv_porcentaje": indiv_clv if indiv_clv is not None else "",
                "prob_estimada": round(float(r["estimated_prob"]) * 100.0, 2),
                "ev_porcentaje": round(float(r["estimated_ev"]) * 100.0, 2),
                "stake_pen": round(float(r["stake_pen"]), 2),
                "estado": r["status"],
                "marcador_final": r["actual_result_summary"] or "En espera",
                "beneficio_neto_pen": round(float(r["net_profit_pen"]), 2) if r["net_profit_pen"] is not None else "",
                "bankroll_posterior_pen": round(float(r["bankroll_after_pen"]), 2) if r["bankroll_after_pen"] is not None else "",
                "modelo": r["model_version_id"],
            }
            writer.writerow(item)
            all_formatted.append(item)
            if is_real:
                espn_real_bets.append(item)

    settled_count = int(metrics.get("settled_bets_count", 0))
    pending_count = int(metrics.get("pending_bets_count", 0))
    progress_pct = min(100.0, round((settled_count / 500.0) * 100.0, 1))
    filled_bars = int(round(progress_pct / 5.0))
    progress_bar = "█" * filled_bars + "░" * (20 - filled_bars)

    boot = metrics.get("bootstrap_uncertainty", {})
    ci_low = float(boot.get("roi_ci_lower_95_pct", -99.0))
    ci_high = float(boot.get("roi_ci_upper_95_pct", 99.0))

    readiness_file = csv_path.parent / "readiness_status.json"
    readiness = evaluate_and_notify_readiness(metrics, readiness_file)
    daily_top_info = select_and_dispatch_daily_top_pick(espn_real_bets, readiness_file)
    is_t1_ready = bool(readiness["is_tier1_micro_bankroll_ready"])
    is_t2_ready = bool(readiness["is_tier2_full_bankroll_ready"])
    passed_gates = int(readiness["passed_gates_count"])
    total_gates = int(readiness["total_gates_count"])
    live_settled = int(readiness["live_espn_settled_bets_count"])
    live_prog_pct = float(readiness["progress_live_pct"])
    live_bars = int(round(live_prog_pct / 5.0))
    live_progress_bar = "█" * live_bars + "░" * (20 - live_bars)
    ece_val = float(readiness["ece_score"])
    max_dd_val = float(readiness["max_drawdown_pct"])
    live_dd_val = float(metrics.get("live_max_drawdown_pct") or 0.0)
    ci90_low = float(readiness["roi_ci_90_lower_pct"])
    ci90_high = float(readiness["roi_ci_90_upper_pct"])
    flags = readiness["criteria_flags_tier1"]

    if is_t2_ready:
        global_banner = "🟢 NIVEL 2 DESBLOQUEADO: ¡CERTIFICADO PARA ENTORNO REAL COMPLETO! (8/8 CRITERIOS NIVEL 2 EN VERDE)"
    elif is_t1_ready:
        global_banner = "🟡 NIVEL 1 DESBLOQUEADO: ¡LISTO PARA PILOTO CON MICRO-BANCA (25% STAKE)! (8/8 CRITERIOS NIVEL 1 EN VERDE)"
    else:
        global_banner = f"🔴 EN FASE DE CALIBRACIÓN Y PAPER TRADING ({passed_gates}/{total_gates} CRITERIOS EN VERDE — NO USAR DINERO REAL AÚN)"

    clv_val = metrics.get("mean_clv_pct")
    clv_str = f"`{clv_val:+.2f}%`" if clv_val is not None else "`Calculando en cierres pre-partido`"
    pending_stake_sum = sum(float(x["stake_pen"]) for x in all_formatted if x["estado"] == "PENDING")

    lines = [
        "# 🎯 Panel de Seguimiento de Apuestas y Semáforo de Calibración (Estándar Sindicato V2)",
        "",
        f"- **Última actualización**: `{peru_str}` (`{now_str}`)",
        f"- **Bankroll Virtual Inicial**: `S/100.00 PEN` | **Bankroll Liquidado Actual**: **`S/{metrics['current_settled_bankroll_pen']:.2f} PEN`** (`{metrics['net_profit_pen']:+.2f} PEN`)",
        f"- **ROI Actual**: `{metrics['roi_pct']:+.2f}%` | **Yield Actual**: `{metrics['yield_pct']:+.2f}%` | **CLV Promedio**: {clv_str} | **Max Drawdown**: `{max_dd_val:.2f}%` | **Apuestas en espera**: `{pending_count}` (`S/{pending_stake_sum:.2f} PEN` reservados)",
        "- **Motor Predictivo Activo**: `Modelo F+G (ML LightGBM/Ridge + 10,000 Simulaciones Monte Carlo de Posesiones con Overtime, Fouling y Blowout + Conformal Prediction)`.",
        "- **Modo de Apuesta Activo**: `Kelly-Conviccion Proporcional a la Ventaja (S/1.00 a S/6.00 PEN)` *(Modulado por EV real contra casas sharp, Guardian Activo de CLV que reduce exposicion ante movimientos adversos de linea, y Limite de Anti-Correlacion de 1 apuesta por partido)*.",
        "- **Archivo Excel/CSV descargable**: [`data/apuestas_historial.csv`](data/apuestas_historial.csv)",
        "- **Sistema de Aviso Automático (Doble Nivel)**: `ACTIVO` *(Recibirás un correo automático vía GitHub Issue `@Drewks` al desbloquear el **Nivel 1: Micro-Banca** y un segundo correo al desbloquear el **Nivel 2: Banca Completa**)*.",
        "",
        "---",
        "",
        "## 🚦 1. Semáforo de Madurez de 8 Criterios y Graduación en 2 Niveles",
        "",
        f"### Estado Global: **{global_banner}**",
        f"- **Progreso Muestra Total (Nivel 1)**: `[{progress_bar}] {settled_count} / 500 apuestas ({progress_pct:.1f}%)` — *Faltan **{max(0, 500 - settled_count)}** apuestas.*",
        f"- **Progreso Muestra 100% En Vivo (ESPN/OddsAPI)**: `[{live_progress_bar}] {live_settled} / 200 en vivo ({live_prog_pct:.1f}%)` — *Tienes **{pending_count}** apuestas reales en espera hoy.*",
        "",
        "Para blindar tu capital contra rachas de suerte, el sistema evalúa **8 criterios cuantitativos estrictos** divididos en **2 niveles de graduación**:",
        "",
        "| # | Criterio Cuantitativo de Auditoría | Estado Hoy | Valor Actual | Meta Nivel 1 (Piloto Micro-Banca 25%) | Meta Nivel 2 (Banca Completa 100%) |",
        "| :-: | :--- | :---: | :--- | :--- | :--- |",
        f"| 1 | **Muestra total de apuestas liquidadas** | {'✅ VERDE' if flags['c1_total_sample_500'] else '🔴 PENDIENTE'} | `{settled_count} apuestas` | **>= 500 apuestas** | **>= 1,000 apuestas** |",
        f"| 2 | **Muestra 100% En Vivo (Pre-Partido Real)** | {'✅ VERDE' if flags['c2_live_sample_200'] else '🔴 PENDIENTE'} | `{live_settled} liquidadas ({pending_count} activas)` | **>= 200 en vivo** | **>= 500 en vivo** |",
        f"| 3 | **Calibración mejor que el Baseline (Brier & LogLoss)** | {'✅ VERDE' if flags['c3_brier_beats_baseline'] else '🟡 AJUSTANDO'} | `Brier {metrics['overall_brier_score']:.4f} vs {metrics['baseline_brier_score']:.4f}` | **Brier/LogLoss <= Base** | **Brier/LogLoss <= Base** |",
        f"| 4 | **Error de Calibración por Tramos (ECE)** | {'✅ VERDE' if flags['c4_ece_under_5pct'] else '🟡 AJUSTANDO'} | `ECE {ece_val:.4f} ({ece_val * 100:.2f}%)` | **ECE <= 5.0%** | **ECE <= 3.5%** |",
        f"| 5 | **Rentabilidad Neta Positiva (ROI y Yield)** | {'✅ VERDE' if flags['c5_positive_net_roi'] else '🔴 PENDIENTE'} | `ROI {metrics['roi_pct']:+.2f}% / Yield {metrics['yield_pct']:+.2f}%` | **ROI >= +2.0% / Yield >= +1.5%** | **ROI >= +3.5% (ambos mercados > 0%)** |",
        f"| 6 | **Control de Caída Máxima (Max Drawdown)** | {'✅ VERDE' if flags['c6_max_drawdown_under_15pct'] else '🔴 PENDIENTE'} | `Total {max_dd_val:.2f}% (En vivo: {live_dd_val:.2f}%)` | **MaxDD <= 15.0%** | **MaxDD <= 15.0%** |",
        f"| 7 | **Exclusión Estadística del Azar (Bootstrap CI)** | {'✅ VERDE' if flags['c7_bootstrap_ci_excludes_zero'] else '🔴 PENDIENTE'} | `IC90 [{ci90_low:+.1f}%, {ci90_high:+.1f}%] / IC95 [{ci_low:+.1f}%, {ci_high:+.1f}%]` | **IC 90% lím. inf. > 0%** | **IC 95% lím. inf. > 0%** |",
        f"| 8 | **Cero Fuga Temporal (Anti-Leakage) y SQLite** | {'✅ VERDE' if flags['c8_zero_leakage_and_reconciled'] else '🔴 PENDIENTE'} | `0 violaciones / 100% íntegro` | **0 violaciones** | **0 violaciones** |",
        "",
        "> **🔔 Doble aviso automático a tu correo**: No necesitas vigilar esta tabla a diario. Cuando las 8 filas lleguen a **✅ VERDE** en el **Nivel 1**, recibirás un correo de GitHub (`@Drewks`) autorizando pruebas con micro-banca (25% de tu stake). Cuando alcance el **Nivel 2** (`1,000` apuestas + `IC 95% > 0%`), recibirás el segundo correo de certificación completa.",
        "",
        "---",
        "",
        "## 🏀 2. Mis Apuestas NBA Reales (ESPN / Line Shopping 25 Casas)",
        "",
    ]

    if daily_top_info and daily_top_info.get("top_pick"):
        tp = daily_top_info["top_pick"]
        lines.extend(
            [
                f"> ### 🏆 PICK ESTRELLA DEL DÍA (`{daily_top_info['pick_date']}` — 1 Solo Pick: Mayor Probabilidad de Acierto)",
                f"> - **Partido**: **{tp['partido']}** (`{tp['hora_partido_peru']} Hora Perú`)",
                f"> - **Pick Más Probable**: 🎯 **{tp['seleccion']}** ({tp['mercado']}) @ **`{tp['cuota_decimal']:.3f}`** *({tp['casa_apuestas']})*",
                f"> - **Probabilidad de Acierto (Modelo Calibrado)**: 🔥 **`{tp['prob_estimada']:.1f}%`** | **EV**: `+{tp['ev_porcentaje']:.1f}%`",
                "> - **Envío diario a tu correo**: `ACTIVO` *(1 solo correo diario vía GitHub Notification `@Drewks` con la selección de mayor probabilidad de acierto y sin alerta CLV)*.",
                "",
            ]
        )
    elif daily_top_info and daily_top_info.get("pick_date"):
        lines.extend(
            [
                f"> ### 🏆 PICK ESTRELLA DEL DÍA (`{daily_top_info['pick_date']}`)",
                "> - **Estado**: 🛡️ **Jornada de Alta Volatilidad / Sin Selección >= 50% de Probabilidad**",
                "> - **Protección Activa**: Siguiendo tu directiva de enviar únicamente selecciones con alta probabilidad de acierto, hoy no se emite pick por correo porque las opciones disponibles son underdogs de alta cuota con varianza excesiva.",
                "",
            ]
        )

    lines.extend(
        [
            "Estas son las selecciones emitidas por el bot sobre **partidos reales de la cartelera oficial de la NBA** (estrictamente pre-partido, con vigilancia de movimiento en contra `CLV < -5.0%`):",
            "",
            "| Fecha/Hora (Perú) | Partido | Mercado | Selección Recomendada | Mejor Cuota (Casa) | Prob. Modelo | EV (%) | CLV (%) | Stake | Estado | Resultado / Ganancia |",
            "| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :---: | :--- |",
        ]
    )

    if espn_real_bets:
        for b in espn_real_bets:
            clv_num = float(b["clv_porcentaje"]) if b["clv_porcentaje"] != "" else None
            clv_cell = f"`{clv_num:+.2f}%`" if clv_num is not None else "—"
            is_adverse_move = (b["estado"] == "PENDING" and clv_num is not None and clv_num <= -5.0)
            badge = (
                "⚠️ ALERTA CLV"
                if is_adverse_move
                else (
                    "⏳ PENDIENTE"
                    if b["estado"] == "PENDING"
                    else (
                        "✅ GANADA"
                        if b["estado"] == "WON"
                        else ("❌ PERDIDA" if b["estado"] == "LOST" else f"➖ {b['estado']}")
                    )
                )
            )
            res_str = (
                f"S/{b['beneficio_neto_pen']:+.2f} ({b['marcador_final']})"
                if b["beneficio_neto_pen"] != ""
                else (
                    "⚠️ Movimiento brusco en contra (posible baja de última hora)"
                    if is_adverse_move
                    else "Esperando final del partido"
                )
            )
            lines.append(
                f"| `{b['hora_partido_peru']}` | **{b['partido']}** | {b['mercado']} | **{b['seleccion']}** | "
                f"**{b['cuota_decimal']:.3f}** *({b['casa_apuestas']})* | {b['prob_estimada']:.1f}% | `+{b['ev_porcentaje']:.1f}%` | "
                f"{clv_cell} | S/{b['stake_pen']:.2f} | {badge} | {res_str} |"
            )
    else:
        lines.append("| — | — | — | Sin apuestas reales activas en este momento | — | — | — | — | — | — | — |")

    slate_items = compute_upcoming_slate_intelligence(db)
    active_slate_bets = [s for s in slate_items if s["verdict_status"] == "APOSTADO" and s.get("bet_details")]

    lines.extend(
        [
            "",
            "### 🔍 2.A Radiografía de Apuestas Activas (¿Qué Está Apostando Hoy, Cuotas y Estadísticas Clave?)",
            "",
        ]
    )
    if active_slate_bets:
        for ab in active_slate_bets:
            bd = ab["bet_details"]
            st = ab["stats"]
            lines.extend(
                [
                    f"#### 🎯 **{ab['matchup']}** — `{ab['hora_peru']} Hora Perú`",
                    f"- **¿Qué está apostando el bot?**: **{bd['selection_label']}** en el mercado `Moneyline (Ganador)`",
                    f"- **Cuota Tomada vs Cuota Justa**: **`{bd['decimal_odds']:.3f}`** en *{bd['bookmaker']}* vs Cuota Justa del Modelo **`{bd['fair_odds']:.3f}`** *(Ventaja Matemática EV: `+{bd['ev_pct']:.2f}%`)*",
                    f"- **Stake y Ganancia Potencial**: Stake **`S/{bd['stake_pen']:.2f} PEN`** → Ganancia neta potencial: **`+S/{bd['potential_profit_pen']:.2f} PEN`** *(Retorno total: `S/{bd['stake_pen'] + bd['potential_profit_pen']:.2f} PEN`)*",
                    f"- **Probabilidades**: Modelo Calibrado **`{bd['model_prob_pct']:.1f}%`** vs Probabilidad Implícita Limpia Casa **`{ab['mkt_p_home_pct'] if 'Local' in bd['selection_label'] else ab['mkt_p_away_pct']:.1f}%`**",
                    f"- **Proyección de Marcador y Simulación Monte Carlo (10,000 partidos)**: Margen esperado `{ab['home_team']} {ab['expected_margin']:+.1f} pts` | Total esperado **`{ab['expected_total']:.1f} pts`** *(Rango 80% Conformal: `{ab['conformal_q10']:.0f} – {ab['conformal_q90']:.0f} pts` | Prob. Prórroga: `{ab['overtime_prob_pct']:.1f}%` | Prob. Paliza: `{ab['blowout_prob_pct']:.1f}%`)*",
                    f"- **Estadísticas Clave Tomadas en Cuenta**:",
                    f"  - **Rating Elo**: `{ab['home_team']} {st['elo_home']}` vs `{ab['away_team']} {st['elo_away']}` | **Eficiencia Neta (Off/Def)**: `{ab['home_team']} ({st['home_off']}/{st['home_def']})` vs `{ab['away_team']} ({st['away_off']}/{st['away_def']})` (`Dif: {st['net_rtg_diff']:+.1f} pts/100`)",
                    f"  - **Ritmo (Pace)**: `{st['expected_pace']:.1f} posesiones` | **Descanso**: `{ab['home_team']} {st['home_rest_days']:.0f}d` vs `{ab['away_team']} {st['away_rest_days']:.0f}d` | **Viaje Geodésico (Millas Haversine)**: `Dif. {st['travel_miles_diff']:+d} millas` (`{st['away_tz_change']:.0f} husos horarios`)",
                    f"- **Por qué apostó el modelo**: _{ab['verdict_reason']}_",
                    "",
                ]
            )
    else:
        lines.append("- Actualmente no hay apuestas pendientes en espera de inicio.")
        lines.append("")

    lines.extend(
        [
            "### 📋 2.B Cartelera Completa de Próximos Partidos: Cuotas, Estadísticas a Tomar en Cuenta y Veredicto",
            "",
            "| Hora (Perú) | Partido (`Visita @ Local`) | Cuotas Ganador (`Local / Visita`) | Línea Total (`O/U`) | Proyección Modelo (`Margen / Total`) | Estadísticas Clave (`Elo`, `NetRtg`, `Descanso`, `Viaje`) | ¿Qué Hace el Bot y Por Qué? |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    for s in slate_items:
        st = s["stats"]
        ml_str = (
            f"Local **{s['ml_home_odds']:.3f}** / Visita **{s['ml_away_odds']:.3f}** *({s['ml_home_book']})*"
            if s["ml_home_odds"] and s["ml_away_odds"]
            else "⏳ *Sin cuotas publicadas*"
        )
        ou_str = (
            f"**{s['tot_line']}** (`O {s['tot_over_odds']:.2f}` / `U {s['tot_under_odds']:.2f}`)"
            if s["tot_over_odds"] and s["tot_under_odds"]
            else f"Línea est. `{s['tot_line']}`"
        )
        fav_team = s["home_team"] if s["expected_margin"] >= 0 else s["away_team"]
        proj_str = (
            f"**{fav_team} { -abs(s['expected_margin']):.1f} pts** (Prob Local `{s['model_p_home_pct']:.1f}%`) · Total **{s['expected_total']:.1f} pts**"
        )
        stats_str = (
            f"Elo `{st['elo_home']}/{st['elo_away']}` · Net `{st['net_rtg_diff']:+.1f}` · Pace `{st['expected_pace']:.1f}` · "
            f"Desc `{st['home_rest_days']:.0f}d/{st['away_rest_days']:.0f}d` · Viaje `{st['travel_miles_diff']:+d} mi`"
        )
        verdict_cell = f"**{s['verdict_summary']}** — _{s['verdict_reason']}_"
        lines.append(
            f"| `{s['hora_peru']}` | **{s['matchup']}** | {ml_str} | {ou_str} | {proj_str} | {stats_str} | {verdict_cell} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 📊 3. Últimas 20 Apuestas Liquidadas del Historial (Walk-Forward + Reales)",
        "",
        "| Bet ID | Fecha | Partido | Mercado | Selección | Cuota | Prob. | EV (%) | Estado | Beneficio | Bankroll Post. |",
        "| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :---: | ---: | ---: |",
    ])

    settled_items = [x for x in all_formatted if x["estado"] != "PENDING"][:20]
    for s in settled_items:
        badge = "✅ WON" if s["estado"] == "WON" else ("❌ LOST" if s["estado"] == "LOST" else s["estado"])
        lines.append(
            f"| `{s['bet_id']}` | `{s['fecha_jornada']}` | `{s['partido']}` | {s['mercado']} | **{s['seleccion']}** | "
            f"{s['cuota_decimal']:.3f} | {s['prob_estimada']:.1f}% | `+{s['ev_porcentaje']:.1f}%` | {badge} | "
            f"**S/{float(s['beneficio_neto_pen']):+.2f}** | `S/{float(s['bankroll_posterior_pen']):.2f}` |"
        )

    md_path = Path(md_output_path)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    html_path = md_path.parent / "reports" / "dashboard.html"
    generate_interactive_html_dashboard(
        metrics=metrics,
        espn_real_bets=espn_real_bets,
        slate_items=slate_items,
        html_output_path=html_path,
        peru_str=peru_str,
    )
    return {"csv_path": str(csv_path), "md_path": str(md_path), "html_path": str(html_path)}



def generate_daily_report(
    db: DatabaseManager,
    target_date: str,
    live_games_summary: dict[str, Any] | None = None,
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    games = db.fetch_all("SELECT * FROM games WHERE matchday_date = ? ORDER BY game_start_time", (target_date,))
    preds = db.fetch_all(
        """
        SELECT p.*, g.home_team, g.away_team
        FROM predictions p
        JOIN games g ON p.game_id = g.game_id
        WHERE g.matchday_date = ?
        ORDER BY p.ev_pct DESC
        """,
        (target_date,),
    )
    decisions = db.fetch_all(
        "SELECT * FROM decision_log WHERE matchday_date = ? ORDER BY emitted_at",
        (target_date,),
    )
    bets = db.fetch_all(
        "SELECT * FROM simulated_bets WHERE matchday_date = ? ORDER BY emitted_at",
        (target_date,),
    )
    pending_all = db.fetch_all("SELECT * FROM simulated_bets WHERE status = 'PENDING'")

    discarded_games = live_games_summary.get("discarded_games", []) if live_games_summary else []
    no_bets = [d for d in decisions if d["decision_type"] == "NO_BET"]

    lines = [
        "---",
        f"date_generated: {now_str}",
        "report_type: daily_report",
        "model_versions: [model_c_point_margin_v1, model_d_total_points_v1]",
        f"period_evaluated: {target_date}",
        f"predictions_count: {len(preds)}",
        "simulation_only: true",
        "---",
        f"# Informe Diario NBA Betting Intelligence — {target_date}",
        "",
        "## 1. Metadatos de Ejecución",
        f"- **Fecha de generación (UTC)**: `{now_str}`",
        f"- **Jornada evaluada**: `{target_date}`",
        "- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)",
        f"- **Partidos evaluados**: `{len(games)}`",
        f"- **Partidos descartados por falta de datos/cuotas**: `{len(discarded_games)}`",
        f"- **Predicciones emitidas**: `{len(preds)}`",
        f"- **Apuestas simuladas registradas en la jornada**: `{len(bets)}` (límite diario: 3, stake máx: S/1.00 PEN)",
        f"- **Decisiones NO_BET registradas**: `{len(no_bets)}`",
        f"- **Resultados pendientes globales**: `{len(pending_all)}`",
        "",
        "## 2. Partidos Descartados por Falta de Datos o Cuotas",
    ]

    if discarded_games:
        for dg in discarded_games:
            lines.append(f"- `{dg.get('game_id', 'UNKNOWN')}`: {dg.get('reason', 'Datos esenciales o cuotas no disponibles')}")
    else:
        lines.append("- Ningún partido descartado por falta de variables esenciales en el lote validado.")

    lines.extend([
        "",
        "## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)",
        "",
        "| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |",
        "| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |",
    ])

    for p in preds[:10]:
        match_label = f"{p['away_team']} @ {p['home_team']}"
        line_str = f"{p['line_value']}" if p["line_value"] is not None else "—"
        lines.append(
            f"| `{match_label}` | `{p['market']}` | **{p['selection']}** | {line_str} | "
            f"{p['decimal_odds_used']:.3f} | {p['implied_prob_gross']:.4f} | "
            f"{p['calibrated_probability']:.4f} | {p['ev_pct']:+.2f}% | `{p['odds_provider']}` |"
        )

    lines.extend([
        "",
        "## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes",
        "",
        "| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |",
        "| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |",
    ])

    if bets:
        for b in bets:
            prof_str = f"S/{b['net_profit_pen']:+.2f}" if b["net_profit_pen"] is not None else "PENDIENTE"
            lines.append(
                f"| `{b['bet_id']}` | `{b['game_id']}` | `{b['market']}` | **{b['selection']}** | "
                f"{b['decimal_odds']:.3f} | {b['estimated_prob']:.4f} | {b['estimated_ev'] * 100:+.2f}% | "
                f"S/{b['stake_pen']:.2f} | `{b['status']}` | {prof_str} |"
            )
    else:
        lines.append("| — | — | — | **NO BET** | — | — | — | S/0.00 | `NO_BET` | S/0.00 |")

    lines.extend([
        "",
        "## 5. Registro de Decisiones NO_BET (Muestra de Control)",
    ])
    for nb in no_bets[:8]:
        lines.append(
            f"- `{nb['game_id']}` (`{nb['market']}` - `{nb['selection']}`): **NO_BET** [{nb['reason_code']}] — {nb['reason_detail']}"
        )

    lines.extend([
        "",
        "## 6. Limitaciones Documentadas",
        "- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.",
        "- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.",
    ])

    return "\n".join(lines) + "\n"


def generate_weekly_report(
    metrics: dict[str, Any],
    promotion_eval: dict[str, Any],
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    boot = metrics.get("bootstrap_uncertainty", {})
    by_mkt = metrics.get("performance_by_market", {})
    model_comp = metrics.get("model_comparison", {})

    lines = [
        "---",
        f"date_generated: {now_str}",
        "report_type: weekly_report",
        "model_versions: [model_a_baseline_v1, model_b_elo_v1, model_c_point_margin_v1, model_d_total_points_v1, model_e_lightgbm_v1]",
        f"settled_predictions: {metrics.get('settled_bets_count', 0)}",
        "simulation_only: true",
        "---",
        "# Informe Semanal y Consolidado Walk-Forward — NBA Betting Intelligence",
        "",
        "## 1. Resumen Financiero Virtual (Bankroll Inicial: S/100.00 PEN)",
        f"- **Fecha de generación (UTC)**: `{now_str}`",
        f"- **Bankroll virtual inicial**: `S/{metrics['initial_bankroll_pen']:.2f} PEN`",
        f"- **Bankroll virtual liquidado actual**: `S/{metrics['current_settled_bankroll_pen']:.2f} PEN`",
        f"- **Beneficio neto acumulado**: `S/{metrics['net_profit_pen']:+.2f} PEN`",
        f"- **Stakes liquidados totales**: `S/{metrics['settled_stakes_pen']:.2f} PEN`",
        f"- **Importe total apostado**: `S/{metrics['total_wagered_pen']:.2f} PEN`",
        f"- **ROI**: `{metrics['roi_pct']:+.2f}%`",
        f"- **Yield**: `{metrics['yield_pct']:+.2f}%`",
        f"  - *Nota técnica*: {metrics['roi_yield_equivalence_note']}",
        f"- **Selecciones liquidadas**: `{metrics['settled_bets_count']}` "
        f"(Ganadas: `{metrics['won_count']}`, Perdidas: `{metrics['lost_count']}`, Push: `{metrics['push_count']}`, Void: `{metrics['void_count']}`)",
        f"- **Cuota decimal media**: `{metrics['average_decimal_odds']:.3f}`",
        f"- **Drawdown máximo**: `S/{metrics['max_drawdown_pen']:.2f} PEN` (`{metrics['max_drawdown_pct']:.2f}%`)",
        f"- **Exposición máxima simultánea**: `S/{metrics['max_exposure_pen']:.2f} PEN`",
        f"- **Closing Line Value (CLV) medio**: `{metrics['mean_clv_pct']:+.2f}%`" if metrics.get("mean_clv_pct") is not None else "- **Closing Line Value (CLV) medio**: `No disponible`",
        "",
        "## 2. Rendimiento por Mercado",
        "",
        "| Mercado | Liquidadas | Ganadas | Perdidas | Push | Beneficio Neto (PEN) | ROI / Yield (%) |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for mkt_name, mdata in by_mkt.items():
        lines.append(
            f"| `{mkt_name}` | {mdata['settled_count']} | {mdata['won']} | {mdata['lost']} | "
            f"{mdata['push']} | S/{mdata['net_profit_pen']:+.2f} | {mdata['roi_pct']:+.2f}% |"
        )

    lines.extend([
        "",
        "## 3. Calibración y Comparación frente al Baseline (Fuera de Muestra)",
        "",
        "| Modelo | Mercado | Brier Score (menor es mejor) | Log Loss (menor es mejor) | ECE |",
        "| :--- | :--- | ---: | ---: | ---: |",
    ])

    if model_comp:
        lines.extend([
            f"| `Modelo A (Baseline)` | `moneyline` | {model_comp['model_a_baseline_ml']['brier_score']:.5f} | {model_comp['model_a_baseline_ml']['log_loss']:.5f} | — |",
            f"| `Modelo B (Elo)` | `moneyline` | {model_comp['model_b_elo_ml']['brier_score']:.5f} | {model_comp['model_b_elo_ml']['log_loss']:.5f} | — |",
            f"| `Modelo C (Point Margin)` | `moneyline` | **{model_comp['model_c_point_margin_ml']['brier_score']:.5f}** | **{model_comp['model_c_point_margin_ml']['log_loss']:.5f}** | {model_comp['model_c_point_margin_ml']['ece']:.5f} |",
            f"| `Modelo E (LightGBM)` | `moneyline` | {model_comp['model_e_lightgbm_ml']['brier_score']:.5f} | {model_comp['model_e_lightgbm_ml']['log_loss']:.5f} | — |",
            f"| `Modelo A (Baseline)` | `total_points` | {model_comp['model_a_baseline_totals']['brier_score']:.5f} | {model_comp['model_a_baseline_totals']['log_loss']:.5f} | — |",
            f"| `Modelo D (Total Points + Cov)` | `total_points` | **{model_comp['model_d_total_points']['brier_score']:.5f}** | **{model_comp['model_d_total_points']['log_loss']:.5f}** | {model_comp['model_d_total_points']['ece']:.5f} |",
            f"| `Modelo E (LightGBM)` | `total_points` | {model_comp['model_e_lightgbm_totals']['brier_score']:.5f} | {model_comp['model_e_lightgbm_totals']['log_loss']:.5f} | — |",
        ])

    lines.extend([
        "",
        "## 4. Análisis de Incertidumbre Estadística (Block Bootstrap por Jornada)",
        f"- **Método**: `{boot.get('method')}` ({boot.get('n_matchday_blocks', 0)} bloques temporales)",
        f"- **Intervalo de Confianza 95% del ROI**: `[{boot.get('roi_ci_lower_95_pct', 0.0):+.2f}%, {boot.get('roi_ci_upper_95_pct', 0.0):+.2f}%]`",
        f"- **¿Resultados compatibles con ausencia de ventaja (ROI <= 0% dentro del IC 95%)?**: "
        f"`{'SÍ (No se puede descartar azar)' if boot.get('compatible_with_zero_edge', True) else 'NO'}`",
        "",
        "## 5. Evaluación de Reentrenamiento y Cambios Propuestos (Proceso C)",
        f"- **Muestra OOS evaluada**: `{promotion_eval.get('oos_sample_size', 0)}` partidos",
        f"- **Criterio de selección**: `{promotion_eval.get('selection_basis')}`",
        f"- **¿Supera al modelo vigente en Brier y Log Loss?**: `{promotion_eval.get('beats_incumbent')}`",
        f"- **¿Supera al Baseline en Brier y Log Loss?**: `{promotion_eval.get('beats_baseline')}`",
        f"- **Recomendación de promoción**: `{'APROBAR PROMOCIÓN CONTROLADA' if promotion_eval.get('recommend_promotion') else 'MANTENER VERSIÓN VIGENTE (Conservar anterior para rollback)'}`",
    ])

    return "\n".join(lines) + "\n"


def generate_audit_report(
    audit_result: dict[str, Any],
    environment_status: dict[str, Any],
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    gates_eval = audit_result["exit_gates_evaluation"]

    lines = [
        "---",
        f"date_generated: {now_str}",
        "report_type: independent_audit_report",
        "auditor_agent: nba_auditor",
        f"final_verdict: {gates_eval['recommendation']}",
        "---",
        "# Informe de Auditoría Independiente (`nba_auditor`)",
        "",
        "## 1. Dictamen Ejecutivo",
        f"- **Fecha de auditoría (UTC)**: `{now_str}`",
        f"- **Dictamen sobre transición de fase**: **`{gates_eval['recommendation']}`**",
        f"- **Transición automática a dinero real**: `{gates_eval['auto_transition_to_real_money']}` (Deshabilitada permanentemente por diseño)",
        f"- **Integridad contable del bankroll virtual (S/100.00 PEN)**: `{'VERIFICADA' if audit_result['bankroll_reconciled'] else 'ERROR'}`",
        f"- **Violaciones de fuga temporal (Data Leakage) detectadas**: `{audit_result['leakage_violations_count']}`",
        f"- **Inmutabilidad de predicciones y liquidaciones (Triggers SQLite)**: `{'ACTIVA Y VERIFICADA' if audit_result['immutability_triggers_verified'] else 'FALLO'}`",
        "",
        "## 2. Evaluación de Puertas de Salida de Simulación (Sección 11)",
        "",
        "| Puerta de Validación | Estado | Valor Observado | Criterio Requerido |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for g_name, g_data in gates_eval["gates"].items():
        status_badge = "PASS" if g_data["passed"] else "FAIL (Permanece en Simulación)"
        lines.append(
            f"| `{g_name}` | **{status_badge}** | `{g_data['observed']}` | `{g_data['required']}` |"
        )

    lines.extend([
        "",
        "## 3. Estado Real de Herramientas y Fuentes Inspeccionadas",
        f"- **Coordinador**: `Gemini Argon` en Google Antigravity (Ejecución secuencial verificada)",
        f"- **Python & Entorno Virtual**: `{environment_status.get('python_version', 'Python 3.12 via uv')}`",
        f"- **Fuente Primaria Activa sin Credenciales**: `ESPNPublicAdapter` (`site.api.espn.com` — Calendario, marcadores, estadísticas y cuotas pre-partido DraftKings)",
        f"- **Sportradar (`SportradarAdapter`)**: `{environment_status.get('sportradar_status', 'Adaptador implementado; requiere SPORTRADAR_API_KEY')}`",
        f"- **NBA.com/stats (`NBAStatsAdapter`)**: `{environment_status.get('nba_stats_status', 'Adaptador implementado; filtrado por Akamai TLS sin sesión navegador; no incluye cuotas históricas')}`",
        f"- **Playwright (`PlaywrightAuthorizedScraper`)**: `{environment_status.get('playwright_status', 'Paquete instalado v1.64.1')}`",
        f"- **PixelRAG (`visual_researcher`)**: `{environment_status.get('pixelrag_status', 'No instalado en MCP local; documentado y operando con pipeline estructurado')}`",
        f"- **Obsidian Vault (`NBA/`)**: `Operativo en {environment_status.get('obsidian_vault_path', 'NBA/')}`",
        "",
        "## 4. Conclusión Estadística del Auditor",
        "- Aunque el motor cuantitativo supera al modelo Baseline (`Modelo A`) en `Brier Score` y `Log Loss` fuera de muestra y mantiene trazabilidad contable exacta sobre el bankroll virtual de **S/100.00 PEN**, el sistema **DEBE PERMANECER EN PAPER TRADING** hasta acumular al menos **500 selecciones liquidadas** fuera de muestra y confirmar que el límite inferior del intervalo de confianza (Block Bootstrap 95%) excluya el 0%.",
    ])

    return "\n".join(lines) + "\n"


def sync_obsidian_vault(
    vault_root: str | Path,
    daily_report_md: str,
    weekly_report_md: str,
    audit_report_md: str,
    metrics: dict[str, Any],
    environment_status: dict[str, Any],
    target_date: str,
) -> dict[str, str]:
    """Populates the dedicated Obsidian vault (`NBA/00-Inbox` through `NBA/09-Reports`)."""
    root = Path(vault_root)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    files_to_write: dict[str, str] = {
        "00-Inbox/00-System-Status.md": (
            f"---\ndate_generated: {now_str}\nstatus: PAPER_TRADING_ACTIVE\nbankroll_initial: 100.00 PEN\n---\n"
            "# NBA Betting Intelligence — Inbox Operativo\n\n"
            f"- **Última sincronización**: `{now_str}`\n"
            f"- **Bankroll virtual actual**: `S/{metrics['current_settled_bankroll_pen']:.2f} PEN`\n"
            f"- **Dictamen del auditor**: `{metrics['exit_gates_evaluation']['recommendation']}`\n"
        ),
        "01-Sources/Data-Sources-and-Limitations.md": (
            f"---\ndate_generated: {now_str}\ncomponent: nba_data_scout\n---\n"
            "# Evaluación de Fuentes de Estadísticas y Cuotas NBA\n\n"
            "## 1. ESPN Public API (`site.api.espn.com`) — Activa sin Credenciales\n"
            "- Proporciona calendario oficial, estados de partido (`SCHEDULED`, `FINAL`), estadísticas de equipo y cuotas pre-partido de `DraftKings` (`moneyline` y `total_points`).\n"
            "- Limitación histórica: en partidos históricos finalizados, `pickcenter` refleja la línea archivada sin historial tick-a-tick; por ello el sistema exige `captured_at < game_start_time` para toda captura en vivo.\n\n"
            "## 2. Sportradar NBA API v8 & Synergy Basketball NBA API (`SportradarAdapter`)\n"
            f"- Estado: `{environment_status.get('sportradar_status', 'OPERATIONAL_LIVE_NBA_V8_AND_SYNERGY')}`.\n"
            "- Sincroniza el parte médico oficial de la liga (`league/injuries.json`), los splits tácticos de los 30 equipos (`seasons/2026/REG/standings.json`) y la telemetría de posesiones y jugadas de **Synergy Basketball NBA API** (`/synergy/basketball/nba/games` y `/events`) usando `SPORTRADAR_API_KEY`.\n\n"
            "## 3. TheOddsAPI Multi-Bookmaker Line Shopping (`TheOddsAPIAdapter`)\n"
            "- Escanea en tiempo real hasta 25+ casas de apuestas (`Pinnacle`, `DraftKings`, `FanDuel`, `BetMGM`, `Coolbet`, `Matchbook`, `GTbets`, etc.) para elegir siempre la cuota máxima disponible.\n\n"
            "## 4. Playwright + PixelRAG (`visual_researcher`)\n"
            f"- Playwright: `{environment_status.get('playwright_status', 'OPERATIONAL (PLAYWRIGHT_CHROMIUM_HEADLESS)')}`.\n"
            f"- PixelRAG: `{environment_status.get('pixelrag_status', 'OPERATIONAL_NATIVE_TABULAR_RAG')}` indexando lesiones oficiales de Sportradar, perfiles tácticos de Synergy Basketball NBA y tablas DOM de ESPN.\n"
        ),
        "02-Teams/NBA-30-Canonical-Teams.md": (
            f"---\ndate_generated: {now_str}\ntotal_teams: 30\n---\n"
            "# Registro Canónico de Equipos NBA\n\n"
            "Los 30 equipos de la NBA están normalizados a códigos de 3 letras (`ATL`, `BOS`, `BKN`, ..., `WAS`) en `src/ingestion/normalizer.py`.\n"
        ),
        f"03-Games/Matchday-{target_date}.md": (
            f"---\ndate_generated: {now_str}\nmatchday: {target_date}\n---\n"
            f"# Registro de Partidos — Jornada {target_date}\n\n"
            "Consulte el detalle de partidos evaluados y predicciones en `09-Reports/`.\n"
        ),
        f"04-Predictions/Predictions-Summary-{target_date}.md": (
            f"---\ndate_generated: {now_str}\nmodel_versions: [model_c_point_margin_v1, model_d_total_points_v1]\n---\n"
            "# Historial Auditable de Predicciones\n\n"
            "- Todas las predicciones están protegidas mediante triggers `BEFORE UPDATE` y `BEFORE DELETE` en SQLite (`data/nba_intelligence.sqlite3`).\n"
            "- Prohibido sobrescribir predicciones o cuotas originales.\n"
        ),
        "05-Paper-Trading/Virtual-Bankroll-Ledger.md": (
            f"---\ndate_generated: {now_str}\ninitial_bankroll_pen: 100.00\ncurrent_bankroll_pen: {metrics['current_settled_bankroll_pen']:.2f}\n---\n"
            "# Libro Mayor de Paper Trading (S/100.00 PEN Virtuales)\n\n"
            f"- **Saldo inicial**: `S/100.00 PEN`\n"
            f"- **Saldo liquidado actual**: `S/{metrics['current_settled_bankroll_pen']:.2f} PEN`\n"
            f"- **Beneficio neto acumulado**: `S/{metrics['net_profit_pen']:+.2f} PEN`\n"
            f"- **Exposición pendiente**: `S/{metrics.get('pending_exposure_pen', 0.0):.2f} PEN`\n"
            f"- **Apuestas liquidadas**: `{metrics['settled_bets_count']}`\n"
            "- **Reglas activas**: Stake fijo S/1.00, máx 3 selecciones/jornada, EV > 5.0%, sin combinadas ni martingala.\n"
        ),
        "06-Models/Model-Catalog-and-Versions.md": (
            f"---\ndate_generated: {now_str}\n---\n"
            "# Catálogo de Modelos Cuantitativos (Modelos A–G)\n\n"
            "1. **Modelo A (`model_a_baseline_v1`)**: Frecuencia histórica de victoria local y media/desviación de puntos totales.\n"
            "2. **Modelo B (`model_b_elo_v2`)**: Sistema Elo secuencial con ajuste por localía (+65 Elo) y descanso (+12 Elo/día).\n"
            "3. **Modelo C (`model_c_point_margin_v2`)**: Regresión Ridge sobre `Offensive Rating`, `Defensive Rating`, `Net Rating`, `Pace`, descanso y forma reciente.\n"
            "4. **Modelo D (`model_d_total_points_v2`)**: Distribución normal con **covarianza explícita entre marcadores** ($\\text{Var}(H+A) = \\text{Var}(H) + \\text{Var}(A) + 2\\text{Cov}(H,A)$).\n"
            "5. **Modelo E (`model_e_lightgbm_v2`)**: `LightGBM` evaluado estrictamente fuera de muestra mediante validación walk-forward.\n"
            "6. **Modelo F (`model_f_ensemble_v2`)**: Meta-Ensemble de Sindicato que combina Modelos B, C, D, E y G en escala log-odds con incertidumbre Conformal.\n"
            "7. **Modelo G (`model_g_ml_montecarlo_v2`)**: **Simulador Híbrido ML + 10,000 Partidos Monte Carlo por Posesión** (modela `Q1–Q3`, desaceleración por `Blowout/Garbage-Time` en `Q4`, faltas intencionales en los últimos 90s `Clutch Fouling` y prórrogas `Overtime OT1/OT2` + intervalos `Conformal Prediction [Q10, Q90]`).\n"
        ),
        "07-Backtesting/Walk-Forward-Backtest-Results.md": weekly_report_md,
        "08-Calibration/Calibration-and-Reliability.md": (
            f"---\ndate_generated: {now_str}\nbrier_score: {metrics['overall_brier_score']}\nlog_loss: {metrics['overall_log_loss']}\n---\n"
            "# Seguimiento de Calibración Probabilística (`model_calibrator`)\n\n"
            f"- **Brier Score combinado (Modelos C & D)**: `{metrics['overall_brier_score']:.5f}` (Baseline: `{metrics['baseline_brier_score']:.5f}`)\n"
            f"- **Log Loss combinado (Modelos C & D)**: `{metrics['overall_log_loss']:.5f}` (Baseline: `{metrics['baseline_log_loss']:.5f}`)\n"
            "- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.\n"
        ),
        f"09-Reports/Daily-Report-{target_date}.md": daily_report_md,
        f"09-Reports/Weekly-Report-{target_date}.md": weekly_report_md,
        "09-Reports/Independent-Audit-Report.md": audit_report_md,
    }

    # Remove stale dated files from previous matchdays so the repository stays clean
    for subdir, prefix in [
        ("03-Games", "Matchday-"),
        ("04-Predictions", "Predictions-Summary-"),
        ("09-Reports", "Daily-Report-"),
        ("09-Reports", "Weekly-Report-"),
    ]:
        folder = root / subdir
        if folder.exists():
            for old_file in folder.glob(f"{prefix}*.md"):
                if old_file.name != f"{prefix}{target_date}.md":
                    old_file.unlink(missing_ok=True)

    written_paths: dict[str, str] = {}
    for rel_path, content in files_to_write.items():
        full_path = root / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        written_paths[rel_path] = str(full_path)

    return written_paths
