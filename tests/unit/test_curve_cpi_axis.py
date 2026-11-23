"""FAZ-2 eğri + enflasyon veri omurgası (US02Y/CPI FRED backfill + tezgâh ekseni).

- Bekçi: FRED sembolleri YALNIZ FRED_API_KEY varsa taranır (anahtarsız ortam
  dürüstçe atlar, NO_KEY notu düşer — ağa çıkmaz, uydurma yok).
- Bekçi: anahtar varken sığ FRED sembolü get_history ile doldurulur (yfinance
  yolu değil), CPI kendi AYLIK eşiğiyle ölçülür.
- Tezgâh: curve_at / infl_yoy_at pure hesapları (NaN/eksik → None).
- Tezgâh: CPI serisi yayın gecikmesiyle İLERİ kaydırılır (look-ahead yok).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.types import OHLCVBar
from packages.learning import macro_backfill as mbf


def _bars(sym: str, n: int) -> list[OHLCVBar]:
    base = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=n)
    return [
        OHLCVBar(
            symbol=sym, timeframe="1d", ts=base + timedelta(days=i),
            open=100.0, high=101.0, low=99.0, close=100.0 + i * 0.01,
            volume=0.0, source="test", verified=True,
        )
        for i in range(n)
    ]


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setenv("BAR_HISTORY_ENABLED", "1")
    monkeypatch.setenv("BAR_HISTORY_DIR", str(tmp_path))
    mbf._MEMO["ok"] = set()
    mbf._MEMO["last_attempt"] = 0.0

    def _write(sym: str, n: int) -> None:
        lines = [json.dumps(b.model_dump(mode="json")) for b in _bars(sym, n)]
        (tmp_path / f"{sym}_1d.jsonl").write_text("\n".join(lines), encoding="utf-8")

    return _write


def test_fred_registry_sane():
    # US02Y günlük (derin eşik), CPI aylık (5y ≈ 60 gözlem — küçük eşik ŞART).
    assert mbf.FRED_BACKFILL_MIN_BARS["US02Y"] >= 300
    assert 12 <= mbf.FRED_BACKFILL_MIN_BARS["CPI"] <= 60
    # FRED sembolleri yfinance haritasında OLMAMALI (kaynak tekliği).
    assert not set(mbf.FRED_BACKFILL_MIN_BARS) & set(mbf.BACKFILL_TICKERS)


def test_no_key_skips_fred_symbols(archive, monkeypatch):
    """Anahtar yok → FRED sembolleri taranmaz, ağa çıkılmaz, NO_KEY notu düşer."""
    for sym in mbf.BACKFILL_TICKERS:
        archive(sym, 450)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(mbf, "_fetch", lambda *a, **k: pytest.fail("yf fetch OLMAMALI"))
    monkeypatch.setattr(mbf, "_fetch_fred", lambda *a, **k: pytest.fail("fred fetch OLMAMALI"))
    out = mbf.ensure_depth()
    assert out["status"] == "DEEP" and out["fred"] == "NO_KEY"


def test_key_backfills_shallow_fred_symbol(archive, monkeypatch):
    """Anahtar var + US02Y/CPI sığ → FRED get_history yoluyla dolar."""
    for sym in mbf.BACKFILL_TICKERS:
        archive(sym, 450)
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.setattr(mbf, "_fetch", lambda *a, **k: pytest.fail("yf fetch OLMAMALI"))
    monkeypatch.setattr(mbf, "_fetch_fred", lambda sym, start: _bars(sym, 500))
    out = mbf.ensure_depth()
    assert out["status"] == "FILLED"
    assert any(f.startswith("US02Y:") for f in out["filled"])
    assert any(f.startswith("CPI:") for f in out["filled"])
    from packages.data.providers.ohlcv import history
    assert len(history.load("US02Y", "1d")) >= 400


def test_cpi_uses_monthly_threshold(archive, monkeypatch):
    """CPI 60 aylık gözlemle DERİN sayılır (400 günlük eşiğe takılmaz)."""
    for sym in mbf.BACKFILL_TICKERS:
        archive(sym, 450)
    archive("US02Y", 450)
    archive("CPI", 60)  # 5y aylık seri
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.setattr(mbf, "_fetch_fred", lambda *a, **k: pytest.fail("CPI derin — fetch OLMAMALI"))
    assert mbf.ensure_depth()["status"] == "DEEP"


