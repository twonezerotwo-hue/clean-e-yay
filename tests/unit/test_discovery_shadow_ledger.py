"""K-2 — keşif gölge kanıt defteri testleri.

Ağa ÇIKMAZ. Kapsam: damga + aynı (symbol, tf) dedupe, TP-önce/SL-önce çözüm
(aynı barda ikisi → temkinli SL-önce), TTL expiry (bar yokken yalnız yaş),
çözüm-sonrası yeni sinyalin YENİ izleme açması, aday özeti matematiği
(cf_win_rate/avg_r — expired paydaya girmez), S1-2 rotasyonu ve tarayıcı
entegrasyonu (artifact `shadow` bloğu + dönüş sayaçları).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from packages.data.types import OHLCVBar
from packages.discovery import shadow_ledger

T0 = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)


def _signal(sym="XLV", tf="4h", entry=100.0, sl=98.0, tp=106.0, rr=3.0):
    return {
        "symbol": sym, "kind": "sector_etf", "verdict": "WOULD_OPEN_LONG",
        "entry_timeframe": tf, "entry": entry, "sl": sl, "tp": tp, "rr": rr,
        "confidence": 0.5, "expected_value": 0.8, "regime": "NEUTRAL",
    }


def _bar(ts, *, high, low, close=None):
    return OHLCVBar(
        symbol="STUB", timeframe="4h", ts=ts, open=(close or high),
        high=high, low=low, close=(close or high), source="test", verified=True,
    )


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCOVERY_SHADOW_PATH", str(tmp_path / "shadow.jsonl"))


def _events():
    return shadow_ledger.read_recent()


# ---------------------------------------------------------------------------
# damga + dedupe
# ---------------------------------------------------------------------------

def test_stamp_and_dedupe(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    res = {"XLV": _signal()}
    s1 = shadow_ledger.process_run(
        results=res, scanned=["XLV"], now=T0, bars_for=lambda s, tf, k: [],
    )
    assert s1 == {"tracked_new": 1, "resolved": 0, "active": 1}
    ev = _events()[0]
    assert ev["event"] == "track_open" and ev["side"] == "long"
    assert ev["entry"] == 100.0 and ev["ttl_hours"] == 72.0

    # Aynı (symbol, tf) aktifken yeniden damga YOK; taranmamış sembol de damgalanmaz.
    s2 = shadow_ledger.process_run(
        results=res, scanned=["XLV"], now=T0 + timedelta(hours=4),
        bars_for=lambda s, tf, k: [],
    )
    assert s2 == {"tracked_new": 0, "resolved": 0, "active": 1}
    s3 = shadow_ledger.process_run(
        results=res, scanned=[], now=T0 + timedelta(hours=8),
        bars_for=lambda s, tf, k: [],
    )
    assert s3["tracked_new"] == 0


# ---------------------------------------------------------------------------
# çözümleme
# ---------------------------------------------------------------------------

def test_tp_first_missed_win_then_new_tracking(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    res = {"XLV": _signal()}  # entry 100, sl 98, tp 106
    shadow_ledger.process_run(results=res, scanned=["XLV"], now=T0,
                              bars_for=lambda s, tf, k: [])

    # Sonraki koşu: damgadan SONRAKİ barlar TP'ye değiyor (SL'e değil) →
    # missed_win; sinyal sürüyorsa AYNI koşuda yeni izleme açılır (kanıt birikir).
    bars = [
        _bar(T0 - timedelta(hours=4), high=200.0, low=1.0),   # damga öncesi — sayılmaz
        _bar(T0 + timedelta(hours=4), high=103.0, low=99.0),  # değmedi (mfe 1.5R)
        _bar(T0 + timedelta(hours=8), high=107.0, low=99.0),  # TP ✓ (SL ✗)
    ]
    s = shadow_ledger.process_run(
        results=res, scanned=["XLV"], now=T0 + timedelta(hours=9),
        bars_for=lambda s_, tf, k: bars,
    )
    assert s["resolved"] == 1 and s["tracked_new"] == 1 and s["active"] == 1
    rv = next(e for e in _events() if e["event"] == "resolve")
    assert rv["outcome"] == "missed_win" and rv["bars_seen"] == 2
    assert rv["mfe_r"] == 3.5  # (107-100)/2R


def test_same_bar_both_levels_conservative_sl_first(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    res = {"XLV": _signal()}
    shadow_ledger.process_run(results=res, scanned=["XLV"], now=T0,
                              bars_for=lambda s, tf, k: [])
    # Tek barda hem SL hem TP değdi → temkinli: avoided_loss (kazanç şişirilmez).
    bars = [_bar(T0 + timedelta(hours=4), high=110.0, low=97.0)]
    s = shadow_ledger.process_run(
        results={}, scanned=[], now=T0 + timedelta(hours=5),
        bars_for=lambda s_, tf, k: bars,
    )
    assert s["resolved"] == 1
    rv = next(e for e in _events() if e["event"] == "resolve")
    assert rv["outcome"] == "avoided_loss"


def test_ttl_expiry_without_bars(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    shadow_ledger.process_run(results={"SOLUSD": {**_signal("SOLUSD"), "kind": "crypto"}},
                              scanned=["SOLUSD"], now=T0, bars_for=lambda s, tf, k: [])
    # Bar çekilemiyor (bütçe: aday listesinden düştü) → yalnız yaş-expiry.
    s1 = shadow_ledger.process_run(results={}, scanned=[], now=T0 + timedelta(hours=48),
                                   bars_for=lambda s, tf, k: None)
    assert s1["resolved"] == 0  # 4h TTL 72 saat — henüz dolmadı
    s2 = shadow_ledger.process_run(results={}, scanned=[], now=T0 + timedelta(hours=80),
                                   bars_for=lambda s, tf, k: None)
    assert s2["resolved"] == 1 and s2["active"] == 0
    rv = next(e for e in _events() if e["event"] == "resolve")
    assert rv["outcome"] == "expired" and rv["bars_seen"] == 0


# ---------------------------------------------------------------------------
# aday özeti
# ---------------------------------------------------------------------------

def test_candidate_summary_math(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    bars_win = [_bar(T0 + timedelta(hours=4), high=107.0, low=99.0)]

    # XLV: 1 missed_win (rr 3) + 1 avoided_loss + 1 açık izleme (payda dışı)
    shadow_ledger.process_run(results={"XLV": _signal()}, scanned=["XLV"], now=T0,
                              bars_for=lambda s, tf, k: [])
    shadow_ledger.process_run(results={"XLV": _signal()}, scanned=["XLV"],
                              now=T0 + timedelta(hours=5),
                              bars_for=lambda s, tf, k: bars_win)
    t1 = T0 + timedelta(hours=10)
    bars_loss2 = [_bar(t1 + timedelta(hours=4), high=101.0, low=97.0)]
    shadow_ledger.process_run(results={"XLV": _signal(tf="1d")}, scanned=["XLV"], now=t1,
                              bars_for=lambda s, tf, k: bars_loss2 if tf == "4h" else [])
    # 4h izlemesi avoided_loss oldu; 1d izlemesi açık kaldı → 80h sonra bar yok → süre 240h dolmadı
    shadow_ledger.process_run(results={}, scanned=[], now=t1 + timedelta(hours=8),
                              bars_for=lambda s, tf, k: bars_loss2 if tf == "4h" else [])

    view = shadow_ledger.candidate_summary()
    xlv = view["candidates"]["XLV"]
    assert xlv["n_signals"] == 3
    assert xlv["missed_win"] == 1 and xlv["avoided_loss"] == 1
    assert xlv["cf_win_rate"] == 0.5           # 1 / (1+1)
    assert xlv["avg_r"] == 1.0                 # (+3.0 − 1.0) / 2
    assert sorted(xlv["timeframes"]) == ["1d", "4h"]
    assert view["active_n"] == 1               # 1d izlemesi hâlâ açık


# ---------------------------------------------------------------------------
# S1-2 rotasyonu
# ---------------------------------------------------------------------------

def test_log_rotation_and_archive_read(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    # ~1KB limit: 5 event (~350B/adet) tek devrilme üretir — arşiv + ana dosya
    # birlikte TÜM event'leri korur (iki devrilme olsaydı en eski nesil düşerdi).
    monkeypatch.setenv("DISCOVERY_SHADOW_MAX_MB", "0.001")
    for i in range(5):
        shadow_ledger.process_run(
            results={f"S{i}": _signal(f"S{i}")}, scanned=[f"S{i}"],
            now=T0 + timedelta(hours=i), bars_for=lambda s, tf, k: [],
        )
    p = Path(tmp_path / "shadow.jsonl")
    assert p.with_suffix(p.suffix + ".1").exists()  # devrildi
    syms = {e["symbol"] for e in shadow_ledger.read_recent()}
    assert syms == {"S0", "S1", "S2", "S3", "S4"}  # okuyucu arşive uzanıyor


# ---------------------------------------------------------------------------
# tarayıcı entegrasyonu (artifact `shadow` bloğu)
# ---------------------------------------------------------------------------

def test_scanner_embeds_shadow_ledger(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from packages.discovery import scanner
    from packages.discovery import universe as uni

    monkeypatch.setenv("DISCOVERY_SCAN_PATH", str(tmp_path / "scan.json"))
    _isolate(monkeypatch, tmp_path)
    sector_path = tmp_path / "sector_rotation.json"
    monkeypatch.setenv("SECTOR_ROTATION_PATH", str(sector_path))
    sector_path.write_text(json.dumps({"sectors": [
        {"sector": "XLV", "label": "Sağlık", "verdict": "RISING",
         "rank": 1, "score": 6.5},
    ]}), encoding="utf-8")

    # 1d + 4h bullish → sinyal (entry_tf=4h); teknik motor + ağ stub'lı.
    scores = {("XLV", "1d"): 75.0, ("XLV", "4h"): 75.0, ("XLV", "1h"): 50.0}
    monkeypatch.setattr(
        scanner, "build_timeframe_result",
        lambda sym, tf, bars: SimpleNamespace(
            status="OK",
            score_overview=SimpleNamespace(direction_score=scores.get((sym, tf))),
            key_levels=SimpleNamespace(atr=1.5),
        ),
    )
    monkeypatch.setattr(scanner, "load_config", lambda: {
        "scan": {"interval_sec": 900, "per_run": 5, "min_bars": 60},
        "crypto": {"markets_ttl_sec": 3600},
    })
    monkeypatch.setattr(scanner, "_regime_label", lambda: "NEUTRAL")
    monkeypatch.setattr(
        uni, "crypto_shortlist",
        lambda cfg, fetch_json=None: {"status": "OK", "fetched_at": T0.isoformat(),
                                      "universe_n": 0, "eligible_n": 0, "candidates": []},
    )

    def flat_bars(tf):
        # Damgadan ÖNCEKİ düz barlar (2026-01-01…) → çözümleme tetiklenmez.
        step = {"1h": timedelta(hours=1), "4h": timedelta(hours=4)}.get(tf, timedelta(days=1))
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        return [
            OHLCVBar(symbol="STUB", timeframe=tf, ts=t0 + i * step,
                     open=100.0, high=100.0, low=100.0, close=100.0,
                     source="test", verified=True)
            for i in range(70)
        ]

    r = scanner.run_if_due(now=T0, get_bars=lambda s, tf: flat_bars(tf))
    assert r["signals_n"] == 1
    assert r["shadow"] == {"tracked_new": 1, "resolved": 0, "active": 1}
    art = json.loads((tmp_path / "scan.json").read_text(encoding="utf-8"))
    shadow = art["shadow"]
    assert shadow["last_run"]["tracked_new"] == 1
    assert shadow["candidates"]["XLV"]["n_signals"] == 1
    assert shadow["candidates"]["XLV"]["resolved"] == 0
    ev = shadow_ledger.read_recent()[0]
    assert ev["event"] == "track_open" and ev["symbol"] == "XLV"
    assert ev["timeframe"] == "4h" and ev["sl"] < ev["entry"] < ev["tp"]
