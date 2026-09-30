"""Build world-state evidence from the existing market snapshot.

This module deliberately does not fetch data, call an LLM, or emit a trade
decision. It reuses the snapshot's verified news/catalyst and rotation outputs.
"""
from __future__ import annotations

import math
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


def _story_key(text: str) -> str:
    return re.sub(r"\W+", " ", text.casefold()).strip()


def _source_family(source: Any) -> str:
    value = str(source or "unknown").casefold()
    if re.search(r"\bap\b", value):
        return "associated press"
    for family in ("reuters", "associated press", "bloomberg", "afp", "official", "ministry", "government"):
        if family in value:
            return family
    return re.sub(r"^https?://", "", value).split("/")[0] or "unknown"


def _source_credibility(source: Any, verified: bool) -> float:
    return {
        "reuters": 0.90, "associated press": 0.88, "bloomberg": 0.88,
        "afp": 0.82, "official": 0.92, "ministry": 0.88,
        "government": 0.90,
    }.get(_source_family(source), 0.60 if verified else 0.20)


def _official_source(source: Any, text: str) -> bool:
    value = f"{source or ''} {text}".casefold()
    return any(token in value for token in ("official", "ministry", "government", "white house", "treasury", "military"))


def _decay_factor(age_seconds: float | None, half_life_minutes: int | None) -> float:
    if age_seconds is None or half_life_minutes is None or half_life_minutes <= 0:
        return 1.0
    return round(max(0.0, min(1.0, math.exp(-math.log(2.0) * age_seconds / (half_life_minutes * 60.0)))), 4)


def _event_taxonomy(text: str, raw_type: Any) -> str:
    value = text.casefold()
    rules = (
        (("nuclear",), "NUCLEAR_ESCALATION"),
        (("ceasefire", "truce", "ateşkes"), "CEASEFIRE"),
        (("peace talks", "barış görüş", "negotiat"), "PEACE_TALKS"),
        (("sanction", "yaptırım"), "SANCTIONS_RELIEF" if any(x in value for x in ("relief", "lift", "kaldır")) else "SANCTIONS"),
        (("chokepoint", "strait", "hormuz", "boğaz"), "CHOKEPOINT_THREAT" if any(x in value for x in ("threat", "could", "may", "tehdit")) else "CHOKEPOINT_DISRUPTION"),
        (("shipping attack", "ship attack", "gemi saldır", "vessel hit"), "SHIPPING_ATTACK"),
        (("port disruption", "port closure", "liman kapat"), "PORT_DISRUPTION"),
        (("pipeline", "boru hatt"), "PIPELINE_DISRUPTION"),
        (("energy infrastructure", "refinery", "enerji tesisi"), "ENERGY_INFRASTRUCTURE_ATTACK"),
        (("airstrike", "air strike", "hava saldır"), "AIRSTRIKE"),
        (("missile", "füze"), "MISSILE_ATTACK"),
        (("drone", "iha", "sih"), "DRONE_ATTACK"),
        (("ground offensive", "kara harekat", "invasion"), "GROUND_OFFENSIVE"),
        (("trade restriction", "tariff", "ticaret kısıt"), "TRADE_RESTRICTION"),
        (("de-escalat", "gerilimi azalt", "withdraw", "çekil"), "MILITARY_DEESCALATION"),
        (("escalat", "attack", "strike", "saldır", "çatışma"), "MILITARY_ESCALATION"),
    )
    for keywords, result in rules:
        if any(keyword in value for keyword in keywords):
            return result
    raw = str(raw_type or "UNKNOWN").upper()
    return raw if raw and raw != "UNKNOWN" else "UNKNOWN"


def _event_channels(event_type: str, text: str) -> tuple[str, ...]:
    value = text.casefold()
    channels: list[str] = []
    if event_type in {"CHOKEPOINT_THREAT", "CHOKEPOINT_DISRUPTION", "SHIPPING_ATTACK", "PORT_DISRUPTION"} or any(x in value for x in ("shipping", "strait", "hormuz", "gemi", "liman")):
        channels.append("shipping_risk")
    if event_type in {"PIPELINE_DISRUPTION", "ENERGY_INFRASTRUCTURE_ATTACK", "CHOKEPOINT_DISRUPTION"} or any(x in value for x in ("oil", "energy", "pipeline", "opec", "petrol")):
        channels.append("energy_supply_risk")
    if event_type in {"SANCTIONS", "SANCTIONS_RELIEF", "TRADE_RESTRICTION"}:
        channels.extend(("trade_risk", "sanctions_pressure"))
    if event_type in {"MILITARY_ESCALATION", "AIRSTRIKE", "MISSILE_ATTACK", "DRONE_ATTACK", "GROUND_OFFENSIVE", "NUCLEAR_ESCALATION"}:
        channels.append("risk_aversion")
    return tuple(dict.fromkeys(channels))


