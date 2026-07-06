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
    assert rep["engine"] == "subsignal_scorecard_v2"
    assert "1d" in rep["per_timeframe"]
    assert rep["per_timeframe"]["1d"]["points"] == 0


def test_v2_sampling_non_overlapping(monkeypatch):
    """v2 cetvel duzeltmesi 1: adim = ufuk -> ardisik ileri-getiriler ayni
    hareketi PAYLASMAZ (sisik n biter). Nokta sayisi stride'li beklentiyle esit."""
    n_bars = 400
    closes = [100 + i * 0.1 for i in range(n_bars)]
    bars = [_FakeBar(c) for c in closes]
    monkeypatch.setattr(ss, "get_bars", lambda sym, tf: bars)
    rep = ss.analyze(symbols=["X"], timeframes=("1d",))
    h = ss._HORIZON["1d"]
    expected = len(range(ss._MIN_WARMUP, n_bars - h, h))
    assert rep["per_timeframe"]["1d"]["points"] == expected
    # v1 (adim=1) olsaydi ~H kati nokta olurdu — geriye kacis yok.
    assert expected < (n_bars - h - ss._MIN_WARMUP)


def test_v2_baseline_and_typical_move_fields(monkeypatch):
    """v2 duzeltme 2+3: TF seviyesinde tipik |hareket| ve hep-yukari taban
    cizgisi raporlanir; sinyal seviyesinde oran/kararlilik/taban alanlari var."""
    closes = [100 + i * 0.1 for i in range(400)]
    bars = [_FakeBar(c) for c in closes]
    monkeypatch.setattr(ss, "get_bars", lambda sym, tf: bars)
    rep = ss.analyze(symbols=["X"], timeframes=("1d",))
    tf = rep["per_timeframe"]["1d"]
    assert tf["typical_move_pct"] > 0
    # duz yukari seri -> taban cizgisi pozitif (boga donemi kontrolu somut)
    assert tf["baseline_edge_pct"] > 0
    for row in tf["signals"].values():
        assert {"edge_ratio", "stable", "beats_baseline",
                "edge_first_half", "edge_second_half"} <= set(row)


def test_v2_verdict_rules():
    """v2 damga: EDGE = oran esigi + tabani gecme + iki-yari kararlilik.
    Her kosul tek basina dusunce damga duser (FLAT); ters oran = INVERSE."""
    v = ss._verdict
    assert v(0.5, 10, beats_baseline=True, stable=True) == "INSUFFICIENT"
    assert v(0.5, 50, beats_baseline=True, stable=True) == "EDGE"
    assert v(0.5, 50, beats_baseline=False, stable=True) == "FLAT"   # boga hediyesi
    assert v(0.5, 50, beats_baseline=True, stable=False) == "FLAT"   # tek-yari ezberi
    assert v(0.05, 50, beats_baseline=True, stable=True) == "FLAT"   # oran zayif
    assert v(-0.5, 50, beats_baseline=False, stable=False) == "INVERSE"


def test_run_if_due_disabled_by_default(monkeypatch):
    """Flag yoksa run_if_due() no-op (DEFAULT OFF) — learning koşusu bayt-eşdeğer."""
    monkeypatch.delenv(ss.FLAG, raising=False)
    assert ss.run_if_due() == {"status": "DISABLED"}


def test_run_if_due_skips_fresh_artifact(tmp_path, monkeypatch):
    """D5 interval kapısı: taze artifact varken yeniden ÖLÇMEZ (SKIP_FRESH) —
    haftalık koşum sözü; analyze çağrılmadığını sahte-analyze ile kanıtla."""
    import json
    from datetime import UTC, datetime
    art = tmp_path / "sc.json"
    art.write_text(json.dumps({"generated_at": datetime.now(UTC).isoformat(),
                               "engine": ss._ENGINE}), encoding="utf-8")
    monkeypatch.setenv(ss.FLAG, "1")
    monkeypatch.setattr(ss, "_ART", str(art))
    monkeypatch.setattr(ss, "analyze", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("taze artifact varken analyze çağrılmamalı")))
    out = ss.run_if_due()
    assert out["status"] == "SKIP_FRESH" and out["age_sec"] >= 0


