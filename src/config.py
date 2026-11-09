"""
Typed loader for config/model_config.yaml (the single source of truth for model and risk parameters).

Values are validated on load so that a misconfiguration fails fast instead of silently changing
risk. Risk limits are additionally checked against the hard caps from AGENTS.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "model_config.yaml"

# Hard caps from AGENTS.md (paper_trading_manager). Config can be stricter, never looser.
AGENTS_MAX_STAKE_PEN = 20.00
AGENTS_MAX_STAKE_BANKROLL_FRACTION = 0.20
AGENTS_MAX_KELLY_FRACTION = 1.00
AGENTS_MIN_EV_THRESHOLD = 0.05
AGENTS_MAX_SELECTIONS_PER_MATCHDAY = 3


class ConfigError(ValueError):
    """Raised when the configuration file is missing keys or violates documented limits."""


@dataclass(frozen=True)
class ModelConfig:
    version_id: str
    ewma_alpha_slow: float
    ewma_alpha_fast: float
    tempo_alpha_slow: float
    tempo_alpha_fast: float
    market_anchor_model_weight: float


@dataclass(frozen=True)
class RiskConfig:
    virtual_bankroll_initial_pen: float
    staking_mode: str
    kelly_fraction: float
    min_stake_pen: float
    max_stake_bankroll_fraction: float
    base_stake_pen: float
    max_stake_pen: float
    max_selections_per_matchday: int
    min_ev_threshold: float
    max_portfolio_exposure_pct: float
    allow_parlays: bool
    allow_player_props_betting: bool


@dataclass(frozen=True)
class AppConfig:
    model: ModelConfig
    risk: RiskConfig
    betting_allowed_source_types: tuple[str, ...]


def _require(section: dict[str, Any], key: str, section_name: str) -> Any:
    if key not in section:
        raise ConfigError(f"Missing config key '{section_name}.{key}' in {CONFIG_PATH}")
    return section[key]


def _in_range(name: str, value: float, low: float, high: float) -> float:
    if not (low <= float(value) <= high):
        raise ConfigError(f"Config value {name}={value} outside allowed range [{low}, {high}]")
    return float(value)


def parse_config(raw: dict[str, Any]) -> AppConfig:
    m = raw.get("model") or {}
    r = raw.get("risk_management") or {}
    src = raw.get("sources") or {}

    model = ModelConfig(
        version_id=str(_require(m, "version_id", "model")),
        ewma_alpha_slow=_in_range("ewma_alpha_slow", _require(m, "ewma_alpha_slow", "model"), 0.001, 0.5),
        ewma_alpha_fast=_in_range("ewma_alpha_fast", _require(m, "ewma_alpha_fast", "model"), 0.001, 0.5),
        tempo_alpha_slow=_in_range("tempo_alpha_slow", _require(m, "tempo_alpha_slow", "model"), 0.001, 0.5),
        tempo_alpha_fast=_in_range("tempo_alpha_fast", _require(m, "tempo_alpha_fast", "model"), 0.001, 0.5),
        market_anchor_model_weight=_in_range(
            "market_anchor_model_weight", _require(m, "market_anchor_model_weight", "model"), 0.0, 1.0
        ),
    )
    staking_mode = str(_require(r, "staking_mode", "risk_management"))
    if staking_mode not in ("fractional_kelly", "flat"):
        raise ConfigError(f"staking_mode must be 'fractional_kelly' or 'flat', got {staking_mode!r}")
    risk = RiskConfig(
        virtual_bankroll_initial_pen=_in_range(
            "virtual_bankroll_initial_pen", _require(r, "virtual_bankroll_initial_pen", "risk_management"), 1.0, 1e6
        ),
        staking_mode=staking_mode,
        kelly_fraction=_in_range("kelly_fraction", _require(r, "kelly_fraction", "risk_management"), 0.01, AGENTS_MAX_KELLY_FRACTION),
        min_stake_pen=_in_range("min_stake_pen", _require(r, "min_stake_pen", "risk_management"), 0.01, AGENTS_MAX_STAKE_PEN),
        max_stake_bankroll_fraction=_in_range(
            "max_stake_bankroll_fraction",
            _require(r, "max_stake_bankroll_fraction", "risk_management"),
            0.001,
            AGENTS_MAX_STAKE_BANKROLL_FRACTION,
        ),
        base_stake_pen=_in_range("base_stake_pen", _require(r, "base_stake_pen", "risk_management"), 0.01, AGENTS_MAX_STAKE_PEN),
        max_stake_pen=_in_range("max_stake_pen", _require(r, "max_stake_pen", "risk_management"), 0.01, AGENTS_MAX_STAKE_PEN),
        max_selections_per_matchday=int(
            _in_range(
                "max_selections_per_matchday",
                _require(r, "max_selections_per_matchday", "risk_management"),
                1,
                AGENTS_MAX_SELECTIONS_PER_MATCHDAY,
            )
        ),
        min_ev_threshold=_in_range("min_ev_threshold", _require(r, "min_ev_threshold", "risk_management"), AGENTS_MIN_EV_THRESHOLD, 1.0),
        max_portfolio_exposure_pct=_in_range(
            "max_portfolio_exposure_pct", _require(r, "max_portfolio_exposure_pct", "risk_management"), 0.0, 1.0
        ),
        allow_parlays=bool(_require(r, "allow_parlays", "risk_management")),
        allow_player_props_betting=bool(_require(r, "allow_player_props_betting", "risk_management")),
    )
    if risk.base_stake_pen > risk.max_stake_pen:
        raise ConfigError("base_stake_pen cannot exceed max_stake_pen")
    if risk.min_stake_pen > risk.max_stake_pen:
        raise ConfigError("min_stake_pen cannot exceed max_stake_pen")
    allowed = tuple(str(x) for x in (src.get("betting_allowed_source_types") or ["OBSERVED"]))
    if allowed != ("OBSERVED",):
        raise ConfigError("Only OBSERVED odds may be used for betting decisions")
    return AppConfig(model=model, risk=risk, betting_allowed_source_types=allowed)


@lru_cache(maxsize=1)
def load_config(path: str | None = None) -> AppConfig:
    cfg_path = Path(path) if path else CONFIG_PATH
    if not cfg_path.exists():
        raise ConfigError(f"Configuration file not found: {cfg_path}")
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return parse_config(raw)
