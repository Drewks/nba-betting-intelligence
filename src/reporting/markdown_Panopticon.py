"""
Panopticon Markdown & Bet Tracking Dashboard Generator (`SEGUIMIENTO_APUESTAS.md`).

Provides dynamic risk/staking headers from `config/model_config.yaml`, recomputed
chronological observed running bankroll across `v_observed_simulated_bets`, and
truthful Player Props & SGP settlement tables (excluding synthetic `VOID` rows).
"""

from __future__ import annotations

from src.reporting.dashboard_export import (
    _compute_clean_props_metrics,
    export_bets_and_tracking_dashboard,
    generate_bet_tracking_markdown,
)
from src.reporting.slate_intelligence import (
    compute_upcoming_slate_intelligence,
    generate_slate_intelligence_markdown,
)

__all__ = [
    "_compute_clean_props_metrics",
    "compute_upcoming_slate_intelligence",
    "export_bets_and_tracking_dashboard",
    "generate_bet_tracking_markdown",
    "generate_slate_intelligence_markdown",
]
