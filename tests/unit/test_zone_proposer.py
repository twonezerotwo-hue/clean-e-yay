"""Aday bölge önericisi testleri (owner kesişim yöntemi, mekanik geometri).

Saf geometri (pivot/log-çizgi/kesişim/kümeleme) + uçtan uca analiz: bilinen
log-doğrusal destek + log-fib seviyesinin AYNI bölgede kesiştiği sentetik
haftalık seride confluence bölgesi bulunmalı.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.data.types import OHLCVBar
from packages.learning import zone_proposer as zp

_T0 = datetime(2020, 1, 6, tzinfo=UTC)  # bir Pazartesi


def _bar(i, hi, lo, close=None):
    c = close if close is not None else (hi + lo) / 2
    return OHLCVBar(symbol="TEST", timeframe="1w", ts=_T0 + timedelta(weeks=i),
                    open=c, high=hi, low=lo, close=c, volume=1.0)


def test_fit_log_line_and_price_at():
    """Log-uzayda doğru: iki nokta → eğim/kesişim; ara nokta geometrik ortalama."""
    slope, intercept = zp.fit_log_line(0, 100.0, 10, 1000.0)
    assert zp.line_price_at(slope, intercept, 0) == pytest.approx(100.0)
    assert zp.line_price_at(slope, intercept, 10) == pytest.approx(1000.0)
    # 5. barda log-orta = 10^2.5 ≈ 316.2 (lineer orta 550 DEĞİL — log kanıtı)
    assert zp.line_price_at(slope, intercept, 5) == pytest.approx(316.23, abs=0.1)


def test_line_intersection():
    """Yükselen ve alçalan iki doğru bilinen barda kesişir."""
    up = zp.Line(*zp.fit_log_line(0, 100.0, 10, 200.0), kind="support", touches=2)
    down = zp.Line(*zp.fit_log_line(0, 400.0, 10, 100.0), kind="resistance", touches=2)
    x = zp.line_intersection(up, down)
    assert x is not None
    xi, xp = x
    assert 0 < xi < 10           # aralarında bir yerde kesişir
    # kesişimde iki doğru aynı fiyatı verir
    assert xp == pytest.approx(zp.line_price_at(down.slope, down.intercept, xi))


def test_parallel_lines_no_intersection():
    a = zp.Line(0.01, 2.0, "support", 2)
    b = zp.Line(0.01, 2.5, "resistance", 2)
    assert zp.line_intersection(a, b) is None


def test_find_pivots_detects_extremes():
    """Belirgin tepe ve dip fraktal pivot olarak bulunur."""
    heights = [10, 11, 12, 20, 12, 11, 10, 9, 5, 9, 10, 11, 12]  # tepe@3, dip@8
    bars = [_bar(i, h + 0.5, h - 0.5) for i, h in enumerate(heights)]
    pivots = zp.find_pivots(bars, span=2)
    highs = {p.index for p in pivots if p.kind == "H"}
    lows = {p.index for p in pivots if p.kind == "L"}
    assert 3 in highs
    assert 8 in lows


def test_cluster_levels_micro_price_not_rounded_to_zero():
    """Mikro-fiyatlı asset (HTX ≈ $0.000002): bölge kenarları 0.0'a EZİLMEZ
    (canlı bulgu 2026-07-12: 0.0-0.0 bölge iptal bile edilemiyordu)."""
    levels = [
        {"price": 1.8e-06, "source": "fib_retr", "at": None},
        {"price": 1.82e-06, "source": "support_line", "at": None},
    ]
    zones = zp.cluster_levels(levels, tol=0.03)
    assert len(zones) == 1
    assert zones[0]["low"] > 0
    assert zones[0]["low"] == pytest.approx(1.8e-06, rel=0.01)


def test_cluster_levels_scores_distinct_sources():
    """Aynı bölgedeki farklı kaynaklar confluence'ı artırır; aynı kaynak tekrarı
    saymaz; uzak seviye ayrı bölge."""
    levels = [
        {"price": 100.0, "source": "fib_retr", "at": None},
        {"price": 101.0, "source": "support_line", "at": "2026-09-01"},
        {"price": 100.5, "source": "fib_retr", "at": None},  # aynı kaynak → +0
        {"price": 200.0, "source": "fib_ext", "at": None},   # uzak → ayrı bölge
    ]
    zones = zp.cluster_levels(levels, tol=0.03)
    zones.sort(key=lambda z: z["mid"])
    assert len(zones) == 2
    assert zones[0]["confluence"] == 2          # fib_retr + support_line
    assert zones[0]["at"] == "2026-09-01"       # zaman-taşıyan üye tarihi
    assert zones[1]["confluence"] == 1


def _rising_support_series():
    """Log-doğrusal yükselen destekli, bir tepeden düzeltmeli sentetik seri.

    Destek S(i)=10^(2+g·i); NORMAL barlar desteğin ~%15 üstünde bir bantta
    gezer, iki dip (bar 6, 30) desteğe DEĞER (gerçek yerel minimum), ara tepe
    (20) ve makro tepe (45) yerel maksimum, 46-54 tepeden düzeltme aşağı iner."""
    import math
    g = math.log10(1.005)  # haftada %0.5 log-eğim (diplerin altında kalacak kadar yatay)
    bars = []
    for i in range(60):
        s = 10 ** (2 + g * i)             # destek çizgisi
        if i in (6, 30):                   # desteğe değen iki dip (yerel min)
            bars.append(_bar(i, s * 1.05, s * 1.00))
        elif i == 20:                      # ara tepe (yerel max)
            bars.append(_bar(i, s * 1.60, s * 1.50, close=s * 1.55))
        elif i == 45:                      # makro tepe (yerel max)
            bars.append(_bar(i, s * 1.95, s * 1.85, close=s * 1.90))
        elif 46 <= i <= 54:                # tepeden düzeltme aşağı
            f = 1.85 - (i - 45) * 0.085
            bars.append(_bar(i, s * (f + 0.05), s * f, close=s * (f + 0.02)))
        else:                              # normal bant (~%15 üstü)
            bars.append(_bar(i, s * 1.20, s * 1.15, close=s * 1.17))
    return bars


def test_analyze_bars_finds_confluence_zone():
    """Uçtan uca: yükselen destek + fib + tarihî pivotların olduğu seride en az
    bir confluence≥2 bölge, hesaplanan bir kaynak içerir ve fiyata göre etiketli."""
    bars = _rising_support_series()
    cfg = {"pivot_span": 3, "min_weekly_bars": 20, "horizon_bars": 12,
           "cluster_tol_pct": 3.0, "min_confluence": 2, "max_zones": 5}
    res = zp.analyze_bars(bars, cfg)
    assert res["status"] == "OK"
    assert res["pivots"]["highs"] >= 2 and res["pivots"]["lows"] >= 2
    assert res["zones"], "en az bir confluence bölgesi beklenirdi"
    calc = {"support_line", "resistance_line", "line_cross", "fib_retr", "fib_ext"}
    for z in res["zones"]:
        assert z["confluence"] >= 2
        assert calc.intersection(z["sources"])   # yalnız yatay-pivot bölgesi yok
        assert z["side"] in ("altında", "üstünde")
        assert z["low"] <= z["mid"] <= z["high"]


def test_analyze_bars_insufficient_history():
    """Kısa seri → INSUFFICIENT (makro yöntem derin tarih ister)."""
    bars = [_bar(i, 100 + i, 99 + i) for i in range(10)]
    res = zp.analyze_bars(bars, {"pivot_span": 3, "min_weekly_bars": 30})
    assert res["status"] == "INSUFFICIENT"
    assert res["zones"] == []


def test_run_if_due_and_viewmodel_roundtrip(tmp_path, monkeypatch):
    """compute→write→viewmodel: zone'lu asset satırı döner; taze artifact SKIP."""
    out = tmp_path / "zone_proposer.json"
    monkeypatch.setenv("ZONE_PROPOSER_PATH", str(out))
    # Evreni tek sahte sembole indir; onun haftalık barları sentetik confluence serisi.
    monkeypatch.setattr(zp, "_universe", lambda cfg: [{"symbol": "TEST"}])
    monkeypatch.setattr(zp, "_weekly_bars",
                        lambda sym, cg_id=None: _rising_support_series())
    monkeypatch.setattr(zp, "_cfg", lambda: {
        "pivot_span": 3, "min_weekly_bars": 20, "horizon_bars": 12,
        "cluster_tol_pct": 3.0, "min_confluence": 2, "max_zones": 5})

    r = zp.run_if_due()
    assert r["status"] == "OK"
    assert r["assets"] == 1
    assert r["with_zones"] == 1
    assert out.exists()

    vm = zp.viewmodel()
    assert vm["status"] == "OK"
    assert vm["assets"] and vm["assets"][0]["symbol"] == "TEST"
    assert vm["assets"][0]["top_confluence"] >= 2

    # ikinci koşu taze artifact → SKIP_FRESH (yeniden hesaplanmaz)
    assert zp.run_if_due()["status"] == "SKIP_FRESH"


