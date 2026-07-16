"""Makro arşiv derinlik bekçisi — fundamental_v4 / rejim-momentum veri tabanı.

v4.1 (yüzdelik momentum) DXY/US10Y için 187+ gün, rank penceresi tam dolsun
diye ~379 gün arşiv ister. 5y backfill lokalde elle koşuldu ama `data/runtime`
git'e girmez → AWS arşivi sığ kalır ve v4 orada None'a düşerdi (lokal↔AWS
davranış AYRIŞMASI — kural 6 ihlali). Bu bekçi learning worker döngüsünde
makro arşiv derinliğini kontrol eder; eşiğin altındaki sembole TEK SEFERLİK
5y backfill koşar (yfinance). Böylece her ortam kendi arşivini kendisi doldurur.

- Off-tick: yalnız learning worker çağırır (karar yoluna ağ çağrısı GİRMEZ).
- `BAR_HISTORY_ENABLED` kapalıysa no-op (bayt-aynı).
- Süreç-içi memo: derinlik bir kez TAM görülünce tekrar ölçülmez; başarısız
  fetch en erken `RETRY_SEC` sonra yeniden denenir (yfinance'e vurma).
- PAPER_SAFE — yalnız veri arşivi yazar.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta

_log = logging.getLogger("learning.macro_backfill")

# Yahoo ticker'ları (rotasyon evreni + makro eksenler; BTC = BTC-USD).
# NOT: scripts/backfill_history.py bu haritaya DELEGE eder (tek kaynak).
BACKFILL_TICKERS: dict[str, str] = {
    "BTCUSD": "BTC-USD",
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "BRENT": "BZ=F",
    "DXY": "DX-Y.NYB",
    "SP500": "^GSPC",
    "VIX": "^VIX",
    "MOVE": "^MOVE",   # tahvil-piyasası oynaklığı — sentinel kripto-DIŞI stres bacağı
    "TLT": "TLT",
    "HYG": "HYG",
    "LQD": "LQD",
    "US10Y": "^TNX",
    "US05Y": "^FVX",
}

# v4.1 ihtiyacı: eksen 127 + rank penceresi 252 = 379; 400 güvenli eşik.
MIN_BARS = 400
RETRY_SEC = 6 * 3600

# FRED-kaynaklı makro seriler (FAZ-2 veri omurgası; yfinance'te temiz karşılığı
# yok). Sembol → min-bar eşiği AYRI: US02Y günlük (~1255/5y), CPI AYLIK
# (~60 gözlem/5y) — tek MIN_BARS eşiği CPI'yi sonsuza dek "sığ" gösterirdi.
# FRED_API_KEY yoksa bu semboller ATLANIR (uydurma yok; AWS .env anahtarı
# git-senkron taşınır, kural-6 — her ortam kendi arşivini kendi doldurur).
FRED_BACKFILL_MIN_BARS: dict[str, int] = {"US02Y": 400, "CPI": 48}
FRED_START_DAYS = 5 * 365 + 45  # 5y + CPI yayın-gecikme payı

# Süreç-içi durum: {"ok": derinliği tam görülen semboller, "last_attempt": ts}
_MEMO: dict = {"ok": set(), "last_attempt": 0.0}


def _fetch(ticker: str, symbol: str, rng: str) -> list:
    from packages.data.providers.ohlcv import yfinance

    orig = yfinance._TF_PLAN["1d"]
    yfinance._TF_PLAN["1d"] = (orig[0], rng)  # geçici; canlı plan değişmez
    try:
        return yfinance.fetch_by_ticker(ticker, symbol, "1d") or []
    finally:
        yfinance._TF_PLAN["1d"] = orig


def _write_merged(symbol: str, fetched: list) -> dict:
    """Çekilen barları mevcut arşivle birleştirip atomik yazar (canlı bar kazanır)."""
    from packages.data.providers.ohlcv import history

    existing = history.load(symbol, "1d")
    merged = history.merged(fetched, existing)
    path = history._path(symbol, "1d")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for b in merged:
            fh.write(json.dumps(b.model_dump(mode="json")) + "\n")
    tmp.replace(path)
    yrs = (merged[-1].ts - merged[0].ts).days / 365.0
    return {
        "symbol": symbol, "status": "OK", "before": len(existing),
        "fetched": len(fetched), "after": len(merged), "years": round(yrs, 1),
    }


def backfill_symbol(symbol: str, ticker: str, rng: str = "5y") -> dict:
    """Tek sembol backfill (yfinance): 5y çek + mevcut arşivle birleştir."""
    fetched = _fetch(ticker, symbol, rng)
    if not fetched:
        return {"symbol": symbol, "status": "FETCH_EMPTY"}
    return _write_merged(symbol, fetched)


def _fetch_fred(symbol: str, start: str) -> list:
    from packages.data.providers.price import fred

    return fred.get_history(symbol, start=start) or []


def backfill_symbol_fred(symbol: str) -> dict:
    """Tek FRED sembolü backfill (US02Y/CPI): 5y seri çek + arşivle birleştir.

    FRED_API_KEY yoksa get_history [] döner → FETCH_EMPTY (uydurma/fallback YOK)."""
    start = (datetime.now(UTC) - timedelta(days=FRED_START_DAYS)).date().isoformat()
    fetched = _fetch_fred(symbol, start)
    if not fetched:
        return {"symbol": symbol, "status": "FETCH_EMPTY"}
    return _write_merged(symbol, fetched)


def ensure_depth(min_bars: int = MIN_BARS) -> dict:
    """Sığ makro arşivleri 5y backfill'le doldur; derinse no-op.

    yfinance sembolleri `min_bars` eşiğiyle; FRED sembolleri (US02Y/CPI) kendi
    eşiğiyle ve YALNIZ FRED_API_KEY varsa (yoksa dürüstçe atlanır, özet not düşer).
    Dönen özet: {status, checked, filled, failed[, fred]}."""
    from packages.data.providers.ohlcv import history

    if not history.enabled():
        return {"status": "DISABLED"}
    fred_key = bool(os.environ.get("FRED_API_KEY"))
    # sembol → (min eşik, kaynak) — tek tarama, kaynak başına doğru eşik.
    targets: dict[str, tuple[int, str]] = {s: (min_bars, "yf") for s in BACKFILL_TICKERS}
    if fred_key:
        targets.update({s: (m, "fred") for s, m in FRED_BACKFILL_MIN_BARS.items()})
    shallow: list[tuple[str, int]] = []
    for sym, (need, _src) in targets.items():
        if sym in _MEMO["ok"]:
            continue
        bars = len(history.load(sym, "1d"))
        if bars >= need:
            _MEMO["ok"].add(sym)
        else:
            shallow.append((sym, bars))
    if not shallow:
        out = {"status": "DEEP", "checked": len(targets)}
        if not fred_key:
            out["fred"] = "NO_KEY"  # US02Y/CPI bu ortamda doldurulamaz (dürüst not)
        return out
    now = time.monotonic()
    if _MEMO["last_attempt"] and now - _MEMO["last_attempt"] < RETRY_SEC:
        return {"status": "RETRY_WAIT", "shallow": [s for s, _ in shallow]}
    _MEMO["last_attempt"] = now
    filled, failed = [], []
    for sym, before in shallow:
        need, src = targets[sym]
        try:
            r = (
                backfill_symbol_fred(sym)
                if src == "fred"
                else backfill_symbol(sym, BACKFILL_TICKERS[sym])
            )
            if r["status"] == "OK" and r["after"] >= need:
                _MEMO["ok"].add(sym)
                filled.append(f"{sym}:{before}->{r['after']}")
            else:
                failed.append(f"{sym}:{r['status']}")
        except Exception as exc:  # tek sembol hatası bekçiyi durdurmasın
            failed.append(f"{sym}:{type(exc).__name__}")
    _log.info("macro_backfill: filled=%s failed=%s", filled, failed)
    out = {"status": "FILLED" if filled else "FAILED", "filled": filled, "failed": failed}
    if not fred_key:
        out["fred"] = "NO_KEY"
    return out
