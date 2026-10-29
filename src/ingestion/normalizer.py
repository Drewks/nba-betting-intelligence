"""Canonical normalization for NBA teams, seasons, identifiers, and odds formats."""

from __future__ import annotations

NBA_TEAMS: dict[str, dict[str, str]] = {
    "ATL": {"full_name": "Atlanta Hawks", "conference": "East", "division": "Southeast"},
    "BOS": {"full_name": "Boston Celtics", "conference": "East", "division": "Atlantic"},
    "BKN": {"full_name": "Brooklyn Nets", "conference": "East", "division": "Atlantic"},
    "CHA": {"full_name": "Charlotte Hornets", "conference": "East", "division": "Southeast"},
    "CHI": {"full_name": "Chicago Bulls", "conference": "East", "division": "Central"},
    "CLE": {"full_name": "Cleveland Cavaliers", "conference": "East", "division": "Central"},
    "DAL": {"full_name": "Dallas Mavericks", "conference": "West", "division": "Southwest"},
    "DEN": {"full_name": "Denver Nuggets", "conference": "West", "division": "Northwest"},
    "DET": {"full_name": "Detroit Pistons", "conference": "East", "division": "Central"},
    "GSW": {"full_name": "Golden State Warriors", "conference": "West", "division": "Pacific"},
    "HOU": {"full_name": "Houston Rockets", "conference": "West", "division": "Southwest"},
    "IND": {"full_name": "Indiana Pacers", "conference": "East", "division": "Central"},
    "LAC": {"full_name": "LA Clippers", "conference": "West", "division": "Pacific"},
    "LAL": {"full_name": "Los Angeles Lakers", "conference": "West", "division": "Pacific"},
    "MEM": {"full_name": "Memphis Grizzlies", "conference": "West", "division": "Southwest"},
    "MIA": {"full_name": "Miami Heat", "conference": "East", "division": "Southeast"},
    "MIL": {"full_name": "Milwaukee Bucks", "conference": "East", "division": "Central"},
    "MIN": {"full_name": "Minnesota Timberwolves", "conference": "West", "division": "Northwest"},
    "NOP": {"full_name": "New Orleans Pelicans", "conference": "West", "division": "Southwest"},
    "NYK": {"full_name": "New York Knicks", "conference": "East", "division": "Atlantic"},
    "OKC": {"full_name": "Oklahoma City Thunder", "conference": "West", "division": "Northwest"},
    "ORL": {"full_name": "Orlando Magic", "conference": "East", "division": "Southeast"},
    "PHI": {"full_name": "Philadelphia 76ers", "conference": "East", "division": "Atlantic"},
    "PHX": {"full_name": "Phoenix Suns", "conference": "West", "division": "Pacific"},
    "POR": {"full_name": "Portland Trail Blazers", "conference": "West", "division": "Northwest"},
    "SAC": {"full_name": "Sacramento Kings", "conference": "West", "division": "Pacific"},
    "SAS": {"full_name": "San Antonio Spurs", "conference": "West", "division": "Southwest"},
    "TOR": {"full_name": "Toronto Raptors", "conference": "East", "division": "Atlantic"},
    "UTA": {"full_name": "Utah Jazz", "conference": "West", "division": "Northwest"},
    "WAS": {"full_name": "Washington Wizards", "conference": "East", "division": "Southeast"},
}

TEAM_ALIASES: dict[str, str] = {
    "GS": "GSW",
    "NY": "NYK",
    "NO": "NOP",
    "NOP": "NOP",
    "SA": "SAS",
    "UTAH": "UTA",
    "WSH": "WAS",
    "PHO": "PHX",
    "BRK": "BKN",
    "CHO": "CHA",
    "LOS ANGELES CLIPPERS": "LAC",
}

for code, meta in NBA_TEAMS.items():
    TEAM_ALIASES[code] = code
    TEAM_ALIASES[meta["full_name"].upper()] = code
    short_Mascot = meta["full_name"].split()[-1].upper()
    TEAM_ALIASES[short_Mascot] = code


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
