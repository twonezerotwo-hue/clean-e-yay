"""Public economic-calendar web observer (shadow-only).

Investing.com publishes the calendar rows in the page's JSON state. This
observer reads that public page, keeps the rows unverified, and never feeds the
verified event-risk gate or opens a position by itself.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime

from packages.data.types import Catalyst, utcnow

SOURCE = "investing_web_calendar"
ENDPOINT = "https://www.investing.com/economic-calendar?lang=1"
USER_AGENT = "clean-e-yay/1.0 (public-calendar-observer)"
TIMEOUT_SEC = 8
TTL_SEC = 900

_STATUS: dict[str, object] = {
    "status": "unknown",
    "last_success_at": None,
    "last_error": None,
    "calls": 0,
    "fallbacks": 0,
    "events": 0,
}
_LOCK = threading.Lock()
_CACHE: tuple[float, list[Catalyst]] | None = None


def _enabled() -> bool:
    # The observer is enabled for normal runtime, but never makes fixture tests
    # reach the network. CALENDAR_WEB_SHADOW=false is the explicit kill switch.
    if os.environ.get("TEST_USE_MOCK", "").lower() == "true":
        return False
    return os.environ.get("CALENDAR_WEB_SHADOW", "true").lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def get_provider_status() -> dict[str, dict]:
    with _LOCK:
        return {"calendar_web": dict(_STATUS)}


def reset_provider_status() -> None:
    global _CACHE
    with _LOCK:
        _STATUS.update(
            status="unknown",
            last_success_at=None,
            last_error=None,
            calls=0,
            fallbacks=0,
            events=0,
        )
        _CACHE = None


def _mark(*, status: str, error: str | None = None, events: int = 0) -> None:
    with _LOCK:
        _STATUS["calls"] = int(_STATUS.get("calls", 0)) + 1
        _STATUS["status"] = status
        _STATUS["last_error"] = error
        _STATUS["events"] = events
        if status == "ok":
            _STATUS["last_success_at"] = datetime.now(UTC).isoformat()


def _value(raw: object) -> float | None:
    text = html.unescape(str(raw or "")).strip().replace(",", "")
    if not text or text in {"-", "—", "N/A", "n/a"}:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        value = float(match.group(0))
    except ValueError:
        return None
    suffix = text[match.end() :].lstrip().upper()[:1]
    return value * {"K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0}.get(suffix, 1.0)


def _unit(raw: object) -> str | None:
    text = html.unescape(str(raw or "")).strip().upper()
    if not text:
        return None
    if "%" in text:
        return "percent"
    if text.endswith(("K", "M", "B")):
        return "scaled_count"
    return "number"


def _importance(raw: object) -> str:
    try:
        level = int(str(raw or "0"))
    except ValueError:
        level = 0
    return {0: "low", 1: "low", 2: "medium", 3: "high"}.get(level, "critical")


def _timestamp(row: dict, *, now: datetime) -> datetime:
    raw = str(row.get("time") or "")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    except ValueError:
        try:
            value = datetime.strptime(str(row.get("date")), "%Y-%m-%d")
        except ValueError:
            return now.replace(hour=12, minute=0, second=0, microsecond=0)
        return value.replace(tzinfo=UTC, hour=12)


def parse_events(body: str, *, now: datetime | None = None) -> list[Catalyst]:
    """Extract Investing's embedded calendar state without executing scripts."""
    reference = now or utcnow()
    marker = body.find("calendarEventsByDate")
    if marker < 0:
        return []
    start = body.find("{", marker)
    if start < 0:
        return []
    try:
        grouped, _ = json.JSONDecoder().raw_decode(html.unescape(body[start:]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(grouped, dict):
        return []

    out: list[Catalyst] = []
    for rows in grouped.values():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or not str(row.get("event") or "").strip():
                continue
            ts = _timestamp(row, now=reference)
            event_id = row.get("occurrenceId") or row.get("eventId")
            raw_id = f"{SOURCE}|{event_id}|{ts.isoformat()}|{row.get('event')}"
            out.append(
                Catalyst(
                    id=str(event_id or hashlib.sha1(raw_id.encode()).hexdigest()[:16]),
                    ts=ts,
                    title=str(row.get("event")),
                    importance=_importance(row.get("importance")),
                    region=str(row.get("country") or row.get("currencyFlag") or "") or None,
                    category="MACRO_WEB_SHADOW",
                    market_impact="web calendar consensus; unverified",
                    days_until=(ts.date() - reference.date()).days,
                    hours_until=round((ts - reference).total_seconds() / 3600, 1),
                    source=SOURCE,
                    verified=False,
                    actual=_value(row.get("actual")),
                    expected=_value(row.get("forecast")),
                    previous=_value(row.get("previous")),
                    revised=_value(row.get("revised")),
                    unit=_unit(row.get("actual") or row.get("forecast") or row.get("previous")),
                )
            )
    return out


def _fetch(now: datetime) -> list[Catalyst]:
    request = urllib.request.Request(
        ENDPOINT,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
        body = response.read(2_000_000).decode("utf-8", "replace")
    return parse_events(body, now=now)


def list_catalysts(*, now: datetime | None = None, horizon_days: int = 120) -> list[Catalyst]:
    """Return cached, unverified public-calendar rows for shadow comparison."""
    global _CACHE
    if not _enabled():
        _mark(status="disabled")
        return []
    reference = now or utcnow()
    cached = _CACHE
    if cached and (datetime.now(UTC).timestamp() - cached[0]) < TTL_SEC:
        return [item for item in cached[1] if -1 <= item.days_until <= horizon_days]
    try:
        events = _fetch(reference)
    except (OSError, urllib.error.URLError, ValueError) as exc:
        _mark(status="degraded", error=str(exc)[:160])
        return []
    _CACHE = (datetime.now(UTC).timestamp(), events)
    _mark(status="ok", events=len(events))
    return [item for item in events if -1 <= item.days_until <= horizon_days]
