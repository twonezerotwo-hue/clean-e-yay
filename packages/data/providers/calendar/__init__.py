"""Olay takvimi sağlayıcısı — gerçek YAML calendar (P0 legacy parity).

`config/event_calendar.yaml`'dan okur (eski Codex EventCalendarService
portu). Politika ([docs/DATA_POLICY.md]):
- Runtime'da **mock event yasaktır**. Dosya yoksa/bozuksa boş liste döner;
  pipeline `calendar_unavailable` warning ekler, provider status DEGRADED.
- Fixture event'ler yalnızca test/dev path (`TEST_USE_MOCK=true` veya
  `CALENDAR_USE_FIXTURE=true`) ve `verified=False` damgalı — event risk
  gate'i verified olmayan event'leri SAYMAZ.

Event risk yalnızca kısıtlayıcıdır: RiskGate'e `packages/risk/event_risk.py`
üzerinden bağlanır, asla size artırmaz / gate gevşetmez.
"""
from __future__ import annotations

import hashlib
import os
import threading
from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path

import yaml

from packages.data.types import Catalyst, utcnow

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CALENDAR_PATH = _REPO_ROOT / "config" / "event_calendar.yaml"

# Legacy importance → Clean Catalyst.importance
_IMPORTANCE_MAP = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
}

_LOCK = threading.Lock()
_STATUS: dict[str, dict] = {
    "calendar": {
        "status": "unknown",
        "last_success_at": None,
        "last_error": None,
        "calls": 0,
        "fallbacks": 0,
    }
}


def _truthy(v: str | None) -> bool:
    return (v or "").lower() == "true"


def is_fixture_mode() -> bool:
    """Test/dev fixture path açık mı? Runtime'da false kalmalıdır."""
    return _truthy(os.environ.get("TEST_USE_MOCK")) or _truthy(
        os.environ.get("CALENDAR_USE_FIXTURE")
    )


def _mark(*, ok: bool, error: str | None = None) -> None:
    with _LOCK:
        st = _STATUS["calendar"]
        st["calls"] += 1
        if ok:
            st["status"] = "ok"
            st["last_success_at"] = datetime.now(UTC).isoformat()
            st["last_error"] = None
        else:
            st["status"] = "degraded"
            if error:
                st["last_error"] = error


def get_provider_status() -> dict[str, dict]:
    with _LOCK:
        return {k: dict(v) for k, v in _STATUS.items()}


def reset_provider_status() -> None:
    with _LOCK:
        for v in _STATUS.values():
            v.update(
                status="unknown",
                last_success_at=None,
                last_error=None,
                calls=0,
                fallbacks=0,
            )


# ---------------------------------------------------------------------------
# Fixture (yalnızca test/dev) — verified=False, karar zincirine girmez
# ---------------------------------------------------------------------------

_FIXTURE_EVENTS: list[tuple[str, str, int]] = [
    # (title, importance, hours_from_now)
    ("US CPI (YoY)", "high", 4),
    ("FOMC Minutes", "high", 26),
    ("ECB Press Conference", "medium", 51),
    ("US Initial Jobless Claims", "low", 8),
    ("China Industrial Production", "medium", 34),
    ("OPEC+ Monthly Report", "medium", 14),
]


def _fixture_catalysts(limit: int) -> list[Catalyst]:
    now = utcnow()
    out: list[Catalyst] = []
    for i, (title, imp, h) in enumerate(_FIXTURE_EVENTS[:limit]):
        cid = hashlib.sha1(f"fixture|{title}|{i}".encode()).hexdigest()[:10]
        ts = now + timedelta(hours=h)
        out.append(
            Catalyst(
                id=cid,
                ts=ts,
                title=title,
                importance=imp,  # type: ignore[arg-type]
                days_until=(ts.date() - now.date()).days,
                hours_until=round(h, 1),
                source="fixture",
                verified=False,
            )
        )
    return out


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

def list_catalysts(
    limit: int = 10,
    *,
    horizon_days: int = 120,
    yaml_path: Path | None = None,
    reference: datetime | None = None,
) -> list[Catalyst]:
    """Bugünden `horizon_days` içindeki event'ler, yakın tarihten uzağa.

    Veri yoksa boş liste — asla mock, asla crash.
    """
    if yaml_path is None and is_fixture_mode():
        return _fixture_catalysts(limit)

    path = yaml_path or DEFAULT_CALENDAR_PATH
    now = reference or utcnow()
    today = now.date()

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        raw_events = data.get("events") or []
        if not isinstance(raw_events, list):
            raise ValueError("events is not a list")
    except Exception as exc:
        _mark(ok=False, error=str(exc)[:160] or "calendar load failed")
        return []

    out: list[Catalyst] = []
    for ev in raw_events:
        try:
            ev_date = datetime.strptime(str(ev["date"]), "%Y-%m-%d").date()
        except (KeyError, TypeError, ValueError):
            continue
        days_until = (ev_date - today).days
        if days_until < 0 or days_until > horizon_days:
            continue
        # Event saat bilgisi taşımaz — gün ortası (12:00 UTC) kabul edilir;
        # hours_until risk penceresi için yaklaşık değerdir.
        ev_ts = datetime.combine(ev_date, dt_time(12, 0), tzinfo=UTC)
        hours_until = round((ev_ts - now).total_seconds() / 3600, 1)
        importance = _IMPORTANCE_MAP.get(str(ev.get("importance", "")).upper(), "medium")
        out.append(
            Catalyst(
                id=str(ev.get("id") or hashlib.sha1(str(ev).encode()).hexdigest()[:10]),
                ts=ev_ts,
                title=str(ev.get("name", "")),
                importance=importance,  # type: ignore[arg-type]
                region=ev.get("region"),
                category=ev.get("category"),
                market_impact=ev.get("market_impact"),
                days_until=days_until,
                hours_until=hours_until,
                source="event_calendar.yaml",
                verified=True,
            )
        )

    if not out:
        _mark(ok=False, error="no upcoming events in calendar")
        return []

    out.sort(key=lambda c: c.ts)
    _mark(ok=True)
    return out[:limit]
