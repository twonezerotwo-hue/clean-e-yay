"""T-4 — Kilit seviyede mum teyidi (`technical.candle_confirm`) testleri.

- Dedektör: engulfing (iki-bar, öncelikli) + pin bar (hammer/shooting star);
  yetersiz bar / gövdesiz bar / sinyalsiz bar → None (uydurma yok).
- Skor: flag KAPALI → candle_bias geçilse bile skor bayt-aynı; flag AÇIK →
  formasyon kanadına momentumla uyum/çelişki olarak girer (yön üretmez).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.providers.technical import candles
from packages.data.providers.technical import timeframe as tf
from packages.data.types import OHLCVBar


def _bar(i: int, o: float, h: float, l: float, c: float) -> OHLCVBar:  # noqa: E741 — test kısaltması, dosya deseni test_volume_validation ile aynı
    return OHLCVBar(
        symbol="TEST", timeframe="1d",
        ts=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
        open=o, high=h, low=l, close=c, volume=100.0,
    )


_FILLER = _bar(0, 100, 101, 99, 100)


def test_too_few_bars_is_none():
    assert candles.detect([_bar(0, 100, 101, 99, 100.5)]) is None
    assert candles.detect([]) is None


def test_bullish_engulfing():
    bars = [_FILLER, _bar(1, 100, 100.5, 98.9, 99.0), _bar(2, 98.8, 101.5, 98.5, 101.0)]
    sig = candles.detect(bars)
    assert sig is not None and sig.name == "bullish_engulfing" and sig.bias == "BULLISH"


def test_bearish_engulfing():
    bars = [_FILLER, _bar(1, 99.0, 101.1, 98.9, 101.0), _bar(2, 101.2, 101.5, 98.5, 98.8)]
    sig = candles.detect(bars)
    assert sig is not None and sig.name == "bearish_engulfing" and sig.bias == "BEARISH"


def test_hammer():
    # Uzun alt fitil (98 → gövde 100.4-100.6), üst fitil küçük, kapanış üst yarıda.
    bars = [_FILLER, _FILLER, _bar(2, 100.4, 100.7, 98.0, 100.6)]
    sig = candles.detect(bars)
    assert sig is not None and sig.name == "hammer" and sig.bias == "BULLISH"


def test_shooting_star():
    bars = [_FILLER, _FILLER, _bar(2, 100.6, 103.0, 100.3, 100.4)]
    sig = candles.detect(bars)
    assert sig is not None and sig.name == "shooting_star" and sig.bias == "BEARISH"


def test_plain_bar_is_none():
    bars = [_FILLER, _FILLER, _bar(2, 100.0, 100.6, 99.8, 100.5)]
    assert candles.detect(bars) is None


def test_doji_prev_cannot_be_engulfed():
    # Önceki bar gövdesiz (doji) — "yutulacak gövde yok", engulfing sayılmaz.
    bars = [_FILLER, _bar(1, 100.0, 100.5, 99.5, 100.0), _bar(2, 99.4, 101.5, 99.3, 101.2)]
    sig = candles.detect(bars)
    assert sig is None or sig.name != "bullish_engulfing"


def test_direction_score_flag_off_ignores_candle():
    cfg_off = tf.TechnicalConfig()
    s_with, _ = tf._direction_score(70.0, 0.0, "bullish", cfg=cfg_off, candle_bias="BULLISH")
    s_without, _ = tf._direction_score(70.0, 0.0, "bullish", cfg=cfg_off)
    assert s_with == s_without


def test_direction_score_flag_on_aligned_candle_confirms():
    cfg_on = tf.TechnicalConfig(candle_confirm_enabled=True)
    s_with, _ = tf._direction_score(70.0, 0.0, "bullish", cfg=cfg_on, candle_bias="BULLISH")
    s_without, _ = tf._direction_score(70.0, 0.0, "bullish", cfg=cfg_on)
    assert s_with > s_without


def test_direction_score_flag_on_opposing_candle_penalizes():
    # Long momentum + kilit seviyede shooting star → güven kesilir (yön çevrilmez).
    cfg_on = tf.TechnicalConfig(candle_confirm_enabled=True)
    s_opposed, _ = tf._direction_score(70.0, 0.0, "bullish", cfg=cfg_on, candle_bias="BEARISH")
    s_plain, _ = tf._direction_score(70.0, 0.0, "bullish", cfg=cfg_on)
    assert 50.0 < s_opposed < s_plain


def test_candle_never_fabricates_direction():
    cfg_on = tf.TechnicalConfig(candle_confirm_enabled=True)
    s, _ = tf._direction_score(50.0, 0.0, "mixed", cfg=cfg_on, candle_bias="BULLISH")
    assert s == 50.0