def test_run_if_due_self_heals_no_data_artifact(tmp_path, monkeypatch):
    """Hiçbir asset'i OK olmayan artifact (sağlayıcı kesintisi koşusu) taze
    sayılmaz — sonraki koşu yeniden dener (24 saat kilitleme yok)."""
    import json
    from datetime import UTC, datetime

    out = tmp_path / "zone_proposer.json"
    out.write_text(json.dumps({
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": "zone_proposer_v1",
        "assets": [{"symbol": "BTCUSD", "status": "NO_DATA", "zones": []}],
    }), encoding="utf-8")
    monkeypatch.setenv("ZONE_PROPOSER_PATH", str(out))
    monkeypatch.setattr(zp, "_universe", lambda cfg: [{"symbol": "TEST"}])
    monkeypatch.setattr(zp, "_weekly_bars",
                        lambda sym, cg_id=None: _rising_support_series())
    monkeypatch.setattr(zp, "_cfg", lambda: {
        "pivot_span": 3, "min_weekly_bars": 20, "horizon_bars": 12,
        "cluster_tol_pct": 3.0, "min_confluence": 2, "max_zones": 5})

    r = zp.run_if_due()          # bozuk artifact'a rağmen yeniden hesaplar
    assert r["status"] == "OK"
    assert r["with_zones"] == 1


