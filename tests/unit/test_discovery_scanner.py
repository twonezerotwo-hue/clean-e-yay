"""K-1 — keşif evreni + tarayıcı testleri (owner kararları 2026-07-04).

Ağa ÇIKMAZ: markets fetch'i, OHLCV ve teknik motor stub'lanır. Kapsam:
kripto kısa-liste süzgeci (stablecoin/dublör/mevcut/likidite/negatif-momentum),
sektör adayları, sinyal kuralları (LONG-only + üst dilim onayı + güven tabanı
+ EV), kota/round-robin, interval cache ve markets TTL yeniden kullanımı.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from packages.discovery import scanner, universe

# ---------------------------------------------------------------------------
# universe.crypto_shortlist
# ---------------------------------------------------------------------------

def _row(cg_id, sym, vol=1e9, chg7=5.0, chg30=10.0, rank=1):
    return {
        "id": cg_id, "symbol": sym, "name": sym.upper(), "market_cap_rank": rank,
        "total_volume": vol,
        "price_change_percentage_7d_in_currency": chg7,
        "price_change_percentage_30d_in_currency": chg30,
    }


def test_crypto_shortlist_filters_and_ranks():
    rows = [
        _row("tether", "usdt"),                      # stablecoin → dışlanır
        _row("wrapped-bitcoin", "wbtc"),             # dublör → dışlanır
        _row("bitcoin", "btc"),                      # zaten canlı evrende → dışlanır
        _row("lowvol", "low", vol=1000),             # likidite tabanı altı
        _row("downer", "dwn", chg7=-5, chg30=-10),   # negatif momentum (LONG-only)
        _row("nochg", "nch", chg7=None),             # momentum ölçülemiyor
        _row("solana", "sol", chg7=4.0, chg30=20.0),
        _row("chainlink", "link", chg7=10.0, chg30=8.0),
        _row("uniswap", "uni", chg7=1.0, chg30=2.0),
    ]
    cfg = {"top_n": 50, "min_total_volume_usd": 20_000_000, "shortlist_n": 2}
    out = universe.crypto_shortlist(cfg, fetch_json=lambda url: rows)
    assert out["status"] == "OK"
    assert out["universe_n"] == 9 and out["eligible_n"] == 3
    syms = [c["symbol"] for c in out["candidates"]]
    # momentum: sol=0.6*20+0.4*4=13.6 > link=0.6*8+0.4*10=8.8 > uni → ilk 2
    assert syms == ["SOLUSD", "LINKUSD"]
    assert out["candidates"][0]["cg_id"] == "solana"


def test_crypto_shortlist_unavailable_on_fetch_failure():
    out = universe.crypto_shortlist({}, fetch_json=lambda url: None)
    assert out["status"] == "UNAVAILABLE" and out["candidates"] == []


# ---------------------------------------------------------------------------
# universe.sector_candidates (K-0b artifact'ından)
# ---------------------------------------------------------------------------

def _write_sector_artifact(tmp_path, monkeypatch, sectors):
    path = tmp_path / "sector_rotation.json"
    monkeypatch.setenv("SECTOR_ROTATION_PATH", str(path))
    path.write_text(json.dumps({"sectors": sectors}), encoding="utf-8")


def test_sector_candidates_rising_only_rank_order(tmp_path, monkeypatch):
    _write_sector_artifact(tmp_path, monkeypatch, [
        {"sector": "XLE", "label": "Enerji", "verdict": "FALLING", "rank": 9, "score": -5},
        {"sector": "XLV", "label": "Sağlık", "verdict": "RISING", "rank": 1, "score": 6.5},
        {"sector": "XLF", "label": "Finans", "verdict": "RISING", "rank": 2, "score": 4.9},
        {"sector": "XLP", "label": "Temel", "verdict": "NEUTRAL", "rank": 6, "score": 0.1},
    ])
    cands = universe.sector_candidates()
    assert [c["symbol"] for c in cands] == ["XLV", "XLF"]
    assert cands[0]["kind"] == "sector_etf" and cands[0]["sector_rank"] == 1


# ---------------------------------------------------------------------------
# scanner — sinyal kuralları + kota/cursor/cache
# ---------------------------------------------------------------------------

def _fake_tf_result(symbol, tf, bars, scores):
    score = scores.get((symbol, tf))
    return SimpleNamespace(
        status="OK",
        score_overview=SimpleNamespace(direction_score=score),
        key_levels=SimpleNamespace(atr=1.5),
    )


def _bars_stub(tf="1d", n=70, close=100.0):
    from packages.data.types import OHLCVBar

    step = {"1h": timedelta(hours=1), "4h": timedelta(hours=4)}.get(tf, timedelta(days=1))
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        OHLCVBar(
            symbol="STUB", timeframe=tf, ts=t0 + i * step,
            open=close, high=close, low=close, close=close,
            source="test", verified=True,
        )
        for i in range(n)
    ]


def _setup(monkeypatch, tmp_path, *, scores, sectors=None, crypto=None, per_run=5):
    monkeypatch.setenv("DISCOVERY_SCAN_PATH", str(tmp_path / "scan.json"))
    _write_sector_artifact(tmp_path, monkeypatch, sectors or [])
    monkeypatch.setattr(
        scanner, "build_timeframe_result",
        lambda sym, tf, bars: _fake_tf_result(sym, tf, bars, scores),
    )
    monkeypatch.setattr(scanner, "load_config", lambda: {
        "scan": {"interval_sec": 900, "per_run": per_run, "min_bars": 60},
        "crypto": {"markets_ttl_sec": 3600},
    })
    monkeypatch.setattr(
        scanner, "_regime_label", lambda: "NEUTRAL"
    )
    # universe.crypto_shortlist'i stub'la (ağ yok)
    from packages.discovery import universe as uni
    monkeypatch.setattr(
        uni, "crypto_shortlist",
        lambda cfg, fetch_json=None: {
            "status": "OK",
            "fetched_at": datetime(2026, 7, 4, 12, 0, tzinfo=UTC).isoformat(),
            "universe_n": 50, "eligible_n": len(crypto or []),
            "candidates": list(crypto or []),
        },
    )


def _run(now=None):
    return scanner.run_if_due(
        now=now or datetime(2026, 7, 4, 12, 0, tzinfo=UTC),
        get_bars=lambda s, tf: _bars_stub(tf),
        fetch_crypto_bars=lambda cg_id, s, tf: _bars_stub(tf, n=300),
    )


def _artifact():
    import os
    return json.loads(Path(os.environ["DISCOVERY_SCAN_PATH"]).read_text(encoding="utf-8"))


def test_signal_requires_1d_plus_confirmation(monkeypatch, tmp_path):
    sectors = [{"sector": "XLV", "label": "Sağlık", "verdict": "RISING", "rank": 1, "score": 6.5}]
    # 1d + 4h bullish (75 → raw 0.5 ≥ min 0.30), 1h nötr → sinyal, entry=4h
    scores = {("XLV", "1d"): 75.0, ("XLV", "4h"): 75.0, ("XLV", "1h"): 50.0}
    _setup(monkeypatch, tmp_path, scores=scores, sectors=sectors)
    r = _run()
    assert r["status"] == "OK" and r["signals_n"] == 1
    res = _artifact()["results"]["XLV"]
    assert res["verdict"] == "WOULD_OPEN_LONG"
    assert res["entry_timeframe"] == "4h"
    assert res["sl"] < res["entry"] < res["tp"]  # long geometrisi
    assert res["confidence"] >= 0.3 and res["expected_value"] > 0


def test_no_signal_without_1d(monkeypatch, tmp_path):
    sectors = [{"sector": "XLF", "label": "Finans", "verdict": "RISING", "rank": 1, "score": 4.0}]
    scores = {("XLF", "1d"): 50.0, ("XLF", "4h"): 75.0, ("XLF", "1h"): 75.0}
    _setup(monkeypatch, tmp_path, scores=scores, sectors=sectors)
    assert _run()["signals_n"] == 0
    assert "htf_1d_not_bullish" in _artifact()["results"]["XLF"]["reasons"]


def test_no_signal_single_tf(monkeypatch, tmp_path):
    sectors = [{"sector": "XLI", "label": "Sanayi", "verdict": "RISING", "rank": 1, "score": 3.0}]
    scores = {("XLI", "1d"): 75.0, ("XLI", "4h"): 50.0, ("XLI", "1h"): 50.0}
    _setup(monkeypatch, tmp_path, scores=scores, sectors=sectors)
    assert _run()["signals_n"] == 0
    assert "single_tf_only" in _artifact()["results"]["XLI"]["reasons"]


def test_no_signal_below_min_confidence(monkeypatch, tmp_path):
    # 56 → raw 0.12 < min_open_confidence 0.30 → güven tabanı bloklar
    sectors = [{"sector": "IYT", "label": "Ulaşım", "verdict": "RISING", "rank": 1, "score": 2.0}]
    scores = {("IYT", "1d"): 56.0, ("IYT", "4h"): 56.0, ("IYT", "1h"): 56.0}
    _setup(monkeypatch, tmp_path, scores=scores, sectors=sectors)
    assert _run()["signals_n"] == 0
    reasons = _artifact()["results"]["IYT"]["reasons"]
    assert any(x.startswith("below_min_open_confidence") for x in reasons)


def test_bearish_candidate_no_short_v1(monkeypatch, tmp_path):
    # LONG-only: güçlü bearish skorlar sinyal ÜRETMEZ
    sectors = [{"sector": "XLE", "label": "Enerji", "verdict": "RISING", "rank": 1, "score": 1.5}]
    scores = {("XLE", "1d"): 20.0, ("XLE", "4h"): 20.0, ("XLE", "1h"): 20.0}
    _setup(monkeypatch, tmp_path, scores=scores, sectors=sectors)
    assert _run()["signals_n"] == 0


def test_quota_round_robin_and_cache(monkeypatch, tmp_path):
    sectors = [
        {"sector": s, "label": s, "verdict": "RISING", "rank": i + 1, "score": 5 - i}
        for i, s in enumerate(["XLV", "XLF", "XLI"])
    ]
    crypto = [{"symbol": "SOLUSD", "cg_id": "solana", "momentum": 13.6}]
    scores = {}  # skorlar None → hepsi NO_SIGNAL (kota mekaniği test ediliyor)
    _setup(monkeypatch, tmp_path, scores=scores, sectors=sectors, crypto=crypto, per_run=2)

    t0 = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
    r1 = _run(t0)
    assert r1["candidates_total"] == 4
    assert r1["scanned"] == ["XLV", "XLF"] and r1["cursor"] == 2

    # interval içinde → CACHED
    r2 = scanner.run_if_due(now=t0 + timedelta(minutes=5))
    assert r2["status"] == "CACHED"

    # interval doldu → kaldığı yerden devam (round-robin)
    r3 = _run(t0 + timedelta(minutes=20))
    assert r3["scanned"] == ["XLI", "SOLUSD"] and r3["cursor"] == 0

    art = _artifact()
    assert set(art["results"]) == {"XLV", "XLF", "XLI", "SOLUSD"}
    assert art["results"]["SOLUSD"]["kind"] == "crypto"


def test_result_ttl_skips_fresh_candidates(monkeypatch, tmp_path):
    # API-bütçe kapısı: sonucu taze aday yeniden analiz edilmez (learning
    # worker tek-seferlik süreç — provider bellek-cache'i koşular arası ölür).
    sectors = [{"sector": "XLV", "label": "Sağlık", "verdict": "RISING", "rank": 1, "score": 6.5}]
    crypto = [{"symbol": "SOLUSD", "cg_id": "solana", "momentum": 13.6}]
    _setup(monkeypatch, tmp_path, scores={}, sectors=sectors, crypto=crypto, per_run=5)

    t0 = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
    r1 = _run(t0)
    assert sorted(r1["scanned"]) == ["SOLUSD", "XLV"]

    # interval doldu ama sonuçlar taze (result_ttl_sec=14400) → hiç analiz yok
    calls = {"n": 0}

    def counting(cg_id, s, tf):
        calls["n"] += 1
        return _bars_stub(tf, n=300)

    r2 = scanner.run_if_due(
        now=t0 + timedelta(minutes=20),
        get_bars=lambda s, tf: _bars_stub(tf),
        fetch_crypto_bars=counting,
    )
    assert r2["status"] == "OK" and r2["scanned"] == [] and calls["n"] == 0

    # tazelik doldu (>4h) → yeniden analiz
    r3 = _run(t0 + timedelta(hours=5))
    assert sorted(r3["scanned"]) == ["SOLUSD", "XLV"]


def test_crypto_universe_reused_within_ttl(monkeypatch, tmp_path):
    sectors = []
    crypto = [{"symbol": "SOLUSD", "cg_id": "solana", "momentum": 13.6}]
    scores = {}
    _setup(monkeypatch, tmp_path, scores=scores, sectors=sectors, crypto=crypto, per_run=1)
    from packages.discovery import universe as uni

    t0 = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
    _run(t0)

    def boom(cfg, fetch_json=None):
        raise AssertionError("markets TTL içinde yeniden çekildi")

    monkeypatch.setattr(uni, "crypto_shortlist", boom)
    r = _run(t0 + timedelta(minutes=20))  # scan interval doldu, markets TTL dolmadı
    # markets listesi YENİDEN ÇEKİLMEDİ (boom patlamadı); aday da sonuç-TTL
    # kapısıyla taze olduğundan yeniden analiz edilmedi.
    assert r["status"] == "OK" and r["scanned"] == []
    assert _artifact()["crypto_universe"]["candidates"][0]["symbol"] == "SOLUSD"
