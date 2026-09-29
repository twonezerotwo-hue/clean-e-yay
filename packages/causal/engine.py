"""Pure deterministic propagation from world-state factors to asset evidence."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from packages.causal.model import AssetImpact, CausalEdge, CausalShadow
from packages.data.registry.loader import load_thresholds
from packages.world_state.model import WorldStateSnapshot

_EDGES: tuple[tuple[str, str, int, float], ...] = (
    ("energy_supply_risk", "inflation_pressure", 1, 0.55),
    ("inflation_pressure", "rates_pressure", 1, 0.50),
    ("rates_pressure", "real_yield_pressure", 1, 0.65),
    ("real_yield_pressure", "gold_pressure", -1, 0.65),
    ("rates_pressure", "liquidity", -1, 0.55),
    ("liquidity", "crypto_liquidity", 1, 0.65),
    ("risk_aversion", "credit_stress", 1, 0.60),
    ("credit_stress", "equity_pressure", -1, 0.65),
    ("usd_pressure", "gold_pressure", -1, 0.45),
    ("usd_pressure", "crypto_liquidity", -1, 0.55),
)


def _clamp(value: float) -> float:
    return round(max(-1.0, min(1.0, value)), 4)


def _value(state: WorldStateSnapshot, name: str) -> float | None:
    return getattr(state, name, None)


def _edges(state: WorldStateSnapshot) -> tuple[CausalEdge, ...]:
    edges: list[CausalEdge] = []
    for source, target, sign, strength in _EDGES:
        if _value(state, source) is None:
            continue
        edges.append(
            CausalEdge(
                source=source,
                target=target,
                sign=sign,
                base_strength=strength,
                confidence=state.confidence,
                evidence=(f"{source}={_value(state, source):.3f}",),
            )
        )
    return tuple(edges)


def _propagate(state: WorldStateSnapshot) -> dict[str, float]:
    factors: dict[str, float] = {}
    for name in (
        "liquidity", "usd_pressure", "rates_pressure", "real_yield_pressure",
        "inflation_pressure", "growth_pressure", "risk_aversion", "credit_stress",
        "energy_supply_risk", "shipping_risk", "geopolitical_risk", "crypto_liquidity",
        "equity_risk_appetite",
    ):
        value = _value(state, name)
        if value is not None:
            factors[name] = float(value)
    # One bounded forward pass keeps the graph auditable and avoids recursive
    # feedback becoming an unbounded score multiplier.
    for source, target, sign, strength in _EDGES:
        source_value = factors.get(source)
        if source_value is None:
            continue
        contribution = source_value * sign * strength
        factors[target] = _clamp(factors.get(target, 0.0) + contribution)
    return factors


def _impact(symbol: str, factors: dict[str, float], state: WorldStateSnapshot) -> AssetImpact:
    terms: list[tuple[str, float]] = []
    if symbol in {"XAUUSD", "XAGUSD"}:
        for key, weight in (("gold_pressure", 1.0), ("risk_aversion", 0.6), ("usd_pressure", -0.4)):
            if key in factors:
                terms.append((key, factors[key] * weight))
        horizon = "4h-1d"
    elif symbol in {"BTCUSD", "ETHUSD"}:
        for key, weight in (("crypto_liquidity", 1.0), ("usd_pressure", -0.5), ("risk_aversion", -0.5)):
            if key in factors:
                terms.append((key, factors[key] * weight))
        horizon = "1h-4h"
    elif symbol in {"BRENT", "OIL"}:
        for key, weight in (("energy_supply_risk", 1.0), ("shipping_risk", 0.6), ("growth_pressure", -0.3)):
            if key in factors:
                terms.append((key, factors[key] * weight))
        horizon = "1h-1d"
    elif symbol in {"SP500", "NVDA", "TEM", "CLNN"}:
        for key, weight in (("equity_risk_appetite", 1.0), ("credit_stress", -0.7), ("risk_aversion", -0.5)):
            if key in factors:
                terms.append((key, factors[key] * weight))
        horizon = "4h-1d"
    else:
        for key, weight in (("liquidity", 0.7), ("risk_aversion", -0.5), ("usd_pressure", -0.3)):
            if key in factors:
                terms.append((key, factors[key] * weight))
        horizon = "4h-1d"
    score = _clamp(sum(value for _, value in terms)) if terms else None
    positive = tuple(key for key, value in terms if value > 0.05)
    negative = tuple(key for key, value in terms if value < -0.05)
    missing = tuple(key for key in ("liquidity", "risk_aversion", "usd_pressure") if key not in factors)
    conflicts = ("world factors conflict",) if positive and negative else ()
    return AssetImpact(
        symbol=symbol,
        direction_score=score,
        confidence=round(state.confidence * min(1.0, len(terms) / 3.0), 4),
        time_horizon=horizon,
        drivers=tuple(key for key, _ in terms),
        positive_drivers=positive,
        negative_drivers=negative,
        world_state_contribution=score,
        flow_contribution=factors.get("liquidity"),
        geopolitical_contribution=factors.get("geopolitical_risk"),
        missing_evidence=missing,
        conflicts=conflicts,
    )


def build_shadow(
    state: WorldStateSnapshot,
    symbols: Iterable[str],
    *,
    enabled: bool | None = None,
    decision_apply: bool | None = None,
) -> CausalShadow:
    config = load_thresholds().get("causal_world") or {}
    active = (
        bool(config.get("enabled", True) and config.get("causal_graph_enabled", True))
        if enabled is None
        else bool(enabled)
    )
    apply = bool(config.get("decision_apply", False)) if decision_apply is None else bool(decision_apply)
    if not active:
        return CausalShadow(state.generated_at, False, False, state.to_dict(), warnings=("disabled",))
    factors = _propagate(state)
    impacts = tuple(_impact(symbol, factors, state) for symbol in symbols)
    warnings = list(state.missing_inputs)
    if state.confidence < 0.5:
        warnings.append("low_world_state_confidence")
    return CausalShadow(
        generated_at=datetime.now(UTC),
        enabled=True,
        decision_apply=apply,
        world_state=state.to_dict(),
        edges=_edges(state),
        impacts=impacts,
        warnings=tuple(dict.fromkeys(warnings)),
    )
