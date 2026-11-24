"""Herkese açık ekonomik takvim — beklenti (konsensüs) kaynağı, doğrulanmamış gözlem.

ForexFactory'nin haftalık JSON'u (anahtarsız) açıklama zamanı, önem, beklenti ve
önceki değeri verir; gerçekleşen değer resmî kaynaktan (FRED, macro/derived.py)
gelir, sürpriz ikisinin farkıdır. Satırlar hiçbir zaman doğrulanmış sayılmaz,
olay riski kapısına girmez ve işlem açmaz. Gözlem kaynağıdır: erişim sorunu tick'i
DEGRADED yapmaz (sağlıkta ayrıca görünür).

Çekim en fazla saatte bir; satırlar diskte 21 gün tutulur (hafta dönünce geçen
haftanın beklentisi kaybolmasın, süreçler aynı dosyayı paylaşır). Çekim başarısızsa
diskteki gerçek satırlar kullanılır, durum 'degraded' olur. 25 Kasım 2026'ya dek
kaynak Investing sayfasıydı; bu IP'ye 403 veriyordu (anlık görüntülerin %98'i).
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
from datetime import UTC, datetime, timedelta
from pathlib import Path

from packages.data.types import Catalyst, utcnow
from packages.ops.store import write_text_atomic

SOURCE = "forexfactory_calendar"
ENDPOINT = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
USER_AGENT = "clean-e-yay/1.0 (public-calendar-reader)"
TIMEOUT_SEC = 8
TTL_SEC = 3600
KEEP_DAYS = 21

_STATUS: dict[str, object] = {
    "status": "unknown",
    "last_success_at": None,
    "last_error": None,
    "calls": 0,
    "fallbacks": 0,
    "events": 0,
}
_LOCK = threading.Lock()


def _path() -> Path:
    return Path(os.environ.get("CALENDAR_CONSENSUS_PATH", "data/runtime/calendar_consensus.json"))


def _fixture_mode() -> bool:
    return os.environ.get("TEST_USE_MOCK", "").lower() == "true"


def get_provider_status() -> dict[str, dict]:
    with _LOCK:
        return {"calendar_web": dict(_STATUS)}


def reset_provider_status() -> None:
    with _LOCK:
        _STATUS.update(status="unknown", last_success_at=None, last_error=None, calls=0, fallbacks=0, events=0)


def _mark(*, status: str, error: str | None = None, events: int = 0, fallback: bool = False) -> None:
    with _LOCK:
        _STATUS["calls"] = int(_STATUS.get("calls", 0)) + 1
        _STATUS["status"] = status
        _STATUS["last_error"] = error
        _STATUS["events"] = events
        if fallback:
            _STATUS["fallbacks"] = int(_STATUS.get("fallbacks", 0)) + 1
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
    suffix = text[match.end():].lstrip().upper()[:1]
    return value * {"K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0, "T": 1_000_000_000_000.0}.get(suffix, 1.0)


def _unit(raw: object) -> str | None:
    text = html.unescape(str(raw or "")).strip().upper()
    if not text:
        return None
    if "%" in text:
        return "percent"
    if text.endswith(("K", "M", "B", "T")):
        return "scaled_count"
    return "number"


_IMPORTANCE = {"high": "high", "medium": "medium", "low": "low"}


def _row_id(row: dict) -> str:
    raw = f"{SOURCE}|{row.get('date')}|{row.get('country')}|{row.get('title')}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _ts(row: dict) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(row.get("date") or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def parse_rows(rows: object) -> dict[str, dict]:
    """Ham JSON satırları → {id: satır}; tarihsiz ya da başlıksız satır atlanır."""
    out: dict[str, dict] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not str(row.get("title") or "").strip() or _ts(row) is None:
            continue
        out[_row_id(row)] = {k: row.get(k) for k in ("title", "country", "date", "impact", "forecast", "previous", "actual")}
    return out


def to_catalysts(rows: dict[str, dict], *, now: datetime) -> list[Catalyst]:
    out: list[Catalyst] = []
    for rid, row in rows.items():
        ts = _ts(row)
        if ts is None:
            continue
        out.append(Catalyst(
            id=rid,
            ts=ts,
            title=str(row.get("title")),
            importance=_IMPORTANCE.get(str(row.get("impact") or "").strip().lower(), "low"),
            region=str(row.get("country") or "") or None,
            category="MACRO_WEB_SHADOW",
            market_impact="public calendar consensus; unverified",
            days_until=(ts.date() - now.date()).days,
            hours_until=round((ts - now).total_seconds() / 3600, 1),
            source=SOURCE,
            verified=False,
            actual=_value(row.get("actual")),
            expected=_value(row.get("forecast")),
            previous=_value(row.get("previous")),
            unit=_unit(row.get("forecast") or row.get("previous") or row.get("actual")),
        ))
    out.sort(key=lambda c: c.ts)
    return out


def _load() -> dict:
    try:
        state = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _fetch() -> list:
    request = urllib.request.Request(ENDPOINT, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
        return json.loads(response.read(2_000_000).decode("utf-8", "replace"))


def list_catalysts(*, now: datetime | None = None, horizon_days: int = 120, past_days: int = 1) -> list[Catalyst]:
    """Doğrulanmamış takvim satırları (beklenti ile); en fazla saatte bir ağ çekimi.

    ``past_days``: takvim listesi için 1 gün (eski davranış); beklenti eşleşmesi için
    KEEP_DAYS (hafta dönünce geçen haftanın açıklaması da eşleşsin)."""
    if _fixture_mode():
        _mark(status="disabled")
        return []
    reference = now or utcnow()
    state = _load()
    rows: dict[str, dict] = dict(state.get("rows") or {})
    try:
        fetched_at = datetime.fromisoformat(str(state.get("fetched_at")))
    except (TypeError, ValueError):
        fetched_at = None
    fresh = fetched_at is not None and (datetime.now(UTC) - fetched_at).total_seconds() < TTL_SEC
    if fresh:
        _mark(status="ok", events=len(rows))
    else:
        try:
            rows.update(parse_rows(_fetch()))
            cutoff = reference - timedelta(days=KEEP_DAYS)
            rows = {k: v for k, v in rows.items() if (_ts(v) or reference) >= cutoff}
            write_text_atomic(_path(), json.dumps({"fetched_at": datetime.now(UTC).isoformat(), "rows": rows}, ensure_ascii=False))
            _mark(status="ok", events=len(rows))
        except (OSError, urllib.error.URLError, ValueError) as exc:
            # Diskteki gerçek (eski) satırlar kullanılır; uydurma yok.
            _mark(status="degraded", error=str(exc)[:160], events=len(rows), fallback=bool(rows))
    return [c for c in to_catalysts(rows, now=reference) if -past_days <= c.days_until <= horizon_days]


__all__ = ["KEEP_DAYS", "SOURCE", "get_provider_status", "list_catalysts", "parse_rows", "reset_provider_status", "to_catalysts"]
