"""
Execution helpers for `PaperTradingEngine` (`src/paper_trading/execution_helpers.py`).

Handles decision logging and immutable bet + bankroll ledger reservation so
`src/paper_trading/engine.py` remains focused and concise.
"""

from __future__ import annotations

from typing import Any
import uuid

from src.config import ExecutionConfig, load_config
from src.prediction.ev_calculator import optimize_simultaneous_kelly_portfolio


def record_decision_entry(
    db: Any,
    game_id: str,
    matchday_date: str,
    market: str,
    selection: str,
    decision_type: str,
    reason_code: str,
    reason_detail: str,
    ev_pct: float,
    emitted_at: str,
    model_version_id: str,
) -> dict[str, Any]:
    """Inserts an immutable entry into `decision_log` and returns its structured record."""
    decision_id = f"DEC_{uuid.uuid4().hex[:10].upper()}"
    db.execute_insert(
        """
        INSERT INTO decision_log (
            decision_id, game_id, matchday_date, market, selection,
            decision_type, reason_code, reason_detail, ev_pct, emitted_at, model_version_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision_id,
            game_id,
            matchday_date,
            market,
            selection,
            decision_type,
            reason_code,
            reason_detail,
            ev_pct,
            emitted_at,
            model_version_id,
        ),
    )
    return {
        "decision_id": decision_id,
        "game_id": game_id,
        "market": market,
        "selection": selection,
        "decision_type": decision_type,
        "reason_code": reason_code,
        "reason_detail": reason_detail,
        "ev_pct": ev_pct,
    }


def reserve_and_insert_simulated_bet(
    db: Any,
    *,
    state: dict[str, float],
    prediction_id: str | None,
    game_id: str,
    matchday_date: str,
    market: str,
    selection: str,
    line_value: float | None,
    dec_odds: float,
    cal_prob: float,
    ev_unit: float,
    ev_pct: float,
    bet_stake: float,
    emitted_at: str,
    model_version_id: str,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Persists a new PENDING simulated bet, reserves ledger exposure, and logs `BET_PLACED`."""
    bet_id = f"BET_{matchday_date.replace('-', '')}_{uuid.uuid4().hex[:8].upper()}"
    curr_br = float(state["settled_bankroll_pen"])
    curr_exp = round(float(state["pending_exposure_pen"]) + bet_stake, 4)
    curr_avail = round(curr_br - curr_exp, 4)

    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO simulated_bets (
                bet_id, prediction_id, game_id, matchday_date, market, selection,
                line_value, decimal_odds, estimated_prob, estimated_ev, stake_pen,
                emitted_at, model_version_id, status, net_profit_pen,
                bankroll_after_pen, actual_result_summary, settled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', NULL, NULL, NULL, NULL)
            """,
            (
                bet_id,
                prediction_id,
                game_id,
                matchday_date,
                market,
                selection,
                line_value,
                dec_odds,
                float(cal_prob),
                ev_unit,
                bet_stake,
                emitted_at,
                model_version_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO bankroll_ledger (
                timestamp, event_type, reference_bet_id, amount_delta_pen,
                settled_bankroll_pen, pending_exposure_pen, available_balance_pen
            ) VALUES (?, 'BET_RESERVED', ?, 0.0, ?, ?, ?)
            """,
            (emitted_at, bet_id, curr_br, curr_exp, curr_avail),
        )

    new_state = {
        "settled_bankroll_pen": curr_br,
        "pending_exposure_pen": curr_exp,
        "available_balance_pen": curr_avail,
    }
    record_decision_entry(
        db,
        game_id,
        matchday_date,
        market,
        selection,
        "BET_PLACED",
        "QUALIFIED_POSITIVE_EV",
        f"Placed virtual bet {bet_id} with EV {ev_pct:.2f}% and stake S/{bet_stake:.2f}",
        ev_pct,
        emitted_at,
        model_version_id,
    )
    bet_summary = {
        "bet_id": bet_id,
        "prediction_id": prediction_id,
        "game_id": game_id,
        "matchday_date": matchday_date,
        "market": market,
        "selection": selection,
        "line_value": line_value,
        "decimal_odds": dec_odds,
        "estimated_prob": float(cal_prob),
        "estimated_ev": ev_unit,
        "stake_pen": bet_stake,
        "status": "PENDING",
    }
    return new_state, bet_summary



def sort_and_prepare_candidates(
    candidate_predictions: list[dict[str, Any]],
    *,
    dynamic_conviction_staking: bool,
    proposed_stake_pen: float | None,
    min_ev_threshold: float,
    max_stake_pen: float,
    get_bankroll_fn: Any,
) -> list[dict[str, Any]]:
    """Sorts matchday candidates and optionally runs simultaneous Kelly optimization."""
    if not dynamic_conviction_staking:
        return sorted(candidate_predictions, key=lambda c: float(c.get("ev_unit", -999.0)), reverse=True)

    sorted_candidates = sorted(
        candidate_predictions,
        key=lambda c: float(c.get("ev_unit", -999.0)) * ((float(c.get("calibrated_probability") or 0.50) / 0.55) ** 2.0),
        reverse=True,
    )
    if proposed_stake_pen is None:
        qualifying = [c for c in sorted_candidates if float(c.get("ev_unit", -1.0)) > min_ev_threshold]
        if len(qualifying) >= 2:
            curr_br = get_bankroll_fn()["settled_bankroll_pen"]
            max_indiv = min(0.06, max_stake_pen / max(1.0, curr_br))
            opt_picks = optimize_simultaneous_kelly_portfolio(
                qualifying,
                bankroll_pen=curr_br,
                max_total_exposure_fraction=0.15,
                max_individual_fraction=max_indiv,
            )
            pred_to_opt = {c["prediction_id"]: c for c in opt_picks if "prediction_id" in c}
            for c in sorted_candidates:
                if c.get("prediction_id") in pred_to_opt:
                    c["kelly_recommended_stake_pen"] = pred_to_opt[c["prediction_id"]]["kelly_recommended_stake_pen"]
                    c["kelly_optimal_fraction"] = pred_to_opt[c["prediction_id"]]["kelly_optimal_fraction"]
    return sorted_candidates


def check_candidate_edge_and_model_guards(
    cand: dict[str, Any],
    *,
    min_ev_threshold: float,
    execution_cfg: ExecutionConfig | None = None,
) -> tuple[str, str] | None:
    """Evaluates pre-duplicate model, odds, disagreement, steam, conformal, and meta-label gates."""
    ex_cfg = execution_cfg or load_config().execution
    game_id = cand["game_id"]
    market = cand["market"]
    dec_odds = float(cand.get("decimal_odds_used") or 0.0)
    cal_prob = cand.get("calibrated_probability")
    ev_unit = float(cand.get("ev_unit", -1.0))
    ev_pct = float(cand.get("ev_pct", -100.0))

    if cal_prob is None or dec_odds <= 1.0:
        return ("INVALID_ODDS_OR_PROB", "Missing calibrated probability or invalid decimal odds")
    if ev_unit <= min_ev_threshold:
        return ("EV_BELOW_THRESHOLD", f"EV {ev_pct:.2f}% <= threshold {min_ev_threshold * 100:.2f}%")
    if str(game_id).startswith("ESPN_") and ev_unit > ex_cfg.max_plausible_ev_unit:
        return (
            "UNVERIFIED_INJURY_OR_LINEUP_OUTLIER",
            f"Extreme EV ({ev_pct:.2f}% > {ex_cfg.max_plausible_ev_unit * 100:.1f}%) indicates likely star injury/rest not in team-level features; skipped.",
        )

    disagreement = cand.get("model_market_disagreement")
    max_gap = float(cand.get("max_model_market_disagreement") or 0.15)
    if disagreement is not None and abs(float(disagreement)) > max_gap:
        return (
            "MODEL_MARKET_DISAGREEMENT",
            f"Model differs from de-vigged market by {abs(float(disagreement)) * 100:.1f} pts (> {max_gap * 100:.0f}); likely missing information, skipped.",
        )

    ml_max_odds = cand.get("moneyline_max_odds")
    if ml_max_odds is None:
        try:
            ml_max_odds = load_config().model.moneyline_max_odds
        except Exception:
            ml_max_odds = None
    if market == "moneyline" and ml_max_odds is not None and dec_odds > float(ml_max_odds):
        return (
            "EXCESSIVE_LONGSHOT_VARIANCE",
            f"Moneyline odds {dec_odds:.2f} (> {float(ml_max_odds):.2f} max cap); skipped to protect bankroll and CLV.",
        )
    if dec_odds > ex_cfg.longshot_odds_threshold and ev_pct < ex_cfg.longshot_min_ev_pct:
        return (
            "EXCESSIVE_LONGSHOT_VARIANCE",
            f"Longshot odds {dec_odds:.2f} (> {ex_cfg.longshot_odds_threshold:.2f}) require EV >= {ex_cfg.longshot_min_ev_pct:.1f}% (observed: {ev_pct:.2f}%); skipped to protect bankroll.",
        )

    steam_delta = float(cand.get("steam_delta") or 0.0)
    if steam_delta <= ex_cfg.adverse_steam_threshold:
        return (
            "ADVERSE_SHARP_STEAM_MOVE",
            f"Market fair probability moved {steam_delta * 100:.2f}% against this side since opening (<= {ex_cfg.adverse_steam_threshold * 100:.1f}%); skipped.",
        )

    conf_w = cand.get("conformal_width")
    if conf_w is not None and float(conf_w) > ex_cfg.max_conformal_width:
        return (
            "CONFORMAL_UNCERTAINTY_TOO_WIDE",
            f"Venn-Abers conformal prediction interval width {float(conf_w):.3f} > {ex_cfg.max_conformal_width:.2f}; epistemic uncertainty too high.",
        )

    if cand.get("meta_label_pass") is False:
        return (
            cand.get("meta_label_reason") or "NEGATIVE_EXPECTED_CLV",
            f"Meta-labeling model predicts negative Closing Line Value (P(CLV > 0) = {float(cand.get('p_positive_clv') or 0.0):.2f}); skipped to protect edge.",
        )
    return None


def check_candidate_caps_and_duplicates(
    db: Any,
    cand: dict[str, Any],
    *,
    day_count: int,
    day_totals_count: int,
    day_ml_count: int,
    selected_games: set[str],
    selected_game_markets: set[tuple[str, str]],
    single_bet_per_game: bool,
    max_selections_per_matchday: int,
    hybrid_allocation_enabled: bool,
    max_moneyline_per_matchday: int,
    max_totals_per_matchday: int,
) -> tuple[str, str] | None:
    """Checks DB duplicates, per-game anti-correlation limits, matchday cap, and hybrid allocation."""
    game_id = cand["game_id"]
    market = cand["market"]
    selection = cand["selection"]
    line_value = cand.get("line_value")

    dup = db.fetch_one(
        """
        SELECT bet_id FROM simulated_bets
        WHERE game_id = ? AND market = ? AND selection = ?
          AND COALESCE(line_value, -9999) = COALESCE(?, -9999)
        """,
        (game_id, market, selection, line_value),
    )
    if dup:
        return ("DUPLICATE_SELECTION", f"Duplicate selection already recorded ({dup['bet_id']})")

    if single_bet_per_game:
        if game_id in selected_games:
            return (
                "CORRELATED_GAME_EXPOSURE",
                f"Another selection for game {game_id} was already placed in this matchday.",
            )
        existing_pending = db.fetch_one(
            "SELECT bet_id, market, selection FROM simulated_bets WHERE game_id = ? AND status = 'PENDING'",
            (game_id,),
        )
        if existing_pending:
            return (
                "PENDING_BET_IN_SAME_GAME",
                f"Game already has an active pending bet ({existing_pending['bet_id']}: "
                f"{existing_pending['market']} {existing_pending['selection']})",
            )
    elif (game_id, market) in selected_game_markets:
        return ("MARKET_ALREADY_SELECTED", "Another selection in the same game and market was already placed")

    if day_count >= max_selections_per_matchday:
        return ("MATCHDAY_CAP_REACHED", f"Matchday cap of {max_selections_per_matchday} selections reached")

    if hybrid_allocation_enabled:
        if market == "moneyline" and day_ml_count >= max_moneyline_per_matchday:
            return (
                "MARKET_CAP_REACHED",
                f"Matchday cap of {max_moneyline_per_matchday} moneyline pick(s) reached (70/30 hybrid allocation)",
            )
        if market == "total_points" and day_totals_count >= max_totals_per_matchday:
            if day_ml_count > 0 or day_count >= max_selections_per_matchday:
                return (
                    "MARKET_CAP_REACHED",
                    f"Matchday cap of {max_totals_per_matchday} total_points pick(s) reached (70/30 hybrid allocation)",
                )
    return None
