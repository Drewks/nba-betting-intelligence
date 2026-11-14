"""
Common feature definitions and utility functions for NBA statistical models.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from src.validation.validator import parse_iso_utc


FEATURE_COLUMNS: list[str] = [
    "home_off_rtg",
    "home_def_rtg",
    "away_off_rtg",
    "away_def_rtg",
    "net_rtg_diff",
    "matchup_mismatch",
    "expected_pace",
    "pace_clash",
    "rest_diff",
    "b2b_advantage",
    "fatigue_diff",
    "altitude_advantage",
    "travel_miles_diff",
    "venue_split_diff",
    "streak_diff",
    "recent_margin_diff",
    "form_surge_diff",
    "recent_total_trend",
    "four_factors_diff",
    "shot_quality_xeFG_diff",
    "elo_spread",
    "structural_margin",
    "structural_total",
    "home_court_indicator",
]

MARGIN_FEATURE_COLUMNS: list[str] = [
    "elo_spread",
    "eff_spread",
    "structural_margin",
    "four_factors_diff",
    "shot_quality_xeFG_diff",
    "net_rtg_diff",
    "fatigue_diff",
    "altitude_advantage",
    "form_surge_diff",
    "recent_margin_diff",
    "expected_pace",
]

TOTAL_FEATURE_COLUMNS: list[str] = [
    "structural_total",
    "off_def_sum",
    "tempo_sum",
    "b2b_total_drag",
    "blowout_drag",
    "expected_pace",
    "pace_clash",
    "recent_total_trend",
]


def _filter_strictly_prior_final_games(
    historical_games: list[dict[str, Any]],
    cutoff_time_str: str,
) -> list[dict[str, Any]]:
    cutoff_dt = parse_iso_utc(cutoff_time_str)
    valid = [
        g
        for g in historical_games
        if g.get("status") == "FINAL"
        and g.get("home_score") is not None
        and g.get("away_score") is not None
        and (
            str(g.get("game_start_time", "")) < cutoff_time_str
            if len(str(g.get("game_start_time", ""))) == len(cutoff_time_str)
            else parse_iso_utc(g["game_start_time"]) < cutoff_dt
        )
    ]
    valid.sort(key=lambda g: (str(g.get("game_start_time", "")), str(g.get("game_id", ""))))
    return valid


def iter_expanding_temporal_oof_folds(
    sorted_games: list[dict[str, Any]],
    min_warmup: int = 20,
    n_folds: int = 5,
) -> list[tuple[list[int], list[int], str]]:
    """
    Splits chronologically sorted games into expanding walk-forward OOF folds grouped by
    tipoff timestamp so every training game satisfies parse_iso_utc(train) < parse_iso_utc(fold_cutoff)
    and every validation game satisfies parse_iso_utc(val) >= parse_iso_utc(fold_cutoff).
    """
    n_total = len(sorted_games)
    if n_total <= min_warmup or n_folds < 1:
        return []

    # Group contiguous indices with identical parsed tipoff timestamp so boundary ties stay strictly together.
    parsed_ts = [parse_iso_utc(str(g["game_start_time"])) for g in sorted_games]
    groups: list[list[int]] = []
    for idx, ts_dt in enumerate(parsed_ts):
        if not groups or ts_dt != parsed_ts[groups[-1][0]]:
            groups.append([idx])
        else:
            groups[-1].append(idx)

    prefix_count = 0
    eval_start_group = 0
    while eval_start_group < len(groups) and prefix_count < min_warmup:
        prefix_count += len(groups[eval_start_group])
        eval_start_group += 1

    if eval_start_group >= len(groups):
        return []

    eval_groups = groups[eval_start_group:]
    k_eff = min(int(n_folds), len(eval_groups))
    q, rem = divmod(len(eval_groups), k_eff)

    folds: list[tuple[list[int], list[int], str]] = []
    pos = 0
    for f_i in range(k_eff):
        size = q + (1 if f_i < rem else 0)
        fold_val_groups = eval_groups[pos : pos + size]
        pos += size
        if not fold_val_groups:
            continue
        val_indices = [i for grp in fold_val_groups for i in grp]
        first_val_idx = val_indices[0]
        train_indices = list(range(0, first_val_idx))
        if not train_indices:
            continue
        fold_cutoff = str(sorted_games[first_val_idx]["game_start_time"])
        folds.append((train_indices, val_indices, fold_cutoff))
    return folds


def build_oof_sigma_metadata(
    *,
    method: str,
    oof_residuals: list[float] | np.ndarray,
    insample_residuals: list[float] | np.ndarray | None,
    effective_sigma: float,
    fold_records: list[dict[str, Any]],
    train_sample: list[dict[str, Any]],
) -> dict[str, Any]:
    """Builds transparent OOS vs in-sample residual dispersion diagnostics without feeding in-sample errors to sigma."""
    oof_arr = np.asarray(oof_residuals, dtype=float)
    ins_arr = np.asarray(insample_residuals, dtype=float) if insample_residuals is not None else np.empty(0)
    oof_raw = round(float(np.std(oof_arr, ddof=1)), 4) if len(oof_arr) >= 2 else None
    ins_raw = round(float(np.std(ins_arr, ddof=1)), 4) if len(ins_arr) >= 2 else None
    delta = (
        round(float(oof_raw - ins_raw), 4)
        if (oof_raw is not None and ins_raw is not None)
        else None
    )
    return {
        "method": method,
        "uses_insample_for_sigma": False,
        "oof_sample_size": int(len(oof_arr)),
        "insample_sample_size": int(len(ins_arr)),
        "n_folds": len(fold_records),
        "train_time_start": str(train_sample[0]["game_start_time"]) if train_sample else None,
        "train_time_end": str(train_sample[-1]["game_start_time"]) if train_sample else None,
        "oof_time_start": fold_records[0]["val_min_time"] if fold_records else None,
        "oof_time_end": fold_records[-1]["val_max_time"] if fold_records else None,
        "oof_residual_std_raw": oof_raw,
        "insample_residual_std_raw": ins_raw,
        "oof_minus_insample_std": delta,
        "effective_sigma": round(float(effective_sigma), 4),
        "folds": fold_records,
    }


def make_fold_record(
    sorted_games: list[dict[str, Any]],
    train_indices: list[int],
    val_indices: list[int],
    fold_cutoff: str,
) -> dict[str, Any]:
    """Summarizes strict temporal fold boundaries for F-001 audit verification."""
    return {
        "fold_cutoff": fold_cutoff,
        "train_max_time": str(sorted_games[train_indices[-1]]["game_start_time"]),
        "val_min_time": str(sorted_games[val_indices[0]]["game_start_time"]),
        "val_max_time": str(sorted_games[val_indices[-1]]["game_start_time"]),
        "n_train": len(train_indices),
        "n_val": len(val_indices),
    }
