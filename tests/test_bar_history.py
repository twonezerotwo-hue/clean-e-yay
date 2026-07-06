"""Bar arşivi testleri — kanıt-büyütme katmanı (İZOLE, salt-veri).

Kritik güvenceler: (1) flag OFF → append/load no-op (bayt-aynı baseline),
(2) yalnız KAPANMIŞ barlar arşivlenir, (3) tekrar çağrı dublike yazmaz,
(4) bozuk satır load'u düşürmez, (5) karne birleşimi arşiv+canlıyı doğru diker.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.providers.ohlcv import history
from packages.data.types import OHLCVBar


def _bar(i: int, tf: str = "1h", close: float = 100.0) -> OHLCVBar:
    return OHLCVBar(
        symbol="TESTUSD", timeframe=tf,
        ts=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=i),
        open=close, high=close * 1.01, low=close * 0.99, close=close, volume=1.0,
    )


def _on(monkeypatch, tmp_path):
    monkeypatch.setenv(history.FLAG, "1")
    monkeypatch.setenv("BAR_HISTORY_DIR", str(tmp_path))
    # Süreç içi hızlı-yol önbelleğini sıfırla (testler arası sızıntı olmasın).
    history._LAST_TS.clear()


def test_disabled_by_default_noop(tmp_path, monkeypatch):
    """Flag yok -> append 0, load []; dizine dosya YAZILMAZ (bayt-aynı baseline)."""
    monkeypatch.setenv("BAR_HISTORY_DIR", str(tmp_path))
    history._LAST_TS.clear()
    assert history.append_new("TESTUSD", "1h", [_bar(i) for i in range(5)]) == 0
    assert history.load("TESTUSD", "1h") == []
    assert list(tmp_path.iterdir()) == []


def test_append_skips_forming_bar_and_dedups(tmp_path, monkeypatch):
    """Son (oluşan) bar arşive girmez; tekrar çağrı dublike yazmaz; yeni bar
    gelince yalnız fark eklenir."""
    _on(monkeypatch, tmp_path)
    bars = [_bar(i) for i in range(5)]
    assert history.append_new("TESTUSD", "1h", bars) == 4  # son bar hariç
    assert history.append_new("TESTUSD", "1h", bars) == 0  # idempotent
    bars2 = [_bar(i) for i in range(7)]                    # 2 yeni bar geldi
    assert history.append_new("TESTUSD", "1h", bars2) == 2
    loaded = history.load("TESTUSD", "1h")
    assert [b.ts for b in loaded] == [_bar(i).ts for i in range(6)]


def test_append_survives_process_restart(tmp_path, monkeypatch):
    """Süreç içi önbellek silinse de (restart) dosya kuyruğundan devam eder —
    dublike yazmaz."""
    _on(monkeypatch, tmp_path)
    history.append_new("TESTUSD", "1h", [_bar(i) for i in range(5)])
    history._LAST_TS.clear()  # restart simülasyonu
    assert history.append_new("TESTUSD", "1h", [_bar(i) for i in range(6)]) == 1
    assert len(history.load("TESTUSD", "1h")) == 5


def test_load_skips_corrupt_lines(tmp_path, monkeypatch):
    """Bozuk JSONL satırı arşivi düşürmez; geçerli barlar okunur."""
    _on(monkeypatch, tmp_path)
    history.append_new("TESTUSD", "1h", [_bar(i) for i in range(3)])
    p = tmp_path / "TESTUSD_1h.jsonl"
    with p.open("a", encoding="utf-8") as fh:
        fh.write("BOZUK-SATIR{{{\n")
    assert len(history.load("TESTUSD", "1h")) == 2


def test_merged_archive_plus_live(tmp_path, monkeypatch):
    """Birleşim: arşiv eski barları katar, çakışan ts'te CANLI kazanır,
    arşiv boşken canlı AYNEN döner (karne v2 davranışı değişmez)."""
    _on(monkeypatch, tmp_path)
    live = [_bar(i, close=200.0) for i in range(3, 8)]
    assert history.merged([], live) is live  # boş arşiv -> dokunma
    archive = [_bar(i, close=100.0) for i in range(6)]
    out = history.merged(archive, live)
    assert [b.ts for b in out] == [_bar(i).ts for i in range(8)]
    # ts=3..5 çakışması: canlı (close=200) kazanır
    assert out[3].close == 200.0 and out[0].close == 100.0


def test_get_bars_hook_off_is_byte_same(tmp_path, monkeypatch):
    """get_bars hook'u flag OFF iken hiçbir yan etki üretmez (arşiv dizini boş)."""
    monkeypatch.setenv("BAR_HISTORY_DIR", str(tmp_path))
    monkeypatch.setenv("TEST_USE_MOCK", "true")  # fixture yolu — arşiv bekçisi
    history._LAST_TS.clear()
    from packages.data.providers import ohlcv
    bars = ohlcv.get_bars("BTCUSD", "1h")
    assert bars  # fixture veri döndü
    assert list(tmp_path.iterdir()) == []  # arşive tek bayt yazılmadı
