"""
Statistical baseline, matchup Defense-vs-Position (DvP), pace, and usage
redistribution helpers for experimental Player Props projections.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

import numpy as np

from src.ingestion.normalizer import normalize_player_match_key
from src.prediction.props_constants import (
    PLAYER_PROP_BASELINES,
    PROP_DISPERSION_MULTIPLIERS,
    TEAM_DEFENSIVE_MULTIPLIERS,
)
from src.validation.validator import TemporalLeakageError, parse_iso_utc

logger = logging.getLogger(__name__)


def compute_ewma_baseline_from_records(
    records: list[tuple[float, float, float, float, float]],
    prior_profile: tuple[float, float, float, float, float, float],
    alpha: float = 0.85,
) -> tuple[float, float, float, float, float, float] | None:
    """Computes EWMA (minutes, usg, pts/min, reb/min, ast/min, 3pm/min) from newest-first logs."""
    valid = [r for r in records if r[0] >= 8.0]
    if len(valid) < 3:
        return None
    _p_min, prior_usg, prior_ppm, _p_rpm, _p_apm, _p_tpm = prior_profile
    weights = [alpha ** i for i in range(len(valid))]
    w_sum = sum(weights)
    dyn_min = sum(w * r[0] for w, r in zip(weights, valid, strict=False)) / w_sum
    dyn_ppm = sum(w * (r[1] / max(1.0, r[0])) for w, r in zip(weights, valid, strict=False)) / w_sum
    dyn_rpm = sum(w * (r[2] / max(1.0, r[0])) for w, r in zip(weights, valid, strict=False)) / w_sum
    dyn_apm = sum(w * (r[3] / max(1.0, r[0])) for w, r in zip(weights, valid, strict=False)) / w_sum
    dyn_tpm = sum(w * (r[4] / max(1.0, r[0])) for w, r in zip(weights, valid, strict=False)) / w_sum

    scoring_ratio = dyn_ppm / max(0.20, prior_ppm)
    dyn_usg = float(np.clip(prior_usg * (0.50 + 0.50 * scoring_ratio), 12.0, 40.0))
    return (
        round(float(dyn_min), 1),
        round(float(dyn_usg), 1),
        round(float(dyn_ppm), 3),
        round(float(dyn_rpm), 3),
        round(float(dyn_apm), 3),
        round(float(dyn_tpm), 3),
    )


def resolve_as_of_cutoff(
    db: Any,
    as_of_utc: str | None = None,
    as_of_timestamp: str | None = None,
    caller: str = "props_query",
) -> str | None:
    """Validates strict historical cutoff timestamps whenever DB queries run."""
    cutoff = as_of_utc or as_of_timestamp
    if db is not None and not cutoff:
        raise TemporalLeakageError(
            f"{caller} requires explicit `as_of_timestamp` / `as_of_utc` when querying historical DB records."
        )
    if cutoff:
        parse_iso_utc(cutoff)
    return cutoff


def get_player_baseline(
    db: Any,
    cache: dict[tuple[str, str], tuple[float, float, float, float, float, float]],
    player_name: str,
    team_abbr: str | None = None,
    lookback_games: int = 15,
    alpha: float = 0.85,
    as_of_utc: str | None = None,
    as_of_timestamp: str | None = None,
) -> tuple[float, float, float, float, float, float]:
    """Dynamically computes rolling baseline stats strictly < `as_of_utc`."""
    _unused_team = team_abbr
    effective_cutoff = resolve_as_of_cutoff(
        db,
        as_of_utc=as_of_utc,
        as_of_timestamp=as_of_timestamp,
        caller="get_player_baseline",
    )
    norm_name = player_name.strip()
    cache_key = (norm_name, str(effective_cutoff or ""))
    if cache_key in cache:
        return cache[cache_key]

    p_key = normalize_player_match_key(norm_name)
    prior = PLAYER_PROP_BASELINES.get(norm_name)
    if prior is None and p_key:
        for b_name, b_prof in PLAYER_PROP_BASELINES.items():
            if normalize_player_match_key(b_name) == p_key:
                prior = b_prof
                break

    prior_profile = prior if prior is not None else (26.0, 17.5, 0.45, 0.16, 0.09, 0.04)

    if db is not None and p_key and effective_cutoff is not None:
        try:
            records: list[tuple[float, float, float, float, float]] = []
            try:
                pb_rows = db.fetch_all(
                    """
                    SELECT pb.minutes, pb.pts, pb.reb, pb.ast, pb.threed
                    FROM player_boxscores pb
                    JOIN games m ON pb.game_id = m.game_id
                    WHERE pb.player_key = ?
                      AND pb.game_id NOT LIKE 'SYN%'
                      AND pb.minutes >= 8.0
                      AND datetime(m.game_start_time) < datetime(?)
                    ORDER BY pb.game_start_time DESC
                    LIMIT ?
                    """,
                    (p_key, effective_cutoff, lookback_games),
                )
                records = [
                    (
                        float(r["minutes"]),
                        float(r["pts"]),
                        float(r["reb"]),
                        float(r["ast"]),
                        float(r["threed"]),
                    )
                    for r in pb_rows
                ]
            except Exception:
                records = []

            if len(records) < 3:
                like_pattern = f"%{norm_name}%"
                gb_rows = db.fetch_all(
                    """
                    SELECT g.players_json
                    FROM game_boxscores g
                    JOIN games m ON g.game_id = m.game_id
                    WHERE g.players_json LIKE ?
                      AND m.game_id NOT LIKE 'SYN%'
                      AND datetime(m.game_start_time) < datetime(?)
                      AND (g.fetched_at IS NULL OR datetime(g.fetched_at) <= datetime(?))
                    ORDER BY m.game_start_time DESC
                    LIMIT ?
                    """,
                    (like_pattern, effective_cutoff, effective_cutoff, lookback_games * 2),
                )
                records = []
                for r in gb_rows:
                    p_data = json.loads(r.get("players_json") or "{}")
                    if not isinstance(p_data, dict):
                        continue
                    matched = False
                    for _team_key, plist in p_data.items():
                        if not isinstance(plist, list):
                            continue
                        for p in plist:
                            p_cand = normalize_player_match_key(str(p.get("name", "")))
                            if p_cand == p_key or (len(p_key) > 5 and (p_key in p_cand or p_cand in p_key)):
                                m_val = float(p.get("min", 0.0))
                                if m_val >= 8.0:
                                    records.append((
                                        m_val,
                                        float(p.get("pts", 0.0)),
                                        float(p.get("reb") or 0.0),
                                        float(p.get("ast") or 0.0),
                                        float(p.get("threed") or 0.0),
                                    ))
                                matched = True
                                break
                        if matched:
                            break
                    if len(records) >= lookback_games:
                        break

            computed = compute_ewma_baseline_from_records(records, prior_profile, alpha=alpha)
            if computed is not None:
                cache[cache_key] = computed
                return computed
        except Exception as exc:
            logger.debug(f"Dynamic baseline query error for {player_name}: {exc}")

    cache[cache_key] = prior_profile
    return prior_profile


def get_team_defensive_multipliers(
    db: Any,
    cache: dict[tuple[str, str], dict[str, Any]],
    opponent_team: str | None,
    lookback_window: int = 30,
    as_of_utc: str | None = None,
    as_of_timestamp: str | None = None,
) -> dict[str, Any]:
    """Computes Defense vs Position (DvP) and Pace multipliers strictly < cutoff."""
    effective_cutoff = resolve_as_of_cutoff(
        db,
        as_of_utc=as_of_utc,
        as_of_timestamp=as_of_timestamp,
        caller="get_team_defensive_multipliers",
    )
    if not opponent_team:
        return {"PTS": 1.00, "REB": 1.00, "AST": 1.00, "3PM": 1.00, "pace": 99.5, "tier": "AVERAGE"}

    opp = opponent_team.strip().upper()
    cache_key = (opp, str(effective_cutoff or ""))
    if cache_key in cache:
        return cache[cache_key]

    fallback = TEAM_DEFENSIVE_MULTIPLIERS.get(
        opp, {"PTS": 1.00, "REB": 1.00, "AST": 1.00, "3PM": 1.00, "pace": 99.5, "tier": "AVERAGE"}
    )

    if db is None or effective_cutoff is None:
        cache[cache_key] = fallback
        return fallback

    try:
        rows = db.fetch_all(
            """
            SELECT home_team, away_team, home_score, away_score, home_pace, away_pace
            FROM games
            WHERE status = 'FINAL' AND home_score IS NOT NULL AND away_score IS NOT NULL
              AND game_id NOT LIKE 'SYN%'
              AND datetime(game_start_time) < datetime(?)
              AND (home_team = ? OR away_team = ?)
            ORDER BY game_start_time DESC
            LIMIT ?
            """,
            (effective_cutoff, opp, opp, lookback_window),
        )
        if len(rows) < 5:
            cache[cache_key] = fallback
            return fallback

        league_row = db.fetch_one(
            """
            SELECT AVG(home_score + away_score) / 2.0 AS avg_pts
            FROM games
            WHERE status = 'FINAL' AND home_score IS NOT NULL AND away_score IS NOT NULL
              AND game_id NOT LIKE 'SYN%'
              AND datetime(game_start_time) < datetime(?)
            """,
            (effective_cutoff,),
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

        b_rows = db.fetch_all(
            """
            SELECT g.team_stats_json
            FROM game_boxscores g
            JOIN games m ON g.game_id = m.game_id
            WHERE m.game_id NOT LIKE 'SYN%'
              AND datetime(m.game_start_time) < datetime(?)
              AND (g.fetched_at IS NULL OR datetime(g.fetched_at) <= datetime(?))
              AND (m.home_team = ? OR m.away_team = ?)
            ORDER BY m.game_start_time DESC
            LIMIT ?
            """,
            (effective_cutoff, effective_cutoff, opp, opp, lookback_window),
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
        cache[cache_key] = result
        return result
    except Exception as exc:
        logger.debug(f"Dynamic team multipliers error for {opp}: {exc}")
        cache[cache_key] = fallback
        return fallback


def project_player_stats(
    db: Any,
    baseline_cache: dict[tuple[str, str], tuple[float, float, float, float, float, float]],
    team_cache: dict[tuple[str, str], dict[str, Any]],
    minutes_engine: Any,
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
    """Computes projected PTS, REB, AST, 3PM, PRA, PR, PA, RA distributions."""
    effective_cutoff = resolve_as_of_cutoff(
        db,
        as_of_utc=as_of_utc,
        as_of_timestamp=as_of_timestamp,
        caller="project_player_stats",
    )
    profile = get_player_baseline(
        db, baseline_cache, player_name, team, as_of_timestamp=effective_cutoff
    )
    base_min, base_usg, pts_pm, reb_pm, ast_pm, th_pm = profile

    absent = absent_teammates or []
    usage_bump_pct = 0.0
    minutes_bump = 0.0

    for abs_p in absent:
        abs_prof = get_player_baseline(
            db, baseline_cache, abs_p, team, as_of_timestamp=effective_cutoff
        )
        if abs_prof:
            abs_usg = abs_prof[1]
            if abs_usg >= 26.0:
                if base_usg >= 22.0:
                    usage_bump_pct += 0.28 * abs_usg
                    minutes_bump += min(3.5, 40.0 - base_min)
                else:
                    usage_bump_pct += 0.12 * abs_usg
                    minutes_bump += min(2.0, 36.0 - base_min)
            else:
                usage_bump_pct += 0.08 * abs_usg
                minutes_bump += min(1.5, 36.0 - base_min)

    opp = opponent_team.upper() if opponent_team else None
    matchup_info = (
        get_team_defensive_multipliers(db, team_cache, opp, as_of_timestamp=effective_cutoff)
        if opp
        else None
    )
    def_tier = str(matchup_info.get("tier", "AVERAGE")) if matchup_info else "NEUTRAL"
    m_pts = float(matchup_info.get("PTS", 1.0)) if matchup_info else 1.0
    m_reb = float(matchup_info.get("REB", 1.0)) if matchup_info else 1.0
    m_ast = float(matchup_info.get("AST", 1.0)) if matchup_info else 1.0
    m_th = float(matchup_info.get("3PM", 1.0)) if matchup_info else 1.0

    pace_val = expected_game_pace
    if pace_val is None and matchup_info:
        pace_val = float(matchup_info.get("pace", 99.5))
    pace_factor = float(np.clip((pace_val or 99.5) / 99.5, 0.92, 1.08))

    blowout_min_discount = 0.0
    if spread_blowout_risk is not None and abs(spread_blowout_risk) > 10.5 and base_min >= 31.0:
        blowout_min_discount = min(2.5, round((abs(spread_blowout_risk) - 10.5) * 0.35, 1))

    effective_minutes = round(max(18.0, base_min + minutes_bump - blowout_min_discount), 1)
    hurdle_minutes = minutes_engine.predict_minutes_quantiles(
        base_minutes=base_min,
        spread=spread_blowout_risk or 0.0,
        is_starter=(base_min >= 28.0),
        injury_status=injury_status,
        referee_foul_rate=referee_foul_rate,
        foul_trouble_prone=foul_trouble_prone,
        expected_pace=pace_val or 99.5,
    )
    usg_factor = 1.0 + (usage_bump_pct / 100.0)

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
