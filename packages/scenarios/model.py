"""Serializable scenario models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ScenarioResult:
    event_id: str
    scenario_id: str
    name: str
    probability: float
    probability_source: str
    class_name: str
    horizon: str
    affected_assets: dict[str, float]
    factor_channels: tuple[str, ...]
    invalidators: tuple[str, ...]
    evidence_used: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScenarioReport:
    version: str
    status: str
    events: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["ScenarioReport", "ScenarioResult"]
