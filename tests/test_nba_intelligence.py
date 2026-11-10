"""
Test Suite Facade (`tests/test_nba_intelligence.py`).
Maintains backward compatibility for tests and external scripts importing fixtures.
The 50 core unit and integration tests have been modularized into specialized test modules under tests/.
"""

from __future__ import annotations

from tests.helpers import _seed_sample_game_and_prediction

__all__ = [
    "_seed_sample_game_and_prediction",
]


def test_test_suite_facade_and_fixtures() -> None:
    """Verifies test suite facade integrity and export of shared fixtures."""
    assert callable(_seed_sample_game_and_prediction)
