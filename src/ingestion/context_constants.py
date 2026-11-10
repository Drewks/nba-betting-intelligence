"""
Contextual NBA domain constants for ingestion adapters:
- Star player spread point values
- High-altitude home court bonuses
- NBA referee crew profiles (over/under and home margin tendencies)
- Long-term injury classification keywords
"""

from __future__ import annotations

# High-impact NBA star players (estimated point spread value when ruled OUT)
STAR_PLAYER_IMPACT_PTS: dict[str, float] = {
    "Nikola Jokic": 6.8,
    "Luka Doncic": 6.2,
    "Shai Gilgeous-Alexander": 6.0,
    "Giannis Antetokounmpo": 6.0,
    "Joel Embiid": 5.8,
    "Victor Wembanyama": 5.2,
    "Jayson Tatum": 4.8,
    "Stephen Curry": 5.0,
    "Anthony Davis": 4.5,
    "Kevin Durant": 4.5,
    "LeBron James": 4.2,
    "Devin Booker": 4.2,
    "Anthony Edwards": 4.0,
    "Donovan Mitchell": 4.0,
    "Jalen Brunson": 4.0,
    "Tyrese Haliburton": 3.8,
    "Domantas Sabonis": 3.8,
    "Trae Young": 3.8,
    "Ja Morant": 4.0,
    "Damian Lillard": 3.6,
    "Jimmy Butler": 3.5,
    "Zion Williamson": 3.8,
    "Chet Holmgren": 3.5,
    "Jaylen Brown": 3.5,
    "Bam Adebayo": 3.5,
    "De'Aaron Fox": 3.6,
    "Karl-Anthony Towns": 3.4,
    "Kyrie Irving": 3.5,
    "James Harden": 3.3,
    "Paul George": 3.3,
    "Jusuf Nurkic": 2.2,
    "Tobias Harris": 2.0,
}

# High-altitude home courts (extra home advantage in points)
HIGH_ALTITUDE_BONUS_PTS: dict[str, float] = {
    "DEN": 1.6,  # Mile High (1,609m)
    "UTA": 1.1,  # Salt Lake City (1,288m)
}

# NBA Official Referee Crew Profiles: (total_points_delta_per_ref, home_margin_delta_per_ref)
NBA_REFEREE_CREW_PROFILE: dict[str, tuple[float, float]] = {
    "Scott Foster": (1.35, 0.35),
    "Tony Brothers": (1.45, 0.40),
    "Marc Davis": (-1.10, -0.15),
    "Zach Zarba": (0.85, 0.25),
    "James Capers": (-0.95, 0.10),
    "Josh Tiven": (0.70, 0.20),
    "Courtney Kirkland": (0.90, 0.15),
    "Sean Wright": (0.65, 0.10),
    "Curtis Blair": (0.80, 0.20),
    "Ben Taylor": (1.05, 0.15),
    "Ed Malloy": (0.55, 0.25),
    "JB DeRosa": (0.95, 0.10),
    "Bill Kennedy": (-0.75, -0.10),
    "Kevin Scott": (0.60, 0.15),
    "Mitchell Ervin": (1.10, 0.20),
    "Rodney Mott": (-0.85, 0.05),
    "Tyler Ford": (0.90, 0.20),
    "David Guthrie": (-0.65, 0.10),
    "James Williams": (0.75, 0.15),
}

LONG_TERM_INJURY_KEYWORDS: tuple[str, ...] = (
    "out for season",
    "indefinitely",
    "surgery",
    "torn",
    "fracture",
    "weeks",
    "months",
    "acl",
    "achilles",
)
