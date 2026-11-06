"""Canonical normalization for NBA teams, seasons, identifiers, and odds formats."""

from __future__ import annotations

from src.utils.team_dictionary import (
    NBA_TEAMS as RAW_NBA_TEAMS,
    TEAM_ALIASES,
    format_matchup,
    format_matchup_string,
    get_team,
    get_team_code,
    get_team_full_name,
)

# Backward-compatible dictionary of dicts
NBA_TEAMS: dict[str, dict[str, str]] = {
    code: info.to_dict() for code, info in RAW_NBA_TEAMS.items()
}


def normalize_team_code(raw_team: str) -> str:
    """Normalizes any NBA team name or abbreviation to its canonical 3-letter code."""
    if not raw_team or not isinstance(raw_team, str):
        raise ValueError(f"Invalid team identifier: {raw_team!r}")
    cleaned = raw_team.strip().upper()
    if cleaned in TEAM_ALIASES:
        return TEAM_ALIASES[cleaned]
    raise ValueError(f"Unrecognized NBA team identifier: {raw_team!r}")



def normalize_season(raw_season: str | int) -> str:
    """Normalizes season representation into 'YYYY-YY' format (e.g., '2026-27')."""
    s = str(raw_season).strip()
    if len(s) == 7 and s[4] == "-":
        return s
    if len(s) == 4 and s.isdigit():
        year = int(s)
        next_short = str((year + 1) % 100).zfill(2)
        return f"{year}-{next_short}"
    raise ValueError(f"Invalid season format: {raw_season!r}")


def american_to_decimal_odds(american_odds: str | int | float) -> float:
    """Converts American odds (e.g., -135, +114) into rounded 4-decimal Decimal odds."""
    if american_odds is None:
        raise ValueError("American odds cannot be None")
    s = str(american_odds).strip().upper()
    if s in ("EVEN", "EV"):
        return 2.0
    val = float(s.replace("+", ""))
    if abs(val) < 100:
        raise ValueError(f"Invalid American odds value: {american_odds!r}")
    if val > 0:
        return round(1.0 + (val / 100.0), 4)
    return round(1.0 + (100.0 / abs(val)), 4)
