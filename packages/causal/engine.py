"""Pure deterministic propagation from world-state factors to asset evidence."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from packages.causal.model import AssetImpact, CausalEdge, CausalShadow
from packages.data.registry import assets as asset_registry
from packages.data.registry.loader import load_thresholds
from packages.decision.conflict_resolver import ConflictInputs
from packages.decision.conflict_resolver import resolve as resolve_conflict
from packages.world_state.model import WorldStateSnapshot

_EDGE_DEFAULTS: tuple[tuple[str, str, int, str, float], ...] = (
    ("shipping_risk", "energy_supply_risk", 1, "shipping_to_energy", 0.80),
    ("energy_supply_risk", "oil_pressure", 1, "energy_to_oil", 0.80),
    ("oil_pressure", "inflation_pressure", 1, "oil_to_inflation", 0.55),
    ("inflation_pressure", "rates_pressure", 1, "inflation_to_rates", 0.50),
    ("rates_pressure", "real_yield_pressure", 1, "rates_to_real_yield", 0.65),
    ("real_yield_pressure", "gold_pressure", -1, "real_yield_to_gold", 0.65),
    ("rates_pressure", "liquidity", -1, "rates_to_liquidity", 0.55),
    ("usd_pressure", "liquidity", -1, "usd_to_liquidity", 0.55),
    ("liquidity", "crypto_liquidity", 1, "liquidity_to_crypto", 0.65),
    ("risk_aversion", "credit_stress", 1, "risk_to_credit", 0.60),
    ("credit_stress", "equity_pressure", -1, "credit_to_equity", 0.65),
    ("usd_pressure", "gold_pressure", -1, "usd_to_gold", 0.45),
)


def _clamp(value: float) -> float:
    return round(max(-1.0, min(1.0, value)), 4)


def _value(state: WorldStateSnapshot, name: str) -> float | None:
    return getattr(state, name, None)


def _edge_specs(config: dict) -> tuple[tuple[str, str, int, str, float], ...]:
    graph = config.get("graph") or {}
    return tuple((source, target, sign, key, float(graph.get(key, default))) for source, target, sign, key, default in _EDGE_DEFAULTS)


def _propagate(state: WorldStateSnapshot, config: dict) -> tuple[dict[str, float], tuple[CausalEdge, ...]]:
    factors: dict[str, float] = {}
    for name in (
        "liquidity", "usd_pressure", "rates_pressure", "real_yield_pressure",
        "inflation_pressure", "growth_pressure", "risk_aversion", "credit_stress",
        "energy_supply_risk", "shipping_risk", "geopolitical_risk", "crypto_liquidity",
        "equity_risk_appetite", "shipping_risk", "oil_pressure", "gold_pressure",
    ):
        value = _value(state, name)
        if value is not None:
            factors[name] = float(value)
    # One bounded forward pass keeps the graph auditable and avoids recursive
    # feedback becoming an unbounded score multiplier.
    initial = set(factors)
    edges: list[CausalEdge] = []
    for source, target, sign, _key, strength in _edge_specs(config):
        source_value = factors.get(source)
        if source_value is None:
            continue
        contribution = source_value * sign * strength
        # Direct measured inputs remain authoritative. Derived nodes are added
        # once, preventing the same source from being counted twice.
        if target not in initial:
            factors[target] = _clamp(factors.get(target, 0.0) + contribution)
        edges.append(CausalEdge(
            source=source, target=target, sign=sign,
            base_strength=strength, confidence=state.confidence,
            source_value=source_value, contribution=round(contribution, 4),
            effective_strength=round(strength * state.confidence, 4),
            evidence=(f"{source}={source_value:.3f}", f"contribution={contribution:.3f}"),
        ))
    return factors, tuple(edges)


def _technical_timing(technicals: Mapping[str, object] | None, symbol: str) -> tuple[float | None, str]:
    """Summarise technical timing without changing the causal thesis.

    The technical layer is deliberately read-only here: world/causal direction
    remains independent, while the result only describes confirmation,
    conflict, or a wait condition for UI shadow comparison.
    """
    if not technicals:
        return None, "UNAVAILABLE"
    raw = technicals.get(symbol)
    if raw is None:
        return None, "UNAVAILABLE"
    by_tf = raw if isinstance(raw, Mapping) else {"1d": raw}
    values: list[float] = []
    for timeframe in ("4h", "1d", "1h", "15m"):
        item = by_tf.get(timeframe)
        score = getattr(item, "direction_score", None)
        if score is None and isinstance(item, Mapping):
            score = item.get("direction_score")
        if score is None:
            continue
        try:
            values.append(_clamp((float(score) - 50.0) / 50.0))
        except (TypeError, ValueError):
            continue
    if not values:
        return None, "UNAVAILABLE"
    confirmation = round(sum(values) / len(values), 4)
    directional = [value for value in values if abs(value) >= 0.15]
    if not directional or abs(confirmation) < 0.15:
        return confirmation, "WAIT"
    if any(value > 0 for value in directional) and any(value < 0 for value in directional):
        return confirmation, "CONFLICT"
    return confirmation, "CONFIRMED"


def _impact(
    symbol: str,
    factors: dict[str, float],
    state: WorldStateSnapshot,
    technicals: Mapping[str, object] | None = None,
) -> AssetImpact:
    asset = asset_registry.get(symbol)
    asset_class = asset.asset_class if asset is not None else "other"
    exposure_cfg = (load_thresholds().get("causal_world") or {}).get("asset_exposures") or {}
    exposures = exposure_cfg.get(asset_class) or exposure_cfg.get("other") or {
        "liquidity": 0.7, "risk_aversion": -0.5, "usd_pressure": -0.3,
    }
    terms = [(key, factors[key] * float(weight)) for key, weight in exposures.items() if key in factors]
    horizon = "1h-4h" if asset_class == "crypto" else "1h-1d" if asset_class == "energy" else "4h-1d"
    score = _clamp(sum(value for _, value in terms)) if terms else None
    positive = tuple(key for key, value in terms if value > 0.05)
    negative = tuple(key for key, value in terms if value < -0.05)
    missing = tuple(key for key in exposures if key not in factors)
    positioning = (state.positioning or {}).get(symbol) or {}
    positioning_state = str(positioning.get("state") or "NEUTRAL")
    positioning_adjustment = 0.0
    if positioning_state == "CROWDED_LONG" and score is not None and score > 0:
        positioning_adjustment = -0.15
    elif positioning_state == "CROWDED_SHORT" and score is not None and score < 0:
        positioning_adjustment = 0.15
    vol = positioning.get("volatility") or {}
    volatility_regime = str(vol.get("regime") or "UNAVAILABLE")
    if volatility_regime in {"EXTREME", "ELEVATED"}:
        positioning_adjustment -= 0.10
    adjusted_score = _clamp((score or 0.0) + positioning_adjustment) if score is not None else None
    conflicts = ("world factors conflict",) if positive and negative else ()
    technical_confirmation, timing_status = _technical_timing(technicals, symbol)
    if technical_confirmation is None:
        confluence = "INSUFFICIENT_EVIDENCE"
    elif adjusted_score is None or abs(adjusted_score) < 0.15:
        confluence = "MIXED"
    elif technical_confirmation * adjusted_score > 0.03:
        confluence = "STRONG_CONFLUENCE" if timing_status == "CONFIRMED" else "MODERATE_CONFLUENCE"
    elif technical_confirmation * adjusted_score < -0.03:
        confluence = "CONFLICT"
    else:
        confluence = "MIXED"
    coverage = len(terms) / max(1, len(exposures))
    confidence = state.confidence * min(1.0, coverage) * (0.75 if positioning_state == "UNAVAILABLE" else 1.0)
    return AssetImpact(
        symbol=symbol,
        direction_score=adjusted_score,
        confidence=round(max(0.0, min(1.0, confidence)), 4),
        time_horizon=horizon,
        drivers=tuple(key for key, _ in terms),
        positive_drivers=positive,
        negative_drivers=negative,
        world_state_contribution=adjusted_score,
        flow_contribution=_clamp(sum(factors[key] * float(exposures[key]) for key in exposures if key in {"liquidity", "usd_pressure", "crypto_liquidity", "equity_risk_appetite"} and key in factors)) if terms else None,
        macro_contribution=_clamp(sum(factors[key] * float(exposures[key]) for key in exposures if key in {"rates_pressure", "real_yield_pressure", "inflation_pressure", "growth_pressure"} and key in factors)) if terms else None,
        geopolitical_contribution=_clamp(sum(factors[key] * float(exposures[key]) for key in exposures if key in {"risk_aversion", "energy_supply_risk", "shipping_risk", "credit_stress"} and key in factors)) if terms else None,
        positioning_contribution=positioning_adjustment,
        technical_confirmation=technical_confirmation,
        timing_status=timing_status,
        positioning_state=positioning_state,
        volatility_regime=volatility_regime,
        confluence_state=confluence,
        missing_evidence=missing,
        conflicts=conflicts,
    )


def build_shadow(
    state: WorldStateSnapshot,
    symbols: Iterable[str],
    *,
    enabled: bool | None = None,
    decision_apply: bool | None = None,
    technicals: Mapping[str, object] | None = None,
    legacy_scores: Mapping[str, Mapping[str, object]] | None = None,
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
    factors, edges = _propagate(state, config)
    impacts = tuple(_impact(symbol, factors, state, technicals) for symbol in symbols)
    consensus: list[dict[str, object]] = []
    conflict_shadow: list[dict[str, object]] = []
    for impact in impacts:
        if impact.direction_score is None or impact.confidence < 0.25:
            direction = "ABSTAIN"
        elif impact.direction_score > 0.15:
            direction = "bullish"
        elif impact.direction_score < -0.15:
            direction = "bearish"
        else:
            direction = "neutral"
        timing = impact.technical_confirmation
        shadow_score = 50.0 + (impact.direction_score or 0.0) * 50.0
        if timing is not None:
            shadow_score += timing * 10.0
        shadow_score = max(0.0, min(100.0, round(shadow_score, 2)))
        legacy = (legacy_scores or {}).get(impact.symbol) or {}
        consensus.append({
            "symbol": impact.symbol,
            "timeframe": "shadow",
            "legacy_score": legacy.get("score"),
            "legacy_direction": legacy.get("direction"),
            "world_score": round(50.0 + (impact.world_state_contribution or 0.0) * 50.0, 2) if impact.world_state_contribution is not None else None,
            "causal_score": round(50.0 + (impact.direction_score or 0.0) * 50.0, 2) if impact.direction_score is not None else None,
            "technical_confirmation": impact.technical_confirmation,
            "positioning_adjustment": impact.positioning_contribution,
            "confluence_state": impact.confluence_state,
            "final_shadow_score": shadow_score if direction != "ABSTAIN" else None,
            "final_shadow_direction": direction,
            "confidence": impact.confidence,
            "coverage": round(1.0 - len(impact.missing_evidence) / max(1, len(impact.drivers) + len(impact.missing_evidence)), 4),
            "warnings": list(impact.conflicts) + list(impact.missing_evidence),
            "divergence_reason": "legacy_vs_causal" if legacy.get("direction") and legacy.get("direction") != direction else None,
        })
        resolution = resolve_conflict(ConflictInputs(
            dqs_status="OK" if state.data_quality == "OK" else "DEGRADED",
            risk_gate_action="HOLD",
            trigger_confirmed=impact.timing_status == "CONFIRMED",
            sl_tp_rr_valid=True,
            setup_type="SETUP" if direction != "ABSTAIN" else "NO_TRADE",
            historical_edge_strong_negative=False,
            size_multiplier=1.0,
            alignment_status="CONFLICTED" if impact.confluence_state == "CONFLICT" else "ALIGNED",
        ))
        conflict_shadow.append({
            "symbol": impact.symbol,
            "final_action": resolution.final_action,
            "blocked_by": resolution.blocked_by,
            "path": resolution.conflict_resolution_path,
        })
    warnings = list(state.missing_inputs)
    if state.confidence < 0.5:
        warnings.append("low_world_state_confidence")
    return CausalShadow(
        generated_at=datetime.now(UTC),
        enabled=True,
        decision_apply=apply,
        world_state=state.to_dict(),
        edges=edges,
        impacts=impacts,
        causal_consensus=tuple(consensus),
        conflict_shadow=tuple(conflict_shadow),
        warnings=tuple(dict.fromkeys(warnings)),
    )
