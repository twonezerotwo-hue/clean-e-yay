"""Small, serialisable models for world-state evidence.

All normalised pressures use ``-1..1``. ``None`` means unavailable; it is never
silently converted to a neutral value. These models are evidence only and do not
contain trade actions or sizing.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


def _json(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    return value


@dataclass(frozen=True)
class GeopoliticalEvent:
    event_id: str
    event_type: str
    actors: tuple[str, ...] = ()
    region: str | None = None
    location: str | None = None
    status: str = "UNKNOWN"
    confirmed_action: bool = False
    threat_only: bool = False
    severity: float | None = None
    energy_exposure: float | None = None
    shipping_exposure: float | None = None
    trade_exposure: float | None = None
    financial_sanctions_exposure: float | None = None
    commodity_exposure: float | None = None
    nuclear_risk: float | None = None
    direct_us_involvement: bool | None = None
    source_confidence: float = 0.0
    source_credibility: float = 0.0
    independent_confirmation_count: int = 0
    official_confirmation: bool = False
    confirmation_count: int = 0
    source_diversity: int = 0
    published_at: datetime | None = None
    freshness_seconds: float | None = None
    half_life_minutes: int | None = None
    valid_until: datetime | None = None
    decay_factor: float = 1.0
    expired: bool = False
    channels: tuple[str, ...] = ()
    channel_strengths: dict[str, float] | None = None
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _json(asdict(self))


@dataclass(frozen=True)
class PolicyStatement:
    statement_id: str
    speaker: str | None = None
    institution: str | None = None
    speaker_role: str | None = None
    authority_score: float | None = None
    topic: str | None = None
    policy_direction: str | None = None
    hawkish_dovish: float | None = None
    tightening_easing: float | None = None
    new_information_score: float | None = None
    repetition_score: float | None = None
    credibility: float | None = None
    source_confidence: float = 0.0
    expected_value: float | None = None
    actual_value: float | None = None
    numeric_surprise: float | None = None
    normalization_method: str | None = None
    numeric_confidence: float | None = None
    semantic_surprise: float | None = None
    baseline_direction: float | None = None
    market_relevance: float | None = None
    published_at: datetime | None = None
    freshness_seconds: float | None = None
    half_life_minutes: int | None = None
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _json(asdict(self))


@dataclass(frozen=True)
class MacroSurpriseImpact:
    """Numeric macro release mapped to causal factors (not a statement)."""
    event_id: str
    event_type: str
    topic: str
    raw_surprise: float | None = None
    normalized_surprise: float | None = None
    numeric_confidence: float = 0.0
    normalization_method: str | None = None
    inflation_contribution: float = 0.0
    growth_contribution: float = 0.0
    rates_contribution: float = 0.0
    oil_contribution: float = 0.0
    effective_strength: float = 0.0
    published_at: datetime | None = None
    verified: bool = False
    source: str | None = None
    half_life_minutes: int | None = None
    decay_factor: float = 1.0
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _json(asdict(self))


@dataclass(frozen=True)
class WorldStateSnapshot:
    generated_at: datetime
    liquidity: float | None = None
    usd_pressure: float | None = None
    rates_pressure: float | None = None
    real_yield_pressure: float | None = None
    inflation_pressure: float | None = None
    growth_pressure: float | None = None
    risk_aversion: float | None = None
    credit_stress: float | None = None
    energy_supply_risk: float | None = None
    shipping_risk: float | None = None
    sanctions_pressure: float | None = None
    trade_risk: float | None = None
    oil_pressure: float | None = None
    geopolitical_risk: float | None = None
    crypto_liquidity: float | None = None
    equity_risk_appetite: float | None = None
    usd_flow: float | None = None
    treasury_flow: float | None = None
    equity_flow: float | None = None
    credit_flow: float | None = None
    metals_flow: float | None = None
    energy_flow: float | None = None
    crypto_flow: float | None = None
    defensive_flow: float | None = None
    macro_coverage: float = 0.0
    flow_coverage: float = 0.0
    geopolitical_coverage: float = 0.0
    statement_coverage: float = 0.0
    positioning_coverage: float = 0.0
    global_flow_regime: str = "UNKNOWN"
    confidence: float = 0.0
    data_quality: str = "UNAVAILABLE"
    coverage: float = 0.0
    evidence: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    geopolitical_events: tuple[GeopoliticalEvent, ...] = ()
    statements: tuple[PolicyStatement, ...] = ()
    macro_surprises: tuple[MacroSurpriseImpact, ...] = ()
    macro_surprise_inflation: float | None = None
    macro_surprise_growth: float | None = None
    macro_surprise_rates: float | None = None
    macro_surprise_oil: float | None = None
    positioning: dict[str, dict[str, Any]] | None = None
    macro_sources: dict[str, dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return _json(asdict(self))
