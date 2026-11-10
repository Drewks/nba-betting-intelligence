"""
Test Helpers Facade (`tests/test_nba_intelligence.py`).
Maintains backward compatibility for tests and scripts importing fixtures
from test_nba_intelligence. The 50 core unit/integration tests have been
modularized into specialized test modules under tests/.
"""

from __future__ import annotations

from tests.test_helpers import _seed_sample_game_and_prediction

__all__ = [
    "_seed_sample_game_and_prediction",
]