def _geo_events(snapshot: MarketSnapshot, now: datetime, config: dict[str, Any]) -> tuple[GeopoliticalEvent, ...]:
    by_id = {getattr(item, "headline_id", ""): item for item in snapshot.catalyst_impacts}
    grouped: dict[str, list[tuple[Any, Any]]] = {}
    for headline in snapshot.headlines:
        impact = by_id.get(getattr(headline, "id", ""))
        event_type = getattr(impact, "event_type", "unknown") if impact else "unknown"
        if not str(event_type).startswith("geopolitical_"):
            continue
        grouped.setdefault(_story_key(_headline_text(headline)), []).append((headline, impact))

    events: list[GeopoliticalEvent] = []
    source_cfg = config.get("source") or {}
    decay_cfg = config.get("decay") or {}
    for rows in grouped.values():
        headline, impact = rows[0]
        title = _headline_text(headline)
        lower = title.casefold()
        event_type = _event_taxonomy(title, getattr(impact, "event_type", "unknown"))
        threat_only = any(word in lower for word in ("threat", "could", "may", "might", "iddia", "tehdit"))
        verified_rows = [row for row, _ in rows if getattr(row, "verified", False)]
        families = {_source_family(getattr(row, "source", None)) for row, _ in rows}
        official = any(_official_source(getattr(row, "source", None), _headline_text(row)) for row in verified_rows)
        confirmed = bool(verified_rows) and not threat_only
        ts = getattr(headline, "ts", None)
        age = max(0.0, (now - ts).total_seconds()) if ts else None
        half_life = getattr(impact, "expected_half_life_minutes", None) or int(decay_cfg.get("default_half_life_minutes", 240))
        decay = _decay_factor(age, half_life)
        raw_conf = float(getattr(impact, "confidence", 0.0) or 0.0)
        credibility = max((_source_credibility(getattr(row, "source", None), True) for row in verified_rows), default=0.20)
        confidence = credibility * min(1.0, 0.75 + len(verified_rows) * float(source_cfg.get("confirmation_factor", 0.12)))
        confidence *= min(1.0, 0.80 + len(families) * float(source_cfg.get("diversity_factor", 0.10)))
        confidence *= decay
        if official:
            confidence += float(source_cfg.get("official_bonus", 0.12))
        confidence = min(1.0, max(raw_conf, confidence))
        if not verified_rows:
            confidence = min(confidence, float(source_cfg.get("rumor_cap", 0.25)))
        raw_severity = abs(float(getattr(impact, "surprise_level", 0.0) or 0.0)) or 0.5
        channels = _event_channels(event_type, title)
        events.append(
            GeopoliticalEvent(
                event_id=str(getattr(headline, "id", "")),
                event_type=event_type,
                actors=tuple(str(x) for x in (getattr(headline, "actors", None) or ())),
                region=getattr(headline, "region", None),
                location=getattr(headline, "location", None),
                status="CONFIRMED" if confirmed else "THREAT",
                confirmed_action=confirmed,
                threat_only=threat_only,
                severity=_clamp(raw_severity * decay, 0.0, 1.0),
                energy_exposure=1.0 if any(w in lower for w in ("oil", "energy", "pipeline", "opec", "petrol")) else 0.0,
                shipping_exposure=1.0 if any(w in lower for w in ("shipping", "port", "strait", "gemi", "hormuz")) else 0.0,
                trade_exposure=1.0 if event_type in {"SANCTIONS", "SANCTIONS_RELIEF", "TRADE_RESTRICTION"} else 0.0,
                financial_sanctions_exposure=1.0 if event_type in {"SANCTIONS", "SANCTIONS_RELIEF"} else 0.0,
                commodity_exposure=1.0 if any(w in lower for w in ("commodity", "oil", "gold", "petrol")) else 0.0,
                nuclear_risk=1.0 if event_type == "NUCLEAR_ESCALATION" else 0.0,
                direct_us_involvement=True if any(w in lower for w in ("u.s.", "united states", "washington", "abd")) else None,
                source_confidence=round(confidence, 4),
                source_credibility=round(credibility, 4),
                confirmation_count=len(verified_rows),
                independent_confirmation_count=len(families),
                source_diversity=len(families),
                official_confirmation=official,
                published_at=ts,
                freshness_seconds=age,
                half_life_minutes=half_life,
                valid_until=getattr(impact, "valid_until", None),
                decay_factor=decay,
                channels=channels,
                evidence=tuple(_headline_text(row)[:240] for row, _ in rows[:4]),
            )
        )
    return tuple(events)


