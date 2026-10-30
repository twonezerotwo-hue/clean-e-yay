"""Official macro-release observers.

The adapters are read-only and additive.  They return verified *published*
observations with no expectation invented by the provider.  Expectations still
come from the calendar observer and are joined later by the canonical evidence
layer.  Nothing in this module opens an order or relaxes a gate.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

from packages.data.types import Catalyst, utcnow

_BLS_ENDPOINT = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
_EIA_ENDPOINT = "https://api.eia.gov/v2/petroleum/sum/sndw/data/"
_EIA_GAS_ENDPOINT = "https://api.eia.gov/v2/natural-gas/stor/wkly/data/"
_EIA_GAS_SERIES = "NW2_EPG0_SWO_R48_BCF"
_USER_AGENT = "clean-e-yay/1.0 (official-macro-shadow)"
_TIMEOUT_SEC = 6.0
_DEFAULT_TTL_SEC = 900.0
# BLS aylık açıklar; anahtarsız uç günde 25 istek verir. 15 dakikada bir sormak
# kotayı öğlene bitiriyordu (2026-10-30: anahtar geçersiz → anahtarsız uç da
# doldu). BLS ayrı önbellekte 6 saatte bir sorulur (günde 4 istek).
_BLS_TTL_SEC = 21600.0
_BLS_CACHE: tuple[float, list] | None = None
# Quarterly releases such as GDP and ECI can be more than one quarter old
# before the next publication.  Keep the latest verified observation instead
# of dropping it at the 120-day edge; freshness is reported by the snapshot
# and never treated as a surprise without a matching expectation.
_LOOKBACK_DAYS = 400

_BLS_SERIES: tuple[tuple[str, str, str], ...] = (
    ("BLS_CPI", "CUUR0000SA0", "US CPI"),
    ("BLS_CORE_CPI", "CUSR0000SA0L1E", "US Core CPI"),
    ("BLS_PPI", "WPSFD4", "US Producer Price Index"),
    ("BLS_NFP", "CES0000000001", "US Nonfarm Payrolls"),
    ("BLS_UNEMPLOYMENT", "LNS14000000", "US Unemployment Rate"),
    ("BLS_JOLTS", "JTS000000000000000JOL", "US Job Openings"),
    ("BLS_ECI", "CIU2020000000000A", "US Employment Cost Index"),
)

_BLS_UNITS = {
    "BLS_CPI": "index",
    "BLS_CORE_CPI": "index",
    "BLS_PPI": "index",
    "BLS_NFP": "thousands",
    "BLS_UNEMPLOYMENT": "percent",
    "BLS_JOLTS": "thousands",
    "BLS_ECI": "percent",
}

_FRED_SERIES: tuple[tuple[str, str, str], ...] = (
    ("FRED_PCE", "PCE", "US PCE Price Index"),
    ("FRED_CORE_PCE", "CORE_PCE", "US Core PCE Price Index"),
    ("FRED_GDP", "GDP", "US Gross Domestic Product"),
    ("FRED_FEDFUNDS", "FEDFUNDS", "US Federal Funds Rate"),
)

_FRED_UNITS = {
    "FRED_PCE": "index",
    "FRED_CORE_PCE": "index",
    "FRED_GDP": "currency",
    "FRED_FEDFUNDS": "percent",
}

_STATUS: dict[str, dict[str, Any]] = {
    name: {
        "status": "unknown",
        "last_success_at": None,
        "last_error": None,
        "calls": 0,
        "events": 0,
        "fallbacks": 0,
    }
    for name in ("macro_bls", "macro_fred", "macro_eia")
}
_LOCK = threading.Lock()
_CACHE: tuple[float, list[Catalyst]] | None = None


def _enabled() -> bool:
    if os.environ.get("TEST_USE_MOCK", "").lower() == "true":
        return False
    return os.environ.get("MACRO_OFFICIAL_SHADOW", "true").lower() not in {"0", "false", "no", "off"}


def _ttl() -> float:
    try:
        return max(60.0, float(os.environ.get("MACRO_RELEASE_TTL_SEC", _DEFAULT_TTL_SEC)))
    except (TypeError, ValueError):
        return _DEFAULT_TTL_SEC


def _bls_ttl() -> float:
    try:
        return max(_ttl(), float(os.environ.get("MACRO_BLS_TTL_SEC", _BLS_TTL_SEC)))
    except (TypeError, ValueError):
        return _BLS_TTL_SEC


def _bls_cached(reference: datetime) -> list:
    """BLS satırları kendi (uzun) önbelleğinden; başarısız sonuç da önbelleğe girer
    ki geçersiz anahtar ya da dolu kota uç noktayı her turda yormasın."""
    global _BLS_CACHE
    now_ts = datetime.now(UTC).timestamp()
    if _BLS_CACHE and now_ts - _BLS_CACHE[0] < _bls_ttl():
        return list(_BLS_CACHE[1])
    rows = _bls_releases(reference)
    _BLS_CACHE = (now_ts, list(rows))
    return rows


def _mark(name: str, *, status: str, error: str | None = None, events: int = 0) -> None:
    with _LOCK:
        state = _STATUS[name]
        state["calls"] += 1
        state["status"] = status
        state["events"] = events
        state["last_error"] = error
        if status == "ok":
            state["last_success_at"] = datetime.now(UTC).isoformat()


def get_provider_status() -> dict[str, dict]:
    with _LOCK:
        return {key: dict(value) for key, value in _STATUS.items()}


def reset_provider_status() -> None:
    global _CACHE, _BLS_CACHE
    with _LOCK:
        for value in _STATUS.values():
            value.update(status="unknown", last_success_at=None, last_error=None, calls=0, events=0, fallbacks=0)
        _CACHE = None
        _BLS_CACHE = None


def _json_request(url: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json", "Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SEC) as response:
        return json.loads(response.read().decode("utf-8"))


def _bls_timestamp(year: int, period: str) -> datetime | None:
    try:
        if period.startswith("M"):
            month = int(period[1:])
        elif period.startswith("Q"):
            quarter = int(period[1:])
            if quarter < 1 or quarter > 4:
                return None
            month = (quarter - 1) * 3 + 1
        else:
            return None
        if month < 1 or month > 12:
            return None
        return datetime(year, month, 1, 12, tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _bls_releases(now: datetime) -> list[Catalyst]:
    payload: dict[str, Any] = {"seriesid": [series_id for _, series_id, _ in _BLS_SERIES], "startyear": str(now.year - 2), "endyear": str(now.year)}
    if os.environ.get("BLS_API_KEY"):
        payload["registrationkey"] = os.environ["BLS_API_KEY"]
    try:
        data = _json_request(_BLS_ENDPOINT, payload=payload)
    except (OSError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, AssertionError) as exc:
        _mark("macro_bls", status="degraded", error=str(exc)[:160])
        return []
    if str(data.get("status", "")).upper() != "REQUEST_SUCCEEDED" and os.environ.get("BLS_API_KEY"):
        # A stale/expired registration key must not disable the public BLS
        # endpoint.  Retry once without it; the no-key API is rate-limited but
        # sufficient for this cached shadow observer.
        try:
            data = _json_request(_BLS_ENDPOINT, payload={k: v for k, v in payload.items() if k != "registrationkey"})
        except (OSError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            pass
    if str(data.get("status", "")).upper() != "REQUEST_SUCCEEDED":
        _mark("macro_bls", status="degraded", error="BLS request unsuccessful")
        return []
    labels = {series_id: (event_id, title) for event_id, series_id, title in _BLS_SERIES}
    out: list[Catalyst] = []
    for series in data.get("Results", {}).get("series", []) or []:
        event_id, title = labels.get(str(series.get("seriesID")), (None, None))
        if not event_id or not title:
            continue
        observations: list[tuple[datetime, float]] = []
        for item in series.get("data", []) or []:
            try:
                ts = _bls_timestamp(int(item["year"]), str(item["period"]))
                value = float(str(item["value"]).replace(",", ""))
            except (KeyError, TypeError, ValueError):
                continue
            if ts is not None and ts <= now:
                observations.append((ts, value))
        observations.sort(key=lambda row: row[0], reverse=True)
        if not observations:
            continue
        ts, actual = observations[0]
        previous = observations[1][1] if len(observations) > 1 else None
        if (now - ts).days > _LOOKBACK_DAYS:
            continue
        out.append(Catalyst(
            id=f"{event_id}:{ts.date().isoformat()}", ts=ts, title=title,
            importance="high", region="US", category=f"{event_id}_OFFICIAL",
            market_impact="official BLS release; actual observed",
            days_until=(ts.date() - now.date()).days,
            hours_until=round((ts - now).total_seconds() / 3600, 1),
            source="bls_official", verified=True, actual=actual, previous=previous,
            unit=_BLS_UNITS.get(event_id),
            evidence=["BLS Public Data API", f"series={event_id}"],
        ))
    _mark("macro_bls", status="ok" if out else "degraded", events=len(out), error=None if out else "no recent BLS observations")
    return out


def _fred_releases(now: datetime) -> list[Catalyst]:
    try:
        from packages.data.providers.price import fred
        labels = {symbol: (event_id, title) for event_id, symbol, title in _FRED_SERIES}
        out: list[Catalyst] = []
        start = (now - timedelta(days=_LOOKBACK_DAYS)).date().isoformat()
        for symbol, (event_id, title) in labels.items():
            bars = fred.get_history(symbol, start=start)
            if not bars:
                continue
            latest = bars[-1]
            previous = bars[-2].close if len(bars) > 1 else None
            out.append(Catalyst(
                id=f"{event_id}:{latest.ts.date().isoformat()}", ts=latest.ts,
                title=title, importance="high", region="US", category=f"{event_id}_OFFICIAL",
                market_impact="official FRED release; actual observed",
                days_until=(latest.ts.date() - now.date()).days,
                hours_until=round((latest.ts - now).total_seconds() / 3600, 1),
                source="fred_official", verified=True, actual=float(latest.close), previous=previous,
                unit=_FRED_UNITS.get(event_id),
                evidence=["Federal Reserve Bank of St. Louis FRED", f"series={symbol}"],
            ))
        _mark("macro_fred", status="ok" if out else "disabled", events=len(out), error=None if out else "FRED key missing or no observations")
        return out
    except (OSError, ValueError, TypeError, AssertionError) as exc:
        _mark("macro_fred", status="degraded", error=str(exc)[:160])
        return []


def _eia_releases(now: datetime) -> list[Catalyst]:
    key = os.environ.get("EIA_API_KEY")
    if not key:
        _mark("macro_eia", status="disabled", error="EIA_API_KEY missing")
        return []
    feeds = (
        (_EIA_ENDPOINT, "WCESTUS1", "US Crude Oil Inventories", "OIL_INVENTORY_OFFICIAL", "thousand_barrels"),
        (_EIA_GAS_ENDPOINT, _EIA_GAS_SERIES, "US Natural Gas Storage", "NATURAL_GAS_STORAGE_OFFICIAL", "billion_cubic_feet"),
    )
    out: list[Catalyst] = []
    errors: list[str] = []
    for endpoint, series, title, category, unit in feeds:
        query_params = [
            ("api_key", key), ("frequency", "weekly"), ("data[0]", "value"),
            ("facets[series][]", series), ("sort[0][column]", "period"),
            ("sort[0][direction]", "desc"), ("length", "2"),
        ]
        query = f"{endpoint}?{urllib.parse.urlencode(query_params)}"
        try:
            data = _json_request(query)
            rows = data.get("response", {}).get("data", []) or []
            values: list[tuple[datetime, float]] = []
            for row in rows:
                ts = datetime.strptime(str(row.get("period")), "%Y-%m-%d").replace(tzinfo=UTC)
                values.append((ts, float(row.get("value"))))
            if not values:
                continue
            ts, actual = values[0]
            previous = values[1][1] if len(values) > 1 else None
            out.append(Catalyst(
                id=f"EIA_{category.removesuffix('_OFFICIAL')}:{ts.date().isoformat()}", ts=ts,
                title=title, importance="high", region="US",
                category=category, market_impact="official EIA release; actual observed",
                source="eia_official", verified=True, actual=actual, previous=previous,
                days_until=(ts.date() - now.date()).days,
                hours_until=round((ts - now).total_seconds() / 3600, 1),
                unit=unit,
                evidence=["US Energy Information Administration API", f"series={series}"],
            ))
        except (OSError, urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError, json.JSONDecodeError, AssertionError) as exc:
            errors.append(f"{series}: {str(exc)[:100]}")
    _mark(
        "macro_eia",
        status="ok" if out else "degraded",
        events=len(out),
        error=None if out else ("; ".join(errors) or "no EIA observations"),
    )
    return out


def list_releases(*, now: datetime | None = None) -> list[Catalyst]:
    """Return recent verified official observations, cached and shadow-only."""
    global _CACHE
    if not _enabled():
        for name in _STATUS:
            _mark(name, status="disabled", error="MACRO_OFFICIAL_SHADOW disabled")
        return []
    reference = now or utcnow()
    cached = _CACHE
    if cached and datetime.now(UTC).timestamp() - cached[0] < _ttl():
        return list(cached[1])
    from packages.data.providers.macro import derived

    # Takvimle aynı birimde türetilmiş resmî gerçekleşen (yalnız bayrak açıkken).
    rows = [*_bls_cached(reference), *_fred_releases(reference), *_eia_releases(reference), *derived.releases(reference)]
    # Keep one official row per canonical event/date, preferring BLS over FRED
    # for CPI-like series and EIA over generic oil headlines.
    unique: dict[tuple[str, str], Catalyst] = {}
    priority = {"bls_official": 3, "eia_official": 3, "fred_official": 2}
    for row in rows:
        key = (row.title.casefold(), row.ts.date().isoformat())
        if key not in unique or priority.get(row.source, 0) > priority.get(unique[key].source, 0):
            unique[key] = row
    result = sorted(unique.values(), key=lambda item: item.ts, reverse=True)
    _CACHE = (datetime.now(UTC).timestamp(), result)
    return result


__all__ = ["get_provider_status", "list_releases", "reset_provider_status"]


_TRACKED_TOPICS = {
    "CPI": ("US CPI", "macro_bls_official"),
    "CORE_CPI": ("US Core CPI", "macro_bls_official"),
    "PPI": ("US Producer Price Index", "macro_bls_official"),
    "NFP": ("US Nonfarm Payrolls", "macro_bls_official"),
    "JOLTS": ("US Job Openings", "macro_bls_official"),
    "ECI": ("US Employment Cost Index", "macro_bls_official"),
    "PCE": ("US PCE Price Index", "macro_fred_official"),
    "CORE_PCE": ("US Core PCE Price Index", "macro_fred_official"),
    "GDP": ("US Gross Domestic Product", "macro_fred_official"),
    "FED_FUNDS": ("US Federal Funds Rate", "macro_fred_official"),
    "EIA_OIL": ("US Crude Oil Inventories", "macro_eia_official"),
    "EIA_GAS": ("US Natural Gas Storage", "macro_eia_official"),
    # Free public calendar/news shadow topics.  They are intentionally never
    # marked verified by this provider.
    "ADP": ("ADP/private payroll", "macro_extended_web_shadow"),
    "ISM_PMI": ("ISM manufacturing/services PMI", "macro_extended_web_shadow"),
    "DURABLE_GOODS": ("Durable Goods Orders", "macro_extended_web_shadow"),
    "FOMC_STATEMENT": ("FOMC statement/minutes", "macro_extended_web_shadow"),
}


def coverage(releases: list[Catalyst] | None = None, catalysts: list[Catalyst] | None = None) -> dict[str, dict[str, Any]]:
    """Expose an honest configured-vs-observed macro inventory.

    ``ACTIVE`` means a verified official row is present in the current
    snapshot.  ``ADAPTER_NO_RECENT_ROW`` keeps an existing official adapter
    visible when the provider has no current observation.  Extended topics are
    calendar/news shadow only until independently verified.
    """
    rows = [*(releases or ()), *(catalysts or ())]
    result: dict[str, dict[str, Any]] = {}
    for topic, (label, source_id) in _TRACKED_TOPICS.items():
        matches = [row for row in rows if label.casefold().split("/")[0] in str(getattr(row, "title", "")).casefold()]
        official = [row for row in matches if bool(getattr(row, "verified", False))]
        if source_id == "macro_extended_web_shadow":
            status = "SHADOW_CALENDAR_OR_NEWS" if matches else "NO_CURRENT_SHADOW_ROW"
            verified = False
        else:
            status = "ACTIVE" if official else "ADAPTER_NO_RECENT_ROW"
            verified = bool(official)
        result[topic] = {
            "label": label,
            "source_id": source_id,
            "status": status,
            "verified": verified,
            "rows": len(matches),
        }
    return result


__all__.append("coverage")
