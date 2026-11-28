"""
Custom exceptions for the paper trading engine.
"""

from __future__ import annotations


class RiskLimitError(ValueError):
    """Raised when a proposed bet violates conservative risk or staking rules."""


class DoubleSettlementError(RuntimeError):
    """Raised when attempting to settle a bet that has already been settled."""
