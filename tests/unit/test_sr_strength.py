"""T-3 — Destek/direnç gücü (`technical.sr_strength`) testleri.

- Flag KAPALI (default): taraf ağırlığı 0.6 sabit — dokunma sayısı ne olursa
  olsun skor bayt-aynı.
- Flag AÇIK: 1 dokunuş → 0.5 (zayıf seviye), 2 → 0.6 (nötr), 3+ → 0.7 (güçlü).
- Çok dokunulmuş destek, momentum long'unu tek-dokunuşlu desteğe göre daha
  güçlü teyit eder.
"""
from __future__ import annotations

from packages.data.providers.technical import timeframe as tf
from packages.data.types import TechnicalConfluenceZone


def _zone(kind="support"):
    return TechnicalConfluenceZone(price=99.5, kind=kind, components=["swing_support", "vwap"])


def test_flag_off_weight_fixed_regardless_of_touches():
    z = [_zone()]
    for touches in (1, 2, 5):
        w = tf._zone_side_weight("support", z, sr_touches={"support": touches})
        assert w == 0.6


def test_flag_on_touch_tiers():
    z = [_zone()]
    on = dict(sr_strength_on=True)
    assert tf._zone_side_weight("support", z, sr_touches={"support": 1}, **on) == 0.5
    assert tf._zone_side_weight("support", z, sr_touches={"support": 2}, **on) == 0.6
    assert tf._zone_side_weight("support", z, sr_touches={"support": 3}, **on) == 0.7
    assert tf._zone_side_weight("support", z, sr_touches={"support": 7}, **on) == 0.7


def test_flag_on_missing_touches_stays_neutral():
    z = [_zone()]
    assert tf._zone_side_weight("support", z, sr_touches=None, sr_strength_on=True) == 0.6
    assert tf._zone_side_weight("support", z, sr_touches={}, sr_strength_on=True) == 0.6


def test_direction_score_flag_off_byte_identical():
    cfg_off = tf.TechnicalConfig()
    z = [_zone()]
    s_many, _ = tf._direction_score(
        70.0, 0.0, "bullish", zones=z, cfg=cfg_off, sr_touches={"support": 5}
    )
    s_none, _ = tf._direction_score(70.0, 0.0, "bullish", zones=z, cfg=cfg_off)
    assert s_many == s_none


def test_direction_score_flag_on_strong_level_confirms_more():
    cfg_on = tf.TechnicalConfig(sr_strength_enabled=True)
    z = [_zone()]
    s_strong, _ = tf._direction_score(
        70.0, 0.0, "bullish", zones=z, cfg=cfg_on, sr_touches={"support": 3}
    )
    s_weak, _ = tf._direction_score(
        70.0, 0.0, "bullish", zones=z, cfg=cfg_on, sr_touches={"support": 1}
    )
    assert s_strong > s_weak  # 0.7 teyit > 0.5 teyit


def test_weak_resistance_penalizes_less_than_strong():
    # Long momentum dirence koşuyor: 1 dokunuşlu direnç (0.5) 3+ dokunuşludan (0.7)
    # daha az ceza kesmeli.
    cfg_on = tf.TechnicalConfig(sr_strength_enabled=True)
    z = [TechnicalConfluenceZone(price=101.0, kind="resistance", components=["swing_resistance", "vwap"])]
    s_weak_res, _ = tf._direction_score(
        70.0, 0.0, "bullish", zones=z, cfg=cfg_on, sr_touches={"resistance": 1}
    )
    s_strong_res, _ = tf._direction_score(
        70.0, 0.0, "bullish", zones=z, cfg=cfg_on, sr_touches={"resistance": 4}
    )
    assert s_weak_res > s_strong_res
