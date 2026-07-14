"""Makro arşiv derinlik bekçisi (fundamental_v4 veri tabanı, kural-6 senkron).

- Arşiv kapalı → DISABLED (no-op, bayt-aynı).
- Derin arşiv → DEEP (fetch ÇAĞRILMAZ).
- Sığ arşiv → 5y backfill koşar, dosya dolur; başarısız fetch retry-guard'a girer.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.types import OHLCVBar
from packages.learning import macro_backfill as mbf


def _bars(sym: str, n: int) -> list[OHLCVBar]:
    base = datetime(2021, 1, 1, tzinfo=UTC)
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


def test_disabled_is_noop(monkeypatch):
    monkeypatch.delenv("BAR_HISTORY_ENABLED", raising=False)
    assert mbf.ensure_depth() == {"status": "DISABLED"}


def test_deep_archive_never_fetches(archive, monkeypatch):
    for sym in mbf.BACKFILL_TICKERS:
        archive(sym, 450)
    monkeypatch.setattr(mbf, "_fetch", lambda *a, **k: pytest.fail("fetch ÇAĞRILMAMALI"))
    out = mbf.ensure_depth()
    assert out["status"] == "DEEP"
    # Memo doldu → ikinci çağrı arşivi yeniden bile okumaz (hızlı yol)
    assert mbf.ensure_depth()["status"] == "DEEP"


def test_shallow_archive_backfills(archive, monkeypatch):
    for sym in mbf.BACKFILL_TICKERS:
        archive(sym, 450)
    archive("DXY", 30)   # sığ
    archive("US10Y", 30)
    monkeypatch.setattr(mbf, "_fetch", lambda t, s, r: _bars(s, 500))
    out = mbf.ensure_depth()
    assert out["status"] == "FILLED"
    assert any(f.startswith("DXY:") for f in out["filled"])
    from packages.data.providers.ohlcv import history
    assert len(history.load("DXY", "1d")) >= 400  # arşiv gerçekten doldu


def test_failed_fetch_enters_retry_guard(archive, monkeypatch):
    for sym in mbf.BACKFILL_TICKERS:
        archive(sym, 450)
    archive("VIX", 10)
    monkeypatch.setattr(mbf, "_fetch", lambda t, s, r: [])  # ağ yok/boş
    out = mbf.ensure_depth()
    assert out["status"] == "FAILED" and any(f.startswith("VIX:") for f in out["failed"])
    # Hemen tekrar deneme YOK (yfinance'e vurma) — retry penceresi bekler
    assert mbf.ensure_depth()["status"] == "RETRY_WAIT"
