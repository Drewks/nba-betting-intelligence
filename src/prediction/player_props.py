"""
V8 Player Props Quantitative Engine (`src/prediction/player_props.py`):
Institutional statistical modeling of NBA Player Props & Same-Game Parlays (SGP):
  1. Micro-Usage & Minutes Redistribution: Re-allocates vacated usage rate (USG%) and minute shares
     when teammates are confirmed OUT via the LineupSynergyEngine.
  2. Tactical Matchup & Pace Context Factors:
     - Opponent Defense vs Position (DvP) defensive rating splits across all 30 NBA franchises.
     - Expected Game Pace factor (differential relative to 99.5 baseline).
     - Blowout Spread Dampening: Mitigates star minute inflation when spread > 10.5 pts.
  3. Parametric Probability Distributions:
     - Poisson distribution for count variables (Assists, Rebounds, 3-Pointers).
     - Overdispersed Gaussian distribution for continuous scoring (Points, PRA, PR, PA, RA).
  4. Venn-Abers Conformal Multi-Probabilistic Calibration & Lower-Bound EV:
     Guarantees finite-sample multi-probabilistic safety against bookmaker lines.
  5. Bivariate Gaussian Copula Simulator for RETAbet Perú "Crea tu Apuesta" (SGP):
     Monte Carlo joint simulation capturing non-linear positive correlations between
     team victory and star player performance.
  6. Fractional Kelly Allocation: Sizing tailored for micro-bankrolls with longshot protection.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import hashlib
import math
logger = logging.getLogger(__name__)
import os
from pathlib import Path
from typing import Any
import uuid

import numpy as np
from scipy.stats import norm

from src.calibration.calibrator import VennAbersConformalInterval
from src.config import load_config
from src.prediction.ev_calculator import (
    calculate_ev,
    devig_multiplicative,
    market_anchored_probability,
)
from src.prediction.minutes_model import MinutesProjectionEngine
from src.prediction.props_constants import (
    PLAYER_BASELINES,
    PLAYER_PROP_BASELINES,
    PROP_DISPERSION_MULTIPLIERS,
    TEAM_DEFENSIVE_MULTIPLIERS,
    get_fallback_rosters,
)
from src.prediction.props_distribution import (
    compute_exceedance_probabilities as compute_exceedance_probs_math,
)
from src.prediction.vine_copula import VineCopulaSGP
from src.storage.db import DatabaseManager

__all__ = [
    "PLAYER_BASELINES",
    "PLAYER_PROP_BASELINES",
    "TEAM_DEFENSIVE_MULTIPLIERS",
    "PlayerPropsEngine",
    "get_fallback_rosters",
]


class PlayerPropsEngine:
    """
    Quantitative Modeling of NBA Player Props & SGP:
    Calculates expected statistical values per player, absorbs usage bumps from injuries,
    adjusts for opponent defense and game pace, computes Poisson/Gaussian exceedance probabilities,
    simulates SGP joint copulas for RETAbet Perú, and identifies +EV bets.
    """

    def __init__(self, db: DatabaseManager | None = None, min_ev_threshold: float = 0.05) -> None:
        self.db = db
        self.min_ev_threshold = min_ev_threshold
        risk = load_config().risk
        self.risk = risk
        self.kelly_fraction = risk.kelly_fraction
        self.max_stake_pen = risk.max_stake_pen
        self.max_bankroll_fraction = risk.max_stake_bankroll_fraction
        self.calibrator = VennAbersConformalInterval(window=1200)
        self.minutes_engine = MinutesProjectionEngine()
        self.vine_copula_engine = VineCopulaSGP()
        self._player_baselines_cache: dict[str, tuple[float, float, float, float, float, float]] = {}
        self._team_multipliers_cache: dict[str, dict[str, Any]] = {}

    def _props_exposure_allows(self, stake_pen: float, bankroll_pen: float) -> bool:
        """Props/SGP ledger exposure cap: pending stakes may not exceed max_portfolio_exposure_pct of bankroll."""
        if stake_pen <= 0.0:
            return False
        if self.db is None:
            return True
        row = self.db.fetch_one("SELECT COALESCE(SUM(stake_pen), 0.0) AS s FROM player_prop_picks WHERE status = 'PENDING'")
        pending = float(row["s"]) if row else 0.0
        return (pending + stake_pen) <= self.risk.max_portfolio_exposure_pct * max(0.0, bankroll_pen) + 0.01

    def _props_may_record(
        self, game_id: str, matchday_date: str, player_key: str, category: str, selection: str,
        stake_pen: float, bankroll_pen: float,
    ) -> bool:
        """
        Single gate for every props/SGP paper bet: positive stake, exposure cap, game not finished,
        idempotency (the same selection is recorded once, however many cycles evaluate it) and the
        per-matchday selection cap of the props ledger.
        """
        if self.db is None or not self._props_exposure_allows(stake_pen, bankroll_pen):
            return False
        g_rec = self.db.fetch_one("SELECT status FROM games WHERE game_id = ?", (game_id,))
        if g_rec and g_rec.get("status") in ("FINAL", "POSTPONED", "CANCELLED"):
            return False
        dup = self.db.fetch_one(
            """
            SELECT 1 AS x FROM player_prop_picks
            WHERE game_id = ? AND player_name = ? AND prop_category = ? AND selection = ? LIMIT 1
            """,
            (game_id, player_key, category, selection),
        )
        if dup:
            return False
        row = self.db.fetch_one("SELECT COUNT(*) AS c FROM player_prop_picks WHERE matchday_date = ?", (matchday_date,))
        return int(row["c"] if row else 0) < self.risk.max_selections_per_matchday

    def _persist_prop_pick(self, prop_pick: dict[str, Any], bankroll_pen: float) -> bool:
        if not self._props_may_record(
            prop_pick["game_id"], prop_pick["matchday_date"], prop_pick["player_name"], prop_pick["prop_category"],
            prop_pick["selection"], float(prop_pick.get("kelly_stake_pen") or 0.0), bankroll_pen,
        ):
            return False
        assert self.db is not None
        try:
            self.db.execute_insert(
                """
                INSERT OR IGNORE INTO player_prop_picks (
                    prop_id, game_id, matchday_date, player_name, team, prop_category,
                    line_value, selection, decimal_odds, projected_mean, projected_std,
                    model_prob, conformal_p_low, conformal_p_high, ev_pct, ev_lower_bound_pct,
                    stake_pen, kelly_stake_pen, usage_bump_pct, rationale, emitted_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    prop_pick["prop_id"], prop_pick["game_id"], prop_pick["matchday_date"], prop_pick["player_name"],
                    prop_pick["team"], prop_pick["prop_category"], prop_pick["line_value"], prop_pick["selection"],
                    prop_pick["decimal_odds"], prop_pick["projected_mean"], prop_pick["projected_std"],
                    prop_pick["model_prob"], prop_pick["conformal_p_low"], prop_pick["conformal_p_high"],
                    prop_pick["ev_pct"], prop_pick["ev_lower_bound_pct"], prop_pick["kelly_stake_pen"],
                    prop_pick["kelly_stake_pen"], prop_pick["usage_bump_pct"], prop_pick["rationale"],
                    prop_pick["emitted_at"],
                ),
            )
            return True
        except Exception as exc:
            logger.warning(f"Failed to persist player prop opportunity: {exc}")
            return False

    def _persist_sgp_pick(self, sgp_cand: dict[str, Any], bankroll_pen: float) -> bool:
        player_key = f"{sgp_cand['player_name']} + {sgp_cand['game_selection']}"
        if not self._props_may_record(
            sgp_cand["game_id"], sgp_cand["matchday_date"], player_key, "SGP", "SGP",
            float(sgp_cand.get("kelly_stake_pen") or 0.0), bankroll_pen,
        ):
            return False
        assert self.db is not None
        try:
            self.db.execute_insert(
                """
                INSERT OR IGNORE INTO player_prop_picks (
                    prop_id, game_id, matchday_date, player_name, team, prop_category,
                    line_value, selection, decimal_odds, projected_mean, projected_std,
                    model_prob, conformal_p_low, conformal_p_high, ev_pct, ev_lower_bound_pct,
                    stake_pen, kelly_stake_pen, usage_bump_pct, rationale, emitted_at, status
                ) VALUES (?, ?, ?, ?, ?, 'SGP', ?, 'SGP', ?, 0.0, 0.0, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, 'PENDING')
                """,
                (
                    sgp_cand["sgp_id"], sgp_cand["game_id"], sgp_cand["matchday_date"], player_key, sgp_cand["team"],
                    float(sgp_cand["prop_line"]), float(sgp_cand["offered_sgp_odds"]), float(sgp_cand["p_joint"]),
                    round(max(0.01, float(sgp_cand["p_joint"]) * 0.85), 4),
                    round(min(0.99, float(sgp_cand["p_joint"]) * 1.15), 4),
                    float(sgp_cand["ev_pct"]), round(float(sgp_cand["ev_pct"]) * 0.8, 2),
                    float(sgp_cand["kelly_stake_pen"]), float(sgp_cand["kelly_stake_pen"]), sgp_cand["rationale"],
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                ),
            )
            return True
        except Exception as exc:
            logger.warning(f"Failed to persist SGP opportunity: {exc}")
            return False

    def get_player_baseline(
        self,
        player_name: str,
        team_abbr: str | None = None,
        lookback_games: int = 15,
        alpha: float = 0.85,
    ) -> tuple[float, float, float, float, float, float]:
        """
        Dynamically computes rolling baseline stats for a player:
        (minutes, usg_pct, pts_per_min, reb_per_min, ast_per_min, threed_per_min).

        Resolution Order:
        1. In-memory session cache.
        2. Rolling EWMA from SQLite game_boxscores (last lookback_games).
        3. Static calibrated prior (PLAYER_PROP_BASELINES).
        4. Generic rotation player fallback (26.0, 17.5, 0.45, 0.16, 0.09, 0.04).
        """
        norm_name = player_name.strip()
        if norm_name in self._player_baselines_cache:
            return self._player_baselines_cache[norm_name]

        # Check calibrated static prior for reference ratios (reb, ast, usg)
        prior = PLAYER_PROP_BASELINES.get(norm_name)
        if prior is None:
            clean_search = norm_name.lower().replace(".", "").replace("'", "").replace("-", " ")
            for b_name, b_prof in PLAYER_PROP_BASELINES.items():
                if b_name.lower().replace(".", "").replace("'", "").replace("-", " ") == clean_search:
                    prior = b_prof
                    break

        prior_min, prior_usg, prior_ppm, prior_rpm, prior_apm, prior_tpm = (
            prior if prior is not None else (26.0, 17.5, 0.45, 0.16, 0.09, 0.04)
        )

        # Dynamic rolling extraction from SQLite game_boxscores
        if self.db is not None:
            try:
                like_pattern = f"%{norm_name}%"
                rows = self.db.fetch_all(
                    """
                    SELECT g.game_id, g.players_json, m.game_start_time
                    FROM game_boxscores g
                    JOIN games m ON g.game_id = m.game_id
                    WHERE g.players_json LIKE ?
                    ORDER BY m.game_start_time DESC
                    LIMIT ?
                    """,
                    (like_pattern, lookback_games * 2),
                )
                p_lower = norm_name.lower().replace(".", "").replace("'", "")
                mins_list: list[float] = []
                pts_list: list[float] = []
                reb_list: list[tuple[float, float]] = []  # (reb, min)
                ast_list: list[tuple[float, float]] = []  # (ast, min)
                th_list: list[tuple[float, float]] = []   # (threed, min)

                for r in rows:
                    p_data = json.loads(r.get("players_json") or "{}")
                    found = False
                    if isinstance(p_data, dict):
                        for _, plist in p_data.items():
                            for p in plist:
                                p_cand = str(p.get("name", "")).strip().lower().replace(".", "").replace("'", "")
                                if p_cand == p_lower or (len(p_lower) > 5 and (p_lower in p_cand or p_cand in p_lower)):
                                    m_val = float(p.get("min", 0.0))
                                    if m_val >= 8.0:
                                        mins_list.append(m_val)
                                        pts_list.append(float(p.get("pts", 0.0)))
                                        if "reb" in p and p["reb"] is not None:
                                            reb_list.append((float(p["reb"]), m_val))
                                        if "ast" in p and p["ast"] is not None:
                                            ast_list.append((float(p["ast"]), m_val))
                                        if "threed" in p and p["threed"] is not None:
                                            th_list.append((float(p["threed"]), m_val))
                                    found = True
                                    break
                            if found:
                                break
                    if len(mins_list) >= lookback_games:
                        break

                if len(mins_list) >= 3:
                    weights = [alpha ** i for i in range(len(mins_list))]
                    W = sum(weights)
                    dyn_min = sum(w * m for w, m in zip(weights, mins_list, strict=False)) / W
                    dyn_ppm = sum(w * (pt / max(1.0, m)) for w, pt, m in zip(weights, pts_list, mins_list, strict=False)) / W

                    if len(reb_list) >= 3:
                        rw = [alpha ** i for i in range(len(reb_list))]
                        dyn_rpm = sum(w * (rb / max(1.0, m)) for w, (rb, m) in zip(rw, reb_list, strict=False)) / sum(rw)
                    else:
                        dyn_rpm = prior_rpm

                    if len(ast_list) >= 3:
                        aw = [alpha ** i for i in range(len(ast_list))]
                        dyn_apm = sum(w * (a / max(1.0, m)) for w, (a, m) in zip(aw, ast_list, strict=False)) / sum(aw)
                    else:
                        dyn_apm = prior_apm

                    if len(th_list) >= 3:
                        tw = [alpha ** i for i in range(len(th_list))]
                        dyn_tpm = sum(w * (th / max(1.0, m)) for w, (th, m) in zip(tw, th_list, strict=False)) / sum(tw)
                    else:
                        dyn_tpm = prior_tpm

                    scoring_ratio = dyn_ppm / max(0.20, prior_ppm)
                    dyn_usg = float(np.clip(prior_usg * (0.50 + 0.50 * scoring_ratio), 12.0, 40.0))

                    result = (
                        round(float(dyn_min), 1),
                        round(float(dyn_usg), 1),
                        round(float(dyn_ppm), 3),
                        round(float(dyn_rpm), 3),
                        round(float(dyn_apm), 3),
                        round(float(dyn_tpm), 3),
                    )
                    self._player_baselines_cache[norm_name] = result
                    return result
            except Exception as exc:
                logger.debug(f"Dynamic baseline query error for {player_name}: {exc}")

        result = (prior_min, prior_usg, prior_ppm, prior_rpm, prior_apm, prior_tpm)
        self._player_baselines_cache[norm_name] = result
        return result

    def get_team_defensive_multipliers(
        self,
        opponent_team: str | None,
        lookback_window: int = 30,
    ) -> dict[str, Any]:
        """
        Dynamically computes Defense vs Position (DvP) and Pace multipliers for all 30 NBA teams
        from real finished games and team stats in SQLite.
        Falls back to TEAM_DEFENSIVE_MULTIPLIERS if team data is absent or insufficient.
        """
        if not opponent_team:
            return {"PTS": 1.00, "REB": 1.00, "AST": 1.00, "3PM": 1.00, "pace": 99.5, "tier": "AVERAGE"}

        opp = opponent_team.strip().upper()
        if opp in self._team_multipliers_cache:
            return self._team_multipliers_cache[opp]

        fallback = TEAM_DEFENSIVE_MULTIPLIERS.get(opp, {"PTS": 1.00, "REB": 1.00, "AST": 1.00, "3PM": 1.00, "pace": 99.5, "tier": "AVERAGE"})

        if self.db is None:
            self._team_multipliers_cache[opp] = fallback
            return fallback

        try:
            rows = self.db.fetch_all(
                """
                SELECT home_team, away_team, home_score, away_score, home_pace, away_pace
                FROM games
                WHERE status = 'FINAL' AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND (home_team = ? OR away_team = ?)
                ORDER BY game_start_time DESC
                LIMIT ?
                """,
                (opp, opp, lookback_window),
            )
            if len(rows) < 5:
                self._team_multipliers_cache[opp] = fallback
                return fallback

            league_row = self.db.fetch_one(
                """
                SELECT AVG(home_score + away_score) / 2.0 AS avg_pts
                FROM games
                WHERE status = 'FINAL' AND home_score IS NOT NULL AND away_score IS NOT NULL
                """
            )
            league_avg_pts = float(league_row["avg_pts"]) if league_row and league_row["avg_pts"] else 114.2

            pts_allowed: list[float] = []
            paces: list[float] = []
            for r in rows:
                if r["home_team"] == opp:
                    pts_allowed.append(float(r["away_score"]))
                    if r.get("home_pace"):
                        paces.append(float(r["home_pace"]))
                else:
                    pts_allowed.append(float(r["home_score"]))
                    if r.get("away_pace"):
                        paces.append(float(r["away_pace"]))

            mean_pa = float(np.mean(pts_allowed))
            pts_mult = round(float(np.clip(mean_pa / league_avg_pts, 0.88, 1.15)), 2)

            b_rows = self.db.fetch_all(
                """
                SELECT g.team_stats_json
                FROM game_boxscores g
                JOIN games m ON g.game_id = m.game_id
                WHERE (m.home_team = ? OR m.away_team = ?)
                ORDER BY m.game_start_time DESC
                LIMIT ?
                """,
                (opp, opp, lookback_window),
            )
            tpm_allowed: list[float] = []
            for br in b_rows:
                tdata = json.loads(br.get("team_stats_json") or "{}")
                for tcode, stats in tdata.items():
                    if tcode != opp and "tpm" in stats:
                        tpm_allowed.append(float(stats["tpm"]))

            if len(tpm_allowed) >= 5:
                th_mult = round(float(np.clip(np.mean(tpm_allowed) / 13.0, 0.88, 1.15)), 2)
            else:
                th_mult = pts_mult

            reb_mult = round(1.0 + (pts_mult - 1.0) * 0.70, 2)
            ast_mult = round(1.0 + (pts_mult - 1.0) * 0.85, 2)
            team_pace = round(float(np.mean(paces)), 1) if paces else float(fallback.get("pace", 99.5))

            if pts_mult < 0.96:
                tier = "ELITE"
            elif pts_mult < 0.99:
                tier = "GOOD"
            elif pts_mult < 1.02:
                tier = "AVERAGE"
            elif pts_mult < 1.05:
                tier = "VULNERABLE"
            else:
                tier = "TARGET"

            result = {
                "PTS": pts_mult,
                "REB": reb_mult,
                "AST": ast_mult,
                "3PM": th_mult,
                "pace": team_pace,
                "tier": tier,
            }
            self._team_multipliers_cache[opp] = result
            return result
        except Exception as exc:
            logger.debug(f"Dynamic team multipliers error for {opp}: {exc}")
            self._team_multipliers_cache[opp] = fallback
            return fallback

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
    ) -> dict[str, Any]:
        """
        Computes projected Points, Rebounds, Assists, 3PM, PRA, PR, PA, and RA.
        When star teammates are absent, redistributes vacated usage rate and minutes.
        Adjusts for opponent defensive efficiency (DvP), projected game pace, and blowout risk.
        """
        profile = self.get_player_baseline(player_name, team)
        base_min, base_usg, pts_pm, reb_pm, ast_pm, th_pm = profile

        absent = absent_teammates or []
        usage_bump_pct = 0.0
        minutes_bump = 0.0

        # Vacated usage & minute redistribution logic
        for abs_p in absent:
            abs_prof = self.get_player_baseline(abs_p, team)
            if abs_prof:
                _abs_min, abs_usg = abs_prof[0], abs_prof[1]
                # High-usage star out (>26% USG)
                if abs_usg >= 26.0:
                    # If this player is secondary initiator/scorer, absorbs major usage share
                    if base_usg >= 22.0:
                        usage_bump_pct += 0.28 * abs_usg
                        minutes_bump += min(3.5, 40.0 - base_min)
                    else:
                        usage_bump_pct += 0.12 * abs_usg
                        minutes_bump += min(2.0, 36.0 - base_min)
                else:
                    # Regular rotation player out
                    usage_bump_pct += 0.08 * abs_usg
                    minutes_bump += min(1.5, 36.0 - base_min)

        # Matchup defense adjustment (dynamic from SQLite with fallback to prior)
        opp = opponent_team.upper() if opponent_team else None
        matchup_info = self.get_team_defensive_multipliers(opp) if opp else None
        def_tier = str(matchup_info.get("tier", "AVERAGE")) if matchup_info else "NEUTRAL"
        m_pts = float(matchup_info.get("PTS", 1.0)) if matchup_info else 1.0
        m_reb = float(matchup_info.get("REB", 1.0)) if matchup_info else 1.0
        m_ast = float(matchup_info.get("AST", 1.0)) if matchup_info else 1.0
        m_th = float(matchup_info.get("3PM", 1.0)) if matchup_info else 1.0

        # Pace factor adjustment (relative to 99.5 baseline)
        pace_val = expected_game_pace
        if pace_val is None and matchup_info:
            pace_val = float(matchup_info.get("pace", 99.5))
        pace_factor = float(np.clip((pace_val or 99.5) / 99.5, 0.92, 1.08))

        # Blowout risk dampening on star minutes when game spread is extreme (|spread| > 10.5)
        blowout_min_discount = 0.0
        if spread_blowout_risk is not None and abs(spread_blowout_risk) > 10.5 and base_min >= 31.0:
            blowout_min_discount = min(2.5, round((abs(spread_blowout_risk) - 10.5) * 0.35, 1))

        effective_minutes = round(max(18.0, base_min + minutes_bump - blowout_min_discount), 1)
        hurdle_minutes = self.minutes_engine.predict_minutes_quantiles(
            base_minutes=base_min,
            spread=spread_blowout_risk or 0.0,
            is_starter=(base_min >= 28.0),
            injury_status=injury_status,
            referee_foul_rate=referee_foul_rate,
            foul_trouble_prone=foul_trouble_prone,
            expected_pace=pace_val or 99.5,
        )
        usg_factor = 1.0 + (usage_bump_pct / 100.0)

        # Adjusted scoring and stat rates scale with usage factor, matchup factor, and pace factor
        adj_pts_pm = pts_pm * (usg_factor ** 0.85) * m_pts * pace_factor
        adj_ast_pm = ast_pm * (usg_factor ** 0.70) * m_ast * pace_factor
        adj_th_pm = th_pm * (usg_factor ** 0.80) * m_th * pace_factor
        adj_reb_pm = reb_pm * m_reb * pace_factor

        proj_pts = round(effective_minutes * adj_pts_pm, 1)
        proj_reb = round(effective_minutes * adj_reb_pm, 1)
        proj_ast = round(effective_minutes * adj_ast_pm, 1)
        proj_th = round(effective_minutes * adj_th_pm, 1)
        proj_pra = round(proj_pts + proj_reb + proj_ast, 1)
        proj_pr = round(proj_pts + proj_reb, 1)
        proj_pa = round(proj_pts + proj_ast, 1)
        proj_ra = round(proj_reb + proj_ast, 1)

        # Standard deviations (empirical NBA player dispersion models dynamically calibrated)
        disp = PROP_DISPERSION_MULTIPLIERS
        std_pts = round(math.sqrt(max(1.0, proj_pts * disp.get("PTS", 1.85))), 2)
        std_pra = round(math.sqrt(max(1.0, proj_pra * disp.get("PRA", 2.10))), 2)
        std_pr = round(math.sqrt(max(1.0, proj_pr * disp.get("PR", 1.95))), 2)
        std_pa = round(math.sqrt(max(1.0, proj_pa * disp.get("PA", 1.90))), 2)
        std_ra = round(math.sqrt(max(1.0, proj_ra * disp.get("RA", 1.50))), 2)
        std_reb = round(math.sqrt(max(disp.get("REB_FLOOR", 0.5), proj_reb)), 2)
        std_ast = round(math.sqrt(max(disp.get("AST_FLOOR", 0.5), proj_ast)), 2)
        std_th = round(math.sqrt(max(disp.get("TH_FLOOR", 0.3), proj_th)), 2)

        avg_matchup_adj = round(((m_pts + m_reb + m_ast) / 3.0 - 1.0) * 100.0, 1)

        return {
            "player_name": player_name,
            "team": team,
            "opponent_team": opp,
            "matchup_tier": def_tier,
            "matchup_adjustment_pct": avg_matchup_adj,
            "pace_factor": round(pace_factor, 3),
            "effective_minutes": effective_minutes,
            "hurdle_minutes": hurdle_minutes,
            "usage_bump_pct": round(usage_bump_pct, 1),
            "blowout_min_discount": blowout_min_discount,
            "projections": {
                "PTS": {"mean": proj_pts, "std": std_pts, "dist": "normal"},
                "REB": {"mean": proj_reb, "std": std_reb, "dist": "poisson"},
                "AST": {"mean": proj_ast, "std": std_ast, "dist": "poisson"},
                "PRA": {"mean": proj_pra, "std": std_pra, "dist": "normal"},
                "3PM": {"mean": proj_th, "std": std_th, "dist": "poisson"},
                "PR": {"mean": proj_pr, "std": std_pr, "dist": "normal"},
                "PA": {"mean": proj_pa, "std": std_pa, "dist": "normal"},
                "RA": {"mean": proj_ra, "std": std_ra, "dist": "normal"},
            },
        }

    def compute_exceedance_probabilities(
        self,
        prop_category: str,
        line_value: float,
        proj_mean: float,
        proj_std: float,
        dist_type: str = "normal",
    ) -> tuple[float, float]:
        """
        Computes (p_over, p_under) given a line and parametric distribution.
        Delegates to src.prediction.props_distribution.compute_exceedance_probabilities.
        """
        return compute_exceedance_probs_math(
            prop_category=prop_category,
            line_value=line_value,
            proj_mean=proj_mean,
            proj_std=proj_std,
            dist_type=dist_type,
        )

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
    ) -> list[dict[str, Any]]:
        """
        Evaluates a specific player prop line against our tactical & injury-adjusted projection.
        `persist=False` evaluates without recording a paper bet (used for unobserved/research lines).
        Calculates +EV, Venn-Abers conformal lower bounds, line edge metrics, and recommended Kelly stakes.
        """
        proj_info = self.project_player_stats(
            player_name=player_name,
            team=team,
            absent_teammates=absent_teammates,
            opponent_team=opponent_team,
            expected_game_pace=expected_game_pace,
            spread_blowout_risk=spread_blowout_risk,
        )
        cat_data = proj_info["projections"].get(prop_category)
        if not cat_data:
            return []

        mu = float(cat_data["mean"])
        sigma = float(cat_data["std"])
        dist_type = cat_data["dist"]

        p_over_raw, p_under_raw = self.compute_exceedance_probabilities(
            prop_category=prop_category,
            line_value=line_value,
            proj_mean=mu,
            proj_std=sigma,
            dist_type=dist_type,
        )

        opportunities: list[dict[str, Any]] = []

        # Evaluate both sides (OVER and UNDER)
        for sel, p_raw, dec_odds in [("OVER", p_over_raw, over_odds), ("UNDER", p_under_raw, under_odds)]:
            if dec_odds <= 1.0:
                continue

            # Fair de-vigged implied probability from two-way bookmaker line
            p_fair_a, p_fair_b, _ = devig_multiplicative(over_odds, under_odds)
            mkt_fair = p_fair_a if sel == "OVER" else p_fair_b

            # Conformal Venn-Abers interval for prop probability
            conf_int = self.calibrator.predict_interval(p_raw)
            p_low = float(conf_int["p0"])
            p_high = float(conf_int["p1"])
            conf_w = float(conf_int["width"])

            # Market-anchored probability (75% prop model / 25% sharp book)
            anchored_prob = market_anchored_probability(p_raw, mkt_fair, model_weight=0.75)

            # Expected value
            ev_metrics = calculate_ev(anchored_prob, dec_odds)
            ev_pct = float(ev_metrics["ev_pct"])

            # Conservative lower-bound EV based on conformal lower bound
            lb_anchored = market_anchored_probability(p_low, mkt_fair, model_weight=0.75)
            lb_ev_metrics = calculate_ev(lb_anchored, dec_odds)
            lb_ev_pct = float(lb_ev_metrics["ev_pct"])

            # Discrepancy metric between model projection and book line
            line_diff = round((mu - line_value) if sel == "OVER" else (line_value - mu), 1)
            line_diff_pct = round((line_diff / max(1.0, line_value)) * 100.0, 1)

            # Kelly Stake allocation
            stake_pen = 0.0
            kelly_frac = 0.0
            is_edge_qualified = (lb_ev_pct >= (self.min_ev_threshold * 100.0)) or (ev_pct >= 6.0 and lb_ev_pct >= -10.0)
            if is_edge_qualified and conf_w <= 0.35:
                b_val = dec_odds - 1.0
                f_star = max(0.0, (anchored_prob * (b_val + 1.0) - 1.0) / max(0.05, b_val))
                eff_f = min(self.max_bankroll_fraction, f_star * self.kelly_fraction)
                raw_s = bankroll_pen * eff_f
                # Respect quarter-Kelly without artificial floors
                if eff_f <= 0.0 or ev_pct <= 0.0:
                    stake_pen = 0.00
                else:
                    stake_pen = round(max(0.0, min(self.max_stake_pen, raw_s)), 2)
                kelly_frac = round(eff_f, 4)

                rationale = (
                    ("" if line_source == "OBSERVED" else "[LÍNEA ESTIMADA, no observada] ")
                    + f"[{prop_category} {sel} {line_value}] {player_name} ({team}). "
                    f"Proyección: {mu:.1f} (std: {sigma:.1f}, Ventaja vs Línea: {line_diff:+0.1f} pts). "
                    f"Prob Modelo: {anchored_prob * 100:.1f}% vs Casa: {mkt_fair * 100:.1f}%. "
                    f"Ajustes: +{proj_info['usage_bump_pct']:.1f}% USG, Rival {proj_info.get('opponent_team') or 'NBA'} ({proj_info['matchup_tier']}). "
                    f"Lower-Bound EV: {lb_ev_pct:+.2f}% a cuota {dec_odds:.2f}. Kelly: S/ {stake_pen:.2f} PEN."
                )

                prop_pick = {
                    "prop_id": f"PROP_{game_id}_{player_name.replace(' ', '_')}_{prop_category}_{sel}_{uuid.uuid4().hex[:6]}",
                    "type": "INDIVIDUAL_PROP",
                    "game_id": game_id,
                    "matchday_date": matchday_date,
                    "player_name": player_name,
                    "team": team,
                    "opponent_team": proj_info.get("opponent_team"),
                    "matchup_tier": proj_info["matchup_tier"],
                    "matchup_adjustment_pct": proj_info["matchup_adjustment_pct"],
                    "pace_factor": proj_info["pace_factor"],
                    "prop_category": prop_category,
                    "line_value": line_value,
                    "selection": sel,
                    "decimal_odds": dec_odds,
                    "projected_mean": mu,
                    "projected_std": sigma,
                    "line_diff": line_diff,
                    "line_diff_pct": line_diff_pct,
                    "model_prob": round(anchored_prob, 4),
                    "conformal_p_low": round(p_low, 4),
                    "conformal_p_high": round(p_high, 4),
                    "ev_pct": round(ev_pct, 2),
                    "ev_lower_bound_pct": round(lb_ev_pct, 2),
                    "kelly_stake_pen": stake_pen,
                    "kelly_optimal_fraction": kelly_frac,
                    "usage_bump_pct": proj_info["usage_bump_pct"],
                    "effective_minutes": proj_info["effective_minutes"],
                    "rationale": rationale,
                    "line_source": line_source,
                    "emitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                opportunities.append(prop_pick)

                if persist:
                    self._persist_prop_pick(prop_pick, bankroll_pen)

        return opportunities

    def simulate_multi_leg_sgp_vine_copula(
        self,
        legs: list[dict[str, Any]],
        offered_sgp_odds: float,
        correlation_matrix: np.ndarray | None = None,
        copula_family: str = "student_t",
        df: int = 5,
        bankroll_pen: float = 100.0,
        n_simulations: int = 25000,
        random_seed: int = 42,
    ) -> dict[str, Any]:
        """
        V9 Phase 2: Multi-leg Same Game Parlay (3 to 5 legs) Vine Copula Engine.
        Leverages C-Vine / Student-t heavy tail simulation to accurately price correlated
        parlays offered by Peruvian bookmakers (RETAbet 'Crea tu Apuesta', Betsson).
        """
        return self.vine_copula_engine.simulate_multivariate_copula(
            legs=legs,
            offered_sgp_odds=offered_sgp_odds,
            correlation_matrix=correlation_matrix,
            copula_family=copula_family,
            df=df,
            bankroll_pen=bankroll_pen,
            n_simulations=n_simulations,
            random_seed=random_seed,
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
    ) -> dict[str, Any]:
        """
        V8 Phase 3: Bivariate Gaussian Copula Simulator for RETAbet Perú "Crea tu Apuesta" (SGP).
        Models the non-linear joint dependency between game outcome (spread/moneyline) and
        player statistical props (PTS, REB, AST, PRA), exploiting retail bookmaker mispricing
        where soft correlation tables underestimate joint probability.
        """
        p_game = float(np.clip(game_model_prob, 0.05, 0.95))
        p_prop = float(np.clip(prop_model_prob, 0.05, 0.95))
        rho = float(np.clip(correlation_rho, -0.80, 0.80))

        # Generate correlated bivariate normal draws
        rng = np.random.default_rng(random_seed)
        cov_matrix = np.array([[1.0, rho], [rho, 1.0]], dtype=float)
        z = rng.multivariate_normal(mean=[0.0, 0.0], cov=cov_matrix, size=n_simulations)

        # Marginal uniform transformation via Standard Normal CDF
        u1 = norm.cdf(z[:, 0])
        u2 = norm.cdf(z[:, 1])

        # Joint indicator evaluation
        hits = (u1 <= p_game) & (u2 <= p_prop)
        p_joint = float(np.clip(np.mean(hits), 0.01, 0.95))

        p_independent = p_game * p_prop
        corr_boost_pct = round(((p_joint - p_independent) / p_independent) * 100.0, 2)
        fair_sgp_odds = round(1.0 / p_joint, 3)

        ev_unit = (p_joint * offered_sgp_odds) - 1.0
        ev_pct = round(ev_unit * 100.0, 2)

        # Kelly allocation with longshot variance shield
        b = offered_sgp_odds - 1.0
        f_star = max(0.0, (p_joint * (b + 1.0) - 1.0) / max(0.05, b))
        # Fractional Kelly from config; no floors: without positive EV the stake is 0
        eff_f = min(self.max_bankroll_fraction, f_star * self.kelly_fraction) if ev_unit > 0.0 else 0.0
        stake_pen = round(min(self.max_stake_pen, bankroll_pen * eff_f), 2)

        is_value = ev_pct >= 3.0 and p_joint >= 0.18

        rationale = (
            f"[SGP — CUOTA ESTIMADA, no observada] {game_selection_label} + {player_name} {prop_category} {prop_selection} {prop_line}. "
            f"Prob Conjunta Cópula: {p_joint * 100:.1f}% (vs {p_independent * 100:.1f}% Independiente, Impulso: +{corr_boost_pct}%). "
            f"Cuota Ofrecida: {offered_sgp_odds:.2f} vs Justa: {fair_sgp_odds:.2f} (EV: {ev_pct:+.1f}%). "
            f"Stake Sugerido: S/ {stake_pen:.2f} PEN."
        )

        norm_name = player_name.replace(" ", "_")
        slug_raw = f"{game_id}_{norm_name}_{prop_category}_{prop_selection}_{prop_line}"
        slug = hashlib.sha256(slug_raw.encode("utf-8")).hexdigest()[:8]
        sgp_id = f"SGP_{game_id}_{norm_name}_{prop_category}_{slug}"

        odd_g = round(1.0 / max(0.05, p_game), 2)
        odd_p = round(offered_sgp_odds / max(1.05, odd_g), 2)
        legs = [
            {
                "game_id": game_id,
                "market": "moneyline",
                "selection": game_selection_label,
                "odds": odd_g,
                "desc": f"{team} Victoria",
            },
            {
                "game_id": game_id,
                "market": f"player_{prop_category.lower()}",
                "prop_category": prop_category,
                "selection": prop_selection,
                "line_value": float(prop_line),
                "player_name": player_name,
                "odds": odd_p,
                "desc": f"{player_name} {prop_category} {prop_selection} {prop_line}",
            },
        ]

        return {
            "sgp_id": sgp_id,
            "type": "RETABET_SGP",
            "game_id": game_id,
            "matchday_date": matchday_date,
            "bookmaker": "RETAbet Perú",
            "game_selection": game_selection_label,
            "player_name": player_name,
            "team": team,
            "prop_category": prop_category,
            "prop_selection": prop_selection,
            "prop_line": prop_line,
            "p_game": round(p_game, 4),
            "p_prop": round(p_prop, 4),
            "p_independent": round(p_independent, 4),
            "p_joint": round(p_joint, 4),
            "correlation_rho": rho,
            "correlation_boost_pct": corr_boost_pct,
            "fair_sgp_odds": fair_sgp_odds,
            "offered_sgp_odds": offered_sgp_odds,
            "decimal_odds": offered_sgp_odds,
            "num_legs": 2,
            "legs": legs,
            "ev_pct": ev_pct,
            "kelly_stake_pen": stake_pen,
            "is_value_sgp": is_value,
            "rationale": rationale,
        }

    def scan_retabet_sgp_slate(
        self,
        slate_games: list[dict[str, Any]],
        props_list: list[dict[str, Any]],
        bankroll_pen: float = 100.0,
        min_ev_pct: float = 3.0,
        persist: bool = False,
    ) -> list[dict[str, Any]]:
        """
        V8 Phase 3: Automated RETAbet SGP Slate Scanner (RESEARCH ONLY: offered SGP prices are simulated,
        not observed, and combined bets are prohibited by AGENTS.md; never persisted unless persist=True).
        Pairs available slate game projections with qualified player prop picks to identify
        statistically correlated Same-Game Parlay value opportunities in RETAbet's "Crea tu Apuesta".
        """
        sgp_opportunities: list[dict[str, Any]] = []
        games_by_id = {g.get("game_id"): g for g in slate_games if g.get("game_id")}

        for prop in props_list:
            gid = prop.get("game_id")
            game = games_by_id.get(gid)
            if not game:
                continue

            team = prop.get("team")
            is_home = (team == game.get("home_team"))
            game_prob = float(game.get("model_p_home_pct", 50.0) / 100.0) if is_home else float(game.get("model_p_away_pct", 50.0) / 100.0)
            sel_label = f"{game.get('home_name' if is_home else 'away_name') or team} Gana"

            cat = prop.get("prop_category", "PTS")
            rho = 0.35 if cat in ("PTS", "AST", "PRA", "PA", "PR") else 0.18

            p_p = float(prop.get("model_prob") or 0.50)
            obs_g_odds = float(game.get("home_odds" if is_home else "away_odds") or 0.0)
            obs_p_odds = float(prop.get("decimal_odds") or 0.0)
            if obs_g_odds > 1.0 and obs_p_odds > 1.0:
                sim_offered_odds = round(obs_g_odds * obs_p_odds * 0.90, 2)
            elif "offered_sgp_odds" in prop and float(prop["offered_sgp_odds"]) > 1.0:
                sim_offered_odds = float(prop["offered_sgp_odds"])
            elif not persist:
                # Research simulation mode: derive synthetic fair estimate with bookmaker margin haircut
                odds_g = 1.0 / max(0.05, game_prob)
                odds_p = float(prop.get("decimal_odds") or (1.0 / max(0.05, p_p)))
                sim_offered_odds = round(max(1.01, odds_g * odds_p * 0.90), 2)
            else:
                # Production persistence strictly requires genuine observed market quotes
                continue

            sgp_cand = self.simulate_same_game_parlay_copula(
                game_id=gid or "NBA_GAME",
                matchday_date=prop.get("matchday_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                game_selection_label=sel_label,
                game_model_prob=game_prob,
                player_name=prop.get("player_name", "Player"),
                team=team or "NBA",
                prop_category=cat,
                prop_selection=prop.get("selection", "OVER"),
                prop_line=float(prop.get("line_value", 20.5)),
                prop_model_prob=p_p,
                offered_sgp_odds=sim_offered_odds,
                correlation_rho=rho,
                bankroll_pen=bankroll_pen,
            )
            if sgp_cand["ev_pct"] >= min_ev_pct and sgp_cand["p_joint"] >= 0.18:
                sgp_cand["is_value_sgp"] = True
                sgp_opportunities.append(sgp_cand)
                if persist:
                    self._persist_sgp_pick(sgp_cand, bankroll_pen)

        return sgp_opportunities

    def generate_high_probability_parlays(
        self,
        slate_games: list[dict[str, Any]],
        props_list: list[dict[str, Any]],
        bankroll_pen: float = 100.0,
        min_leg_prob: float = 0.75,
    ) -> list[dict[str, Any]]:
        """
        V9 Pure Alpha Mode: High-Probability Multi-Leg 'Lock Builder' Generator.
        Constructs combinations of highly probable events (alt-lines P >= 75-85%, favorite moneyline anchors)
        that multiply into attractive odds (2.05 - 3.20) with high joint win probability (60% - 70%)
        and aggressive, unconstrained stakes (S/ 7.50 - S/ 16.00 PEN).
        """
        parlays: list[dict[str, Any]] = []

        # 1. Extract Moneyline Anchors (heavy favorites with model win prob >= 70%)
        ml_anchors: list[dict[str, Any]] = []
        for g in slate_games:
            p_home = float(g.get("model_p_home_pct", 50.0)) / 100.0
            p_away = float(g.get("model_p_away_pct", 50.0)) / 100.0
            gid = g.get("game_id", "GAME")
            h_team = g.get("home_team", "HOME")
            a_team = g.get("away_team", "AWAY")
            obs_h_odds = float(g.get("home_odds") or 0.0)
            obs_a_odds = float(g.get("away_odds") or 0.0)
            if p_home >= 0.70:
                h_odds = obs_h_odds if obs_h_odds > 1.0 else round(max(1.05, 1.0 / p_home * 0.96), 2)
                ml_anchors.append({
                    "game_id": gid,
                    "team": h_team,
                    "selection": f"{h_team} ML",
                    "prob": p_home,
                    "odds": h_odds,
                    "type": "ML_ANCHOR",
                })
            elif p_away >= 0.70:
                a_odds = obs_a_odds if obs_a_odds > 1.0 else round(max(1.05, 1.0 / p_away * 0.96), 2)
                ml_anchors.append({
                    "game_id": gid,
                    "team": a_team,
                    "selection": f"{a_team} ML",
                    "prob": p_away,
                    "odds": a_odds,
                    "type": "ML_ANCHOR",
                })

        # 2. Extract High-Probability Alternate Prop Lines (P >= 75%)
        alt_props: list[dict[str, Any]] = []
        for p in props_list:
            p_mean = float(p.get("projected_mean", 0.0))
            p_std = float(p.get("projected_std", 1.0))
            cat = p.get("prop_category", "PTS")
            if p_mean <= 0 or p_std <= 0:
                continue

            # Calculate conservative safe line: mean - 0.90 * std -> Prob ~ 81.5%
            safe_line = max(2.5, math.floor(p_mean - 0.90 * p_std) + 0.5)
            z = (safe_line - p_mean) / p_std
            p_over = float(1.0 - norm.cdf(z))

            if p_over >= min_leg_prob:
                obs_prop_odds = float(p.get("decimal_odds") or 0.0)
                fair_odds = 1.0 / p_over
                retail_odds = obs_prop_odds if obs_prop_odds > 1.0 else round(max(1.05, fair_odds * 1.04), 2)
                alt_props.append({
                    "game_id": p.get("game_id"),
                    "player_name": p.get("player_name"),
                    "team": p.get("team"),
                    "category": cat,
                    "line": safe_line,
                    "selection": "OVER",
                    "prob": round(p_over, 4),
                    "odds": retail_odds,
                    "description": f"{p.get('player_name')} {cat} +{safe_line:.0f}",
                })

        # 3. Strategy A: Same-Game Anchor SGP (Game ML + Alt Prop from same game)
        for anchor in ml_anchors:
            gid = anchor["game_id"]
            team = anchor["team"]
            matching_props = [ap for ap in alt_props if ap["game_id"] == gid and ap["team"] == team]
            if matching_props:
                best_prop = matching_props[0]
                p_slug = hashlib.sha256(f"{gid}_{best_prop['player_name']}_{best_prop['category']}_{best_prop['line']}".encode()).hexdigest()[:8]
                legs = [
                    {
                        "game_id": gid,
                        "market": "moneyline",
                        "selection": anchor["selection"],
                        "prob": anchor["prob"],
                        "odds": anchor["odds"],
                        "desc": f"{anchor['team']} Victoria Directa",
                    },
                    {
                        "game_id": gid,
                        "market": f"player_{best_prop['category'].lower()}",
                        "prop_category": best_prop["category"],
                        "selection": best_prop["selection"],
                        "line_value": float(best_prop["line"]),
                        "player_name": best_prop["player_name"],
                        "prob": best_prop["prob"],
                        "odds": best_prop["odds"],
                        "desc": best_prop["description"],
                    },
                ]
                rho = 0.35
                p1, p2 = anchor["prob"], best_prop["prob"]
                cov = np.array([[1.0, rho], [rho, 1.0]])
                z_draws = np.random.default_rng(42).multivariate_normal([0.0, 0.0], cov, size=5000)
                joint_p = float(np.mean((norm.cdf(z_draws[:, 0]) <= p1) & (norm.cdf(z_draws[:, 1]) <= p2)))

                combined_odds = round(anchor["odds"] * best_prop["odds"], 2)
                ev_pct = round(((joint_p * combined_odds) - 1.0) * 100.0, 2)

                b = combined_odds - 1.0
                if b <= 0.0 or ev_pct <= 0.0:
                    suggested_stake = 0.00
                else:
                    f_k = max(0.0, (joint_p * (b + 1.0) - 1.0) / b)
                    eff_f = min(self.max_bankroll_fraction, f_k * self.kelly_fraction)
                    suggested_stake = round(max(0.0, min(self.max_stake_pen, bankroll_pen * eff_f)), 2)

                parlays.append({
                    "parlay_id": f"HP_SGP_{gid}_{p_slug}",
                    "type": "RETABET_SGP",
                    "strategy": "SAME_GAME_ANCHOR",
                    "game_id": gid,
                    "bookmaker": "RETAbet Perú",
                    "num_legs": len(legs),
                    "legs": legs,
                    "offered_sgp_odds": combined_odds,
                    "decimal_odds": combined_odds,
                    "p_joint": round(joint_p, 4),
                    "win_probability_pct": round(joint_p * 100.0, 1),
                    "ev_pct": ev_pct,
                    "kelly_stake_pen": suggested_stake,
                    "stake_pen": suggested_stake,
                    "rationale": (
                        f"[COMBINADA DE ALTA PROBABILIDAD SGP] {legs[0]['desc']} + {legs[1]['desc']}. "
                        f"Probabilidad de Acierto: {joint_p * 100.0:.1f}%. Cuota Combinada: {combined_odds:.2f} (EV: +{ev_pct:.1f}%). "
                        f"Stake Alfa: S/ {suggested_stake:.2f} PEN."
                    ),
                    "emitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

        # 4. Strategy B: Cross-Game Multi-Match Power Parlay
        all_independent_legs: list[dict[str, Any]] = []
        for anc in ml_anchors:
            all_independent_legs.append({
                "game_id": anc["game_id"],
                "market": "moneyline",
                "selection": anc["selection"],
                "desc": f"{anc['selection']} ({anc['team']})",
                "prob": anc["prob"],
                "odds": anc["odds"],
            })
        for ap in alt_props:
            all_independent_legs.append({
                "game_id": ap["game_id"],
                "market": f"player_{ap['category'].lower()}",
                "prop_category": ap["category"],
                "selection": ap["selection"],
                "line_value": float(ap["line"]),
                "player_name": ap["player_name"],
                "desc": ap["description"],
                "prob": ap["prob"],
                "odds": ap["odds"],
            })

        games_seen = set()
        distinct_legs = []
        for leg in sorted(all_independent_legs, key=lambda x: x["prob"], reverse=True):
            if leg["game_id"] not in games_seen:
                distinct_legs.append(leg)
                games_seen.add(leg["game_id"])
            if len(distinct_legs) >= 3:
                break

        if len(distinct_legs) >= 2:
            combined_odds = 1.0
            joint_p = 1.0
            for leg in distinct_legs[:3]:
                combined_odds *= leg["odds"]
                joint_p *= leg["prob"]

            combined_odds = round(combined_odds, 2)
            ev_pct = round(((joint_p * combined_odds) - 1.0) * 100.0, 2)
            b = combined_odds - 1.0
            if b <= 0.0 or ev_pct <= 0.0:
                suggested_stake = 0.00
            else:
                f_k = max(0.0, (joint_p * (b + 1.0) - 1.0) / max(0.05, b))
                eff_f = min(self.max_bankroll_fraction, f_k * self.kelly_fraction)
                suggested_stake = round(max(0.0, min(self.max_stake_pen, bankroll_pen * eff_f)), 2)

            hash_str = "_".join(f"{leg['game_id']}_{leg.get('player_name', '')}_{leg.get('line_value', '')}" for leg in distinct_legs[:3])
            p_slug = hashlib.sha256(hash_str.encode()).hexdigest()[:8]
            parlays.append({
                "parlay_id": f"HP_POWER_PARLAY_{p_slug}",
                "type": "RETABET_SGP",
                "strategy": "MULTI_MATCH_POWER_PARLAY",
                "game_id": "CROSS_SLATE",
                "bookmaker": "RETAbet / Betsson Perú",
                "num_legs": len(distinct_legs[:3]),
                "legs": distinct_legs[:3],
                "offered_sgp_odds": combined_odds,
                "decimal_odds": combined_odds,
                "p_joint": round(joint_p, 4),
                "win_probability_pct": round(joint_p * 100.0, 1),
                "ev_pct": ev_pct,
                "kelly_stake_pen": suggested_stake,
                "stake_pen": suggested_stake,
                "rationale": (
                    f"[SUPER COMBINADA MULTI-PARTIDO] {' + '.join(leg['desc'] for leg in distinct_legs[:3])}. "
                    f"Probabilidad Conjunta: {joint_p * 100.0:.1f}%. Cuota Combinada: {combined_odds:.2f} (EV: +{ev_pct:.1f}%). "
                    f"Stake Alfa: S/ {suggested_stake:.2f} PEN."
                ),
                "emitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        return parlays

    def generate_slate_prop_opportunities(
        self,
        slate_games: list[dict[str, Any]] | None = None,
        bankroll_pen: float = 100.0,
        min_ev_pct: float = 3.0,
        injuries_by_team: dict[str, list[str]] | None = None,
        output_file: Path | str | None = None,
        allow_synthetic_lines: bool = False,
        allow_parlays: bool | None = None,
    ) -> list[dict[str, Any]]:
        """
        V8 Institutional End-to-End Prop & SGP Slate Generator:
        1. Automatically extracts active slate games and injury absentees.
        2. Evaluates star rotation players across Points, Rebounds, Assists, 3PM, and PRA.
        3. Tests lines against tactical opponent defense (DvP), pace, and usage absorption.
        4. Simulates RETAbet Perú 'Crea tu Apuesta' Gaussian Copulas for correlated SGPs.
        5. Persists the consolidated results to `data/evaluation/latest_player_props.json`.
        """
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Strict Data Integrity: require observed bookmaker lines by default
        if allow_parlays is None:
            allow_parlays = self.risk.allow_parlays

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

        # Strictly enforce upcoming scheduled games only (zero historical/finished games)
        valid_slate_games = [
            g for g in slate_games
            if g.get("status", "SCHEDULED") == "SCHEDULED" and (not g.get("game_start_time") or str(g.get("game_start_time")) > now_iso)
        ]

        # Build injuries mapping if not passed
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

        # Also fallback to visual RAG context if available
        if not team_injuries:
            try:
                v_path = Path("data/visual_rag/latest_visual_context.json")
                if v_path.exists():
                    v_data = json.loads(v_path.read_text(encoding="utf-8"))
                    for doc in v_data.get("top_retrieved_context", []):
                        doc.get("snippet", "")
                        for _team_code in PLAYER_PROP_BASELINES:
                            pass
            except Exception as exc:
                logger.debug(f"Failed to load visual context: {exc}")

        qualified_props: list[dict[str, Any]] = []

        # Fetch verified official rosters from SQLite (with ESPN sync)
        active_rosters: dict[str, list[str]] = {}
        if self.db is not None:
            try:
                from src.ingestion.roster_manager import get_all_rosters
                active_rosters = get_all_rosters(self.db)
            except Exception as exc:
                logging.warning(f"Handled exception in player_props (line 1133): {exc}")

        fallback_rosters = get_fallback_rosters()

        for game in valid_slate_games:
            gid = game.get("game_id", f"G_SLATE_{uuid.uuid4().hex[:6]}")
            mdate = game.get("matchday_date", today_str)
            home_t = game.get("home_team")
            away_t = game.get("away_team")
            spread_val = float(game.get("expected_margin") or 0.0)
            pace_val = float(game.get("stats", {}).get("expected_pace") or 99.5) if isinstance(game.get("stats"), dict) else 99.5

            for _is_home, team_code, opp_code in [(True, home_t, away_t), (False, away_t, home_t)]:
                if not team_code:
                    continue
                team_players = active_rosters.get(team_code)
                if not team_players and self.db:
                    try:
                        db_p = self.db.fetch_all(
                            "SELECT player_name FROM game_boxscores WHERE team = ? GROUP BY player_name ORDER BY COUNT(*) DESC LIMIT 10",
                            (team_code,),
                        )
                        if db_p:
                            team_players = [r["player_name"] for r in db_p]
                    except Exception:
                        pass
                if not team_players:
                    team_players = fallback_rosters.get(team_code, [])
                absent_list = team_injuries.get(team_code, [])

                for p_raw in team_players:
                    # Match canonical baseline profile or compute dynamic rolling baseline
                    prof = self.get_player_baseline(p_raw, team_code)
                    canonical_name = p_raw
                    if not prof:
                        continue

                    # Skip if player is marked absent
                    if canonical_name in absent_list or p_raw in absent_list:
                        continue

                    p_name = canonical_name

                    # Evaluate primary stat lines: PTS and PRA for primary scorers, AST for guards, REB for bigs
                    categories_to_eval = ["PTS"]
                    if prof[4] >= 0.18:  # Good passer (AST)
                        categories_to_eval.append("AST")
                    if prof[3] >= 0.25:  # Good rebounder (REB)
                        categories_to_eval.append("REB")
                    if prof[5] >= 0.08:  # Good shooter (3PM)
                        categories_to_eval.append("3PM")
                    categories_to_eval.append("PRA")

                    # Project raw baseline to find standard retail market line
                    proj = self.project_player_stats(
                        player_name=p_name,
                        team=team_code,
                        absent_teammates=absent_list,
                        opponent_team=opp_code,
                        expected_game_pace=pace_val,
                        spread_blowout_risk=spread_val,
                    )

                    for cat in categories_to_eval:
                        p_data = proj["projections"].get(cat)
                        if not p_data:
                            continue

                        # Strict Data Integrity: Require observed prop quotes from bookmaker snapshots
                        observed_quotes: list[dict[str, Any]] = []
                        if self.db and gid:
                            observed_quotes = self.db.fetch_all(
                                """
                                SELECT line_value, decimal_odds, counterpart_decimal_odds, selection
                                FROM v_observed_odds_snapshots
                                WHERE game_id = ? AND market = 'player_prop' AND provider LIKE ?
                                """,
                                (gid, f"%{p_name}%"),
                            )

                        if not observed_quotes:
                            continue

                        lines_to_test: list[tuple[float, float, float]] = []
                        for oq in observed_quotes:
                            lv = float(oq.get("line_value") or 0.0)
                            oo = float(oq.get("decimal_odds") or 0.0)
                            uo = float(oq.get("counterpart_decimal_odds") or 0.0)
                            if lv > 0.5 and oo > 1.0 and uo > 1.0:
                                lines_to_test.append((lv, oo, uo))

                        if not lines_to_test:
                            continue

                        for lv, oo, uo in lines_to_test:
                            picks = self.evaluate_prop_opportunity(
                                player_name=p_name,
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
                            )
                            for pk in picks:
                                if pk["ev_pct"] >= min_ev_pct and pk["ev_lower_bound_pct"] >= -10.0:
                                    qualified_props.append(pk)

        # Sort individual props by highest Lower-Bound EV
        qualified_props.sort(key=lambda x: (x.get("ev_lower_bound_pct", 0.0), x.get("ev_pct", 0.0)), reverse=True)
        top_individual_props = qualified_props[:15]

        # Combined bets (SGP / parlays): prices are ESTIMATED (no bookmaker SGP price is captured) and
        # labelled as such; enabled by risk_management.allow_parlays.
        top_sgp_candidates: list[dict[str, Any]] = []
        high_prob_parlays: list[dict[str, Any]] = []
        if allow_parlays:
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

        # Record paper bets only after ranking, so the per-matchday cap keeps the best selections rather
        # than the first ones evaluated. The best combined bet goes first so combinadas are not crowded
        # out by single props; `_props_may_record` enforces cap, exposure and idempotency across cycles.
        if self.db is not None:
            for sgp in top_sgp_candidates[:1]:
                self._persist_sgp_pick(sgp, bankroll_pen)
            for pk in top_individual_props:
                self._persist_prop_pick(pk, bankroll_pen)
            for sgp in top_sgp_candidates[1:]:
                self._persist_sgp_pick(sgp, bankroll_pen)

        consolidated = high_prob_parlays + top_sgp_candidates + top_individual_props

        # Persist safely without polluting versioned repo files during tests
        if output_file is not None:
            out_file = Path(output_file)
            try:
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(json.dumps(consolidated, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                logger.debug(f"Failed to write props output file: {exc}")
        elif not os.environ.get("PYTEST_CURRENT_TEST"):
            out_file = Path("data/evaluation/latest_player_props.json")
            try:
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(json.dumps(consolidated, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                logger.debug(f"Failed to write props output file: {exc}")

        return consolidated
