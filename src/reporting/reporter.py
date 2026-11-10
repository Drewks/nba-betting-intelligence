"""
Reporting & Obsidian Vault Synchronization (`src/reporting/reporter.py`).
Facade re-exporting all reporting, slate intelligence, dashboard exports, and Obsidian synchronization:
- _fmt
- compute_upcoming_slate_intelligence
- export_bets_and_tracking_dashboard
- generate_daily_report
- generate_weekly_report
- generate_audit_report
- sync_obsidian_vault
"""

from __future__ import annotations

from src.reporting.audit_report import generate_audit_report
from src.reporting.daily_report import generate_daily_report
from src.reporting.dashboard_export import export_bets_and_tracking_dashboard
from src.reporting.obsidian_sync import sync_obsidian_vault
from src.reporting.slate_intelligence import (
    _fmt,
    compute_upcoming_slate_intelligence,
)
from src.reporting.weekly_report import generate_weekly_report

__all__ = [
    "_fmt",
    "compute_upcoming_slate_intelligence",
    "export_bets_and_tracking_dashboard",
    "generate_audit_report",
    "generate_daily_report",
    "generate_weekly_report",
    "sync_obsidian_vault",
]
