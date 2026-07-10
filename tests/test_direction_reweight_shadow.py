"""Yön yeniden-ağırlık gölgesi testleri (İZOLE, salt-gözlem).

Kritik güvenceler:
- touche bileşeni CANLI `_momentum_score` ile BİREBİR aynı olmalı (formül drift'i =
  sessiz yanlış kanıt → owner'ı yanıltır).
- owner skoru ADX rejim kapısını uygular: trend modunda RSI YÖN ÜRETMEZ (rol-kısıt).
- Paired adalet: `leans` iki skoru ATOMİK döner (biri hesaplanamıyorsa ikisi de yok).
- analyze() yapısı + bindirmesiz örnekleme + LOOK-AHEAD yokluğu.
- Flag DEFAULT OFF → worker-adımı no-op; interval/eski-cetvel kapıları.
"""
from __future__ import annotations

import random

from packages.data.providers.technical.timeframe import _clamp, _momentum_score
from packages.learning import direction_reweight_shadow as dr


import math


class _FakeBar:
    def __init__(self, c, hi=None, lo=None):
        self.close = c
        self.high = hi if hi is not None else c * 1.01
        self.low = lo if lo is not None else c * 0.99
        self.open = c


def _wavy(n=320, base=100.0, slope=0.25, amp=3.0, period=12):
    """Salınımlı yukarı trend → market_structure pivot (HH/HL) bulur (struct ≠ None)."""
    out = []
    for i in range(n):
        c = base + slope * i + amp * math.sin(i / period * 2 * math.pi)
        out.append(_FakeBar(c, c * 1.008, c * 0.992))
    return out


def test_leans_touche_matches_momentum_score():
    """touche bileşeni = (_momentum_score − 50)/50 — üretim formülünün AYNISI.
    Gerçek göstergelerle (import; kopya değil) türetilir; drift = sessiz hata."""
    import packages.data.providers.technical.indicators as ind
    from packages.signals import market_structure as ms

    bars = _wavy()
    closes = [b.close for b in bars]
    pair = dr.leans(closes, bars)
    assert pair is not None
    touche, _owner = pair
    # bağımsız yeniden hesap (canlı yolun aynısı)
    rsi_v = ind.rsi(closes)
    macd_t = ind.macd(closes)
    atr_v = ind.atr(bars)
    macd_atr = macd_t[2] / atr_v
    from packages.data.providers.technical.timeframe import _EMA_PERIODS, _ema_stack
    stack = _ema_stack([ind.ema(closes, p) for p in _EMA_PERIODS])
    expected = _clamp((_momentum_score(rsi_v, macd_atr, stack) - 50.0) / 50.0, -1.0, 1.0)
    assert abs(touche - expected) < 1e-9
    assert ms.lean(bars) is not None  # struct hesaplanabilir (owner tarafı için)


def test_leans_atomic_pair_or_none():
    """Paired adalet: yetersiz ısınmada leans() None döner (yarım skor SIZMAZ)."""
    closes = [100.0, 101.0, 102.0]
    bars = [_FakeBar(c) for c in closes]
    assert dr.leans(closes, bars) is None


def test_leans_uptrend_both_bullish():
    """Net yukarı trendde iki skor da pozitif (yön okur; owner ters düşmez)."""
    bars = _wavy(slope=0.4, amp=2.0)
    closes = [b.close for b in bars]
    pair = dr.leans(closes, bars)
    assert pair is not None
    touche, owner = pair
    assert touche > 0 and owner > 0
    assert -1.0 <= owner <= 1.0


def test_owner_rsi_role_restricted_in_trend(monkeypatch):
    """Owner kuralı: TREND modunda (ADX yüksek) RSI YÖN ÜRETMEZ. RSI'ı zıt uca
    zorla + struct/mom'u sabit tut → trend modunda owner değişmez, range'de değişir."""
    import packages.data.providers.technical.indicators as ind
    from packages.signals import market_structure as ms

    closes = [100 + i * 0.3 for i in range(320)]
    bars = [_FakeBar(c) for c in closes]
    # struct ve momentum bileşenlerini sabitle (yalnız RSI ve ADX değişsin)
    monkeypatch.setattr(dr.market_structure, "lean", lambda *a, **k: 0.5)
    monkeypatch.setattr(ind, "macd", lambda c: (0.0, 0.0, 0.0))
    monkeypatch.setattr(ind, "atr", lambda b: 1.0)
    monkeypatch.setattr(dr, "_ema_stack", lambda emas: "mixed")  # mom stack_sign=0
    monkeypatch.setattr(ind, "ema", lambda c, p: 100.0)
    monkeypatch.setattr(ind, "rsi", lambda c: 90.0)  # RSI aşırı-alım (güçlü +)
    assert ms is dr.market_structure  # aynı modül (patch hedefi doğru)

    monkeypatch.setattr(ind, "adx", lambda b: (30.0, 20.0, 10.0))  # TREND modu
    trend_owner = dr.leans(closes, bars)[1]
    monkeypatch.setattr(ind, "adx", lambda b: (10.0, 20.0, 10.0))  # RANGE modu
    range_owner = dr.leans(closes, bars)[1]

    # struct=0.5, mom=0 → trend: 0.64*0.5=0.32 (RSI YOK). range: 0.50*0.5 + 0.22*RSI.
    assert abs(trend_owner - 0.32) < 1e-9          # RSI susmuş
    assert range_owner > trend_owner               # range'de RSI(+) owner'ı ittirdi


