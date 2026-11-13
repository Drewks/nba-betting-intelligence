"""
Unit and Integration Tests for Telegram Push Alerts, Deduplication, Interactive Allowlist,
and Real Unblocked Peruvian / Pinnacle Odds Extraction
(`tests/test_telegram_alerts_and_peru_real.py`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import sys

import pytest

from src.ingestion.live_peru_scraper import (
    LivePeruOddsScraper,
    parse_pinnacle_nba_events,
    parse_teapuesto_nba_events,
)
from src.ingestion.playwright_scraper import PeruPlaywrightScraper
from src.reporting.telegram_bot import (
    TelegramAlertBot,
    dispatch_pending_bet_alerts,
    format_injury_sniper_alert,
    format_slate_status_summary,
)
from src.reporting.telegram_interactive import TelegramInteractiveListener
from src.storage.db import DatabaseManager
from tests.helpers import _seed_sample_game_and_prediction


def _sample_teapuesto_payload() -> dict[str, Any]:
    return {
        "data": {
            "tournaments": {
                "46": {
                    "id": 46,
                    "name": "NBA",
                    "events": [
                        {
                            "id": 9991,
                            "name": "Phoenix Suns - Charlotte Hornets",
                            "start_time": "2026-11-13 02:00:00",
                            "status": 0,
                            "markets": [
                                {
                                    "provider_market_id": "219",
                                    "name": "Ganador (incl. prórroga)",
                                    "market_odds": [
                                        {
                                            "is_favorite": False,
                                            "odds": [
                                                {"provider_odd_id": "4", "name": "Phoenix Suns", "value": 1.36},
                                                {"provider_odd_id": "5", "name": "Charlotte Hornets", "value": 2.85},
                                            ],
                                        }
                                    ],
                                },
                                {
                                    "provider_market_id": "225",
                                    "name": "Total (incl. prórroga)",
                                    "market_odds": [
                                        {
                                            "is_favorite": False,
                                            "odds": [
                                                {"provider_odd_id": "13", "name": "menos de 213.5", "value": 1.87, "special_value": "213.5"},
                                                {"provider_odd_id": "12", "name": "más de 213.5", "value": 1.77, "special_value": "213.5"},
                                            ],
                                        },
                                        {
                                            "is_favorite": True,
                                            "odds": [
                                                {"provider_odd_id": "13", "name": "menos de 214.5", "value": 1.80, "special_value": "214.5"},
                                                {"provider_odd_id": "12", "name": "más de 214.5", "value": 1.84, "special_value": "214.5"},
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "provider_market_id": "223",
                                    "name": "Hándicap (incl. prórroga)",
                                    "market_odds": [
                                        {
                                            "is_favorite": True,
                                            "odds": [
                                                {"provider_odd_id": "1714", "name": "Phoenix Suns (-7.5)", "value": 1.86},
                                                {"provider_odd_id": "1715", "name": "Charlotte Hornets (+7.5)", "value": 1.78},
                                            ],
                                        }
                                    ],
                                },
                                {
                                    "provider_market_id": "921",
                                    "name": " total puntos",
                                    "market_odds": [
                                        {
                                            "name": "Kalkbrenner, Ryan total puntos",
                                            "odds": [
                                                {"provider_odd_id": "12", "name": "más de 4.5", "value": 1.53},
                                                {"provider_odd_id": "13", "name": "menos de 4.5", "value": 1.68},
                                            ],
                                        }
                                    ],
                                },
                            ],
                        },
                        {
                            "id": 9992,
                            "name": "Minnesota Timberwolves - Dallas Mavericks",
                            "start_time": "2026-11-13 01:00:00",
                            "status": 1,  # Live in-play must be excluded pre-game
                            "markets": [
                                {
                                    "provider_market_id": "219",
                                    "name": "Ganador (incl. prórroga)",
                                    "market_odds": [
                                        {
                                            "odds": [
                                                {"provider_odd_id": "4", "name": "Minnesota Timberwolves", "value": 1.80},
                                                {"provider_odd_id": "5", "name": "Dallas Mavericks", "value": 1.95},
                                            ]
                                        }
                                    ],
                                }
                            ],
                        },
                    ],
                }
            }
        }
    }


def _sample_pinnacle_payload() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matchups = [
        {
            "id": 1001,
            "type": "matchup",
            "special": None,
            "isLive": False,
            "hasMarkets": True,
            "startTime": "2026-11-13T02:00:00Z",
            "participants": [
                {"alignment": "home", "name": "Phoenix Suns"},
                {"alignment": "away", "name": "Charlotte Hornets"},
            ],
        },
        {
            "id": 1002,
            "type": "matchup",
            "special": None,
            "isLive": True,  # Live game must be excluded pre-game
            "hasMarkets": True,
            "startTime": "2026-11-13T01:00:00Z",
            "participants": [
                {"alignment": "home", "name": "Minnesota Timberwolves"},
                {"alignment": "away", "name": "Dallas Mavericks"},
            ],
        },
    ]
    markets = [
        {
            "matchupId": 1001,
            "period": 0,
            "isAlternate": False,
            "status": "open",
            "type": "moneyline",
            "prices": [
                {"designation": "home", "price": -238},
                {"designation": "away", "price": 208},
            ],
        },
        {
            "matchupId": 1001,
            "period": 0,
            "isAlternate": False,
            "status": "open",
            "type": "total",
            "prices": [
                {"designation": "over", "points": 215.5, "price": -108},
                {"designation": "under", "points": 215.5, "price": -104},
            ],
        },
        {
            "matchupId": 1001,
            "period": 0,
            "isAlternate": False,
            "status": "open",
            "type": "spread",
            "prices": [
                {"designation": "home", "points": -6.5, "price": -105},
                {"designation": "away", "points": 6.5, "price": -107},
            ],
        },
        {
            "matchupId": 1002,
            "period": 0,
            "isAlternate": False,
            "status": "open",
            "type": "moneyline",
            "prices": [
                {"designation": "home", "price": -150},
                {"designation": "away", "price": 130},
            ],
        },
    ]
    return matchups, markets


def test_telegram_alert_formatting_and_deduplication(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "test_tg.sqlite3")
    pred_id = _seed_sample_game_and_prediction(db, "G_TG_01")
    db.execute_insert(
        """
        INSERT INTO simulated_bets (
            bet_id, prediction_id, game_id, matchday_date, market, selection,
            line_value, decimal_odds, estimated_prob, estimated_ev, stake_pen,
            emitted_at, model_version_id, status
        ) VALUES (
            'BET_TG_01', ?, 'G_TG_01', '2026-10-20', 'total_points', 'OVER',
            224.5, 2.05, 0.56, 0.088, 1.50,
            '2026-10-20T20:05:00Z', 'model_c_test_v1', 'PENDING'
        )
        """,
        (pred_id,),
    )

    bot = TelegramAlertBot(bot_token="fake_token", chat_id="12345", alerts_log_path=tmp_path / "alerts.json")
    sent_msgs: list[str] = []
    bot.send_raw_message = lambda text, parse_mode="Markdown": sent_msgs.append(text) or True  # type: ignore[method-assign]

    # Single bet formatting handles line_value & fallbacks accurately
    alt_fmt = bot.format_single_bet_alert(
        {
            "game_id": "G_ALT",
            "market_type": "total_points",
            "selection": "UNDER",
            "line_value": 218.5,
            "decimal_odds": 1.95,
            "estimated_prob": 0.565,
            "estimated_ev": 0.102,
            "stake_pen": 2.0,
            "bookmaker": "Te Apuesto Perú",
        }
    )
    assert "TOTAL_POINTS" in alt_fmt
    assert "UNDER 218.5" in alt_fmt
    assert "56.5%" in alt_fmt
    assert "+10.2%" in alt_fmt
    assert "Te Apuesto Perú" in alt_fmt

    # Sniper alert formatting uses transitions/synergy_shift/kelly_stake_pen
    sniper_msg = format_injury_sniper_alert(
        {
            "alert_id": "SNIP_1",
            "game_id": "G_TG_01",
            "selection": "AWAY",
            "decimal_odds": 2.40,
            "ev_lower_bound_pct": 6.4,
            "kelly_stake_pen": 1.85,
            "synergy_shift": -5.2,
            "transitions": [{"player_name": "Jayson Tatum", "team": "BOS", "new_status": "OUT"}],
            "rational": "Late star scratch shifts fair probability.",
        }
    )
    assert "Jayson Tatum (BOS → OUT)" in sniper_msg
    assert "-5.2 pts" in sniper_msg
    assert "S/ 1.85 PEN" in sniper_msg
    assert "+6.4%" in sniper_msg

    # Slate summary formatting reads real run_cloud_cycle keys
    summary_msg = format_slate_status_summary(
        {"mode": "morning", "predictions_generated": 14, "new_bets_placed_in_cycle": 0, "bankroll_state": {"settled_bankroll_pen": 96.40}},
        pending_count=1,
    )
    assert "`14`" in summary_msg
    assert "(Pendientes: `1`)" in summary_msg
    assert "S/ 96.40 PEN" in summary_msg

    # Dry-run should dispatch log without locking dedup ledger
    state_file = tmp_path / "dedup_state.json"
    dry_count = dispatch_pending_bet_alerts(bot, db, min_ev=5.0, state_path=state_file, dry_run=True)
    assert dry_count == 1
    assert not state_file.exists()

    # Live run dispatches once, second run deduplicates to 0
    sent_msgs.clear()
    first = dispatch_pending_bet_alerts(bot, db, min_ev=5.0, state_path=state_file, dry_run=False)
    second = dispatch_pending_bet_alerts(bot, db, min_ev=5.0, state_path=state_file, dry_run=False)
    assert first == 1
    assert second == 0
    assert len(sent_msgs) == 1
    assert "TOTAL_POINTS" in sent_msgs[0]
    assert "OVER 224.5" in sent_msgs[0]


def test_telegram_interactive_allowed_chat_ids_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "test_interactive.sqlite3")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy_token")
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")

    listener = TelegramInteractiveListener(db=db, offset_file=tmp_path / "offset.txt")
    assert listener.allowed_chat_ids == {"987654321"}

    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111, 222, ")
    listener_multi = TelegramInteractiveListener(db=db, offset_file=tmp_path / "offset2.txt")
    assert listener_multi.allowed_chat_ids == {"111", "222"}


def test_parse_teapuesto_and_pinnacle_live_json_and_persist(tmp_path: Path) -> None:
    ta_rows = parse_teapuesto_nba_events(_sample_teapuesto_payload(), captured_at="2026-11-13T01:00:00Z")
    assert len(ta_rows) == 1  # Live status=1 game excluded
    ta = ta_rows[0]
    assert ta["home_team"] == "PHX"
    assert ta["away_team"] == "CHA"
    assert ta["home_odds"] == pytest.approx(1.36)
    assert ta["away_odds"] == pytest.approx(2.85)
    assert ta["total_points_line"] == pytest.approx(214.5)
    assert ta["total_over_odds"] == pytest.approx(1.84)
    assert ta["total_under_odds"] == pytest.approx(1.80)
    assert ta["spread_home_line"] == pytest.approx(-7.5)
    assert ta["spread_home_odds"] == pytest.approx(1.86)
    assert ta["spread_away_odds"] == pytest.approx(1.78)
    assert ta["player_props"][0]["player_name"] == "Ryan Kalkbrenner"
    assert ta["player_props"][0]["line_value"] == pytest.approx(4.5)

    matchups, markets = _sample_pinnacle_payload()
    pin_rows = parse_pinnacle_nba_events(matchups, markets, captured_at="2026-11-13T01:00:00Z")
    assert len(pin_rows) == 1  # Live isLive=True game excluded
    pin = pin_rows[0]
    assert pin["home_team"] == "PHX"
    assert pin["away_team"] == "CHA"
    assert pin["home_odds"] == pytest.approx(1.4202, abs=1e-3)
    assert pin["away_odds"] == pytest.approx(3.08, abs=1e-3)
    assert pin["total_points_line"] == pytest.approx(215.5)
    assert pin["spread_home_line"] == pytest.approx(-6.5)

    # Seed DB game (reversed home/away to test side alignment immunity: CHA home, PHX away)
    db = DatabaseManager(tmp_path / "test_peru_persist.sqlite3")
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team,
            status, features_available_at, source_provider, ingested_at
        ) VALUES (
            'G_PHX_CHA', '2026-27', '2026-11-13', '2099-11-13T02:00:00Z', 'PHX', 'CHA',
            'SCHEDULED', '2026-11-12T18:00:00Z', 'espn', '2026-11-12T18:00:00Z'
        )
        """
    )

    # Boost Te Apuesto CHA price to simulate stale retail line vs Pinnacle (3.45 vs Pinnacle 3.08 -> +12% CLV)
    ta_stale = {**ta, "team_odds": {"PHX": 1.36, "CHA": 3.45}, "away_odds": 3.45}
    scraper = LivePeruOddsScraper(db=db, min_clv_pct=4.0, enable_live_network=False)
    scraper._fetch_teapuesto_slate = lambda force_refresh=False: [ta_stale]  # type: ignore[method-assign]
    scraper._fetch_pinnacle_slate = lambda force_refresh=False: [pin]  # type: ignore[method-assign]

    scan_res = scraper.scan_and_alert_entire_slate(notify_telegram=False, force_all=False)
    assert len(scan_res) == 1
    row_res = scan_res[0]
    assert row_res["observed_quotes_count"] >= 1
    assert any(st["selection"] == "AWAY" and st["is_stale_line"] for st in row_res["stale_lines"])

    # Assert ML + Totals persisted with OBSERVED provenance (schema permits moneyline, total_points, player_prop)
    persisted = db.fetch_all(
        "SELECT provider, market, selection, line_value, decimal_odds, source_type FROM v_observed_odds_snapshots WHERE game_id = 'G_PHX_CHA'"
    )
    markets_seen = {(r["provider"], r["market"], r["selection"]) for r in persisted}
    assert ("Te Apuesto Perú [LIVE_API]", "moneyline", "HOME") in markets_seen
    assert ("Te Apuesto Perú [LIVE_API]", "total_points", "OVER") in markets_seen
    assert ("Pinnacle [LIVE_API]", "moneyline", "HOME") in markets_seen
    assert ("Pinnacle [LIVE_API]", "total_points", "UNDER") in markets_seen
    assert all(r["source_type"] == "OBSERVED" for r in persisted)


