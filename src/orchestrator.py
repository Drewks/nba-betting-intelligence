"""
Main Coordinator (`orchestrator` on Gemini Argon):
Controls the 12-phase sequential workflow, waits for each agent's completion before invoking the next,
enforces at most 2 controlled retries on failure, and halts for human intervention if errors persist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import uuid

from src.agents.specialized_agents import (
    ModelCalibratorAgent,
    NBAAuditorAgent,
    NBADataScoutAgent,
    VisualResearcherAgent,
)
from src.backtesting.backtester import WalkForwardBacktester
from src.ingestion.adapters import DataSourceRouter, ESPNPublicAdapter, SyntheticFixtureAdapter
from src.paper_trading.engine import PaperTradingEngine
from src.reporting.reporter import (
    export_bets_and_tracking_dashboard,
    generate_audit_report,
    generate_daily_report,
    generate_weekly_report,
    sync_obsidian_vault,
)
from src.storage.db import DatabaseManager


class HumanInterventionRequiredError(RuntimeError):
    """Raised when a sequential agent fails after the maximum 2 controlled retries."""


class Orchestrator:
    """Sequential multi-agent coordinator for NBA Betting Intelligence."""

    def __init__(
        self,
        db_path: str | Path = "data/nba_intelligence.sqlite3",
        reports_dir: str | Path = "reports",
        obsidian_vault_dir: str | Path = "NBA",
        max_retries: int = 2,
    ) -> None:
        self.db = DatabaseManager(db_path)
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.obsidian_vault_dir = Path(obsidian_vault_dir)
        self.max_retries = max_retries
        self.run_id = f"RUN_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6].upper()}"

        self.paper_engine = PaperTradingEngine(
            db=self.db,
            initial_bankroll_pen=100.00,
            base_stake_pen=1.00,
            max_stake_pen=1.00,
            max_selections_per_matchday=3,
            min_ev_threshold=0.05,
        )
        self.scout_agent = NBADataScoutAgent(self.db)
        self.visual_agent = VisualResearcherAgent()
        self.calibrator_agent = ModelCalibratorAgent()
        self.auditor_agent = NBAAuditorAgent(self.db, self.paper_engine)

    def execute_step_sequentially(
        self,
        phase_number: int,
        agent_name: str,
        step_fn: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Executes a single agent step synchronously, waiting for full delivery before returning.
        Retries at most self.max_retries (2) times before raising HumanInterventionRequiredError.
        """
        exec_id = f"{self.run_id}_P{phase_number:02d}_{agent_name}"
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for attempt in range(self.max_retries + 1):
            try:
                self.db.log_agent_execution(
                    exec_id=exec_id,
                    run_id=self.run_id,
                    phase_number=phase_number,
                    agent_name=agent_name,
                    status="STARTED" if attempt == 0 else "RETRYING",
                    retry_count=attempt,
                    started_at=started_at,
                    completed_at=None,
                    details={"attempt": attempt + 1},
                )
                result = step_fn()
                completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                self.db.log_agent_execution(
                    exec_id=exec_id,
                    run_id=self.run_id,
                    phase_number=phase_number,
                    agent_name=agent_name,
                    status="COMPLETED",
                    retry_count=attempt,
                    started_at=started_at,
                    completed_at=completed_at,
                    details={"status": "OK"},
                )
                return result
            except Exception as exc:
                completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                self.db.log_agent_execution(
                    exec_id=exec_id,
                    run_id=self.run_id,
                    phase_number=phase_number,
                    agent_name=agent_name,
                    status="FAILED",
                    retry_count=attempt,
                    started_at=started_at,
                    completed_at=completed_at,
                    details={"error": str(exc)},
                )
                if attempt >= self.max_retries:
                    raise HumanInterventionRequiredError(
                        f"Agent '{agent_name}' failed in Phase {phase_number} after {self.max_retries} retries. "
                        f"Human intervention required. Last error: {exc}"
                    ) from exc
        raise HumanInterventionRequiredError(f"Unreachable retry state for {agent_name}")

    def run_full_pipeline(self, include_live_espn: bool = True) -> dict[str, Any]:
        """Executes the complete sequential multi-agent pipeline and generates all reports."""
        # Step 1: Investigate sources (nba_data_scout)
        sources_info = self.execute_step_sequentially(
            1, "nba_data_scout", lambda: self.scout_agent.investigate_sources()
        )

        # Step 2: Ingest and validate historical walk-forward dataset + optional live ESPN slate (nba_data_scout)
        def _step2_ingest() -> dict[str, Any]:
            syn_router = DataSourceRouter([SyntheticFixtureAdapter(seed=42, num_matchdays=45, games_per_day=5)])
            hist_bundle = self.scout_agent.ingest_and_validate_dataset(syn_router)
            live_bundle: dict[str, Any] = {"validated_games": [], "validated_odds": [], "discarded_games": []}
            if include_live_espn and sources_info["espn_public_api"]["reachable"]:
                try:
                    live_router = DataSourceRouter([ESPNPublicAdapter(timeout_seconds=8)])
                    live_bundle = self.scout_agent.ingest_and_validate_dataset(live_router)
                except Exception:
                    pass
            return {"historical": hist_bundle, "live_espn": live_bundle}

        ingestion_result = self.execute_step_sequentially(2, "nba_data_scout", _step2_ingest)

        # Step 3: Visual & unstructured context verification (visual_researcher)
        visual_context = self.execute_step_sequentially(
            3, "visual_researcher", lambda: self.visual_agent.inspect_and_extract_context()
        )

        # Steps 4-8: Chronological predictions, selection controls, virtual betting, and settlement
        backtester = WalkForwardBacktester(
            db=self.db,
            paper_engine=self.paper_engine,
            warmup_matchdays=12,
            retrain_every_matchdays=10,
        )
        all_games = (
            ingestion_result["historical"]["validated_games"]
            + ingestion_result["live_espn"]["validated_games"]
        )
        all_odds = (
            ingestion_result["historical"]["validated_odds"]
            + ingestion_result["live_espn"]["validated_odds"]
        )

        backtest_metrics = self.execute_step_sequentially(
            4, "nba_quant_and_paper_trading_manager",
            lambda: backtester.run_walk_forward(games=all_games, odds=all_odds),
        )

        # Steps 9 & 10: Evaluate calibration and controlled retraining promotion (model_calibrator)
        promotion_eval = self.execute_step_sequentially(
            9, "model_calibrator",
            lambda: self.calibrator_agent.evaluate_calibration_and_promotion(backtest_metrics),
        )

        # Step 11: Independent audit (nba_auditor)
        audit_result = self.execute_step_sequentially(
            11, "nba_auditor",
            lambda: self.auditor_agent.run_independent_audit(backtest_metrics),
        )

        # Step 12: Generate reports and sync Obsidian Vault (orchestrator)
        def _step12_reports() -> dict[str, Any]:
            matchdays = sorted({g["matchday_date"] for g in all_games})
            target_date = matchdays[-1] if matchdays else datetime.now(timezone.utc).strftime("%Y-%m-%d")
            env_status = {
                "python_version": "CPython 3.12.13 (uv virtual environment)",
                "sportradar_status": sources_info["sportradar_api"]["status"],
                "nba_stats_status": sources_info["nba_com_stats"]["direct_http_status"],
                "playwright_status": sources_info["playwright"]["status"],
                "pixelrag_status": visual_context["pixelrag_status"],
                "obsidian_vault_path": str(self.obsidian_vault_dir),
            }

            daily_md = generate_daily_report(
                self.db,
                target_date=target_date,
                live_games_summary=ingestion_result["live_espn"],
            )
            weekly_md = generate_weekly_report(backtest_metrics, promotion_eval)
            audit_md = generate_audit_report(audit_result, env_status)

            (self.reports_dir / "daily_report.md").write_text(daily_md, encoding="utf-8")
            (self.reports_dir / "weekly_report.md").write_text(weekly_md, encoding="utf-8")
            (self.reports_dir / "audit_report.md").write_text(audit_md, encoding="utf-8")

            root_dir = self.reports_dir.parent
            export_bets_and_tracking_dashboard(
                db=self.db,
                metrics=backtest_metrics,
                csv_output_path=root_dir / "data" / "apuestas_historial.csv",
                md_output_path=root_dir / "SEGUIMIENTO_APUESTAS.md",
            )

            obsidian_files = sync_obsidian_vault(
                vault_root=self.obsidian_vault_dir,
                daily_report_md=daily_md,
                weekly_report_md=weekly_md,
                audit_report_md=audit_md,
                metrics=backtest_metrics,
                environment_status=env_status,
                target_date=target_date,
            )
            return {
                "target_date": target_date,
                "daily_report_path": str(self.reports_dir / "daily_report.md"),
                "weekly_report_path": str(self.reports_dir / "weekly_report.md"),
                "audit_report_path": str(self.reports_dir / "audit_report.md"),
                "obsidian_files_count": len(obsidian_files),
            }

        reports_info = self.execute_step_sequentially(12, "orchestrator", _step12_reports)

        return {
            "run_id": self.run_id,
            "sources_info": sources_info,
            "visual_context": visual_context,
            "backtest_metrics": backtest_metrics,
            "promotion_eval": promotion_eval,
            "audit_result": audit_result,
            "reports_info": reports_info,
        }
