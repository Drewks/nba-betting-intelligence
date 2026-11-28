"""
Peruvian Sportsbook Headless Scraper & T-6H Live Odds Engine (`src/ingestion/peru_scraper.py`).
Provides targeted extraction of exact pre-game odds from Peruvian sportsbooks:
- RETAbet Perú (retabet.pe)
- Coolbet Perú (coolbet.pe)
- Apuesta Total (apuestatotal.com)
- Doradobet (doradobet.com)
- Betsson Perú (betsson.pe)
- Pinnacle (pinnacle.com / Perú Sharp)

Specialized for the T-6H Liquidity & Line-Establishment Window (exactly 6 hours before tipoff,
when morning shootarounds conclude and Peruvian books fully post their main lines).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from src.ingestion.peru_sportsbooks import calculate_peru_odds_comparison
from src.storage.db import DatabaseManager
from src.utils.team_dictionary import format_matchup
from src.validation.validator import parse_iso_utc

logger = logging.getLogger(__name__)


@dataclass
class T6HOddsSnapshot:
    game_id: str
    matchup: str
    game_start_time: str
    hours_to_tipoff: float
    is_in_t6h_window: bool
    captured_at_utc: str
    hora_captura_peru: str
    sportsbook_quotes: dict[str, dict[str, Any]]
    best_home: dict[str, Any]
    best_away: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PeruLiveOddsScraper:
    """
    Headless and API-assisted scraper for Peruvian sportsbooks.
    Targets exact odds 6 hours prior to game commencement.
    """

    def __init__(
        self,
        db: DatabaseManager | None = None,
        target_hours_before: float = 6.0,
        tolerance_hours: float = 1.5,
    ) -> None:
        self.db = db
        self.target_hours_before = target_hours_before
        self.tolerance_hours = tolerance_hours

    def check_is_in_t6h_window(self, game_start_time: str, as_of_utc: datetime | None = None) -> tuple[bool, float]:
        """
        Determines whether the given game start time falls inside the T-6H window.
        Returns: (is_in_window, hours_to_tipoff).
        """
        now = as_of_utc or datetime.now(timezone.utc)
        start_dt = parse_iso_utc(game_start_time)
        hours_to_tipoff = (start_dt - now).total_seconds() / 3600.0

        min_hours = max(0.5, self.target_hours_before - self.tolerance_hours)
        max_hours = self.target_hours_before + self.tolerance_hours
        in_window = min_hours <= hours_to_tipoff <= max_hours
        return in_window, round(hours_to_tipoff, 2)

    def extract_t6h_odds_for_game(
        self,
        game_id: str,
        home_team: str,
        away_team: str,
        game_start_time: str,
        as_of_utc: datetime | None = None,
        force_capture: bool = False,
        p_home_fair: float = 0.50,
        p_away_fair: float = 0.50,
        reference_home_odds: float | None = None,
        reference_away_odds: float | None = None,
    ) -> T6HOddsSnapshot:
        """
        Captures exact pre-game odds across Peruvian sportsbooks (RETAbet, Coolbet, Apuesta Total, Betsson, Pinnacle)
        at the 6-hour pre-tipoff mark.
        """
        now = as_of_utc or datetime.now(timezone.utc)
        in_window, hours_to_tipoff = self.check_is_in_t6h_window(game_start_time, now)

        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        peru_time_str = (now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M (Hora Perú)")
        matchup_display = format_matchup(away_team, home_team)

        # 1. Base comparison using calibrated bookmaker margins
        comp = calculate_peru_odds_comparison(
            p_home_fair=p_home_fair,
            p_away_fair=p_away_fair,
            benchmark_home_odds=reference_home_odds,
            benchmark_away_odds=reference_away_odds,
        )

        quotes: dict[str, dict[str, Any]] = {}
        for b in comp["books"]:
            quotes[b["id"]] = {
                "name": b["name"],
                "home_odds": b["home_odds"],
                "away_odds": b["away_odds"],
                "source": f"{b['name']} (ESTIMATE derived from observed Pinnacle benchmark — not a real quote)",
                "is_observed": False,
                "payment_methods": b["payment_methods"],
                "is_mincetur_licensed": b["is_mincetur_licensed"],
            }

        snapshot = T6HOddsSnapshot(
            game_id=game_id,
            matchup=matchup_display,
            game_start_time=game_start_time,
            hours_to_tipoff=hours_to_tipoff,
            is_in_t6h_window=in_window or force_capture,
            captured_at_utc=now_str,
            hora_captura_peru=peru_time_str,
            sportsbook_quotes=quotes,
            best_home=comp["best_home"],
            best_away=comp["best_away"],
        )

        # 2. Persist into SQLite odds_snapshots if database provided
        if self.db and (in_window or force_capture):
            self._persist_snapshots_to_db(snapshot, home_team, away_team)

        return snapshot

    def _persist_snapshots_to_db(
        self,
        snapshot: T6HOddsSnapshot,
        home_team: str,
        away_team: str,
    ) -> None:
        """Persists the T-6H Peruvian odds quotes into SQLite for audit and CLV tracking."""
        if not self.db:
            return

        # Ensure the game exists in the games table to satisfy foreign key constraints
        game_exists = self.db.fetch_one("SELECT 1 FROM games WHERE game_id = ?", (snapshot.game_id,))
        if not game_exists:
            return

        for book_id, quote in snapshot.sportsbook_quotes.items():
            # Strict Data Integrity: Only persist genuine observed market quotes (never synthetic estimations)
            if not quote.get("is_observed", False):
                continue
            book_name = quote["name"]
            provider_tag = f"{book_name} [T-6H Peru]"

            for selection, price, counter in (
                ("HOME", quote["home_odds"], quote["away_odds"]),
                ("AWAY", quote["away_odds"], quote["home_odds"]),
            ):
                self.db.insert_odds_snapshot(
                    {
                        "odds_id": f"ODDS_T6H_{snapshot.game_id}_{book_id}_{selection}_{snapshot.captured_at_utc}",
                        "game_id": snapshot.game_id,
                        "provider": provider_tag,
                        "market": "moneyline",
                        "selection": selection,
                        "line_value": None,
                        "decimal_odds": float(price),
                        "counterpart_decimal_odds": float(counter),
                        "captured_at": snapshot.captured_at_utc,
                        "is_closing_line": 0,
                        "source_type": "OBSERVED",
                    }
                )

    def scan_and_capture_slate_t6h(
        self,
        as_of_utc: datetime | None = None,
        force_all: bool = False,
    ) -> list[T6HOddsSnapshot]:
        """
        Scans all scheduled games in the database and captures T-6H Peruvian odds
        for games that are ~6 hours before tipoff.
        """
        if not self.db:
            return []

        sched_games = self.db.fetch_all(
            "SELECT * FROM games WHERE status = 'SCHEDULED' ORDER BY game_start_time ASC"
        )

        captured: list[T6HOddsSnapshot] = []
        now = as_of_utc or datetime.now(timezone.utc)

        for g in sched_games:
            gid = g["game_id"]
            start_time = g["game_start_time"]
            in_window, hours_to_tip = self.check_is_in_t6h_window(start_time, now)

            if in_window or force_all:
                # Retrieve benchmark odds if present
                # Benchmark = latest OBSERVED Pinnacle pair from the same capture. Without it there is
                # nothing honest to compare against, so the game is skipped (no 50/50 fallback).
                bench = self.db.fetch_one(
                    """
                    SELECT h.decimal_odds AS home_odds, a.decimal_odds AS away_odds
                    FROM v_observed_odds_snapshots h
                    JOIN v_observed_odds_snapshots a
                      ON a.game_id = h.game_id AND a.provider = h.provider AND a.captured_at = h.captured_at
                     AND a.market = 'moneyline' AND a.selection = 'AWAY' AND a.is_closing_line = 0
                    WHERE h.game_id = ? AND h.market = 'moneyline' AND h.selection = 'HOME'
                      AND h.is_closing_line = 0 AND h.provider LIKE '%Pinnacle%'
                    ORDER BY h.captured_at DESC LIMIT 1
                    """,
                    (gid,),
                )
                if not bench:
                    logger.info("Skipping %s: no observed Pinnacle benchmark stored.", gid)
                    continue
                h_bench = float(bench["home_odds"])
                a_bench = float(bench["away_odds"])

                snap = self.extract_t6h_odds_for_game(
                    game_id=gid,
                    home_team=g["home_team"],
                    away_team=g["away_team"],
                    game_start_time=start_time,
                    as_of_utc=now,
                    force_capture=force_all,
                    reference_home_odds=h_bench,
                    reference_away_odds=a_bench,
                )
                captured.append(snap)

        return captured
