"""Supply/demand zon + HTF hiyerarşi testleri (owner yapısal sistemi, 2026-07-09).

S/D: impulse kökeni zon; mitigasyon; en yakın taze zon.
HTF: rejim-önce bias (1W>1D); range dipte-long/tepede-short; EMA filtresi.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar
from packages.signals.market_structure import MarketStructure
from packages.structure import htf
from packages.structure import supply_demand as sd

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(i, o, h, lo, c):
    return OHLCVBar(symbol="TEST", timeframe="4h", ts=_T0 + timedelta(hours=4 * i),
                    open=o, high=h, low=lo, close=c, volume=1.0)


# ---------------------------------- supply/demand ----------------------------

def test_demand_zone_from_up_impulse():
    """Sakin taban → güçlü yukarı impulse → köken barı demand zonu."""
    bars = [_bar(i, 100, 100.4, 99.6, 100) for i in range(20)]     # sakin (ATR küçük)
    bars.append(_bar(20, 100, 100.3, 99.7, 100))                    # KÖKEN (demand)
    for k in range(1, 6):                                            # güçlü yukarı impulse
        base = 100 + k * 3
        bars.append(_bar(20 + k, base, base + 1, base - 0.5, base + 0.8))
    zones = sd.detect(bars)
    dem = [z for z in zones if z.kind == "demand"]
    assert dem, "yukarı impulse kökeninde demand zonu bulunmalı"
    assert dem[0].origin_index == 20 and dem[0].bottom == 99.7


def test_supply_zone_from_down_impulse():
    bars = [_bar(i, 100, 100.4, 99.6, 100) for i in range(20)]
    bars.append(_bar(20, 100, 100.3, 99.7, 100))                    # KÖKEN (supply)
    for k in range(1, 6):
        base = 100 - k * 3
        bars.append(_bar(20 + k, base, base + 0.5, base - 1, base - 0.8))
    zones = sd.detect(bars)
    assert any(z.kind == "supply" and z.origin_index == 20 for z in zones)


def test_mitigation_flag():
    """Fiyat zona geri girip geçtiyse mitigated=True."""
    bars = [_bar(i, 100, 100.4, 99.6, 100) for i in range(20)]
    bars.append(_bar(20, 100, 100.3, 99.7, 100))
    for k in range(1, 6):
        base = 100 + k * 3
        bars.append(_bar(20 + k, base, base + 1, base - 0.5, base + 0.8))
    bars.append(_bar(26, 101, 101, 99.5, 100))   # zona geri döndü (mitige)
    zones = sd.detect(bars)
    dem = [z for z in zones if z.kind == "demand" and z.origin_index == 20]
    assert dem and dem[0].mitigated is True


def test_insufficient_bars_empty():
    assert sd.detect([_bar(i, 100, 101, 99, 100) for i in range(10)]) == []


# ---------------------------------- HTF hiyerarşi ----------------------------

def _ms(trend):
    return MarketStructure(trend=trend, lean=0.0, bos="none", choch="none",
                           streak=0, legs=4, detail="", last_high=110, last_low=100)


def test_htf_bias_1w_priority():
    """1W varsa 1D'yi geçer (öncelik)."""
    b = htf.htf_bias({"1w": _ms("BEARISH"), "1d": _ms("BULLISH")})
    assert b.bias == "short" and b.source_tf == "1w"


def test_alignment_long_short():
    assert htf.aligned("long", "long") is True
    assert htf.aligned("long", "short") is False
    assert htf.aligned("short", "short") is True


def test_range_bias_extremes_only():
    """Range'de long yalnız dipte, short yalnız tepede, ortada işlem yok."""
    assert htf.aligned("range", "long", at_extreme="bottom") is True
    assert htf.aligned("range", "long", at_extreme="mid") is False
    assert htf.aligned("range", "short", at_extreme="top") is True
    assert htf.aligned("range", "short", at_extreme=None) is False


def test_ema_filter():
    assert htf.ema_filter(105, 100) == "long"
    assert htf.ema_filter(95, 100) == "short"
    assert htf.ema_filter(None, 100) == "neutral"


def test_gate_full_surface():
    g = htf.gate({"1d": _ms("BULLISH")}, "long", price=105, ema200=100)
    assert g["bias"] == "long" and g["aligned"] is True
    assert g["ema_filter"] == "long" and g["ema_confirms"] is True
