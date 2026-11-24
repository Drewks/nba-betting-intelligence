"""
Decision-time market quotes (`src/prediction/market_quotes.py`).

Which observed quotes count as a price that could have been taken at a decision time (`config.execution`),
and the market that decision sees: the de-vigged consensus of those quotes and the line steam over the
snapshots captured up to it. The live cycle (`scripts/cloud_cycle_helpers.py`) takes its quotes from
`pair_valid_pretip_quotes`; the walk-forward simulation reads its market through `decision_time_market`,
which builds consensus and steam from the same functions and the same quote sets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.config import ExecutionConfig
from src.prediction.ev_calculator import compute_line_steam, compute_market_consensus
from src.validation.validator import parse_iso_utc

__all__ = ["DecisionTimeMarket", "decision_time_market", "pair_valid_pretip_quotes"]


def pair_valid_pretip_quotes(
    raw_game_odds: list[dict[str, Any]],
    start_dt: datetime,
    *,
    decision_dt: datetime | None = None,
    max_quote_age_hours: float | None = None,
    excluded_provider_markers: tuple[str, ...] = (),
    max_overround: float | None = None,
) -> list[dict[str, Any]]:
    """
    Extracts complete two-sided pre-tipoff observed pairs grouped by `(provider, market, canonical_line)`.

    For live decisions (`decision_dt` set) only quotes that existed at the decision time and are at most
    `max_quote_age_hours` old are used, and providers whose label contains an excluded marker (e.g.
    "(Best of" aggregates that pair the best price of one book with another book's counterpart) are
    skipped: those prices are not a quote any single book offered. Two-way markets whose overround
    exceeds `max_overround` are dropped: at a ~10% margin no realistic edge survives.
    """
    latest_by_key: dict[tuple[str, str, float | None, str], tuple[datetime, dict[str, Any]]] = {}
    for o in raw_game_odds:
        try:
            cap_dt = parse_iso_utc(str(o["captured_at"]))
            dec_val = float(o.get("decimal_odds") or 0.0)
        except Exception:
            continue
        if cap_dt >= start_dt or dec_val <= 1.0:
            continue
        if any(marker in str(o.get("provider") or "") for marker in excluded_provider_markers):
            continue
        if decision_dt is not None:
            if cap_dt > decision_dt:
                continue
            if max_quote_age_hours is not None and (decision_dt - cap_dt).total_seconds() > max_quote_age_hours * 3600.0:
                continue
        mkt_str = str(o["market"])
        sel_u = str(o["selection"]).upper()
        raw_lv = o.get("line_value")
        lv_key: float | None
        if mkt_str == "moneyline":
            if raw_lv is not None or sel_u not in ("HOME", "AWAY"):
                continue
            lv_key = None
        elif mkt_str == "total_points":
            if raw_lv is None or sel_u not in ("OVER", "UNDER"):
                continue
            lv_key = round(float(raw_lv), 2)
            if lv_key <= 50.0:
                continue
        elif mkt_str == "spread":
            if raw_lv is None or sel_u not in ("HOME", "AWAY") or abs(float(raw_lv)) > 45.0:
                continue
            lv_key = round(float(raw_lv) if sel_u == "HOME" else -float(raw_lv), 2)
        else:
            continue
        key_t = (str(o["provider"]), mkt_str, lv_key, sel_u)
        prev = latest_by_key.get(key_t)
        if prev is None or cap_dt >= prev[0]:
            latest_by_key[key_t] = (cap_dt, o)

    sides_by_market = {
        "moneyline": ("HOME", "AWAY"),
        "total_points": ("OVER", "UNDER"),
        "spread": ("HOME", "AWAY"),
    }
    paired: list[dict[str, Any]] = []
    for mkt_name, (side_a, side_b) in sides_by_market.items():
        prov_lines = sorted({(k[0], k[2]) for k in latest_by_key if k[1] == mkt_name})
        for prov, lv_key in prov_lines:
            entry_a = latest_by_key.get((prov, mkt_name, lv_key, side_a))
            entry_b = latest_by_key.get((prov, mkt_name, lv_key, side_b))
            if not entry_a or not entry_b:
                continue
            row_a, row_b = entry_a[1], entry_b[1]
            if max_overround is not None:
                overround = 1.0 / float(row_a["decimal_odds"]) + 1.0 / float(row_b["decimal_odds"]) - 1.0
                if overround > max_overround:
                    continue
            paired.append({**row_a, "counterpart_decimal_odds": float(row_b["decimal_odds"])})
            paired.append({**row_b, "counterpart_decimal_odds": float(row_a["decimal_odds"])})
    return paired


@dataclass(frozen=True)
class DecisionTimeMarket:
    """The market known at one decision time: consensus of the quotes that could be taken, and line steam."""

    consensus: dict[tuple[str, str, float | None], dict[str, Any]]
    steam: dict[tuple[str, str], dict[str, float]]

    def consensus_prob(self, market: str, selection: str, line_value: float | None) -> float | None:
        """De-vigged consensus for one side, looked up as the live cycle does (exact line, then rounded)."""
        entry = self.consensus.get((market, selection, line_value))
        if entry is None and line_value is not None:
            entry = self.consensus.get((market, selection, round(float(line_value), 2)))
        return float(entry["p_market"]) if entry else None

    def steam_delta(self, market: str, selection: str) -> float:
        """Fair-probability move of one side from its first to its latest snapshot (0 without history)."""
        entry = self.steam.get((market, selection))
        return float(entry["steam_delta"]) if entry else 0.0


def decision_time_market(
    snapshots: list[dict[str, Any]],
    start_dt: datetime,
    decision_dt: datetime,
    *,
    execution_cfg: ExecutionConfig,
) -> DecisionTimeMarket:
    """
    The market as the live cycle (`evaluate_scheduled_slate_candidates`) sees it when deciding at
    `decision_dt`, from one game's pre-game (non-closing) odds snapshots:
      - consensus (`compute_market_consensus`) over the quotes a bet could have been taken at then:
        `pair_valid_pretip_quotes` with `config.execution` (complete two-way pairs, latest per book and line,
        at most `max_quote_age_hours` old, no cross-book aggregates, overround <= `max_bookmaker_overround`);
      - steam (`compute_line_steam`) over every snapshot captured up to the decision.
    Snapshots captured after `decision_dt` are ignored by both (no lookahead).
    """
    known = [o for o in snapshots if parse_iso_utc(str(o["captured_at"])) <= decision_dt]
    takeable = pair_valid_pretip_quotes(
        known,
        start_dt,
        decision_dt=decision_dt,
        max_quote_age_hours=execution_cfg.max_quote_age_hours,
        excluded_provider_markers=execution_cfg.excluded_provider_markers,
        max_overround=execution_cfg.max_bookmaker_overround,
    )
    return DecisionTimeMarket(consensus=compute_market_consensus(takeable), steam=compute_line_steam(known))
