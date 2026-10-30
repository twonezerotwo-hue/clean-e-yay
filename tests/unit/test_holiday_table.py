"""Resmî tatil tablosu: bayrak kapalıyken davranış aynı; açıkken tatil ve erken kapanış."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml

from packages.market_sessions import calendar_provider as cp
from packages.market_sessions.config import load_config


@pytest.fixture
def us(monkeypatch):
    monkeypatch.setattr(cp, "calendar_library_available", lambda: False)
    return load_config().market_by_id("US_EQUITY")


def _at(*args):
    return datetime(*args, tzinfo=UTC)


def test_flag_off_keeps_weekday_fallback(us, monkeypatch):
    monkeypatch.delenv("EYAY_HOLIDAY_TABLE_ENABLED", raising=False)
    rs = cp.resolve_session(us, _at(2026, 7, 3, 14, 0))  # 10:00 ET, resmî tatil
    assert rs.is_open is True and rs.holiday_verified is False
    assert "exchange_calendar_missing:XNYS" in rs.diagnostics


def test_flag_on_closes_official_holiday(us, monkeypatch):
    monkeypatch.setenv("EYAY_HOLIDAY_TABLE_ENABLED", "true")
    rs = cp.resolve_session(us, _at(2026, 7, 3, 14, 0))
    assert rs.is_open is False and rs.is_holiday is True and rs.holiday_verified is True
    assert rs.next_open_utc == _at(2026, 7, 6, 13, 30)  # Pazartesi 09:30 EDT


def test_flag_on_normal_day_and_early_close(us, monkeypatch):
    monkeypatch.setenv("EYAY_HOLIDAY_TABLE_ENABLED", "true")
    assert cp.resolve_session(us, _at(2026, 7, 6, 14, 0)).is_open is True
    noon = cp.resolve_session(us, _at(2026, 11, 27, 17, 0))  # 12:00 EST
    assert noon.is_open is True and noon.close_utc == _at(2026, 11, 27, 18, 0)
    assert "early_close" in noon.diagnostics
    assert cp.resolve_session(us, _at(2026, 11, 27, 18, 30)).is_open is False  # 13:30 EST


def test_next_open_skips_holiday(us, monkeypatch):
    monkeypatch.setenv("EYAY_HOLIDAY_TABLE_ENABLED", "true")
    rs = cp.resolve_session(us, _at(2026, 11, 25, 22, 0))  # Çarşamba kapanış sonrası
    assert rs.next_open_utc == _at(2026, 11, 27, 14, 30)  # Perşembe tatil, Cuma 09:30 EST


def test_unlisted_exchange_or_uncovered_date_falls_back(us, monkeypatch):
    monkeypatch.setenv("EYAY_HOLIDAY_TABLE_ENABLED", "true")
    assert cp.resolve_session(us, _at(2028, 7, 3, 14, 0)).holiday_verified is False
    london = load_config().market_by_id("LONDON")
    assert cp.resolve_session(london, _at(2026, 7, 3, 10, 0)).holiday_verified is False


def test_table_is_well_formed():
    data = yaml.safe_load(cp._HOLIDAY_TABLE_PATH.read_text(encoding="utf-8"))
    for exchange, name in data["exchanges"].items():
        cal = data["calendars"][name]
        for key in [*cal["closed"], *cal["early_close"]]:
            day = datetime.fromisoformat(key)
            assert day.weekday() < 5, (exchange, key)  # tatil hafta içine düşer
            assert key <= cal["covers_until"]