def test_universe_includes_discovery_candidates(monkeypatch):
    """Keşif evreni (owner kararı 2026-07-12): kripto kısa listesi cg_id ile,
    yükselen ETF'ler ve canlı sinyal sembolleri (ETF / cg_id'li kripto) girer;
    discovery_max sınırı ve çift-kayıt eleme çalışır."""
    art = {
        "crypto_universe": {"candidates": [
            {"symbol": "ZECUSD", "cg_id": "zcash"},
            {"symbol": "WBTUSD", "cg_id": "whitebit"},
        ]},
        "rising_sectors": [{"symbol": "XLK"}],
        "results": {
            "XLV": {"kind": "sector_etf"},
            "ZECUSD": {"kind": "crypto"},       # cg_map'te var → girer
            "HYPEUSD": {"kind": "crypto"},      # cg_id bilinmiyor → giremez
        },
        "signal_symbols": ["XLV", "ZECUSD", "HYPEUSD"],
    }
    from packages.discovery import scanner as _sc
    monkeypatch.setattr(_sc, "_load_artifact", lambda: art)

    cands = zp._universe({"discovery_candidates": True, "discovery_max": 10})
    by_sym = {c["symbol"]: c for c in cands}
    assert "BTCUSD" in by_sym                       # rotasyon çekirdeği durur
    assert by_sym["ZECUSD"]["cg_id"] == "zcash"     # kısa liste cg_id ile
    assert "XLK" in by_sym and "XLV" in by_sym      # yükselen + sinyal ETF
    assert "HYPEUSD" not in by_sym                  # kör kripto çağrısı yok
    assert len(cands) == len(by_sym)                # çift kayıt yok

    # discovery_max=1 → keşiften yalnız 1 aday eklenir
    few = zp._universe({"discovery_candidates": True, "discovery_max": 1})
    core_n = len(zp._universe({"discovery_candidates": False}))
    assert len(few) == core_n + 1


def test_notify_new_strong_zone(tmp_path, monkeypatch):
    """Yeni ★4+ bölge → bildirim; örtüşen eski bölge / zayıf bölge / ilk koşu
    (prev yok) → sessiz."""
    import packages.notifications as notif
    monkeypatch.setattr(notif, "NOTIFICATIONS_PATH", tmp_path / "notif.jsonl")

    prev = {"assets": [{"symbol": "TLT", "zones": [
        {"low": 80.0, "high": 82.0, "confluence": 5}]}]}
    rep = {"assets": [
        {"symbol": "TLT", "zones": [
            {"low": 80.5, "high": 82.5, "confluence": 5, "sources": ["a"],
             "dist_pct": -2.0, "side": "altında"},          # eskiyle örtüşür → yok
            {"low": 90.0, "high": 91.0, "confluence": 4, "sources": ["a", "b"],
             "dist_pct": 5.0, "side": "üstünde"},           # YENİ ★4 → bildirim
            {"low": 95.0, "high": 96.0, "confluence": 2, "sources": ["a"],
             "dist_pct": 8.0, "side": "üstünde"},           # zayıf → yok
        ]},
    ]}
    assert zp._notify_new_zones(None, rep, {}) == 0          # ilk koşu sessiz
    n = zp._notify_new_zones(prev, rep, {"notify_min_confluence": 4})
    assert n == 1
    recent = notif.list_recent(10)
    assert any(r.type == "zone_candidate" and "TLT" in r.title for r in recent)
