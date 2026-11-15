"""
Experimental Same-Game Parlay (SGP) bivariate copula and multi-leg lock-builder
helpers (`allow_parlays = false` in production config).
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
from typing import Any

import numpy as np
from scipy.stats import norm

from src.prediction.multivariate_copula import wilson_confidence_interval


def simulate_same_game_parlay_copula_impl(
    engine: Any,
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
    """Bivariate Gaussian Copula Simulator for Same-Game Parlays (SGP)."""
    _unused = pure_alpha
    if n_simulations <= 0:
        raise ValueError(f"n_simulations must be positive, received {n_simulations}")

    p_game = float(np.clip(game_model_prob, 1e-6, 1.0 - 1e-6))
    p_prop = float(np.clip(prop_model_prob, 1e-6, 1.0 - 1e-6))
    rho = float(np.clip(correlation_rho, -0.95, 0.95))

    rng = np.random.default_rng(random_seed)
    cov_matrix = np.array([[1.0, rho], [rho, 1.0]], dtype=float)
    z = rng.multivariate_normal(mean=[0.0, 0.0], cov=cov_matrix, size=n_simulations)

    u1 = norm.cdf(z[:, 0])
    u2 = norm.cdf(z[:, 1])

    hits_mask = (u1 <= p_game) & (u2 <= p_prop)
    hits_count = int(np.sum(hits_mask))
    p_joint = float(hits_count) / float(n_simulations)

    ci_95_low, ci_95_high = wilson_confidence_interval(hits_count, n_simulations)
    mc_se = math.sqrt(p_joint * (1.0 - p_joint) / float(n_simulations)) if hits_count > 0 else ci_95_high / 2.0
    rel_error = (mc_se / p_joint) if hits_count > 0 else float("inf")
    sufficient_precision = (hits_count >= min_hits) and (rel_error <= max_relative_error)

    p_independent = p_game * p_prop
    corr_boost_pct = round(((p_joint - p_independent) / max(1e-9, p_independent)) * 100.0, 2)
    fair_sgp_odds: float | None = round(1.0 / p_joint, 3) if p_joint > 0.0 else None

    ev_unit = (p_joint * offered_sgp_odds) - 1.0
    ev_pct = round(ev_unit * 100.0, 2)

    if not sufficient_precision:
        is_value = False
        stake_pen = 0.0
        decision = "NO_BET"
        decision_reason = "INSUFFICIENT_SIMULATION_PRECISION"
    else:
        b = offered_sgp_odds - 1.0
        f_star = max(0.0, (p_joint * (b + 1.0) - 1.0) / max(0.05, b))
        eff_f = min(engine.max_bankroll_fraction, f_star * engine.kelly_fraction) if ev_unit > 0.0 else 0.0
        is_value = ev_pct >= 3.0 and p_joint >= 0.18 and eff_f > 0.0
        stake_pen = round(min(engine.max_stake_pen, bankroll_pen * eff_f), 2) if ev_unit > 0.0 else 0.0
        decision = "BET_VALUE_SGP" if is_value else "NO_BET"
        decision_reason = "POSITIVE_EV_COPULA" if is_value else "BELOW_EV_OR_PROB_THRESHOLD"

    fair_str = f"{fair_sgp_odds:.2f}" if fair_sgp_odds is not None else "N/A (0 hits)"
    rationale = (
        f"[SGP — CUOTA ESTIMADA, no observada] {game_selection_label} + {player_name} {prop_category} {prop_selection} {prop_line}. "
        f"Hits={hits_count}/{n_simulations}, p_joint={p_joint * 100:.2f}% "
        f"(CI95: [{ci_95_low * 100:.2f}%, {ci_95_high * 100:.2f}%], vs {p_independent * 100:.2f}% Indep). "
        f"Cuota Ofrecida: {offered_sgp_odds:.2f} vs Justa: {fair_str} (EV: {ev_pct:+.1f}%). "
        f"Decisión: {decision} ({decision_reason}). Stake Sugerido: S/ {stake_pen:.2f} PEN."
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
        "p_joint": round(p_joint, 6),
        "hits": hits_count,
        "n_simulations": int(n_simulations),
        "ci_95_low": round(ci_95_low, 6),
        "ci_95_high": round(ci_95_high, 6),
        "mc_standard_error": round(mc_se, 6),
        "relative_error": round(rel_error, 6) if math.isfinite(rel_error) else None,
        "sufficient_precision": sufficient_precision,
        "decision": decision,
        "decision_reason": decision_reason,
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


def scan_retabet_sgp_slate_impl(
    engine: Any,
    slate_games: list[dict[str, Any]],
    props_list: list[dict[str, Any]],
    bankroll_pen: float = 100.0,
    min_ev_pct: float = 3.0,
    persist: bool = False,
    allow_player_props: bool | None = None,
    allow_parlays: bool | None = None,
) -> list[dict[str, Any]]:
    """Automated RETAbet SGP Slate Scanner (RESEARCH ONLY unless gates allow)."""
    sgp_opportunities: list[dict[str, Any]] = []
    games_by_id = {g.get("game_id"): g for g in slate_games if g.get("game_id")}

    for prop in props_list:
        gid = prop.get("game_id")
        game = games_by_id.get(gid)
        if not game:
            continue

        team = prop.get("team")
        is_home = team == game.get("home_team")
        game_prob = (
            float(game.get("model_p_home_pct", 50.0) / 100.0)
            if is_home
            else float(game.get("model_p_away_pct", 50.0) / 100.0)
        )
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
            odds_g = 1.0 / max(0.05, game_prob)
            odds_p = float(prop.get("decimal_odds") or (1.0 / max(0.05, p_p)))
            sim_offered_odds = round(max(1.01, odds_g * odds_p * 0.90), 2)
        else:
            continue

        sgp_cand = engine.simulate_same_game_parlay_copula(
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
        if (
            sgp_cand.get("sufficient_precision", False)
            and sgp_cand["ev_pct"] >= min_ev_pct
            and sgp_cand["p_joint"] >= 0.18
        ):
            sgp_cand["is_value_sgp"] = True
            sgp_opportunities.append(sgp_cand)
            if persist:
                engine._persist_sgp_pick(
                    sgp_cand,
                    bankroll_pen,
                    allow_player_props=allow_player_props,
                    allow_parlays=allow_parlays,
                )

    return sgp_opportunities


def generate_high_probability_parlays_impl(
    engine: Any,
    slate_games: list[dict[str, Any]],
    props_list: list[dict[str, Any]],
    bankroll_pen: float = 100.0,
    min_leg_prob: float = 0.75,
) -> list[dict[str, Any]]:
    """High-probability SGP / cross-game lock builder (quarantined research helper)."""
    parlays: list[dict[str, Any]] = []

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

    alt_props: list[dict[str, Any]] = []
    for p in props_list:
        p_mean = float(p.get("projected_mean", 0.0))
        p_std = float(p.get("projected_std", 1.0))
        cat = p.get("prop_category", "PTS")
        if p_mean <= 0 or p_std <= 0:
            continue

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
                eff_f = min(engine.max_bankroll_fraction, f_k * engine.kelly_fraction)
                suggested_stake = round(max(0.0, min(engine.max_stake_pen, bankroll_pen * eff_f)), 2)

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
            eff_f = min(engine.max_bankroll_fraction, f_k * engine.kelly_fraction)
            suggested_stake = round(max(0.0, min(engine.max_stake_pen, bankroll_pen * eff_f)), 2)

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
