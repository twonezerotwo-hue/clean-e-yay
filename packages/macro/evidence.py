"""Build one deterministic identity for macro/news/technical evidence.

This module does not fetch data and never emits an order.  Missing values stay
missing.  The returned dictionaries are compact references suitable for a
snapshot, replay and dashboard; raw provider payloads remain in their owners.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from packages.data.providers.news.provenance import source_family, story_key
from packages.paper.signal_identity import build_evidence_id

_ASSET_ALIASES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("brent", "wti", "crude", "oil", "petrol", "opec", "eia", "hormuz", "houthi"), ("BRENT", "WTI")),
    (("natural gas", "natgas", "lng", "gas supply"), ("NATGAS",)),
    (("gold", "altın", "xau"), ("XAUUSD",)),
    (("silver", "gümüş", "xag"), ("XAGUSD",)),
    (("dollar", "dxy", "fed", "fomc", "interest rate", "inflation", "cpi", "pce", "jobs", "nfp", "payroll", "adp", "jolts", "job openings", "employment cost", "eci", "wage"), ("DXY",)),
    (("treasury", "yield", "bond", "us10y", "interest rate", "fed", "fomc", "inflation"), ("US10Y",)),
    (("nasdaq", "s&p", "sp500", "equity", "stocks", "stock market", "ai spending"), ("SP500",)),
    (("ism", "manufacturing pmi", "services pmi", "durable goods", "durable orders"), ("SP500", "COPPER")),
    (("bitcoin", "btc", "crypto", "ethereum", "eth", "digital asset"), ("BTCUSD", "ETHUSD")),
)

_RISK_ON = ("ceasefire", "peace", "truce", "rate cut", "easing", "stimulus", "de-escalat", "barış", "ateşkes")
_RISK_OFF = ("war", "attack", "strike", "sanction", "blockade", "escalat", "missile", "invasion", "savaş", "saldırı", "yaptırım")
_INFLATION = ("inflation", "cpi", "pce", "ppi", "price pressure", "enflasyon")
_JOBS = ("nfp", "nonfarm", "payroll", "adp", "private employment", "employment", "unemployment", "jobless", "jolts", "job openings", "employment cost", "eci", "wage", "işsizlik", "istihdam")
_OIL_INVENTORY = ("oil inventory", "crude inventory", "eia inventory", "stok")


def _text(item: Any) -> str:
    return " ".join(str(getattr(item, key, "") or "") for key in ("title", "title_tr", "category", "market_impact")).casefold()


def _assets(text: str, affected: Any) -> tuple[str, ...]:
    explicit = tuple(str(value).upper() for value in (affected or ()) if value)
    found: list[str] = list(explicit)
    for needles, symbols in _ASSET_ALIASES:
        if any(needle in text for needle in needles):
            found.extend(symbols)
    # Preserve deterministic order and do not create a fake market asset.
    return tuple(dict.fromkeys(found))


def _channel(text: str) -> str:
    if any(word in text for word in _OIL_INVENTORY):
        return "oil_supply"
    if any(word in text for word in ("natural gas", "gas storage", "lng")):
        return "energy_supply"
    if any(word in text for word in _INFLATION):
        return "inflation_rates"
    if any(word in text for word in _JOBS):
        return "growth_labor"
    if any(word in text for word in ("fed", "fomc", "ecb", "interest rate", "merkez bank")):
        return "monetary_policy"
    if any(word in text for word in ("war", "attack", "sanction", "blockade", "hormuz", "yemen", "iran", "ukraine", "israel")):
        return "geopolitics_supply_risk"
    return "market_news"


def _base_direction(text: str) -> str | None:
    if any(word in text for word in _RISK_ON):
        return "bullish"
    if any(word in text for word in _RISK_OFF):
        return "bearish"
    return None


def _asset_direction(base: str | None, asset: str) -> str | None:
    if base is None:
        return None
    # A supply shock normally raises energy/metals while pressuring risk assets.
    if asset in {"BRENT", "WTI", "NATGAS", "XAUUSD", "XAGUSD"} and base == "bearish":
        return "bullish"
    return base


def _surprise(actual: Any, expected: Any) -> float | None:
    if actual is None or expected is None:
        return None
    try:
        return round(float(actual) - float(expected), 8)
    except (TypeError, ValueError):
        return None


def _ts(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def _canonical_event_id(catalyst: Any, title: str) -> str:
    """Join compatible provider rows without trusting feed-specific IDs."""
    published = getattr(catalyst, "ts", None)
    day = published.astimezone(UTC).date().isoformat() if isinstance(published, datetime) else "unknown-day"
    # Calendar expectations and official observations are only comparable when
    # their units match.  For example, BLS CPI is an index while a calendar
    # forecast is usually a percentage; joining those would create a fake
    # surprise and contaminate every downstream consumer.
    unit = str(getattr(catalyst, "unit", None) or "unknown").casefold()
    topic = _event_topic(title)
    # A published macro observation is dated to its measurement period while
    # a calendar row is dated to the later release day.  For known macro
    # topics, use topic+unit as the identity so same-unit actual/forecast rows
    # can join across that release-date gap.  General news keeps the date to
    # avoid collapsing unrelated stories.
    macro_topics = {
        "core_pce", "pce", "core_cpi", "cpi", "ppi", "nfp",
        "unemployment", "jolts", "eci", "gdp", "adp", "ism_pmi", "durable_goods", "fed_policy", "oil_inventory", "natural_gas_storage",
    }
    key = f"macro|{topic}|{unit}" if topic in macro_topics else f"{day}|{topic}|{unit}"
    return "evt_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def _event_topic(title: str) -> str:
    value = title.casefold()
    rules = (
        (("core pce", "pcepilfe"), "core_pce"),
        (("pce", "personal consumption expenditures"), "pce"),
        (("core cpi", "core consumer price"), "core_cpi"),
        (("cpi", "consumer price index", "inflation"), "cpi"),
        (("ppi", "producer price"), "ppi"),
        (("nonfarm", "nfp", "payroll"), "nfp"),
        (("adp", "private payroll", "private employment"), "adp"),
        (("unemployment", "jobless"), "unemployment"),
        (("jolts", "job openings", "job opening"), "jolts"),
        (("employment cost", "eci", "wage"), "eci"),
        (("gdp", "gross domestic"), "gdp"),
        (("ism", "manufacturing pmi", "services pmi"), "ism_pmi"),
        (("durable goods", "durable-goods", "durable orders"), "durable_goods"),
        (("fed funds", "federal funds", "fomc", "rate decision"), "fed_policy"),
        (("crude inventory", "oil inventory", "eia"), "oil_inventory"),
        (("natural gas storage", "gas storage", "underground storage"), "natural_gas_storage"),
    )
    for needles, topic in rules:
        if any(needle in value for needle in needles):
            return topic
    return story_key(title)


def _technical(snapshot: Any, asset: str, regime: str, expected_direction: str | None) -> list[tuple[str, str, float | None, str | None]]:
    by_tf = getattr(snapshot, "technicals_by_tf", None) or {}
    rows = by_tf.get(asset) or {}
    if not rows:
        legacy = (getattr(snapshot, "technicals", None) or {}).get(asset)
        rows = {getattr(legacy, "timeframe", "1d"): legacy} if legacy is not None else {}
    if not rows:
        return [("event", "UNAVAILABLE", None, regime)]
    out: list[tuple[str, str, float | None, str | None]] = []
    for timeframe, item in sorted(rows.items()):
        if item is None:
            out.append((str(timeframe), "UNAVAILABLE", None, regime))
            continue
        score = getattr(item, "direction_score", None)
        if score is None:
            score = getattr(item, "score", None)
        bias = str(getattr(item, "ema_stack", "") or "").casefold()
        status = str(getattr(item, "status", "DEGRADED") or "DEGRADED").upper()
        confirmation = "UNAVAILABLE"
        if status != "OK" or score is None:
            confirmation = "DEGRADED"
        elif expected_direction == "bullish":
            confirmation = "CONFIRMED" if score >= 55 and bias != "bearish" else "CONTRADICTED"
        elif expected_direction == "bearish":
            confirmation = "CONFIRMED" if score <= 45 and bias != "bullish" else "CONTRADICTED"
        elif score >= 55 or score <= 45:
            confirmation = "NEUTRAL"
        elif 45 < score < 55:
            confirmation = "NEUTRAL"
        else:
            confirmation = "CONTRADICTED"
        out.append((str(timeframe), confirmation, float(score) if score is not None else None, regime))
    return out


def _region(value: Any) -> str:
    text = str(value or "").casefold().strip()
    return {"usd": "us", "usa": "us", "u.s.": "us", "united states": "us"}.get(text, text)


def _compatible_rows(left: Any, right: Any) -> bool:
    """Match one actual to one forecast without collapsing separate releases."""
    if _event_topic(str(getattr(left, "title", ""))) != _event_topic(str(getattr(right, "title", ""))):
        return False
    if str(getattr(left, "unit", None) or "").casefold() != str(getattr(right, "unit", None) or "").casefold():
        return False
    lreg, rreg = _region(getattr(left, "region", None)), _region(getattr(right, "region", None))
    if lreg and rreg and lreg != rreg:
        return False
    lts, rts = getattr(left, "ts", None), getattr(right, "ts", None)
    if isinstance(lts, datetime) and isinstance(rts, datetime) and abs(lts - rts).days > 45:
        return False
    return True


def _observation_groups(observations: list[Any]) -> list[tuple[str, list[Any]]]:
    """Create one stable group per actual/forecast pair.

    Provider IDs are intentionally not trusted.  Pairing is one-to-one and
    uses topic, unit, region and the nearest release time; separate releases
    of the same indicator remain separate evidence records.
    """
    rows = [row for row in observations if getattr(row, "id", None) and str(getattr(row, "title", "") or "")]
    used: set[str] = set()
    groups: list[tuple[str, list[Any]]] = []
    actuals = [row for row in rows if getattr(row, "actual", None) is not None and getattr(row, "verified", False)]
    for actual in sorted(actuals, key=lambda row: getattr(row, "ts", datetime.min)):
        candidates = [
            row for row in rows
            if row is not actual
            and str(getattr(row, "id", "")) not in used
            and getattr(row, "expected", None) is not None
            and _compatible_rows(actual, row)
        ]
        candidates.sort(key=lambda row: abs((getattr(row, "ts", datetime.min) - getattr(actual, "ts", datetime.min)).total_seconds()) if isinstance(getattr(row, "ts", None), datetime) and isinstance(getattr(actual, "ts", None), datetime) else 0.0)
        pair = candidates[0] if candidates else None
        items = [actual]
        used.add(str(getattr(actual, "id", "")))
        if pair is not None:
            items.append(pair)
            used.add(str(getattr(pair, "id", "")))
        anchor = pair or actual
        ts = getattr(anchor, "ts", None)
        day = ts.astimezone(UTC).date().isoformat() if isinstance(ts, datetime) else "unknown-day"
        topic = _event_topic(str(getattr(actual, "title", "")))
        unit = str(getattr(actual, "unit", None) or "unknown").casefold()
        region = _region(getattr(actual, "region", None)) or _region(getattr(pair, "region", None) if pair else None) or "unknown"
        event_id = "evt_" + hashlib.sha256(f"macro|{topic}|{unit}|{region}|{day}".encode()).hexdigest()[:20]
        groups.append((event_id, items))
    for row in rows:
        row_id = str(getattr(row, "id", ""))
        if row_id in used:
            continue
        groups.append((_canonical_event_id(row, str(getattr(row, "title", ""))), [row]))
    return groups


def build_macro_evidence(snapshot: Any, *, regime: str = "UNKNOWN", decision_id: str | None = None) -> tuple[dict[str, Any], ...]:
    """Return canonical, shadow-only evidence rows for one market snapshot."""
    result: list[dict[str, Any]] = []
    observations = [
        *(getattr(snapshot, "catalysts", ()) or ()),
        *(getattr(snapshot, "macro_releases", ()) or ()),
    ]
    for event_id, items in sorted(_observation_groups(observations), key=lambda item: item[0]):
        # Official actuals outrank shadow calendar values; the expectation can
        # come from the public calendar when the official release has none.
        ordered = sorted(items, key=lambda item: bool(getattr(item, "verified", False)), reverse=True)
        primary = ordered[0]
        official = next((item for item in ordered if getattr(item, "verified", False) and getattr(item, "actual", None) is not None), None)
        expected_item = next((item for item in items if getattr(item, "expected", None) is not None), None)
        provider_ids = [str(getattr(item, "id", "")) for item in items if getattr(item, "id", None)]
        families = sorted({source_family(getattr(item, "source", None), title=getattr(item, "title", None)) for item in items})
        text = " ".join(_text(item) for item in items)
        base = _base_direction(text)
        channel = _channel(text)
        actual = getattr(official or primary, "actual", None)
        expected = getattr(expected_item, "expected", None) if expected_item else None
        previous = getattr(official or primary, "previous", None)
        revised = getattr(official or primary, "revised", None)
        surprise = _surprise(actual, expected)
        # Numeric surprise is a signal only when it is explicitly available;
        # it is never converted into a default value.
        if surprise is not None and channel in {"inflation_rates", "growth_labor", "monetary_policy"}:
            if surprise > 0 and channel == "inflation_rates":
                base = "bearish"
            elif surprise < 0 and channel == "inflation_rates":
                base = "bullish"
        assets = _assets(text, tuple(
            asset for item in items for asset in (getattr(item, "affected_assets", None) or ())
        ))
        if not assets:
            continue
        for asset in assets:
            direction = _asset_direction(base, asset)
            for timeframe, confirmation, score, current_regime in _technical(snapshot, asset, regime, direction):
                source_id = "+".join(families)
                evidence_id = build_evidence_id(event_id=event_id, source_id=source_id, asset=asset, direction=direction, timeframe=timeframe, decision_id=decision_id)
                result.append({
                    "evidence_id": evidence_id,
                    "event_id": event_id,
                    "source_id": source_id,
                    "asset": asset,
                    "direction": direction,
                    "timeframe": timeframe,
                    "expected": expected,
                    "actual": actual,
                    "previous": previous,
                    "revised": revised,
                    "unit": getattr(official or primary, "unit", None),
                    "surprise": surprise,
                    "channel": channel,
                    "technical_confirmation": confirmation,
                    "technical_score": round(score, 4) if score is not None else None,
                    "correlation_regime": current_regime,
                    "decision_id": decision_id,
                    "verified": bool(getattr(official or primary, "verified", False)),
                    "published_at": _ts(getattr(official or primary, "ts", None)),
                    "ingested_at": _ts(getattr(snapshot, "ingested_at", None)),
                    "provenance": {
                        "source": getattr(primary, "source", None),
                        "source_family": families,
                        "provider_event_ids": provider_ids,
                        "titles": [str(getattr(item, "title", "")) for item in items],
                        "url": None,
                        "shadow_only": True,
                    },
                })
    return tuple(result)


__all__ = ["build_evidence_id", "build_macro_evidence"]
