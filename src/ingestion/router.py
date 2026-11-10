"""
DataSourceRouter (`src/ingestion/router.py`):
Routes data requests through prioritized interchangeable adapters with automatic failover.
"""

from __future__ import annotations

from typing import Any

from src.ingestion.base import AdapterUnavailableError, BaseNBADataAdapter


class DataSourceRouter:
    """Routes data requests through prioritized interchangeable adapters with automatic failover."""

    def __init__(self, adapters: list[BaseNBADataAdapter]) -> None:
        if not adapters:
            raise ValueError("DataSourceRouter requires at least one adapter.")
        self.adapters = adapters

    def fetch_with_failover(
        self,
        date_str: str | None = None,
        as_of_utc: str | None = None,
    ) -> dict[str, Any]:
        errors: list[dict[str, str]] = []
        for adapter in self.adapters:
            try:
                data = adapter.fetch_games_and_odds(date_str=date_str, as_of_utc=as_of_utc)
                if data.get("games"):
                    return {
                        "active_provider": adapter.provider_name,
                        "games": data["games"],
                        "odds": data.get("odds", []),
                        "failover_events": errors,
                    }
                errors.append(
                    {
                        "provider": adapter.provider_name,
                        "reason": "Returned 0 games for requested query",
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "provider": adapter.provider_name,
                        "reason": str(exc),
                    }
                )
        raise AdapterUnavailableError(f"All configured adapters failed: {errors}")
