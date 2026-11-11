"""
Peruvian Sportsbooks, Odds Scrapers, Arbitrage Hunter and Telegram Bot Tests (`tests/test_peru_scrapers_and_telegram.py`).
Modular test suite extracted from legacy test_nba_intelligence monolith.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import numpy as np
import pytest

from src.prediction.ev_calculator import (
    devig_multiplicative,
)
from src.storage.db import DatabaseManager



def test_32_injury_sniper_pregame_dual_window(tmp_path: Path) -> None:
    """
    V7.1 Fase 6 Verification:
    Tests the automated Injury Sniper Dual-Window Monitor at T-2h and T-30m:
      1) Temporal classification into WINDOW_2H (90-150m) and WINDOW_30M (15-45m).
      2) Transition detection for star players (Questionable -> OUT, late scratches).
      3) Lineup synergy penalty recalculation and Venn-Abers conformal Lower-Bound EV.
      4) Emission of actionable Sniper Alerts with simultaneous Kelly portfolio stakes.
      5) Immutable audit logging into the SQLite `sniper_alerts` table.
    """
    from src.prediction.injury_sniper import (
        classify_game_window,
        detect_injury_status_transitions,
        InjurySniperMonitor,
    )
    from src.storage.db import DatabaseManager

    ref_utc = datetime(2026, 11, 7, 22, 0, 0, tzinfo=timezone.utc)

    # 1. Test Window Classification
    w_2h, d_2h = classify_game_window("2026-11-08T00:00:00Z", ref_utc)  # 120m
    assert w_2h == "WINDOW_2H"
    assert d_2h == 120.0

    w_30m, d_30m = classify_game_window("2026-11-07T22:30:00Z", ref_utc)  # 30m
    assert w_30m == "WINDOW_30M"
    assert d_30m == 30.0

    w_imm, d_imm = classify_game_window("2026-11-07T22:10:00Z", ref_utc)  # 10m
    assert w_imm == "TIPOFF_IMMINENT"

    w_fut, d_fut = classify_game_window("2026-11-08T03:00:00Z", ref_utc)  # 300m
    assert w_fut == "UPCOMING_FUTURE"

    # 2. Test Injury Transition Detection
    cached_inj = [
        {"name": "Luka Doncic", "status": "QUESTIONABLE", "team": "DAL"},
        {"name": "Rudy Gobert", "status": "DOUBTFUL", "team": "MIN"},
    ]
    live_inj = [
        {"name": "Luka Doncic", "status": "OUT", "team": "DAL", "notes": "Left ankle sprain"},
        {"name": "Rudy Gobert", "status": "AVAILABLE", "team": "MIN", "notes": "Cleared to play"},
    ]
    transitions = detect_injury_status_transitions(cached_inj, live_inj)
    assert len(transitions) == 2

    luka_t = next(t for t in transitions if t["player_name"] == "Luka Doncic")
    assert luka_t["old_status"] == "QUESTIONABLE"
    assert luka_t["new_status"] == "OUT"
    assert luka_t["tactical_role"] == "PRIMARY_INITIATOR"
    assert luka_t["severity"] == "CRITICAL"
    assert luka_t["is_synergy_star"] is True

    rudy_t = next(t for t in transitions if t["player_name"] == "Rudy Gobert")
    assert rudy_t["old_status"] == "DOUBTFUL"
    assert rudy_t["new_status"] == "AVAILABLE"
    assert rudy_t["tactical_role"] == "RIM_ANCHOR"
    assert rudy_t["severity"] == "HIGH"

    # 3. Test Sniper Opportunity Evaluation & Conformal Lower-Bound EV
    db_file = tmp_path / "test_sniper.sqlite3"
    db = DatabaseManager(db_file)
    # Seed teams & game to satisfy foreign keys
    db.execute_insert(
        "INSERT INTO teams (team_id, full_name, conference, division, updated_at) VALUES ('PHX', 'Phoenix Suns', 'West', 'Pacific', '2026-10-01T00:00:00Z');"
    )
    db.execute_insert(
        "INSERT INTO teams (team_id, full_name, conference, division, updated_at) VALUES ('DAL', 'Dallas Mavericks', 'West', 'Southwest', '2026-10-01T00:00:00Z');"
    )
    db.execute_insert(
        """
        INSERT INTO games (
            game_id, season, matchday_date, game_start_time, home_team, away_team, status,
            features_available_at, source_provider, ingested_at
        ) VALUES ('G_SNIPER_TEST', '2026-27', '2026-11-07', '2026-11-08T00:00:00Z', 'PHX', 'DAL', 'SCHEDULED', '2026-11-07T20:00:00Z', 'espn', '2026-11-07T20:00:00Z');
        """
    )

    odds_list = [
        {
            "odds_id": "O_PHX",
            "game_id": "G_SNIPER_TEST",
            "provider": "draftkings",
            "market": "moneyline",
            "selection": "HOME",
            "line_value": None,
            "decimal_odds": 1.88,
            "counterpart_decimal_odds": 1.95,
            "captured_at": "2026-11-07T22:00:00Z",
        },
        {
            "odds_id": "O_DAL",
            "game_id": "G_SNIPER_TEST",
            "provider": "draftkings",
            "market": "moneyline",
            "selection": "AWAY",
            "line_value": None,
            "decimal_odds": 1.95,
            "counterpart_decimal_odds": 1.88,
            "captured_at": "2026-11-07T22:00:00Z",
        },
    ]

    monitor = InjurySniperMonitor(db=db, min_ev_threshold=0.04)
    # Give the sniper's Venn-Abers calibrator a well-calibrated history so its intervals are informative
    rng = np.random.default_rng(7)
    cal_records = []
    for i in range(600):
        p_i = float(rng.uniform(0.2, 0.8))
        cal_records.append(
            {"game_start_time": f"2026-10-{1 + i % 28:02d}T00:00:00Z", "raw_probability": p_i, "outcome": int(rng.random() < p_i)}
        )
    assert monitor.calibrator.fit(cal_records, "2026-11-01T00:00:00Z") is True

    common = {
        "game_id": "G_SNIPER_TEST",
        "matchday_date": "2026-11-07",
        "game_start_time": "2026-11-08T00:00:00Z",
        "home_team": "PHX",
        "away_team": "DAL",
        "market_odds": odds_list,
        "window_type": "WINDOW_2H",
        "minutes_to_tipoff": 120.0,
        "bankroll_pen": 100.0,
    }

    # 4a. A long-known absence (same status as the previous snapshot) is already priced by the market
    no_alerts = monitor.evaluate_game_sniper_opportunity(
        live_injuries=[{"name": "Luka Doncic", "status": "OUT", "team": "DAL", "position": "PG"}],
        cached_injuries=[{"name": "Luka Doncic", "status": "OUT", "team": "DAL"}],
        **common,
    )
    assert no_alerts == []

    # 4b. A NEW transition (QUESTIONABLE -> OUT) shifts the de-vigged market probability toward PHX
    alerts = monitor.evaluate_game_sniper_opportunity(
        live_injuries=[{"name": "Luka Doncic", "status": "OUT", "team": "DAL", "position": "PG"}],
        cached_injuries=[{"name": "Luka Doncic", "status": "QUESTIONABLE", "team": "DAL"}],
        **common,
    )
    assert len(alerts) >= 1
    phx_alert = next(a for a in alerts if a["selection"] == "HOME")
    assert phx_alert["target_team"] == "PHX"
    assert phx_alert["synergy_shift"] > 3.0  # incremental loss of Luka (Q -> OUT) adds > 3 pts to Home
    assert phx_alert["point_prob"] > phx_alert["market_p_home"]
    assert phx_alert["ev_lower_bound_pct"] >= 4.0
    assert 0.0 < phx_alert["kelly_stake_pen"] <= 10.00  # configured per-selection cap
    assert phx_alert["window_type"] == "WINDOW_2H"

    # 5. Verify SQLite persistence in sniper_alerts
    persisted = db.fetch_all("SELECT * FROM sniper_alerts WHERE game_id = 'G_SNIPER_TEST'")
    assert len(persisted) >= 1
    row = persisted[0]
    assert row["selection"] == "HOME"
    assert row["window_type"] == "WINDOW_2H"
    assert row["ev_lower_bound_pct"] >= 4.0


def test_34_peru_sportsbooks_and_odds_comparator() -> None:
    """
    Test 34: Verification of Peruvian Sportsbooks Integration & Local Odds Comparator.
    Ensures:
    1. MINCETUR regulated sportsbooks (Betsson, Coolbet, Apuesta Total, Te Apuesto, Doradobet)
       are properly mapped with local payment gateways (Yape, Plin, BCP, BBVA).
    2. Sharp international operators accessible in Peru (Pinnacle, 1xBet) are accurately modeled.
    3. Comparator produces strictly positive decimal odds, correct de-vigged pricing, and
       valid serialization for the Generative UI dashboard.
    """
    from src.ingestion.peru_sportsbooks import (
        PERU_SPORTSBOOKS,
        calculate_peru_odds_comparison,
        get_peru_sportsbooks_catalog,
        get_peru_sportsbooks_json_for_frontend,
    )

    # 1. Verify catalog completeness
    catalog = get_peru_sportsbooks_catalog()
    assert len(catalog) >= 9
    book_ids = {b["id"] for b in catalog}
    assert "betsson_pe" in book_ids
    assert "coolbet_pe" in book_ids
    assert "retabet_pe" in book_ids
    assert "apuesta_total" in book_ids
    assert "te_apuesto" in book_ids
    assert "doradobet" in book_ids
    assert "pinnacle_pe" in book_ids

    # Verify MINCETUR compliance & payment methods
    betsson = PERU_SPORTSBOOKS["betsson_pe"]
    assert betsson.is_mincetur_licensed is True
    assert "Yape" in betsson.payment_methods
    assert "Plin" in betsson.payment_methods

    retabet = PERU_SPORTSBOOKS["retabet_pe"]
    assert retabet.is_mincetur_licensed is True
    assert "Tarjeta RETAbet" in retabet.payment_methods
    assert "Yape" in retabet.payment_methods

    # 2. Verify odds comparison engine
    comp = calculate_peru_odds_comparison(
        p_home_fair=0.55,
        p_away_fair=0.45,
        benchmark_home_odds=1.85,
        benchmark_away_odds=2.00,
    )
    assert comp["best_home"]["odds"] >= 1.70
    assert comp["best_away"]["odds"] >= 1.90
    assert len(comp["books"]) == len(PERU_SPORTSBOOKS)

    for b in comp["books"]:
        assert b["home_odds"] > 1.0
        assert b["away_odds"] > 1.0
        assert len(b["payment_methods"]) >= 1

    # 3. Verify frontend JSON payload
    frontend_json = get_peru_sportsbooks_json_for_frontend()
    parsed = json.loads(frontend_json)
    assert "sportsbooks" in parsed
    assert len(parsed["sportsbooks"]) == len(PERU_SPORTSBOOKS)


def test_35_v8_shin_devig_peru_inefficiencies_and_obsidian_dataview(tmp_path: Path) -> None:
    """
    Test 35 (V8 Quantitative Upgrades Verification):
    1. Shin's Method (`devig_shin`) and Power De-Vigging (`devig_power`) properly correct
       favorite-longshot bias (assigning higher fair prob to heavy favorite and lower fair prob
       to longshot than naive multiplicative de-vigging, while summing to 1.0).
    2. Peruvian sportsbook comparator anchors retail books (RETAbet, Betsson, Apuesta Total, Doradobet)
       to Shin de-vigged benchmark odds even when neutral 0.5/0.5 fair probs are passed.
    3. `detect_peru_market_inefficiencies` accurately detects cross-bookmaker Surebet/Arbitrage
       and Soft-Book +EV opportunities in Soles (S/. PEN).
    4. `sync_obsidian_vault` generates `00-Inbox/01-Dataview-Quant-Dashboard.md` with DataviewJS & Tracker blocks.
    """
    from src.prediction.ev_calculator import devig_power, devig_shin
    from src.ingestion.peru_sportsbooks import (
        calculate_peru_odds_comparison,
        detect_peru_market_inefficiencies,
    )
    from src.reporting.reporter import sync_obsidian_vault

    # 1. Favorite-Longshot Bias removal verification (Favorite 1.35 vs Longshot 3.40)
    p_fav_mult, p_dog_mult, ov_mult = devig_multiplicative(1.35, 3.40)
    p_fav_shin, p_dog_shin, ov_shin = devig_shin(1.35, 3.40)
    p_fav_pow, p_dog_pow, ov_pow = devig_power(1.35, 3.40)

    assert p_fav_shin + p_dog_shin == pytest.approx(1.0, abs=1e-5)
    assert p_fav_pow + p_dog_pow == pytest.approx(1.0, abs=1e-5)
    assert ov_shin == pytest.approx(ov_mult, abs=1e-5)
    # Shin and Power both assign higher true probability to the favorite and lower to the longshot
    assert p_fav_shin > p_fav_mult
    assert p_dog_shin < p_dog_mult
    assert p_fav_pow > p_fav_mult
    assert p_dog_pow < p_dog_mult

    # Even odds symmetry check
    p1_s, p2_s, _ = devig_shin(1.91, 1.91)
    assert p1_s == pytest.approx(0.50, abs=1e-5)
    assert p2_s == pytest.approx(0.50, abs=1e-5)

    # 2. Peruvian comparator with neutral 0.5/0.5 but heavy favorite benchmark (1.38 vs 3.10)
    comp = calculate_peru_odds_comparison(
        p_home_fair=0.50,
        p_away_fair=0.50,
        benchmark_home_odds=1.38,
        benchmark_away_odds=3.10,
    )
    retabet_row = next(b for b in comp["books"] if b["id"] == "retabet_pe")
    betsson_row = next(b for b in comp["books"] if b["id"] == "betsson_pe")
    # Retail books must reflect the heavy favorite (< 1.45) rather than 1.908
    assert retabet_row["home_odds"] < 1.45
    assert retabet_row["away_odds"] > 2.65
    assert betsson_row["home_odds"] < 1.45
    assert "market_efficiency" in comp

    # 3. Cross-bookmaker Arbitrage (Surebet) & +EV detection
    mock_books = [
        {"id": "coolbet_pe", "name": "Coolbet Perú", "is_mincetur_licensed": True, "home_odds": 2.12, "away_odds": 1.80},
        {"id": "retabet_pe", "name": "RETAbet Perú", "is_mincetur_licensed": True, "home_odds": 1.82, "away_odds": 2.08},
    ]
    ineff = detect_peru_market_inefficiencies(mock_books, model_p_home=0.52, model_p_away=0.48, bankroll_pen=100.0)
    assert ineff["is_surebet_arbitrage"] is True
    assert ineff["arbitrage_roi_pct"] > 2.0
    assert ineff["arbitrage_allocation_pen"] is not None
    assert ineff["arbitrage_allocation_pen"]["guaranteed_profit_pen"] > 2.0
    assert len(ineff["plus_ev_opportunities"]) >= 1

    # 4. Obsidian DataviewJS & Tracker Vault Generation
    dummy_metrics = {
        "current_settled_bankroll_pen": 102.50,
        "net_profit_pen": 2.50,
        "roi_pct": 4.20,
        "mean_clv_pct": 1.45,
        "overall_brier_score": 0.0718,
        "baseline_brier_score": 0.1062,
        "overall_log_loss": 0.2512,
        "baseline_log_loss": 0.3410,
        "settled_bets_count": 64,
        "pending_exposure_pen": 5.00,
        "exit_gates_evaluation": {"recommendation": "REMAIN_IN_PAPER_TRADING"},
    }
    vault_files = sync_obsidian_vault(
        vault_root=tmp_path / "NBA",
        daily_report_md="# Daily",
        weekly_report_md="# Weekly",
        audit_report_md="# Audit",
        metrics=dummy_metrics,
        environment_status={},
        target_date="2026-11-07",
    )
    assert "00-Inbox/01-Dataview-Quant-Dashboard.md" in vault_files
    dv_content = (tmp_path / "NBA" / "00-Inbox" / "01-Dataview-Quant-Dashboard.md").read_text(encoding="utf-8")
    assert "```dataviewjs" in dv_content
    assert "```tracker" in dv_content


# 45. V9 Fase 3: Stale Line Hunter & Risk-Free Cross-Bookmaker Surebet Arbitrage
def test_45_stale_line_latency_and_surebet_arbitrage() -> None:
    """
    Test 45 (V9 Phase 3 Verification):
    1. Stale Line Hunter: Monitors velocity differentials between sharp market-makers (Pinnacle)
       and Peruvian retail bookmakers (RETAbet, Betsson, Doradobet, Inkabet).
    2. Closing Line Value (+CLV) estimation and Kelly stake sizing in Soles (S/. PEN).
    3. Cross-bookmaker Arbitrage / Surebet detection guaranteeing risk-free profit.
    """
    from src.ingestion.stale_line_hunter import StaleLineHunter

    hunter = StaleLineHunter(min_clv_pct=5.0, min_arb_margin_pct=1.0)

    # 1. Stale Line Detection: Sharp line moved to 1.72, RETAbet remains lagged at 1.95
    sharp_line = {
        "bookmaker": "Pinnacle",
        "market": "moneyline",
        "selection": "HOME",
        "decimal_odds": 1.72,
        "is_sharp": True,
        "timestamp": "2026-11-08T22:30:00Z",
    }
    retail_lines = [
        {
            "bookmaker": "RETAbet Perú",
            "market": "moneyline",
            "selection": "HOME",
            "decimal_odds": 1.95,
            "timestamp": "2026-11-08T22:10:00Z",  # 20 mins older!
        },
        {
            "bookmaker": "Doradobet",
            "market": "moneyline",
            "selection": "HOME",
            "decimal_odds": 1.75,
            "timestamp": "2026-11-08T22:28:00Z",
        },
    ]

    stale_picks = hunter.identify_stale_lines(
        game_id="G_STALE_TEST_01",
        matchday_date="2026-11-09",
        sharp_line=sharp_line,
        retail_lines=retail_lines,
        bankroll_pen=100.0,
    )
    assert len(stale_picks) >= 1
    top_stale = stale_picks[0]
    assert top_stale["retail_bookmaker"] == "RETAbet Perú"
    assert top_stale["expected_clv_pct"] > 10.0
    assert 1.0 <= top_stale["kelly_stake_pen"] <= 5.0
    assert top_stale["is_stale_line"] is True

    # 2. Cross-Bookmaker Surebet Arbitrage Calculation
    surebet = hunter.compute_surebet_arbitrage(
        game_id="G_SUREBET_TEST",
        matchday_date="2026-11-09",
        book_a="Betsson Perú",
        selection_a="HOME",
        odds_a=2.15,
        book_b="Coolbet",
        selection_b="AWAY",
        odds_b=2.10,
        total_investment_pen=100.0,
    )
    assert surebet["is_arbitrage"] is True
    assert surebet["arb_margin_pct"] > 5.0
    assert surebet["guaranteed_net_profit_pen"] > 5.0
    assert round(surebet["stake_a_pen"] + surebet["stake_b_pen"], 2) == 100.00
    assert surebet["payout_a_pen"] > 100.00
    assert surebet["payout_b_pen"] > 100.00


# 48. V9 Scraping en Vivo: Real-Time Peruvian Odds Scraper & Arbitrage Monitor
def test_48_live_peru_odds_scraper_and_arbitrage_alerts(tmp_path: Path) -> None:
    """
    Test 48: Verification of Live Peruvian Sportsbook Scraper & Arbitrage Monitor:
    1. Multi-book quote collection across RETAbet, Betsson, Doradobet, Coolbet, Apuesta Total, Pinnacle.
    2. Calculation of best local and away odds and synthetic margin.
    3. Detection of Stale Lines (+CLV) when retail book lags sharp Pinnacle odds.
    4. Detection of Cross-Bookmaker Surebet Arbitrage with Soles (S/. PEN) stake allocation.
    5. Formatting and validation of Telegram Surebet alert.
    """
    from src.ingestion.live_peru_scraper import LivePeruOddsScraper
    from src.reporting.telegram_bot import TelegramAlertBot

    db = DatabaseManager(tmp_path / "test_live_peru.sqlite3")
    scraper = LivePeruOddsScraper(
        db=db,
        min_clv_pct=4.0,
        min_arb_margin_pct=1.0,
        bankroll_pen=100.0,
    )

    # 1. Collect slate odds
    res = scraper.collect_slate_odds(
        game_id="G_LIVE_TEST_1",
        home_team="BOS",
        away_team="MIA",
        game_start_time="2026-11-10T00:00:00Z",
        sharp_home_odds=1.65,
        sharp_away_odds=2.30,
    )

    assert res["game_id"] == "G_LIVE_TEST_1"
    assert "best_home" in res
    assert "best_away" in res
    # Retail quotes derived from the benchmark are DISPLAY-ONLY estimates (never observed)
    assert len(res["quotes"]) >= 8
    assert res["quotes"]["retabet_pe"]["source_type"] == "DERIVED"
    assert res["quotes"]["retabet_pe"]["is_observed"] is False
    assert "sharp_benchmark" in res["quotes"]
    # Estimates are never used for stale-line or surebet detection, and nothing derived is persisted
    assert res["stale_lines"] == []
    assert res["surebet"] is None
    assert db.fetch_one("SELECT COUNT(*) AS c FROM odds_snapshots")["c"] == 0

    # Without an observed benchmark there is no fallback price (the old 1.90/1.91 default is gone)
    res_nobench = scraper.collect_slate_odds(
        game_id="G_LIVE_TEST_2",
        home_team="BOS",
        away_team="MIA",
        game_start_time="2026-11-10T00:00:00Z",
    )
    assert res_nobench["quotes"] == {} or all(q["source_type"] == "OBSERVED" for q in res_nobench["quotes"].values())

    # 2. Test Stale Line identification against sharp benchmark
    # Mocking sharp move to 1.55 on HOME while RETAbet remains lagged at 1.80
    sharp_spec = {"bookmaker": "Pinnacle", "market": "moneyline", "selection": "HOME", "decimal_odds": 1.55}
    retail_lines = [{"bookmaker": "RETAbet Perú", "selection": "HOME", "decimal_odds": 1.80}]
    stale_found = scraper.hunter.identify_stale_lines(
        game_id="G_LIVE_TEST_1",
        matchday_date="2026-11-10",
        sharp_line=sharp_spec,
        retail_lines=retail_lines,
        bankroll_pen=100.0,
    )
    assert len(stale_found) >= 1
    assert stale_found[0]["expected_clv_pct"] > 10.0
    assert stale_found[0]["is_stale_line"] is True

    # 3. Test Surebet Arbitrage detection
    surebet = scraper.hunter.compute_surebet_arbitrage(
        game_id="G_LIVE_TEST_1",
        matchday_date="2026-11-10",
        book_a="Betsson Perú",
        odds_a=2.20,
        selection_a="BOS",
        book_b="Coolbet Perú",
        odds_b=2.15,
        selection_b="MIA",
        total_investment_pen=100.0,
    )
    assert surebet["is_arbitrage"] is True
    assert surebet["arb_margin_pct"] > 5.0
    assert surebet["guaranteed_net_profit_pen"] > 5.0

    # 4. Telegram Surebet alert formatter
    bot = TelegramAlertBot()
    alert_msg = bot.format_surebet_alert(surebet)
    assert "ARBITRAJE LIBRE DE RIESGO" in alert_msg
    assert "Betsson Perú" in alert_msg
    assert "Coolbet Perú" in alert_msg
    assert "S/ 100.00 PEN" in alert_msg


# 49. V9 Phase 4: Bidirectional Interactive Telegram Bot & Slash Commands
def test_49_telegram_interactive_listener_and_commands(tmp_path: Path) -> None:
    """
    Test 49: Verification of Bidirectional Interactive Telegram Bot:
    1. Security filter: Unauthorized chats are rejected with friendly notification.
    2. Authorized command handlers:
       - /start and /ayuda: Returns command directory with clickable actions.
       - /banca: Returns virtual bankroll in Soles (S/. PEN), PnL, Win Rate, and CPPI 85% floor.
       - /picks: Formats pending bets with odds and stakes.
       - /sgp: Formats player props and RETAbet correlated SGPs.
       - /cuotas: Displays Peruvian odds comparison, stale lines, and surebets.
       - /partidos: Displays match slate in Peru Time (PET).
       - Unknown command: Returns friendly fallback with /ayuda prompt.
    3. Mocked update processing and offset pointer progression.
    """
    from src.reporting.telegram_interactive import TelegramInteractiveListener

    db = DatabaseManager(tmp_path / "test_telegram_interactive.sqlite3")
    listener = TelegramInteractiveListener(
        bot_token="TEST_BOT_TOKEN_12345",
        allowed_chat_ids=["5198335170"],
        db=db,
        offset_file=tmp_path / "test_offset.txt",
    )

    # 1. Security Check: Rejection of unauthorized chat
    unauth_resp = listener.process_message(
        chat_id="99999999",
        text="/banca",
        from_user={"first_name": "Intruder", "username": "intruder"},
    )
    assert "Acceso No Autorizado" in unauth_resp
    assert "99999999" in unauth_resp

    # 2. Authorized /start & /ayuda
    start_resp = listener.process_message(
        chat_id="5198335170",
        text="/start",
        from_user={"first_name": "Andre", "username": "andbo06"},
    )
    assert "NBA BETTING INTELLIGENCE V9" in start_resp
    assert "/banca" in start_resp
    assert "/picks" in start_resp
    assert "/sgp" in start_resp
    assert "/cuotas" in start_resp
    assert "/partidos" in start_resp

    # 3. Authorized /banca
    banca_resp = listener.process_message(
        chat_id="5198335170",
        text="/banca",
        from_user={"first_name": "Andre", "username": "andbo06"},
    )
    assert "ESTADO DE LA BANCA VIRTUAL" in banca_resp
    assert "S/ 100.00 PEN" in banca_resp or "S/ 99." in banca_resp
    assert "MODO ALFA PURO" in banca_resp or "Suelo CPPI" in banca_resp
    assert "Régimen:" in banca_resp

    # 4. Authorized /picks
    picks_resp = listener.process_message(
        chat_id="5198335170",
        text="/picks",
        from_user={"first_name": "Andre", "username": "andbo06"},
    )
    assert "PRONÓSTICOS" in picks_resp

    # 5. Authorized /sgp
    sgp_resp = listener.process_message(
        chat_id="5198335170",
        text="/sgp",
        from_user={"first_name": "Andre", "username": "andbo06"},
    )
    assert "PROPS" in sgp_resp.upper() or "RETABET" in sgp_resp.upper()

    # 6. Authorized /cuotas
    cuotas_resp = listener.process_message(
        chat_id="5198335170",
        text="/cuotas",
        from_user={"first_name": "Andre", "username": "andbo06"},
    )
    assert "COMPARADOR DE CUOTAS PERÚ" in cuotas_resp or "No se encontraron cuotas" in cuotas_resp

    # 7. Authorized /partidos
    partidos_resp = listener.process_message(
        chat_id="5198335170",
        text="/partidos",
        from_user={"first_name": "Andre", "username": "andbo06"},
    )
    assert "CARTELERA NBA" in partidos_resp or "No se registraron partidos" in partidos_resp

    # 8. Unrecognized command fallback
    fallback_resp = listener.process_message(
        chat_id="5198335170",
        text="/desconocido",
        from_user={"first_name": "Andre", "username": "andbo06"},
    )
    assert "Comando no reconocido" in fallback_resp
    assert "/ayuda" in fallback_resp

    # 9. Mocked polling cycle & offset tracking
    mock_updates = [
        {
            "update_id": 1001,
            "message": {
                "message_id": 42,
                "chat": {"id": 5198335170},
                "from": {"first_name": "Andre"},
                "text": "/banca",
            },
        }
    ]
    replies_sent: list[tuple[str | int, str]] = []
    listener.get_updates = lambda offset=None, timeout=25: mock_updates if offset != 1002 else []  # type: ignore
    listener.send_reply = lambda chat_id, text, reply_to_message_id=None: replies_sent.append((chat_id, text)) or True  # type: ignore

    processed = listener.run_polling_cycle(timeout=1)
    assert processed == 1
    assert len(replies_sent) == 1
    assert replies_sent[0][0] == 5198335170
    assert "ESTADO DE LA BANCA VIRTUAL" in replies_sent[0][1]
    assert listener.last_update_id == 1002
