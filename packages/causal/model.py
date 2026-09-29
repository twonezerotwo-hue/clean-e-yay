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
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _json(asdict(self))


@dataclass(frozen=True)
class AssetImpact:
    symbol: str
    direction_score: float | None
    confidence: float
    time_horizon: str
    drivers: tuple[str, ...] = ()
    positive_drivers: tuple[str, ...] = ()
    negative_drivers: tuple[str, ...] = ()
    world_state_contribution: float | None = None
    flow_contribution: float | None = None
    macro_contribution: float | None = None
    geopolitical_contribution: float | None = None
    statement_contribution: float | None = None
    positioning_contribution: float | None = None
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
    impacts: tuple[AssetImpact, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _json(asdict(self))
