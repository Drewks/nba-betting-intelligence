"""
Shadow Signal Ledger (`src/paper_trading/shadow_ledger.py`).

Records ALL positive-EV (`ev_unit > 0`) observed pre-game signals without enforcing
`min_stake_pen` (`KELLY_STAKE_BELOW_MINIMUM`), `min_ev_threshold` (`EV_BELOW_THRESHOLD`),
or the official 3-bets/day selection cap. Keeps zero impact on the official S/100 PEN
bankroll while capturing empirical CLV and 1u hypothetical ROI across blocked signals.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import logging
import math
from typing import Any

import numpy as np
from scipy.stats import t as student_t

from src.evaluation.clv import compute_bet_clv, index_closing_rows
from src.paper_trading.settlement import calculate_settlement_outcome
from src.paper_trading.staking import kelly_fraction_full

logger = logging.getLogger(__name__)

_NON_ELIGIBLE_REASONS = {
    "NONEXISTENT_GAME",
    "GAME_NOT_SCHEDULED",
    "GAME_ALREADY_STARTED",
    "INVALID_ODDS_RECORD",
    "SYNTHETIC_REJECTED",
    "NO_MARKET",
}


def _shadow_key(cand: dict[str, Any]) -> tuple[str, str, str, float | None]:
    lv = cand.get("line_value")
    return (
        str(cand.get("game_id") or ""),
        str(cand.get("market") or ""),
        str(cand.get("selection") or "").upper(),
        round(float(lv), 2) if lv is not None else None,
    )


def record_shadow_slate(
    db: Any,
    matchday_date: str,
    candidate_predictions: list[dict[str, Any]],
    *,
    placed_bets: list[dict[str, Any]],
    no_bet_decisions: list[dict[str, Any]],
    bankroll_pen: float,
    kelly_fraction: float,
    max_bankroll_fraction: float,
    default_model_version_id: str = "unknown",
) -> int:
    """Persists qualifying `+EV` observed candidates into immutable `shadow_candidates`."""
    try:
        has_table = db.fetch_one(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shadow_candidates'"
        )
        if not has_table:
            return 0
    except Exception:
        return 0

    placed_keys = {_shadow_key(b) for b in placed_bets}
    reason_by_key: dict[tuple[str, str, str, float | None], tuple[str, str]] = {}
    for b in placed_bets:
        reason_by_key[_shadow_key(b)] = ("BET_PLACED", "QUALIFIED_POSITIVE_EV")
    for d in no_bet_decisions:
        key_no_line = (str(d.get("game_id") or ""), str(d.get("market") or ""), str(d.get("selection") or "").upper())
        for c in candidate_predictions:
            ck = _shadow_key(c)
            if (ck[0], ck[1], ck[2]) == key_no_line and ck not in reason_by_key:
                reason_by_key[ck] = (str(d.get("decision_type") or "NO_BET"), str(d.get("reason_code") or "NO_BET"))

    candidate_gids = sorted({str(c.get("game_id") or "") for c in candidate_predictions if c.get("game_id")})
    if not candidate_gids:
        return 0
    placeholders = ",".join("?" for _ in candidate_gids)
    existing_game_ids = {
        str(r["game_id"])
        for r in db.fetch_all(
            f"SELECT game_id FROM games WHERE game_id IN ({placeholders})",
            tuple(candidate_gids),
        )
    }

    inserted = 0
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for cand in candidate_predictions:
        mkt = str(cand.get("market") or "")
        if mkt not in ("moneyline", "total_points", "spread"):
            continue
        ev_unit = float(cand.get("ev_unit", -1.0) or -1.0)
        dec_odds = float(cand.get("decimal_odds_used") or cand.get("decimal_odds") or 0.0)
        if ev_unit <= 0.0 or dec_odds <= 1.0:
            continue
        src_type = str(cand.get("odds_source_type") or cand.get("source_type") or "OBSERVED").upper()
        if src_type != "OBSERVED":
            continue
        gid = str(cand.get("game_id") or "")
        if not gid or gid.startswith("SYN") or gid not in existing_game_ids:
            continue

        ck = _shadow_key(cand)
        decision_status, reason_code = reason_by_key.get(
            ck,
            ("BET_PLACED", "QUALIFIED_POSITIVE_EV") if ck in placed_keys else ("NO_BET", "FILTERED_OR_CAPPED"),
        )
        if reason_code in _NON_ELIGIBLE_REASONS:
            continue

        cal_prob = float(cand.get("estimated_probability") or cand.get("calibrated_probability") or 0.5)
        raw_prob = float(cand.get("raw_model_probability") or cand.get("raw_probability") or cal_prob)
        emitted_at = str(cand.get("emitted_at") or cand.get("simulated_prediction_time") or now_str)
        m_ver = str(cand.get("model_version_id") or default_model_version_id)
        pred_id = cand.get("prediction_id")
        if pred_id:
            shadow_id = f"SHD_{pred_id}"
        else:
            digest = hashlib.sha1(
                f"{gid}|{mkt}|{ck[2]}|{ck[3]}|{cand.get('odds_provider', '')}|{emitted_at}".encode("utf-8")
            ).hexdigest()[:14].upper()
            shadow_id = f"SHD_{digest}"

        f_full = kelly_fraction_full(cal_prob, dec_odds)
        hypo_stake = round(max(0.0, float(bankroll_pen) * min(f_full * float(kelly_fraction), float(max_bankroll_fraction))), 4)

        changes = db.execute_insert(
            """
            INSERT OR IGNORE INTO shadow_candidates (
                shadow_id, prediction_id, game_id, matchday_date, market, selection, line_value,
                model_version_id, odds_provider, decimal_odds, raw_probability, calibrated_probability,
                ev_unit, ev_pct, hypothetical_kelly_stake_pen, decision_status, rejection_reason,
                emitted_at, status, source_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 'OBSERVED')
            """,
            (
                shadow_id,
                pred_id,
                gid,
                matchday_date,
                mkt,
                ck[2],
                ck[3],
                m_ver,
                str(cand.get("odds_provider") or "unknown"),
                dec_odds,
                raw_prob,
                cal_prob,
                ev_unit,
                float(cand.get("ev_pct") or round(ev_unit * 100.0, 4)),
                hypo_stake,
                decision_status,
                reason_code,
                emitted_at,
            ),
        )
        if changes:
            inserted += 1
    return inserted


def settle_pending_shadow_candidates(db: Any, settled_at: str | None = None) -> list[dict[str, Any]]:
    """Settles PENDING shadow candidates against finalized game scores and closing odds CLV."""
    has_table = db.fetch_one("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shadow_candidates'")
    if not has_table:
        return []

    pending = db.fetch_all(
        """
        SELECT s.*, g.status AS game_status, g.home_score, g.away_score, g.result_recorded_at
        FROM shadow_candidates s
        JOIN games g ON s.game_id = g.game_id
        WHERE s.status = 'PENDING'
          AND g.status IN ('FINAL', 'POSTPONED', 'CANCELLED')
        """
    )
    if not pending:
        return []

    closing_rows = db.fetch_all(
        """
        SELECT game_id, market, selection, line_value, decimal_odds, counterpart_decimal_odds, provider, captured_at
        FROM v_observed_odds_snapshots
        WHERE is_closing_line = 1
        """
    )
    closing_index = index_closing_rows(closing_rows)
    now_str = settled_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    settled_out: list[dict[str, Any]] = []

    for row in pending:
        outcome_status, unit_profit, _ = calculate_settlement_outcome(
            market=row["market"],
            selection=row["selection"],
            line_value=row.get("line_value"),
            decimal_odds=float(row["decimal_odds"]),
            stake_pen=1.0,
            game_status=row["game_status"],
            home_score=row.get("home_score"),
            away_score=row.get("away_score"),
        )
        clv_info = compute_bet_clv(row, closing_index, row.get("odds_provider"))
        close_fair = float(clv_info["p_close_fair"]) if clv_info else None
        close_odds = round(1.0 / close_fair, 4) if (close_fair and close_fair > 0.0) else None
        clv_pct = float(clv_info["clv_ev_pct"]) if (clv_info and not clv_info["is_outlier"]) else None
        ts = row.get("result_recorded_at") or now_str

        with db.connect() as conn:
            conn.execute(
                """
                UPDATE shadow_candidates
                SET closing_decimal_odds = ?, closing_fair_prob = ?, clv_pct = ?,
                    status = ?, hypothetical_unit_profit = ?, settled_at = ?
                WHERE shadow_id = ? AND status = 'PENDING'
                """,
                (close_odds, close_fair, clv_pct, outcome_status, unit_profit, ts, row["shadow_id"]),
            )
        settled_out.append(
            {
                "shadow_id": row["shadow_id"],
                "status": outcome_status,
                "hypothetical_unit_profit": unit_profit,
                "clv_pct": clv_pct,
            }
        )
    return settled_out


def clv_evidence(
    clvs: list[float],
    target_clv_pct: float = 1.0,
    groups: list[str] | None = None,
) -> dict[str, Any]:
    """
    How much the closing-line-value sample says about an edge.

    Signals on the same game are correlated (same result, same line move), so when `groups` (game ids)
    are given the interval is computed over per-game mean CLVs: one independent observation per game.

    - `verdict`: EDGE_SUPPORTED if the 95% Student-t CI of the mean CLV is above zero, NO_EDGE if it is below
      zero, INCONCLUSIVE otherwise (INSUFFICIENT_SAMPLE under 10 signals).
    - `signals_needed_for_target`: number of independent units (games when grouped) that would detect a
      true mean CLV of `target_clv_pct` with 80% power at 5% two-sided significance, given the
      observed dispersion.
    """
    n_signals = len(clvs)
    values = list(clvs)
    if groups is not None and len(groups) == len(clvs):
        per_game: dict[str, list[float]] = defaultdict(list)
        for g, c in zip(groups, clvs, strict=True):
            per_game[str(g)].append(float(c))
        values = [float(np.mean(v)) for v in per_game.values()]
    n = len(values)
    if n < 2:
        return {"n": n, "n_signals": n_signals, "verdict": "INSUFFICIENT_SAMPLE"}
    arr = np.asarray(values, dtype=float)
    mean = float(arr.mean())
    sd = float(arr.std(ddof=1))
    # Student-t quantile: with ~10 independent games a normal 1.96 interval is too narrow.
    t_crit = float(student_t.ppf(0.975, df=n - 1))
    half = t_crit * sd / math.sqrt(n)
    lower, upper = mean - half, mean + half
    if n < 10:
        verdict = "INSUFFICIENT_SAMPLE"
    elif lower > 0.0:
        verdict = "EDGE_SUPPORTED"
    elif upper < 0.0:
        verdict = "NO_EDGE"
    else:
        verdict = "INCONCLUSIVE"
    needed = math.ceil(((1.96 + 0.8416) * sd / target_clv_pct) ** 2) if sd > 0 else n
    return {
        "n": n,
        "n_signals": n_signals,
        "independent_unit": "game" if groups is not None else "signal",
        "mean_clv_pct": round(mean, 3),
        "ci95_pct": [round(lower, 3), round(upper, 3)],
        "std_clv_pct": round(sd, 3),
        "verdict": verdict,
        "target_clv_pct": target_clv_pct,
        "signals_needed_for_target": needed,
    }


def clv_evidence_by_market(db: Any) -> dict[str, dict[str, Any]]:
    """CLV evidence of the settled shadow signals of each market, one independent unit per game."""
    has_table = db.fetch_one("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shadow_candidates'")
    if not has_table:
        return {}
    rows = db.fetch_all(
        """
        SELECT market, game_id, clv_pct FROM shadow_candidates
        WHERE status IN ('WON', 'LOST', 'PUSH') AND clv_pct IS NOT NULL
        """
    )
    by_market: dict[str, tuple[list[float], list[str]]] = defaultdict(lambda: ([], []))
    for r in rows:
        clvs, games = by_market[str(r["market"])]
        clvs.append(float(r["clv_pct"]))
        games.append(str(r["game_id"]))
    return {m: clv_evidence(c, groups=g) for m, (c, g) in by_market.items()}


def summarize_shadow_ledger(db: Any, model_version_id: str | None = None) -> dict[str, Any]:
    """Returns audit-ready summary of all shadow candidates separated from the official bankroll."""
    has_table = db.fetch_one("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shadow_candidates'")
    if not has_table:
        return {"total_candidates": 0, "pending": 0, "settled": 0}

    where = "WHERE model_version_id = ?" if model_version_id else ""
    params: tuple[Any, ...] = (model_version_id,) if model_version_id else ()
    rows = db.fetch_all(f"SELECT * FROM shadow_candidates {where} ORDER BY emitted_at DESC", params)

    resolved = [r for r in rows if r["status"] in ("WON", "LOST", "PUSH")]
    non_push = [r for r in rows if r["status"] in ("WON", "LOST")]
    clv_rows = [r for r in resolved if r.get("clv_pct") is not None]
    clvs = [float(r["clv_pct"]) for r in clv_rows]
    clv_games = [str(r["game_id"]) for r in clv_rows]
    unit_profit = round(sum(float(r.get("hypothetical_unit_profit") or 0.0) for r in resolved), 4)
    unit_roi = round((unit_profit / len(non_push)) * 100.0, 2) if non_push else 0.0

    by_reason: dict[str, dict[str, Any]] = defaultdict(lambda: {"total": 0, "settled": 0, "won": 0, "lost": 0, "unit_profit": 0.0})
    for r in rows:
        rc = str(r.get("rejection_reason") or "UNKNOWN")
        by_reason[rc]["total"] += 1
        if r["status"] in ("WON", "LOST", "PUSH"):
            by_reason[rc]["settled"] += 1
            by_reason[rc]["unit_profit"] = round(by_reason[rc]["unit_profit"] + float(r.get("hypothetical_unit_profit") or 0.0), 4)
        if r["status"] == "WON":
            by_reason[rc]["won"] += 1
        elif r["status"] == "LOST":
            by_reason[rc]["lost"] += 1

    return {
        "total_candidates": len(rows),
        "pending": sum(1 for r in rows if r["status"] == "PENDING"),
        "settled": len(resolved),
        "won": sum(1 for r in resolved if r["status"] == "WON"),
        "lost": sum(1 for r in resolved if r["status"] == "LOST"),
        "push": sum(1 for r in resolved if r["status"] == "PUSH"),
        "unit_profit_1u": unit_profit,
        "unit_roi_pct": unit_roi,
        "mean_clv_pct": round(float(np.mean(clvs)), 3) if clvs else None,
        "clv_beat_close_rate": round(float(np.mean([c > 0.0 for c in clvs])), 4) if clvs else None,
        "clv_sample_size": len(clvs),
        "clv_evidence": clv_evidence(clvs, groups=clv_games),
        "by_rejection_reason": dict(by_reason),
    }
