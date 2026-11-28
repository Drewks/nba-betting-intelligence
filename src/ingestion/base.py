"""Base interfaces shared by all data adapters (kept dependency-free to avoid import cycles)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AdapterUnavailableError(RuntimeError):
    """Raised when an external data adapter cannot be reached or lacks credentials."""


class BaseNBADataAdapter(ABC):
    """Abstract interface for interchangeable NBA statistics, schedule, and odds providers."""

    provider_name: str = "base"

    @abstractmethod
    def fetch_games_and_odds(
        self,
        date_str: str | None = None,
        as_of_utc: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Returns {'games': [...], 'odds': [...]} with explicit provenance and timestamps."""
