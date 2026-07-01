"""Strateji-farkında işlem şekillendirme (packages/paper/strategy_shaping.py) — Faz 4.

Flag OFF → nötr (bayt-aynı). Flag ON → setup ailesine göre çarpanlar. size_mult ≤ 1.0
(no-boost). Guardrail [0.5, 1.5]. Tanınmayan setup → nötr.
"""
from __future__ import annotations

from packages.risk import strategy_shaping as ss

_CFG = {
    "enabled": True,
    "profiles": {
        "TREND": {"stop": 1.0, "tp_rr": 1.15, "trail": 1.25, "size": 1.0},
        "REVERSAL_CONFIRMED": {"stop": 0.85, "tp_rr": 1.0, "trail": 1.0, "size": 1.0},
        "REVERSAL_WATCH": {"stop": 0.85, "tp_rr": 0.9, "trail": 0.85, "size": 0.7},
        "RANGE": {"stop": 0.85, "tp_rr": 0.8, "trail": 0.8, "size": 0.7},
        "SCALP": {"stop": 0.75, "tp_rr": 0.8, "trail": 0.75, "size": 0.7},
        "BREAKOUT": {"stop": 1.0, "tp_rr": 1.15, "trail": 1.10, "size": 1.0},
        "PULLBACK": {"stop": 0.9, "tp_rr": 1.0, "trail": 1.0, "size": 1.0},
    },
}


def _on(monkeypatch, cfg=_CFG):
    monkeypatch.setattr(ss, "_cfg", lambda: cfg)


def test_flag_off_is_neutral(monkeypatch):
    monkeypatch.setattr(ss, "_cfg", lambda: {"enabled": False, "profiles": _CFG["profiles"]})
    out = ss.shape("TREND_LONG")
    assert out is ss.NEUTRAL
    assert out.active is False
    assert (out.stop_mult, out.tp_rr_mult, out.trail_mult, out.size_mult) == (1.0, 1.0, 1.0, 1.0)


def test_trend_gets_wide_trailing(monkeypatch):
    _on(monkeypatch)
    out = ss.shape("TREND_LONG")
    assert out.family == "TREND"
    assert out.trail_mult == 1.25  # kazananı sür
    assert out.tp_rr_mult == 1.15


def test_reversal_confirmed_vs_watch(monkeypatch):
    _on(monkeypatch)
    conf = ss.shape("REVERSAL_SHORT_CONFIRMED")
    watch = ss.shape("REVERSAL_LONG_WATCH")
    assert conf.family == "REVERSAL_CONFIRMED"
    assert watch.family == "REVERSAL_WATCH"
    assert conf.stop_mult == 0.85
    assert watch.size_mult == 0.7  # onaysız → küçük


def test_scalp_tight(monkeypatch):
    _on(monkeypatch)
    out = ss.shape("SCALP_LONG")
    assert out.family == "SCALP"
    assert out.stop_mult == 0.75 and out.trail_mult == 0.75


def test_unknown_and_no_trade_neutral(monkeypatch):
    _on(monkeypatch)
    assert ss.shape("NO_TRADE") is ss.NEUTRAL
    assert ss.shape(None) is ss.NEUTRAL
    assert ss.shape("WEIRD_TYPE") is ss.NEUTRAL


def test_size_mult_never_boosts(monkeypatch):
    # Bozuk config size>1.0 dese bile ≤ 1.0'a clamp (no-boost invariant).
    _on(monkeypatch, {"enabled": True, "profiles": {"TREND": {"size": 1.5, "stop": 1.0}}})
    out = ss.shape("TREND_LONG")
    assert out.size_mult == 1.0


def test_guardrail_clamps_extremes(monkeypatch):
    # stop 5.0 → 1.5'e, trail 0.1 → 0.5'e clamp.
    _on(monkeypatch, {"enabled": True, "profiles": {"TREND": {"stop": 5.0, "trail": 0.1}}})
    out = ss.shape("TREND_LONG")
    assert out.stop_mult == 1.5
    assert out.trail_mult == 0.5


def test_family_priority_reversal_before_trend(monkeypatch):
    # REVERSAL_LONG_CONFIRMED "TREND" içermez ama başlık eşleşmesi doğru aileyi seçmeli.
    _on(monkeypatch)
    assert ss.shape("REVERSAL_LONG_CONFIRMED").family == "REVERSAL_CONFIRMED"
    assert ss.shape("BREAKOUT_SHORT").family == "BREAKOUT"
    assert ss.shape("PULLBACK_LONG").family == "PULLBACK"
    assert ss.shape("RANGE_SHORT").family == "RANGE"
