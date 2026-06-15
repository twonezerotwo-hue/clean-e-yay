"""Resolve a market's trading session for a given instant.

Strategy (pluggable, deterministic-by-default):
  1. If an exchange-calendar library is installed (``pandas_market_calendars`` or
     ``exchange_calendars``) AND the market is a real exchange, use it for
     holiday/early-close-aware sessions (``holiday_verified=True``). Any failure
     or an unsupported exchange code → fall through.
  2. Otherwise use a deterministic fallback: regular weekday sessions only, in
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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from zoneinfo import ZoneInfo

from .config import MarketConfig


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
