"""Build world-state evidence from the existing market snapshot.

This module deliberately does not fetch data, call an LLM, or emit a trade
decision. It reuses the snapshot's verified news/catalyst and rotation outputs.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.registry.loader import load_thresholds
from packages.world_state.model import GeopoliticalEvent, PolicyStatement, WorldStateSnapshot


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return round(max(low, min(high, value)), 4)


def _flow(rotation: Any, symbol: str) -> float | None:
    if getattr(rotation, "status", "UNAVAILABLE") == "UNAVAILABLE":
        return None
    value = (getattr(rotation, "per_symbol", None) or {}).get(symbol)
    if value is None:
        return None
    return _clamp((float(value) - 50.0) / 50.0)


def _mean(values: list[float | None]) -> float | None:
    present = [float(v) for v in values if v is not None]
    return _clamp(sum(present) / len(present)) if present else None


def _headline_text(headline: Any) -> str:
    return " ".join(str(getattr(headline, key, "") or "") for key in ("title", "title_tr"))


def _geo_events(snapshot: MarketSnapshot, now: datetime) -> tuple[GeopoliticalEvent, ...]:
    by_id = {getattr(item, "headline_id", ""): item for item in snapshot.catalyst_impacts}
    events: list[GeopoliticalEvent] = []
    seen_stories: set[str] = set()
    for headline in snapshot.headlines:
        impact = by_id.get(getattr(headline, "id", ""))
        event_type = getattr(impact, "event_type", "unknown") if impact else "unknown"
        if not str(event_type).startswith("geopolitical_"):
            continue
        title = _headline_text(headline)
        lower = title.lower()
        story_key = re.sub(r"\W+", " ", lower).strip()
        if story_key in seen_stories:
            continue
        seen_stories.add(story_key)
        threat_only = any(word in lower for word in ("threat", "could", "may", "might", "iddia"))
        confirmed = bool(getattr(headline, "verified", False)) and not threat_only
        ts = getattr(headline, "ts", None)
        age = max(0.0, (now - ts).total_seconds()) if ts else None
        confidence = float(getattr(impact, "confidence", 0.0) or 0.0)
        if not getattr(headline, "verified", False):
            confidence = min(confidence, 0.2)
        severity = abs(float(getattr(impact, "surprise_level", 0.0) or 0.0)) or 0.5
        events.append(
            GeopoliticalEvent(
                event_id=str(getattr(headline, "id", "")),
                event_type=str(event_type).upper(),
                region=getattr(headline, "region", None),
                status="CONFIRMED" if confirmed else "THREAT",
                confirmed_action=confirmed,
                threat_only=threat_only,
                severity=_clamp(severity, 0.0, 1.0),
                energy_exposure=1.0 if any(w in lower for w in ("oil", "energy", "pipeline", "opec")) else 0.0,
                shipping_exposure=1.0 if any(w in lower for w in ("shipping", "port", "strait", "gemi")) else 0.0,
                commodity_exposure=1.0 if any(w in lower for w in ("commodity", "oil", "gold", "petrol")) else 0.0,
                source_confidence=round(confidence, 4),
                confirmation_count=1 if confirmed else 0,
                source_diversity=1 if getattr(headline, "source", None) else 0,
                published_at=ts,
                freshness_seconds=age,
                half_life_minutes=getattr(impact, "expected_half_life_minutes", None),
                valid_until=getattr(impact, "valid_until", None),
                evidence=(title[:240],),
            )
        )
    return tuple(events)


def _statements(snapshot: MarketSnapshot, now: datetime) -> tuple[PolicyStatement, ...]:
    result: list[PolicyStatement] = []
    central_words = ("fed", "fomc", "ecb", "boj", "bank of england", "powell", "lagarde")
    for headline in snapshot.headlines:
        text = _headline_text(headline)
        lower = text.lower()
        if not any(word in lower for word in central_words):
            continue
        hawkish = any(word in lower for word in ("hawkish", "higher for longer", "rate hike", "tighten"))
        dovish = any(word in lower for word in ("dovish", "rate cut", "easing", "accommodative"))
        ts = getattr(headline, "ts", None)
        result.append(
            PolicyStatement(
                statement_id=str(getattr(headline, "id", "")),
                institution="central_bank",
                speaker_role="unknown",
                authority_score=0.5,
                topic="monetary_policy",
                policy_direction="tightening" if hawkish else "easing" if dovish else "unknown",
                hawkish_dovish=1.0 if hawkish else -1.0 if dovish else None,
                tightening_easing=1.0 if hawkish else -1.0 if dovish else None,
                new_information_score=0.5 if (hawkish or dovish) else None,
                credibility=0.6 if getattr(headline, "verified", False) else 0.1,
                source_confidence=0.7 if getattr(headline, "verified", False) else 0.1,
                semantic_surprise=0.25 if (hawkish or dovish) else None,
                market_relevance=0.7,
                published_at=ts,
                freshness_seconds=max(0.0, (now - ts).total_seconds()) if ts else None,
                half_life_minutes=240,
                evidence=(text[:240],),
            )
        )
    return tuple(result)


def normalized_surprise(actual: float | None, expected: float | None, historical_volatility: float | None) -> float | None:
    """Return a bounded numeric surprise; missing inputs remain unavailable."""
    if actual is None or expected is None or historical_volatility is None or historical_volatility <= 0:
        return None
    return _clamp((float(actual) - float(expected)) / float(historical_volatility))


def build(snapshot: MarketSnapshot, *, now: datetime | None = None) -> WorldStateSnapshot:
    """Create the additive world-state view from one existing snapshot."""
    current = (now or datetime.now(UTC)).astimezone(UTC)
    config = load_thresholds().get("causal_world") or {}
    if not config.get("enabled", True) or not config.get("world_state_enabled", True):
        return WorldStateSnapshot(
            generated_at=current,
            data_quality="DISABLED",
            missing_inputs=("world_state_disabled",),
        )
    rotation = snapshot.rotation
    usd = _flow(rotation, "DXY")
    equity = _flow(rotation, "SP500")
    crypto = _mean([_flow(rotation, "BTCUSD"), _flow(rotation, "ETHUSD")])
    hyg = _flow(rotation, "HYG")
    lqd = _flow(rotation, "LQD")
    credit_stress = _clamp((lqd - hyg) / 2.0) if hyg is not None and lqd is not None else None
    risk_aversion = _mean([-equity if equity is not None else None, credit_stress])
    liquidity = _mean([crypto, equity, -usd if usd is not None else None])
    events = _geo_events(snapshot, current) if config.get("geopolitical_enabled", True) else ()
    statements = _statements(snapshot, current) if config.get("statements_enabled", True) else ()
    geo = _mean([e.severity * e.source_confidence for e in events if e.confirmed_action])
    energy = _mean([e.energy_exposure * (e.severity or 0.0) * e.source_confidence for e in events])
    shipping = _mean([e.shipping_exposure * (e.severity or 0.0) * e.source_confidence for e in events])
    available = [usd, equity, crypto, credit_stress, risk_aversion, liquidity, geo, energy, shipping]
    coverage = round(sum(v is not None for v in available) / len(available), 4)
    flow_values = [v for v in (liquidity, equity, crypto) if v is not None]
    flow_mean = sum(flow_values) / len(flow_values) if flow_values else None
    if flow_mean is None:
        flow_regime = "UNKNOWN"
    elif flow_mean > 0.35:
        flow_regime = "LIQUIDITY_EXPANSION"
    elif flow_mean < -0.35 and (credit_stress or 0.0) > 0.35:
        flow_regime = "LIQUIDITY_CRISIS"
    elif flow_mean > 0.15:
        flow_regime = "RISK_ON"
    elif flow_mean < -0.15:
        flow_regime = "RISK_OFF"
    else:
        flow_regime = "NEUTRAL"
    quality_score = float(getattr(snapshot.quality, "score", 0.0) or 0.0) / 100.0
    confidence = round(max(0.0, min(1.0, quality_score * (0.5 + coverage / 2.0))), 4)
    missing = tuple(name for name, value in {
        "DXY": usd, "SP500": equity, "crypto": crypto,
        "credit": credit_stress, "risk_aversion": risk_aversion,
    }.items() if value is None)
    evidence = tuple((getattr(rotation, "evidence", None) or [])[:8])
    return WorldStateSnapshot(
        generated_at=current,
        liquidity=liquidity,
        usd_pressure=usd,
        risk_aversion=risk_aversion,
        credit_stress=credit_stress,
        energy_supply_risk=energy,
        shipping_risk=shipping,
        geopolitical_risk=geo,
        crypto_liquidity=crypto,
        equity_risk_appetite=equity,
        global_flow_regime=flow_regime,
        confidence=confidence,
        data_quality=str(getattr(snapshot.quality, "status", "UNAVAILABLE")),
        coverage=coverage,
        evidence=evidence,
        missing_inputs=missing,
        geopolitical_events=events,
        statements=statements,
    )
