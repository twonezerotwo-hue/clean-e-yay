"""Pure deterministic propagation from world-state factors to asset evidence."""
from __future__ import annotations

import math
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
    ("sanctions_pressure", "trade_risk", 1, "sanctions_to_trade", 0.70),
    ("trade_risk", "growth_pressure", -1, "trade_to_growth", 0.45),
    ("trade_risk", "inflation_pressure", 1, "trade_to_inflation", 0.30),
    ("sanctions_pressure", "risk_aversion", 1, "sanctions_to_risk", 0.35),
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
        "sanctions_pressure", "trade_risk",
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
        target_before = factors.get(target)
        applied = target not in initial
        if applied:
            factors[target] = _clamp(factors.get(target, 0.0) + contribution)
        target_after = factors.get(target)
        edges.append(CausalEdge(
            source=source, target=target, sign=sign,
            base_strength=strength, confidence=state.confidence,
            source_value=source_value, contribution=round(contribution, 4),
            effective_strength=round(strength * state.confidence, 4),
            applied=applied,
            target_before=target_before,
            target_after=target_after,
            reason="derived_target_updated" if applied else "direct_measurement_authoritative",
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


def _technical_tf(technicals: Mapping[str, object] | None, symbol: str, timeframe: str) -> float | None:
    raw = (technicals or {}).get(symbol)
    if raw is None:
        return None
    item = raw.get(timeframe) if isinstance(raw, Mapping) else raw if timeframe == "1d" else None
    score = item.get("direction_score") if isinstance(item, Mapping) else getattr(item, "direction_score", None)
    try:
        return _clamp((float(score) - 50.0) / 50.0) if score is not None else None
    except (TypeError, ValueError):
        return None


def _entry_timing_state(thesis: float | None, technical: float | None, positioning_reasons: tuple[str, ...] = ()) -> str:
    if thesis is None or technical is None:
        return "WAIT"
    if abs(thesis) < 0.05 or abs(technical) < 0.15:
        return "WAIT"
    if thesis * technical < -0.02:
        return "CAUTION" if positioning_reasons else "CONFLICT"
    return "CAUTION" if positioning_reasons else "CONFIRMED"


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
    positioning_reasons: list[str] = []
    if positioning_state == "CROWDED_LONG" and score is not None and score > 0:
        positioning_adjustment = -0.15
        positioning_reasons.append("crowded_long_against_bullish_thesis")
    elif positioning_state == "CROWDED_SHORT" and score is not None and score < 0:
        positioning_adjustment = 0.15
        positioning_reasons.append("crowded_short_against_bearish_thesis")
    vol = positioning.get("volatility") or {}
    volatility_regime = str(vol.get("regime") or "UNAVAILABLE")
    if volatility_regime in {"EXTREME", "ELEVATED"}:
        positioning_adjustment -= 0.10
        positioning_reasons.append(f"volatility_{volatility_regime.lower()}_caution")
    options = positioning.get("options") or {}
    options_state = str(options.get("state") or "")
    if options_state == "CALL_CROWDING" and score is not None and score > 0:
        positioning_adjustment -= 0.08
        positioning_reasons.append("call_crowding_caution")
    elif options_state == "PUT_SKEW_CAUTION":
        positioning_adjustment -= 0.05
        positioning_reasons.append("put_skew_or_put_call_caution")
    elif options_state == "RICH_VOL_OR_BACKWARDATION":
        positioning_adjustment -= 0.08
        positioning_reasons.append("rich_iv_or_term_backwardation_caution")
    squeeze_state = str(positioning.get("squeeze_state") or "").upper()
    if squeeze_state in {"HIGH", "ELEVATED"}:
        if positioning_state == "CROWDED_LONG":
            positioning_adjustment -= 0.10
            positioning_reasons.append("long_squeeze_risk")
        elif positioning_state == "CROWDED_SHORT":
            positioning_adjustment += 0.10
            positioning_reasons.append("short_squeeze_risk")
        else:
            positioning_reasons.append("squeeze_risk_unresolved")
    statement_contribution = 0.0
    statement_drivers: list[str] = []
    for statement in state.statements or ():
        direction = statement.tightening_easing
        if direction is None:
            continue
        age = statement.freshness_seconds
        half_life = statement.half_life_minutes or 240
        decay = 1.0 if age is None else math.exp(-math.log(2.0) * max(0.0, age) / (half_life * 60.0))
        surprise = abs(statement.numeric_surprise or statement.semantic_surprise or 0.25)
        contribution = float(direction) * float(statement.authority_score or 0.0) * float(statement.market_relevance or 0.0) * float(statement.source_confidence or 0.0) * max(0.0, 1.0 - float(statement.repetition_score or 0.0)) * min(1.0, surprise) * decay
        # Tightening is a rates/liquidity shock; easing is the inverse.  Asset
        # exposures decide whether the shock is beneficial or harmful.
        sensitivity = float(exposures.get("rates_pressure", 0.0)) - float(exposures.get("liquidity", 0.0))
        statement_contribution += contribution * sensitivity
        if abs(contribution) > 0.01:
            statement_drivers.append(f"statement:{statement.institution}:{'tightening' if direction > 0 else 'easing'}")
    statement_contribution = _clamp(statement_contribution)
    macro_surprise_contribution = 0.0
    macro_surprise_drivers: list[str] = []
    for surprise in state.macro_surprises or ():
        contribution = (
            surprise.inflation_contribution * float(exposures.get("inflation_pressure", 0.0))
            + surprise.growth_contribution * float(exposures.get("growth_pressure", 0.0))
            + surprise.rates_contribution * float(exposures.get("rates_pressure", 0.0))
            + surprise.oil_contribution * float(exposures.get("energy_supply_risk", exposures.get("growth_pressure", 0.0)))
        )
        macro_surprise_contribution += contribution
        if abs(contribution) > 0.005:
            macro_surprise_drivers.append(f"macro_surprise:{surprise.event_type}:{surprise.event_id}")
    macro_surprise_contribution = _clamp(macro_surprise_contribution)
    base_thesis_score = _clamp((score or 0.0) + statement_contribution) if score is not None else None
    # Positioning is a confidence/timing layer only. It must never be allowed
    # to cross or manufacture the causal thesis sign.
    adjusted_score = base_thesis_score
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
    positioning_multiplier = max(0.0, min(1.0, 1.0 - min(0.75, abs(positioning_adjustment))))
    confidence = state.confidence * min(1.0, coverage) * (0.75 if positioning_state == "UNAVAILABLE" else 1.0) * positioning_multiplier
    if positioning_reasons:
        confidence *= 0.92
    entry_quality = "CONFIRMED" if timing_status == "CONFIRMED" and not positioning_reasons else "CAUTION" if positioning_reasons else timing_status
    if squeeze_state == "HIGH" and positioning_state == "CROWDED_LONG":
        positioning_state = "LONG_SQUEEZE_RISK"
    elif squeeze_state == "HIGH" and positioning_state == "CROWDED_SHORT":
        positioning_state = "SHORT_SQUEEZE_RISK"
    elif volatility_regime in {"EXTREME", "ELEVATED"}:
        positioning_state = "VOL_STRESS"
    elif options_state != "" and options_state != "NEUTRAL":
        positioning_state = "OPTIONS_STRESS"
    return AssetImpact(
        symbol=symbol,
        direction_score=adjusted_score,
        confidence=round(max(0.0, min(1.0, confidence)), 4),
        time_horizon=horizon,
        base_thesis_score=base_thesis_score,
        drivers=tuple(key for key, _ in terms) + tuple(statement_drivers) + tuple(macro_surprise_drivers),
        positive_drivers=positive,
        negative_drivers=negative,
        world_state_contribution=adjusted_score,
        flow_contribution=_clamp(sum(factors[key] * float(exposures[key]) for key in exposures if key in {"liquidity", "usd_pressure", "crypto_liquidity", "equity_risk_appetite"} and key in factors)) if terms else None,
        macro_contribution=_clamp(sum(factors[key] * float(exposures[key]) for key in exposures if key in {"rates_pressure", "real_yield_pressure", "inflation_pressure", "growth_pressure"} and key in factors)) if terms else None,
        macro_surprise_contribution=macro_surprise_contribution,
        geopolitical_contribution=_clamp(sum(factors[key] * float(exposures[key]) for key in exposures if key in {"risk_aversion", "energy_supply_risk", "shipping_risk", "credit_stress"} and key in factors)) if terms else None,
        positioning_contribution=positioning_adjustment,
        positioning_multiplier=round(positioning_multiplier, 4),
        entry_quality=entry_quality,
        statement_contribution=statement_contribution,
        positioning_reasons=tuple(positioning_reasons),
        technical_confirmation=technical_confirmation,
        timing_status=timing_status,
        positioning_state=positioning_state,
        volatility_regime=volatility_regime,
        confluence_state=confluence,
        missing_evidence=missing,
        conflicts=conflicts,
    )


def build_event_asset_attribution(
    event: Mapping[str, object],
    symbols: Iterable[str],
) -> dict[str, object]:
    """Compute marginal asset predictions from one event's channels only.

    This is intentionally smaller than a full snapshot rebuild and is called
    by the off-tick learning worker. No global world-state prediction is copied
    into unrelated event rows.
    """
    config = load_thresholds().get("causal_world") or {}
    raw_channels = event.get("channel_strengths") or event.get("channels") or {}
    if isinstance(raw_channels, (list, tuple)):
        raw_channels = {str(channel): 1.0 for channel in raw_channels}
    channels = {str(key): float(value) for key, value in (raw_channels or {}).items() if value is not None}
    factors: dict[str, float] = {}
    for channel, value in channels.items():
        factor = {
            "shipping_risk": "shipping_risk",
            "energy_supply_risk": "energy_supply_risk",
            "trade_risk": "trade_risk",
            "sanctions_pressure": "sanctions_pressure",
            "risk_aversion": "risk_aversion",
            "inflation_pressure": "inflation_pressure",
            "growth_pressure": "growth_pressure",
            "rates_pressure": "rates_pressure",
            "oil_pressure": "oil_pressure",
            "energy_infrastructure_attack": "energy_supply_risk",
        }.get(channel)
        if factor:
            factors[factor] = _clamp(factors.get(factor, 0.0) + value)
    # Reuse the same bounded graph priors, but never inject unrelated snapshot
    # factors. Direct event channels are authoritative for this marginal pass.
    for source, target, sign, _key, strength in _edge_specs(config):
        if source in factors and target not in factors:
            factors[target] = _clamp(factors[source] * sign * strength)
    exposures_cfg = (config.get("asset_exposures") or {})
    predictions: dict[str, float] = {}
    for symbol in symbols:
        asset = asset_registry.get(symbol)
        asset_class = asset.asset_class if asset is not None else "other"
        exposures = exposures_cfg.get(asset_class) or exposures_cfg.get("other") or {}
        terms = [factors[key] * float(weight) for key, weight in exposures.items() if key in factors]
        if terms:
            predictions[symbol] = _clamp(sum(terms))
    source_confidence = float(event.get("source_confidence", event.get("numeric_confidence", 0.0)) or 0.0)
    return {
        "event_id": str(event.get("event_id") or event.get("id") or ""),
        "event_type": str(event.get("event_type") or "UNKNOWN"),
        "channels": channels,
        "asset_predictions": predictions,
        "prediction_confidence": round(max(0.0, min(1.0, source_confidence)), 4),
        "attribution_method": "event_marginal_v1",
        "evidence": tuple(f"{key}={value:.4f}" for key, value in sorted(channels.items())),
    }


def build_shadow(
    state: WorldStateSnapshot,
    symbols: Iterable[str],
    *,
    enabled: bool | None = None,
    decision_apply: bool | None = None,
    technicals: Mapping[str, object] | None = None,
    legacy_scores: Mapping[str, Mapping[str, object]] | None = None,
    conflict_inputs: Mapping[str, Mapping[str, object]] | None = None,
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
        world_thesis_score = round(50.0 + (impact.direction_score or 0.0) * 50.0, 2) if impact.direction_score is not None else None
        tf_keys = [key for key in (legacy_scores or {}) if key.startswith(f"{impact.symbol}|")]
        rows = [(str((legacy_scores or {}).get(key, {}).get("timeframe") or key.split("|", 1)[1]), (legacy_scores or {}).get(key) or {}) for key in tf_keys]
        if not rows:
            rows = [("shadow", (legacy_scores or {}).get(impact.symbol) or {})]
        for timeframe, legacy in rows:
            tf_confirmation = _technical_tf(technicals, impact.symbol, timeframe)
            entry_timing_state = _entry_timing_state(impact.direction_score, tf_confirmation, impact.positioning_reasons)
            timing_modifier = (tf_confirmation or 0.0) * 10.0
            final_shadow_score_tf = max(0.0, min(100.0, round((world_thesis_score or 50.0) + timing_modifier, 2))) if world_thesis_score is not None else None
            consensus.append({
                "symbol": impact.symbol,
                "timeframe": timeframe,
                "legacy_score": legacy.get("score"),
                "legacy_direction": legacy.get("direction"),
                "world_score": world_thesis_score,
                "world_thesis_score": world_thesis_score,
                "world_thesis_direction": direction,
                "causal_score": round(50.0 + (impact.direction_score or 0.0) * 50.0, 2) if impact.direction_score is not None else None,
                "technical_confirmation_tf": tf_confirmation,
                "technical_confirmation_mtf": impact.technical_confirmation,
                "technical_confirmation": tf_confirmation if tf_confirmation is not None else impact.technical_confirmation,
                "entry_timing_state": entry_timing_state,
                "positioning_adjustment": impact.positioning_contribution,
                "positioning_state": impact.positioning_state,
                "positioning_reasons": list(impact.positioning_reasons),
                "confluence_state": impact.confluence_state,
                "final_shadow_score_tf": final_shadow_score_tf if direction != "ABSTAIN" else None,
                "final_shadow_score": final_shadow_score_tf if direction != "ABSTAIN" else None,
                "final_shadow_direction": direction,
                "confidence": impact.confidence,
                "coverage": round(1.0 - len(impact.missing_evidence) / max(1, len(impact.drivers) + len(impact.missing_evidence)), 4),
                "warnings": list(impact.conflicts) + list(impact.missing_evidence),
                "divergence_reason": "legacy_vs_causal" if legacy.get("direction") and legacy.get("direction") != direction else None,
            })
        supplied = (conflict_inputs or {}).get(impact.symbol) or {}
        required = ("dqs_status", "risk_gate_action", "trigger_confirmed", "trade_economics_valid", "setup_type", "historical_edge_strong_negative", "size_multiplier", "alignment_status")
        missing_context = [key for key in required if key not in supplied or supplied[key] is None]
        if missing_context:
            # No resolver call is made with fabricated HOLD/True/size values.
            # UNAVAILABLE is explicit and cannot be mistaken for a trade state.
            conflict_shadow.append({"symbol": impact.symbol, "final_action": "UNAVAILABLE", "blocked_by": ["inputs_unavailable"], "path": [], "inputs_unavailable": missing_context})
        else:
            resolver_payload = {key: supplied[key] for key in required if key != "trade_economics_valid"}
            resolver_payload["sl_tp_rr_valid"] = supplied["trade_economics_valid"]
            resolution = resolve_conflict(ConflictInputs(**resolver_payload))
            conflict_shadow.append({"symbol": impact.symbol, "final_action": resolution.final_action, "blocked_by": resolution.blocked_by, "path": resolution.conflict_resolution_path, "inputs_used": list(required)})
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
