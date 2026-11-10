"""Virtual paper trading engines and immutable settlement accounting."""

from src.paper_trading.cppi import compute_cppi_multiplier
from src.paper_trading.engine import (
    DoubleSettlementError,
    PaperTradingEngine,
    RiskLimitError,
    build_production_engine,
)
from src.paper_trading.parlay_engine import ParlayRiskLimitError, ParlayTradingEngine
from src.paper_trading.staking import fractional_kelly_stake, kelly_fraction_full

__all__ = [
    "DoubleSettlementError",
    "PaperTradingEngine",
    "ParlayRiskLimitError",
    "ParlayTradingEngine",
    "RiskLimitError",
    "build_production_engine",
    "compute_cppi_multiplier",
    "fractional_kelly_stake",
    "kelly_fraction_full",
]
