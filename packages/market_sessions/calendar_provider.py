"""Resolve a market's trading session for a given instant.

Strategy (pluggable, deterministic-by-default):
  1. If an exchange-calendar library is installed (``pandas_market_calendars`` or
     ``exchange_calendars``) AND the market is a real exchange, use it for
     holiday/early-close-aware sessions (``holiday_verified=True``). Any failure
     or an unsupported exchange code → fall through.
  2. If ``EYAY_HOLIDAY_TABLE_ENABLED`` is on and the exchange is listed in
     ``config/exchange_holidays_v1.0.yaml`` (official dates), use that table for
     holidays and early closes (``holiday_verified=True``). Off by default.
  3. Otherwise use a deterministic fallback: regular weekday sessions only, in
     the market's local timezone via stdlib ``zoneinfo`` (DST-correct). Holidays
     are NOT known → ``holiday_verified=False`` + diagnostic
     ``exchange_calendar_missing:<exchange>``. We never pretend a fully verified
     market status (rule: missing calendar data becomes diagnostics, not
     invented conclusions).

The default path (no library) is deterministic, so tests using frozen datetimes
are stable and CI needs no heavy dependency. Install the optional library to get
holiday-verified sessions.
"""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .config import MarketConfig

_HOLIDAY_TABLE_PATH = Path(__file__).resolve().parents[2] / "config" / "exchange_holidays_v1.0.yaml"
_HOLIDAY_CACHE: dict | None = None


@dataclass
class ResolvedSession:
    is_open: bool
    open_utc: datetime | None
    close_utc: datetime | None
    is_holiday: bool | None
    holiday_verified: bool
    next_open_utc: datetime | None
    diagnostics: list[str] = field(default_factory=list)


def calendar_library_available() -> bool:
    return (
        importlib.util.find_spec("pandas_market_calendars") is not None
        or importlib.util.find_spec("exchange_calendars") is not None
    )


def _parse_hhmm(value: str) -> dt_time:
    hh, mm = value.split(":")
    return dt_time(int(hh), int(mm))


def _local_window(date_local, tz: ZoneInfo, open_t: dt_time, close_t: dt_time):
    open_local = datetime.combine(date_local, open_t, tzinfo=tz)
    close_local = datetime.combine(date_local, close_t, tzinfo=tz)
    return open_local.astimezone(UTC), close_local.astimezone(UTC)


def _next_weekday_open(now_local: datetime, tz: ZoneInfo, open_t: dt_time) -> datetime | None:
    """Next session open (today or a following weekday) strictly in the future."""
    now_utc = now_local.astimezone(UTC)
    for i in range(0, 8):
        d = (now_local + timedelta(days=i)).date()
        if d.weekday() >= 5:  # Sat/Sun
            continue
        open_utc = datetime.combine(d, open_t, tzinfo=tz).astimezone(UTC)
        if open_utc > now_utc:
            return open_utc
    return None


def resolve_session(market: MarketConfig, now_utc: datetime) -> ResolvedSession:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    now_utc = now_utc.astimezone(UTC)
    tz = ZoneInfo(market.timezone)
    now_local = now_utc.astimezone(tz)
    open_t = _parse_hhmm(market.regular_open)
    close_t = _parse_hhmm(market.regular_close)

    # 24/7 continuous (crypto) — genuinely always open, no holidays.
    if market.kind == "continuous":
        open_utc, close_utc = _local_window(now_local.date(), tz, open_t, close_t)
        return ResolvedSession(
            is_open=True,
            open_utc=open_utc,
            close_utc=close_utc,
            is_holiday=False,
            holiday_verified=True,
            next_open_utc=open_utc,
            diagnostics=["continuous_market"],
        )

    # Optional exchange-calendar library (holiday/early-close aware).
    if market.kind == "exchange" and calendar_library_available():
        resolved = _resolve_with_library(market, now_utc, tz)
        if resolved is not None:
            return resolved

    # Official holiday table (flagged; used when the library is absent).
    if market.kind == "exchange" and holiday_table_enabled():
        resolved = _resolve_with_table(market, now_utc, tz, open_t, close_t)
        if resolved is not None:
            return resolved

    # Deterministic weekday fallback (DST-correct via zoneinfo; holidays unverified).
    diagnostics = [f"exchange_calendar_missing:{market.exchange}"]
    if market.kind == "futures_global":
        diagnostics.append("futures_fallback")

    today = now_local.date()
    is_weekday = today.weekday() < 5
    if is_weekday:
        open_utc, close_utc = _local_window(today, tz, open_t, close_t)
        is_open = open_utc <= now_utc < close_utc
    else:
        open_utc, close_utc, is_open = None, None, False

    return ResolvedSession(
        is_open=is_open,
        open_utc=open_utc,
        close_utc=close_utc,
        is_holiday=None,  # unknown without a calendar — never invented
        holiday_verified=False,
        next_open_utc=_next_weekday_open(now_local, tz, open_t),
        diagnostics=diagnostics,
    )


