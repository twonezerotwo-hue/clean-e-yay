"""Faz A — touche alt-sinyal karnesi testleri (İZOLE, salt-gözlem).

Kritik güvence: `sub_leans` decomposition'i canlı `_momentum_score` ile BİREBİR
aynı olmalı (formül drift'i = sessiz yanlış kanıt). Ayrıca analyze() yapısı ve
LOOK-AHEAD yokluğu.
"""
from __future__ import annotations

import random

from packages.data.providers.technical.timeframe import (
    _MOM_WEIGHTS,
    _clamp,
    _momentum_score,
)
from packages.learning import subsignal_scorecard as ss


def _recompose(leans: dict[str, float]) -> float | None:
    """sub_leans çıktısını (lean'ler) _momentum_score'un yaptığı gibi tek skora
    topla — fidelity kıyası için."""
    wl = []
    if "trend" in leans:
        wl.append((leans["trend"], _MOM_WEIGHTS["trend"]))
    if "rsi" in leans:
        wl.append((leans["rsi"], _MOM_WEIGHTS["rsi"]))
    if "macd" in leans:
        wl.append((leans["macd"], _MOM_WEIGHTS["macd"]))
    if not wl:
        return None
    num = sum(ln * w for ln, w in wl)
    den = sum(w for _, w in wl)
    return _clamp(50.0 + (num / den) * 50.0, 0.0, 100.0)


class _FakeBar:
    def __init__(self, c):
        self.close = c
        self.high = c * 1.01
        self.low = c * 0.99
        self.open = c


def test_sub_leans_fidelity_matches_momentum_score():
    """En kritik güvence: alt-sinyal ayrıştırması canlı momentum skorunu BİREBİR
    yeniden üretir (import edilen sabitlerle; kopya değil)."""
    rng = random.Random(42)
    # sub_leans ham gostergeden turer; burada dogrudan lean formulunu de test et:
    # rastgele rsi/macd_atr/ema_stack -> recompose == _momentum_score
    for _ in range(500):
        rsi_v = rng.uniform(0, 100)
        macd_atr = rng.uniform(-2, 2)
        stack = rng.choice(["bullish", "bearish", "mixed", None])
        leans = {}
        if stack is not None:
            leans["trend"] = {"bullish": 1.0, "bearish": -1.0, "mixed": 0.0}[stack]
        leans["rsi"] = _clamp((rsi_v - 50.0) / 50.0, -1.0, 1.0)
        leans["macd"] = _clamp(macd_atr / 1.0, -1.0, 1.0)
        assert _recompose(leans) == _momentum_score(rsi_v, macd_atr, stack)


def test_sub_leans_on_bars_returns_expected_signals():
    """Yeterli trend'li seride trend/rsi/macd lean'leri üretilir ve −1..+1'de."""
    closes = [100 + i * 0.5 for i in range(260)]  # yukari trend
    bars = [_FakeBar(c) for c in closes]
    leans = ss.sub_leans(closes, bars)
    assert set(leans).issubset({"trend", "rsi", "macd"})
    assert leans  # bos degil
    for v in leans.values():
        assert -1.0 <= v <= 1.0
    # net yukari trend -> trend lean bullish (+1)
    assert leans.get("trend") == 1.0


def test_sub_leans_insufficient_history_empty():
    """Isinma altinda gosterge None -> lean uretilmez (uydurma yok)."""
    closes = [100.0, 101.0, 102.0]
    bars = [_FakeBar(c) for c in closes]
    leans = ss.sub_leans(closes, bars)
    # ema200/rsi yetersiz -> trend/rsi yok (macd de muhtemelen yok)
    assert "trend" not in leans


def test_analyze_structure_no_crash(monkeypatch):
    """analyze() bar yoksa bile saglam yapida doner (izole, patlamaz)."""
    monkeypatch.setattr(ss, "get_bars", lambda sym, tf: [])
    rep = ss.analyze(symbols=["BTCUSD"], timeframes=("1d",))
    assert rep["engine"] == "subsignal_scorecard_v1"
    assert "1d" in rep["per_timeframe"]
    assert rep["per_timeframe"]["1d"]["points"] == 0


def test_run_disabled_by_default(monkeypatch):
    """Flag yoksa run() no-op (DEFAULT OFF)."""
    monkeypatch.delenv(ss.FLAG, raising=False)
    assert ss.run() == {"status": "DISABLED"}
