"""
Pure settlement outcome calculation for paper trading bets and player props.
"""

from __future__ import annotations

from typing import Any

from src.validation.validator import DataValidationError


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