def _resolve_with_library(
    market: MarketConfig, now_utc: datetime, tz: ZoneInfo
) -> ResolvedSession | None:
    """Best-effort holiday-aware resolution. Returns None on any problem (then the
    caller falls back deterministically). Only runs when the lib is installed."""
    try:
        import pandas_market_calendars as mcal  # type: ignore[import-not-found]

        cal = mcal.get_calendar(market.exchange)
        day = now_utc.astimezone(tz).date()
        horizon = (day + timedelta(days=10)).isoformat()
        sched = cal.schedule(start_date=day.isoformat(), end_date=horizon)
        if sched.empty:
            return ResolvedSession(
                is_open=False,
                open_utc=None,
                close_utc=None,
                is_holiday=True,
                holiday_verified=True,
                next_open_utc=None,
                diagnostics=["holiday_verified"],
            )
        first = sched.iloc[0]
        open_utc = first["market_open"].to_pydatetime().astimezone(UTC)
        close_utc = first["market_close"].to_pydatetime().astimezone(UTC)
        today_session = open_utc.astimezone(tz).date() == day
        is_open = today_session and open_utc <= now_utc < close_utc
        is_holiday = not today_session  # no session today → holiday/non-trading day
        next_open_utc = open_utc
        if today_session and now_utc >= close_utc and len(sched) > 1:
            next_open_utc = sched.iloc[1]["market_open"].to_pydatetime().astimezone(UTC)
        return ResolvedSession(
            is_open=is_open,
            open_utc=open_utc if today_session else None,
            close_utc=close_utc if today_session else None,
            is_holiday=is_holiday,
            holiday_verified=True,
            next_open_utc=next_open_utc,
            diagnostics=["holiday_verified"],
        )
    except Exception:
        # Any library/data error → deterministic fallback (caller handles None).
        return None


def holiday_table_enabled() -> bool:
    return os.environ.get("EYAY_HOLIDAY_TABLE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _holiday_calendar(exchange: str) -> dict | None:
    global _HOLIDAY_CACHE
    if _HOLIDAY_CACHE is None:
        try:
            _HOLIDAY_CACHE = yaml.safe_load(_HOLIDAY_TABLE_PATH.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            _HOLIDAY_CACHE = {}
    name = (_HOLIDAY_CACHE.get("exchanges") or {}).get(exchange)
    return (_HOLIDAY_CACHE.get("calendars") or {}).get(name) if name else None


def _resolve_with_table(
    market: MarketConfig, now_utc: datetime, tz: ZoneInfo, open_t: dt_time, close_t: dt_time
) -> ResolvedSession | None:
    """Holiday/early-close aware session from the official table. Returns None when
    the exchange is not listed or the date is past ``covers_until`` (caller falls back)."""
    cal = _holiday_calendar(market.exchange)
    today = now_utc.astimezone(tz).date()
    if not cal or today.isoformat() > str(cal.get("covers_until", "")):
        return None
    closed = cal.get("closed") or {}
    early = cal.get("early_close") or {}

    def window(day):
        key = day.isoformat()
        if day.weekday() >= 5 or key in closed:
            return None
        end = _parse_hhmm(str(early[key])) if key in early else close_t
        return _local_window(day, tz, open_t, end)

    today_window = window(today)
    next_open = None
    for i in range(0, 12):
        w = window(today + timedelta(days=i))
        if w is not None and w[0] > now_utc:
            next_open = w[0]
            break
    diagnostics = ["holiday_verified", "holiday_table"]
    if today.isoformat() in early:
        diagnostics.append("early_close")
    return ResolvedSession(
        is_open=bool(today_window and today_window[0] <= now_utc < today_window[1]),
        open_utc=today_window[0] if today_window else None,
        close_utc=today_window[1] if today_window else None,
        is_holiday=today.isoformat() in closed,
        holiday_verified=True,
        next_open_utc=next_open,
        diagnostics=diagnostics,
    )
