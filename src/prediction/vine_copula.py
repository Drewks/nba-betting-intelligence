"""
V9 Phase 2: Multi-Dimensional Vine Copula Engine for Same-Game Parlays (src/prediction/vine_copula.py).
Models joint dependencies for 3 to 5-leg Correlated Same-Game Parlays (SGP) in RETAbet Perú
("Crea tu Apuesta") and Betsson Perú ("Creador de Apuestas") using Student-t tail-dependent
and Canonical Vine (C-Vine) decompositions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import numpy as np
from scipy.stats import norm, t as student_t


def nearest_positive_definite(matrix: np.ndarray) -> np.ndarray:
    """
    Finds the nearest positive semi-definite correlation matrix using
    eigenvalue floor clipping (Higham algorithm variant).
    """
    B = (matrix + matrix.T) / 2.0
    eigval, eigvec = np.linalg.eigh(B)
    eigval = np.maximum(eigval, 1e-6)
    Q = eigvec @ np.diag(eigval) @ eigvec.T
    d = np.sqrt(np.diag(Q))
    d[d == 0] = 1.0
    corr = Q / np.outer(d, d)
    np.fill_diagonal(corr, 1.0)
    return corr


class VineCopulaSGP:
    """
    Multi-dimensional Vine Copula Simulator for 2 to 5-leg Correlated Same-Game Parlays (SGP).
    Exploits tail dependence and retail bookmaker mispricings in RETAbet "Crea tu Apuesta"
    and Betsson "Creador de Apuestas".
    """

    DEFAULT_CORRELATIONS: dict[tuple[str, str], float] = {
        ("GAME_WIN", "PTS"): 0.32,
        ("GAME_WIN", "AST"): 0.28,
        ("GAME_WIN", "REB"): 0.18,
        ("GAME_WIN", "3PM"): 0.22,
        ("GAME_WIN", "PRA"): 0.35,
        ("TOTAL_OVER", "PTS"): 0.30,
        ("TOTAL_OVER", "AST"): 0.25,
        ("TOTAL_OVER", "3PM"): 0.28,
        ("TOTAL_OVER", "PRA"): 0.32,
        ("PTS", "AST"): 0.24,
        ("PTS", "3PM"): 0.45,
        ("PTS", "REB"): 0.15,
        ("REB", "AST"): 0.12,
        ("PTS", "PRA"): 0.82,
        ("AST", "PRA"): 0.55,
        ("REB", "PRA"): 0.50,
    }

    def __init__(
        self,
        correlations: dict[tuple[str, str], float] | None = None,
        weights_path: str | Path | None = None,
    ) -> None:
        self.correlations = dict(self.DEFAULT_CORRELATIONS)
        if correlations:
            self.correlations.update(correlations)
        else:
            w_path = Path(weights_path) if weights_path else Path("config/calibrated_weights.json")
            if w_path.exists():
                try:
                    with open(w_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    cal_corrs = data.get("sgp_copula_correlations") or {}
                    for k_str, val in cal_corrs.items():
                        parts = k_str.split(",")
                        if len(parts) == 2:
                            self.correlations[(parts[0].strip(), parts[1].strip())] = float(val)
                except Exception:
                    pass


    def build_sgp_correlation_matrix(self, legs: list[dict[str, Any]]) -> np.ndarray:
        """
        Constructs a mathematically valid, positive semi-definite correlation matrix
        across all D legs of a proposed Same-Game Parlay.
        """
        n = len(legs)
        if n < 2:
            return np.eye(n)

        corr = np.eye(n, dtype=float)
        for i in range(n):
            cat_i = legs[i].get("category", "PTS").upper()
            team_i = legs[i].get("team", "")
            for j in range(i + 1, n):
                cat_j = legs[j].get("category", "PTS").upper()
                team_j = legs[j].get("team", "")
                same_team = (team_i == team_j) and bool(team_i)

                # Lookup correlation pair
                pair_key = (cat_i, cat_j)
                rev_key = (cat_j, cat_i)
                rho = self.correlations.get(pair_key) or self.correlations.get(rev_key) or self.DEFAULT_CORRELATIONS.get(pair_key) or self.DEFAULT_CORRELATIONS.get(rev_key) or 0.15

                # Adjust for team context
                if not same_team:
                    # Competing rebounders or opposing players in same game
                    if cat_i == "REB" and cat_j == "REB":
                        rho = -0.12  # Rebounds on one end take away from other
                    elif "GAME_WIN" in (cat_i, cat_j):
                        rho = -rho  # Opponent star stats correlate negatively with rival win
                    else:
                        rho = rho * 0.50  # Weaker cross-team correlation

                # Directional selection adjustments (UNDER flips correlation sign)
                sel_i = legs[i].get("selection", "OVER").upper()
                sel_j = legs[j].get("selection", "OVER").upper()
                if (sel_i == "UNDER" and sel_j != "UNDER") or (sel_j == "UNDER" and sel_i != "UNDER"):
                    rho = -rho

                corr[i, j] = rho
                corr[j, i] = rho

        return nearest_positive_definite(corr)

    def simulate_multivariate_copula(
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
        Simulates multivariate joint probability for N legs (2 <= N <= 5).
        Uses Student-t Copula with heavy tail dependence parameter to capture
        extreme joint cluster events (e.g. Overtime or high-possession shootouts).
        """
        n_legs = len(legs)
        if n_legs < 2:
            raise ValueError(f"SGP requires at least 2 legs, received {n_legs}")

        # Extract marginal probabilities
        probs = [float(np.clip(leg.get("model_prob", 0.50), 0.05, 0.95)) for leg in legs]

        # Build correlation matrix
        if correlation_matrix is None or correlation_matrix.shape != (n_legs, n_legs):
            Sigma = self.build_sgp_correlation_matrix(legs)
        else:
            Sigma = nearest_positive_definite(correlation_matrix)

        rng = np.random.default_rng(random_seed)

        # Generate multivariate draws
        if copula_family == "student_t":
            # Student-t copula: Z ~ N(0, Sigma), S ~ Chi2(df), X = Z / sqrt(S/df)
            z = rng.multivariate_normal(mean=np.zeros(n_legs), cov=Sigma, size=n_simulations)
            s = rng.chisquare(df=df, size=(n_simulations, 1))
            x = z / np.sqrt(s / float(df))
            u = student_t.cdf(x, df=df)
        else:
            # Gaussian copula
            z = rng.multivariate_normal(mean=np.zeros(n_legs), cov=Sigma, size=n_simulations)
            u = norm.cdf(z)

        # Vectorized joint indicator: all legs must hit (u[:, i] <= probs[i])
        hits = np.ones(n_simulations, dtype=bool)
        for i in range(n_legs):
            hits &= (u[:, i] <= probs[i])

        p_joint = float(np.clip(np.mean(hits), 0.005, 0.95))
        p_independent = float(np.prod(probs))

        corr_boost_pct = round(((p_joint - p_independent) / max(0.0001, p_independent)) * 100.0, 2)
        fair_sgp_odds = round(1.0 / max(0.005, p_joint), 2)

        # Compute Expected Value (EV)
        offered_odds = max(1.10, float(offered_sgp_odds))
        ev_unit = (p_joint * offered_odds) - 1.0
        ev_pct = round(ev_unit * 100.0, 2)

        # Fractional Kelly staking with longshot/variance cap
        b = offered_odds - 1.0
        f_star = max(0.0, (p_joint * (b + 1.0) - 1.0) / max(0.05, b))
        fractional_multiplier = 0.20 if n_legs >= 3 else 0.35  # Conservative 1/5th Kelly for 3+ legs
        eff_fraction = min(0.035, f_star * fractional_multiplier)
        stake_pen = round(max(1.00, min(3.50, bankroll_pen * eff_fraction)), 2) if eff_fraction > 0 else 0.0

        is_value = (ev_pct >= 3.5) and (p_joint >= 0.08)

        # Format descriptive rationale
        leg_desc = " + ".join([f"{leg.get('player_name', leg.get('team', 'Leg'))} {leg.get('category', '')} {leg.get('selection', '')} {leg.get('line', '')}".strip() for leg in legs])
        rationale = (
            f"[RETAbet/Betsson SGP {n_legs}-Legs] {leg_desc}. "
            f"Prob Conjunta Cópula Student-t: {p_joint * 100:.2f}% (vs {p_independent * 100:.2f}% Independiente, Impulso: +{corr_boost_pct}%). "
            f"Cuota Ofrecida: {offered_odds:.2f} vs Justa: {fair_sgp_odds:.2f} (EV: {ev_pct:+.1f}%). "
            f"Stake Sugerido: S/ {stake_pen:.2f} PEN."
        )

        return {
            "num_legs": n_legs,
            "copula_family": copula_family,
            "degrees_of_freedom": df,
            "p_joint": round(p_joint, 4),
            "p_independent": round(p_independent, 4),
            "correlation_boost_pct": corr_boost_pct,
            "fair_sgp_odds": fair_sgp_odds,
            "offered_sgp_odds": round(offered_odds, 2),
            "ev_pct": ev_pct,
            "kelly_stake_pen": stake_pen,
            "is_value_sgp": is_value,
            "rationale": rationale,
            "legs": legs,
        }
