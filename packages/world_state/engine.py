"""Build world-state evidence from the existing market snapshot.

This module deliberately does not fetch data, call an LLM, or emit a trade
decision. It reuses the snapshot's verified news/catalyst and rotation outputs.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.providers.news.provenance import source_family as _provenance_source_family
from packages.data.providers.news.provenance import story_key as _provenance_story_key
from packages.data.registry.loader import load_thresholds
from packages.world_state.model import (
    EventInteraction,
    ExpectationState,
    FlowObservation,
    GeopoliticalEvent,
    MacroSurpriseImpact,
    PolicyStatement,
    WorldStateSnapshot,
)


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return round(max(low, min(high, value)), 4)


def _flow(rotation: Any, symbol: str) -> float | None:
    if getattr(rotation, "status", "UNAVAILABLE") == "UNAVAILABLE":
        return None
    value = (getattr(rotation, "per_symbol", None) or {}).get(symbol)
    if value is None:
        return None
    return _clamp((float(value) - 50.0) / 50.0)


_FLOW_AXES = {
    "DXY": "usd", "TLT": "treasury", "SP500": "equity", "HYG": "credit",
    "LQD": "credit", "XAUUSD": "metals", "XAGUSD": "metals", "BRENT": "energy",
    "BTCUSD": "crypto", "ETHUSD": "crypto",
}


def _flow_observations(snapshot: MarketSnapshot, rotation: Any, now: datetime) -> tuple[tuple[FlowObservation, ...], dict[str, dict[str, Any]]]:
    """Normalise optional published flow evidence and proxy rotation evidence.

    The ingestion pipeline may expose ``flow_observations`` in a future
    provider-neutral shape.  Until then, rotation remains an explicitly named
    price-flow proxy.  A proxy is supplementary and cannot overwrite a real
    observation for the same axis.
    """
    raw = getattr(snapshot, "flow_observations", None) or ()
    observations: list[FlowObservation] = []
    for item in raw if isinstance(raw, (list, tuple)) else (raw,):
        if isinstance(item, FlowObservation):
            obs = item
        elif isinstance(item, dict):
            try:
                obs = FlowObservation(
                    asset_or_market=str(item.get("asset_or_market") or item.get("asset") or ""),
                    flow_type=str(item.get("flow_type") or "capital_flow"),
                    value=float(item["value"]) if item.get("value") is not None else None,
                    normalized_value=float(item["normalized_value"]) if item.get("normalized_value") is not None else None,
                    source_type=str(item.get("source_type") or "UNAVAILABLE").upper(),
                    source=item.get("source"),
                    timestamp=item.get("timestamp"),
                    freshness_seconds=float(item["freshness_seconds"]) if item.get("freshness_seconds") is not None else None,
                    confidence=float(item.get("confidence") or 0.0),
                    coverage=float(item.get("coverage") or 0.0),
                    independence_weight=float(item.get("independence_weight") if item.get("independence_weight") is not None else 1.0),
                    evidence=tuple(str(x) for x in item.get("evidence") or ()),
                )
            except (TypeError, ValueError):
                continue
        else:
            continue
        if obs.asset_or_market and obs.source_type in {"REAL_FLOW", "POSITIONING_PROXY", "PRICE_FLOW_PROXY"}:
            observations.append(obs)

    # Existing rotation is always labelled proxy; never infer a real fund-flow
    # claim from price momentum.
    for symbol, _axis in _FLOW_AXES.items():
        value = _flow(rotation, symbol)
        if value is None:
            continue
        observations.append(FlowObservation(
            asset_or_market=symbol,
            flow_type="rotation_momentum",
            normalized_value=value,
            source_type="PRICE_FLOW_PROXY",
            source="rotation.per_symbol",
            timestamp=getattr(snapshot, "generated_at", now),
            freshness_seconds=max(0.0, (now - getattr(snapshot, "generated_at", now)).total_seconds()) if getattr(snapshot, "generated_at", None) else None,
            confidence=0.35,
            coverage=1.0,
            independence_weight=0.35,
            evidence=("price-based rotation; not published fund flow",),
        ))

    rank = {"REAL_FLOW": 3, "POSITIONING_PROXY": 2, "PRICE_FLOW_PROXY": 1, "UNAVAILABLE": 0}
    selected: dict[str, FlowObservation] = {}
    for obs in observations:
        axis = _FLOW_AXES.get(obs.asset_or_market, str(obs.asset_or_market).casefold())
        current = selected.get(axis)
        if current is None or rank.get(obs.source_type, 0) > rank.get(current.source_type, 0):
            selected[axis] = obs
    state = {
        axis: {
            "value": obs.normalized_value,
            "source_type": obs.source_type,
            "source": obs.source,
            "confidence": obs.confidence,
            "coverage": obs.coverage,
            "independence_weight": obs.independence_weight,
            "freshness_seconds": obs.freshness_seconds,
            "evidence": list(obs.evidence),
        }
        for axis, obs in sorted(selected.items())
    }
    return tuple(observations), state


def _selected_flow(flow_state: dict[str, dict[str, Any]], axis: str, fallback: float | None) -> float | None:
    item = flow_state.get(axis) or {}
    value = item.get("value")
    if value is None:
        return fallback
    # Do not count the same price return once as technical evidence and again
    # as independent capital flow.  Published flow/positioning can retain its
    # full weight; price-only rotation is explicitly discounted.
    try:
        weight = float(item.get("independence_weight", 1.0) or 0.0)
    except (TypeError, ValueError):
        weight = 1.0
    if str(item.get("source_type") or "").upper() == "PRICE_FLOW_PROXY":
        weight = max(0.0, min(1.0, weight))
        return _clamp(float(value) * weight)
    return _clamp(float(value))


def _expectations(snapshot: MarketSnapshot, statements: tuple[PolicyStatement, ...], now: datetime) -> tuple[ExpectationState, ...]:
    out: list[ExpectationState] = []
    for item in getattr(snapshot, "catalysts", ()) or ():
        expected = getattr(item, "expected", None)
        actual = getattr(item, "actual", None)
        if expected is None and actual is None:
            continue
        volatility = getattr(item, "historical_surprise_volatility", None)
        surprise = normalized_surprise(actual, expected, volatility)
        if surprise is None and actual is not None and expected is not None:
            surprise = _clamp((float(actual) - float(expected)) / max(abs(float(expected)), 1.0))
        out.append(ExpectationState(
            subject=str(getattr(item, "title", None) or getattr(item, "id", "unknown")),
            expected_value=float(expected) if expected is not None else None,
            actual_value=float(actual) if actual is not None else None,
            expected_direction=None,
            expectation_source="EXPLICIT_CONSENSUS" if expected is not None else "UNAVAILABLE",
            consensus_confidence=1.0 if expected is not None and getattr(item, "verified", False) else 0.5 if expected is not None else 0.0,
            pricing_confidence=0.0,
            surprise=surprise,
            as_of=getattr(item, "ts", None),
            source=getattr(item, "source", None),
            evidence=(f"event_id={getattr(item, 'id', '')}", "actual/expected from calendar"),
        ))
    for statement in statements:
        direction = statement.tightening_easing
        if direction is None and statement.baseline_direction is None:
            continue
        out.append(ExpectationState(
            subject=f"statement:{statement.institution or 'unknown'}",
            expected_direction=statement.baseline_direction,
            baseline_direction=statement.baseline_direction,
            expected_value=statement.expected_value,
            actual_value=statement.actual_value,
            expectation_source="PREVIOUS_GUIDANCE" if statement.baseline_direction is not None else "UNAVAILABLE",
            consensus_confidence=statement.source_confidence,
            semantic_surprise=statement.semantic_surprise,
            surprise=statement.numeric_surprise,
            as_of=statement.published_at,
            source=statement.evidence[-1] if statement.evidence else None,
            evidence=(f"repetition={statement.repetition_score or 0.0:.2f}",),
        ))
    return tuple(out)


def _event_interactions(events: tuple[GeopoliticalEvent, ...], surprises: tuple[MacroSurpriseImpact, ...]) -> tuple[EventInteraction, ...]:
    """Bounded pairwise synergy/redundancy; no 3-way expansion."""
    items: list[tuple[str, set[str], float, str]] = []
    for event in events:
        channels = set(event.channels or ())
        for channel, _value in (event.channel_strengths or {}).items():
            channels.add(channel)
        items.append((event.event_id, channels, float(event.severity or 0.0) * float(event.source_confidence or 0.0), event.event_type))
    for event in surprises:
        channels = {key for key, value in {
            "inflation_pressure": event.inflation_contribution,
            "growth_pressure": event.growth_contribution,
            "rates_pressure": event.rates_contribution,
            "oil_pressure": event.oil_contribution,
        }.items() if value}
        items.append((event.event_id, channels, float(event.effective_strength or 0.0), event.event_type))
    out: list[EventInteraction] = []
    for index, (left_id, left_channels, left_value, left_type) in enumerate(items):
        for right_id, right_channels, right_value, right_type in items[index + 1:]:
            common = left_channels & right_channels
            if not common or not left_id or not right_id:
                continue
            channel = sorted(common)[0]
            same_root = left_type == right_type or left_id.split(":", 1)[0] == right_id.split(":", 1)[0]
            signed_left = left_value
            signed_right = right_value
            relation = "REDUNDANT" if same_root else "SYNERGISTIC"
            multiplier = 0.55 if same_root else 1.15
            if signed_left * signed_right < 0:
                relation, multiplier = "CONFLICT", 0.35
            contribution = _clamp((signed_left + signed_right) * (multiplier - 1.0))
            out.append(EventInteraction(
                event_ids=(left_id, right_id), channel=channel, relation=relation,
                multiplier=multiplier, contribution=contribution,
                root_event_ids=(left_id, right_id),
                evidence=(f"{left_type}+{right_type}", "pairwise_bounded"),
            ))
    return tuple(out)


def _mean(values: list[float | None]) -> float | None:
    present = [float(v) for v in values if v is not None]
    return _clamp(sum(present) / len(present)) if present else None


def _headline_text(headline: Any, article_rows: dict[str, dict[str, Any]] | None = None) -> str:
    title = " ".join(str(getattr(headline, key, "") or "") for key in ("title", "title_tr"))
    try:
        from packages.data.providers.news.article_enrichment import context_for

        text, _article = context_for(headline, article_rows=article_rows)
        return text or title
    except Exception:
        return title


def _story_key(text: str) -> str:
    # Shared with the news consensus/reporting layer so story grouping cannot
    # disagree between the world graph and the dashboard evidence view.
    return _provenance_story_key(text)


def _source_family(source: Any, *, title: Any = None, url: Any = None) -> str:
    # Google News query buckets are not independent publishers.  Keep this
    # wrapper for callers while delegating to the shared provenance rule.
    return _provenance_source_family(source, title=title, url=url)


def _source_credibility(source: Any, verified: bool) -> float:
    return {
        "direct:reuters": 0.90, "direct:associated_press": 0.88,
        "direct:bloomberg": 0.88, "direct:afp": 0.82,
        "direct:official": 0.92, "direct:ministry": 0.88,
        "direct:government": 0.90,
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
        (("chokepoint", "strait", "hormuz", "bab el-mandeb", "bab al mandab", "red sea", "gulf of aden", "boğaz", "kızıldeniz", "aden körfezi"), "CHOKEPOINT_THREAT" if any(x in value for x in ("threat", "threaten", "could", "may", "warn", "tehdit")) else "CHOKEPOINT_DISRUPTION"),
        (("shipping attack", "ship attack", "gemi saldır", "vessel hit"), "SHIPPING_ATTACK"),
        (("port disruption", "port closure", "liman kapat"), "PORT_DISRUPTION"),
        (("pipeline", "boru hatt"), "PIPELINE_DISRUPTION"),
        (("airstrike", "air strike", "hava saldır"), "AIRSTRIKE"),
        (("missile", "füze"), "MISSILE_ATTACK"),
        (("energy infrastructure", "refinery", "enerji tesisi"), "ENERGY_INFRASTRUCTURE_ATTACK"),
        (("drone", "iha", "sih"), "DRONE_ATTACK"),
        (("ground offensive", "kara harekat", "invasion"), "GROUND_OFFENSIVE"),
        (("trade restriction", "export restriction", "export ban", "tariff", "ticaret kısıt"), "TRADE_RESTRICTION"),
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
    if any(x in value for x in ("oil", "energy", "pipeline", "refinery", "opec", "petrol")):
        channels.append("energy_supply_risk")
    if "refinery" in value or "energy infrastructure" in value or "enerji tesisi" in value:
        channels.append("energy_infrastructure_attack")
    if event_type in {"SANCTIONS", "SANCTIONS_RELIEF", "TRADE_RESTRICTION"}:
        channels.extend(("trade_risk", "sanctions_pressure"))
    if event_type in {"MILITARY_ESCALATION", "AIRSTRIKE", "MISSILE_ATTACK", "DRONE_ATTACK", "GROUND_OFFENSIVE", "NUCLEAR_ESCALATION"}:
        channels.append("risk_aversion")
    return tuple(dict.fromkeys(channels))


def _geo_events(snapshot: MarketSnapshot, now: datetime, config: dict[str, Any]) -> tuple[GeopoliticalEvent, ...]:
    by_id = {getattr(item, "headline_id", ""): item for item in snapshot.catalyst_impacts}
    try:
        from packages.data.providers.news.article_enrichment import cached

        article_rows = cached(getattr(item, "url", None) for item in snapshot.headlines)
    except Exception:
        article_rows = {}
    grouped: dict[str, list[tuple[Any, Any]]] = {}
    for headline in snapshot.headlines:
        impact = by_id.get(getattr(headline, "id", ""))
        event_type = getattr(impact, "event_type", "unknown") if impact else "unknown"
        # Taxonomy is headline-first.  The legacy catalyst impact is useful
        # evidence, but an absent/unknown prefix must never hide a geopolitical
        # event from the causal shadow.
        text = _headline_text(headline, article_rows)
        if (not text.strip() or
                _event_taxonomy(text, event_type) == "UNKNOWN"):
            continue
        # Article prose informs taxonomy, but not identity; syndication must
        # still collapse by the canonical RSS title.
        grouped.setdefault(_story_key(_headline_text(headline, {})), []).append((headline, impact))

    events: list[GeopoliticalEvent] = []
    source_cfg = config.get("source") or {}
    decay_cfg = config.get("decay") or {}
    for rows in grouped.values():
        headline, impact = rows[0]
        title = _headline_text(headline, article_rows)
        lower = title.casefold()
        event_type = _event_taxonomy(title, getattr(impact, "event_type", "unknown"))
        threat_only = any(word in lower for word in ("threat", "could", "may", "might", "iddia", "tehdit"))
        verified_rows = [row for row, _ in rows if getattr(row, "verified", False)]
        families = {
            _source_family(
                getattr(row, "source", None),
                title=_headline_text(row, article_rows),
                url=getattr(row, "url", None),
            )
            for row, _ in rows
        }
        official = any(_official_source(getattr(row, "source", None), _headline_text(row, article_rows)) for row in verified_rows)
        confirmed = bool(verified_rows) and not threat_only
        ts = getattr(headline, "ts", None)
        age = max(0.0, (now - ts).total_seconds()) if ts else None
        half_life = getattr(impact, "expected_half_life_minutes", None) or int(decay_cfg.get("default_half_life_minutes", 240))
        decay = _decay_factor(age, half_life)
        raw_conf = float(getattr(impact, "confidence", 0.0) or 0.0)
        credibility = max((_source_credibility(getattr(row, "source", None), True) for row in verified_rows), default=0.20)
        confidence = credibility * min(1.0, 0.75 + len(verified_rows) * float(source_cfg.get("confirmation_factor", 0.12)))
        confidence *= min(1.0, 0.80 + len(families) * float(source_cfg.get("diversity_factor", 0.10)))
        # Decay is applied exactly once to effective event strength.  It is not
        # folded into source confidence, otherwise the graph silently applies
        # decay² when it multiplies severity by confidence.
        if official:
            confidence += float(source_cfg.get("official_bonus", 0.12))
        confidence = min(1.0, max(raw_conf, confidence))
        if not verified_rows:
            confidence = min(confidence, float(source_cfg.get("rumor_cap", 0.25)))
        raw_severity = abs(float(getattr(impact, "surprise_level", 0.0) or 0.0)) or 0.5
        valid_until = getattr(impact, "valid_until", None)
        if isinstance(valid_until, str):
            try:
                valid_until = datetime.fromisoformat(valid_until)
                if valid_until.tzinfo is None:
                    valid_until = valid_until.replace(tzinfo=UTC)
            except ValueError:
                valid_until = None
        expired = bool(valid_until is not None and valid_until <= now)
        effective_decay = 0.0 if expired else decay
        channels = _event_channels(event_type, title)
        effective_strength = raw_severity * confidence * effective_decay
        channel_strengths = {channel: round(effective_strength, 4) for channel in channels}
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
                severity=_clamp(raw_severity * effective_decay, 0.0, 1.0),
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
                valid_until=valid_until,
                decay_factor=effective_decay,
                expired=expired,
                channels=channels,
                channel_strengths=channel_strengths,
                evidence=tuple(_headline_text(row, article_rows)[:240] for row, _ in rows[:4]),
            )
        )
    return tuple(events)


def _statements(snapshot: MarketSnapshot, now: datetime, config: dict[str, Any]) -> tuple[PolicyStatement, ...]:
    result: list[PolicyStatement] = []
    keywords = ("fed", "fomc", "federal reserve", "ecb", "boj", "pboc", "people's bank", "bank of england", "boe", "powell", "lagarde", "treasury", "white house", "opec", "saudi", "russia", "china", "central bank")
    authority_cfg = config.get("statement_authority") or {}
    previous: dict[str, list[float]] = {}
    signatures: set[tuple[str, int]] = set()
    try:
        from packages.data.providers.news.article_enrichment import cached

        article_rows = cached(getattr(item, "url", None) for item in snapshot.headlines)
    except Exception:
        article_rows = {}
    for headline in sorted(snapshot.headlines, key=lambda item: getattr(item, "ts", now)):
        text = _headline_text(headline, article_rows)
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
        elif "boe" in lower or "bank of england" in lower:
            institution = "BOE"
        elif "pboc" in lower or "people's bank" in lower:
            institution = "PBOC"
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
        normalization_method = "historical_volatility" if numeric is not None else None
        if numeric is None and actual is not None and expected is not None:
            numeric = _clamp((float(actual) - float(expected)) / max(abs(float(expected)), 1.0))
            normalization_method = "relative_difference_fallback"
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
                normalization_method=normalization_method,
                numeric_confidence=1.0 if normalization_method == "historical_volatility" else 0.5 if normalization_method else None,
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


def _macro_topic(title: str) -> tuple[str, str] | None:
    value = title.casefold()
    rules = (
        (("core pce", "core personal consumption"), ("inflation", "inflation")),
        (("pce", "personal consumption expenditures"), ("inflation", "inflation")),
        (("core cpi", "core consumer price"), ("inflation", "inflation")),
        (("cpi", "consumer price", "inflation"), ("inflation", "inflation")),
        (("ppi", "producer price"), ("inflation", "inflation")),
        (("unemployment", "jobless rate"), ("unemployment", "growth")),
        (("jolts", "job openings", "job opening"), ("jolts", "growth")),
        (("employment cost", "eci", "wage"), ("eci", "growth")),
        (("nonfarm", "nfp", "payroll", "jobs", "employment"), ("jobs", "growth")),
        (("adp", "private payroll", "private employment"), ("jobs", "growth")),
        (("gdp", "gross domestic"), ("gdp", "growth")),
        (("ism", "manufacturing pmi", "services pmi", "pmi", "retail sales", "industrial production", "consumer confidence"), ("growth", "growth")),
        (("durable goods", "durable-goods", "durable orders"), ("growth", "growth")),
        (("fed", "fomc", "rate decision", "interest rate"), ("policy_rate", "rates")),
        (("oil inventory", "crude inventory", "eia inventory"), ("oil_inventory", "oil")),
        (("natural gas storage", "gas storage", "underground storage"), ("natural_gas_storage", "oil")),
    )
    for keywords, result in rules:
        if any(keyword in value for keyword in keywords):
            return result
    return None


def _macro_join_topic(title: str) -> str | None:
    """Provider-neutral topic used only to join actuals to expectations."""
    value = title.casefold()
    rules = (
        (("core pce", "core personal consumption"), "core_pce"),
        (("pce", "personal consumption expenditures"), "pce"),
        (("core cpi", "core consumer price"), "core_cpi"),
        (("cpi", "consumer price"), "cpi"),
        (("ppi", "producer price"), "ppi"),
        (("nonfarm", "nfp", "payroll"), "nfp"),
        (("adp", "private payroll", "private employment"), "adp"),
        (("unemployment", "jobless rate"), "unemployment"),
        (("jolts", "job openings", "job opening"), "jolts"),
        (("employment cost", "eci", "wage"), "eci"),
        (("gdp", "gross domestic"), "gdp"),
        (("ism", "manufacturing pmi", "services pmi"), "ism_pmi"),
        (("durable goods", "durable-goods", "durable orders"), "durable_goods"),
        (("fed funds", "federal funds", "fomc", "rate decision"), "fed_policy"),
        (("crude inventory", "oil inventory", "eia"), "oil_inventory"),
        (("natural gas storage", "gas storage", "underground storage"), "natural_gas_storage"),
        (("pmi",), "pmi"),
        (("retail sales",), "retail_sales"),
        (("industrial production",), "industrial_production"),
        (("consumer confidence",), "consumer_confidence"),
    )
    for needles, topic in rules:
        if any(needle in value for needle in needles):
            return topic
    return None


def _macro_expectation_compatible(actual: Any, expected: Any) -> bool:
    """Guard the actual/forecast join against unit and stale-event mistakes."""
    if _macro_join_topic(str(getattr(actual, "title", ""))) != _macro_join_topic(str(getattr(expected, "title", ""))):
        return False
    # Country/currency is part of the event identity.  A US CPI actual must
    # never consume a Canada/Euro-area CPI forecast simply because the title
    # contains the same keyword.  Treat common US aliases as equivalent.
    def _region(value: Any) -> str:
        text = str(value or "").casefold().strip()
        return {"usd": "us", "usa": "us", "u.s.": "us", "united states": "us"}.get(text, text)

    left_region, right_region = _region(getattr(actual, "region", None)), _region(getattr(expected, "region", None))
    if left_region and right_region and left_region != right_region:
        return False
    left_unit = str(getattr(actual, "unit", None) or "").casefold()
    right_unit = str(getattr(expected, "unit", None) or "").casefold()
    if left_unit != right_unit:
        return False
    left_ts = getattr(actual, "ts", None)
    right_ts = getattr(expected, "ts", None)
    if isinstance(left_ts, datetime) and isinstance(right_ts, datetime):
        if abs(left_ts - right_ts) > timedelta(days=45):
            return False
    return True


def _macro_observations(snapshot: MarketSnapshot) -> tuple[Any, ...]:
    """Join official actuals to calendar expectations without inventing data."""
    rows = [*(getattr(snapshot, "catalysts", ()) or ()), *(getattr(snapshot, "macro_releases", ()) or ())]
    expected_rows = [row for row in rows if getattr(row, "expected", None) is not None]
    output: list[Any] = []
    used_expectations: set[str] = set()
    seen: set[str] = set()
    for row in rows:
        event_id = str(getattr(row, "id", "") or "")
        if not event_id or event_id in seen:
            continue
        merged = row
        if getattr(row, "actual", None) is not None and getattr(row, "expected", None) is None:
            candidates = [
                item for item in expected_rows
                if item is not row
                and str(getattr(item, "id", "")) not in used_expectations
                and _macro_expectation_compatible(row, item)
            ]
            if candidates:
                row_ts = getattr(row, "ts", None)
                candidates.sort(key=lambda item: abs((getattr(item, "ts", row_ts) - row_ts).total_seconds()) if isinstance(row_ts, datetime) and isinstance(getattr(item, "ts", None), datetime) else 0.0)
                expected = candidates[0]
                updates = {
                    "expected": getattr(expected, "expected", None),
                    "evidence": [*(getattr(row, "evidence", None) or ()), f"expectation_join={getattr(expected, 'id', '')}"],
                }
                try:
                    merged = row.model_copy(update=updates)
                except AttributeError:
                    from types import SimpleNamespace

                    merged = SimpleNamespace(**{**getattr(row, "__dict__", {}), **updates})
                used_expectations.add(str(getattr(expected, "id", "")))
        output.append(merged)
        seen.add(event_id)
    return tuple(output)


def _macro_surprises(snapshot: MarketSnapshot, now: datetime, config: dict[str, Any]) -> tuple[MacroSurpriseImpact, ...]:
    half_lives = config.get("macro_surprise_half_life_minutes") or {}
    result: list[MacroSurpriseImpact] = []
    seen: set[str] = set()
    for catalyst in _macro_observations(snapshot):
        event_id = str(getattr(catalyst, "id", ""))
        actual = getattr(catalyst, "actual", None)
        expected = getattr(catalyst, "expected", None)
        topic_info = _macro_topic(str(getattr(catalyst, "title", "")))
        if not event_id or event_id in seen or actual is None or expected is None or topic_info is None:
            continue
        seen.add(event_id)
        topic, channel = topic_info
        historical_volatility = getattr(catalyst, "historical_surprise_volatility", None)
        normalized = normalized_surprise(actual, expected, historical_volatility)
        method = "historical_volatility"
        confidence = 1.0
        if normalized is None:
            normalized = _clamp((float(actual) - float(expected)) / max(abs(float(expected)), 1.0))
            method = "relative_difference_fallback"
            confidence = 0.5
        if topic == "unemployment" or topic == "oil_inventory":
            normalized *= -1.0
        half_life = int(half_lives.get(topic, 360 if topic in {"inflation", "jobs", "gdp", "growth"} else 720 if topic == "policy_rate" else 180))
        ts = getattr(catalyst, "ts", None)
        age = max(0.0, (now - ts).total_seconds()) if ts else None
        decay = _decay_factor(age, half_life)
        verified = bool(getattr(catalyst, "verified", False))
        confidence *= 1.0 if verified else 0.5
        effective = float(normalized or 0.0) * confidence * decay
        inflation = effective if channel == "inflation" else 0.0
        growth = effective if channel == "growth" else 0.0
        rates = effective if channel == "rates" else effective * 0.6 if channel == "inflation" else effective * 0.35 if channel == "growth" else 0.0
        oil = effective if channel == "oil" else 0.0
        result.append(MacroSurpriseImpact(
            event_id=event_id,
            event_type=topic,
            topic=topic,
            raw_surprise=round(float(actual) - float(expected), 6),
            normalized_surprise=round(float(normalized), 6),
            numeric_confidence=confidence,
            normalization_method=method,
            inflation_contribution=round(inflation, 6),
            growth_contribution=round(growth, 6),
            rates_contribution=round(rates, 6),
            oil_contribution=round(oil, 6),
            effective_strength=round(effective, 6),
            published_at=ts,
            verified=verified,
            source=getattr(catalyst, "source", None),
            half_life_minutes=half_life,
            decay_factor=decay,
            evidence=(str(getattr(catalyst, "title", ""))[:240], f"normalization={method}"),
        ))
    return tuple(result)


def _blend_pressure(base: float | None, surprise: float | None, surprise_weight: float = 0.35) -> float | None:
    if base is None:
        return _clamp(surprise) if surprise is not None else None
    if surprise is None:
        return base
    return _clamp(base * (1.0 - surprise_weight) + surprise * surprise_weight)


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
        squeeze = getattr(item, "squeeze_level", None)
        squeeze_state = None
        if isinstance(squeeze, str):
            squeeze_state = squeeze.upper()
        elif squeeze is not None:
            squeeze_state = "HIGH" if float(squeeze) >= 0.7 else "ELEVATED" if float(squeeze) >= 0.45 else "NORMAL"
        out[symbol] = {"type": "derivatives", "funding_rate": funding, "oi_change_pct": oi_change, "squeeze_level": squeeze, "squeeze_state": squeeze_state, "state": crowded}
    for symbol, item in (getattr(snapshot, "options", {}) or {}).items():
        total += 1
        if getattr(item, "status", "DEGRADED") != "OK" or not getattr(item, "verified", False):
            continue
        available += 1
        skew = getattr(item, "skew_25d", None)
        pcr = getattr(item, "put_call_oi_ratio", None)
        iv_spread = getattr(item, "iv_rv_spread", None)
        term_slope = getattr(item, "term_slope", None)
        options_state = "NEUTRAL"
        if getattr(item, "regime", None) in {"RICH_VOL", "TERM_STRESS"} or (iv_spread is not None and float(iv_spread) > 0.1) or (term_slope is not None and float(term_slope) < 0):
            options_state = "RICH_VOL_OR_BACKWARDATION"
        elif (skew is not None and float(skew) > 0.05) or (pcr is not None and float(pcr) > 1.3):
            options_state = "PUT_SKEW_CAUTION"
        elif (skew is not None and float(skew) < -0.05) or (pcr is not None and float(pcr) < 0.7):
            options_state = "CALL_CROWDING"
        out.setdefault(symbol, {})["options"] = {"regime": getattr(item, "regime", None), "atm_iv": getattr(item, "atm_iv", None), "iv_rv_spread": iv_spread, "term_slope": term_slope, "skew_25d": skew, "put_call_oi_ratio": pcr, "state": options_state}
    for symbol, by_tf in (getattr(snapshot, "volatility", {}) or {}).items():
        item = by_tf.get("1d") if isinstance(by_tf, dict) else None
        total += 1
        if item is None or getattr(item, "status", "DEGRADED") != "OK" or not getattr(item, "verified", False):
            continue
        available += 1
        out.setdefault(symbol, {})["volatility"] = {"regime": getattr(item, "regime", None), "vol_state": getattr(item, "vol_state", None)}
    return out, round(available / total, 4) if total else 0.0


def _macro_signal(snapshot: MarketSnapshot, symbol: str) -> tuple[float | None, dict[str, Any]]:
    """Return a measured macro pressure and explicit provenance.

    A one-point FRED quote is a level, not a pressure signal.  Pressure is
    therefore derived only from archived OHLCV history; if that history is not
    available we expose the direct quote as context and keep the factor None.
    This prevents rotation's per-symbol scores from masquerading as US02Y/
    US10Y macro data.
    """
    quotes = getattr(snapshot, "prices", None)
    quote = next((q for q in (quotes or []) if getattr(q, "symbol", None) == symbol), None)
    source: dict[str, Any] = {"source_type": "UNAVAILABLE", "source": symbol, "method": "none"}
    if quote is not None:
        source.update({"source_type": "DIRECT", "source": getattr(quote, "source", symbol), "method": "price_quote", "verified": bool(getattr(quote, "verified", False)), "level": getattr(quote, "price", None)})
    try:
        from packages.data.providers.ohlcv import history
        from packages.data.providers.rotation.flow import vol_norm_momentum
        bars = history.load(symbol, "1d")
        if len(bars) < 128 and symbol in {"US02Y", "US10Y", "CPI"}:
            # Reuse the existing FRED history path when configured.  It is
            # internally TTL-cached and returns [] without an API key.
            from packages.data.providers.price.fred import get_history
            bars = get_history(symbol) or bars
        closes = [float(bar.close) for bar in bars if getattr(bar, "close", None)]
        signal = vol_norm_momentum(closes)
        if signal is not None:
            source.update({"source_type": "DERIVED", "method": "vol_norm_momentum", "history_bars": len(closes)})
            return _clamp(signal / 3.0), source
    except Exception:
        pass
    # Compatibility for old, explicitly fixture-shaped snapshots only.  A
    # production MarketSnapshot always has `prices`, so runtime never reads
    # rotation.per_symbol for macro rates.
    if not hasattr(snapshot, "prices"):
        legacy = _flow(getattr(snapshot, "rotation", None), symbol)
        if legacy is not None:
            source.update({"source_type": "LEGACY_FIXTURE", "method": "fixture_rotation"})
            return legacy, source
    return None, source


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
    flow_observations, flow_state = _flow_observations(snapshot, rotation, current)
    flows = {
        "usd": _flow(rotation, "DXY"),
        "treasury": _flow(rotation, "TLT"),
        "equity": _flow(rotation, "SP500"),
        "credit": _mean([_flow(rotation, "HYG"), -_flow(rotation, "LQD") if _flow(rotation, "LQD") is not None else None]),
        "metals": _mean([_flow(rotation, "XAUUSD"), _flow(rotation, "XAGUSD")]),
        "energy": _flow(rotation, "BRENT"),
        "crypto": _mean([_flow(rotation, "BTCUSD"), _flow(rotation, "ETHUSD")]),
    }
    # Published flow outranks positioning and price proxies on the same axis;
    # the proxy remains visible for divergence audits.
    flows = {axis: _selected_flow(flow_state, axis, value) for axis, value in flows.items()}
    for axis in ("usd", "treasury", "equity", "credit", "metals", "energy", "crypto", "defensive"):
        flow_state.setdefault(axis, {
            "value": flows.get(axis),
            "source_type": "DERIVED" if axis == "defensive" and flows.get(axis) is not None else "UNAVAILABLE" if flows.get(axis) is None else "PRICE_FLOW_PROXY",
            "source": "world_state_derived" if axis == "defensive" else None,
            "confidence": 0.0 if flows.get(axis) is None else 0.35,
            "coverage": 0.0 if flows.get(axis) is None else 1.0,
            "independence_weight": 0.35 if flows.get(axis) is not None else 0.0,
            "freshness_seconds": None,
            "evidence": [],
        })
    usd = flows["usd"]
    equity = flows["equity"]
    treasury = flows["treasury"]
    credit_flow = flows["credit"]
    credit_stress = _clamp(-credit_flow) if credit_flow is not None else None
    events = _geo_events(snapshot, current, config) if config.get("geopolitical_enabled", True) else ()
    from packages.discovery import build_world_candidates
    from packages.physical import build_assessments as build_physical_assessments
    from packages.scenarios import build_report as build_scenario_report
    from packages.world_graph import build_context as build_world_graph_context

    graph_context = build_world_graph_context(events).to_dict()
    physical_commodity = build_physical_assessments(graph_context)
    scenario_report = build_scenario_report(events).to_dict()
    asset_discovery = build_world_candidates(graph_context, scenario_report)
    statements = _statements(snapshot, current, config) if config.get("statements_enabled", True) else ()
    macro_surprises = _macro_surprises(snapshot, current, config) if config.get("statements_enabled", True) else ()
    expectations = _expectations(snapshot, statements, current)
    interactions = _event_interactions(events, macro_surprises)
    geo = _mean([e.severity * e.source_confidence for e in events if e.confirmed_action])
    energy_risk = _mean([e.energy_exposure * (e.severity or 0.0) * e.source_confidence for e in events])
    shipping = _mean([e.shipping_exposure * (e.severity or 0.0) * e.source_confidence for e in events])
    sanctions = _mean([e.financial_sanctions_exposure * (e.severity or 0.0) * e.source_confidence for e in events])
    trade = _mean([e.trade_exposure * (e.severity or 0.0) * e.source_confidence for e in events])
    us02y, us02y_source = _macro_signal(snapshot, "US02Y")
    us10y, us10y_source = _macro_signal(snapshot, "US10Y")
    rates = _mean([us02y, us10y])
    cpi_signal, cpi_source = _macro_signal(snapshot, "CPI")
    surprise_inflation = _mean([item.inflation_contribution for item in macro_surprises])
    surprise_growth = _mean([item.growth_contribution for item in macro_surprises])
    surprise_rates = _mean([item.rates_contribution for item in macro_surprises])
    surprise_oil = _mean([item.oil_contribution for item in macro_surprises])
    # Tek sürpriz tablosu açıkken (EYAY_MACRO_MATRIX_ENABLED) sürpriz faktörlere
    # karıştırılmaz; varlık başına yön nedensellik katmanında tablodan eklenir.
    from packages.macro import matrix as surprise_matrix

    blend = not surprise_matrix.enabled()
    inflation = _blend_pressure(_mean([cpi_signal, energy_risk, sanctions, flows["energy"] if flows["energy"] is not None and flows["energy"] > 0 else None]), surprise_inflation if blend else None)
    growth = _blend_pressure(_mean([equity, -trade if trade is not None else None]), surprise_growth if blend else None, 0.75)
    rates = _blend_pressure(rates, surprise_rates if blend else None)
    oil_pressure = _blend_pressure(flows["energy"], surprise_oil if blend else None)
    interaction_by_channel: dict[str, list[float]] = {}
    for interaction in interactions:
        interaction_by_channel.setdefault(interaction.channel, []).append(interaction.contribution)
    # One central channel map keeps every supported interaction auditable.  A
    # bounded blend means pairwise evidence can explain/adjust a direct factor
    # but can never replace it or create a new shock from nothing.
    interaction_cfg = config.get("interaction") or {}
    interaction_weight = max(0.0, min(0.5, float(interaction_cfg.get("weight", 0.15) or 0.15)))
    interaction_map = {
        "inflation_pressure": "inflation_pressure",
        "growth_pressure": "growth_pressure",
        "rates_pressure": "rates_pressure",
        "oil_pressure": "oil_pressure",
        "risk_aversion": "risk_aversion",
        "energy_supply_risk": "energy_supply_risk",
        "shipping_risk": "shipping_risk",
        "trade_risk": "trade_risk",
        "sanctions_pressure": "sanctions_pressure",
        "liquidity": "liquidity",
    }
    interaction_values = {key: _mean(interaction_by_channel.get(channel, [])) for channel, key in interaction_map.items()}
    inflation = _blend_pressure(inflation, interaction_values["inflation_pressure"], interaction_weight)
    growth = _blend_pressure(growth, interaction_values["growth_pressure"], interaction_weight)
    rates = _blend_pressure(rates, interaction_values["rates_pressure"], interaction_weight)
    oil_pressure = _blend_pressure(oil_pressure, interaction_values["oil_pressure"], interaction_weight)
    energy_risk = _blend_pressure(energy_risk, interaction_values["energy_supply_risk"], interaction_weight)
    shipping = _blend_pressure(shipping, interaction_values["shipping_risk"], interaction_weight)
    trade = _blend_pressure(trade, interaction_values["trade_risk"], interaction_weight)
    sanctions = _blend_pressure(sanctions, interaction_values["sanctions_pressure"], interaction_weight)
    risk_aversion_interaction = _mean(interaction_by_channel.get("risk_aversion", []))
    real_yield = _clamp(rates - (inflation or 0.0) * 0.5) if rates is not None else None
    risk_aversion = _blend_pressure(_mean([-equity if equity is not None else None, credit_stress, shipping]), risk_aversion_interaction, interaction_weight)
    liquidity = _mean([flows["crypto"], equity, -usd if usd is not None else None, -rates if rates is not None else None, credit_flow])
    liquidity = _blend_pressure(liquidity, interaction_values["liquidity"], interaction_weight)
    defensive = _mean([treasury, -usd if usd is not None else None, flows["metals"]])
    flow_state["defensive"] = {
        "value": defensive,
        "source_type": "DERIVED" if defensive is not None else "UNAVAILABLE",
        "source": "world_state_derived",
        "confidence": 0.35 if defensive is not None else 0.0,
        "coverage": 1.0 if defensive is not None else 0.0,
        "independence_weight": 0.35 if defensive is not None else 0.0,
        "freshness_seconds": None,
        "evidence": ["treasury/usd/metals composite"] if defensive is not None else [],
    }
    flow_axis_values = [*list(flows.values()), defensive]
    flow_coverage = round(sum(value is not None for value in flow_axis_values) / len(flow_axis_values), 4)
    macro_values = [rates, real_yield, inflation, growth, usd]
    macro_coverage = round(sum(value is not None for value in macro_values) / len(macro_values), 4)
    geo_coverage = round(sum(e.source_confidence > 0 for e in events) / max(1, len(events)), 4) if events else 0.0
    statement_coverage = round(sum(s.source_confidence > 0 for s in statements) / max(1, len(statements)), 4) if statements else 0.0
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
    from packages.macro.evidence import build_macro_evidence
    macro_evidence = build_macro_evidence(snapshot, regime=flow_regime)
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
        macro_surprises=macro_surprises,
        macro_evidence=macro_evidence,
        macro_surprise_inflation=surprise_inflation,
        macro_surprise_growth=surprise_growth,
        macro_surprise_rates=surprise_rates,
        macro_surprise_oil=surprise_oil,
        positioning=positioning,
        flow_state=flow_state,
        flow_observations=flow_observations,
        expectations=expectations,
        interactions=interactions,
        provenance={
            "snapshot_as_of": current,
            "market_data_as_of": getattr(snapshot, "market_data_as_of", None),
            "events_available_as_of": getattr(snapshot, "events_available_as_of", None),
            "statements_available_as_of": getattr(snapshot, "statements_available_as_of", None),
            "macro_available_as_of": getattr(snapshot, "macro_available_as_of", None),
            "expectations_as_of": getattr(snapshot, "expectations_as_of", None),
            "flow_available_as_of": getattr(snapshot, "flow_available_as_of", None),
            "ingested_at": getattr(snapshot, "ingested_at", None),
            "domains": getattr(snapshot, "provenance_domains", None) or {},
        },
        schema_version=2,
        causal_config_version=str(config.get("config_version") or "v1.0"),
        regime=flow_regime,
        graph_context=graph_context,
        physical_commodity=physical_commodity,
        scenario_report=scenario_report,
        asset_discovery=asset_discovery,
        macro_sources={
            "US02Y": us02y_source,
            "US10Y": us10y_source,
            "CPI": cpi_source,
            "growth": {"source_type": "PROXY", "source": "equity_flow" if equity is not None else "UNAVAILABLE", "components": ["SP500", "trade_risk"]},
            "real_yield": {"source_type": "DERIVED", "method": "rates_pressure_minus_inflation_pressure" if rates is not None and inflation is not None else "UNAVAILABLE"},
        },
        sanctions_pressure=sanctions,
        trade_risk=trade,
        oil_pressure=oil_pressure,
    )
