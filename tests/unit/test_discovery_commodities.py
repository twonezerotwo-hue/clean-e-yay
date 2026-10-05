"""Emtia keşif evreni (owner kararı 2026-10-05) — ağa ÇIKMAZ.

Kapsam: momentum kısa listesi (yalnız pozitif, yetersiz bar atlanır, hiç veri
yoksa UNAVAILABLE), tarayıcının emtia dalı (Yahoo ticker ile bar; 4h 1h'ten
türetilir), artifact + görünümdeki emtia evreni, TTL içinde yeniden kullanım.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from packages.data.types import OHLCVBar
from packages.discovery import scanner, universe

T0 = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _bars(tf: str, closes: list[float]) -> list[OHLCVBar]:
    step = {"1h": timedelta(hours=1), "4h": timedelta(hours=4)}.get(tf, timedelta(days=1))
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        OHLCVBar(symbol="STUB", timeframe=tf, ts=start + i * step, open=c, high=c, low=c,
                 close=c, source="test", verified=True)
        for i, c in enumerate(closes)
    ]


def _trend(n: int, start: float, end: float) -> list[float]:
    return [start + (end - start) * i / (n - 1) for i in range(n)]


ITEMS = {
    "COPPER": {"ticker": "HG=F", "label": "Bakır"},
    "COCOA": {"ticker": "CC=F", "label": "Kakao"},
    "WHEAT": {"ticker": "ZW=F", "label": "Buğday"},
    "SHORT": {"ticker": "XX=F", "label": "Kısa veri"},
}


def _daily(ticker, symbol, tf):
    return {
        "HG=F": _bars("1d", _trend(60, 100.0, 120.0)),   # +momentum
        "CC=F": _bars("1d", _trend(60, 100.0, 150.0)),   # en güçlü
        "ZW=F": _bars("1d", _trend(60, 100.0, 90.0)),    # negatif → elenir
        "XX=F": _bars("1d", _trend(10, 100.0, 130.0)),   # 30g ölçülemez → elenir
    }.get(ticker)


def test_commodity_shortlist_positive_momentum_ranked():
    out = universe.commodity_shortlist({"items": ITEMS, "shortlist_n": 2}, fetch_bars=_daily)
    assert out["status"] == "OK" and out["universe_n"] == 4 and out["eligible_n"] == 2
    assert [c["symbol"] for c in out["candidates"]] == ["COCOA", "COPPER"]
    assert out["candidates"][0]["ticker"] == "CC=F" and out["candidates"][0]["chg_30d_pct"] > 0


def test_commodity_shortlist_unavailable_without_data():
    out = universe.commodity_shortlist({"items": ITEMS}, fetch_bars=lambda t, s, tf: None)
    assert out["status"] == "UNAVAILABLE" and out["candidates"] == []


def _setup(monkeypatch, tmp_path, calls):
    monkeypatch.setenv("DISCOVERY_SCAN_PATH", str(tmp_path / "scan.json"))
    monkeypatch.setenv("DISCOVERY_SHADOW_PATH", str(tmp_path / "shadow.jsonl"))
    monkeypatch.setenv("SECTOR_ROTATION_PATH", str(tmp_path / "sector.json"))
    monkeypatch.setattr(scanner, "load_config", lambda: {
        "scan": {"interval_sec": 900, "per_run": 5, "min_bars": 60},
        "crypto": {"markets_ttl_sec": 3600},
        "commodities": {"items": ITEMS, "shortlist_n": 1, "ranking_ttl_sec": 3600},
    })
    monkeypatch.setattr(scanner, "_regime_label", lambda: "NEUTRAL")
    monkeypatch.setattr(universe, "crypto_shortlist", lambda cfg, fetch_json=None: {
        "status": "OK", "fetched_at": T0.isoformat(), "candidates": []})
    monkeypatch.setattr(scanner, "build_timeframe_result", lambda sym, tf, bars: SimpleNamespace(
        status="OK", score_overview=SimpleNamespace(direction_score=75.0),
        key_levels=SimpleNamespace(atr=1.0)))

    def fetch(ticker, symbol, tf):
        calls.append((ticker, symbol, tf))
        if tf == "1d":
            return _daily(ticker, symbol, tf) if len(calls) <= len(ITEMS) else _bars("1d", _trend(300, 100, 150))
        return _bars(tf, _trend(400, 100, 150))

    return fetch


def test_scanner_analyzes_commodity_via_ticker_and_resamples_4h(monkeypatch, tmp_path):
    calls: list[tuple] = []
    fetch = _setup(monkeypatch, tmp_path, calls)
    r = scanner.run_if_due(now=T0, get_bars=lambda s, tf: [], fetch_crypto_bars=lambda *a: None,
                           fetch_ticker_bars=fetch)
    assert r["status"] == "OK" and r["scanned"] == ["COCOA"]
    analysis_tfs = [tf for t, s, tf in calls[len(ITEMS):] if s == "COCOA"]
    assert "4h" not in analysis_tfs and {"1h", "1d"} <= set(analysis_tfs)  # 4h = 1h'ten resample
    art = json.loads(Path(os.environ["DISCOVERY_SCAN_PATH"]).read_text(encoding="utf-8"))
    assert art["commodity_universe"]["candidates"][0]["symbol"] == "COCOA"
    assert art["results"]["COCOA"]["kind"] == "commodity"
    vm = scanner.viewmodel()
    assert vm["universe"]["commodities"] == {
        "status": "OK", "count": 1, "fetched_at": art["commodity_universe"]["fetched_at"],
        "symbols": ["COCOA"]}


def test_commodity_ranking_reused_within_ttl(monkeypatch, tmp_path):
    calls: list[tuple] = []
    fetch = _setup(monkeypatch, tmp_path, calls)
    scanner.run_if_due(now=T0, get_bars=lambda s, tf: [], fetch_crypto_bars=lambda *a: None,
                       fetch_ticker_bars=fetch)
    ranked = sum(1 for _, _, tf in calls if tf == "1d")
    calls.clear()
    monkeypatch.setattr(universe, "commodity_shortlist", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    scanner.run_if_due(now=T0 + timedelta(minutes=20), get_bars=lambda s, tf: [],
                       fetch_crypto_bars=lambda *a: None, fetch_ticker_bars=fetch)
    assert ranked >= len(ITEMS)  # ilk koşu sıraladı; ikinci koşu TTL içinde yeniden sıralamadı
