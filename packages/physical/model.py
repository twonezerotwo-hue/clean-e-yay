"""Serializable physical supply-chain models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CommodityObservation:
    """As-of measured supply-chain inputs; no field is silently defaulted."""

    commodity_id: str
    baseline_supply: float | None = None
    at_risk_supply: float | None = None
    alternative_supply: float | None = None
    inventory_release: float | None = None
    spare_capacity: float | None = None
    demand: float | None = None
    unit: str = "unknown"
    as_of: str | None = None
    source: str | None = None
    verified: bool = False


@dataclass(frozen=True)
class SupplyChainAssessment:
    commodity_id: str
    commodity_name: str
    status: str
    unit: str
    baseline_supply: float | None = None
    at_risk_supply: float | None = None
    alternative_supply: float | None = None
    inventory_release: float | None = None
    spare_capacity: float | None = None
    demand: float | None = None
    gross_supply_shock: float | None = None
    effective_supply_shock: float | None = None
    effective_supply_shock_pct: float | None = None
    mitigation_coverage: float | None = None
    affected_assets: tuple[str, ...] = ()
    factor_channels: tuple[str, ...] = ()
    topology_entities: tuple[str, ...] = ()
    observation_as_of: str | None = None
    observation_source: str | None = None
    missing_inputs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    method: str = "physical_supply_balance_shadow_v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["CommodityObservation", "SupplyChainAssessment"]
