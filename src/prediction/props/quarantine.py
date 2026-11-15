"""
Quarantined risk gates, name normalization, provider parsing, and DB persistence
helpers for experimental NBA Player Props & SGP simulation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from src.config import RiskConfig
from src.ingestion.normalizer import normalize_player_match_key

logger = logging.getLogger(__name__)

_PROP_CATEGORY_ALIASES: dict[str, str] = {
    "PTS": "PTS",
    "POINTS": "PTS",
    "POINT": "PTS",
    "REB": "REB",
    "REBOUNDS": "REB",
    "REBOUND": "REB",
    "AST": "AST",
    "ASSISTS": "AST",
    "ASSIST": "AST",
    "3PM": "3PM",
    "3PT": "3PM",
    "THREES": "3PM",
    "PRA": "PRA",
    "PR": "PR",
    "PA": "PA",
    "RA": "RA",
}


def _normalize_player_match_key(name: str) -> str:
    """Normalizes a player name for exact canonical matching across bookmakers and rosters."""
    return normalize_player_match_key(name)


def _parse_observed_prop_provider(provider_str: str) -> tuple[str, str] | None:
    """
    Extracts (player_name, canonical_category) from a bookmaker prop provider string.
    Supports:
      - Structured pipe format: '{book}|{player_name}|{category}' (or '{book}|{player_name}')
      - Underscore format: '{book}_{player_name}_{category}' or '{book}_{player_name}' (defaults strictly to 'PTS')
    Returns None if player_name or category cannot be cleanly parsed.
    """
    raw = str(provider_str or "").strip()
    if not raw:
        return None

    if "|" in raw:
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) < 2 or not parts[1]:
            return None
        player_part = parts[1]
        cat_token = parts[2].upper() if len(parts) >= 3 and parts[2] else "PTS"
        canonical_cat = _PROP_CATEGORY_ALIASES.get(cat_token)
        if not canonical_cat:
            return None
        return player_part, canonical_cat

    if "_" in raw:
        parts = [p.strip() for p in raw.split("_") if p.strip()]
        if len(parts) < 2:
            return None
        last_upper = parts[-1].upper()
        if len(parts) >= 3 and last_upper in _PROP_CATEGORY_ALIASES:
            canonical_cat = _PROP_CATEGORY_ALIASES[last_upper]
            player_part = " ".join(parts[1:-1]).strip()
        else:
            canonical_cat = "PTS"
            player_part = " ".join(parts[1:]).strip()
        if not player_part:
            return None
        return player_part, canonical_cat

    return None


def log_blocked_prop_decision(
    db: Any,
    model_version_id: str,
    *,
    game_id: str,
    matchday_date: str,
    market: str,
    selection: str,
    reason_code: str,
    reason_detail: str,
    ev_pct: float | None = None,
) -> None:
    """Persists NO_BET audit trail into decision_log whenever risk gates block a prop/SGP."""
    if db is None:
        return
    try:
        db.execute_insert(
            """
            INSERT INTO decision_log (
                decision_id, game_id, matchday_date, market, selection,
                decision_type, reason_code, reason_detail, ev_pct, emitted_at, model_version_id
            ) VALUES (?, ?, ?, ?, ?, 'NO_BET', ?, ?, ?, ?, ?)
            """,
            (
                f"DEC_PROP_{uuid.uuid4().hex[:12]}",
                game_id or "UNKNOWN_GAME",
                matchday_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                market,
                selection,
                reason_code,
                reason_detail,
                ev_pct,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                model_version_id,
            ),
        )
    except Exception as exc:
        logger.debug(f"Failed to log blocked prop decision: {exc}")


def check_props_risk_gate(
    db: Any,
    risk: RiskConfig | None,
    config_load_error: str | None,
    model_version_id: str,
    *,
    is_sgp: bool,
    game_id: str,
    matchday_date: str,
    selection: str,
    ev_pct: float | None = None,
    allow_player_props: bool | None = None,
    allow_parlays: bool | None = None,
) -> tuple[bool, str]:
    """Fail-closed centralized risk gate enforced before writing to `player_prop_picks`."""
    if risk is None:
        detail = (
            f"Fail-closed: risk configuration unavailable ({config_load_error or 'missing risk_config'}); "
            "player_prop_picks persistence denied."
        )
        log_blocked_prop_decision(
            db,
            model_version_id,
            game_id=game_id,
            matchday_date=matchday_date,
            market="sgp" if is_sgp else "player_prop",
            selection=selection,
            reason_code="DISABLED_BY_CONFIG",
            reason_detail=detail,
            ev_pct=ev_pct,
        )
        return False, detail

    eff_props = bool(risk.allow_player_props_betting) if allow_player_props is None else bool(allow_player_props)
    if not eff_props:
        detail = "Player props paper betting is disabled (`risk_management.allow_player_props_betting=false`)."
        log_blocked_prop_decision(
            db,
            model_version_id,
            game_id=game_id,
            matchday_date=matchday_date,
            market="sgp" if is_sgp else "player_prop",
            selection=selection,
            reason_code="DISABLED_BY_CONFIG",
            reason_detail=detail,
            ev_pct=ev_pct,
        )
        return False, detail

    if is_sgp:
        eff_parlays = bool(risk.allow_parlays) if allow_parlays is None else bool(allow_parlays)
        if not eff_parlays:
            detail = "SGP/parlay persistence is disabled (`risk_management.allow_parlays=false`)."
            log_blocked_prop_decision(
                db,
                model_version_id,
                game_id=game_id,
                matchday_date=matchday_date,
                market="sgp",
                selection=selection,
                reason_code="DISABLED_BY_CONFIG",
                reason_detail=detail,
                ev_pct=ev_pct,
            )
            return False, detail

    return True, "ALLOWED"


def props_exposure_allows(
    db: Any,
    risk: RiskConfig | None,
    stake_pen: float,
    bankroll_pen: float,
) -> bool:
    """Checks props/SGP ledger pending stake against `max_portfolio_exposure_pct`."""
    if stake_pen <= 0.0 or risk is None:
        return False
    if db is None:
        return True
    row = db.fetch_one("SELECT COALESCE(SUM(stake_pen), 0.0) AS s FROM player_prop_picks WHERE status = 'PENDING'")
    pending = float(row["s"]) if row else 0.0
    return (pending + stake_pen) <= risk.max_portfolio_exposure_pct * max(0.0, bankroll_pen) + 0.01


def props_may_record(
    db: Any,
    risk: RiskConfig | None,
    config_load_error: str | None,
    model_version_id: str,
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
    """Single recording gate for props/SGP paper bets."""
    sgp_flag = (category.upper() == "SGP") if is_sgp is None else bool(is_sgp)
    allowed, _reason = check_props_risk_gate(
        db,
        risk,
        config_load_error,
        model_version_id,
        is_sgp=sgp_flag,
        game_id=game_id,
        matchday_date=matchday_date,
        selection=f"{player_key} {category} {selection}".strip(),
        ev_pct=ev_pct,
        allow_player_props=allow_player_props,
        allow_parlays=allow_parlays,
    )
    if not allowed or db is None or risk is None or not props_exposure_allows(db, risk, stake_pen, bankroll_pen):
        return False
    g_rec = db.fetch_one("SELECT status FROM games WHERE game_id = ?", (game_id,))
    if g_rec and g_rec.get("status") in ("FINAL", "POSTPONED", "CANCELLED"):
        return False
    dup = db.fetch_one(
        """
        SELECT 1 AS x FROM player_prop_picks
        WHERE game_id = ? AND player_name = ? AND prop_category = ? AND selection = ? LIMIT 1
        """,
        (game_id, player_key, category, selection),
    )
    if dup:
        return False
    row = db.fetch_one("SELECT COUNT(*) AS c FROM player_prop_picks WHERE matchday_date = ?", (matchday_date,))
    return int(row["c"] if row else 0) < risk.max_selections_per_matchday


def persist_prop_pick(
    db: Any,
    risk: RiskConfig | None,
    config_load_error: str | None,
    model_version_id: str,
    prop_pick: dict[str, Any],
    bankroll_pen: float,
    *,
    allow_player_props: bool | None = None,
) -> bool:
    """Persists a qualified player prop pick when allowed by quarantined risk gates."""
    ev_raw = prop_pick.get("ev_pct")
    ev_val = float(ev_raw) if ev_raw is not None else None
    if bool(prop_pick.get("lower_bound_ev_blocked")) or float(prop_pick.get("kelly_stake_pen") or 0.0) <= 0.0:
        log_blocked_prop_decision(
            db,
            model_version_id,
            game_id=str(prop_pick.get("game_id") or "UNKNOWN_GAME"),
            matchday_date=str(prop_pick.get("matchday_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            market="player_prop",
            selection=f"{prop_pick.get('player_name', '')} {prop_pick.get('prop_category', '')} {prop_pick.get('selection', '')}".strip(),
            reason_code=str(prop_pick.get("decision_reason") or "UNFITTED_CALIBRATOR_FALLBACK"),
            reason_detail="Prop lower-bound EV staking blocked because calibrator is unfitted or stake is 0.",
            ev_pct=ev_val,
        )
        return False
    if not props_may_record(
        db,
        risk,
        config_load_error,
        model_version_id,
        prop_pick["game_id"],
        prop_pick["matchday_date"],
        prop_pick["player_name"],
        prop_pick["prop_category"],
        prop_pick["selection"],
        float(prop_pick.get("kelly_stake_pen") or 0.0),
        bankroll_pen,
        is_sgp=False,
        allow_player_props=allow_player_props,
        ev_pct=ev_val,
    ):
        return False
    assert db is not None
    try:
        db.execute_insert(
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


def persist_sgp_pick(
    db: Any,
    risk: RiskConfig | None,
    config_load_error: str | None,
    model_version_id: str,
    sgp_cand: dict[str, Any],
    bankroll_pen: float,
    *,
    allow_player_props: bool | None = None,
    allow_parlays: bool | None = None,
) -> bool:
    """Persists a qualified SGP candidate when both props and parlays gates allow."""
    ev_raw = sgp_cand.get("ev_pct")
    ev_val = float(ev_raw) if ev_raw is not None else None
    if sgp_cand.get("decision") == "NO_BET" or float(sgp_cand.get("kelly_stake_pen") or 0.0) <= 0.0:
        log_blocked_prop_decision(
            db,
            model_version_id,
            game_id=str(sgp_cand.get("game_id") or "UNKNOWN_GAME"),
            matchday_date=str(sgp_cand.get("matchday_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            market="sgp",
            selection=f"{sgp_cand.get('player_name', '')} + {sgp_cand.get('game_selection', '')}".strip(),
            reason_code=str(sgp_cand.get("decision_reason") or "NO_VALUE_OR_INSUFFICIENT_PRECISION"),
            reason_detail="SGP blocked from paper ledger due to NO_BET decision or zero Kelly stake.",
            ev_pct=ev_val,
        )
        return False
    player_key = f"{sgp_cand['player_name']} + {sgp_cand['game_selection']}"
    if not props_may_record(
        db,
        risk,
        config_load_error,
        model_version_id,
        sgp_cand["game_id"],
        sgp_cand["matchday_date"],
        player_key,
        "SGP",
        "SGP",
        float(sgp_cand.get("kelly_stake_pen") or 0.0),
        bankroll_pen,
        is_sgp=True,
        allow_player_props=allow_player_props,
        allow_parlays=allow_parlays,
        ev_pct=ev_val,
    ):
        return False
    assert db is not None
    ci_low_raw = sgp_cand.get("ci_95_low")
    ci_high_raw = sgp_cand.get("ci_95_high")
    p_low = float(ci_low_raw) if ci_low_raw is not None else float(sgp_cand["p_joint"])
    p_high = float(ci_high_raw) if ci_high_raw is not None else float(sgp_cand["p_joint"])
    try:
        db.execute_insert(
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
                round(p_low, 4),
                round(p_high, 4),
                float(sgp_cand["ev_pct"]),
                round(((p_low * float(sgp_cand["offered_sgp_odds"])) - 1.0) * 100.0, 2),
                float(sgp_cand["kelly_stake_pen"]), float(sgp_cand["kelly_stake_pen"]), sgp_cand["rationale"],
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
        )
        return True
    except Exception as exc:
        logger.warning(f"Failed to persist SGP opportunity: {exc}")
        return False
