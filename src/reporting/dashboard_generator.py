"""
Interactive HTML Dashboard Generator (`src/reporting/dashboard_generator.py`).
Assembles payload and composes `dashboard_markup` + `dashboard_scripts`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.config import load_config
from src.ingestion.peru_sportsbooks import get_peru_sportsbooks_json_for_frontend
from src.reporting.dashboard_markup import render_dashboard_markup
from src.reporting.dashboard_scripts import render_dashboard_scripts
from src.utils.team_dictionary import get_teams_json_for_frontend

logger = logging.getLogger(__name__)


def _round_or_none(value: Any, digits: int) -> float | None:
    return None if value is None else round(float(value), digits)


def generate_interactive_html_dashboard(
    metrics: dict[str, Any],
    espn_real_bets: list[dict[str, Any]],
    slate_items: list[dict[str, Any]],
    html_output_path: str | Path,
    peru_str: str,
    player_props: list[dict[str, Any]] | None = None,
    props_paper_trading: dict[str, Any] | None = None,
    db: Any | None = None,
) -> str:
    """Generates the standalone interactive HTML dashboard without hidden DB side-effects."""
    if player_props is None:
        try:
            props_file = Path(html_output_path).resolve().parent.parent / "data" / "evaluation" / "latest_player_props.json"
            if props_file.exists():
                player_props = json.loads(props_file.read_text(encoding="utf-8"))
            else:
                player_props = []
        except Exception:
            player_props = []

    risk_cfg = load_config().risk
    min_ev_pct = round(float(risk_cfg.min_ev_threshold) * 100.0, 1)
    kelly_pct = round(float(risk_cfg.kelly_fraction) * 100.0)
    pending_stake = round(
        sum(float(b.get("stake_pen") or 0.0) for b in espn_real_bets if (b.get("estado") or b.get("status")) == "PENDING"),
        2,
    )
    settled_bank = round(float(metrics.get("current_settled_bankroll_pen", risk_cfg.virtual_bankroll_initial_pen)), 2)
    avail_bank = round(settled_bank - pending_stake, 2)
    pending_cnt = sum(1 for b in espn_real_bets if (b.get("estado") or b.get("status")) == "PENDING")

    payload: dict[str, Any] = {
        "updated_peru": peru_str,
        "summary": {
            "initial_bankroll_pen": float(risk_cfg.virtual_bankroll_initial_pen),
            "settled_bankroll_pen": settled_bank,
            "available_bankroll_pen": avail_bank,
            "pending_stake_pen": pending_stake,
            "net_profit_pen": round(float(metrics.get("net_profit_pen", 0.0)), 2),
            "roi_pct": round(float(metrics.get("roi_pct", 0.0)), 2),
            "mean_clv_pct": _round_or_none(metrics.get("mean_clv_pct"), 2),
            "clv_sample_size": int(metrics.get("clv_sample_size") or 0),
            "brier_score": _round_or_none(metrics.get("model_brier_on_market_subset"), 4),
            "market_brier": _round_or_none(metrics.get("market_brier_score"), 4),
            "market_sample_size": int(metrics.get("market_comparison_sample_size") or 0),
            "pending_count": pending_cnt,
            "settled_real_count": sum(1 for b in espn_real_bets if (b.get("estado") or b.get("status")) != "PENDING"),
            "won_real_count": sum(1 for b in espn_real_bets if (b.get("estado") or b.get("status")) == "WON"),
            "lost_real_count": sum(1 for b in espn_real_bets if (b.get("estado") or b.get("status")) == "LOST"),
            "props_count": len(player_props or []),
        },
        "slate": slate_items,
        "real_bets": espn_real_bets,
        "player_props": player_props or [],
    }

    if props_paper_trading is None and db is not None:
        try:
            from src.reporting.dashboard_export import _compute_clean_props_metrics

            props_paper_trading = _compute_clean_props_metrics(
                db=db,
                initial_bankroll_pen=float(risk_cfg.virtual_bankroll_initial_pen),
            )
        except Exception:
            props_paper_trading = {}

    if props_paper_trading and "recent_settled" in props_paper_trading:
        props_paper_trading = dict(props_paper_trading)
        props_paper_trading["recent_settled"] = [
            r
            for r in (props_paper_trading.get("recent_settled") or [])
            if r.get("status") in ("WON", "LOST", "PUSH")
        ]

    payload["props_paper_trading"] = props_paper_trading or {}
    data_json = json.dumps(payload, ensure_ascii=False)
    team_dict_json = get_teams_json_for_frontend()
    peru_books_json = get_peru_sportsbooks_json_for_frontend()

    html = render_dashboard_markup(
        avail_bank=avail_bank,
        settled_bank=settled_bank,
        pending_cnt=pending_cnt,
        pending_stake=pending_stake,
        min_ev_pct=min_ev_pct,
    ) + render_dashboard_scripts(
        data_json=data_json,
        team_dict_json=team_dict_json,
        peru_books_json=peru_books_json,
        settled_bank=settled_bank,
        min_ev_pct=min_ev_pct,
        kelly_pct=kelly_pct,
    )

    out = Path(html_output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return str(out)
