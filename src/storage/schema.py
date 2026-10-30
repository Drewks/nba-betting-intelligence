"""SQLite database schema with strict immutability triggers for predictions and paper trading."""

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS teams (
        team_id TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        conference TEXT NOT NULL,
        division TEXT NOT NULL,
        source_ids_json TEXT DEFAULT '{}',
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS games (
        game_id TEXT PRIMARY KEY,
        season TEXT NOT NULL,
        matchday_date TEXT NOT NULL,
        game_start_time TEXT NOT NULL,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('SCHEDULED', 'FINAL', 'POSTPONED', 'CANCELLED')),
        home_score INTEGER,
        away_score INTEGER,
        home_off_rtg REAL,
        home_def_rtg REAL,
        home_pace REAL,
        away_off_rtg REAL,
        away_def_rtg REAL,
        away_pace REAL,
        home_rest_days INTEGER,
        away_rest_days INTEGER,
        features_available_at TEXT NOT NULL,
        source_provider TEXT NOT NULL,
        ingested_at TEXT NOT NULL,
        result_recorded_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS odds_snapshots (
        odds_id TEXT PRIMARY KEY,
        game_id TEXT NOT NULL,
        provider TEXT NOT NULL,
        market TEXT NOT NULL CHECK (market IN ('moneyline', 'total_points')),
        selection TEXT NOT NULL CHECK (selection IN ('HOME', 'AWAY', 'OVER', 'UNDER')),
        line_value REAL,
        decimal_odds REAL NOT NULL CHECK (decimal_odds > 1.0),
        counterpart_decimal_odds REAL CHECK (counterpart_decimal_odds IS NULL OR counterpart_decimal_odds > 1.0),
        captured_at TEXT NOT NULL,
        is_closing_line INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (game_id) REFERENCES games(game_id)
    );
    """,
    """
    CREATE TRIGGER IF NOT EXISTS prevent_odds_update
    BEFORE UPDATE ON odds_snapshots
    BEGIN
        SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Captured odds snapshots cannot be modified.');
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS prevent_odds_delete
    BEFORE DELETE ON odds_snapshots
    BEGIN
        SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Captured odds snapshots cannot be deleted.');
    END;
    """,
    """
    CREATE TABLE IF NOT EXISTS model_versions (
        model_version_id TEXT PRIMARY KEY,
        model_family TEXT NOT NULL,
        market TEXT NOT NULL CHECK (market IN ('moneyline', 'total_points')),
        train_start_date TEXT NOT NULL,
        train_end_date TEXT NOT NULL,
        trained_at TEXT NOT NULL,
        hyperparameters_json TEXT NOT NULL,
        oos_brier_score REAL,
        oos_log_loss REAL,
        is_active INTEGER NOT NULL DEFAULT 0,
        approved_by TEXT NOT NULL,
        parent_version_id TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS predictions (
        prediction_id TEXT PRIMARY KEY,
        game_id TEXT NOT NULL,
        market TEXT NOT NULL CHECK (market IN ('moneyline', 'total_points')),
        selection TEXT NOT NULL CHECK (selection IN ('HOME', 'AWAY', 'OVER', 'UNDER')),
        line_value REAL,
        model_version_id TEXT NOT NULL,
        raw_probability REAL NOT NULL CHECK (raw_probability >= 0.0 AND raw_probability <= 1.0),
        calibrated_probability REAL NOT NULL CHECK (calibrated_probability >= 0.0 AND calibrated_probability <= 1.0),
        uncertainty_std REAL NOT NULL CHECK (uncertainty_std >= 0.0),
        implied_prob_gross REAL NOT NULL,
        implied_prob_fair REAL,
        bookmaker_overround REAL,
        decimal_odds_used REAL NOT NULL CHECK (decimal_odds_used > 1.0),
        odds_provider TEXT NOT NULL,
        odds_captured_at TEXT NOT NULL,
        ev_unit REAL NOT NULL,
        ev_pct REAL NOT NULL,
        emitted_at TEXT NOT NULL,
        features_snapshot_json TEXT NOT NULL,
        FOREIGN KEY (game_id) REFERENCES games(game_id),
        FOREIGN KEY (model_version_id) REFERENCES model_versions(model_version_id)
    );
    """,
    """
    CREATE TRIGGER IF NOT EXISTS prevent_prediction_update
    BEFORE UPDATE ON predictions
    BEGIN
        SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Historical predictions cannot be modified.');
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS prevent_prediction_delete
    BEFORE DELETE ON predictions
    BEGIN
        SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Historical predictions cannot be deleted.');
    END;
    """,
    """
    CREATE TABLE IF NOT EXISTS simulated_bets (
        bet_id TEXT PRIMARY KEY,
        prediction_id TEXT NOT NULL UNIQUE,
        game_id TEXT NOT NULL,
        matchday_date TEXT NOT NULL,
        market TEXT NOT NULL CHECK (market IN ('moneyline', 'total_points')),
        selection TEXT NOT NULL CHECK (selection IN ('HOME', 'AWAY', 'OVER', 'UNDER')),
        line_value REAL,
        decimal_odds REAL NOT NULL CHECK (decimal_odds > 1.0),
        estimated_prob REAL NOT NULL,
        estimated_ev REAL NOT NULL,
        stake_pen REAL NOT NULL CHECK (stake_pen > 0.0 AND stake_pen <= 25.0),
        emitted_at TEXT NOT NULL,
        model_version_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('PENDING', 'WON', 'LOST', 'PUSH', 'VOID')),
        net_profit_pen REAL,
        bankroll_after_pen REAL,
        actual_result_summary TEXT,
        settled_at TEXT,
        UNIQUE(game_id, market, selection, line_value),
        FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id),
        FOREIGN KEY (game_id) REFERENCES games(game_id)
    );
    """,
    """
    CREATE TRIGGER IF NOT EXISTS prevent_settled_bet_tampering
    BEFORE UPDATE ON simulated_bets
    BEGIN
        SELECT CASE
            WHEN OLD.status != 'PENDING' THEN
                RAISE(ABORT, 'DOUBLE_SETTLEMENT_OR_TAMPERING: Bet has already been settled and is immutable.')
            WHEN NEW.decimal_odds != OLD.decimal_odds
              OR NEW.stake_pen != OLD.stake_pen
              OR NEW.selection != OLD.selection
              OR COALESCE(NEW.line_value, -9999) != COALESCE(OLD.line_value, -9999)
              OR NEW.prediction_id != OLD.prediction_id
              OR NEW.emitted_at != OLD.emitted_at
              OR NEW.estimated_prob != OLD.estimated_prob
              OR NEW.estimated_ev != OLD.estimated_ev THEN
                RAISE(ABORT, 'IMMUTABLE_VIOLATION: Original bet parameters and odds cannot be modified.')
        END;
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS prevent_bet_delete
    BEFORE DELETE ON simulated_bets
    BEGIN
        SELECT RAISE(ABORT, 'IMMUTABLE_VIOLATION: Simulated bets cannot be deleted from audit history.');
    END;
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_log (
        decision_id TEXT PRIMARY KEY,
        game_id TEXT NOT NULL,
        matchday_date TEXT NOT NULL,
        market TEXT NOT NULL,
        selection TEXT NOT NULL,
        decision_type TEXT NOT NULL CHECK (decision_type IN ('BET_PLACED', 'NO_BET')),
        reason_code TEXT NOT NULL,
        reason_detail TEXT NOT NULL,
        ev_pct REAL,
        emitted_at TEXT NOT NULL,
        model_version_id TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS bankroll_ledger (
        entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL CHECK (event_type IN ('INITIAL_VIRTUAL_BANKROLL', 'BET_RESERVED', 'BET_SETTLED')),
        reference_bet_id TEXT,
        amount_delta_pen REAL NOT NULL,
        settled_bankroll_pen REAL NOT NULL CHECK (settled_bankroll_pen >= 0.0),
        pending_exposure_pen REAL NOT NULL CHECK (pending_exposure_pen >= 0.0),
        available_balance_pen REAL NOT NULL CHECK (available_balance_pen >= 0.0)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS calibration_logs (
        eval_id TEXT PRIMARY KEY,
        evaluated_at TEXT NOT NULL,
        model_version_id TEXT NOT NULL,
        market TEXT NOT NULL,
        sample_size INTEGER NOT NULL,
        brier_score REAL NOT NULL,
        log_loss REAL NOT NULL,
        ece REAL NOT NULL,
        calibration_method TEXT NOT NULL,
        bins_json TEXT NOT NULL,
        promoted INTEGER NOT NULL DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_execution_log (
        exec_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        phase_number INTEGER NOT NULL,
        agent_name TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('STARTED', 'COMPLETED', 'FAILED', 'RETRYING')),
        retry_count INTEGER NOT NULL DEFAULT 0,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        details_json TEXT NOT NULL
    );
    """,
]
