"""
Builds the audit-history recovery bundle consumed by migration
`2026_11_09_003_restore_history_from_93cfa87` (src/storage/migrations.py).

Context: on 2026-11-09 the bot's database (commit 93cfa87) was replaced by an older snapshot and
164 predictions were deleted to create a unique index. This script diffs a SOURCE database (the bot's
last good state) against a TARGET database (the damaged one) and emits a deterministic JSON bundle with:
  - missing_rows: rows present in SOURCE and absent in TARGET (to be re-inserted),
  - game_result_restores: FINAL results rolled back to non-FINAL,
  - bet_settlement_restores: settled bets rolled back to PENDING,
  - prop_settlements_overwritten: settled props overwritten to VOID (documented, not reverted).

Usage:
  git show 93cfa87:data/nba_intelligence.sqlite3 > /tmp/source.sqlite3
  uv run python scripts/build_recovery_bundle.py --source /tmp/source.sqlite3 \
      --target data/nba_intelligence.sqlite3 --source-ref 93cfa87
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.migrations import RECOVERY_BUNDLE_PATH

TABLE_PKS: dict[str, str] = {
    "odds_snapshots": "odds_id",
    "predictions": "prediction_id",
    "simulated_bets": "bet_id",
    "decision_log": "decision_id",
    "player_prop_picks": "prop_id",
    "bankroll_ledger": "entry_id",
}

UNOBSERVED_MARKERS = ("[T-6H Peru]", "[LIVE_SCRAPER]", "Synthetic", "Calibrated Feed")


def _classify_source_type(row: dict[str, Any]) -> str:
    provider = str(row.get("provider") or "")
    if str(row.get("game_id", "")).startswith("SYN") or "Synthetic" in provider:
        return "SYNTHETIC"
    if any(m in provider for m in UNOBSERVED_MARKERS):
        return "SYNTHETIC"
    return "OBSERVED"


def build_bundle(source: Path, target: Path, source_ref: str) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute(f"ATTACH DATABASE 'file:{source}?mode=ro' AS src")

    missing_rows: dict[str, list[dict[str, Any]]] = {}
    for table, pk in TABLE_PKS.items():
        rows = conn.execute(
            f"SELECT * FROM src.{table} WHERE {pk} NOT IN (SELECT {pk} FROM main.{table}) ORDER BY {pk}"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if table == "odds_snapshots":
                d["source_type"] = d.get("source_type") or _classify_source_type(d)
            out.append(d)
        missing_rows[table] = out

    game_result_restores = [
        dict(r)
        for r in conn.execute(
            """
            SELECT s.game_id, s.status, s.home_score, s.away_score, s.result_recorded_at
            FROM src.games s JOIN main.games m ON s.game_id = m.game_id
            WHERE s.status = 'FINAL' AND m.status != 'FINAL'
            ORDER BY s.game_id
            """
        ).fetchall()
    ]
    bet_settlement_restores = [
        dict(r)
        for r in conn.execute(
            """
            SELECT s.bet_id, s.status, s.net_profit_pen, s.bankroll_after_pen, s.actual_result_summary, s.settled_at
            FROM src.simulated_bets s JOIN main.simulated_bets m ON s.bet_id = m.bet_id
            WHERE s.status != 'PENDING' AND m.status = 'PENDING'
            ORDER BY s.bet_id
            """
        ).fetchall()
    ]
    prop_settlements_overwritten = [
        dict(r)
        for r in conn.execute(
            """
            SELECT s.prop_id, s.status AS original_status, s.net_profit_pen AS original_net_profit_pen
            FROM src.player_prop_picks s JOIN main.player_prop_picks m ON s.prop_id = m.prop_id
            WHERE s.status IN ('WON', 'LOST', 'PUSH') AND m.status = 'VOID'
            ORDER BY s.prop_id
            """
        ).fetchall()
    ]

    payload = {
        "missing_rows": missing_rows,
        "game_result_restores": game_result_restores,
        "bet_settlement_restores": bet_settlement_restores,
        "prop_settlements_overwritten": prop_settlements_overwritten,
    }
    payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return {
        "bundle_version": 1,
        "source_ref": source_ref,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": {
            **{f"missing_{t}": len(v) for t, v in missing_rows.items()},
            "game_result_restores": len(game_result_restores),
            "bet_settlement_restores": len(bet_settlement_restores),
            "prop_settlements_overwritten": len(prop_settlements_overwritten),
        },
        "payload_sha256": hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
        "payload": payload,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the audit-history recovery bundle.")
    parser.add_argument("--source", required=True, help="Bot's last good database (e.g. from commit 93cfa87)")
    parser.add_argument("--target", default=str(PROJECT_ROOT / "data" / "nba_intelligence.sqlite3"))
    parser.add_argument("--source-ref", default="93cfa87")
    parser.add_argument("--out", default=str(RECOVERY_BUNDLE_PATH))
    args = parser.parse_args()

    bundle = build_bundle(Path(args.source), Path(args.target), args.source_ref)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(bundle["counts"], indent=2))
    print(f"sha256={bundle['payload_sha256']} -> {out}")


if __name__ == "__main__":
    main()
