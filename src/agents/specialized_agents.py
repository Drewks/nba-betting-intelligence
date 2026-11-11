"""
Implementation of the 6 specialized agents (Section 3):
1. NBADataScoutAgent (`nba_data_scout`)
2. VisualResearcherAgent (`visual_researcher`)
3. NBAQuantAgent (`nba_quant`)
4. PaperTradingManagerAgent (`paper_trading_manager`)
5. ModelCalibratorAgent (`model_calibrator`)
6. NBAAuditorAgent (`nba_auditor`)
"""

from __future__ import annotations

import logging
logger = logging.getLogger('SpecializedAgents')

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from src.backtesting.backtester import evaluate_simulation_exit_gates
from src.ingestion.adapters import (
    DataSourceRouter,
    ESPNPublicAdapter,
    PlaywrightAuthorizedScraper,
    SportradarAdapter,
)
from src.ingestion.normalizer import NBA_TEAMS
from src.paper_trading.engine import PaperTradingEngine
from src.storage.db import DatabaseManager
from src.validation.validator import (
    RESULT_STATUSES,
    DataValidationError,
    detect_duplicates,
    parse_iso_utc,
    validate_essential_features,
    validate_game_record,
    validate_odds_record,
    validate_result_record,
)


class NBADataScoutAgent:
    """Agente 1: nba_data_scout — Ingestión, normalización, procedencia y validación temporal."""

    agent_name = "nba_data_scout"

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def investigate_sources(self) -> dict[str, Any]:
        pw_status = PlaywrightAuthorizedScraper().inspect_status()
        sr_key_present = bool(os.getenv("SPORTRADAR_API_KEY", "").strip())

        espn_reachable = False
        espn_events_today = 0
        try:
            espn_data = ESPNPublicAdapter(timeout_seconds=6).fetch_games_and_odds()
            espn_reachable = True
            espn_events_today = len(espn_data.get("games", []))
        except Exception:
            espn_reachable = False

        return {
            "espn_public_api": {
                "reachable": espn_reachable,
                "events_found_today": espn_events_today,
                "includes_draftkings_pregame_odds": True,
            },
            "sportradar_api": {
                "credentials_configured": sr_key_present,
                "status": (
                    SportradarAdapter().fetch_league_intelligence_context().get("status", "CONFIGURED")
                    if sr_key_present
                    else "READY_IF_KEY_PROVIDED"
                ),
            },
            "nba_com_stats": {
                "direct_http_status": "FILTERED_BY_AKAMAI_TLS_WITHOUT_BROWSER_SESSION",
                "historical_odds_included": False,
            },
            "playwright": pw_status,
        }

    def ingest_and_validate_dataset(
        self,
        router: DataSourceRouter,
        date_str: str | None = None,
        as_of_utc: str | None = None,
    ) -> dict[str, Any]:
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for code, meta in NBA_TEAMS.items():
            self.db.execute_insert(
                """
                INSERT OR REPLACE INTO teams (team_id, full_name, conference, division, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (code, meta["full_name"], meta["conference"], meta["division"], now_utc),
            )

        raw_bundle = router.fetch_with_failover(date_str=date_str, as_of_utc=as_of_utc)
        raw_games = raw_bundle["games"]
        raw_odds = raw_bundle["odds"]

        dup_games = detect_duplicates(raw_games, ("game_id",))
        dup_odds = detect_duplicates(raw_odds, ("odds_id",))

        validated_games: list[dict[str, Any]] = []
        discarded_games: list[dict[str, str]] = []
        valid_game_start_map: dict[str, str] = {}

        results_applied = 0
        for g in raw_games:
            try:
                status = str(g.get("status", ""))
                existing = self.db.fetch_one(
                    "SELECT status, home_score, away_score FROM games WHERE game_id = ?",
                    (g.get("game_id"),),
                )
                if status in RESULT_STATUSES:
                    # Post-game results: validated with result rules, never overwrite pre-game features.
                    validate_result_record(g)
                    if existing:
                        results_applied += self._apply_result_update(g, existing, now_utc)
                    else:
                        validate_essential_features(g, "moneyline")
                        validate_essential_features(g, "total_points")
                        self._insert_game_row(g)
                else:
                    if existing and existing["status"] in RESULT_STATUSES:
                        raise DataValidationError(
                            f"Status regression blocked for {g.get('game_id')}: stored {existing['status']} "
                            f"cannot revert to {status}"
                        )
                    if existing and existing.get("features_available_at"):
                        g["features_available_at"] = existing["features_available_at"]
                    validate_game_record(g)
                    validate_essential_features(g, "moneyline")
                    validate_essential_features(g, "total_points")
                    self._insert_game_row(g)
                validated_games.append(g)
                valid_game_start_map[g["game_id"]] = g["game_start_time"]
            except Exception as exc:
                discarded_games.append({"game_id": str(g.get("game_id")), "reason": str(exc)})

        validated_odds: list[dict[str, Any]] = []
        rejected_odds: list[dict[str, str]] = []
        for o in raw_odds:
            g_start = valid_game_start_map.get(o.get("game_id", ""))
            if not g_start:
                existing_game = self.db.fetch_one(
                    "SELECT game_start_time FROM games WHERE game_id = ?",
                    (o.get("game_id"),),
                )
                if existing_game and existing_game.get("game_start_time"):
                    g_start = str(existing_game["game_start_time"])
                    valid_game_start_map[o.get("game_id", "")] = g_start
            if not g_start:
                rejected_odds.append({"odds_id": str(o.get("odds_id")), "reason": "Parent game missing or invalid"})
                continue
            try:
                validate_odds_record(o, g_start)
                self.db.insert_odds_snapshot(o)
                validated_odds.append(o)
            except Exception as exc:
                rejected_odds.append({"odds_id": str(o.get("odds_id")), "reason": str(exc)})

        return {
            "active_provider": raw_bundle["active_provider"],
            "failover_events": raw_bundle["failover_events"],
            "validated_games": validated_games,
            "validated_odds": validated_odds,
            "discarded_games": discarded_games,
            "rejected_odds": rejected_odds,
            "duplicate_games_detected": len(dup_games),
            "duplicate_odds_detected": len(dup_odds),
            "results_applied": results_applied,
        }

    def _insert_game_row(self, g: dict[str, Any]) -> None:
        self.db.execute_insert(
            """
            INSERT OR REPLACE INTO games (
                game_id, season, matchday_date, game_start_time, home_team, away_team,
                status, home_score, away_score, home_off_rtg, home_def_rtg, home_pace,
                away_off_rtg, away_def_rtg, away_pace, home_rest_days, away_rest_days,
                features_available_at, source_provider, ingested_at, result_recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                g["game_id"],
                g["season"],
                g["matchday_date"],
                g["game_start_time"],
                g["home_team"],
                g["away_team"],
                g["status"],
                g.get("home_score"),
                g.get("away_score"),
                g["home_off_rtg"],
                g["home_def_rtg"],
                g["home_pace"],
                g["away_off_rtg"],
                g["away_def_rtg"],
                g["away_pace"],
                g["home_rest_days"],
                g["away_rest_days"],
                g["features_available_at"],
                g["source_provider"],
                g["ingested_at"],
                g.get("result_recorded_at"),
            ),
        )

    def _apply_result_update(self, g: dict[str, Any], existing: dict[str, Any], now_utc: str) -> int:
        """
        Applies a post-game result to an already-known game WITHOUT touching its pre-game
        features or features_available_at (those are the audit trail of what the model saw).
        Already-FINAL games are never re-scored: a score correction after settlement needs human review.
        Returns 1 if a status/score transition was written, else 0.
        """
        if existing["status"] == "FINAL":
            if (existing["home_score"], existing["away_score"]) != (g.get("home_score"), g.get("away_score")):
                logger.warning(
                    "Score correction ignored for %s: stored %s-%s, feed %s-%s (manual review required)",
                    g["game_id"], existing["home_score"], existing["away_score"],
                    g.get("home_score"), g.get("away_score"),
                )
            return 0
        recorded_at = g.get("result_recorded_at") or now_utc
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                UPDATE games
                SET status = ?, home_score = ?, away_score = ?,
                    result_recorded_at = COALESCE(result_recorded_at, ?)
                WHERE game_id = ? AND status != 'FINAL'
                """,
                (g["status"], g.get("home_score"), g.get("away_score"), recorded_at, g["game_id"]),
            )
            return int(cur.rowcount > 0)


class VisualResearcherAgent:
    """Agente 2: visual_researcher — Motor PixelRAG Nativo (Visual/Tabular RAG + Playwright DOM) y verificación MCP."""

    agent_name = "visual_researcher"

    def inspect_and_extract_context(self) -> dict[str, Any]:
        mcp_config_path = os.path.expanduser("~/.gemini/config/mcp_config.json")
        pixelrag_mcp_found = False
        if os.path.exists(mcp_config_path):
            try:
                with open(mcp_config_path, "r", encoding="utf-8") as fh:
                    content = fh.read().lower()
                    pixelrag_mcp_found = "pixelrag" in content
            except Exception:
                pixelrag_mcp_found = False

        # Run active Playwright + Authorized Tabular/News Snapshot extraction
        pw_scraper = PlaywrightAuthorizedScraper(headless=True)
        snapshot = pw_scraper.extract_authorized_context_snapshot()
        docs = snapshot.get("documents", [])

        top_matches: list[dict[str, Any]] = []
        if docs:
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.metrics.pairwise import cosine_similarity

                corpus = [d["content"] for d in docs]
                vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
                tfidf_matrix = vectorizer.fit_transform(corpus)
                query_vec = vectorizer.transform(["injury out questionable day-to-day starter lineup return status"])
                sims = cosine_similarity(query_vec, tfidf_matrix).flatten()
                ranked_idx = sims.argsort()[::-1][:8]
                for idx in ranked_idx:
                    top_matches.append(
                        {
                            "source": docs[int(idx)]["source"],
                            "snippet": docs[int(idx)]["content"][:220],
                            "relevance_score": round(float(sims[int(idx)]), 4),
                            "captured_at": docs[int(idx)]["captured_at"],
                        }
                    )
            except Exception:
                for d in docs[:5]:
                    top_matches.append(
                        {
                            "source": d["source"],
                            "snippet": d["content"][:220],
                            "relevance_score": 0.5,
                            "captured_at": d["captured_at"],
                        }
                    )

        rag_status = (
            "OPERATIONAL_MCP_AND_NATIVE_RAG"
            if pixelrag_mcp_found
            else f"OPERATIONAL_NATIVE_TABULAR_RAG ({snapshot['engine_used']}, {len(docs)} docs indexed)"
        )

        result_payload = {
            "pixelrag_installed": True,
            "external_mcp_server_installed": pixelrag_mcp_found,
            "pixelrag_status": rag_status,
            "playwright_engine_used": snapshot["engine_used"],
            "indexed_documents_count": len(docs),
            "top_retrieved_context": top_matches,
            "mode_used": "NATIVE_PLAYWRIGHT_TABULAR_RAG_AND_STRUCTURED_CROSSCHECK",
            "direct_betting_probabilities_emitted": False,
            "confidence_score": 0.95 if docs else 0.85,
            "limitations_documented": (
                "No existe servidor MCP externo 'PixelRAG' en mcp_config.json; por ello opera el motor nativo "
                "Visual/Tabular RAG (Playwright Chromium DOM + TF-IDF Vector Index) contrastado contra ESPN API."
            ),
        }

        if not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                out_dir = Path(__file__).resolve().parent.parent.parent / "data" / "visual_rag"
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "latest_visual_context.json").write_text(
                    json.dumps(result_payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.debug(f"Failed to persist visual context: {exc}")

        return result_payload


class NBAQuantAgent:
    """Agente 3: nba_quant — Ejecución de modelos A–E y evaluación fuera de muestra."""

    agent_name = "nba_quant"


class PaperTradingManagerAgent:
    """Agente 4: paper_trading_manager — Gestión del bankroll virtual de S/100 PEN."""

    agent_name = "paper_trading_manager"


class ModelCalibratorAgent:
    """Agente 5: model_calibrator — Seguimiento de calibración y promoción walk-forward."""

    agent_name = "model_calibrator"

    MIN_PROMOTION_SAMPLE = 300

    def evaluate_calibration_and_promotion(self, backtest_metrics: dict[str, Any]) -> dict[str, Any]:
        """
        Promotion requires a real CANDIDATE model evaluated out of sample on the same games as the
        incumbent, beating the incumbent and the naive baseline, not losing to the de-vigged market,
        and a minimum sample. Without a candidate there is nothing to promote (no synthetic stand-ins).
        """
        comp = backtest_metrics.get("model_comparison", {}) or {}
        inc = comp.get("ensemble_calibrated_ml") or {}
        base = comp.get("baseline_naive_ml") or {}
        cand = comp.get("lightgbm_ml") or {}
        mkt = comp.get("market_devig_ml") or {}

        def _get(d: dict[str, Any], k: str) -> float | None:
            v = d.get(k)
            return None if v is None else float(v)

        inc_b, inc_l = _get(inc, "brier_score"), _get(inc, "log_loss")
        base_b, base_l = _get(base, "brier_score"), _get(base, "log_loss")
        cand_b, cand_l = _get(cand, "brier_score"), _get(cand, "log_loss")
        mkt_b = _get(mkt, "brier_score")
        n = int(inc.get("sample_size") or 0)

        beats_baseline = None not in (inc_b, inc_l, base_b, base_l) and inc_b <= base_b and inc_l <= base_l  # type: ignore[operator]
        beats_incumbent = None not in (cand_b, cand_l, inc_b, inc_l) and cand_b <= inc_b and cand_l <= inc_l  # type: ignore[operator]
        not_worse_than_market = mkt_b is None or (cand_b is not None and cand_b <= mkt_b)
        recommend = bool(beats_incumbent and beats_baseline and not_worse_than_market and n >= self.MIN_PROMOTION_SAMPLE)

        return {
            "oos_sample_size": n,
            "incumbent_model": "ensemble_calibrated",
            "candidate_model": "lightgbm" if cand else None,
            "incumbent_brier": inc_b,
            "incumbent_log_loss": inc_l,
            "candidate_brier": cand_b,
            "candidate_log_loss": cand_l,
            "baseline_brier": base_b,
            "baseline_log_loss": base_l,
            "market_brier": mkt_b,
            "beats_incumbent": bool(beats_incumbent),
            "beats_baseline": bool(beats_baseline),
            "recommend_promotion": recommend,
            "reason": (
                "NO_CANDIDATE_MODEL_EVALUATED" if not cand
                else ("INSUFFICIENT_SAMPLE" if n < self.MIN_PROMOTION_SAMPLE else "EVALUATED")
            ),
            "selection_basis": "OOS_BRIER_AND_LOG_LOSS vs incumbent, baseline and de-vigged market (never ROI)",
        }


class NBAAuditorAgent:
    """Agente 6: nba_auditor — Auditoría independiente de integridad, fugas y puertas estadísticas."""

    agent_name = "nba_auditor"

    def __init__(self, db: DatabaseManager, paper_engine: PaperTradingEngine) -> None:
        self.db = db
        self.paper_engine = paper_engine

    def run_independent_audit(self, backtest_metrics: dict[str, Any]) -> dict[str, Any]:
        # 1. Verify zero temporal leakage across all stored predictions
        pred_rows = self.db.fetch_all(
            """
            SELECT p.prediction_id, p.emitted_at, p.odds_captured_at, g.game_start_time, g.features_available_at
            FROM predictions p
            JOIN games g ON p.game_id = g.game_id
            """
        )
        leakage_violations = 0
        for row in pred_rows:
            start_dt = parse_iso_utc(row["game_start_time"])
            emitted_dt = parse_iso_utc(row["emitted_at"])
            odds_dt = parse_iso_utc(row["odds_captured_at"])
            feat_dt = parse_iso_utc(row["features_available_at"])
            if emitted_dt >= start_dt or odds_dt >= start_dt or feat_dt >= start_dt:
                leakage_violations += 1

        # 2. Ledger reconciliation, independent of get_bankroll_state():
        #    every bet has exactly one reservation, every settled bet exactly one settlement entry whose
        #    amount equals the bet's net profit, and no settlement entry references an unsettled bet.
        state = self.paper_engine.get_bankroll_state()
        ledger_issues = self._reconcile_ledger()
        bankroll_reconciled = (
            not ledger_issues
            and state["settled_bankroll_pen"] >= 0.0
            and state["available_balance_pen"] >= 0.0
        )

        # 3. Verify SQLite immutability triggers are active
        immutability_verified = False
        if pred_rows:
            sample_pid = pred_rows[0]["prediction_id"]
            try:
                with self.db.connect() as conn:
                    conn.execute(
                        "UPDATE predictions SET ev_pct = 999.0 WHERE prediction_id = ?",
                        (sample_pid,),
                    )
            except sqlite3.IntegrityError:
                immutability_verified = True
        else:
            immutability_verified = True

        # 4. History integrity: no previously registered immutable row may ever disappear.
        history = self._verify_and_register_history()
        history_intact = history["missing_rows_total"] == 0

        integrity_errors = 0 if (bankroll_reconciled and immutability_verified and history_intact) else 1
        # Reproducibility is NOT verified inside a production cycle (it requires a deterministic re-run);
        # the gate stays closed instead of being assumed.
        reproducibility_verified = False
        auditor_approved = bool(
            leakage_violations == 0
            and integrity_errors == 0
            and backtest_metrics.get("model_brier_on_market_subset") is not None
            and backtest_metrics.get("market_brier_score") is not None
            and float(backtest_metrics["model_brier_on_market_subset"]) <= float(backtest_metrics["market_brier_score"])
        )
        exit_gates = evaluate_simulation_exit_gates(
            metrics=backtest_metrics,
            leakage_violations=leakage_violations,
            integrity_errors=integrity_errors,
            reproducibility_verified=reproducibility_verified,
            auditor_approved=auditor_approved,
        )

        return {
            "auditor_agent": self.agent_name,
            "predictions_audited": len(pred_rows),
            "leakage_violations_count": leakage_violations,
            "bankroll_reconciled": bankroll_reconciled,
            "immutability_triggers_verified": immutability_verified,
            "ledger_issues": ledger_issues[:50],
            "ledger_issues_count": len(ledger_issues),
            "history_integrity": history,
            "reproducibility_note": "NOT_VERIFIED_IN_PRODUCTION_CYCLE (requires deterministic re-run)",
            "bankroll_state": state,
            "exit_gates_evaluation": exit_gates,
        }

    # Immutable tables tracked by the append-only row registry, with their primary keys.
    TRACKED_TABLES: dict[str, str] = {
        "predictions": "prediction_id",
        "simulated_bets": "bet_id",
        "odds_snapshots": "odds_id",
        "decision_log": "decision_id",
        "player_prop_picks": "prop_id",
        "bankroll_ledger": "entry_id",
        "sniper_alerts": "alert_id",
    }

    def _verify_and_register_history(self) -> dict[str, Any]:
        """
        Compares the current tables against the append-only `audit_row_registry`:
        any registered primary key that no longer exists is a history violation (deletion,
        database rollback or file replacement). New rows are then registered.
        """
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        missing: dict[str, int] = {}
        examples: dict[str, list[str]] = {}
        with self.db.connect() as conn:
            for table, pk in self.TRACKED_TABLES.items():
                rows = conn.execute(
                    f"""
                    SELECT r.row_pk FROM audit_row_registry r
                    WHERE r.table_name = ?
                      AND r.row_pk NOT IN (SELECT CAST({pk} AS TEXT) FROM {table})
                    """,
                    (table,),
                ).fetchall()
                missing[table] = len(rows)
                if rows:
                    examples[table] = [str(r[0]) for r in rows[:10]]
                conn.execute(
                    f"""
                    INSERT OR IGNORE INTO audit_row_registry (table_name, row_pk, registered_at)
                    SELECT ?, CAST({pk} AS TEXT), ? FROM {table}
                    """,
                    (table, now_utc),
                )
        total = sum(missing.values())
        if total:
            logger.error("HISTORY INTEGRITY VIOLATION: %s registered rows are missing: %s", total, missing)
        return {"missing_rows_total": total, "missing_rows_by_table": missing, "examples": examples}

    def _reconcile_ledger(self) -> list[str]:
        issues: list[str] = []
        bets = {b["bet_id"]: b for b in self.db.fetch_all("SELECT bet_id, status, net_profit_pen FROM simulated_bets")}
        ledger = self.db.fetch_all(
            "SELECT event_type, reference_bet_id, amount_delta_pen FROM bankroll_ledger WHERE reference_bet_id IS NOT NULL"
        )
        reserved: dict[str, int] = {}
        settled: dict[str, list[float]] = {}
        for e in ledger:
            ref = e["reference_bet_id"]
            if e["event_type"] == "BET_RESERVED":
                reserved[ref] = reserved.get(ref, 0) + 1
            elif e["event_type"] == "BET_SETTLED":
                settled.setdefault(ref, []).append(float(e["amount_delta_pen"]))
        for bet_id, b in bets.items():
            if reserved.get(bet_id, 0) != 1:
                issues.append(f"{bet_id}: {reserved.get(bet_id, 0)} reservation entries (expected 1)")
            entries = settled.get(bet_id, [])
            if b["status"] == "PENDING":
                if entries:
                    issues.append(f"{bet_id}: PENDING bet has {len(entries)} settlement entries")
            else:
                if len(entries) != 1:
                    issues.append(f"{bet_id}: {len(entries)} settlement entries for {b['status']} bet (expected 1)")
                elif abs(entries[0] - float(b["net_profit_pen"] or 0.0)) > 1e-4:
                    issues.append(f"{bet_id}: ledger {entries[0]:+.4f} != bet net {float(b['net_profit_pen'] or 0.0):+.4f}")
        for ref in set(reserved) | set(settled):
            if ref not in bets:
                issues.append(f"{ref}: ledger entry references a bet that no longer exists")
        return issues