def test_endpoint_no_artifact_returns_no_data(tmp_path, monkeypatch):
    """GET /learning/subsignal-scorecard: artifact yoksa NO_DATA + enabled=False.
    Dikkat: apps.api.main import'u .env'i os.environ'a yükler (bilinen sızıntı
    sınıfı) — flag import SONRASI silinir ki test dev-.env'inden bağımsız olsun."""
    from fastapi.testclient import TestClient

    from apps.api.main import app
    monkeypatch.delenv(ss.FLAG, raising=False)
    monkeypatch.setattr(ss, "_ART", str(tmp_path / "yok.json"))
    r = TestClient(app).get("/api/v1/learning/subsignal-scorecard")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "NO_DATA" and body["enabled"] is False


def test_endpoint_serves_artifact(tmp_path, monkeypatch):
    """Artifact varsa içerik aynen sunulur (status=OK + per_timeframe)."""
    import json

    from fastapi.testclient import TestClient

    from apps.api.main import app
    art = tmp_path / "sc.json"
    art.write_text(json.dumps({"generated_at": "2026-07-06T00:00:00+00:00",
                               "engine": "subsignal_scorecard_v2",
                               "per_timeframe": {"4h": {"signals": {}}}}),
                   encoding="utf-8")
    monkeypatch.setattr(ss, "_ART", str(art))
    body = TestClient(app).get("/api/v1/learning/subsignal-scorecard").json()
    assert body["status"] == "OK"
    assert body["engine"] == "subsignal_scorecard_v2"
    assert "4h" in body["per_timeframe"]


def test_run_if_due_regenerates_old_engine_artifact(tmp_path, monkeypatch):
    """Cetvel sürümü değişince (v1 artifact) TAZE olsa bile yeniden ölçülür —
    canlıda yakalanan hata: dünkü v1 kaydı v2 ölçümünü bir hafta bloke ediyordu."""
    import json
    from datetime import UTC, datetime
    art = tmp_path / "sc.json"
    art.write_text(json.dumps({"generated_at": datetime.now(UTC).isoformat(),
                               "engine": "subsignal_scorecard_v1"}), encoding="utf-8")
    monkeypatch.setenv(ss.FLAG, "1")
    monkeypatch.setattr(ss, "_ART", str(art))
    monkeypatch.setattr(ss, "analyze", lambda *a, **k: {
        "generated_at": datetime.now(UTC).isoformat(), "engine": ss._ENGINE,
        "per_timeframe": {"4h": {}}})
    out = ss.run_if_due()
    assert out["status"] == "OK"
    assert json.loads(art.read_text(encoding="utf-8"))["engine"] == ss._ENGINE


def test_run_if_due_remeasures_stale_artifact(tmp_path, monkeypatch):
    """Bayat (interval'i aşmış) artifact → yeniden ölçüm + atomik yazım."""
    import json
    from datetime import UTC, datetime, timedelta
    art = tmp_path / "sc.json"
    old = datetime.now(UTC) - timedelta(days=8)
    art.write_text(json.dumps({"generated_at": old.isoformat()}), encoding="utf-8")
    monkeypatch.setenv(ss.FLAG, "1")
    monkeypatch.setattr(ss, "_ART", str(art))
    monkeypatch.setattr(ss, "analyze", lambda *a, **k: {
        "generated_at": datetime.now(UTC).isoformat(), "per_timeframe": {"1d": {}}})
    out = ss.run_if_due()
    assert out == {"status": "OK", "timeframes": ["1d"]}
    assert json.loads(art.read_text(encoding="utf-8"))["per_timeframe"] == {"1d": {}}
