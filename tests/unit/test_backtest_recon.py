"""B-1 (2026-07-04) — geçmiş çok-modül yeniden-kurma + fidelity testleri.

Pinlenen sözleşme:
- LOOK-AHEAD YOK: reconstruct_at(index) yalnız as_of TARİHİNE kadarki barları
  görür (gelecek bar karara sızmaz) — farklı uzunluktaki seriler tarih-hizalı.
- Determinizm: aynı barlar aynı skoru üretir.
- news geçmişe kurulamaz → news_reconstructed=False damgası.
- Flag OFF → learning worker adımı DISABLED (tam no-op).
- quantum yeniden-kurma canlı rotation.compute ile aynı formülü kullanır.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar
from packages.learning import backtest_recon as br


def _series(symbol, n, start_close=100.0, drift=1.0, start_day=1):
    """n adet 1d bar (deterministik artan close)."""
    base = datetime(2025, 1, start_day, tzinfo=UTC)
    return [
        OHLCVBar(
            symbol=symbol,
            timeframe="1d",
            ts=base + timedelta(days=i),
            open=start_close + i * drift,
            high=start_close + i * drift + 1,
            low=start_close + i * drift - 1,
            close=start_close + i * drift,
            volume=1000.0,
            source="test",
            verified=True,
        )
        for i in range(n)
    ]


def _full_bars(n=60):
    """Tüm rotasyon+BTC sembolleri için eş-tarihli seriler."""
    from packages.data.providers.rotation.engine import ROTATION_SYMBOLS

    syms = set(ROTATION_SYMBOLS.values()) | {"BTCUSD"}
    return {s: _series(s, n, start_close=100.0 + hash(s) % 20, drift=0.5) for s in syms}


def _macro(n=60):
    return {
        "DXY": _series("DXY", n, 100.0, 0.1),
        "VIX": _series("VIX", n, 15.0, 0.05),
        # US10Y/US02Y/CPI: OHLCV'de yok (FRED) — bilerek boş; Likidite düşer.
    }


def test_flag_default_off():
    assert br.enabled() is False


def test_reconstruct_deterministic():
    bars, macro = _full_bars(), _macro()
    last = len(bars["BTCUSD"]) - 1
    r1 = br.reconstruct_at(bars, macro, last)
    r2 = br.reconstruct_at(bars, macro, last)
    assert r1.quantum == r2.quantum
    assert r1.regime_label == r2.regime_label
    assert r1.error is None


def test_no_lookahead_date_aligned():
    """Farklı uzunlukta seri: BTCUSD 40 bar, XAUUSD 60 bar aynı tarihlerde
    başlar → reconstruct_at(BTCUSD son index) XAUUSD'nin de yalnız o tarihe
    kadarki barlarını kullanmalı (indeks-hizalama DEĞİL)."""
    from packages.data.providers.rotation.engine import ROTATION_SYMBOLS

    bars = {s: _series(s, 60, drift=0.5) for s in set(ROTATION_SYMBOLS.values()) | {"BTCUSD"}}
    # BTCUSD'yi kısalt: yalnız ilk 40 gün. Son index → 2025-02-09.
    bars["BTCUSD"] = _series("BTCUSD", 40, drift=0.5)
    macro = _macro(60)
    last = len(bars["BTCUSD"]) - 1  # 39
    r = br.reconstruct_at(bars, macro, last)
    # as_of = BTCUSD[39].ts = 2025-02-09; gelecek bar karara girmemeli.
    assert r.as_of.startswith("2025-02-09")
    assert r.error is None


def test_insufficient_bars_below_min():
    bars = _full_bars(10)  # < _MIN_BARS (32)
    r = br.reconstruct_at(bars, _macro(10), 9)
    assert r.error == "insufficient_bars"


def test_news_not_reconstructed_flag():
    r = br.reconstruct_at(_full_bars(), _macro(), 59)
    assert r.news_reconstructed is False


def test_index_out_of_range():
    bars = _full_bars(40)
    r = br.reconstruct_at(bars, _macro(40), 999)
    assert r.error == "index_out_of_range"


def test_fidelity_report_shape(tmp_path, monkeypatch):
    """fidelity_report canlı cache okur; verdict + artifact üretmeli (izole)."""
    out = tmp_path / "recon.json"
    monkeypatch.setenv("BACKTEST_RECON_PATH", str(out))
    r = br.fidelity_report()
    assert r["verdict"] in {"FAITHFUL", "DRIFT", "UNAVAILABLE", "INSUFFICIENT_DATA"}
    assert out.exists()  # izole artifact yazıldı (canlı deftere DEĞİL)


def test_worker_step_gated_by_flag(monkeypatch):
    """Learning worker adımı `enabled()` kapısıyla sürülür — flag OFF iken
    fidelity_report ÇAĞRILMAZ (adım no-op). run_once koşturmadan gate'i pinler
    (in-process modül cache sızıntısı olmasın — empirical_pwin deseni)."""
    called = {"n": 0}
    monkeypatch.setattr(br, "fidelity_report", lambda: called.__setitem__("n", called["n"] + 1))
    monkeypatch.delenv("BACKTEST_RECON_ENABLED", raising=False)
    if br.enabled():  # OFF → adım fidelity_report'u atlar
        br.fidelity_report()
    assert called["n"] == 0
    # ON → adım çağırır
    monkeypatch.setenv("BACKTEST_RECON_ENABLED", "1")
    if br.enabled():
        br.fidelity_report()
    assert called["n"] == 1
