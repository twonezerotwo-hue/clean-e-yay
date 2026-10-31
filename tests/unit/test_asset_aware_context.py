"""Temel ve sentinel varlığa duyarlı: işaret varlık sınıfından, makro sapması kısa TF'de küçülür."""
from __future__ import annotations

import pytest

from packages.consensus import engine as ce


@pytest.mark.parametrize(("module", "score", "symbol", "tf", "want"), [
    ("fundamental", 10.0, "BTCUSD", "1d", 10.0),    # sıkılaşma: kripto ayı, tam güç
    ("fundamental", 10.0, "BTCUSD", "15m", 40.0),   # aynı bilgi 15 dakikada çeyrek güç
    ("fundamental", 10.0, "DXY", "1d", 90.0),       # sıkılaşma dolar için olumlu
    ("fundamental", 10.0, "WTI", "1d", 30.0),       # enerji zayıf duyarlı
    ("sentinel", 80.0, "XAUUSD", "1h", 35.0),       # sakin piyasa güvenli liman için zayıf olumsuz
    ("sentinel", 80.0, "SP500", "1h", 80.0),        # sakin piyasa hisse için olumlu
    ("sentinel", 80.0, "UNKNOWN_CUSTOM", "1h", 80.0),  # bilinmeyen varlık: eski davranış
])
def test_oriented_scores(module, score, symbol, tf, want):
    assert ce._oriented(module, score, symbol, tf) == pytest.approx(want)


def test_build_applies_orientation_per_asset(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(ce, "_fundamental_v4", lambda: 10.0)
    snap = SimpleNamespace(rotation=SimpleNamespace(status="UNAVAILABLE", score=50.0),
                           technicals_by_tf={}, technicals={}, headlines=[], volatility={}, derivatives={}, options={})
    regime = SimpleNamespace(label="NEUTRAL", layers=[], dropped=[])
    btc = ce.build("BTCUSD", snap, regime, "15m")
    dxy = ce.build("DXY", snap, regime, "1d")
    assert next(m for m in btc.modules if m.name == "fundamental").score == pytest.approx(40.0)
    assert next(m for m in dxy.modules if m.name == "fundamental").score == pytest.approx(90.0)
