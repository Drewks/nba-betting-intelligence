"""
Experimental NBA Player Props & SGP Quantitative Engine (Quarantined).

Production status: QUARANTINED (`allow_player_props_betting: false`, `allow_parlays: false`
in `config/model_config.yaml`). Retained behind fail-closed risk gates for calibration
benchmarks and controlled unit tests only.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any
import uuid

import numpy as np

from src.calibration.calibrator import VennAbersConformalInterval
from src.config import RiskConfig, load_config
from src.prediction.minutes_model import MinutesProjectionEngine
from src.prediction.multivariate_copula import MultivariateStudentTCopula
from src.prediction.props.calibration import (
    build_historical_props_calibration_dataset as _build_cal_dataset,
    evaluate_prop_opportunity_impl,
    fit_props_calibrators,
)
from src.prediction.props.parlays import (
    generate_high_probability_parlays_impl,
    scan_retabet_sgp_slate_impl,
    simulate_same_game_parlay_copula_impl,
)
from src.prediction.props.projector import (
    compute_ewma_baseline_from_records as _compute_ewma,
    get_player_baseline as _get_player_baseline,
    get_team_defensive_multipliers as _get_team_multipliers,
    project_player_stats as _project_player_stats,
    resolve_as_of_cutoff as _resolve_cutoff,
)
from src.prediction.props.quarantine import (
    _normalize_player_match_key,
    _parse_observed_prop_provider,
    check_props_risk_gate,
    log_blocked_prop_decision,
    persist_prop_pick,
    persist_sgp_pick,
    props_exposure_allows,
    props_may_record,
)
from src.prediction.props_constants import get_fallback_rosters
from src.prediction.props_distribution import (
    compute_exceedance_probabilities as compute_exceedance_probs_math,
)
from src.storage.db import DatabaseManager

logger = logging.getLogger(__name__)

EXPERIMENTAL_QUARANTINED: bool = True


class PlayerPropsEngine:
    """Quarantined quantitative engine for experimental NBA Player Props & SGP simulation."""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        min_ev_threshold: float = 0.05,
        risk_config: RiskConfig | None = None,
        allow_player_props: bool | None = None,
        category_min_samples: int = 30,
        global_min_samples: int = 60,
    ) -> None:
        self.db = db
        self.min_ev_threshold = min_ev_threshold
        self._config_load_error: str | None = None
        self.model_version_id: str = "model_f_ensemble_v8"
        if risk_config is not None:
            self.risk: RiskConfig | None = risk_config
        else:
            try:
                cfg = load_config()
                self.risk = cfg.risk
                self.model_version_id = getattr(getattr(cfg, "model", None), "version_id", "model_f_ensemble_v8")
            except Exception as exc:
                self.risk = None
                self._config_load_error = str(exc)

        if self.risk is not None:
            if allow_player_props is not None:
                self.risk = replace(self.risk, allow_player_props_betting=bool(allow_player_props))
            self.kelly_fraction = self.risk.kelly_fraction
            self.max_stake_pen = self.risk.max_stake_pen
            self.max_bankroll_fraction = self.risk.max_stake_bankroll_fraction
        else:
            self.kelly_fraction = 0.25
            self.max_stake_pen = 5.0
            self.max_bankroll_fraction = 0.03

        self.global_min_samples = max(10, int(global_min_samples))
        self.category_min_samples = max(10, int(category_min_samples))
        self.calibrator = VennAbersConformalInterval(window=1200, min_samples=self.global_min_samples)
        self.category_calibrators: dict[str, VennAbersConformalInterval] = {}
        self.calibration_cutoff_utc: str | None = None
        self.calibration_dataset_size: int = 0
        self.oos_calibration_dataset: list[dict[str, Any]] = []
        self.calibration_summary: dict[str, Any] = {
            "global": {"is_fitted": False, "sample_size": 0, "cutoff_utc": None},
            "categories": {},
        }
        self.minutes_engine = MinutesProjectionEngine()
        self.copula_engine = MultivariateStudentTCopula()
        self._player_baselines_cache: dict[tuple[str, str], tuple[float, float, float, float, float, float]] = {}
        self._team_multipliers_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def _log_blocked_prop_decision(
        self,
        *,
        game_id: str,
        matchday_date: str,
        market: str,
        selection: str,
        reason_code: str,
        reason_detail: str,
        ev_pct: float | None = None,
    ) -> None:
        log_blocked_prop_decision(
            self.db,
            self.model_version_id,
            game_id=game_id,
            matchday_date=matchday_date,
            market=market,
            selection=selection,
            reason_code=reason_code,
            reason_detail=reason_detail,
            ev_pct=ev_pct,
        )

    def _check_props_risk_gate(
        self,
        *,
        is_sgp: bool,
        game_id: str,
        matchday_date: str,
        selection: str,
        ev_pct: float | None = None,
        allow_player_props: bool | None = None,
        allow_parlays: bool | None = None,
    ) -> tuple[bool, str]:
        return check_props_risk_gate(
            self.db,
            self.risk,
            self._config_load_error,
            self.model_version_id,
            is_sgp=is_sgp,
            game_id=game_id,
            matchday_date=matchday_date,
            selection=selection,
            ev_pct=ev_pct,
            allow_player_props=allow_player_props,
            allow_parlays=allow_parlays,
        )

    def _props_exposure_allows(self, stake_pen: float, bankroll_pen: float) -> bool:
        return props_exposure_allows(self.db, self.risk, stake_pen, bankroll_pen)

    def _props_may_record(
        self,
        game_id: str,
        matchday_date: str,
        player_key: str,
        category: str,
        selection: str,
        stake_pen: float,
        bankroll_pen: float,
        *,
        is_sgp: bool | None = None,
        allow_player_props: bool | None = None,
        allow_parlays: bool | None = None,
        ev_pct: float | None = None,
    ) -> bool:
        return props_may_record(
            self.db,
            self.risk,
            self._config_load_error,
            self.model_version_id,
            game_id,
            matchday_date,
            player_key,
            category,
            selection,
            stake_pen,
            bankroll_pen,
            is_sgp=is_sgp,
            allow_player_props=allow_player_props,
            allow_parlays=allow_parlays,
            ev_pct=ev_pct,
        )

    def _persist_prop_pick(
        self,
        prop_pick: dict[str, Any],
        bankroll_pen: float,
        *,
        allow_player_props: bool | None = None,
    ) -> bool:
        return persist_prop_pick(
            self.db,
            self.risk,
            self._config_load_error,
            self.model_version_id,
            prop_pick,
            bankroll_pen,
            allow_player_props=allow_player_props,
        )

    def _persist_sgp_pick(
        self,
        sgp_cand: dict[str, Any],
        bankroll_pen: float,
        *,
        allow_player_props: bool | None = None,
        allow_parlays: bool | None = None,
    ) -> bool:
        return persist_sgp_pick(
            self.db,
            self.risk,
            self._config_load_error,
            self.model_version_id,
            sgp_cand,
            bankroll_pen,
            allow_player_props=allow_player_props,
            allow_parlays=allow_parlays,
        )

    @staticmethod
    def _compute_ewma_baseline_from_records(
        records: list[tuple[float, float, float, float, float]],
        prior_profile: tuple[float, float, float, float, float, float],
        alpha: float = 0.85,
    ) -> tuple[float, float, float, float, float, float] | None:
        return _compute_ewma(records, prior_profile, alpha=alpha)

    def _resolve_as_of_cutoff(
        self,
        as_of_utc: str | None = None,
        as_of_timestamp: str | None = None,
        caller: str = "props_query",
    ) -> str | None:
        return _resolve_cutoff(self.db, as_of_utc=as_of_utc, as_of_timestamp=as_of_timestamp, caller=caller)

    def get_player_baseline(
        self,
        player_name: str,
        team_abbr: str | None = None,
        lookback_games: int = 15,
        alpha: float = 0.85,
        as_of_utc: str | None = None,
        as_of_timestamp: str | None = None,
    ) -> tuple[float, float, float, float, float, float]:
        return _get_player_baseline(
            self.db,
            self._player_baselines_cache,
            player_name,
            team_abbr=team_abbr,
            lookback_games=lookback_games,
            alpha=alpha,
            as_of_utc=as_of_utc,
            as_of_timestamp=as_of_timestamp,
        )

    def get_team_defensive_multipliers(
        self,
        opponent_team: str | None,
        lookback_window: int = 30,
        as_of_utc: str | None = None,
        as_of_timestamp: str | None = None,
    ) -> dict[str, Any]:
        return _get_team_multipliers(
            self.db,
            self._team_multipliers_cache,
            opponent_team,
            lookback_window=lookback_window,
            as_of_utc=as_of_utc,
            as_of_timestamp=as_of_timestamp,
        )

    def project_player_stats(
        self,
        player_name: str,
        team: str,
        absent_teammates: list[str] | None = None,
        opponent_team: str | None = None,
        expected_game_pace: float | None = None,
        spread_blowout_risk: float | None = None,
        referee_foul_rate: float = 1.0,
        injury_status: str = "ACTIVE",
        foul_trouble_prone: bool = False,
        as_of_utc: str | None = None,
        as_of_timestamp: str | None = None,
    ) -> dict[str, Any]:
        return _project_player_stats(
            self.db,
            self._player_baselines_cache,
            self._team_multipliers_cache,
            self.minutes_engine,
            player_name,
            team,
            absent_teammates=absent_teammates,
            opponent_team=opponent_team,
            expected_game_pace=expected_game_pace,
            spread_blowout_risk=spread_blowout_risk,
            referee_foul_rate=referee_foul_rate,
            injury_status=injury_status,
            foul_trouble_prone=foul_trouble_prone,
            as_of_utc=as_of_utc,
            as_of_timestamp=as_of_timestamp,
        )

    def compute_exceedance_probabilities(
        self,
        prop_category: str,
        line_value: float,
        proj_mean: float,
        proj_std: float,
        dist_type: str = "normal",
    ) -> tuple[float, float, float]:
        return compute_exceedance_probs_math(
            prop_category=prop_category,
            line_value=line_value,
            proj_mean=proj_mean,
            proj_std=proj_std,
            dist_type=dist_type,
        )

    def build_historical_props_calibration_dataset(
        self,
        as_of_utc: str,
        max_oos_boxscore_samples: int = 350,
    ) -> list[dict[str, Any]]:
        return _build_cal_dataset(self, as_of_utc=as_of_utc, max_oos_boxscore_samples=max_oos_boxscore_samples)

    def fit_calibrators(
        self,
        as_of_utc: str,
        calibration_records: list[dict[str, Any]] | None = None,
        global_min_samples: int | None = None,
        category_min_samples: int | None = None,
    ) -> dict[str, Any]:
        return fit_props_calibrators(
            self,
            as_of_utc=as_of_utc,
            calibration_records=calibration_records,
            global_min_samples=global_min_samples,
            category_min_samples=category_min_samples,
        )

    def _select_calibrator_for_category(self, prop_category: str) -> tuple[VennAbersConformalInterval | None, str]:
        cat_key = prop_category.strip().upper()
        cat_cal = self.category_calibrators.get(cat_key)
        if cat_cal is not None and cat_cal.is_fitted:
            return cat_cal, f"venn_abers_category:{cat_key}"
        if self.calibrator.is_fitted:
            return self.calibrator, "venn_abers_global"
        return None, "unfitted_heuristic_fallback"

    def evaluate_prop_opportunity(
        self,
        player_name: str,
        team: str,
        game_id: str,
        matchday_date: str,
        prop_category: str,
        line_value: float,
        over_odds: float,
        under_odds: float,
        absent_teammates: list[str] | None = None,
        bankroll_pen: float = 100.0,
        opponent_team: str | None = None,
        expected_game_pace: float | None = None,
        spread_blowout_risk: float | None = None,
        persist: bool = True,
        line_source: str = "OBSERVED",
        as_of_utc: str | None = None,
        as_of_timestamp: str | None = None,
        allow_player_props: bool | None = None,
    ) -> list[dict[str, Any]]:
        return evaluate_prop_opportunity_impl(
            self,
            player_name=player_name,
            team=team,
            game_id=game_id,
            matchday_date=matchday_date,
            prop_category=prop_category,
            line_value=line_value,
            over_odds=over_odds,
            under_odds=under_odds,
            absent_teammates=absent_teammates,
            bankroll_pen=bankroll_pen,
            opponent_team=opponent_team,
            expected_game_pace=expected_game_pace,
            spread_blowout_risk=spread_blowout_risk,
            persist=persist,
            line_source=line_source,
            as_of_utc=as_of_utc,
            as_of_timestamp=as_of_timestamp,
            allow_player_props=allow_player_props,
        )

    def simulate_multi_leg_sgp_copula(
        self,
        legs: list[dict[str, Any]],
        offered_sgp_odds: float,
        correlation_matrix: np.ndarray | None = None,
        copula_family: str = "student_t",
        df: int = 5,
        bankroll_pen: float = 100.0,
        n_simulations: int = 25000,
        random_seed: int = 42,
        min_hits: int = 10,
        max_relative_error: float = 0.25,
    ) -> dict[str, Any]:
        return self.copula_engine.simulate_multivariate_copula(
            legs=legs,
            offered_sgp_odds=offered_sgp_odds,
            correlation_matrix=correlation_matrix,
            copula_family=copula_family,
            df=df,
            bankroll_pen=bankroll_pen,
            n_simulations=n_simulations,
            random_seed=random_seed,
            min_hits=min_hits,
            max_relative_error=max_relative_error,
        )

    def simulate_same_game_parlay_copula(
        self,
        game_id: str,
        matchday_date: str,
        game_selection_label: str,
        game_model_prob: float,
        player_name: str,
        team: str,
        prop_category: str,
        prop_selection: str,
        prop_line: float,
        prop_model_prob: float,
        offered_sgp_odds: float,
        correlation_rho: float = 0.28,
        bankroll_pen: float = 100.0,
        n_simulations: int = 10000,
        random_seed: int = 42,
        pure_alpha: bool = False,
        min_hits: int = 10,
        max_relative_error: float = 0.25,
    ) -> dict[str, Any]:
        return simulate_same_game_parlay_copula_impl(
            self,
            game_id=game_id,
            matchday_date=matchday_date,
            game_selection_label=game_selection_label,
            game_model_prob=game_model_prob,
            player_name=player_name,
            team=team,
            prop_category=prop_category,
            prop_selection=prop_selection,
            prop_line=prop_line,
            prop_model_prob=prop_model_prob,
            offered_sgp_odds=offered_sgp_odds,
            correlation_rho=correlation_rho,
            bankroll_pen=bankroll_pen,
            n_simulations=n_simulations,
            random_seed=random_seed,
            pure_alpha=pure_alpha,
            min_hits=min_hits,
            max_relative_error=max_relative_error,
        )

    def scan_retabet_sgp_slate(
        self,
        slate_games: list[dict[str, Any]],
        props_list: list[dict[str, Any]],
        bankroll_pen: float = 100.0,
        min_ev_pct: float = 3.0,
        persist: bool = False,
        allow_player_props: bool | None = None,
        allow_parlays: bool | None = None,
    ) -> list[dict[str, Any]]:
        return scan_retabet_sgp_slate_impl(
            self,
            slate_games=slate_games,
            props_list=props_list,
            bankroll_pen=bankroll_pen,
            min_ev_pct=min_ev_pct,
            persist=persist,
            allow_player_props=allow_player_props,
            allow_parlays=allow_parlays,
        )

    def generate_high_probability_parlays(
        self,
        slate_games: list[dict[str, Any]],
        props_list: list[dict[str, Any]],
        bankroll_pen: float = 100.0,
        min_leg_prob: float = 0.75,
    ) -> list[dict[str, Any]]:
        return generate_high_probability_parlays_impl(
            self,
            slate_games=slate_games,
            props_list=props_list,
            bankroll_pen=bankroll_pen,
            min_leg_prob=min_leg_prob,
        )

    def generate_slate_prop_opportunities(
        self,
        slate_games: list[dict[str, Any]] | None = None,
        bankroll_pen: float = 100.0,
        min_ev_pct: float = 3.0,
        injuries_by_team: dict[str, list[str]] | None = None,
        output_file: Path | str | None = None,
        allow_parlays: bool | None = None,
        allow_player_props: bool | None = None,
    ) -> list[dict[str, Any]]:
        """End-to-End Prop & SGP Slate Generator gated strictly by `allow_player_props_betting` / `allow_parlays`."""
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        eff_allow_parlays = (
            bool(self.risk.allow_parlays)
            if allow_parlays is None and self.risk is not None
            else bool(allow_parlays) if allow_parlays is not None else False
        )

        if slate_games is None and self.db is not None:
            slate_games = self.db.fetch_all(
                """
                SELECT * FROM games
                WHERE status = 'SCHEDULED'
                  AND game_start_time > ?
                  AND game_id NOT LIKE 'SYN%'
                ORDER BY game_start_time ASC
                LIMIT 15
                """,
                (now_iso,),
            )
        slate_games = slate_games or []
        valid_slate_games = [
            g for g in slate_games
            if g.get("status", "SCHEDULED") == "SCHEDULED" and (not g.get("game_start_time") or str(g.get("game_start_time")) > now_iso)
        ]

        if self.db is not None and valid_slate_games:
            slate_cutoff = min(
                (str(g["game_start_time"]) for g in valid_slate_games if g.get("game_start_time")),
                default=now_iso,
            )
            self.fit_calibrators(as_of_utc=slate_cutoff)

        team_injuries: dict[str, list[str]] = injuries_by_team or {}
        if not team_injuries and self.db is not None:
            try:
                inj_rows = self.db.fetch_all("SELECT team, player_name FROM player_injuries WHERE status IN ('OUT', 'DOUBTFUL')")
                for r in inj_rows:
                    t = r.get("team")
                    p = r.get("player_name")
                    if t and p:
                        team_injuries.setdefault(t, []).append(p)
            except Exception as exc:
                logger.debug(f"Failed to load injuries from DB: {exc}")

        qualified_props: list[dict[str, Any]] = []
        active_rosters: dict[str, list[str]] = {}
        if self.db is not None:
            try:
                from src.ingestion.roster_manager import get_all_rosters
                active_rosters = get_all_rosters(self.db)
            except Exception as exc:
                logger.warning(f"Handled exception loading active rosters: {exc}")

        fallback_rosters = get_fallback_rosters()

        for game in valid_slate_games:
            gid = game.get("game_id", f"G_SLATE_{uuid.uuid4().hex[:6]}")
            mdate = game.get("matchday_date", today_str)
            home_t = game.get("home_team")
            away_t = game.get("away_team")
            spread_val = float(game.get("expected_margin") or 0.0)
            pace_val = float(game.get("stats", {}).get("expected_pace") or 99.5) if isinstance(game.get("stats"), dict) else 99.5

            observed_props_index: dict[tuple[str, str], list[tuple[float, float, float]]] = {}
            if self.db and gid:
                g_start_str = str(game.get("game_start_time") or "").strip()
                if g_start_str:
                    raw_prop_rows = self.db.fetch_all(
                        """
                        SELECT provider, line_value, decimal_odds, counterpart_decimal_odds, selection
                        FROM v_observed_odds_snapshots
                        WHERE game_id = ?
                          AND market = 'player_prop'
                          AND COALESCE(is_closing_line, 0) = 0
                          AND datetime(captured_at) < datetime(?)
                        ORDER BY captured_at DESC
                        """,
                        (gid, g_start_str),
                    )
                else:
                    raw_prop_rows = self.db.fetch_all(
                        """
                        SELECT provider, line_value, decimal_odds, counterpart_decimal_odds, selection
                        FROM v_observed_odds_snapshots
                        WHERE game_id = ?
                          AND market = 'player_prop'
                          AND COALESCE(is_closing_line, 0) = 0
                        ORDER BY captured_at DESC
                        """,
                        (gid,),
                    )
                for oq in raw_prop_rows:
                    parsed_prov = _parse_observed_prop_provider(str(oq.get("provider") or ""))
                    if not parsed_prov:
                        continue
                    oq_player, oq_cat = parsed_prov
                    p_key = _normalize_player_match_key(oq_player)
                    if not p_key:
                        continue
                    lv = round(float(oq.get("line_value") or 0.0), 2)
                    dec_odds = float(oq.get("decimal_odds") or 0.0)
                    counter_odds = float(oq.get("counterpart_decimal_odds") or 0.0)
                    sel_side = str(oq.get("selection") or "OVER").strip().upper()
                    oo, uo = (counter_odds, dec_odds) if sel_side == "UNDER" else (dec_odds, counter_odds)
                    if lv > 0.0 and oo > 1.0 and uo > 1.0:
                        bucket = observed_props_index.setdefault((p_key, oq_cat), [])
                        quote_tuple = (lv, oo, uo)
                        if quote_tuple not in bucket:
                            bucket.append(quote_tuple)

            if not observed_props_index:
                continue

            as_of_game_str = str(game.get("game_start_time") or now_iso)
            for _is_home, team_code, opp_code in [(True, home_t, away_t), (False, away_t, home_t)]:
                if not team_code:
                    continue
                team_players = list(active_rosters.get(team_code) or [])
                if not team_players and self.db:
                    try:
                        db_p = self.db.fetch_all(
                            """
                            SELECT MAX(player_name) AS player_name
                            FROM player_boxscores
                            WHERE team = ?
                              AND game_id NOT LIKE 'SYN%'
                              AND datetime(game_start_time) < datetime(?)
                              AND minutes >= 10.0
                            GROUP BY player_key
                            ORDER BY MAX(game_start_time) DESC, COUNT(*) DESC
                            LIMIT 12
                            """,
                            (team_code, as_of_game_str),
                        )
                        if db_p:
                            team_players = [r["player_name"] for r in db_p]
                    except Exception:
                        pass
                if not team_players:
                    team_players = list(fallback_rosters.get(team_code, []))
                absent_list = team_injuries.get(team_code, [])

                for p_raw in team_players:
                    prof = self.get_player_baseline(p_raw, team_code, as_of_utc=as_of_game_str)
                    if not prof or p_raw in absent_list:
                        continue
                    target_p_key = _normalize_player_match_key(p_raw)
                    if not target_p_key:
                        continue

                    categories_to_eval = ["PTS", "PRA"]
                    if prof[4] >= 0.18 or ((target_p_key, "AST") in observed_props_index and prof[0] >= 12.0):
                        categories_to_eval.append("AST")
                    if prof[3] >= 0.25 or ((target_p_key, "REB") in observed_props_index and prof[0] >= 12.0):
                        categories_to_eval.append("REB")
                    if prof[5] >= 0.08 or (
                        (target_p_key, "3PM") in observed_props_index and (prof[0] * prof[5]) >= 0.30
                    ):
                        categories_to_eval.append("3PM")

                    matched_cats = [cat for cat in categories_to_eval if (target_p_key, cat) in observed_props_index]
                    if not matched_cats:
                        continue

                    proj = self.project_player_stats(
                        player_name=p_raw,
                        team=team_code,
                        absent_teammates=absent_list,
                        opponent_team=opp_code,
                        expected_game_pace=pace_val,
                        spread_blowout_risk=spread_val,
                        as_of_utc=as_of_game_str,
                    )

                    for cat in matched_cats:
                        if not proj["projections"].get(cat):
                            continue
                        for lv, oo, uo in observed_props_index.get((target_p_key, cat), []):
                            picks = self.evaluate_prop_opportunity(
                                player_name=p_raw,
                                team=team_code,
                                game_id=gid or "NBA_GAME",
                                matchday_date=mdate,
                                prop_category=cat,
                                line_value=lv,
                                over_odds=oo,
                                under_odds=uo,
                                absent_teammates=absent_list,
                                bankroll_pen=bankroll_pen,
                                opponent_team=opp_code,
                                expected_game_pace=pace_val,
                                spread_blowout_risk=spread_val,
                                persist=False,
                                line_source="OBSERVED",
                                as_of_utc=as_of_game_str,
                            )
                            for pk in picks:
                                if pk["ev_pct"] >= min_ev_pct and pk["ev_lower_bound_pct"] >= -10.0:
                                    qualified_props.append(pk)

        qualified_props.sort(key=lambda x: (x.get("ev_lower_bound_pct", 0.0), x.get("ev_pct", 0.0)), reverse=True)
        top_individual_props = qualified_props[:15]

        top_sgp_candidates: list[dict[str, Any]] = []
        high_prob_parlays: list[dict[str, Any]] = []
        if eff_allow_parlays:
            sgp_candidates = self.scan_retabet_sgp_slate(
                slate_games=valid_slate_games,
                props_list=top_individual_props,
                bankroll_pen=bankroll_pen,
                min_ev_pct=min_ev_pct,
                persist=False,
            )
            sgp_candidates.sort(key=lambda x: x.get("ev_pct", 0.0), reverse=True)
            top_sgp_candidates = sgp_candidates[:8]
            high_prob_parlays = self.generate_high_probability_parlays(
                slate_games=valid_slate_games,
                props_list=top_individual_props,
                bankroll_pen=bankroll_pen,
            )

        if self.db is not None:
            for sgp in top_sgp_candidates[:1]:
                self._persist_sgp_pick(
                    sgp,
                    bankroll_pen,
                    allow_player_props=allow_player_props,
                    allow_parlays=allow_parlays,
                )
            for pk in top_individual_props:
                self._persist_prop_pick(pk, bankroll_pen, allow_player_props=allow_player_props)
            for sgp in top_sgp_candidates[1:]:
                self._persist_sgp_pick(
                    sgp,
                    bankroll_pen,
                    allow_player_props=allow_player_props,
                    allow_parlays=allow_parlays,
                )

        consolidated = high_prob_parlays + top_sgp_candidates + top_individual_props

        if output_file is not None:
            out_file = Path(output_file)
            try:
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(json.dumps(consolidated, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                logger.debug(f"Failed to write props output file: {exc}")

        return consolidated

    def evaluate_historical_oos_calibration(
        self,
        *,
        min_date: str = "2026-01-01T00:00:00Z",
        min_minutes: float = 12.0,
        max_samples: int = 2000,
        benchmarks: tuple[tuple[str, float, str], ...] = (
            ("PTS", 15.5, "pts"),
            ("PTS", 20.5, "pts"),
            ("REB", 5.5, "reb"),
            ("AST", 4.5, "ast"),
            ("3PM", 0.5, "threed"),
            ("3PM", 1.5, "threed"),
            ("PRA", 24.5, "pts+reb+ast"),
        ),
    ) -> dict[str, Any]:
        """Evaluates strictly pre-tipoff OOS calibration and Brier Skill Score against `player_boxscores`."""
        if self.db is None:
            return {"eligible_samples": 0, "evaluated_samples": 0, "benchmarks": {}}

        rows = self.db.fetch_all(
            """
            SELECT pb.game_id, pb.player_name, pb.player_key, pb.team, pb.game_start_time,
                   pb.minutes, pb.pts, pb.reb, pb.ast, pb.threed,
                   g.home_team, g.away_team
            FROM player_boxscores pb
            JOIN games g ON g.game_id = pb.game_id
            WHERE pb.game_start_time >= ?
              AND pb.minutes >= ?
              AND g.status = 'FINAL'
              AND g.game_id NOT LIKE 'SYN%'
            ORDER BY pb.game_start_time ASC, pb.player_key ASC
            """,
            (min_date, float(min_minutes)),
        )
        if not rows:
            return {"eligible_samples": 0, "evaluated_samples": 0, "benchmarks": {}}

        step = max(1, len(rows) // max(1, int(max_samples)))
        sample = rows[::step][:max_samples]
        series: dict[str, list[tuple[float, int, float, float]]] = {
            f"{cat}>{line:.1f}": [] for cat, line, _ in benchmarks
        }

        for r in sample:
            opp_team = r["away_team"] if r["team"] == r["home_team"] else r["home_team"]
            proj = self.project_player_stats(
                player_name=r["player_name"],
                team=r["team"],
                opponent_team=opp_team,
                as_of_utc=r["game_start_time"],
            )
            stat_vals = {
                "pts": float(r["pts"]),
                "reb": float(r["reb"]),
                "ast": float(r["ast"]),
                "threed": float(r["threed"]),
                "pts+reb+ast": float(r["pts"] + r["reb"] + r["ast"]),
            }
            for cat, line, expr in benchmarks:
                c = proj["projections"].get(cat)
                if not c or expr not in stat_vals:
                    continue
                p_over, _p_under, _p_push = self.compute_exceedance_probabilities(
                    prop_category=cat,
                    line_value=line,
                    proj_mean=float(c["mean"]),
                    proj_std=float(c["std"]),
                    dist_type=c["dist"],
                )
                act = stat_vals[expr]
                series[f"{cat}>{line:.1f}"].append((p_over, 1 if act > line else 0, float(c["mean"]), act))

        metrics: dict[str, dict[str, Any]] = {}
        for label, items in series.items():
            if not items:
                continue
            p_arr = np.clip(np.asarray([x[0] for x in items], dtype=float), 1e-4, 1.0 - 1e-4)
            y_arr = np.asarray([x[1] for x in items], dtype=float)
            mu_arr = np.asarray([x[2] for x in items], dtype=float)
            act_arr = np.asarray([x[3] for x in items], dtype=float)
            base_rate = float(np.mean(y_arr))
            base_p = float(np.clip(base_rate, 1e-4, 1.0 - 1e-4))
            brier = float(np.mean((p_arr - y_arr) ** 2))
            brier_base = float(np.mean((base_p - y_arr) ** 2))
            ll = float(-np.mean(y_arr * np.log(p_arr) + (1.0 - y_arr) * np.log(1.0 - p_arr)))
            ll_base = float(-np.mean(y_arr * np.log(base_p) + (1.0 - y_arr) * np.log(1.0 - base_p)))
            bss = ((1.0 - brier / brier_base) * 100.0) if brier_base > 0.0 else 0.0
            metrics[label] = {
                "n": len(items),
                "base_over_rate": round(base_rate, 4),
                "mean_pred_prob": round(float(np.mean(p_arr)), 4),
                "mae": round(float(np.mean(np.abs(mu_arr - act_arr))), 3),
                "brier": round(brier, 4),
                "brier_baseline": round(brier_base, 4),
                "brier_skill_score_pct": round(bss, 2),
                "log_loss": round(ll, 4),
                "log_loss_baseline": round(ll_base, 4),
            }

        return {
            "min_date": min_date,
            "eligible_samples": len(rows),
            "evaluated_samples": len(sample),
            "benchmarks": metrics,
        }
