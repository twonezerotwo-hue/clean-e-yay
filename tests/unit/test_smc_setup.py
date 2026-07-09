"""SMC setup sekans dedektörü testleri (owner yapısal sistemi, 2026-07-09).

Sentetik barlarla: retest dedektörü + sekans state-machine (SWEPT→CHOCH→BOS→
RETEST→READY). market_structure/sweep primitifleri enjekte edilerek izole test.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import LiquiditySweepAnalysis, OHLCVBar
from packages.signals.market_structure import MarketStructure
from packages.structure import smc_setup as smc

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(i, o, h, lo, c):
    return OHLCVBar(symbol="TEST", timeframe="4h", ts=_T0 + timedelta(hours=4 * i),
                    open=o, high=h, low=lo, close=c, volume=1.0)


def _flat_bars(n=30, price=100.0):
    return [_bar(i, price, price + 0.5, price - 0.5, price) for i in range(n)]


def _ms(trend="BULLISH", bos="bullish", choch="bullish", last_high=110.0, last_low=100.0):
    return MarketStructure(trend=trend, lean=0.7, bos=bos, choch=choch, streak=1,
                           legs=4, detail="test", last_high=last_high, last_low=last_low)


def _sweep(bias="REVERSAL_LONG", validity="sane"):
    state = "LOW_SWEEP_RECLAIMED" if bias == "REVERSAL_LONG" else "HIGH_SWEEP_RECLAIMED"
    return LiquiditySweepAnalysis(timeframe="4h", state=state, bias=bias, validity=validity)


def test_insufficient_bars_none():
    s = smc.detect(_flat_bars(10))
    assert s.direction == "none" and s.stage == smc.STAGE_NONE


def test_no_directional_break_none():
    s = smc.detect(_flat_bars(), structure=_ms(trend="RANGING", bos="none", choch="none"),
                   sweep=_sweep())
    assert s.direction == "none"


def test_full_long_sequence_ready():
    """Sweep + CHoCH + BOS + retest → READY long. Kırılan seviye 110'a retest."""
    bars = _flat_bars(30, 112.0)
    # son barlar: 110 (kırılan tepe) seviyesine geri gel (retest) + üstünde kapan
    bars[-3] = _bar(27, 112, 112.4, 110.2, 111)   # retest zonuna değdi
    bars[-2] = _bar(28, 111, 111.5, 110.1, 111.3)
    bars[-1] = _bar(29, 111.3, 112.5, 111.0, 112.4)  # kapanış 112.4 > 110 (tutundu)
    s = smc.detect(bars, structure=_ms(last_high=110.0, last_low=105.0), sweep=_sweep())
    assert s.direction == "long"
    assert s.swept and s.choch and s.bos and s.retested
    assert s.stage == smc.STAGE_READY and s.ready is True
    assert s.stop == 105.0 and s.broken_level == 110.0


def test_sequence_stops_at_bos_without_retest():
    """Sweep+CHoCH+BOS ama retest yok → aşama BOS'ta durur (hazır değil)."""
    bars = _flat_bars(30, 120.0)  # fiyat 120, 110'a hiç geri gelmedi (retest yok)
    s = smc.detect(bars, structure=_ms(last_high=110.0, last_low=105.0), sweep=_sweep())
    assert s.bos and not s.retested
    assert s.stage == smc.STAGE_BOS and not s.ready


def test_sequence_stops_at_swept_without_choch():
    """Sweep var ama CHoCH yön uyumsuz → aşama SWEPT'te durur."""
    bars = _flat_bars(30, 112.0)
    ms = _ms(choch="none", bos="bullish", last_high=110.0, last_low=105.0)
    s = smc.detect(bars, structure=ms, sweep=_sweep())
    assert s.swept and not s.choch
    assert s.stage == smc.STAGE_SWEPT


def test_short_sequence_mirror():
    """Ayna: aşağı break + REVERSAL_SHORT sweep + retest → short yönü."""
    bars = _flat_bars(30, 96.0)                  # fiyat 97 kırılan dibin altında
    bars[-3] = _bar(27, 96, 97.1, 95.8, 96.5)    # yukarı gelip 97 (kırılan dip) retest
    bars[-1] = _bar(29, 96.3, 96.6, 95.8, 96.0)  # kapanış 96.0 < 97 (short tutundu)
    ms = _ms(trend="BEARISH", bos="bearish", choch="bearish", last_high=100.0, last_low=97.0)
    s = smc.detect(bars, structure=ms, sweep=_sweep(bias="REVERSAL_SHORT"))
    assert s.direction == "short" and s.retested
    assert s.stop == 100.0 and s.broken_level == 97.0


def test_stage_rank_ordered():
    assert smc.stage_rank(smc.STAGE_READY) > smc.stage_rank(smc.STAGE_BOS)
    assert smc.stage_rank(smc.STAGE_SWEPT) > smc.stage_rank(smc.STAGE_NONE)
