"""News-driven paper setup preparation.

The module stores expiring world/news intents only.  It never opens a position
and never weakens a gate.  The canonical tick decision loop remains the sole
place that can call :func:`packages.paper.lifecycle.attempt_open`; a prepared
setup is marked ``ACTIVATED`` when that loop later creates the matching paper
position.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from packages.data.registry import assets as asset_registry
from packages.data.registry.loader import load_thresholds
from packages.paper.state import NewsPreparedSetup, PaperState

_RISK_BLOCKS = {"KILL_SWITCH", "RISK_REDUCE", "NO_POSITION_INCREASE"}
_EVIDENCE_TAG = re.compile(r"^[A-Za-z_]+:\S")  # "causal:BTCUSD/1d" gibi etiketler başlık değildir
_ASSET_REFERENCE_TERMS = frozenset({
    "bitcoin", "btc", "ethereum", "ether", "eth", "xrp", "ripple",
    "solana", "sol", "near", "qrl", "quant", "gold", "altın", "silver",
    "gümüş", "oil", "petrol", "brent", "wti", "natural gas", "natgas",
    "lng", "dollar", "usd", "euro", "stocks", "equity", "sp500", "s&p",
})


def is_live(setup: NewsPreparedSetup, now: datetime | None = None) -> bool:
    """Read-only active check used by API views as well as the worker.

    A stale persisted row is presented as expired immediately; a background
    tick is not required for the dashboard to stop calling it actionable.
    """
    if setup.status not in {"WAITING_RISK", "ARMED"}:
        return False
    deadline = _parse_time(setup.valid_until)
    return deadline is None or deadline > (now or datetime.now(UTC))


def view(setup: NewsPreparedSetup, now: datetime | None = None) -> dict[str, Any]:
    data = asdict(setup)
    if setup.status in {"WAITING_RISK", "ARMED"} and not is_live(setup, now):
        data["status"] = "EXPIRED"
        data["last_blocker"] = "news_setup_expired"
    return data


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _cfg() -> dict[str, Any]:
    raw = load_thresholds().get("news_prepared_setups") or {}
    return {
        "enabled": bool(raw.get("enabled", True)),
        "min_confidence": float(raw.get("min_confidence", 0.55)),
        "min_abs_world_score": float(raw.get("min_abs_world_score", 0.15)),
        "ttl_hours": max(1.0, float(raw.get("ttl_hours", 72))),
        "max_active": max(1, int(raw.get("max_active", 16))),
    }


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _setup_id(symbol: str, timeframe: str, side: str, event_id: str) -> str:
    raw = f"{event_id}|{symbol}|{timeframe}|{side}"
    return "news::" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _event_context(world_state: Mapping[str, Any]) -> tuple[str, str, str, datetime | None, list[str]]:
    events = [item for item in (world_state.get("geopolitical_events") or ()) if isinstance(item, Mapping)]
    event = events[0] if events else {}
    event_id = str(event.get("event_id") or event.get("id") or "world-event")
    event_type = str(event.get("event_type") or "WORLD_EVENT")
    evidence = [str(item) for item in (event.get("evidence") or ()) if item]
    # Etiket olayın KENDİ kanıt başlığıdır. Eskiden snapshot'ın ilk başlığı (olayla
    # ilgisiz olabilir: "BNY–Kraken" başlığı TEM/NVDA kayıtlarına yapışıyordu) kullanılıyordu.
    title = next((e.strip() for e in evidence if e.strip() and not _EVIDENCE_TAG.match(e)), "")
    title = title or event_type.replace("_", " ").title()
    valid_until = _parse_time(event.get("valid_until"))
    return event_id, event_type, title[:240], valid_until, evidence[:8]


def _symbol_terms(symbol: str) -> set[str]:
    """Small deterministic alias set for evidence-to-asset binding."""
    value = str(symbol or "").upper()
    terms = {value.casefold()}
    if value.endswith("USD"):
        terms.add(value[:-3].casefold())
    aliases = {
        "BTCUSD": {"bitcoin", "crypto", "kripto", "stablecoin"},
        "ETHUSD": {"ethereum", "ether", "crypto", "kripto", "stablecoin"},
        "XAUUSD": {"gold", "altın", "metals", "precious metal", "metal"},
        "XAGUSD": {"silver", "gümüş", "metals", "precious metal", "metal"},
        "BRENT": {"oil", "petrol", "brent", "opec", "refinery", "pipeline", "energy"},
        "WTI": {"oil", "petrol", "wti", "opec", "refinery", "pipeline", "energy"},
        "NATGAS": {"natural gas", "natgas", "lng", "gas", "energy"},
        "DXY": {"dollar", "usd", "fed", "treasury", "yield"},
        "SP500": {"stock", "stocks", "equity", "s&p", "sp500", "market"},
        "SPY": {"stock", "stocks", "equity", "s&p", "sp500", "market"},
    }
    return terms | aliases.get(value, set())


def _event_context_for_symbol(
    world_state: Mapping[str, Any], symbol: str,
) -> tuple[str, str, str, datetime | None, list[str]] | None:
    """Select only an event whose evidence can be tied to this asset.

    A causal macro event may still influence several assets. When the snapshot
    contains exactly one event and it has no asset-specific match, that event
    is the only available world context and may be used as a global thesis;
    with multiple events an unrelated headline is never copied to a candidate.
    """
    terms = _symbol_terms(symbol)
    events = [item for item in (world_state.get("geopolitical_events") or ()) if isinstance(item, Mapping)]
    for event in events:
        evidence = [str(item) for item in (event.get("evidence") or ()) if item]
        haystack = " ".join(evidence).casefold()
        if any(term in haystack for term in terms):
            event_id = str(event.get("event_id") or event.get("id") or "world-event")
            event_type = str(event.get("event_type") or "WORLD_EVENT")
            title = next((e.strip() for e in evidence if e.strip() and not _EVIDENCE_TAG.match(e)), "")
            title = title or event_type.replace("_", " ").title()
            return (
                event_id, event_type, title[:240], _parse_time(event.get("valid_until")), evidence[:8]
            )
    if len(events) == 1:
        # There is no competing event to mis-bind. The causal consensus and
        # its confidence still gate setup creation; this fallback only keeps a
        # single global world event available to paper preparation.
        event = events[0]
        evidence = [str(item) for item in (event.get("evidence") or ()) if item]
        haystack = " ".join(evidence).casefold()
        # A single event is not automatically global: an explicit reference
        # to another asset must remain unbound rather than leak into this one.
        if any(term in haystack for term in _ASSET_REFERENCE_TERMS if term not in terms):
            return None
        event_id = str(event.get("event_id") or event.get("id") or "world-event")
        event_type = str(event.get("event_type") or "WORLD_EVENT")
        title = next((e.strip() for e in evidence if e.strip() and not _EVIDENCE_TAG.match(e)), "")
        title = title or event_type.replace("_", " ").title()
        return (
            event_id, event_type, title[:240], _parse_time(event.get("valid_until")), evidence[:8]
        )
    return None


def _forecast_map(shadow: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in shadow.get("forecasts") or ():
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol") or "")
        horizon = str(row.get("horizon") or "")
        if symbol and horizon:
            result[(symbol, horizon)] = row
    return result


def _direction(row: Mapping[str, Any]) -> tuple[str | None, float | None]:
    raw = str(row.get("world_thesis_direction") or row.get("final_shadow_direction") or "").upper()
    score = _float(row.get("world_score"))
    if raw in {"BULLISH", "BEARISH"}:
        return ("long" if raw == "BULLISH" else "short"), score
    causal = _float(row.get("causal_score"))
    if causal is not None:
        if causal >= 57.5:
            return "long", causal
        if causal <= 42.5:
            return "short", causal
    return None, score


def sync(
    state: PaperState,
    *,
    causal_shadow: Mapping[str, Any],
    world_state: Mapping[str, Any],
    prices: Mapping[str, float],
    decisions: Iterable[Any],
    risk_action: str,
    snapshot_id: str | None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Refresh the expiring news setup queue and mark canonical activations.

    A setup is only evidence-backed and trade-universe-backed.  It is never
    created from a raw headline without a verified world event and causal
    direction.  Existing positions are used solely to annotate activation;
    this function does not mutate the trading book.
    """
    cfg = _cfg()
    now = now or datetime.now(UTC)
    if not cfg["enabled"]:
        return {"created": 0, "updated": 0, "expired": 0, "activated": 0}

    events = world_state.get("geopolitical_events") or ()
    if not events:
        return {"created": 0, "updated": 0, "expired": 0, "activated": 0}

    trade_symbols = set(asset_registry.trade_symbols())
    forecasts = _forecast_map(causal_shadow)
    decisions_by_key = {
        (str(getattr(d, "symbol", "")), str(getattr(d, "timeframe", ""))): d
        for d in decisions
    }
    open_keys = {(p.symbol, p.timeframe, p.side) for p in state.open_positions}
    counts = {"created": 0, "updated": 0, "expired": 0, "activated": 0}

    for setup in state.news_prepared_setups:
        deadline = _parse_time(setup.valid_until)
        if deadline is not None and deadline <= now and setup.status not in {"ACTIVATED", "EXPIRED"}:
            setup.status = "EXPIRED"
            setup.last_blocker = "news_setup_expired"
            counts["expired"] += 1
        elif setup.status in {"WAITING_RISK", "ARMED"} and _event_context_for_symbol(world_state, setup.symbol) is None:
            setup.status = "STALE"
            setup.last_blocker = "news_evidence_not_linked_to_asset"

    # An old setup must never be resurrected merely because a new event uses
    # the same symbol/timeframe/side.  Legacy rows without event_id are also
    # separated when their evidence title changed.
    existing = {
        (s.symbol, s.timeframe, s.side): s
        for s in state.news_prepared_setups
        if s.status not in {"EXPIRED", "STALE", "ACTIVATED"}
        and (_parse_time(s.valid_until) is None or _parse_time(s.valid_until) > now)
    }

    for row in causal_shadow.get("causal_consensus") or ():
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol") or "")
        timeframe = str(row.get("timeframe") or "")
        if symbol not in trade_symbols or timeframe not in {"15m", "1h", "4h", "1d"}:
            continue
        context = _event_context_for_symbol(world_state, symbol)
        if context is None:
            # No headline can be tied to this asset: keep the decision loop
            # available, but do not manufacture a news-prepared setup.
            continue
        event_id, event_type, title, event_valid_until, event_evidence = context
        valid_until = event_valid_until or (now + timedelta(hours=cfg["ttl_hours"]))
        if valid_until <= now:
            continue
        side, world_score = _direction(row)
        confidence = _float(row.get("confidence"))
        if side is None or confidence is None or confidence < cfg["min_confidence"]:
            continue
        if world_score is not None:
            distance = abs(world_score - 50.0) / 50.0 if world_score > 1 else abs(world_score)
            if distance < cfg["min_abs_world_score"]:
                continue
        price = _float(prices.get(symbol))
        if price is None or price <= 0:
            continue
        forecast = forecasts.get((symbol, "1d")) or forecasts.get((symbol, "1w")) or {}
        key = (symbol, timeframe, side)
        setup = existing.get(key)
        if setup is not None and (
            (getattr(setup, "event_id", None) and setup.event_id != event_id)
            or (not getattr(setup, "event_id", None) and setup.news_title != title)
        ):
            setup = None
        if setup is None:
            # A new world event supersedes an older live setup for the same
            # symbol/TF/side; keeping both would make the UI report duplicate
            # actionable evidence with different news titles.
            for prior in state.news_prepared_setups:
                if (
                    (prior.symbol, prior.timeframe, prior.side) == key
                    and is_live(prior, now)
                    and getattr(prior, "event_id", None) != event_id
                ):
                    prior.status = "STALE"
                    prior.last_blocker = "superseded_by_new_world_event"
            setup = NewsPreparedSetup(
                id=_setup_id(symbol, timeframe, side, event_id),
                symbol=symbol,
                timeframe=timeframe,
                side=side,
                created_at=_iso(now),
                valid_until=_iso(valid_until),
                event_id=event_id,
                world_direction="BULLISH" if side == "long" else "BEARISH",
                world_score=world_score,
                confidence=confidence,
                technical_confirmation=_float(row.get("technical_confirmation")),
                confluence_state=str(row.get("confluence_state") or "UNKNOWN"),
                current_price=price,
                point_estimate=_float(forecast.get("point_estimate")),
                p10=_float(forecast.get("p10")), p50=_float(forecast.get("p50")), p90=_float(forecast.get("p90")),
                event_type=event_type, news_title=title,
                evidence=[*event_evidence, f"causal:{symbol}/{timeframe}", f"confidence:{confidence:.2f}"],
                snapshot_id=snapshot_id,
            )
            state.news_prepared_setups.append(setup)
            existing[key] = setup
            counts["created"] += 1
        else:
            setup.event_id = event_id
            setup.valid_until = _iso(valid_until)
            setup.news_title = title
            setup.current_price = price
            setup.world_score = world_score
            setup.confidence = confidence
            setup.last_checked_at = _iso(now)
            setup.snapshot_id = snapshot_id
            counts["updated"] += 1

        setup.last_checked_at = _iso(now)
        decision = decisions_by_key.get((symbol, timeframe))
        if key in open_keys:
            if setup.status != "ACTIVATED":
                setup.status = "ACTIVATED"
                setup.last_blocker = None
                counts["activated"] += 1
        elif risk_action in _RISK_BLOCKS:
            setup.status = "WAITING_RISK"
            setup.last_blocker = f"risk_gate:{risk_action}"
        elif decision is not None and str(getattr(decision, "action", "")) in {"open_long", "open_short"}:
            setup.status = "ARMED"
            setup.last_blocker = None
        else:
            setup.status = "ARMED"
            setup.last_blocker = "technical_or_consensus_recheck"

    active = [s for s in state.news_prepared_setups if s.status in {"WAITING_RISK", "ARMED"}]
    if len(active) > cfg["max_active"]:
        active.sort(key=lambda item: item.created_at, reverse=True)
        keep = {item.id for item in active[: cfg["max_active"]]}
        for setup in active[cfg["max_active"] :]:
            if setup.id not in keep:
                setup.status = "STALE"
                setup.last_blocker = "news_setup_capacity"
    # Keep terminal records bounded so the JSON state cannot grow forever.
    state.news_prepared_setups = state.news_prepared_setups[-max(32, cfg["max_active"] * 4) :]
    return counts


__all__ = ["is_live", "sync", "view"]
