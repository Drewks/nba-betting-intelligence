"""
Canonical NBA Team Dictionary & Matchup Formatter (`src/utils/team_dictionary.py`).
Provides the single source of truth for all 30 NBA franchises:
- Canonical 3-letter codes
- Full franchise names, cities, and mascots
- Conference, division, and official brand colors
- Case-insensitive alias and nickname resolver
- Robust, idempotent matchup formatting functions for backend and frontend
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re


@dataclass(frozen=True)
class TeamInfo:
    code: str
    city: str
    name: str
    full_name: str
    conference: str
    division: str
    primary_color: str
    secondary_color: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


# All 30 Canonical NBA Teams
NBA_TEAMS: dict[str, TeamInfo] = {
    "ATL": TeamInfo("ATL", "Atlanta", "Hawks", "Atlanta Hawks", "East", "Southeast", "#E03A3E", "#C1D32F"),
    "BOS": TeamInfo("BOS", "Boston", "Celtics", "Boston Celtics", "East", "Atlantic", "#007A33", "#BA9653"),
    "BKN": TeamInfo("BKN", "Brooklyn", "Nets", "Brooklyn Nets", "East", "Atlantic", "#000000", "#FFFFFF"),
    "CHA": TeamInfo("CHA", "Charlotte", "Hornets", "Charlotte Hornets", "East", "Southeast", "#1D1160", "#00788C"),
    "CHI": TeamInfo("CHI", "Chicago", "Bulls", "Chicago Bulls", "East", "Central", "#CE1141", "#000000"),
    "CLE": TeamInfo("CLE", "Cleveland", "Cavaliers", "Cleveland Cavaliers", "East", "Central", "#860038", "#041E42"),
    "DAL": TeamInfo("DAL", "Dallas", "Mavericks", "Dallas Mavericks", "West", "Southwest", "#00538C", "#002B5E"),
    "DEN": TeamInfo("DEN", "Denver", "Nuggets", "Denver Nuggets", "West", "Northwest", "#0E2240", "#FEC524"),
    "DET": TeamInfo("DET", "Detroit", "Pistons", "Detroit Pistons", "East", "Central", "#C8102E", "#1D42BA"),
    "GSW": TeamInfo("GSW", "Golden State", "Warriors", "Golden State Warriors", "West", "Pacific", "#1D428A", "#FFC72C"),
    "HOU": TeamInfo("HOU", "Houston", "Rockets", "Houston Rockets", "West", "Southwest", "#CE1141", "#000000"),
    "IND": TeamInfo("IND", "Indiana", "Pacers", "Indiana Pacers", "East", "Central", "#002D62", "#FDBB30"),
    "LAC": TeamInfo("LAC", "LA", "Clippers", "LA Clippers", "West", "Pacific", "#C8102E", "#1D428A"),
    "LAL": TeamInfo("LAL", "Los Angeles", "Lakers", "Los Angeles Lakers", "West", "Pacific", "#552583", "#FDB927"),
    "MEM": TeamInfo("MEM", "Memphis", "Grizzlies", "Memphis Grizzlies", "West", "Southwest", "#5D76A9", "#12173F"),
    "MIA": TeamInfo("MIA", "Miami", "Heat", "Miami Heat", "East", "Southeast", "#98002E", "#F9A01B"),
    "MIL": TeamInfo("MIL", "Milwaukee", "Bucks", "Milwaukee Bucks", "East", "Central", "#00471B", "#EEE1C6"),
    "MIN": TeamInfo("MIN", "Minnesota", "Timberwolves", "Minnesota Timberwolves", "West", "Northwest", "#0C2340", "#236192"),
    "NOP": TeamInfo("NOP", "New Orleans", "Pelicans", "New Orleans Pelicans", "West", "Southwest", "#0C2340", "#C8102E"),
    "NYK": TeamInfo("NYK", "New York", "Knicks", "New York Knicks", "East", "Atlantic", "#006BB6", "#F58426"),
    "OKC": TeamInfo("OKC", "Oklahoma City", "Thunder", "Oklahoma City Thunder", "West", "Northwest", "#007AC1", "#EF3B24"),
    "ORL": TeamInfo("ORL", "Orlando", "Magic", "Orlando Magic", "East", "Southeast", "#0077C0", "#C4CED4"),
    "PHI": TeamInfo("PHI", "Philadelphia", "76ers", "Philadelphia 76ers", "East", "Atlantic", "#006BB6", "#ED174C"),
    "PHX": TeamInfo("PHX", "Phoenix", "Suns", "Phoenix Suns", "West", "Pacific", "#1D1160", "#E56020"),
    "POR": TeamInfo("POR", "Portland", "Trail Blazers", "Portland Trail Blazers", "West", "Northwest", "#E03A3E", "#000000"),
    "SAC": TeamInfo("SAC", "Sacramento", "Kings", "Sacramento Kings", "West", "Pacific", "#5A2D81", "#63727A"),
    "SAS": TeamInfo("SAS", "San Antonio", "Spurs", "San Antonio Spurs", "West", "Southwest", "#C4CED4", "#000000"),
    "TOR": TeamInfo("TOR", "Toronto", "Raptors", "Toronto Raptors", "East", "Atlantic", "#CE1141", "#000000"),
    "UTA": TeamInfo("UTA", "Utah", "Jazz", "Utah Jazz", "West", "Northwest", "#002B5C", "#00471B"),
    "WAS": TeamInfo("WAS", "Washington", "Wizards", "Washington Wizards", "East", "Southeast", "#002B5C", "#E31837"),
}


# Common abbreviations and historical aliases
TEAM_ALIASES: dict[str, str] = {
    "GS": "GSW",
    "GOLDEN STATE": "GSW",
    "WARRIORS": "GSW",
    "NY": "NYK",
    "NEW YORK": "NYK",
    "KNICKS": "NYK",
    "NO": "NOP",
    "NEW ORLEANS": "NOP",
    "PELICANS": "NOP",
    "SA": "SAS",
    "SAN ANTONIO": "SAS",
    "SPURS": "SAS",
    "UTAH": "UTA",
    "JAZZ": "UTA",
    "WSH": "WAS",
    "WASHINGTON": "WAS",
    "WIZARDS": "WAS",
    "PHO": "PHX",
    "PHOENIX": "PHX",
    "SUNS": "PHX",
    "BRK": "BKN",
    "BROOKLYN": "BKN",
    "NETS": "BKN",
    "CHO": "CHA",
    "CHARLOTTE": "CHA",
    "HORNETS": "CHA",
    "LOS ANGELES CLIPPERS": "LAC",
    "LA CLIPPERS": "LAC",
    "CLIPPERS": "LAC",
    "LOS ANGELES LAKERS": "LAL",
    "LA LAKERS": "LAL",
    "LAKERS": "LAL",
    "BOSTON": "BOS",
    "CELTICS": "BOS",
    "ATLANTA": "ATL",
    "HAWKS": "ATL",
    "CHICAGO": "CHI",
    "BULLS": "CHI",
    "CLEVELAND": "CLE",
    "CAVALIERS": "CLE",
    "CAVS": "CLE",
    "DALLAS": "DAL",
    "MAVERICKS": "DAL",
    "MAVS": "DAL",
    "DENVER": "DEN",
    "NUGGETS": "DEN",
    "DETROIT": "DET",
    "PISTONS": "DET",
    "HOUSTON": "HOU",
    "ROCKETS": "HOU",
    "INDIANA": "IND",
    "PACERS": "IND",
    "MEMPHIS": "MEM",
    "GRIZZLIES": "MEM",
    "MIAMI": "MIA",
    "HEAT": "MIA",
    "MILWAUKEE": "MIL",
    "BUCKS": "MIL",
    "MINNESOTA": "MIN",
    "TIMBERWOLVES": "MIN",
    "WOLVES": "MIN",
    "OKLAHOMA CITY": "OKC",
    "OKLAHOMA": "OKC",
    "THUNDER": "OKC",
    "ORLANDO": "ORL",
    "MAGIC": "ORL",
    "PHILADELPHIA": "PHI",
    "76ERS": "PHI",
    "SIXERS": "PHI",
    "PORTLAND": "POR",
    "TRAIL BLAZERS": "POR",
    "BLAZERS": "POR",
    "SACRAMENTO": "SAC",
    "KINGS": "SAC",
    "TORONTO": "TOR",
    "RAPTORS": "TOR",
}

# Auto-populate canonical codes, full names, and mascots into alias map
for code, meta in NBA_TEAMS.items():
    TEAM_ALIASES[code] = code
    TEAM_ALIASES[meta.full_name.upper()] = code
    TEAM_ALIASES[meta.name.upper()] = code
    TEAM_ALIASES[meta.city.upper()] = code


def get_team(identifier: str | None) -> TeamInfo | None:
    """Safely retrieves a TeamInfo dataclass by code, mascot, city, or alias. Never raises."""
    if not identifier or not isinstance(identifier, str):
        return None
    cleaned = identifier.strip().upper()
    code = TEAM_ALIASES.get(cleaned)
    if code and code in NBA_TEAMS:
        return NBA_TEAMS[code]
    return NBA_TEAMS.get(cleaned)


def get_team_full_name(identifier: str | None, default: str | None = None) -> str:
    """Returns the full team name (e.g. 'Phoenix Suns') or fallback."""
    team = get_team(identifier)
    if team:
        return team.full_name
    return default if default is not None else (str(identifier) if identifier else "")


def get_team_code(identifier: str | None, default: str | None = None) -> str:
    """Returns canonical 3-letter code (e.g. 'PHX') or fallback."""
    team = get_team(identifier)
    if team:
        return team.code
    return default if default is not None else (str(identifier) if identifier else "")


def format_matchup(away: str | None, home: str | None) -> str:
    """
    Returns standard display string: 'Orlando Magic @ Phoenix Suns (ORL @ PHX)'.
    Safely resolves codes, names, or mixed identifiers.
    """
    away_team = get_team(away)
    home_team = get_team(home)
    away_name = away_team.full_name if away_team else (away or "Desconocido")
    home_name = home_team.full_name if home_team else (home or "Desconocido")
    away_code = away_team.code if away_team else (away or "—")
    home_code = home_team.code if home_team else (home or "—")
    return f"{away_name} @ {home_name} ({away_code} @ {home_code})"


def format_matchup_string(text: str | None) -> str:
    """
    Idempotent matchup string formatter.
    Handles:
    - 'ORL @ PHX' -> 'Orlando Magic @ Phoenix Suns (ORL @ PHX)'
    - 'Orlando Magic @ Phoenix Suns (ORL @ PHX)' -> preserved as-is
    - 'Total Under 228.5 (SAS @ SAC)' -> 'Total Under 228.5 (San Antonio Spurs @ Sacramento Kings [SAS @ SAC])'
    """
    if not text or not isinstance(text, str):
        return ""

    # Check if already fully formatted with franchise names
    if any(team.full_name in text for team in NBA_TEAMS.values()):
        return text

    # Handle standard 'AWAY @ HOME'
    if " @ " in text:
        # Check if inside parentheses (e.g. Total Over 220 (LAL @ BOS))
        paren_match = re.search(r"\(([A-Z]{2,4})\s*@\s*([A-Z]{2,4})\)", text)
        if paren_match:
            away_c, home_c = paren_match.groups()
            away_team = get_team(away_c)
            home_team = get_team(home_c)
            if away_team and home_team:
                replacement = f"({away_team.full_name} @ {home_team.full_name} [{away_team.code} @ {home_team.code}])"
                return text[:paren_match.start()] + replacement + text[paren_match.end():]

        parts = text.split(" @ ")
        if len(parts) == 2:
            away_raw = parts[0].strip()
            home_raw = parts[1].strip()
            away_team = get_team(away_raw)
            home_team = get_team(home_raw)
            if away_team and home_team:
                return format_matchup(away_team.code, home_team.code)

    return text


def get_teams_json_for_frontend() -> str:
    """Returns serialized JSON structure for embedding in HTML templates."""
    data = {
        "teams": {k: v.to_dict() for k, v in NBA_TEAMS.items()},
        "aliases": TEAM_ALIASES,
    }
    return json.dumps(data, ensure_ascii=False)
