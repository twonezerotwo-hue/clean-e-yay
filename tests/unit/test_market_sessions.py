"""Market-session engine + gating policy — deterministic (frozen datetimes).

The optional exchange-calendar library is force-disabled so these tests exercise
the deterministic weekday fallback and never depend on wall-clock time or on a
machine happening to have the library installed.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from packages.market_sessions import (
    asset_context,
    evaluate,
    load_config,
)
from packages.market_sessions.models import MarketSessionDecisionInput


@pytest.fixture(autouse=True)
def _force_fallback(monkeypatch):
    """Force the deterministic weekday fallback (no exchange-calendar library)."""
    monkeypatch.setattr(
        "packages.market_sessions.calendar_provider.calendar_library_available",
        lambda: False,
    )


@pytest.fixture
def cfg():
    return load_config()


def _us(ctx):
    return next(s for s in ctx.relevant_markets if s.market_id == "US_EQUITY")


# Reference instants — 2026-06-15 is a Monday (EDT, UTC-4); 2026-06-13 a Saturday.
MON_OPENING = datetime(2026, 6, 15, 13, 35, tzinfo=UTC)   # 09:35 ET
MON_MID = datetime(2026, 6, 15, 15, 0, tzinfo=UTC)        # 11:00 ET
MON_CLOSING = datetime(2026, 6, 15, 19, 45, tzinfo=UTC)   # 15:45 ET
MON_PRE_OPEN = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)   # 08:00 ET (90m to open)
MON_AFTER = datetime(2026, 6, 16, 1, 0, tzinfo=UTC)       # 21:00 ET
SAT = datetime(2026, 6, 13, 15, 0, tzinfo=UTC)            # weekend


# ── Market status / phase ────────────────────────────────────────────────────

def test_us_equity_mid_session_is_open(cfg):
    us = _us(asset_context("SPY", MON_MID, cfg))
    assert us.is_open is True
    assert us.session_phase == "mid_session"
    assert us.minutes_to_close is not None and us.minutes_to_close > 0


def test_us_equity_opening_window(cfg):
    us = _us(asset_context("SPY", MON_OPENING, cfg))
    assert us.is_open is True
    assert us.session_phase == "opening_window"
    assert us.volatility_window is True


def test_us_equity_pre_open_before_open(cfg):
    us = _us(asset_context("SPY", MON_PRE_OPEN, cfg))
    assert us.is_open is False
    assert us.session_phase == "pre_open"
    assert us.minutes_to_open is not None and 0 < us.minutes_to_open <= 120


def test_us_equity_closing_window(cfg):
    us = _us(asset_context("SPY", MON_CLOSING, cfg))
    assert us.session_phase == "closing_window"
    assert us.volatility_window is True


def test_us_equity_after_close(cfg):
    us = _us(asset_context("SPY", MON_AFTER, cfg))
    assert us.is_open is False
    assert us.session_phase == "after_close"


def test_weekend_closed(cfg):
    us = _us(asset_context("SPY", SAT, cfg))
    assert us.is_open is False
    assert us.session_phase == "closed"


def test_fallback_marks_holiday_unverified_with_diagnostic(cfg):
    """Without a calendar lib: holiday status is unverified + diagnostic, never faked."""
    us = _us(asset_context("SPY", MON_MID, cfg))
    assert us.holiday_verified is False
    assert us.is_holiday is None  # unknown — not invented
    assert any(d.startswith("exchange_calendar_missing:") for d in us.diagnostics)


def test_crypto_is_open_24_7(cfg):
    ctx = asset_context("BTCUSD", SAT, cfg)  # weekend
    crypto = next(s for s in ctx.relevant_markets if s.market_id == "CRYPTO_GLOBAL")
    assert crypto.is_open is True
    assert crypto.session_phase == "mid_session"
    assert crypto.holiday_verified is True  # 24/7, genuinely no holidays


def test_dst_conversion_shifts_open_utc_and_does_not_crash(cfg):
    """09:30 New York maps to 13:30 UTC in summer (EDT) and 14:30 UTC in winter (EST)."""
    summer = _us(asset_context("SPY", datetime(2026, 7, 6, 15, 0, tzinfo=UTC), cfg))
    winter = _us(asset_context("SPY", datetime(2026, 1, 12, 15, 0, tzinfo=UTC), cfg))
    assert summer.open_time_utc is not None and summer.open_time_utc.endswith("13:30:00+00:00")
    assert winter.open_time_utc is not None and winter.open_time_utc.endswith("14:30:00+00:00")


# ── Asset session context ────────────────────────────────────────────────────

def test_spy_maps_to_us_market(cfg):
    ctx = asset_context("SPY", MON_MID, cfg)
    assert "US_EQUITY" in {s.market_id for s in ctx.relevant_markets}
    assert ctx.primary_market_open is True


def test_qqq_maps_to_nasdaq_and_us(cfg):
    ids = {s.market_id for s in asset_context("QQQ", MON_MID, cfg).relevant_markets}
    assert "NASDAQ" in ids and "US_EQUITY" in ids


def test_btc_maps_to_crypto_and_is_open(cfg):
    ctx = asset_context("BTCUSD", SAT, cfg)
    assert ctx.any_relevant_market_open is True
    assert ctx.session_risk == "normal"


def test_xauusd_maps_to_metals_and_london_evidence(cfg):
    ids = {s.market_id for s in asset_context("XAUUSD", MON_MID, cfg).relevant_markets}
    assert "METALS_GLOBAL" in ids
    assert "LONDON" in ids


def test_brent_maps_to_energy_and_london(cfg):
    ids = {s.market_id for s in asset_context("BRENT", MON_MID, cfg).relevant_markets}
    assert "ENERGY_GLOBAL" in ids
    assert "LONDON" in ids


def test_unknown_asset_returns_unknown_context_with_diagnostics(cfg):
    ctx = asset_context("ZZZZ", MON_MID, cfg)
    assert ctx.relevant_markets == []
    assert ctx.session_risk == "unknown"
    assert "asset_unmapped" in ctx.diagnostics


# ── Trading-gate policy ──────────────────────────────────────────────────────

def _decide(asset, now, cfg, **kw):
    return evaluate(MarketSessionDecisionInput(asset_code=asset, now_utc=now, **kw), cfg)


def test_non_crypto_outside_session_routes_manual_ready(cfg):
    d = _decide("SPY", SAT, cfg)
    assert d.action == "manual_ready"
    assert d.reason_code == "market_session_no_relevant_market"
    assert d.size_multiplier == 0.5


def test_opening_window_routes_manual_ready(cfg):
    d = _decide("SPY", MON_OPENING, cfg)
    assert d.action == "manual_ready"
    assert d.reason_code == "market_session_opening_window"
    assert d.size_multiplier == 0.5


def test_closing_window_routes_manual_ready(cfg):
    d = _decide("SPY", MON_CLOSING, cfg)
    assert d.action == "manual_ready"
    assert d.reason_code == "market_session_closing_window"


def test_unknown_calendar_routes_manual_ready_not_auto_open(cfg):
    # 2026-07-04: caution (route=open) → manual_ready. Map'siz varlık artık
    # otomatik AÇILMAZ — takvimi bilinmeyen piyasada açılış owner onayına düşer.
    d = _decide("ZZZZ", MON_MID, cfg)
    assert d.action == "manual_ready"
    assert d.size_multiplier == 0.5
    assert d.reason_code == "market_session_calendar_unknown"
    assert "calendar_unknown" in d.diagnostics
    assert d.action != "allow"


def test_mid_session_allows(cfg):
    d = _decide("SPY", MON_MID, cfg)
    assert d.action == "allow"
    assert d.size_multiplier == 1.0


# ── 2026-07-04 fixes: weekend gap + custom US stock mapping ──────────────────

# 2026-06-19 is a Friday. ENERGY_GLOBAL closes 17:00 ET = 21:00 UTC (EDT).
FRI_PRE_CLOSE = datetime(2026, 6, 19, 19, 30, tzinfo=UTC)  # 15:30 ET — 90m to close
WED_SAME_TIME = datetime(2026, 6, 17, 19, 30, tzinfo=UTC)  # Wednesday — no gap


def test_brent_friday_pre_close_routes_manual_ready(cfg):
    # Cuma kapanışına ≤120dk kala otomatik açılış YOK — hafta sonu gap guard'ı.
    d = _decide("BRENT", FRI_PRE_CLOSE, cfg)
    assert d.action == "manual_ready"
    assert d.reason_code == "market_session_weekend_gap"
    assert d.size_multiplier == 0.5


def test_brent_wednesday_same_time_still_allows(cfg):
    # Aynı saat hafta içi (Çarşamba) → gap yok → mid-session allow.
    d = _decide("BRENT", WED_SAME_TIME, cfg)
    assert d.action == "allow"


def test_metals_friday_pre_close_routes_manual_ready(cfg):
    d = _decide("XAUUSD", FRI_PRE_CLOSE, cfg)
    assert d.action == "manual_ready"
    assert d.reason_code == "market_session_weekend_gap"


def test_custom_us_stock_closed_market_no_auto_open(cfg):
    # SPCX/TEM artık US_EQUITY'ye map'li: piyasa kapaliyken (Cumartesi)
    # "calendar unknown → open" deliği yerine manual_ready.
    for sym in ("TEM", "SPCX", "CLNN", "NVDA"):
        d = _decide(sym, SAT, cfg)
        assert d.action == "manual_ready", sym
        assert d.reason_code == "market_session_no_relevant_market", sym


def test_custom_us_stock_mid_session_allows(cfg):
    d = _decide("TEM", MON_MID, cfg)
    assert d.action == "allow"


def test_crypto_allowed_24_7_but_can_carry_caution_evidence(cfg):
    # Weekend: crypto open, no equity boundary → plain allow, no evidence.
    weekend = _decide("BTCUSD", SAT, cfg)
    assert weekend.action == "allow" and weekend.size_multiplier == 1.0
    # During US opening window crypto still allowed but carries caution evidence.
    boundary = _decide("BTCUSD", MON_OPENING, cfg)
    assert boundary.action == "allow"
    assert any("US_EQUITY" in e for e in boundary.evidence)


def test_size_multiplier_never_exceeds_one(cfg):
    times = [MON_OPENING, MON_MID, MON_CLOSING, MON_PRE_OPEN, MON_AFTER, SAT]
    for asset in ["SPY", "QQQ", "BTCUSD", "XAUUSD", "BRENT", "ZZZZ"]:
        for t in times:
            d = _decide(asset, t, cfg)
            assert d.size_multiplier <= 1.0


def test_restriction_cannot_be_relaxed_by_regime_or_risk_status(cfg):
    """AI/regime/risk_gate inputs can never turn a restrictive session decision
    into a looser one or raise its size multiplier."""
    base = _decide("SPY", MON_OPENING, cfg)
    for regime in ["OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS"]:
        for rg in ["allow", "block", None]:
            d = _decide("SPY", MON_OPENING, cfg, regime=regime, risk_gate_status=rg)
            assert d.action == base.action == "manual_ready"
            assert d.size_multiplier <= base.size_multiplier
