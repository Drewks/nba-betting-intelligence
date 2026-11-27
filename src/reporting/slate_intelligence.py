"""
Computes comprehensive pre-game intelligence for the upcoming slate.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from src.config import load_config
from src.features.boxscore_features import compute_boxscore_feature_bundle
from src.ingestion.boxscores import load_boxscores
from src.models.statistical_models import EnsembleStackingModel, build_pregame_features
from src.storage.db import DatabaseManager
from src.utils.team_dictionary import format_matchup, get_team_full_name
from src.validation.validator import parse_iso_utc

logger = logging.getLogger(__name__)


def _fmt(value: Any, spec: str = ".5f", missing: str = "null") -> str:
    """Formats a possibly-missing metric (None -> 'null' / 'n/d'); never substitutes a fake value."""
    return missing if value is None else format(float(value), spec)


def compute_upcoming_slate_intelligence(db: DatabaseManager) -> list[dict[str, Any]]:
    """
    Computes pre-game odds, V9 model projections (Moneyline, Total Points, Spread, Simulation Quantiles, OT/Blowout),
    key basketball statistics (Elo, Off/Def Rating, Pace, Rest/B2B, Geodesic Travel Miles, Altitude),
    and clear Spanish explanations of why the bot placed a bet or decided NO_BET for each upcoming game.
    """
    cfg = load_config()
    risk_cfg = cfg.risk
    min_ev_pct = float(risk_cfg.min_ev_threshold) * 100.0

    all_observed_games = db.fetch_all(
        "SELECT * FROM v_observed_games ORDER BY game_start_time ASC"
    )
    boxscores: dict[str, dict[str, Any]] = {}
    try:
        boxscores = load_boxscores(db)
    except Exception as exc:
        logger.debug("Boxscores unavailable for slate intelligence fallback: %s", exc)
    bx_features = (
        compute_boxscore_feature_bundle(all_observed_games, boxscores)
        if boxscores
        else {}
    )

    all_final_games = [
        {**g, **bx_features.get(g["game_id"], {})}
        for g in all_observed_games
        if g.get("status") == "FINAL" and g.get("home_score") is not None
    ]
    model_f = EnsembleStackingModel(cfg.model.version_id)
    if all_final_games:
        fit_cutoff = (
            parse_iso_utc(str(all_final_games[-1]["game_start_time"])) + timedelta(seconds=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        model_f.fit(all_final_games, fit_cutoff)

    sched_games = db.fetch_all(
        "SELECT * FROM v_observed_games WHERE status = 'SCHEDULED' AND game_id LIKE 'ESPN_%' ORDER BY game_start_time ASC"
    )
    if not sched_games:
        sched_games = db.fetch_all(
            "SELECT * FROM v_observed_games WHERE status = 'SCHEDULED' ORDER BY game_start_time ASC LIMIT 10"
        )
    sched_games = [{**g, **bx_features.get(g["game_id"], {})} for g in sched_games]

    slate_items: list[dict[str, Any]] = []
    for g in sched_games:
        gid = g["game_id"]
        ht = g["home_team"]
        at = g["away_team"]
        feats = build_pregame_features(g, all_final_games, market="total_points")
        pred_ml = model_f.predict_moneyline(g, all_final_games)
        base_line = round(feats.get("structural_total", 228.5) * 2) / 2
        pred_tot = model_f.predict_total_points(g, all_final_games, line_value=base_line)

        ml_odds_rows = db.fetch_all(
            """
            SELECT provider, selection, decimal_odds, counterpart_decimal_odds, captured_at
            FROM v_observed_odds_snapshots
            WHERE game_id = ? AND market = 'moneyline' AND captured_at < ?
            ORDER BY captured_at DESC
            """,
            (gid, g["game_start_time"]),
        )
        tot_odds_rows = db.fetch_all(
            """
            SELECT provider, selection, line_value, decimal_odds, counterpart_decimal_odds, captured_at
            FROM v_observed_odds_snapshots
            WHERE game_id = ? AND market = 'total_points' AND captured_at < ?
            ORDER BY captured_at DESC
            """,
            (gid, g["game_start_time"]),
        )

        h_odds_list: list[float] = []
        a_odds_list: list[float] = []
        for r in ml_odds_rows:
            sel = str(r.get("selection") or "").upper()
            d_odd = float(r["decimal_odds"]) if r.get("decimal_odds") else None
            c_odd = float(r["counterpart_decimal_odds"]) if r.get("counterpart_decimal_odds") else None
            if sel == "HOME":
                if d_odd and d_odd > 1.0:
                    h_odds_list.append(d_odd)
                if c_odd and c_odd > 1.0:
                    a_odds_list.append(c_odd)
            elif sel == "AWAY":
                if d_odd and d_odd > 1.0:
                    a_odds_list.append(d_odd)
                if c_odd and c_odd > 1.0:
                    h_odds_list.append(c_odd)

        best_h_odds = max(h_odds_list, default=None)
        best_a_odds = max(a_odds_list, default=None)

        over_odds_list: list[float] = []
        under_odds_list: list[float] = []
        for r in tot_odds_rows:
            sel = str(r.get("selection") or "").upper()
            d_odd = float(r["decimal_odds"]) if r.get("decimal_odds") else None
            c_odd = float(r["counterpart_decimal_odds"]) if r.get("counterpart_decimal_odds") else None
            if sel == "OVER":
                if d_odd and d_odd > 1.0:
                    over_odds_list.append(d_odd)
                if c_odd and c_odd > 1.0:
                    under_odds_list.append(c_odd)
            elif sel == "UNDER":
                if d_odd and d_odd > 1.0:
                    under_odds_list.append(d_odd)
                if c_odd and c_odd > 1.0:
                    over_odds_list.append(c_odd)

        best_over_odds = max(over_odds_list, default=None)
        best_under_odds = max(under_odds_list, default=None)

        active_bet = db.fetch_one(
            """
            SELECT b.*, p.odds_provider
            FROM v_observed_simulated_bets b
            LEFT JOIN predictions p ON b.prediction_id = p.prediction_id
            WHERE b.game_id = ? AND b.status = 'PENDING'
            LIMIT 1
            """,
            (gid,),
        )

        dec_rows = db.fetch_all(
            "SELECT * FROM decision_log WHERE game_id = ? ORDER BY emitted_at DESC",
            (gid,),
        )
        no_bet_reasons: list[str] = []
        for d in dec_rows:
            d_type = d.get("decision_type") or d.get("decision")
            if d_type == "NO_BET":
                detail = str(d.get("reason_detail") or "")
                no_bet_reasons.append(f"{d['selection']}: {detail}")

        verdict_status = "PENDING_BET" if active_bet else "NO_BET"
        if active_bet:
            mkt = active_bet["market"]
            sel = active_bet["selection"]
            raw_ev = (
                active_bet["ev_pct"]
                if active_bet.get("ev_pct") is not None
                else active_bet.get("estimated_ev", 0.0)
            )
            ev = float(raw_ev) * 100.0
            stake = float(active_bet["stake_pen"])
            odds = float(active_bet["decimal_odds"])
            raw_prob = (
                active_bet["model_probability"]
                if active_bet.get("model_probability") is not None
                else active_bet.get("estimated_prob", 0.5)
            )
            prob = float(raw_prob) * 100.0
            book = str(
                active_bet.get("bookmaker")
                or active_bet.get("odds_provider")
                or "DraftKings"
            )

            if mkt == "moneyline":
                sel_label = f"Victoria {get_team_full_name(ht)}" if sel == "HOME" else f"Victoria {get_team_full_name(at)}"
            else:
                sel_label = f"Más de {active_bet.get('line_value', base_line)} pts (OVER)" if sel == "OVER" else f"Menos de {active_bet.get('line_value', base_line)} pts (UNDER)"

            verdict_summary = f"APUESTA DETECTADA: {sel_label} @ {odds:.2f} en {book}"
            verdict_reason = (
                f"El modelo proyecta una probabilidad de éxito del {prob:.1f}% frente a una cuota de {odds:.2f} "
                f"(valor esperado positivo del +{ev:.1f}% con stake calculado de S/ {stake:.2f} PEN)."
            )
            fair_odds = round(1.0 / (prob / 100.0), 2)
            pot_profit = round(stake * (odds - 1.0), 2)
            bet_ev = round(ev, 1)
            bet_stake = stake
            bet_odds = odds
            bet_prob = round(prob, 1)
            bet_book = book
        else:
            verdict_summary = "SIN APUESTA (NO_BET)"
            if no_bet_reasons:
                verdict_reason = "; ".join(no_bet_reasons[:2])
            else:
                verdict_reason = (
                    f"Las cuotas actuales de las casas no ofrecen suficiente margen de valor esperado "
                    f"(>= {min_ev_pct:.1f}% EV) para justificar una entrada segura."
                )
            sel_label = None
            fair_odds = None
            pot_profit = None
            bet_ev = None
            bet_stake = None
            bet_odds = None
            bet_prob = None
            bet_book = None

        h_ev = round((pred_ml["p_home"] * best_h_odds - 1.0) * 100, 1) if best_h_odds else None
        a_ev = round((pred_ml["p_away"] * best_a_odds - 1.0) * 100, 1) if best_a_odds else None
        over_ev = round((pred_tot["p_over"] * best_over_odds - 1.0) * 100, 1) if best_over_odds else None
        under_ev = round((pred_tot["p_under"] * best_under_odds - 1.0) * 100, 1) if best_under_odds else None

        slate_items.append(
            {
                "game_id": gid,
                "game_start_time": g["game_start_time"],
                "matchup_display": format_matchup(ht, at),
                "home_team_code": ht,
                "away_team_code": at,
                "home_team_name": get_team_full_name(ht),
                "away_team_name": get_team_full_name(at),
                "odds": {
                    "home_odds": best_h_odds,
                    "away_odds": best_a_odds,
                    "over_odds": best_over_odds,
                    "under_odds": best_under_odds,
                    "total_line": base_line,
                },
                "projections": {
                    "p_home_pct": round(pred_ml["p_home"] * 100, 1),
                    "p_away_pct": round(pred_ml["p_away"] * 100, 1),
                    "expected_margin": pred_ml["expected_margin"],
                    "margin_std": pred_ml.get("margin_std", 11.5),
                    "simulation_q10_margin": pred_ml.get("simulation_q10_margin", -15.0),
                    "simulation_q90_margin": pred_ml.get("simulation_q90_margin", 15.0),
                    "is_conformal": 0.0,
                    "expected_total": pred_tot["expected_total"],
                    "total_std": pred_tot.get("total_std_with_covariance", 18.2),
                    "p_over_pct": round(pred_tot["p_over"] * 100, 1),
                    "p_under_pct": round(pred_tot["p_under"] * 100, 1),
                    "simulation_q10_total": pred_tot.get("simulation_q10_total", 205.0),
                    "simulation_q90_total": pred_tot.get("simulation_q90_total", 252.0),
                    "overtime_prob_pct": round(pred_ml.get("overtime_prob", 0.055) * 100, 1),
                    "blowout_prob_pct": round(pred_ml.get("blowout_prob", 0.12) * 100, 1),
                    "home_ev_pct": h_ev,
                    "away_ev_pct": a_ev,
                    "over_ev_pct": over_ev,
                    "under_ev_pct": under_ev,
                },
                "basketball_context": {
                    "home_elo": round(float(feats.get("elo_home", 1500.0)), 1),
                    "away_elo": round(float(feats.get("elo_away", 1500.0)), 1),
                    "elo_diff": round(float(feats.get("elo_diff", 0.0)), 1),
                    "home_off_rtg": round(float(feats.get("home_off_rtg", 112.0)), 1),
                    "home_def_rtg": round(float(feats.get("home_def_rtg", 112.0)), 1),
                    "away_off_rtg": round(float(feats.get("away_off_rtg", 112.0)), 1),
                    "away_def_rtg": round(float(feats.get("away_def_rtg", 112.0)), 1),
                    "net_rtg_diff": round(float(feats.get("net_rtg_diff", 0.0)), 1),
                    "expected_pace": round(float(feats.get("expected_pace", 99.5)), 1),
                    "rest_diff": int(feats.get("rest_diff", 0)),
                    "b2b_advantage": int(feats.get("b2b_advantage", 0)),
                    "travel_miles_diff": round(float(feats.get("travel_miles_diff", 0.0)), 0),
                    "altitude_advantage": round(float(feats.get("altitude_advantage", 0.0)), 1),
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


def generate_slate_intelligence_markdown(db: DatabaseManager) -> str:
    """Renders the upcoming slate intelligence table in Markdown using active config thresholds."""
    slate_items = compute_upcoming_slate_intelligence(db)
    lines = [
        "### 📋 Cartelera Completa de Próximos Partidos: Cuotas, Estadísticas a Tomar en Cuenta y Veredicto",
        "",
        "| Hora (UTC) | Partido | Cuotas Ganador (`Local / Visita`) | Proyección Modelo (`Margen / Total`) | Estadísticas Clave (`Elo`, `NetRtg`, `Descanso`) | ¿Qué Hace el Bot y Por Qué? |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for s in slate_items:
        st = s["basketball_context"]
        proj = s["projections"]
        odds_dict = s["odds"]
        ml_str = (
            f"Local **{odds_dict['home_odds']:.3f}** / Visita **{odds_dict['away_odds']:.3f}**"
            if odds_dict.get("home_odds") and odds_dict.get("away_odds")
            else "⏳ *Sin cuotas publicadas*"
        )
        proj_str = (
            f"**Margen {proj['expected_margin']:+.1f} pts** (Local `{proj['p_home_pct']:.1f}%`) · Total **{proj['expected_total']:.1f} pts**"
        )
        stats_str = (
            f"Elo `{st['home_elo']}/{st['away_elo']}` · Net `{st['net_rtg_diff']:+.1f}` · Pace `{st['expected_pace']:.1f}` · "
            f"Desc `{st['rest_diff']:+d}d`"
        )
        verdict_cell = f"**{s['verdict_summary']}** — _{s['verdict_reason']}_"
        lines.append(
            f"| `{s['game_start_time']}` | **{s['matchup_display']}** | {ml_str} | {proj_str} | {stats_str} | {verdict_cell} |"
        )
    return "\n".join(lines)

