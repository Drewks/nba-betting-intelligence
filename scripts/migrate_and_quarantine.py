import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# 1. Update src/storage/schema.py
schema_path = Path("src/storage/schema.py")
content = schema_path.read_text(encoding="utf-8")

old_odds_table = """    CREATE TABLE IF NOT EXISTS odds_snapshots (
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
    );"""

new_odds_table = """    CREATE TABLE IF NOT EXISTS odds_snapshots (
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
        source_type TEXT NOT NULL DEFAULT 'OBSERVED' CHECK (source_type IN ('OBSERVED', 'DERIVED', 'SYNTHETIC')),
        FOREIGN KEY (game_id) REFERENCES games(game_id)
    );
    \"\"\",
    \"\"\"
    CREATE TABLE IF NOT EXISTS quarantined_odds (
        odds_id TEXT PRIMARY KEY,
        reason TEXT NOT NULL,
        quarantined_at TEXT NOT NULL
    );
    \"\"\",
    \"\"\"
    CREATE VIEW IF NOT EXISTS v_observed_odds_snapshots AS
    SELECT * FROM odds_snapshots
    WHERE odds_id NOT IN (SELECT odds_id FROM quarantined_odds)
      AND source_type = 'OBSERVED';
    \"\"\",
    \"\"\"
    CREATE VIEW IF NOT EXISTS v_observed_predictions AS
    SELECT p.* FROM predictions p
    WHERE odds_provider NOT LIKE '%T-6H%'
      AND odds_provider NOT LIKE '%Synthetic%'
      AND NOT (odds_provider = 'draftkings' AND p.decimal_odds_used = 1.90);
    \"\"\",
    \"\"\"
    CREATE VIEW IF NOT EXISTS v_observed_simulated_bets AS
    SELECT b.* FROM simulated_bets b
    JOIN v_observed_predictions p ON b.prediction_id = p.prediction_id;"""

# Normalize CRLF
content_norm = content.replace("\r\n", "\n")
old_odds_table_norm = old_odds_table.replace("\r\n", "\n")

if old_odds_table_norm in content_norm:
    content_norm = content_norm.replace(old_odds_table_norm, new_odds_table)
    schema_path.write_text(content_norm, encoding="utf-8")
    print("Successfully updated src/storage/schema.py")
else:
    print("Warning: old_odds_table not found in src/storage/schema.py")

# 2. Update real SQLite database data/nba_intelligence.sqlite3
db_path = Path("data/nba_intelligence.sqlite3")
if db_path.exists():
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check if source_type column exists
    cur.execute("PRAGMA table_info(odds_snapshots)")
    cols = [r[1] for r in cur.fetchall()]
    if "source_type" not in cols:
        print("Adding source_type column to odds_snapshots...")
        cur.execute("ALTER TABLE odds_snapshots ADD COLUMN source_type TEXT NOT NULL DEFAULT 'OBSERVED' CHECK (source_type IN ('OBSERVED', 'DERIVED', 'SYNTHETIC'))")

    # Create quarantine table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS quarantined_odds (
        odds_id TEXT PRIMARY KEY,
        reason TEXT NOT NULL,
        quarantined_at TEXT NOT NULL
    )
    """)

    # Create Views
    cur.execute("DROP VIEW IF EXISTS v_observed_odds_snapshots")
    cur.execute("""
    CREATE VIEW v_observed_odds_snapshots AS
    SELECT * FROM odds_snapshots
    WHERE odds_id NOT IN (SELECT odds_id FROM quarantined_odds)
      AND source_type = 'OBSERVED'
    """)

    cur.execute("DROP VIEW IF EXISTS v_observed_predictions")
    cur.execute("""
    CREATE VIEW v_observed_predictions AS
    SELECT p.* FROM predictions p
    WHERE odds_provider NOT LIKE '%T-6H%'
      AND odds_provider NOT LIKE '%Synthetic%'
      AND NOT (odds_provider = 'draftkings' AND p.decimal_odds_used = 1.90)
    """)

    cur.execute("DROP VIEW IF EXISTS v_observed_simulated_bets")
    cur.execute("""
    CREATE VIEW v_observed_simulated_bets AS
    SELECT b.* FROM simulated_bets b
    JOIN v_observed_predictions p ON b.prediction_id = p.prediction_id
    """)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Mark and quarantine fabricated odds:
    # 1. T-6H Peru synthetic quotes
    # 2. SyntheticBook_Authorized
    # 3. 1.90/1.90 draftkings fallbacks
    cur.execute("""
        SELECT odds_id, provider, decimal_odds, counterpart_decimal_odds FROM odds_snapshots
        WHERE provider LIKE '%T-6H%'
           OR provider LIKE '%SyntheticBook%'
           OR (provider = 'draftkings' AND decimal_odds = 1.90 AND counterpart_decimal_odds = 1.90)
           OR (provider LIKE '%Pinnacle (Per%' AND decimal_odds = 1.908)
    """)
    rows_to_quarantine = cur.fetchall()
    print(f"Found {len(rows_to_quarantine)} fabricated odds snapshots to quarantine.")

    for oid, prov, o_h, o_a in rows_to_quarantine:
        reason = f"AUDIT_QUARANTINE: Fabricated/synthetic odds without observed market quote ({prov}, {o_h}/{o_a})"
        cur.execute("INSERT OR IGNORE INTO quarantined_odds (odds_id, reason, quarantined_at) VALUES (?, ?, ?)", (oid, reason, now_iso))

    conn.commit()

    # Verify observed view
    cur.execute("SELECT count(*) FROM v_observed_odds_snapshots")
    obs_odds = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM v_observed_simulated_bets")
    obs_bets = cur.fetchone()[0]
    print(f"Database migrated successfully! Observed odds: {obs_odds}, Observed bets: {obs_bets}")
    conn.close()
