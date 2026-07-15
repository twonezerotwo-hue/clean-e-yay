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
import time

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


def backfill_symbol(symbol: str, ticker: str, rng: str = "5y") -> dict:
    """Tek sembol backfill: 5y çek + mevcut arşivle birleştir (canlı bar kazanır)."""
    from packages.data.providers.ohlcv import history

    fetched = _fetch(ticker, symbol, rng)
    if not fetched:
        return {"symbol": symbol, "status": "FETCH_EMPTY"}
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


def ensure_depth(min_bars: int = MIN_BARS) -> dict:
    """Sığ makro arşivleri 5y backfill'le doldur; derinse no-op.

    Dönen özet: {status, checked, filled, skipped, failed}."""
    from packages.data.providers.ohlcv import history

    if not history.enabled():
        return {"status": "DISABLED"}
    shallow = []
    for sym in BACKFILL_TICKERS:
        if sym in _MEMO["ok"]:
            continue
        bars = len(history.load(sym, "1d"))
        if bars >= min_bars:
            _MEMO["ok"].add(sym)
        else:
            shallow.append((sym, bars))
    if not shallow:
        return {"status": "DEEP", "checked": len(BACKFILL_TICKERS)}
    now = time.monotonic()
    if _MEMO["last_attempt"] and now - _MEMO["last_attempt"] < RETRY_SEC:
        return {"status": "RETRY_WAIT", "shallow": [s for s, _ in shallow]}
    _MEMO["last_attempt"] = now
    filled, failed = [], []
    for sym, before in shallow:
        try:
            r = backfill_symbol(sym, BACKFILL_TICKERS[sym])
            if r["status"] == "OK" and r["after"] >= min_bars:
                _MEMO["ok"].add(sym)
                filled.append(f"{sym}:{before}->{r['after']}")
            else:
                failed.append(f"{sym}:{r['status']}")
        except Exception as exc:  # tek sembol hatası bekçiyi durdurmasın
            failed.append(f"{sym}:{type(exc).__name__}")
    _log.info("macro_backfill: filled=%s failed=%s", filled, failed)
    return {"status": "FILLED" if filled else "FAILED", "filled": filled, "failed": failed}