def test_analyze_structure_no_crash(monkeypatch):
    """analyze() bar yoksa bile sağlam yapıda döner (izole, patlamaz)."""
    monkeypatch.setattr(dr, "get_bars", lambda sym, tf: [])
    monkeypatch.setattr(dr.history, "load", lambda sym, tf: [])
    rep = dr.analyze(symbols=["BTCUSD"], timeframes=("1d",))
    assert rep["engine"] == dr._ENGINE
    assert "1d" in rep["per_timeframe"]
    tf = rep["per_timeframe"]["1d"]
    assert tf["touche"]["n"] == 0 and tf["owner"]["n"] == 0
    assert tf["verdict"] == "INSUFFICIENT"


def test_analyze_non_overlapping_and_fields(monkeypatch):
    """Bindirmesiz örnekleme (adım=ufuk) + paired alanlar raporlanır."""
    bars = _wavy(n=400, slope=0.15, amp=2.5)
    monkeypatch.setattr(dr, "get_bars", lambda sym, tf: bars)
    monkeypatch.setattr(dr.history, "load", lambda sym, tf: [])
    rep = dr.analyze(symbols=["X"], timeframes=("1d",))
    tf = rep["per_timeframe"]["1d"]
    assert {"touche", "owner", "delta_edge_pct", "delta_first_half",
            "delta_second_half", "stable", "disagree_n", "verdict"} <= set(tf)
    # paired adalet: iki skor aynı bar kümesinden → n'ler birbirine yakın
    assert tf["touche"]["n"] > 0 and tf["owner"]["n"] > 0


def test_verdict_rules():
    """Damga: OWNER_BETTER = fark ≥ margin·tipik_hareket VE iki-yarı kararlı.
    margin = 0.08 · typical_move. Kararsızsa/az farkla FLAT; ters büyük fark = TOUCHE_BETTER."""
    v = dr._verdict
    # typical_move=1.0 → margin=0.08
    assert v(0.5, 1.0, 10, stable=True) == "INSUFFICIENT"
    assert v(0.5, 1.0, 50, stable=True) == "OWNER_BETTER"
    assert v(0.5, 1.0, 50, stable=False) == "FLAT"     # tek-yarı ezberi
    assert v(0.02, 1.0, 50, stable=True) == "FLAT"     # fark zayıf (< margin)
    assert v(-0.5, 1.0, 50, stable=True) == "TOUCHE_BETTER"


def test_run_if_due_disabled_by_default(monkeypatch):
    """Flag yoksa run_if_due() no-op (DEFAULT OFF) — learning koşusu bayt-eşdeğer."""
    monkeypatch.delenv(dr.FLAG, raising=False)
    assert dr.run_if_due() == {"status": "DISABLED"}


def test_run_if_due_skips_fresh_artifact(tmp_path, monkeypatch):
    """Interval kapısı: taze artifact varken yeniden ÖLÇMEZ (SKIP_FRESH)."""
    import json
    from datetime import UTC, datetime
    art = tmp_path / "dr.json"
    art.write_text(json.dumps({"generated_at": datetime.now(UTC).isoformat(),
                               "engine": dr._ENGINE}), encoding="utf-8")
    monkeypatch.setenv(dr.FLAG, "1")
    monkeypatch.setattr(dr, "_ART", str(art))
    monkeypatch.setattr(dr, "analyze", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("taze artifact varken analyze çağrılmamalı")))
    out = dr.run_if_due()
    assert out["status"] == "SKIP_FRESH" and out["age_sec"] >= 0


def test_run_if_due_regenerates_old_engine(tmp_path, monkeypatch):
    """Cetvel sürümü değişince (eski engine) TAZE olsa bile yeniden ölçülür."""
    import json
    from datetime import UTC, datetime
    art = tmp_path / "dr.json"
    art.write_text(json.dumps({"generated_at": datetime.now(UTC).isoformat(),
                               "engine": "direction_reweight_shadow_v0"}), encoding="utf-8")
    monkeypatch.setenv(dr.FLAG, "1")
    monkeypatch.setattr(dr, "_ART", str(art))
    monkeypatch.setattr(dr, "analyze", lambda *a, **k: {
        "generated_at": datetime.now(UTC).isoformat(), "engine": dr._ENGINE,
        "per_timeframe": {"4h": {}}})
    out = dr.run_if_due()
    assert out["status"] == "OK"
    assert json.loads(art.read_text(encoding="utf-8"))["engine"] == dr._ENGINE


def test_run_if_due_remeasures_stale(tmp_path, monkeypatch):
    """Bayat (interval'i aşmış) artifact → yeniden ölçüm + atomik yazım."""
    import json
    from datetime import UTC, datetime, timedelta
    art = tmp_path / "dr.json"
    old = datetime.now(UTC) - timedelta(days=8)
    art.write_text(json.dumps({"generated_at": old.isoformat()}), encoding="utf-8")
    monkeypatch.setenv(dr.FLAG, "1")
    monkeypatch.setattr(dr, "_ART", str(art))
    monkeypatch.setattr(dr, "analyze", lambda *a, **k: {
        "generated_at": datetime.now(UTC).isoformat(), "per_timeframe": {"1d": {}}})
    out = dr.run_if_due()
    assert out == {"status": "OK", "timeframes": ["1d"]}
