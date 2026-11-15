"""
Quarantined Player Props & SGP Paper-Trading Ledger helpers (`src/paper_trading/props_ledger.py`).

Extracted from `src/paper_trading/engine.py` to keep the main moneyline/totals/spread
paper trading engine concise and keep disabled-by-default props/SGP accounting isolated.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import math
import sqlite3
from typing import Any
import uuid

import numpy as np

from src.paper_trading.exceptions import DoubleSettlementError, RiskLimitError
from src.paper_trading.settlement import calculate_prop_settlement_outcome
from src.validation.validator import DataValidationError, TemporalLeakageError, parse_iso_utc

logger = logging.getLogger(__name__)


def compute_props_calibration_summary(resolved_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Computes strictly separated calibration and interval diagnostics on resolved WON/LOST props.
    Reports Brier Score, Log Loss, 10-bin ECE, binary accuracy (`accuracy_pct`),
    mean Venn-Abers probability interval width, and binned empirical interval validity.
    """
    squared_errors: list[float] = []
    log_losses: list[float] = []
    probs: list[float] = []
    outcomes: list[float] = []
    accuracy_hits = 0
    calibrated_samples: list[tuple[float, float, float, float]] = []

    for p in resolved_rows:
        status = p.get("status")
        if status not in ("WON", "LOST"):
            continue
        y_true = 1.0 if status == "WON" else 0.0
        raw_mp = p.get("model_prob")
        prob = max(1e-6, min(1.0 - 1e-6, float(raw_mp) if raw_mp is not None else 0.5))
        squared_errors.append((prob - y_true) ** 2)
        log_losses.append(-(y_true * math.log(prob) + (1.0 - y_true) * math.log(1.0 - prob)))
        probs.append(prob)
        outcomes.append(y_true)
        if (status == "WON" and prob >= 0.5) or (status == "LOST" and prob < 0.5):
            accuracy_hits += 1

        raw_low = p.get("conformal_p_low")
        raw_high = p.get("conformal_p_high")
        if raw_low is not None and raw_high is not None:
            p_low = float(raw_low)
            p_high = float(raw_high)
            if 0.0 <= p_low <= p_high <= 1.0 and (p_low > 0.0 or p_high < 1.0):
                calibrated_samples.append((prob, p_low, p_high, y_true))

    wl_count = len(outcomes)
    if wl_count == 0:
        return {
            "brier_score": 0.0,
            "log_loss": None,
            "ece": None,
            "accuracy_pct": None,
            "venn_abers_interval_width_mean": None,
            "venn_abers_calibrated_count": 0,
            "venn_abers_empirical_coverage_valid": None,
            "conformal_coverage_pct": None,
        }

    ece_total = 0.0
    for b in range(10):
        lo = b * 0.1
        hi = (b + 1) * 0.1
        idxs = [i for i, pr in enumerate(probs) if (lo <= pr < hi) or (b == 9 and pr == 1.0)]
        if idxs:
            conf_bin = sum(probs[i] for i in idxs) / len(idxs)
            acc_bin = sum(outcomes[i] for i in idxs) / len(idxs)
            ece_total += (len(idxs) / wl_count) * abs(acc_bin - conf_bin)

    cal_n = len(calibrated_samples)
    width_mean: float | None = None
    emp_cov_valid: bool | None = None
    conformal_cov_pct: float | None = None
    if cal_n > 0:
        width_mean = round(float(np.mean([s[2] - s[1] for s in calibrated_samples])), 4)
        sorted_cal = sorted(calibrated_samples, key=lambda x: x[0])
        n_bins = max(1, min(5, cal_n // 5))
        bin_size = math.ceil(cal_n / n_bins)
        covered_n = 0
        for start in range(0, cal_n, bin_size):
            chunk = sorted_cal[start : start + bin_size]
            mean_low = float(np.mean([c[1] for c in chunk]))
            mean_high = float(np.mean([c[2] for c in chunk]))
            emp_rate = float(np.mean([c[3] for c in chunk]))
            if mean_low - 1e-6 <= emp_rate <= mean_high + 1e-6:
                covered_n += len(chunk)
        conformal_cov_pct = round(covered_n / cal_n * 100.0, 1)
        overall_low = float(np.mean([c[1] for c in calibrated_samples]))
        overall_high = float(np.mean([c[2] for c in calibrated_samples]))
        overall_rate = float(np.mean([c[3] for c in calibrated_samples]))
        emp_cov_valid = bool(overall_low - 1e-6 <= overall_rate <= overall_high + 1e-6)

    return {
        "brier_score": round(float(np.mean(squared_errors)), 4),
        "log_loss": round(float(np.mean(log_losses)), 4),
        "ece": round(ece_total, 4),
        "accuracy_pct": round(accuracy_hits / wl_count * 100.0, 2),
        "venn_abers_interval_width_mean": width_mean,
        "venn_abers_calibrated_count": cal_n,
        "venn_abers_empirical_coverage_valid": emp_cov_valid,
        "conformal_coverage_pct": conformal_cov_pct,
    }


def record_player_prop_pick(
    db: Any,
    risk_config: Any,
    record_decision_fn: Any,
    prop_dict: dict[str, Any],
    enforce_scheduled_status: bool = False,
    allow_parlay: bool | None = None,
    allow_player_props: bool | None = None,
) -> str:
    """Records a player prop paper bet with fail-closed risk gates and roster validation."""
    prop_id = prop_dict.get("prop_id") or f"PROP_{uuid.uuid4().hex[:10].upper()}"
    emitted_at = prop_dict.get("emitted_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    gid = str(prop_dict.get("game_id") or "")
    cat = str(prop_dict.get("prop_category", "")).upper()
    matchday_date = str(prop_dict.get("matchday_date") or emitted_at[:10])
    selection_label = f"{prop_dict.get('player_name', '')} {prop_dict.get('selection', '')}".strip() or "PROP"
    ev_pct = float(prop_dict.get("ev_pct") or 0.0)

    eff_allow_parlay = risk_config.allow_parlays if allow_parlay is None else bool(allow_parlay)
    eff_allow_props = (
        risk_config.allow_player_props_betting
        if allow_player_props is None
        else bool(allow_player_props)
    )
    is_parlay_pick = cat in ("SGP", "SGP_2LEG", "PARLAY")

    if is_parlay_pick and not eff_allow_parlay:
        reason = "Combined bets (SGP/parlays) are disabled (risk_management.allow_parlays = false)."
        record_decision_fn(
            game_id=gid or f"MATCHDAY_{matchday_date}",
            matchday_date=matchday_date,
            market=cat or "SGP",
            selection=selection_label,
            decision_type="NO_BET",
            reason_code="DISABLED_BY_CONFIG",
            reason_detail=reason,
            ev_pct=ev_pct,
            emitted_at=emitted_at,
            model_version_id=str(prop_dict.get("model_version_id") or "player_props_v8"),
        )
        raise RiskLimitError(reason)

    if not eff_allow_props:
        reason = "Player props betting is disabled (risk_management.allow_player_props_betting = false)."
        record_decision_fn(
            game_id=gid or f"MATCHDAY_{matchday_date}",
            matchday_date=matchday_date,
            market=cat or "PLAYER_PROP",
            selection=selection_label,
            decision_type="NO_BET",
            reason_code="DISABLED_BY_CONFIG",
            reason_detail=reason,
            ev_pct=ev_pct,
            emitted_at=emitted_at,
            model_version_id=str(prop_dict.get("model_version_id") or "player_props_v8"),
        )
        raise RiskLimitError(reason)

    game = db.fetch_one("SELECT game_id, game_start_time, status, home_team, away_team FROM games WHERE game_id = ?", (gid,))
    if not game:
        raise DataValidationError(f"Cannot record prop on nonexistent game: {gid}")
    if enforce_scheduled_status and game["status"] != "SCHEDULED":
        raise DataValidationError(f"Cannot record prop on game {gid} with status '{game['status']}' (must be 'SCHEDULED')")

    start_ts = game.get("game_start_time")
    if enforce_scheduled_status and start_ts:
        if parse_iso_utc(emitted_at) >= parse_iso_utc(start_ts):
            raise TemporalLeakageError(
                f"Temporal leakage violation: prop {prop_id} emitted at {emitted_at} >= game tipoff {start_ts}"
            )

    team = prop_dict.get("team", "NBA")
    player_name = prop_dict.get("player_name", "")
    cat = prop_dict.get("prop_category", "")
    if cat != "SGP" and team != "NBA":
        roster_rows = db.fetch_all("SELECT player_name FROM team_rosters WHERE team_id = ? AND is_active = 1", (team,))
        if roster_rows:
            from src.ingestion.roster_manager import normalize_name
            norm_p = normalize_name(player_name)
            norm_active = {normalize_name(r["player_name"]) for r in roster_rows}
            if norm_p not in norm_active:
                other_team_row = db.fetch_one(
                    "SELECT team_id FROM team_rosters WHERE (player_name LIKE ? OR ? LIKE ('%' || player_name || '%')) AND is_active = 1",
                    (f"%{player_name}%", player_name),
                )
                actual_team = other_team_row["team_id"] if other_team_row else "Unknown"
                raise DataValidationError(
                    f"Roster integrity violation: {player_name} is not on active roster of {team} (currently on {actual_team})"
                )

    stake_pen = round(float(prop_dict.get("stake_pen") or prop_dict.get("kelly_stake_pen") or 1.00), 2)
    if stake_pen <= 0.0:
        stake_pen = 1.00

    db.execute_insert(
        """
        INSERT OR IGNORE INTO player_prop_picks (
            prop_id, game_id, matchday_date, player_name, team, prop_category,
            line_value, selection, decimal_odds, projected_mean, projected_std,
            model_prob, conformal_p_low, conformal_p_high, ev_pct, ev_lower_bound_pct,
            stake_pen, kelly_stake_pen, usage_bump_pct, rationale, emitted_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
        """,
        (
            prop_id,
            prop_dict["game_id"],
            prop_dict["matchday_date"],
            prop_dict["player_name"],
            prop_dict.get("team", "NBA"),
            prop_dict["prop_category"],
            float(prop_dict["line_value"]),
            prop_dict["selection"],
            float(prop_dict["decimal_odds"]),
            float(prop_dict.get("projected_mean", 0.0)),
            float(prop_dict.get("projected_std", 0.0)),
            float(prop_dict["model_prob"]),
            float(prop_dict.get("conformal_p_low", 0.0)),
            float(prop_dict.get("conformal_p_high", 1.0)),
            float(prop_dict.get("ev_pct", 0.0)),
            float(prop_dict.get("ev_lower_bound_pct", 0.0)),
            stake_pen,
            float(prop_dict.get("kelly_stake_pen", stake_pen)),
            float(prop_dict.get("usage_bump_pct", 0.0)),
            prop_dict.get("rationale", "Prop opportunity identified by V8 quantitative model"),
            emitted_at,
        ),
    )
    return prop_id


def settle_player_prop(
    db: Any,
    initial_bankroll_pen: float,
    prop_id: str,
    actual_stat: float | None = None,
    game_status: str = "FINAL",
    home_score: int | None = None,
    away_score: int | None = None,
    settled_at: str | None = None,
) -> dict[str, Any]:
    """Settles a single PENDING simulated player prop or SGP parlay bet."""
    prop = db.fetch_one("SELECT * FROM player_prop_picks WHERE prop_id = ?", (prop_id,))
    if not prop:
        raise DataValidationError(f"Player prop pick ID {prop_id!r} does not exist")
    if prop["status"] != "PENDING":
        raise DoubleSettlementError(
            f"Prop {prop_id} has already been settled with status '{prop['status']}' and cannot be settled twice."
        )
    game = db.fetch_one("SELECT * FROM games WHERE game_id = ?", (prop["game_id"],))
    if not game:
        raise DataValidationError(f"Associated game {prop['game_id']} not found")

    settlement_ts = settled_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if game_status not in ("VOID", "CANCELLED", "POSTPONED") and parse_iso_utc(settlement_ts) <= parse_iso_utc(game["game_start_time"]):
        raise TemporalLeakageError(
            f"Cannot settle prop {prop_id} at {settlement_ts} before or at game_start_time ({game['game_start_time']})"
        )

    outcome_status, net_profit, stat_recorded, summary = calculate_prop_settlement_outcome(
        prop=prop,
        actual_stat=actual_stat,
        game_status=game_status,
        home_score=home_score,
        away_score=away_score,
    )
    prior_pnl_row = db.fetch_one(
        """
        SELECT COALESCE(SUM(net_profit_pen), 0.0) AS total_prior_pnl
        FROM player_prop_picks
        WHERE status IN ('WON', 'LOST', 'PUSH', 'VOID')
          AND net_profit_pen IS NOT NULL
          AND prop_id != ?
        """,
        (prop_id,),
    )
    total_prior_pnl = float(prior_pnl_row["total_prior_pnl"]) if prior_pnl_row else 0.0
    new_bankroll = round(initial_bankroll_pen + total_prior_pnl + net_profit, 4)
    if new_bankroll < 0.0:
        raise RiskLimitError(f"Negative props bankroll violation detected: S/{new_bankroll:.2f}")

    try:
        with db.connect() as conn:
            conn.execute(
                """
                UPDATE player_prop_picks
                SET status = ?, actual_stat = ?, net_profit_pen = ?,
                    bankroll_after_pen = ?, actual_result_summary = ?, settled_at = ?
                WHERE prop_id = ?
                """,
                (outcome_status, stat_recorded, net_profit, new_bankroll, summary, settlement_ts, prop_id),
            )
    except sqlite3.IntegrityError as exc:
        raise DoubleSettlementError(f"Database trigger blocked settlement on prop {prop_id}: {exc}") from exc

    return {
        "prop_id": prop_id,
        "status": outcome_status,
        "actual_stat": stat_recorded,
        "net_profit_pen": net_profit,
        "bankroll_after_pen": new_bankroll,
        "actual_result_summary": summary,
        "settled_at": settlement_ts,
    }


def settle_pending_player_props(
    db: Any,
    initial_bankroll_pen: float,
    game_boxscores: dict[str, dict[str, dict[str, float]]] | None = None,
    settled_at: str | None = None,
) -> list[dict[str, Any]]:
    """Scans all PENDING props whose games are FINAL/POSTPONED/CANCELLED and executes settlement."""
    pending_props = db.fetch_all(
        """
        SELECT p.prop_id, p.game_id, p.player_name, p.team, p.prop_category, p.line_value,
               p.selection, g.status as game_status, g.home_score, g.away_score,
               g.home_team, g.away_team, g.result_recorded_at
        FROM player_prop_picks p
        JOIN games g ON p.game_id = g.game_id
        WHERE p.status = 'PENDING'
          AND g.status IN ('FINAL', 'POSTPONED', 'CANCELLED')
        """
    )
    settled_results: list[dict[str, Any]] = []
    for prop in pending_props:
        pid = prop["prop_id"]
        gid = prop["game_id"]
        g_status = prop["game_status"]
        ts = settled_at or prop["result_recorded_at"]

        if g_status in ("POSTPONED", "CANCELLED"):
            try:
                settled_results.append(
                    settle_player_prop(db, initial_bankroll_pen, pid, game_status=g_status, settled_at=ts)
                )
            except Exception as exc:
                logger.warning(f"Failed to settle postponed prop {pid}: {exc}")
            continue

        cat = prop["prop_category"]
        p_name = prop["player_name"]
        stat_val: float | None = None
        if game_boxscores and gid in game_boxscores:
            g_box = game_boxscores[gid]
            p_stats = g_box.get(p_name)
            if not p_stats:
                for k, v in g_box.items():
                    if k in p_name or p_name in k:
                        p_stats = v
                        break
            if p_stats and cat in p_stats:
                stat_val = float(p_stats[cat])
            elif cat == "SGP" and p_stats and "SGP" in p_stats:
                stat_val = float(p_stats["SGP"])

        if stat_val is not None:
            try:
                settled_results.append(
                    settle_player_prop(
                        db,
                        initial_bankroll_pen,
                        prop_id=pid,
                        actual_stat=stat_val,
                        game_status=g_status,
                        home_score=prop["home_score"],
                        away_score=prop["away_score"],
                        settled_at=ts,
                    )
                )
            except Exception as exc:
                logger.warning(f"Failed to settle prop {pid}: {exc}")

    return settled_results


def get_player_props_performance_metrics(db: Any, initial_bankroll_pen: float) -> dict[str, Any]:
    """Computes quarantined performance metrics for Player Props & SGP paper trading."""
    all_props = db.fetch_all("SELECT * FROM player_prop_picks ORDER BY emitted_at DESC")
    settled_all = [p for p in all_props if p["status"] in ("WON", "LOST", "PUSH", "VOID")]
    resolved = [p for p in all_props if p["status"] in ("WON", "LOST", "PUSH")]
    won = [p for p in resolved if p["status"] == "WON"]
    lost = [p for p in resolved if p["status"] == "LOST"]
    push = [p for p in resolved if p["status"] == "PUSH"]
    void = [p for p in settled_all if p["status"] == "VOID"]

    total_staked = sum(float(p.get("stake_pen") or p.get("kelly_stake_pen") or 1.0) for p in resolved if p["status"] in ("WON", "LOST"))
    net_profit = sum(float(p.get("net_profit_pen") or 0.0) for p in resolved)
    current_bankroll = round(initial_bankroll_pen + net_profit, 2)
    resolved_count = len(won) + len(lost)
    win_rate = (len(won) / resolved_count * 100.0) if resolved_count > 0 else 0.0
    roi_pct = (net_profit / total_staked * 100.0) if total_staked > 0 else 0.0
    cal_summary = compute_props_calibration_summary(resolved)

    breakdown: dict[str, dict[str, Any]] = {}
    for cat in ("PTS", "REB", "AST", "PRA", "3PM", "PR", "PA", "RA", "SGP"):
        cat_props = [p for p in settled_all if p.get("prop_category") == cat]
        c_won = [p for p in cat_props if p["status"] == "WON"]
        c_lost = [p for p in cat_props if p["status"] == "LOST"]
        c_push = [p for p in cat_props if p["status"] == "PUSH"]
        c_void = [p for p in cat_props if p["status"] == "VOID"]
        c_staked = sum(float(p.get("stake_pen") or p.get("kelly_stake_pen") or 1.0) for p in cat_props if p["status"] in ("WON", "LOST"))
        c_net = sum(float(p.get("net_profit_pen") or 0.0) for p in cat_props if p["status"] in ("WON", "LOST", "PUSH"))
        c_res = len(c_won) + len(c_lost)
        c_resolved_total = c_res + len(c_push)
        breakdown[cat] = {
            "total_settled": c_resolved_total,
            "resolved_picks": c_resolved_total,
            "won": len(c_won),
            "lost": len(c_lost),
            "push": len(c_push),
            "void": len(c_void),
            "win_rate_pct": round(len(c_won) / c_res * 100.0, 1) if c_res > 0 else 0.0,
            "total_staked_pen": round(c_staked, 2),
            "net_profit_pen": round(c_net, 2),
            "roi_pct": round(c_net / c_staked * 100.0, 2) if c_staked > 0 else 0.0,
        }

    return {
        "total_picks": len(all_props),
        "pending_picks": len(all_props) - len(settled_all),
        "settled_picks": len(resolved),
        "resolved_picks": len(resolved),
        "won_picks": len(won),
        "lost_picks": len(lost),
        "push_picks": len(push),
        "void_picks": len(void),
        "win_rate_pct": round(win_rate, 2),
        "total_staked_pen": round(total_staked, 2),
        "total_net_profit_pen": round(net_profit, 2),
        "current_props_bankroll_pen": round(current_bankroll, 2),
        "roi_pct": round(roi_pct, 2),
        "brier_score": cal_summary["brier_score"],
        "log_loss": cal_summary["log_loss"],
        "ece": cal_summary["ece"],
        "accuracy_pct": cal_summary["accuracy_pct"],
        "venn_abers_interval_width_mean": cal_summary["venn_abers_interval_width_mean"],
        "venn_abers_calibrated_count": cal_summary["venn_abers_calibrated_count"],
        "venn_abers_empirical_coverage_valid": cal_summary["venn_abers_empirical_coverage_valid"],
        "conformal_coverage_pct": cal_summary["conformal_coverage_pct"],
        "category_breakdown": breakdown,
        "recent_settled": resolved[:15],
    }
