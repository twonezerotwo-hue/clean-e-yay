"""Serializable causal graph and asset-impact models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


def _json(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json(item) for item in value]
    if isinstance(value, list):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    return value


@dataclass(frozen=True)
class CausalEdge:
    source: str
    target: str
    sign: int
    base_strength: float
    confidence: float
    source_value: float | None = None
    contribution: float | None = None
    effective_strength: float | None = None
    applied: bool = False
    target_before: float | None = None
    target_after: float | None = None
    reason: str | None = None
    evidence: tuple[str, ...] = ()
    prior_strength: float | None = None
    weight: float | None = None
    weight_source: str = "PRIOR"
    sample_n: int = 0
    regime: str | None = None
    horizon: str | None = None
    confidence_interval: tuple[float | None, float | None] | None = None

    def to_dict(self) -> dict[str, Any]:
        return _json(asdict(self))


@dataclass(frozen=True)
class AssetImpact:
    symbol: str
    direction_score: float | None
    confidence: float
    time_horizon: str
    base_thesis_score: float | None = None
    drivers: tuple[str, ...] = ()
    positive_drivers: tuple[str, ...] = ()
    negative_drivers: tuple[str, ...] = ()
    world_state_contribution: float | None = None
    flow_contribution: float | None = None
    macro_contribution: float | None = None
    macro_surprise_contribution: float | None = None
    geopolitical_contribution: float | None = None
    statement_contribution: float | None = None
    positioning_contribution: float | None = None
    positioning_multiplier: float = 1.0
    entry_quality: str = "UNAVAILABLE"
    positioning_reasons: tuple[str, ...] = ()
    technical_confirmation: float | None = None
    timing_status: str = "UNAVAILABLE"
    positioning_state: str = "UNAVAILABLE"
    volatility_regime: str = "UNAVAILABLE"
    confluence_state: str = "INSUFFICIENT_EVIDENCE"
    conflicts: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _json(asdict(self))


@dataclass(frozen=True)
class CausalShadow:
    generated_at: datetime
    enabled: bool
    decision_apply: bool
    world_state: dict[str, Any]
    edges: tuple[CausalEdge, ...] = ()
    edges_by_horizon: dict[str, tuple[CausalEdge, ...]] | None = None
    impacts: tuple[AssetImpact, ...] = ()
    causal_consensus: tuple[dict[str, Any], ...] = ()
    conflict_shadow: tuple[dict[str, Any], ...] = ()
    interactions: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _json(asdict(self))
