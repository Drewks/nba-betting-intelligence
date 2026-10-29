"""Strict validation of data completeness, odds integrity, duplicates, and temporal leakage."""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any

from src.ingestion.normalizer import normalize_team_code


class DataValidationError(ValueError):
    """Raised when a game, feature, or odds record violates structural or domain constraints."""


class TemporalLeakageError(DataValidationError):
    """Raised when future information (timestamp >= game_start_time or cutoff) is detected."""


ESSENTIAL_GAME_FEATURES: dict[str, list[str]] = {
    "moneyline": [
        "home_off_rtg",
        "home_def_rtg",
        "away_off_rtg",
        "away_def_rtg",
        "home_rest_days",
        "away_rest_days",
    ],
    "total_points": [
        "home_off_rtg",
        "home_def_rtg",
        "away_off_rtg",
        "away_def_rtg",
        "home_pace",
        "away_pace",
    ],
}


def parse_iso_utc(ts_str: str) -> datetime:
    """Parses an ISO-8601 UTC string into a timezone-aware datetime."""
    if not ts_str or not isinstance(ts_str, str):
        raise DataValidationError(f"Missing or invalid timestamp: {ts_str!r}")
    normalized = ts_str.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise DataValidationError(f"Unparseable ISO timestamp: {ts_str!r}") from exc
    if dt.tzinfo is None:
        raise DataValidationError(f"Timestamp must include explicit UTC offset: {ts_str!r}")
    return dt


def validate_game_record(
    game: dict[str, Any],
    simulated_prediction_time: str | None = None,
) -> dict[str, Any]:
    """Validates a game dictionary and verifies zero temporal leakage."""
    required_keys = [
        "game_id",
        "season",
        "matchday_date",
        "game_start_time",
        "home_team",
        "away_team",
        "status",
        "features_available_at",
        "source_provider",
    ]
    for k in required_keys:
        if not game.get(k):
            raise DataValidationError(f"Game record missing required field '{k}'")

    home_code = normalize_team_code(game["home_team"])
    away_code = normalize_team_code(game["away_team"])
    if home_code == away_code:
        raise DataValidationError(f"Home and away teams cannot be identical: {home_code}")

    start_dt = parse_iso_utc(game["game_start_time"])
    avail_dt = parse_iso_utc(game["features_available_at"])

    if avail_dt >= start_dt:
        raise TemporalLeakageError(
            f"Future data leakage in game {game['game_id']}: "
            f"features_available_at ({game['features_available_at']}) >= game_start_time ({game['game_start_time']})"
        )

    if simulated_prediction_time is not None:
        pred_dt = parse_iso_utc(simulated_prediction_time)
        if avail_dt > pred_dt:
            raise TemporalLeakageError(
                f"Feature availability ({game['features_available_at']}) is after "
                f"simulated prediction time ({simulated_prediction_time}) for {game['game_id']}"
            )
        if pred_dt >= start_dt:
            raise TemporalLeakageError(
                f"Prediction time ({simulated_prediction_time}) is at or after "
                f"game tipoff ({game['game_start_time']}) for {game['game_id']}"
            )

    return game


def validate_essential_features(game: dict[str, Any], market: str) -> None:
    """Verifies that all essential variables for the target market are present and finite."""
    if market not in ESSENTIAL_GAME_FEATURES:
        raise DataValidationError(f"Unsupported market: {market!r}")
    for feat in ESSENTIAL_GAME_FEATURES[market]:
        val = game.get(feat)
        if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
            raise DataValidationError(
                f"Missing essential feature '{feat}' for game {game.get('game_id')} in market '{market}'"
            )


def validate_odds_record(
    odds: dict[str, Any],
    game_start_time: str,
    simulated_prediction_time: str | None = None,
) -> dict[str, Any]:
    """Validates decimal odds (> 1.0), market/selection consistency, and pre-game timestamp."""
    if not odds:
        raise DataValidationError("Odds record is empty or None")

    dec_odds = odds.get("decimal_odds")
    if dec_odds is None or not isinstance(dec_odds, (int, float)) or math.isnan(dec_odds) or dec_odds <= 1.0:
        raise DataValidationError(f"Invalid or missing decimal_odds: {dec_odds!r} (must be > 1.0)")

    counterpart = odds.get("counterpart_decimal_odds")
    if counterpart is not None and (not isinstance(counterpart, (int, float)) or counterpart <= 1.0):
        raise DataValidationError(f"Invalid counterpart_decimal_odds: {counterpart!r}")

    market = odds.get("market")
    selection = odds.get("selection")
    line_value = odds.get("line_value")

    if market == "moneyline":
        if selection not in ("HOME", "AWAY"):
            raise DataValidationError(f"Invalid selection '{selection}' for moneyline market")
    elif market == "total_points":
        if selection not in ("OVER", "UNDER"):
            raise DataValidationError(f"Invalid selection '{selection}' for total_points market")
        if line_value is None or not isinstance(line_value, (int, float)) or line_value <= 50.0:
            raise DataValidationError(f"Missing or unrealistic total_points line_value: {line_value!r}")
    else:
        raise DataValidationError(f"Unsupported market in odds record: {market!r}")

    if not odds.get("provider"):
        raise DataValidationError("Odds record missing 'provider'")

    captured_dt = parse_iso_utc(odds.get("captured_at", ""))
    start_dt = parse_iso_utc(game_start_time)

    if captured_dt >= start_dt:
        raise TemporalLeakageError(
            f"Post-tipoff odds rejected for {odds.get('game_id')}: "
            f"captured_at ({odds.get('captured_at')}) >= game_start_time ({game_start_time})"
        )

    if simulated_prediction_time is not None:
        pred_dt = parse_iso_utc(simulated_prediction_time)
        if captured_dt > pred_dt:
            raise TemporalLeakageError(
                f"Future odds rejected for {odds.get('game_id')}: "
                f"captured_at ({odds.get('captured_at')}) > prediction_time ({simulated_prediction_time})"
            )

    return odds


def validate_temporal_split(
    train_games: list[dict[str, Any]],
    eval_games: list[dict[str, Any]],
) -> None:
    """Ensures every training game strictly precedes every evaluation game chronologically."""
    if not train_games or not eval_games:
        raise DataValidationError("Both train_games and eval_games must be non-empty.")

    max_train_dt = max(parse_iso_utc(g["game_start_time"]) for g in train_games)
    min_eval_dt = min(parse_iso_utc(g["game_start_time"]) for g in eval_games)

    train_ids = {g["game_id"] for g in train_games}
    eval_ids = {g["game_id"] for g in eval_games}
    overlap = train_ids.intersection(eval_ids)
    if overlap:
        raise TemporalLeakageError(f"Train and evaluation sets share overlapping game_ids: {sorted(overlap)}")

    if max_train_dt >= min_eval_dt:
        raise TemporalLeakageError(
            f"Temporal split violation: max training game time ({max_train_dt.isoformat()}) "
            f">= min evaluation game time ({min_eval_dt.isoformat()})"
        )


def detect_duplicates(
    records: list[dict[str, Any]],
    key_fields: tuple[str, ...],
) -> list[tuple[Any, ...]]:
    """Returns a list of duplicate composite keys found in records."""
    seen: set[tuple[Any, ...]] = set()
    duplicates: list[tuple[Any, ...]] = []
    for rec in records:
        key = tuple(rec.get(f) for f in key_fields)
        if key in seen:
            duplicates.append(key)
        else:
            seen.add(key)
    return duplicates
