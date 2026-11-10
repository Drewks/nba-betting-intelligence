"""
NBA Player Props Constants and Baseline Priors (`src/prediction/props_constants.py`).
Contains per-player statistical baselines, defensive multipliers (DvP), and fallback rosters.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Canonical baseline player profiles (Per-Minute production, Usage Rate %, and Base Minutes)
# Format: (base_minutes, usg_pct, pts_per_min, reb_per_min, ast_per_min, threes_per_min)
PLAYER_PROP_BASELINES: dict[str, tuple[float, float, float, float, float, float]] = {
    # 1. Dallas Mavericks (DAL)
    "Luka Doncic": (36.5, 35.5, 0.88, 0.25, 0.26, 0.11),
    "Kyrie Irving": (34.0, 27.5, 0.74, 0.14, 0.15, 0.08),
    "Klay Thompson": (28.0, 21.0, 0.55, 0.12, 0.06, 0.10),
    "PJ Washington": (30.0, 16.5, 0.42, 0.21, 0.06, 0.05),
    "Dereck Lively II": (26.0, 14.0, 0.36, 0.32, 0.05, 0.00),
    "Daniel Gafford": (24.0, 15.5, 0.48, 0.32, 0.05, 0.00),

    # 2. Denver Nuggets (DEN)
    "Nikola Jokic": (36.0, 30.5, 0.82, 0.35, 0.28, 0.04),
    "Jamal Murray": (33.0, 25.5, 0.65, 0.13, 0.18, 0.07),
    "Michael Porter Jr.": (32.0, 20.0, 0.56, 0.24, 0.05, 0.08),
    "Aaron Gordon": (30.0, 18.0, 0.48, 0.22, 0.10, 0.03),
    "Christian Braun": (28.0, 16.0, 0.45, 0.17, 0.07, 0.04),

    # 3. Boston Celtics (BOS)
    "Jayson Tatum": (35.5, 29.5, 0.77, 0.24, 0.14, 0.09),
    "Jaylen Brown": (33.5, 28.0, 0.72, 0.17, 0.11, 0.07),
    "Derrick White": (32.0, 19.5, 0.49, 0.13, 0.16, 0.08),
    "Jrue Holiday": (30.0, 17.0, 0.42, 0.16, 0.15, 0.06),
    "Kristaps Porzingis": (28.0, 24.5, 0.68, 0.24, 0.06, 0.06),
    "Payton Pritchard": (25.0, 21.0, 0.58, 0.12, 0.13, 0.11),
    "Al Horford": (26.0, 14.0, 0.35, 0.24, 0.11, 0.06),

    # 4. Golden State Warriors (GSW)
    "Stephen Curry": (32.5, 31.0, 0.84, 0.14, 0.16, 0.14),
    "Jonathan Kuminga": (27.0, 24.0, 0.62, 0.19, 0.07, 0.03),
    "Andrew Wiggins": (28.0, 20.5, 0.52, 0.16, 0.06, 0.05),
    "Draymond Green": (27.5, 14.5, 0.32, 0.26, 0.22, 0.03),
    "Buddy Hield": (25.0, 23.5, 0.66, 0.14, 0.09, 0.13),
    "Brandin Podziemski": (26.0, 16.5, 0.38, 0.20, 0.14, 0.04),

    # 5. Phoenix Suns (PHX)
    "Kevin Durant": (36.0, 29.0, 0.78, 0.19, 0.14, 0.06),
    "Devin Booker": (35.5, 29.5, 0.76, 0.13, 0.20, 0.06),
    "Bradley Beal": (31.0, 22.5, 0.58, 0.13, 0.14, 0.05),
    "Jusuf Nurkic": (25.0, 18.5, 0.43, 0.41, 0.12, 0.02),
    "Tyus Jones": (28.0, 15.0, 0.38, 0.10, 0.24, 0.04),

    # 6. Los Angeles Lakers (LAL)
    "LeBron James": (34.5, 28.5, 0.70, 0.22, 0.24, 0.06),
    "Anthony Davis": (35.5, 28.0, 0.74, 0.36, 0.09, 0.02),
    "Austin Reaves": (32.0, 19.5, 0.49, 0.13, 0.17, 0.05),
    "D'Angelo Russell": (28.0, 22.0, 0.56, 0.10, 0.19, 0.08),
    "Rui Hachimura": (29.0, 17.5, 0.46, 0.18, 0.04, 0.05),

    # 7. Oklahoma City Thunder (OKC)
    "Shai Gilgeous-Alexander": (35.0, 32.5, 0.87, 0.16, 0.18, 0.05),
    "Jalen Williams": (32.5, 23.5, 0.60, 0.14, 0.14, 0.05),
    "Chet Holmgren": (30.0, 21.0, 0.56, 0.27, 0.08, 0.05),
    "Alex Caruso": (24.0, 14.5, 0.36, 0.15, 0.13, 0.05),
    "Luguentz Dort": (28.0, 16.5, 0.41, 0.14, 0.05, 0.06),

    # 8. Milwaukee Bucks (MIL)
    "Giannis Antetokounmpo": (35.0, 34.5, 0.89, 0.34, 0.19, 0.01),
    "Damian Lillard": (34.5, 28.5, 0.73, 0.13, 0.20, 0.09),
    "Brook Lopez": (29.0, 16.5, 0.43, 0.18, 0.05, 0.06),
    "Bobby Portis": (25.0, 23.0, 0.56, 0.30, 0.05, 0.04),
    "Khris Middleton": (28.0, 23.0, 0.56, 0.16, 0.18, 0.06),

    # 9. New York Knicks (NYK)
    "Jalen Brunson": (35.5, 31.0, 0.81, 0.11, 0.20, 0.08),
    "Karl-Anthony Towns": (34.0, 27.0, 0.73, 0.37, 0.10, 0.07),
    "Mikal Bridges": (36.0, 20.0, 0.51, 0.12, 0.10, 0.06),
    "OG Anunoby": (34.0, 18.0, 0.48, 0.15, 0.06, 0.06),
    "Josh Hart": (34.0, 15.0, 0.38, 0.27, 0.14, 0.03),

    # 10. Minnesota Timberwolves (MIN)
    "Anthony Edwards": (35.5, 32.0, 0.78, 0.16, 0.15, 0.10),
    "Julius Randle": (33.0, 27.5, 0.67, 0.26, 0.15, 0.05),
    "Rudy Gobert": (32.0, 15.0, 0.42, 0.39, 0.04, 0.00),
    "Mike Conley": (26.0, 15.5, 0.36, 0.10, 0.21, 0.06),
    "Naz Reid": (26.0, 22.0, 0.58, 0.23, 0.07, 0.08),
    "Jaden McDaniels": (30.0, 15.5, 0.39, 0.12, 0.05, 0.04),

    # 11. Philadelphia 76ers (PHI)
    "Joel Embiid": (34.0, 36.5, 0.95, 0.34, 0.16, 0.04),
    "Tyrese Maxey": (36.5, 29.5, 0.75, 0.10, 0.17, 0.08),
    "Paul George": (33.0, 26.5, 0.67, 0.17, 0.13, 0.08),
    "Kelly Oubre Jr.": (30.0, 21.0, 0.52, 0.17, 0.04, 0.05),
    "Jared McCain": (25.0, 22.5, 0.58, 0.11, 0.10, 0.08),

    # 12. Cleveland Cavaliers (CLE)
    "Donovan Mitchell": (34.5, 31.0, 0.80, 0.14, 0.18, 0.10),
    "Darius Garland": (32.0, 25.0, 0.65, 0.09, 0.22, 0.08),
    "Evan Mobley": (31.5, 22.0, 0.58, 0.28, 0.10, 0.03),
    "Jarrett Allen": (31.0, 17.5, 0.49, 0.35, 0.07, 0.00),
    "Caris LeVert": (25.0, 21.0, 0.52, 0.13, 0.16, 0.05),

    # 13. Indiana Pacers (IND)
    "Tyrese Haliburton": (34.0, 25.0, 0.62, 0.12, 0.29, 0.08),
    "Pascal Siakam": (33.0, 25.5, 0.66, 0.23, 0.12, 0.04),
    "Myles Turner": (28.0, 21.0, 0.58, 0.25, 0.05, 0.06),
    "Bennedict Mathurin": (28.0, 24.0, 0.64, 0.18, 0.07, 0.05),
    "Andrew Nembhard": (27.0, 16.5, 0.41, 0.09, 0.18, 0.03),

    # 14. Sacramento Kings (SAC)
    "De'Aaron Fox": (35.0, 30.5, 0.77, 0.14, 0.18, 0.08),
    "DeMar DeRozan": (34.5, 26.5, 0.68, 0.13, 0.16, 0.03),
    "Domantas Sabonis": (35.5, 22.0, 0.56, 0.38, 0.24, 0.02),
    "Keegan Murray": (33.0, 18.5, 0.46, 0.19, 0.05, 0.07),
    "Malik Monk": (26.0, 24.5, 0.60, 0.11, 0.19, 0.07),

    # 15. Memphis Grizzlies (MEM)
    "Ja Morant": (32.0, 32.5, 0.78, 0.14, 0.25, 0.05),
    "Desmond Bane": (32.5, 26.0, 0.68, 0.15, 0.16, 0.09),
    "Jaren Jackson Jr.": (30.0, 28.0, 0.74, 0.21, 0.06, 0.06),
    "Marcus Smart": (26.0, 18.5, 0.44, 0.11, 0.16, 0.05),
    "Zach Edey": (22.0, 21.0, 0.55, 0.38, 0.04, 0.00),

    # 16. Miami Heat (MIA)
    "Jimmy Butler": (33.0, 25.5, 0.65, 0.17, 0.17, 0.03),
    "Bam Adebayo": (34.0, 24.5, 0.59, 0.31, 0.13, 0.03),
    "Tyler Herro": (34.0, 27.5, 0.71, 0.15, 0.16, 0.10),
    "Terry Rozier": (31.0, 22.0, 0.52, 0.12, 0.15, 0.07),

    # 17. Orlando Magic (ORL)
    "Paolo Banchero": (35.0, 31.0, 0.76, 0.22, 0.16, 0.05),
    "Franz Wagner": (34.0, 28.0, 0.69, 0.17, 0.14, 0.06),
    "Jalen Suggs": (29.0, 21.0, 0.52, 0.14, 0.14, 0.08),
    "Wendell Carter Jr.": (26.0, 17.5, 0.44, 0.32, 0.07, 0.04),

    # 18. Houston Rockets (HOU)
    "Alperen Sengun": (31.5, 27.0, 0.62, 0.33, 0.16, 0.02),
    "Jalen Green": (32.5, 28.0, 0.67, 0.16, 0.10, 0.09),
    "Fred VanVleet": (34.0, 20.0, 0.48, 0.11, 0.19, 0.07),
    "Jabari Smith Jr.": (29.0, 18.0, 0.45, 0.25, 0.04, 0.05),
    "Amen Thompson": (26.0, 19.0, 0.48, 0.26, 0.12, 0.01),

    # 19. San Antonio Spurs (SAS)
    "Victor Wembanyama": (32.0, 32.0, 0.79, 0.34, 0.12, 0.08),
    "Chris Paul": (27.5, 16.0, 0.38, 0.13, 0.29, 0.05),
    "Devin Vassell": (32.0, 24.5, 0.62, 0.13, 0.12, 0.08),
    "Keldon Johnson": (26.0, 22.5, 0.56, 0.21, 0.07, 0.05),
    "Harrison Barnes": (28.0, 16.5, 0.44, 0.14, 0.06, 0.05),

    # 20. Atlanta Hawks (ATL)
    "Trae Young": (36.0, 32.5, 0.77, 0.09, 0.31, 0.08),
    "Jalen Johnson": (35.5, 24.0, 0.58, 0.29, 0.16, 0.04),
    "De'Andre Hunter": (28.0, 22.0, 0.57, 0.15, 0.05, 0.07),
    "Clint Capela": (24.0, 16.5, 0.45, 0.42, 0.04, 0.00),
    "Dyson Daniels": (32.0, 18.0, 0.44, 0.16, 0.13, 0.04),

    # 21. Brooklyn Nets (BKN)
    "Cam Thomas": (33.0, 30.5, 0.78, 0.11, 0.11, 0.08),
    "Dennis Schroder": (31.5, 23.5, 0.58, 0.10, 0.21, 0.06),
    "Cameron Johnson": (30.0, 20.0, 0.54, 0.15, 0.09, 0.08),
    "Nicolas Claxton": (28.0, 15.0, 0.42, 0.35, 0.07, 0.00),

    # 22. Toronto Raptors (TOR)
    "Scottie Barnes": (34.0, 26.5, 0.62, 0.25, 0.19, 0.04),
    "RJ Barrett": (32.5, 28.0, 0.70, 0.19, 0.16, 0.05),
    "Immanuel Quickley": (31.0, 25.0, 0.61, 0.13, 0.20, 0.08),
    "Jakob Poeltl": (29.0, 18.0, 0.49, 0.38, 0.09, 0.00),
    "Gradey Dick": (28.0, 22.0, 0.58, 0.11, 0.06, 0.08),

    # 23. Chicago Bulls (CHI)
    "Zach LaVine": (34.5, 28.0, 0.72, 0.16, 0.14, 0.09),
    "Nikola Vucevic": (32.0, 24.5, 0.64, 0.33, 0.11, 0.06),
    "Coby White": (33.5, 25.0, 0.62, 0.12, 0.15, 0.09),
    "Josh Giddey": (28.0, 23.0, 0.51, 0.23, 0.24, 0.04),

    # 24. Charlotte Hornets (CHA)
    "LaMelo Ball": (34.0, 33.5, 0.85, 0.16, 0.22, 0.11),
    "Brandon Miller": (32.0, 25.5, 0.64, 0.15, 0.11, 0.09),
    "Miles Bridges": (33.0, 23.0, 0.56, 0.22, 0.10, 0.06),
    "Tre Mann": (26.0, 25.0, 0.63, 0.13, 0.14, 0.08),

    # 25. Detroit Pistons (DET)
    "Cade Cunningham": (35.0, 31.0, 0.74, 0.17, 0.26, 0.06),
    "Jaden Ivey": (31.0, 25.5, 0.62, 0.14, 0.13, 0.06),
    "Tobias Harris": (31.0, 19.5, 0.48, 0.23, 0.08, 0.04),
    "Jalen Duren": (27.0, 16.5, 0.43, 0.39, 0.08, 0.00),

    # 26. Washington Wizards (WAS)
    "Jordan Poole": (31.5, 29.5, 0.71, 0.10, 0.16, 0.10),
    "Kyle Kuzma": (31.0, 27.5, 0.63, 0.22, 0.12, 0.06),
    "Jonas Valanciunas": (22.0, 24.0, 0.58, 0.40, 0.09, 0.02),
    "Bilal Coulibaly": (31.0, 19.0, 0.48, 0.18, 0.09, 0.04),

    # 27. Utah Jazz (UTA)
    "Lauri Markkanen": (33.0, 27.0, 0.69, 0.24, 0.06, 0.09),
    "Collin Sexton": (26.5, 26.0, 0.66, 0.10, 0.15, 0.06),
    "John Collins": (27.0, 23.0, 0.61, 0.29, 0.07, 0.04),
    "Keyonte George": (30.0, 24.5, 0.54, 0.11, 0.20, 0.07),
    "Walker Kessler": (27.0, 14.0, 0.36, 0.39, 0.04, 0.00),

    # 28. Portland Trail Blazers (POR)
    "Anfernee Simons": (34.0, 28.5, 0.69, 0.10, 0.16, 0.09),
    "Jerami Grant": (33.0, 24.5, 0.62, 0.12, 0.07, 0.07),
    "Deandre Ayton": (30.0, 20.0, 0.52, 0.35, 0.05, 0.00),
    "Shaedon Sharpe": (28.0, 24.0, 0.60, 0.14, 0.09, 0.06),
    "Deni Avdija": (28.0, 20.0, 0.48, 0.23, 0.13, 0.03),

    # 29. Los Angeles Clippers (LAC)
    "James Harden": (35.0, 29.5, 0.68, 0.21, 0.27, 0.08),
    "Norman Powell": (33.0, 27.0, 0.72, 0.10, 0.07, 0.10),
    "Ivica Zubac": (32.0, 19.5, 0.51, 0.41, 0.08, 0.00),
    "Terance Mann": (24.0, 14.5, 0.36, 0.16, 0.09, 0.04),

    # 30. New Orleans Pelicans (NOP)
    "Zion Williamson": (32.0, 30.5, 0.78, 0.22, 0.16, 0.00),
    "Brandon Ingram": (33.5, 28.0, 0.72, 0.17, 0.17, 0.06),
    "CJ McCollum": (31.5, 25.5, 0.64, 0.12, 0.15, 0.09),
    "Dejounte Murray": (34.0, 27.0, 0.65, 0.17, 0.22, 0.07),
    "Herbert Jones": (28.0, 14.0, 0.38, 0.13, 0.08, 0.05),
}

# Alias
PLAYER_BASELINES = PLAYER_PROP_BASELINES

# Tactical Defense vs Position (DvP) and Pace multipliers for all 30 teams
TEAM_DEFENSIVE_MULTIPLIERS: dict[str, dict[str, Any]] = {
    # Elite Defenses (suppress scoring, boards, assists)
    "OKC": {"PTS": 0.94, "REB": 0.96, "AST": 0.93, "3PM": 0.92, "pace": 100.5, "tier": "ELITE"},
    "MIN": {"PTS": 0.93, "REB": 0.95, "AST": 0.92, "3PM": 0.94, "pace": 98.0, "tier": "ELITE"},
    "BOS": {"PTS": 0.94, "REB": 0.96, "AST": 0.94, "3PM": 0.91, "pace": 99.0, "tier": "ELITE"},
    "ORL": {"PTS": 0.93, "REB": 0.94, "AST": 0.93, "3PM": 0.95, "pace": 98.0, "tier": "ELITE"},
    "HOU": {"PTS": 0.95, "REB": 0.95, "AST": 0.94, "3PM": 0.93, "pace": 99.5, "tier": "ELITE"},
    "MEM": {"PTS": 0.95, "REB": 0.96, "AST": 0.94, "3PM": 0.95, "pace": 102.0, "tier": "ELITE"},

    # Good Defenses
    "CLE": {"PTS": 0.97, "REB": 0.98, "AST": 0.96, "3PM": 0.96, "pace": 100.0, "tier": "GOOD"},
    "GSW": {"PTS": 0.96, "REB": 0.97, "AST": 0.96, "3PM": 0.96, "pace": 101.5, "tier": "GOOD"},
    "MIA": {"PTS": 0.97, "REB": 0.98, "AST": 0.96, "3PM": 0.97, "pace": 97.5, "tier": "GOOD"},
    "LAL": {"PTS": 0.98, "REB": 0.98, "AST": 0.98, "3PM": 0.97, "pace": 100.5, "tier": "GOOD"},
    "PHX": {"PTS": 0.98, "REB": 0.98, "AST": 0.98, "3PM": 0.97, "pace": 98.5, "tier": "GOOD"},

    # Average Defenses
    "DEN": {"PTS": 1.00, "REB": 1.00, "AST": 1.00, "3PM": 1.00, "pace": 99.0, "tier": "AVERAGE"},
    "NYK": {"PTS": 0.99, "REB": 0.99, "AST": 1.00, "3PM": 0.99, "pace": 96.0, "tier": "AVERAGE"},
    "SAC": {"PTS": 1.00, "REB": 1.00, "AST": 1.00, "3PM": 1.00, "pace": 100.0, "tier": "AVERAGE"},
    "DAL": {"PTS": 0.99, "REB": 1.00, "AST": 1.00, "3PM": 0.99, "pace": 99.5, "tier": "AVERAGE"},
    "MIL": {"PTS": 1.01, "REB": 1.00, "AST": 1.01, "3PM": 1.01, "pace": 99.5, "tier": "AVERAGE"},
    "PHI": {"PTS": 1.00, "REB": 1.01, "AST": 1.00, "3PM": 1.00, "pace": 98.5, "tier": "AVERAGE"},
    "IND": {"PTS": 1.03, "REB": 1.02, "AST": 1.02, "3PM": 1.01, "pace": 103.5, "tier": "AVERAGE"},
    "NOP": {"PTS": 1.01, "REB": 1.01, "AST": 1.01, "3PM": 1.01, "pace": 98.5, "tier": "AVERAGE"},
    "LAC": {"PTS": 0.99, "REB": 0.99, "AST": 1.00, "3PM": 0.99, "pace": 98.0, "tier": "AVERAGE"},
    "SAS": {"PTS": 1.01, "REB": 1.00, "AST": 1.01, "3PM": 1.02, "pace": 100.5, "tier": "AVERAGE"},

    # Vulnerable Defenses (elevated scoring environments)
    "ATL": {"PTS": 1.04, "REB": 1.03, "AST": 1.04, "3PM": 1.04, "pace": 103.0, "tier": "VULNERABLE"},
    "CHI": {"PTS": 1.03, "REB": 1.03, "AST": 1.04, "3PM": 1.03, "pace": 102.5, "tier": "VULNERABLE"},
    "DET": {"PTS": 1.03, "REB": 1.02, "AST": 1.03, "3PM": 1.03, "pace": 99.5, "tier": "VULNERABLE"},
    "BKN": {"PTS": 1.04, "REB": 1.04, "AST": 1.04, "3PM": 1.05, "pace": 98.0, "tier": "VULNERABLE"},
    "POR": {"PTS": 1.04, "REB": 1.03, "AST": 1.04, "3PM": 1.04, "pace": 100.0, "tier": "VULNERABLE"},

    # High Value Target Defenses (prime for OVER props)
    "UTA": {"PTS": 1.07, "REB": 1.06, "AST": 1.07, "3PM": 1.08, "pace": 101.5, "tier": "TARGET"},
    "WAS": {"PTS": 1.08, "REB": 1.07, "AST": 1.08, "3PM": 1.09, "pace": 102.5, "tier": "TARGET"},
    "CHA": {"PTS": 1.06, "REB": 1.06, "AST": 1.06, "3PM": 1.07, "pace": 99.5, "tier": "TARGET"},
    "TOR": {"PTS": 1.06, "REB": 1.06, "AST": 1.07, "3PM": 1.06, "pace": 101.0, "tier": "TARGET"},
}

_FALLBACK_ROSTERS_CACHE: dict[str, list[str]] | None = None


def get_fallback_rosters() -> dict[str, list[str]]:
    """Loads fallback rosters from config/fallback_rosters.json with caching."""
    global _FALLBACK_ROSTERS_CACHE
    if _FALLBACK_ROSTERS_CACHE is not None:
        return _FALLBACK_ROSTERS_CACHE
    p = Path("config/fallback_rosters.json")
    if not p.exists():
        p = Path(__file__).resolve().parent.parent.parent / "config" / "fallback_rosters.json"
    if p.exists():
        try:
            _FALLBACK_ROSTERS_CACHE = json.loads(p.read_text(encoding="utf-8"))
            return _FALLBACK_ROSTERS_CACHE
        except Exception:
            pass
    _FALLBACK_ROSTERS_CACHE = {}
    return _FALLBACK_ROSTERS_CACHE