def test_scheduler_morning_and_sniper_telegram_wiring(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import scripts.run_automated_scheduler as sched_mod

    db = DatabaseManager(tmp_path / "test_sched.sqlite3")
    pred_id = _seed_sample_game_and_prediction(db, "G_SCHED_01")
    db.execute_insert(
        """
        INSERT INTO simulated_bets (
            bet_id, prediction_id, game_id, matchday_date, market, selection,
            line_value, decimal_odds, estimated_prob, estimated_ev, stake_pen,
            emitted_at, model_version_id, status
        ) VALUES (
            'BET_SCHED_01', ?, 'G_SCHED_01', '2026-10-20', 'moneyline', 'HOME',
            NULL, 2.10, 0.52, 0.092, 1.00,
            '2026-10-20T20:05:00Z', 'model_c_test_v1', 'PENDING'
        )
        """,
        (pred_id,),
    )

    monkeypatch.setattr(
        sched_mod,
        "run_incremental_cloud_cycle",
        lambda mode="pregame": {"mode": mode, "predictions_generated": 5, "new_bets_placed_in_cycle": 1, "bankroll_state": {"settled_bankroll_pen": 100.0}},
    )
    monkeypatch.setattr(
        sched_mod.PlayerPropsEngine,
        "generate_slate_prop_opportunities",
        lambda self, slate_games, bankroll_pen, min_ev_pct=3.0: [],
    )

    state_file = tmp_path / "sched_dedup.json"
    scheduler = sched_mod.NBADailyScheduler(db_path=tmp_path / "test_sched.sqlite3", alert_state_path=state_file)
    sent: list[str] = []
    scheduler.bot.is_live = True
    scheduler.bot.send_raw_message = lambda text, parse_mode="Markdown": sent.append(text) or True  # type: ignore[method-assign]

    res1 = scheduler.execute_morning_cycle()
    assert res1["alerts_dispatched"] == 1
    assert len(sent) == 1
    assert "MONEYLINE" in sent[0]

    # Mark bet VOID so morning fallback summary runs once per day
    db.execute_insert("UPDATE simulated_bets SET status = 'VOID' WHERE bet_id = 'BET_SCHED_01'")
    res2 = scheduler.execute_morning_cycle()
    assert res2["alerts_dispatched"] == 0
    assert len(sent) == 2
    assert "REPORTE DE JORNADA NBA" in sent[1]

    # Running again same day must not resend duplicate daily summary
    scheduler.execute_morning_cycle()
    assert len(sent) == 2

    # Sniper cycle deduplicates alert
    sent.clear()
    monkeypatch.setattr(
        sched_mod.InjurySniperMonitor,
        "scan_pregame_slate",
        lambda self, force_scan_all=False: {
            "alerts": [
                {
                    "alert_id": "SNIP_SCHED_1",
                    "game_id": "G_SCHED_01",
                    "selection": "AWAY",
                    "decimal_odds": 2.35,
                    "ev_lower_bound_pct": 7.1,
                    "kelly_stake_pen": 2.10,
                    "synergy_shift": -6.0,
                    "transitions": [{"player_name": "Jaylen Brown", "team": "BOS", "new_status": "OUT"}],
                }
            ]
        },
    )
    s_res1 = scheduler.execute_sniper_cycle()
    s_res2 = scheduler.execute_sniper_cycle()
    assert s_res1["alerts_dispatched"] == 1
    assert s_res2["alerts_dispatched"] == 0
    assert len(sent) == 1
    assert "Jaylen Brown (BOS → OUT)" in sent[0]


def test_harvest_local_peru_odds_method_wiring(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import scripts.harvest_local_peru_odds as harvest_mod

    db_file = tmp_path / "test_harvest.sqlite3"
    db = DatabaseManager(db_file)
    _seed_sample_game_and_prediction(db, "G_HARV_01")
    db.execute_insert("UPDATE games SET game_start_time = '2099-10-20T23:00:00Z' WHERE game_id = 'G_HARV_01'")

    called: list[str] = []

    class DummyScraper:
        def __init__(self, db: Any = None, timeout_ms: int = 30000, headless: bool = True) -> None:
            self.db = db

        def scrape_teapuesto_odds(self) -> list[dict[str, Any]]:
            called.append("teapuesto")
            return [
                {
                    "provider": "Te Apuesto Perú",
                    "home_team": "BOS",
                    "away_team": "MIA",
                    "market": "moneyline",
                    "selection": "HOME",
                    "decimal_odds": 1.75,
                    "counterpart_decimal_odds": 2.05,
                    "line_value": None,
                    "captured_at": "2026-10-20T19:00:00Z",
                    "source_type": "OBSERVED",
                }
            ]

        def scrape_pinnacle_odds(self) -> list[dict[str, Any]]:
            called.append("pinnacle")
            return []

        def scrape_retabet_odds(self) -> list[dict[str, Any]]:
            called.append("retabet")
            return []

        def scrape_betano_odds(self) -> list[dict[str, Any]]:
            called.append("betano")
            return []

        def persist_scraped_quotes(self, quotes: list[dict[str, Any]], slate_games: list[dict[str, Any]]) -> int:
            called.append(f"persist:{len(quotes)}:{len(slate_games)}")
            return len(quotes)

    monkeypatch.setattr(harvest_mod, "PeruPlaywrightScraper", DummyScraper)
    monkeypatch.setattr(sys, "argv", ["harvest_local_peru_odds.py", "--db", str(db_file)])
    harvest_mod.main()
    assert called == ["teapuesto", "pinnacle", "persist:1:1"]

    called.clear()
    monkeypatch.setattr(sys, "argv", ["harvest_local_peru_odds.py", "--db", str(db_file), "--site", "retabet", "--dry-run"])
    harvest_mod.main()
    assert called == ["retabet"]
    assert isinstance(PeruPlaywrightScraper()._slate_rows_to_quote_dicts([]), list)
    assert json.loads(json.dumps({"ok": True})) == {"ok": True}
