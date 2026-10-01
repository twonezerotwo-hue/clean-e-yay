"""Bounded physical supply-chain arithmetic.

The engine separates static topology from current measurements.  It can say
which commodity is connected to an event immediately, but it only calculates a
net supply shock when the required as-of quantities are supplied by a verified
provider.  It never opens a trade or changes a causal factor.
"""
from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from packages.physical.model import CommodityObservation, SupplyChainAssessment

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "physical_commodities_v1.0.yaml"


def _path() -> Path:
    raw = os.environ.get("PHYSICAL_COMMODITIES_CONFIG_PATH", str(_DEFAULT_PATH))
    return Path(raw) if Path(raw).is_absolute() else Path(__file__).resolve().parents[2] / raw


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 and result == result and abs(result) != float("inf") else None


def _config() -> tuple[str, list[dict[str, Any]]]:
    try:
        raw = yaml.safe_load(_path().read_text(encoding="utf-8")) or {}
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return "unavailable", []
    rows: list[dict[str, Any]] = []
    for item in raw.get("commodities") or ():
        if not isinstance(item, Mapping) or not item.get("id"):
            continue
        rows.append({
            "id": str(item["id"]),
            "name": str(item.get("name") or item["id"]),
            "unit": str(item.get("unit") or "unknown"),
            "asset_symbols": tuple(str(x) for x in item.get("asset_symbols") or ()),
            "factor_channels": tuple(str(x) for x in item.get("factor_channels") or ()),
        })
    return str(raw.get("version") or "unknown"), rows


def _observation(value: Any, commodity_id: str, unit: str) -> CommodityObservation | None:
    if isinstance(value, CommodityObservation):
        return value
    if not isinstance(value, Mapping):
        return None
    return CommodityObservation(
        commodity_id=commodity_id,
        baseline_supply=_number(value.get("baseline_supply")),
        at_risk_supply=_number(value.get("at_risk_supply")),
        alternative_supply=_number(value.get("alternative_supply")),
        inventory_release=_number(value.get("inventory_release")),
        spare_capacity=_number(value.get("spare_capacity")),
        demand=_number(value.get("demand")),
        unit=str(value.get("unit") or unit),
        as_of=str(value.get("as_of")) if value.get("as_of") else None,
        source=str(value.get("source")) if value.get("source") else None,
        verified=bool(value.get("verified", False)),
    )


def assess_commodity(
    commodity: Mapping[str, Any],
    observation: CommodityObservation | Mapping[str, Any] | None = None,
    *,
    topology_entities: Iterable[str] = (),
) -> SupplyChainAssessment:
    """Compute a conservative balance from one commodity definition."""
    commodity_id = str(commodity.get("id") or "unknown")
    unit = str(commodity.get("unit") or "unknown")
    obs = _observation(observation, commodity_id, unit)
    missing: list[str] = []
    warnings: list[str] = []
    if obs is None:
        missing.extend(("baseline_supply", "at_risk_supply", "verified_observation"))
        warnings.append("physical_observation_unavailable")
    else:
        if not obs.verified:
            warnings.append("observation_not_verified")
        for name in ("baseline_supply", "at_risk_supply", "alternative_supply", "inventory_release", "spare_capacity"):
            if getattr(obs, name) is None:
                missing.append(name)
    baseline = obs.baseline_supply if obs else None
    at_risk = obs.at_risk_supply if obs else None
    alternative = obs.alternative_supply if obs else None
    inventory = obs.inventory_release if obs else None
    spare = obs.spare_capacity if obs else None
    gross = at_risk if at_risk is not None else None
    mitigation_total = None if any(value is None for value in (alternative, inventory, spare)) else alternative + inventory + spare
    effective = max(0.0, gross - mitigation_total) if gross is not None and mitigation_total is not None else None
    coverage = min(1.0, mitigation_total / gross) if mitigation_total is not None and gross and gross > 0 else None
    shock_pct = effective / baseline if effective is not None and baseline and baseline > 0 else None
    if obs is not None and not obs.verified:
        status = "UNVERIFIED"
    elif effective is not None and baseline is not None:
        status = "OK"
    elif obs is not None:
        status = "PARTIAL"
    else:
        status = "INSUFFICIENT_DATA"
    return SupplyChainAssessment(
        commodity_id=commodity_id,
        commodity_name=str(commodity.get("name") or commodity_id),
        status=status,
        unit=obs.unit if obs else unit,
        baseline_supply=baseline,
        at_risk_supply=at_risk,
        alternative_supply=alternative,
        inventory_release=inventory,
        spare_capacity=spare,
        demand=obs.demand if obs else None,
        gross_supply_shock=gross,
        effective_supply_shock=effective,
        effective_supply_shock_pct=shock_pct,
        mitigation_coverage=coverage,
        affected_assets=tuple(sorted(str(x) for x in commodity.get("asset_symbols") or ())),
        factor_channels=tuple(sorted(str(x) for x in commodity.get("factor_channels") or ())),
        topology_entities=tuple(sorted(set(str(x) for x in topology_entities))),
        observation_as_of=obs.as_of if obs else None,
        observation_source=obs.source if obs else None,
        missing_inputs=tuple(dict.fromkeys(missing)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def build_assessments(
    graph_context: Mapping[str, Any] | None = None,
    observations: Mapping[str, CommodityObservation | Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build assessments only for commodities connected to the graph context."""
    version, commodities = _config()
    graph_ids = set(str(x) for x in (graph_context or {}).get("entity_ids") or ())
    connected = {item["id"] for item in commodities if not graph_ids or item["id"] in graph_ids}
    rows: dict[str, dict[str, Any]] = {}
    for commodity in commodities:
        if commodity["id"] not in connected:
            continue
        obs = (observations or {}).get(commodity["id"])
        rows[commodity["id"]] = assess_commodity(
            commodity,
            obs,
            topology_entities=graph_ids,
        ).to_dict()
    status = "OK" if any(row.get("status") == "OK" for row in rows.values()) else "INSUFFICIENT_DATA" if rows else "NO_MATCH"
    return {
        "version": version,
        "status": status,
        "assessments": rows,
        "graph_entities": sorted(graph_ids),
        "warnings": ["physical_observation_required"] if rows and status != "OK" else [],
    }


__all__ = ["assess_commodity", "build_assessments"]
