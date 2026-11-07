"""
Peruvian Sportsbook Intelligence, Shin De-Vigged Pricing & Arbitrage/Value Scanner (`src/ingestion/peru_sportsbooks.py`).
Provides deep integration with sportsbooks operating in Peru (both MINCETUR-licensed and accessible international sharp books):
- Catalog of Peruvian sportsbooks (Betsson, Coolbet, RETAbet, Apuesta Total, Te Apuesto, Doradobet, Inkabet, 1xBet, Pinnacle)
- Local payment gateways (Yape, Plin, Tarjeta RETAbet, BCP, BBVA, Interbank, PagoEfectivo, Cash in physical shops)
- Real-world margin calibration per bookmaker anchored via Shin's De-Vigging method
- Cross-bookmaker synthetic margin, Surebet/Arbitrage detector, and Soft-Book +EV scanner in Soles (S/. PEN)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

from src.prediction.ev_calculator import devig_shin


@dataclass(frozen=True)
class PeruSportsbook:
    id: str
    name: str
    is_mincetur_licensed: bool
    payment_methods: list[str]
    typical_vig_pct: float
    website: str
    badge_color: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Catalog of sportsbooks operating in Peru
PERU_SPORTSBOOKS: dict[str, PeruSportsbook] = {
    "betsson_pe": PeruSportsbook(
        id="betsson_pe",
        name="Betsson Perú",
        is_mincetur_licensed=True,
        payment_methods=["Yape", "Plin", "PagoEfectivo", "BCP", "BBVA", "Interbank", "Tarjetas"],
        typical_vig_pct=5.2,
        website="https://www.betsson.pe",
        badge_color="#FF6600",
        description="Líder regulado por MINCETUR en Perú. Depósitos instantáneos con Yape y Plin.",
    ),
    "coolbet_pe": PeruSportsbook(
        id="coolbet_pe",
        name="Coolbet Perú",
        is_mincetur_licensed=True,
        payment_methods=["Yape", "Plin", "Transferencia Bancaria", "Tarjetas"],
        typical_vig_pct=3.8,
        website="https://www.coolbet.pe",
        badge_color="#00B4D8",
        description="Menor margen comercial en Perú. Cuotas de alta competitividad.",
    ),
    "apuesta_total": PeruSportsbook(
        id="apuesta_total",
        name="Apuesta Total",
        is_mincetur_licensed=True,
        payment_methods=["Yape", "Plin", "Tiendas Físicas", "Teleservicios", "Banca por Internet"],
        typical_vig_pct=6.0,
        website="https://www.apuestatotal.com",
        badge_color="#E60000",
        description="Red masiva de tiendas físicas en todo el Perú y portal online.",
    ),
    "te_apuesto": PeruSportsbook(
        id="te_apuesto",
        name="Te Apuesto",
        is_mincetur_licensed=True,
        payment_methods=["Puntos La Tinka", "Lotocard", "Yape", "Interbank", "BCP"],
        typical_vig_pct=6.8,
        website="https://www.teapuesto.pe",
        badge_color="#FFB703",
        description="La casa oficial de loterías La Tinka S.A., con presencia en módulos retail.",
    ),
    "doradobet": PeruSportsbook(
        id="doradobet",
        name="Doradobet Perú",
        is_mincetur_licensed=True,
        payment_methods=["Yape", "Plin", "PagoEfectivo", "SafetyPay", "Locales"],
        typical_vig_pct=5.5,
        website="https://www.doradobet.com",
        badge_color="#D4AF37",
        description="Amplia presencia en el mercado peruano con depósitos locales rápidos.",
    ),
    "retabet_pe": PeruSportsbook(
        id="retabet_pe",
        name="RETAbet Perú",
        is_mincetur_licensed=True,
        payment_methods=["Yape", "Plin", "Tarjeta RETAbet", "PagoEfectivo", "SafetyPay", "Locales Físicos", "BCP", "BBVA"],
        typical_vig_pct=4.8,
        website="https://retabet.pe",
        badge_color="#E50914",
        description="Regulada MINCETUR en Perú. Especializada en 'Crea tu Apuesta' NBA, retiros al instante con Tarjeta RETAbet y terminales físicas.",
    ),
    "inkabet": PeruSportsbook(
        id="inkabet",
        name="Inkabet",
        is_mincetur_licensed=True,
        payment_methods=["Yape", "Plin", "PagoEfectivo", "BCP", "BBVA"],
        typical_vig_pct=5.4,
        website="https://www.inkabet.pe",
        badge_color="#2A9D8F",
        description="Pionera de apuestas online en Perú, operada por Betsson Group.",
    ),
    "1xbet_pe": PeruSportsbook(
        id="1xbet_pe",
        name="1xBet Perú",
        is_mincetur_licensed=False,
        payment_methods=["Yape", "Plin", "BCP", "BBVA", "Criptomonedas"],
        typical_vig_pct=3.2,
        website="https://1xbet.pe",
        badge_color="#1B3B6F",
        description="Operador internacional muy popular en Perú. Mercados extensos y cuotas altas.",
    ),
    "pinnacle_pe": PeruSportsbook(
        id="pinnacle_pe",
        name="Pinnacle (Perú Sharp)",
        is_mincetur_licensed=False,
        payment_methods=["Transferencia Bancaria Local (PEN)", "Tarjetas", "Cripto"],
        typical_vig_pct=2.2,
        website="https://www.pinnacle.com",
        badge_color="#E63946",
        description="Referencia mundial sharp para profesionales. Acepta soles peruanos sin limitar.",
    ),
}


def get_peru_sportsbooks_catalog() -> list[dict[str, Any]]:
    """Returns the serializable list of sportsbooks available in Peru."""
    return [sb.to_dict() for sb in PERU_SPORTSBOOKS.values()]


def detect_peru_market_inefficiencies(
    books: list[dict[str, Any]],
    model_p_home: float,
    model_p_away: float,
    bankroll_pen: float = 100.0,
) -> dict[str, Any]:
    """
    V8 Cross-Bookmaker Inefficiency, Arbitrage (Surebet) & Soft-Book +EV Detector for Peru:
    1. Identifies the highest Home and Away decimal odds across all Peruvian operators (and MINCETUR-only subset).
    2. Calculates the Synthetic Combined Overround when line-shopping across multiple accounts.
    3. Detects risk-free Cross-Bookmaker Arbitrage (Surebet) when 1/best_home + 1/best_away < 1.0,
       computing exact optimal Soles (S/. PEN) stakes for both sides.
    4. Lists all +EV opportunities where a Peruvian bookmaker's price exceeds our calibrated fair odds.
    """
    if not books:
        return {
            "synthetic_overround_pct": 0.0,
            "is_surebet_arbitrage": False,
            "arbitrage_roi_pct": 0.0,
            "arbitrage_allocation_pen": None,
            "plus_ev_opportunities": [],
        }

    best_h_book = max(books, key=lambda b: float(b.get("home_odds", 1.01)))
    best_a_book = max(books, key=lambda b: float(b.get("away_odds", 1.01)))
    best_h_odds = float(best_h_book["home_odds"])
    best_a_odds = float(best_a_book["away_odds"])

    inv_sum = (1.0 / best_h_odds) + (1.0 / best_a_odds)
    synthetic_overround_pct = round((inv_sum - 1.0) * 100.0, 2)
    is_surebet = inv_sum < 0.9999
    arb_roi_pct = round(((1.0 / inv_sum) - 1.0) * 100.0, 2) if is_surebet else 0.0

    arb_alloc = None
    if is_surebet and bankroll_pen > 0:
        stake_h = round(bankroll_pen * (1.0 / best_h_odds) / inv_sum, 2)
        stake_a = round(bankroll_pen - stake_h, 2)
        guaranteed_return = round(stake_h * best_h_odds, 2)
        arb_alloc = {
            "home_book": best_h_book["name"],
            "home_odds": best_h_odds,
            "home_stake_pen": stake_h,
            "away_book": best_a_book["name"],
            "away_odds": best_a_odds,
            "away_stake_pen": stake_a,
            "guaranteed_payout_pen": guaranteed_return,
            "guaranteed_profit_pen": round(guaranteed_return - bankroll_pen, 2),
        }

    plus_ev_ops: list[dict[str, Any]] = []
    for b in books:
        h_o = float(b["home_odds"])
        a_o = float(b["away_odds"])
        ev_h = round((model_p_home * h_o - 1.0) * 100.0, 2)
        ev_a = round((model_p_away * a_o - 1.0) * 100.0, 2)
        if ev_h > 0.5:
            plus_ev_ops.append({
                "book_id": b["id"],
                "book_name": b["name"],
                "is_mincetur_licensed": b["is_mincetur_licensed"],
                "selection": "HOME",
                "decimal_odds": h_o,
                "model_prob_pct": round(model_p_home * 100.0, 1),
                "ev_pct": ev_h,
            })
        if ev_a > 0.5:
            plus_ev_ops.append({
                "book_id": b["id"],
                "book_name": b["name"],
                "is_mincetur_licensed": b["is_mincetur_licensed"],
                "selection": "AWAY",
                "decimal_odds": a_o,
                "model_prob_pct": round(model_p_away * 100.0, 1),
                "ev_pct": ev_a,
            })

    plus_ev_ops.sort(key=lambda x: -x["ev_pct"])
    return {
        "synthetic_overround_pct": synthetic_overround_pct,
        "is_surebet_arbitrage": is_surebet,
        "arbitrage_roi_pct": arb_roi_pct,
        "arbitrage_allocation_pen": arb_alloc,
        "plus_ev_opportunities": plus_ev_ops,
    }


def calculate_peru_odds_comparison(
    p_home_fair: float,
    p_away_fair: float,
    benchmark_home_odds: float | None = None,
    benchmark_away_odds: float | None = None,
) -> dict[str, Any]:
    """
    Computes calibrated odds for all major Peruvian sportsbooks based on their
    observed vig and pricing structure.
    When benchmark_home_odds and benchmark_away_odds are provided (> 1.0), derives the
    market's true fair baseline via Shin's De-Vigging method (`devig_shin`) so all
    Peruvian retail sportsbooks (RETAbet, Betsson, Coolbet, Apuesta Total, Doradobet,
    Inkabet, Te Apuesto) reflect realistic market-anchored pricing rather than uniform 50/50 lines.
    Returns:
    - best_home: { book, odds }
    - best_away: { book, odds }
    - books: list of all books with home_odds, away_odds, ev_home_pct, ev_away_pct, payment_methods, etc.
    - market_efficiency: cross-bookmaker synthetic margin, arbitrage status, and +EV soft-book picks.
    """
    total_p = p_home_fair + p_away_fair
    if total_p <= 0:
        model_p_h, model_p_a = 0.5, 0.5
    else:
        model_p_h = p_home_fair / total_p
        model_p_a = p_away_fair / total_p

    has_benchmark = (
        benchmark_home_odds is not None
        and benchmark_away_odds is not None
        and float(benchmark_home_odds) > 1.0
        and float(benchmark_away_odds) > 1.0
    )

    if has_benchmark:
        mkt_p_h, mkt_p_a, _ = devig_shin(float(benchmark_home_odds), float(benchmark_away_odds))
        # If caller passed neutral 0.5/0.5 (e.g., pure odds scraper), use Shin fair market prob as model reference too
        if abs(model_p_h - 0.5) < 1e-6 and abs(model_p_a - 0.5) < 1e-6:
            model_p_h, model_p_a = mkt_p_h, mkt_p_a
    else:
        mkt_p_h, mkt_p_a = model_p_h, model_p_a

    comparison_items: list[dict[str, Any]] = []

    best_home_price = 0.0
    best_home_book = ""
    best_away_price = 0.0
    best_away_book = ""

    for sb in PERU_SPORTSBOOKS.values():
        margin = sb.typical_vig_pct / 100.0
        if sb.id == "pinnacle_pe" and has_benchmark:
            h_odds = round(float(benchmark_home_odds), 3)
            a_odds = round(float(benchmark_away_odds), 3)
        elif sb.id == "1xbet_pe" and has_benchmark:
            h_odds = round(max(1.01, float(benchmark_home_odds) * 0.995), 3)
            a_odds = round(max(1.01, float(benchmark_away_odds) * 0.995), 3)
        elif sb.id == "coolbet_pe" and has_benchmark:
            h_odds = round(max(1.01, float(benchmark_home_odds) * 0.985), 3)
            a_odds = round(max(1.01, float(benchmark_away_odds) * 0.985), 3)
        else:
            # Retail Peruvian pricing anchored to Shin de-vigged market probability + asymmetric FLB vig
            # Underdogs carry slightly higher proportional margin in retail books
            flb_weight_h = 1.0 + margin * (0.85 + 0.30 * (1.0 - mkt_p_h))
            flb_weight_a = 1.0 + margin * (0.85 + 0.30 * (1.0 - mkt_p_a))
            p_h_vig = min(0.98, mkt_p_h * flb_weight_h)
            p_a_vig = min(0.98, mkt_p_a * flb_weight_a)
            h_odds = round(max(1.01, 1.0 / p_h_vig), 3)
            a_odds = round(max(1.01, 1.0 / p_a_vig), 3)

        if h_odds > best_home_price:
            best_home_price = h_odds
            best_home_book = sb.name

        if a_odds > best_away_price:
            best_away_price = a_odds
            best_away_book = sb.name

        ev_h_pct = round((model_p_h * h_odds - 1.0) * 100.0, 2)
        ev_a_pct = round((model_p_a * a_odds - 1.0) * 100.0, 2)

        comparison_items.append({
            "id": sb.id,
            "name": sb.name,
            "is_mincetur_licensed": sb.is_mincetur_licensed,
            "payment_methods": sb.payment_methods,
            "typical_vig_pct": sb.typical_vig_pct,
            "home_odds": h_odds,
            "away_odds": a_odds,
            "ev_home_pct": ev_h_pct,
            "ev_away_pct": ev_a_pct,
            "badge_color": sb.badge_color,
            "website": sb.website,
            "description": sb.description,
        })

    # Sort books: Licensed with best odds first
    comparison_items.sort(key=lambda x: (not x["is_mincetur_licensed"], -x["home_odds"]))

    inefficiencies = detect_peru_market_inefficiencies(comparison_items, model_p_h, model_p_a)

    return {
        "best_home": {"book": best_home_book, "odds": best_home_price},
        "best_away": {"book": best_away_book, "odds": best_away_price},
        "books": comparison_items,
        "market_efficiency": inefficiencies,
    }


def get_peru_sportsbooks_json_for_frontend() -> str:
    """Returns JSON serialization for embedding into dashboard scripts."""
    data = {
        "sportsbooks": [sb.to_dict() for sb in PERU_SPORTSBOOKS.values()],
    }
    return json.dumps(data, ensure_ascii=False)
