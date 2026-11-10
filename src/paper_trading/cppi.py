"""
Constant Proportion Portfolio Insurance (CPPI) Capital Preservation Shield.
"""

from __future__ import annotations


def compute_cppi_multiplier(
    current_bankroll: float,
    peak_bankroll: float,
    floor_fraction: float = 0.85,
) -> float:
    """
    V9 Phase 5: Constant Proportion Portfolio Insurance (CPPI) Capital Preservation Shield.
    Calculates dynamic risk multiplier based on cushion above an 85% high-water mark floor:
    - When bankroll is at or above peak: multiplier = 1.0 (full capacity).
    - When bankroll approaches the floor: exposure scales down towards 0.15.
    """
    peak = max(1.0, float(peak_bankroll))
    floor_val = peak * floor_fraction
    cushion = max(0.0, float(current_bankroll) - floor_val)
    target_cushion = max(1.0, peak * (1.0 - floor_fraction))

    cushion_ratio = cushion / target_cushion
    if cushion_ratio >= 1.0:
        return 1.0
    elif cushion_ratio <= 0.0:
        return 0.15
    else:
        return round(max(0.15, min(1.0, float(cushion_ratio))), 4)
