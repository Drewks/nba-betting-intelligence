"""
Pure settlement outcome calculation for paper trading bets and player props.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any

from src.paper_trading.exceptions import DoubleSettlementError, RiskLimitError
from src.validation.validator import DataValidationError, TemporalLeakageError, parse_iso_utc


def calculate_settlement_outcome(
    market: str,
    selection: str,
    line_value: float | None,
    decimal_odds: float,
    stake_pen: float,
    game_status: str,
    home_score: int | None,
    away_score: int | None,
) -> tuple[str, float, str]:
    """
    Pure settlement formula (Section 8):
    - WON:  net_profit = S * (O - 1)
    - LOST: net_profit = -S
    - PUSH / VOID: net_profit = 0.0
    Returns (status, net_profit_pen, result_summary).
    """
    if game_status in ("POSTPONED", "CANCELLED"):
        return "VOID", 0.0, f"Game {game_status}"

    if game_status != "FINAL" or home_score is None or away_score is None:
        raise DataValidationError(
            f"Cannot settle bet before game is FINAL with verified scores (status={game_status})"
        )

    summary = f"HOME {home_score} - AWAY {away_score} (Total: {home_score + away_score})"

    if market == "moneyline":
        if home_score == away_score:
            return "PUSH", 0.0, summary
        home_won = home_score > away_score
        if (selection == "HOME" and home_won) or (selection == "AWAY" and not home_won):
            net_profit = round(stake_pen * (decimal_odds - 1.0), 4)
            return "WON", net_profit, summary
        return "LOST", round(-stake_pen, 4), summary

    if market == "total_points":
        if line_value is None:
            raise DataValidationError("total_points settlement requires line_value")
        total_pts = float(home_score + away_score)
        if abs(total_pts - float(line_value)) < 1e-6:
            return "PUSH", 0.0, summary
        over_hit = total_pts > float(line_value)
        if (selection == "OVER" and over_hit) or (selection == "UNDER" and not over_hit):
            net_profit = round(stake_pen * (decimal_odds - 1.0), 4)
            return "WON", net_profit, summary
        return "LOST", round(-stake_pen, 4), summary

    if market == "spread":
        if line_value is None:
            raise DataValidationError("spread settlement requires line_value")
        side_margin = float(home_score - away_score) if selection == "HOME" else float(away_score - home_score)
        adjusted_margin = side_margin + float(line_value)
        if abs(adjusted_margin) < 1e-6:
            return "PUSH", 0.0, summary
        if adjusted_margin > 0.0:
            net_profit = round(stake_pen * (decimal_odds - 1.0), 4)
            return "WON", net_profit, summary
        return "LOST", round(-stake_pen, 4), summary

    raise DataValidationError(f"Unsupported market for settlement: {market!r}")


def calculate_prop_settlement_outcome(
    prop: dict[str, Any],
    actual_stat: float | None,
    game_status: str,
    home_score: int | None = None,
    away_score: int | None = None,
) -> tuple[str, float, float, str]:
    """
    Calculates settlement outcome for an individual player prop or SGP pick.
    Returns (outcome_status, net_profit, stat_recorded, summary).
    """
    stake_pen = float(prop.get("stake_pen") or prop.get("kelly_stake_pen") or 1.0)
    decimal_odds = float(prop["decimal_odds"])
    line_val = float(prop["line_value"])
    cat = str(prop["prop_category"]).upper()
    sel = str(prop["selection"]).upper()

    if game_status in ("POSTPONED", "CANCELLED", "VOID"):
        return "VOID", 0.0, 0.0, f"Prop {game_status}"

    if game_status != "FINAL":
        raise DataValidationError(f"Cannot settle prop before game is FINAL (status={game_status})")

    if cat == "SGP":
        if actual_stat is not None:
            is_won = float(actual_stat) >= 1.0
            stat_recorded = float(actual_stat)
        else:
            if home_score is None or away_score is None:
                raise DataValidationError("SGP settlement requires game scores or explicit actual_stat")
            raise DataValidationError("SGP settlement requires actual_stat indicator (1.0 = hit, 0.0 = miss)")

        if is_won:
            outcome_status = "WON"
            net_profit = round(stake_pen * (decimal_odds - 1.0), 4)
            summary = f"SGP Acertada: Combinada correlacionada ganadora (+S/{net_profit:.2f} PEN)"
        else:
            outcome_status = "LOST"
            net_profit = round(-stake_pen, 4)
            summary = f"SGP Fallada: Al menos una pierna no se cumplió (-S/{stake_pen:.2f} PEN)"
        return outcome_status, net_profit, stat_recorded, summary

    if actual_stat is None:
        raise DataValidationError(f"Prop {cat} settlement requires actual_stat value")
    stat_recorded = float(actual_stat)

    if sel == "OVER":
        if stat_recorded > line_val:
            outcome_status = "WON"
            net_profit = round(stake_pen * (decimal_odds - 1.0), 4)
            summary = f"{prop['player_name']} {cat} {stat_recorded:.1f} > {line_val:.1f} (GANADA +S/{net_profit:.2f} PEN)"
        elif stat_recorded < line_val:
            outcome_status = "LOST"
            net_profit = round(-stake_pen, 4)
            summary = f"{prop['player_name']} {cat} {stat_recorded:.1f} < {line_val:.1f} (PERDIDA -S/{stake_pen:.2f} PEN)"
        else:
            outcome_status = "PUSH"
            net_profit = 0.0
            summary = f"{prop['player_name']} {cat} {stat_recorded:.1f} == {line_val:.1f} (EMPATE / DEVUELTA)"
    elif sel == "UNDER":
        if stat_recorded < line_val:
            outcome_status = "WON"
            net_profit = round(stake_pen * (decimal_odds - 1.0), 4)
            summary = f"{prop['player_name']} {cat} {stat_recorded:.1f} < {line_val:.1f} (GANADA +S/{net_profit:.2f} PEN)"
        elif stat_recorded > line_val:
            outcome_status = "LOST"
            net_profit = round(-stake_pen, 4)
            summary = f"{prop['player_name']} {cat} {stat_recorded:.1f} > {line_val:.1f} (PERDIDA -S/{stake_pen:.2f} PEN)"
        else:
            outcome_status = "PUSH"
            net_profit = 0.0
            summary = f"{prop['player_name']} {cat} {stat_recorded:.1f} == {line_val:.1f} (EMPATE / DEVUELTA)"
    else:
        raise DataValidationError(f"Unsupported prop selection: {sel}")

    return outcome_status, net_profit, stat_recorded, summary


def settle_simulated_bet(
    db: Any,
    get_bankroll_state_fn: Any,
    bet_id: str,
    game_status: str,
    home_score: int | None,
    away_score: int | None,
    settled_at: str | None = None,
) -> dict[str, Any]:
    """
    Settles a single PENDING simulated bet after verifying temporal order and preventing double settlement.
    """
    bet = db.fetch_one("SELECT * FROM simulated_bets WHERE bet_id = ?", (bet_id,))
    if not bet:
        raise DataValidationError(f"Bet ID {bet_id!r} does not exist")
    if bet["status"] != "PENDING":
        raise DoubleSettlementError(
            f"Bet {bet_id} has already been settled with status '{bet['status']}' and cannot be settled twice."
        )
    game = db.fetch_one("SELECT * FROM games WHERE game_id = ?", (bet["game_id"],))
    if not game:
        raise DataValidationError(f"Associated game {bet['game_id']} not found")

    settlement_ts = settled_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if parse_iso_utc(settlement_ts) <= parse_iso_utc(game["game_start_time"]):
        raise TemporalLeakageError(
            f"Cannot settle bet {bet_id} at {settlement_ts} before or at game_start_time ({game['game_start_time']})"
        )

    outcome_status, net_profit, result_summary = calculate_settlement_outcome(
        market=bet["market"],
        selection=bet["selection"],
        line_value=bet["line_value"],
        decimal_odds=float(bet["decimal_odds"]),
        stake_pen=float(bet["stake_pen"]),
        game_status=game_status,
        home_score=home_score,
        away_score=away_score,
    )

    pre_state = get_bankroll_state_fn()
    new_settled_bankroll = round(pre_state["settled_bankroll_pen"] + net_profit, 4)
    if new_settled_bankroll < 0.0:
        raise RiskLimitError(f"Negative bankroll violation detected: S/{new_settled_bankroll:.2f}")

    new_pending_exposure = round(max(0.0, pre_state["pending_exposure_pen"] - float(bet["stake_pen"])), 4)
    new_available = round(new_settled_bankroll - new_pending_exposure, 4)

    try:
        with db.connect() as conn:
            conn.execute(
                """
                UPDATE simulated_bets
                SET status = ?, net_profit_pen = ?, bankroll_after_pen = ?,
                    actual_result_summary = ?, settled_at = ?
                WHERE bet_id = ?
                """,
                (outcome_status, net_profit, new_settled_bankroll, result_summary, settlement_ts, bet_id),
            )
            conn.execute(
                """
                INSERT INTO bankroll_ledger (
                    timestamp, event_type, reference_bet_id, amount_delta_pen,
                    settled_bankroll_pen, pending_exposure_pen, available_balance_pen
                ) VALUES (?, 'BET_SETTLED', ?, ?, ?, ?, ?)
                """,
                (settlement_ts, bet_id, net_profit, new_settled_bankroll, new_pending_exposure, new_available),
            )
    except sqlite3.IntegrityError as exc:
        raise DoubleSettlementError(f"Database trigger blocked settlement on {bet_id}: {exc}") from exc

    return {
        "bet_id": bet_id,
        "status": outcome_status,
        "net_profit_pen": net_profit,
        "bankroll_after_pen": new_settled_bankroll,
        "actual_result_summary": result_summary,
        "settled_at": settlement_ts,
    }



def persist_closing_lines_for_games(
    db: Any,
    as_of_utc: str | None = None,
    *,
    include_player_props: bool | None = None,
) -> int:
    """
    Promotes the latest pre-tipoff OBSERVED odds capture to a formal closing line
    (is_closing_line = 1) for real games that are FINAL or within 45 minutes of tip-off.

    Partitions by `(provider, market, selection)` so only the actual latest pre-tipoff main
    line per book/market/side is marked as a closing line (never stale earlier line numbers).
    Skips `player_prop` rows when player-prop betting is disabled in config unless explicitly enabled.
    """
    if include_player_props is None:
        try:
            from src.config import load_config

            allow_props = bool(load_config().risk.allow_player_props_betting)
        except Exception:
            allow_props = False
    else:
        allow_props = bool(include_player_props)
    market_filter = "" if allow_props else "AND o.market <> 'player_prop'"

    now_dt = parse_iso_utc(as_of_utc) if as_of_utc else datetime.now(timezone.utc)
    cutoff_str = (now_dt + timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
    games_needing_close = db.fetch_all(
        f"""
        SELECT g.game_id, g.game_start_time, g.status
        FROM games g
        WHERE g.game_id NOT LIKE 'SYN%'
          AND (g.status IN ('FINAL', 'POSTPONED', 'CANCELLED') OR datetime(g.game_start_time) <= datetime(?))
          AND EXISTS (
              SELECT 1 FROM v_observed_odds_snapshots o
              WHERE o.game_id = g.game_id
                AND o.is_closing_line = 0
                {market_filter}
                AND datetime(o.captured_at) <= datetime(g.game_start_time)
          )
        """,
        (cutoff_str,),
    )
    inserted_count = 0
    with db.connect() as conn:
        for g in games_needing_close:
            gid = g["game_id"]
            start_ts = g["game_start_time"]
            snapshots = conn.execute(
                f"""
                SELECT *
                FROM (
                    SELECT o.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY o.provider, o.market, o.selection
                               ORDER BY datetime(o.captured_at) DESC, o.captured_at DESC
                           ) AS rn
                    FROM v_observed_odds_snapshots o
                    WHERE o.game_id = ?
                      AND o.is_closing_line = 0
                      {market_filter}
                      AND datetime(o.captured_at) <= datetime(?)
                )
                WHERE rn = 1
                """,
                (gid, start_ts),
            ).fetchall()

            for s in snapshots:
                close_id = f"{s['odds_id']}_CLOSE"
                existing_close = conn.execute("SELECT 1 FROM odds_snapshots WHERE odds_id = ?", (close_id,)).fetchone()
                if existing_close:
                    continue
                inserted = db.insert_odds_snapshot(
                    {
                        "odds_id": close_id,
                        "game_id": s["game_id"],
                        "provider": s["provider"],
                        "market": s["market"],
                        "selection": s["selection"],
                        "line_value": s["line_value"],
                        "decimal_odds": s["decimal_odds"],
                        "counterpart_decimal_odds": s["counterpart_decimal_odds"],
                        "captured_at": s["captured_at"],
                        "is_closing_line": 1,
                        "source_type": s["source_type"],
                    },
                    conn=conn,
                )
                inserted_count += int(inserted)
    return inserted_count
