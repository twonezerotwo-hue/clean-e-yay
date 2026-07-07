"""Y-6 — Haber olay-çalışması testleri (SALT-GÖZLEM).

- record_events(): yalnız verified + yönlü (asset_impact) başlık deftere girer;
  id ile dedupe; nötr/doğrulanmamış atlanır.
- compute(): olaydan sonraki ilk bara göre N-bar ileri-getiri; yön-hizalı hit;
  olgunlaşmamış olay pending (uydurma yok); n>=min & öngörü → PREDICTIVE, aksi
  NO_EDGE / INSUFFICIENT; global UNPROVEN dürüst.
- viewmodel(): shape + shadow_only.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.data.registry.loader import threshold_override
from packages.learning import news_event_study as nes

_CFG = {"news_event_study": {"horizon_bars": 3, "timeframe": "1d", "min_bucket_n": 2}}


@pytest.fixture(autouse=True)
def study_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_EVENT_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("NEWS_EVENT_STUDY_PATH", str(tmp_path / "study.json"))
    return tmp_path


def _headline(hid="n1", source="rss", sentiment="bullish", verified=True,
              impact=None, ts=None):
    return SimpleNamespace(
        id=hid, source=source, sentiment=sentiment, verified=verified,
        asset_impact=impact if impact is not None else {"BTCUSD": 1.0},
        ts=ts or datetime(2026, 1, 1, tzinfo=UTC),
    )


def _bars(closes, start=datetime(2026, 1, 1, tzinfo=UTC)):
    return [SimpleNamespace(ts=start + timedelta(days=i), close=c)
            for i, c in enumerate(closes)]


@pytest.fixture
def patch_bars(monkeypatch):
    """history.merged'i sabit barlara sabitle (get_bars/load nötr)."""
    from packages.data.providers.ohlcv import history

    def _install(bars):
        monkeypatch.setattr(history, "load", lambda *a, **k: [])
        monkeypatch.setattr("packages.data.providers.ohlcv.get_bars",
                            lambda *a, **k: [])
        monkeypatch.setattr(history, "merged", lambda *a, **k: bars)
    return _install


# ── record_events ─────────────────────────────────────────────────────────────

def test_record_only_verified_directional():
    with threshold_override(_CFG):
        n = nes.record_events(headlines=[
            _headline("a", verified=True, impact={"BTCUSD": 1.0}),
            _headline("b", verified=False, impact={"BTCUSD": 1.0}),   # doğrulanmamış
            _headline("c", verified=True, impact={}),                 # yönsüz
        ])
    assert n == 1
    rows = nes._read_ledger()
    assert [r["id"] for r in rows] == ["a"]


def test_record_dedupes_by_id():
    with threshold_override(_CFG):
        assert nes.record_events(headlines=[_headline("a")]) == 1
        assert nes.record_events(headlines=[_headline("a"), _headline("d")]) == 1
    assert {r["id"] for r in nes._read_ledger()} == {"a", "d"}


# ── compute ───────────────────────────────────────────────────────────────────

def test_compute_bullish_hit_when_price_rises(patch_bars):
    patch_bars(_bars([100, 101, 102, 110]))  # +%10 3 barda, yukarı
    ev = [{"id": "a", "source": "rss", "sentiment": "bullish",
           "ts": datetime(2026, 1, 1, tzinfo=UTC).isoformat(), "symbols": {"BTCUSD": 1.0}}]
    with threshold_override(_CFG):
        t = nes.compute(events=ev * 2)  # n=2 = min
    b = t["buckets"]["rss|bullish"]
    assert b["n"] == 2 and b["hits"] == 2
    assert b["avg_dir_return_pct"] > 0 and b["verdict"] == "PREDICTIVE"
    assert t["global_verdict"] == "PREDICTIVE"


def test_compute_bullish_miss_when_price_falls(patch_bars):
    patch_bars(_bars([100, 99, 98, 90]))  # düşüş ama haber "bullish" → yanlış
    ev = [{"id": "a", "source": "rss", "sentiment": "bullish",
           "ts": datetime(2026, 1, 1, tzinfo=UTC).isoformat(), "symbols": {"BTCUSD": 1.0}}]
    with threshold_override(_CFG):
        t = nes.compute(events=ev * 2)
    b = t["buckets"]["rss|bullish"]
    assert b["hits"] == 0 and b["avg_dir_return_pct"] < 0
    assert b["verdict"] == "NO_EDGE"
    assert t["global_verdict"] == "UNPROVEN"


def test_compute_bearish_hit_when_price_falls(patch_bars):
    patch_bars(_bars([100, 99, 98, 90]))  # düşüş, haber bearish (dir=-1) → hit
    ev = [{"id": "a", "source": "gdelt", "sentiment": "bearish",
           "ts": datetime(2026, 1, 1, tzinfo=UTC).isoformat(), "symbols": {"BTCUSD": -1.0}}]
    with threshold_override(_CFG):
        t = nes.compute(events=ev * 2)
    b = t["buckets"]["gdelt|bearish"]
    assert b["hits"] == 2 and b["avg_dir_return_pct"] > 0  # yön-hizalı pozitif


def test_compute_pending_when_not_matured(patch_bars):
    patch_bars(_bars([100, 101]))  # yalnız 2 bar, horizon=3 → olgunlaşmadı
    ev = [{"id": "a", "source": "rss", "sentiment": "bullish",
           "ts": datetime(2026, 1, 1, tzinfo=UTC).isoformat(), "symbols": {"BTCUSD": 1.0}}]
    with threshold_override(_CFG):
        t = nes.compute(events=ev)
    assert t["matured"] == 0 and t["pending"] == 1
    assert t["buckets"] == {}


def test_compute_insufficient_below_min(patch_bars):
    patch_bars(_bars([100, 101, 102, 110]))
    ev = [{"id": "a", "source": "rss", "sentiment": "bullish",
           "ts": datetime(2026, 1, 1, tzinfo=UTC).isoformat(), "symbols": {"BTCUSD": 1.0}}]
    with threshold_override(_CFG):
        t = nes.compute(events=ev)  # n=1 < min_bucket_n(2)
    assert t["buckets"]["rss|bullish"]["verdict"] == "INSUFFICIENT"
    assert t["global_verdict"] == "UNPROVEN"


# ── viewmodel ─────────────────────────────────────────────────────────────────

def test_viewmodel_shape(patch_bars):
    patch_bars(_bars([100, 101, 102, 110]))
    ev = [{"id": "a", "source": "rss", "sentiment": "bullish",
           "ts": datetime(2026, 1, 1, tzinfo=UTC).isoformat(), "symbols": {"BTCUSD": 1.0}}]
    with threshold_override(_CFG):
        nes.compute(events=ev * 2)
        vm = nes.viewmodel()
    assert vm["shadow_only"] is True
    assert vm["status"] == "OK"
    assert "rss|bullish" in vm["buckets"]
    assert vm["global_verdict"] in ("PREDICTIVE", "UNPROVEN")