def _statements(snapshot: MarketSnapshot, now: datetime, config: dict[str, Any]) -> tuple[PolicyStatement, ...]:
    result: list[PolicyStatement] = []
    keywords = ("fed", "fomc", "federal reserve", "ecb", "boj", "pboс", "bank of england", "powell", "lagarde", "treasury", "white house", "opec", "saudi", "russia", "china")
    authority_cfg = config.get("statement_authority") or {}
    previous: dict[str, list[float]] = {}
    signatures: set[tuple[str, int]] = set()
    for headline in sorted(snapshot.headlines, key=lambda item: getattr(item, "ts", now)):
        text = _headline_text(headline)
        lower = text.casefold()
        if not any(word in lower for word in keywords):
            continue
        hawkish = any(word in lower for word in ("hawkish", "higher for longer", "rate hike", "tighten", "şahin", "sıkılaştır"))
        dovish = any(word in lower for word in ("dovish", "rate cut", "easing", "accommodative", "güvercin", "gevşeme"))
        direction = 1.0 if hawkish else -1.0 if dovish else 0.0
        if any(word in lower for word in ("fed", "fomc", "federal reserve", "powell")):
            institution = "Federal Reserve"
        elif "ecb" in lower or "lagarde" in lower:
            institution = "ECB"
        elif "boj" in lower:
            institution = "BOJ"
        elif "opec" in lower:
            institution = "OPEC"
        elif "treasury" in lower:
            institution = "US Treasury"
        elif "white house" in lower or "administration" in lower:
            institution = "White House"
        else:
            institution = "government"
        if any(x in lower for x in ("chair", "başkan", "powell", "lagarde")):
            role = "chair"
        elif "governor" in lower or "guvernör" in lower:
            role = "governor"
        elif "voting member" in lower:
            role = "voting_member"
        elif "regional president" in lower:
            role = "regional_president"
        elif "minister" in lower or "bakan" in lower:
            role = "minister"
        elif "treasury secretary" in lower:
            role = "treasury_secretary"
        elif "president" in lower:
            role = "president"
        elif "spokesperson" in lower or "sözcü" in lower:
            role = "official_spokesperson"
        elif "anonymous" in lower or "unnamed" in lower or "iddia" in lower:
            role = "anonymous_source"
        else:
            role = "unknown"
        signature = (institution, int(direction))
        repeated = signature in signatures
        signatures.add(signature)
        baseline_values = previous.setdefault(institution, [])
        baseline = sum(baseline_values[-3:]) / len(baseline_values[-3:]) if baseline_values else None
        semantic = abs(direction - baseline) if baseline is not None else (0.25 if direction else 0.0)
        semantic = _clamp(semantic * (0.25 if repeated else 1.0), 0.0, 1.0)
        if direction:
            baseline_values.append(direction)
        actual = getattr(headline, "actual", None)
        expected = getattr(headline, "expected", None)
        historical_volatility = getattr(headline, "historical_surprise_volatility", None)
        numeric = normalized_surprise(actual, expected, historical_volatility)
        if numeric is None and actual is not None and expected is not None:
            numeric = _clamp((float(actual) - float(expected)) / max(abs(float(expected)), 1.0))
        ts = getattr(headline, "ts", None)
        authority = float(authority_cfg.get(role, authority_cfg.get("unknown", 0.35)))
        verified = bool(getattr(headline, "verified", False))
        credibility = _source_credibility(getattr(headline, "source", None), verified)
        result.append(
            PolicyStatement(
                statement_id=str(getattr(headline, "id", "")),
                speaker=getattr(headline, "speaker", None),
                institution=institution,
                speaker_role=role,
                authority_score=authority,
                topic="monetary_policy",
                policy_direction="tightening" if hawkish else "easing" if dovish else "unknown",
                hawkish_dovish=1.0 if hawkish else -1.0 if dovish else None,
                tightening_easing=1.0 if hawkish else -1.0 if dovish else None,
                new_information_score=semantic if direction else None,
                repetition_score=1.0 if repeated else 0.0,
                credibility=credibility,
                source_confidence=round(credibility * authority, 4),
                actual_value=float(actual) if actual is not None else None,
                expected_value=float(expected) if expected is not None else None,
                numeric_surprise=numeric,
                semantic_surprise=semantic if direction else None,
                baseline_direction=baseline,
                market_relevance=round(authority * (0.7 if direction else 0.3), 4),
                published_at=ts,
                freshness_seconds=max(0.0, (now - ts).total_seconds()) if ts else None,
                half_life_minutes=240,
                evidence=(text[:240], f"authority={authority:.2f}", f"source={credibility:.2f}"),
            )
        )
    return tuple(result)


