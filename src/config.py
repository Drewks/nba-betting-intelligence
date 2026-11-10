"""
Typed loader for config/model_config.yaml (the single source of truth for model and risk parameters).

Values are validated on load so that a misconfiguration fails fast instead of silently changing
risk. Risk limits are additionally checked against the hard caps from AGENTS.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "model_config.yaml"

# Hard caps from AGENTS.md (paper_trading_manager). Config can be stricter, never looser.
AGENTS_MAX_STAKE_PEN = 10.00
AGENTS_MAX_STAKE_BANKROLL_FRACTION = 0.10
AGENTS_MAX_KELLY_FRACTION = 0.50
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
    max_model_market_disagreement: float = 0.15


@dataclass(frozen=True)
class TierConfig:
    prob_floor: float
    prob_ceil: float
    base: float
    slope: float
    kelly_cap: float
    kelly_multiplier: float


@dataclass(frozen=True)
class ConvictionProfileConfig:
    tier_low: TierConfig
    tier_mid: TierConfig
    tier_high: TierConfig
    tier_star: TierConfig
    edge_modulator_floor: float
    edge_modulator_div: float
    min_stake_floor: float
    max_longshot_odds: float
    max_longshot_stake: float


DEFAULT_AGGRESSIVE_PROFILE = ConvictionProfileConfig(
    tier_low=TierConfig(0.35, 0.50, 3.50, 2.00, 2.00, 4.0),
    tier_mid=TierConfig(0.50, 0.58, 6.00, 3.50, 3.00, 6.0),
    tier_high=TierConfig(0.58, 0.65, 10.00, 4.50, 4.50, 8.0),
    tier_star=TierConfig(0.65, 1.00, 15.00, 5.00, 5.00, 10.0),
    edge_modulator_floor=0.40,
    edge_modulator_div=0.06,
    min_stake_floor=2.50,
    max_longshot_odds=4.00,
    max_longshot_stake=6.00,
)

DEFAULT_CONSERVATIVE_PROFILE = ConvictionProfileConfig(
    tier_low=TierConfig(0.35, 0.50, 1.00, 0.55, 0.25, 1.2),
    tier_mid=TierConfig(0.50, 0.58, 2.00, 0.95, 0.35, 1.5),
    tier_high=TierConfig(0.58, 0.65, 3.50, 0.95, 0.40, 1.8),
    tier_star=TierConfig(0.65, 1.00, 4.80, 0.85, 0.45, 2.0),
    edge_modulator_floor=0.20,
    edge_modulator_div=0.08,
    min_stake_floor=1.00,
    max_longshot_odds=2.50,
    max_longshot_stake=1.65,
)


@dataclass(frozen=True)
class ConvictionTiersConfig:
    aggressive: ConvictionProfileConfig = DEFAULT_AGGRESSIVE_PROFILE
    conservative: ConvictionProfileConfig = DEFAULT_CONSERVATIVE_PROFILE


@dataclass(frozen=True)
class OvertimeGuardConfig:
    enabled: bool = True
    min_overtime_prob: float = 0.068
    under_haircut: float = 0.85


@dataclass(frozen=True)
class CLVGovernorConfig:
    enabled: bool = True
    lookback_bets: int = 25
    min_sample_size: int = 4
    severe_negative_threshold: float = -2.0
    severe_negative_factor: float = 0.50
    moderate_negative_threshold: float = 0.0
    moderate_negative_factor: float = 0.75
    positive_alpha_threshold: float = 2.0
    positive_alpha_factor: float = 1.10
    neutral_factor: float = 1.00


@dataclass(frozen=True)
class RiskModulatorsConfig:
    high_uncertainty_std: float = 0.08
    high_uncertainty_factor: float = 0.85
    low_uncertainty_std: float = 0.045
    low_uncertainty_factor: float = 1.10
    narrow_conformal_width: float = 0.035
    narrow_conformal_factor: float = 1.06
    wide_conformal_width: float = 0.080
    wide_conformal_factor: float = 0.88
    ev_lower_bound_boost_factor: float = 1.05
    sharp_steam_delta: float = 0.020
    sharp_steam_factor: float = 1.08
    adverse_steam_delta: float = -0.020
    adverse_steam_factor: float = 0.85


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
    conviction_tiers: ConvictionTiersConfig = field(default_factory=ConvictionTiersConfig)
    overtime_guard: OvertimeGuardConfig = field(default_factory=OvertimeGuardConfig)
    clv_governor: CLVGovernorConfig = field(default_factory=CLVGovernorConfig)
    risk_modulators: RiskModulatorsConfig = field(default_factory=RiskModulatorsConfig)


@dataclass(frozen=True)
class SubBankrollConfig:
    enabled: bool = True
    virtual_bankroll_initial_pen: float = 50.00
    staking_mode: str = "dynamic_kelly"
    kelly_fraction: float = 0.40
    min_stake_pen: float = 0.50
    max_stake_pen: float = 5.00
    max_stake_bankroll_fraction: float = 0.10
    max_parlays_per_matchday: int = 2
    min_compound_ev_pct: float = 6.0


@dataclass(frozen=True)
class HybridAllocationConfig:
    enabled: bool = True
    totals_weight: float = 0.70
    moneyline_weight: float = 0.30
    max_totals_per_matchday: int = 2
    max_moneyline_per_matchday: int = 1


@dataclass(frozen=True)
class CLVMetaLabelingConfig:
    enabled: bool = True
    calibrated_weights_path: str = "config/calibrated_weights.json"
    intercept: float = -0.2085
    coef_steam_delta: float = 57.7103
    coef_conformal_width_excess: float = -2.1211
    coef_disagreement_excess: float = -0.1816
    coef_overround_excess: float = -0.0556
    time_decay_rate: float = 0.04
    max_hours_to_tipoff: float = 12.0
    adverse_steam_threshold: float = -0.040
    min_p_clv_threshold: float = 0.48


@dataclass(frozen=True)
class CopulaCorrelationsConfig:
    enabled: bool = True
    calibrated_weights_path: str = "config/calibrated_weights.json"


@dataclass(frozen=True)
class ViewportConfig:
    width: int = 1280
    height: int = 800


@dataclass(frozen=True)
class PlaywrightBrowserConfig:
    headless: bool = True
    timeout_ms: int = 15000
    wait_after_load_ms: int = 2000
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
    viewport: ViewportConfig = field(default_factory=ViewportConfig)


@dataclass(frozen=True)
class SportsbookEndpointConfig:
    name: str
    nba_url: str
    enabled: bool = True
    timeout_ms: int = 15000
    wait_after_load_ms: int = 2000


@dataclass(frozen=True)
class ESPNConfig:
    summary_api_url: str = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}"
    roster_api_url: str = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{espn_code}/roster"
    team_url_map: dict[str, str] = field(default_factory=lambda: {"NOP": "no", "UTA": "utah"})


@dataclass(frozen=True)
class ScraperConfig:
    playwright: PlaywrightBrowserConfig = field(default_factory=PlaywrightBrowserConfig)
    sportsbooks: dict[str, SportsbookEndpointConfig] = field(default_factory=dict)
    espn: ESPNConfig = field(default_factory=ESPNConfig)


SCRAPER_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "scraper_config.yaml"


@dataclass(frozen=True)
class SituationalFactorsConfig:
    home_court_advantage_elo: float = 50.0
    home_court_advantage_pts: float = 1.85
    b2b_penalty_away: float = -2.10
    b2b_penalty_home: float = -1.60
    rest_3plus_bonus_away: float = 0.20
    rest_3plus_bonus_home: float = 0.30
    altitude_edge_multiplier: float = 1.35
    altitude_threshold_feet: float = 4000.0
    altitude_divisor_feet: float = 4200.0
    travel_miles_rate: float = 0.22
    timezone_rate: float = 0.12


@dataclass(frozen=True)
class LineupSynergyConfig:
    initiator_absence_threshold: float = 1.25
    initiator_absence_penalty: float = 0.32
    rim_anchor_absence_threshold: float = 1.40
    rim_anchor_absence_penalty: float = 0.35
    two_way_wing_penalty: float = 0.22
    compound_absence_penalty: float = 0.14


@dataclass(frozen=True)
class AppConfig:
    model: ModelConfig
    risk: RiskConfig
    betting_allowed_source_types: tuple[str, ...]
    sub_bankroll: SubBankrollConfig = field(default_factory=SubBankrollConfig)
    hybrid_allocation: HybridAllocationConfig = field(default_factory=HybridAllocationConfig)
    clv_meta_labeling: CLVMetaLabelingConfig = field(default_factory=CLVMetaLabelingConfig)
    copula_correlations: CopulaCorrelationsConfig = field(default_factory=CopulaCorrelationsConfig)
    situational_factors: SituationalFactorsConfig = field(default_factory=SituationalFactorsConfig)
    lineup_synergy: LineupSynergyConfig = field(default_factory=LineupSynergyConfig)


def _require(section: dict[str, Any], key: str, section_name: str) -> Any:
    if key not in section:
        raise ConfigError(f"Missing config key '{section_name}.{key}' in {CONFIG_PATH}")
    return section[key]


def _in_range(name: str, value: float, low: float, high: float) -> float:
    if not (low <= float(value) <= high):
        raise ConfigError(f"Config value {name}={value} outside allowed range [{low}, {high}]")
    return float(value)


def _parse_tier_config(data: Any, default: TierConfig) -> TierConfig:
    if not isinstance(data, dict):
        return default
    return TierConfig(
        prob_floor=float(data.get("prob_floor", default.prob_floor)),
        prob_ceil=float(data.get("prob_ceil", default.prob_ceil)),
        base=float(data.get("base", default.base)),
        slope=float(data.get("slope", default.slope)),
        kelly_cap=float(data.get("kelly_cap", default.kelly_cap)),
        kelly_multiplier=float(data.get("kelly_multiplier", default.kelly_multiplier)),
    )


def _parse_conviction_profile(data: Any, is_aggressive: bool) -> ConvictionProfileConfig:
    default = DEFAULT_AGGRESSIVE_PROFILE if is_aggressive else DEFAULT_CONSERVATIVE_PROFILE
    if not isinstance(data, dict):
        return default
    return ConvictionProfileConfig(
        tier_low=_parse_tier_config(data.get("tier_low"), default.tier_low),
        tier_mid=_parse_tier_config(data.get("tier_mid"), default.tier_mid),
        tier_high=_parse_tier_config(data.get("tier_high"), default.tier_high),
        tier_star=_parse_tier_config(data.get("tier_star"), default.tier_star),
        edge_modulator_floor=float(data.get("edge_modulator_floor", default.edge_modulator_floor)),
        edge_modulator_div=float(data.get("edge_modulator_div", default.edge_modulator_div)),
        min_stake_floor=float(data.get("min_stake_floor", default.min_stake_floor)),
        max_longshot_odds=float(data.get("max_longshot_odds", default.max_longshot_odds)),
        max_longshot_stake=float(data.get("max_longshot_stake", default.max_longshot_stake)),
    )


def _parse_conviction_tiers(data: Any) -> ConvictionTiersConfig:
    if not isinstance(data, dict):
        return ConvictionTiersConfig()
    return ConvictionTiersConfig(
        aggressive=_parse_conviction_profile(data.get("aggressive"), is_aggressive=True),
        conservative=_parse_conviction_profile(data.get("conservative"), is_aggressive=False),
    )


def _parse_overtime_guard(data: Any) -> OvertimeGuardConfig:
    default = OvertimeGuardConfig()
    if not isinstance(data, dict):
        return default
    return OvertimeGuardConfig(
        enabled=bool(data.get("enabled", default.enabled)),
        min_overtime_prob=float(data.get("min_overtime_prob", default.min_overtime_prob)),
        under_haircut=float(data.get("under_haircut", default.under_haircut)),
    )


def _parse_clv_governor(data: Any) -> CLVGovernorConfig:
    default = CLVGovernorConfig()
    if not isinstance(data, dict):
        return default
    return CLVGovernorConfig(
        enabled=bool(data.get("enabled", default.enabled)),
        lookback_bets=int(data.get("lookback_bets", default.lookback_bets)),
        min_sample_size=int(data.get("min_sample_size", default.min_sample_size)),
        severe_negative_threshold=float(data.get("severe_negative_threshold", default.severe_negative_threshold)),
        severe_negative_factor=float(data.get("severe_negative_factor", default.severe_negative_factor)),
        moderate_negative_threshold=float(data.get("moderate_negative_threshold", default.moderate_negative_threshold)),
        moderate_negative_factor=float(data.get("moderate_negative_factor", default.moderate_negative_factor)),
        positive_alpha_threshold=float(data.get("positive_alpha_threshold", default.positive_alpha_threshold)),
        positive_alpha_factor=float(data.get("positive_alpha_factor", default.positive_alpha_factor)),
        neutral_factor=float(data.get("neutral_factor", default.neutral_factor)),
    )


def _parse_risk_modulators(data: Any) -> RiskModulatorsConfig:
    default = RiskModulatorsConfig()
    if not isinstance(data, dict):
        return default
    return RiskModulatorsConfig(
        high_uncertainty_std=float(data.get("high_uncertainty_std", default.high_uncertainty_std)),
        high_uncertainty_factor=float(data.get("high_uncertainty_factor", default.high_uncertainty_factor)),
        low_uncertainty_std=float(data.get("low_uncertainty_std", default.low_uncertainty_std)),
        low_uncertainty_factor=float(data.get("low_uncertainty_factor", default.low_uncertainty_factor)),
        narrow_conformal_width=float(data.get("narrow_conformal_width", default.narrow_conformal_width)),
        narrow_conformal_factor=float(data.get("narrow_conformal_factor", default.narrow_conformal_factor)),
        wide_conformal_width=float(data.get("wide_conformal_width", default.wide_conformal_width)),
        wide_conformal_factor=float(data.get("wide_conformal_factor", default.wide_conformal_factor)),
        ev_lower_bound_boost_factor=float(data.get("ev_lower_bound_boost_factor", default.ev_lower_bound_boost_factor)),
        sharp_steam_delta=float(data.get("sharp_steam_delta", default.sharp_steam_delta)),
        sharp_steam_factor=float(data.get("sharp_steam_factor", default.sharp_steam_factor)),
        adverse_steam_delta=float(data.get("adverse_steam_delta", default.adverse_steam_delta)),
        adverse_steam_factor=float(data.get("adverse_steam_factor", default.adverse_steam_factor)),
    )


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
        max_model_market_disagreement=_in_range(
            "max_model_market_disagreement",
            m.get("max_model_market_disagreement", 0.15),
            0.01,
            0.50,
        ),
    )
    staking_mode = str(_require(r, "staking_mode", "risk_management"))
    if staking_mode not in ("fractional_kelly", "flat"):
        raise ConfigError(f"staking_mode must be 'fractional_kelly' or 'flat', got {staking_mode!r}")

    conviction_tiers = _parse_conviction_tiers(r.get("conviction_tiers"))
    overtime_guard = _parse_overtime_guard(r.get("overtime_guard"))
    clv_governor = _parse_clv_governor(r.get("clv_governor"))
    risk_modulators = _parse_risk_modulators(r.get("risk_modulators"))

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
        conviction_tiers=conviction_tiers,
        overtime_guard=overtime_guard,
        clv_governor=clv_governor,
        risk_modulators=risk_modulators,
    )
    if risk.base_stake_pen > risk.max_stake_pen:
        raise ConfigError("base_stake_pen cannot exceed max_stake_pen")
    if risk.min_stake_pen > risk.max_stake_pen:
        raise ConfigError("min_stake_pen cannot exceed max_stake_pen")
    allowed = tuple(str(x) for x in (src.get("betting_allowed_source_types") or ["OBSERVED"]))
    if allowed != ("OBSERVED",):
        raise ConfigError("Only OBSERVED odds may be used for betting decisions")

    # Optional sub_bankroll section
    sub_raw = raw.get("sub_bankroll_combinadas")
    if sub_raw:
        sub_bankroll = SubBankrollConfig(
            enabled=bool(sub_raw.get("enabled", True)),
            virtual_bankroll_initial_pen=_in_range("virtual_bankroll_initial_pen", sub_raw.get("virtual_bankroll_initial_pen", 50.0), 1.0, 1000.0),
            staking_mode=str(sub_raw.get("staking_mode", "dynamic_kelly")),
            kelly_fraction=_in_range("kelly_fraction", sub_raw.get("kelly_fraction", 0.40), 0.01, 0.50),
            min_stake_pen=_in_range("min_stake_pen", sub_raw.get("min_stake_pen", 0.50), 0.10, 5.00),
            max_stake_pen=_in_range("max_stake_pen", sub_raw.get("max_stake_pen", 5.00), 0.50, 25.00),
            max_stake_bankroll_fraction=_in_range("max_stake_bankroll_fraction", sub_raw.get("max_stake_bankroll_fraction", 0.10), 0.01, 0.25),
            max_parlays_per_matchday=int(_in_range("max_parlays_per_matchday", sub_raw.get("max_parlays_per_matchday", 2), 1, 10)),
            min_compound_ev_pct=_in_range("min_compound_ev_pct", sub_raw.get("min_compound_ev_pct", 6.0), 1.0, 50.0),
        )
    else:
        sub_bankroll = SubBankrollConfig()

    # Optional hybrid_allocation section
    hyb_raw = raw.get("hybrid_allocation")
    if hyb_raw:
        hybrid_allocation = HybridAllocationConfig(
            enabled=bool(hyb_raw.get("enabled", True)),
            totals_weight=_in_range("totals_weight", hyb_raw.get("totals_weight", 0.70), 0.0, 1.0),
            moneyline_weight=_in_range("moneyline_weight", hyb_raw.get("moneyline_weight", 0.30), 0.0, 1.0),
            max_totals_per_matchday=int(_in_range("max_totals_per_matchday", hyb_raw.get("max_totals_per_matchday", 2), 0, 10)),
            max_moneyline_per_matchday=int(_in_range("max_moneyline_per_matchday", hyb_raw.get("max_moneyline_per_matchday", 1), 0, 10)),
        )
    else:
        hybrid_allocation = HybridAllocationConfig()

    # Optional clv_meta_labeling section
    clv_raw = raw.get("clv_meta_labeling")
    if clv_raw:
        clv_meta_labeling = CLVMetaLabelingConfig(
            enabled=bool(clv_raw.get("enabled", True)),
            calibrated_weights_path=str(clv_raw.get("calibrated_weights_path", "config/calibrated_weights.json")),
            intercept=float(clv_raw.get("intercept", -0.2085)),
            coef_steam_delta=float(clv_raw.get("coef_steam_delta", 57.7103)),
            coef_conformal_width_excess=float(clv_raw.get("coef_conformal_width_excess", -2.1211)),
            coef_disagreement_excess=float(clv_raw.get("coef_disagreement_excess", -0.1816)),
            coef_overround_excess=float(clv_raw.get("coef_overround_excess", -0.0556)),
            time_decay_rate=float(clv_raw.get("time_decay_rate", 0.04)),
            max_hours_to_tipoff=float(clv_raw.get("max_hours_to_tipoff", 12.0)),
            adverse_steam_threshold=float(clv_raw.get("adverse_steam_threshold", -0.040)),
            min_p_clv_threshold=float(clv_raw.get("min_p_clv_threshold", 0.48)),
        )
    else:
        clv_meta_labeling = CLVMetaLabelingConfig()

    # Optional copula_correlations section
    cop_raw = raw.get("copula_correlations")
    if cop_raw:
        copula_correlations = CopulaCorrelationsConfig(
            enabled=bool(cop_raw.get("enabled", True)),
            calibrated_weights_path=str(cop_raw.get("calibrated_weights_path", "config/calibrated_weights.json")),
        )
    else:
        copula_correlations = CopulaCorrelationsConfig()

    # Optional situational_factors section
    sit_raw = raw.get("situational_factors")
    if sit_raw:
        situational_factors = SituationalFactorsConfig(
            home_court_advantage_elo=float(sit_raw.get("home_court_advantage_elo", 50.0)),
            home_court_advantage_pts=float(sit_raw.get("home_court_advantage_pts", 1.85)),
            b2b_penalty_away=float(sit_raw.get("b2b_penalty_away", -2.10)),
            b2b_penalty_home=float(sit_raw.get("b2b_penalty_home", -1.60)),
            rest_3plus_bonus_away=float(sit_raw.get("rest_3plus_bonus_away", 0.20)),
            rest_3plus_bonus_home=float(sit_raw.get("rest_3plus_bonus_home", 0.30)),
            altitude_edge_multiplier=float(sit_raw.get("altitude_edge_multiplier", 1.35)),
            altitude_threshold_feet=float(sit_raw.get("altitude_threshold_feet", 4000.0)),
            altitude_divisor_feet=float(sit_raw.get("altitude_divisor_feet", 4200.0)),
            travel_miles_rate=float(sit_raw.get("travel_miles_rate", 0.22)),
            timezone_rate=float(sit_raw.get("timezone_rate", 0.12)),
        )
    else:
        situational_factors = SituationalFactorsConfig()

    # Optional lineup_synergy section
    syn_raw = raw.get("lineup_synergy")
    if syn_raw:
        lineup_synergy = LineupSynergyConfig(
            initiator_absence_threshold=float(syn_raw.get("initiator_absence_threshold", 1.25)),
            initiator_absence_penalty=float(syn_raw.get("initiator_absence_penalty", 0.32)),
            rim_anchor_absence_threshold=float(syn_raw.get("rim_anchor_absence_threshold", 1.40)),
            rim_anchor_absence_penalty=float(syn_raw.get("rim_anchor_absence_penalty", 0.35)),
            two_way_wing_penalty=float(syn_raw.get("two_way_wing_penalty", 0.22)),
            compound_absence_penalty=float(syn_raw.get("compound_absence_penalty", 0.14)),
        )
    else:
        lineup_synergy = LineupSynergyConfig()

    return AppConfig(
        model=model,
        risk=risk,
        betting_allowed_source_types=allowed,
        sub_bankroll=sub_bankroll,
        hybrid_allocation=hybrid_allocation,
        clv_meta_labeling=clv_meta_labeling,
        copula_correlations=copula_correlations,
        situational_factors=situational_factors,
        lineup_synergy=lineup_synergy,
    )


@lru_cache(maxsize=1)
def load_config(path: str | None = None) -> AppConfig:
    cfg_path = Path(path) if path else CONFIG_PATH
    if not cfg_path.exists():
        raise ConfigError(f"Configuration file not found: {cfg_path}")
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return parse_config(raw)

def parse_scraper_config(raw: dict[str, Any]) -> ScraperConfig:
    pw_raw = raw.get("playwright") or {}
    vp_raw = pw_raw.get("viewport") or {}
    viewport = ViewportConfig(
        width=int(vp_raw.get("width", 1280)),
        height=int(vp_raw.get("height", 800)),
    )
    playwright = PlaywrightBrowserConfig(
        headless=bool(pw_raw.get("headless", True)),
        timeout_ms=int(pw_raw.get("timeout_ms", 15000)),
        wait_after_load_ms=int(pw_raw.get("wait_after_load_ms", 2000)),
        user_agent=str(pw_raw.get("user_agent", (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ))),
        viewport=viewport,
    )

    books_raw = raw.get("sportsbooks") or {}
    sportsbooks: dict[str, SportsbookEndpointConfig] = {}
    for key, b_data in books_raw.items():
        if isinstance(b_data, dict):
            sportsbooks[str(key)] = SportsbookEndpointConfig(
                name=str(b_data.get("name", key)),
                nba_url=str(b_data.get("nba_url", "")),
                enabled=bool(b_data.get("enabled", True)),
                timeout_ms=int(b_data.get("timeout_ms", 15000)),
                wait_after_load_ms=int(b_data.get("wait_after_load_ms", 2000)),
            )

    espn_raw = raw.get("espn") or {}
    espn = ESPNConfig(
        summary_api_url=str(espn_raw.get("summary_api_url", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}")),
        roster_api_url=str(espn_raw.get("roster_api_url", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{espn_code}/roster")),
        team_url_map=dict(espn_raw.get("team_url_map") or {"NOP": "no", "UTA": "utah"}),
    )

    return ScraperConfig(
        playwright=playwright,
        sportsbooks=sportsbooks,
        espn=espn,
    )


@lru_cache(maxsize=1)
def load_scraper_config(path: str | Path | None = None) -> ScraperConfig:
    cfg_p = Path(path) if path else SCRAPER_CONFIG_PATH
    if not cfg_p.exists():
        return ScraperConfig(
            playwright=PlaywrightBrowserConfig(),
            sportsbooks={
                "retabet": SportsbookEndpointConfig(
                    name="RETAbet Perú",
                    nba_url="https://retabet.pe/deportes/baloncesto/usa/nba",
                ),
                "betano": SportsbookEndpointConfig(
                    name="Betano Perú",
                    nba_url="https://pe.betano.com/sport/basquetbol/estados-unidos/nba/",
                ),
            },
            espn=ESPNConfig(),
        )
    raw = yaml.safe_load(cfg_p.read_text(encoding="utf-8")) or {}
    return parse_scraper_config(raw)