def normalized_surprise(actual: float | None, expected: float | None, historical_volatility: float | None) -> float | None:
    """Return a bounded numeric surprise; missing inputs remain unavailable."""
    if actual is None or expected is None or historical_volatility is None or historical_volatility <= 0:
        return None
    return _clamp((float(actual) - float(expected)) / float(historical_volatility))


def _positioning(snapshot: MarketSnapshot) -> tuple[dict[str, dict[str, Any]], float]:
    out: dict[str, dict[str, Any]] = {}
    available = 0
    total = 0
    for symbol, item in (getattr(snapshot, "derivatives", {}) or {}).items():
        total += 1
        if getattr(item, "status", "DEGRADED") != "OK" or not getattr(item, "verified", False):
            continue
        available += 1
        funding = getattr(item, "funding_rate", None)
        oi_change = getattr(item, "oi_change_pct", None)
        crowded = "neutral"
        if funding is not None and oi_change is not None and funding > 0.0003 and oi_change > 0.05:
            crowded = "CROWDED_LONG"
        elif funding is not None and oi_change is not None and funding < -0.0003 and oi_change > 0.05:
            crowded = "CROWDED_SHORT"
        out[symbol] = {"type": "derivatives", "funding_rate": funding, "oi_change_pct": oi_change, "squeeze_level": getattr(item, "squeeze_level", None), "state": crowded}
    for symbol, item in (getattr(snapshot, "options", {}) or {}).items():
        total += 1
        if getattr(item, "status", "DEGRADED") != "OK" or not getattr(item, "verified", False):
            continue
        available += 1
        out.setdefault(symbol, {})["options"] = {"regime": getattr(item, "regime", None), "skew_25d": getattr(item, "skew_25d", None), "put_call_oi_ratio": getattr(item, "put_call_oi_ratio", None)}
    for symbol, by_tf in (getattr(snapshot, "volatility", {}) or {}).items():
        item = by_tf.get("1d") if isinstance(by_tf, dict) else None
        total += 1
        if item is None or getattr(item, "status", "DEGRADED") != "OK" or not getattr(item, "verified", False):
            continue
        available += 1
        out.setdefault(symbol, {})["volatility"] = {"regime": getattr(item, "regime", None), "vol_state": getattr(item, "vol_state", None)}
    return out, round(available / total, 4) if total else 0.0


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
    flows = {
        "usd": _flow(rotation, "DXY"),
        "treasury": _flow(rotation, "TLT"),
        "equity": _flow(rotation, "SP500"),
        "credit": _mean([_flow(rotation, "HYG"), -_flow(rotation, "LQD") if _flow(rotation, "LQD") is not None else None]),
        "metals": _mean([_flow(rotation, "XAUUSD"), _flow(rotation, "XAGUSD")]),
        "energy": _flow(rotation, "BRENT"),
        "crypto": _mean([_flow(rotation, "BTCUSD"), _flow(rotation, "ETHUSD")]),
    }
    usd = flows["usd"]
    equity = flows["equity"]
    treasury = flows["treasury"]
    credit_flow = flows["credit"]
    credit_stress = _clamp(-credit_flow) if credit_flow is not None else None
    events = _geo_events(snapshot, current, config) if config.get("geopolitical_enabled", True) else ()
    statements = _statements(snapshot, current, config) if config.get("statements_enabled", True) else ()
    geo = _mean([e.severity * e.source_confidence for e in events if e.confirmed_action])
    energy_risk = _mean([e.energy_exposure * (e.severity or 0.0) * e.source_confidence for e in events])
    shipping = _mean([e.shipping_exposure * (e.severity or 0.0) * e.source_confidence for e in events])
    rates = _mean([_flow(rotation, "US02Y"), _flow(rotation, "US10Y")])
    inflation = _mean([energy_risk, geo, flows["energy"] if flows["energy"] is not None and flows["energy"] > 0 else None])
    growth = equity
    real_yield = _clamp(rates - (inflation or 0.0) * 0.5) if rates is not None else None
    risk_aversion = _mean([-equity if equity is not None else None, credit_stress, shipping])
    liquidity = _mean([flows["crypto"], equity, -usd if usd is not None else None, -rates if rates is not None else None, credit_flow])
    defensive = _mean([treasury, -usd if usd is not None else None, flows["metals"]])
    flow_axis_values = list(flows.values())
    flow_coverage = round(sum(value is not None for value in flow_axis_values) / len(flow_axis_values), 4)
    macro_values = [rates, real_yield, inflation, growth, usd]
    macro_coverage = round(sum(value is not None for value in macro_values) / len(macro_values), 4)
    geo_coverage = 1.0 if snapshot.headlines else 0.0
    statement_coverage = 1.0 if snapshot.headlines else 0.0
    positioning, positioning_coverage = _positioning(snapshot)
    regime_inputs = [liquidity, risk_aversion, inflation, growth, defensive]
    if liquidity is None:
        flow_regime = "UNKNOWN"
    elif liquidity < -0.45 and usd is not None and usd > 0.25:
        flow_regime = "DOLLAR_SHORTAGE"
    elif liquidity < -0.45 and credit_stress is not None and credit_stress > 0.3:
        flow_regime = "LIQUIDITY_CRISIS"
    elif inflation is not None and inflation > 0.4 and rates is not None and rates > 0.2:
        flow_regime = "INFLATION_SHOCK"
    elif growth is not None and growth < -0.35 and (rates is None or rates < 0):
        flow_regime = "DEFLATIONARY_SHOCK"
    elif liquidity > 0.3 and (risk_aversion is None or risk_aversion < 0.1):
        flow_regime = "LIQUIDITY_EXPANSION"
    elif liquidity > 0.1 and (risk_aversion is None or risk_aversion < 0.2):
        flow_regime = "RISK_ON"
    elif risk_aversion is not None and risk_aversion > 0.3:
        flow_regime = "RISK_OFF"
    elif any(value is not None for value in regime_inputs):
        flow_regime = "MIXED"
    else:
        flow_regime = "UNKNOWN"
    domain_coverage = [flow_coverage, macro_coverage, geo_coverage, statement_coverage, positioning_coverage]
    coverage = round(sum(domain_coverage) / len(domain_coverage), 4)
    quality_score = float(getattr(snapshot.quality, "score", 0.0) or 0.0) / 100.0
    confidence = round(max(0.0, min(1.0, quality_score * coverage)), 4)
    missing = tuple(name for name, value in {
        "DXY": usd, "TLT": treasury, "SP500": equity, "credit": credit_flow,
        "metals": flows["metals"], "BRENT": flows["energy"], "crypto": flows["crypto"],
        "rates": rates, "inflation": inflation, "growth": growth,
    }.items() if value is None)
    evidence = tuple([
        *((getattr(rotation, "evidence", None) or [])[:8]),
        f"flow_coverage={flow_coverage:.2f}",
        f"macro_coverage={macro_coverage:.2f}",
    ])
    return WorldStateSnapshot(
        generated_at=current,
        liquidity=liquidity,
        usd_pressure=usd,
        rates_pressure=rates,
        real_yield_pressure=real_yield,
        inflation_pressure=inflation,
        growth_pressure=growth,
        risk_aversion=risk_aversion,
        credit_stress=credit_stress,
        energy_supply_risk=energy_risk,
        shipping_risk=shipping,
        geopolitical_risk=geo,
        crypto_liquidity=flows["crypto"],
        equity_risk_appetite=equity,
        usd_flow=flows["usd"],
        treasury_flow=flows["treasury"],
        equity_flow=flows["equity"],
        credit_flow=flows["credit"],
        metals_flow=flows["metals"],
        energy_flow=flows["energy"],
        crypto_flow=flows["crypto"],
        defensive_flow=defensive,
        macro_coverage=macro_coverage,
        flow_coverage=flow_coverage,
        geopolitical_coverage=geo_coverage,
        statement_coverage=statement_coverage,
        positioning_coverage=positioning_coverage,
        global_flow_regime=flow_regime,
        confidence=confidence,
        data_quality=str(getattr(snapshot.quality, "status", "UNAVAILABLE")),
        coverage=coverage,
        evidence=evidence,
        missing_inputs=missing,
        geopolitical_events=events,
        statements=statements,
        positioning=positioning,
    )
