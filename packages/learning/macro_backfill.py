"""Makro arşiv derinlik ve tazelik bekçisi — fundamental_v4 / rejim-momentum veri tabanı.

v4.1 (yüzdelik momentum) DXY/US10Y için 187+ gün, rank penceresi tam dolsun
diye ~379 gün arşiv ister. 5y backfill lokalde elle koşuldu ama `data/runtime`
git'e girmez → AWS arşivi sığ kalır ve v4 orada None'a düşerdi (lokal↔AWS
davranış AYRIŞMASI — kural 6 ihlali). Bu bekçi learning worker döngüsünde
makro arşiv derinliğini kontrol eder; eşiğin altındaki sembole TEK SEFERLİK
5y backfill koşar (yfinance). Böylece her ortam kendi arşivini kendisi doldurur.
Canlı bar yolundan geçmeyen seriler için tazeliği de bu bekçi sağlar: son bar
beklenen kapanıştan eskiyse aynı yolla günceller (yalnız kapanmış barlar yazılır).

- Off-tick: yalnız learning worker çağırır (karar yoluna ağ çağrısı GİRMEZ).
- `BAR_HISTORY_ENABLED` kapalıysa no-op (bayt-aynı).
- Süreç-içi memo: derinlik bir kez TAM görülünce tekrar ölçülmez (tazelik her
  turda bakılır); fetch en erken `RETRY_SEC` sonra yeniden denenir (yfinance'e vurma).
- PAPER_SAFE — yalnız veri arşivi yazar.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, date, datetime, timedelta

from packages.ops.store import write_text_atomic

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

# Canlı bar yolundan (get_bars → append_new) GEÇMEYEN günlük seriler: arşivlerini
# yalnız bu bekçi büyütür, bu yüzden derinlik yetmez, tazelik de burada sağlanır.
ARCHIVE_ONLY_DAILY = frozenset({"US10Y", "US05Y", "MOVE", "US02Y"})
# CPI aylık ve yayın gecikmeli (1 Eylül gözlemi Ekim ortasında gelir).
MONTHLY_MAX_AGE_DAYS = 80

# Süreç-içi durum: {"ok": derinliği tam görülen semboller, "last_attempt": ts}
_MEMO: dict = {"ok": set(), "last_attempt": 0.0}


def _is_stale(symbol: str, today: date) -> bool:
    """Bekçinin tazelediği serinin son barı beklenen son kapanıştan eski mi?

    Hafta içi her gün kapanış beklenir; tatil ayrımı yok, tatilde boş deneme
    `RETRY_SEC` ile sınırlı kalır. Boş arşiv sığlık işidir (burada False)."""
    from packages.data.providers.ohlcv import history

    if symbol != "CPI" and symbol not in ARCHIVE_ONLY_DAILY:
        return False
    last = history._tail_ts(history._path(symbol, "1d"))
    if last is None:
        return False
    if symbol == "CPI":
        return (today - last.date()).days > MONTHLY_MAX_AGE_DAYS
    expected = today - timedelta(days=1)
    while expected.weekday() >= 5:
        expected -= timedelta(days=1)
    return last.date() < expected


def _fetch(ticker: str, symbol: str, rng: str) -> list:
    from packages.data.providers.ohlcv import yfinance

    chart = yfinance.fetch_chart(ticker, rng)
    return [bar.model_copy(update={"symbol": symbol}) for bar in chart[1]] if chart else []


def _write_merged(symbol: str, fetched: list) -> dict:
    """Çekilen KAPANMIŞ barları arşivle birleştirip atomik yazar (arşiv barı kazanır;
    bugünün oluşan barı arşive girerse sonraki gün tam barla düzelmezdi)."""
    from packages.data.providers.ohlcv import history

    today = datetime.now(UTC).date()
    closed = [bar for bar in fetched if bar.ts.date() < today]
    existing = history.load(symbol, "1d")
    merged = history.merged(closed, existing)
    if not merged:
        return {"symbol": symbol, "status": "FETCH_EMPTY"}
    path = history._path(symbol, "1d")
    write_text_atomic(path, "".join(json.dumps(b.model_dump(mode="json")) + "\n" for b in merged))
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
    """Sığ ya da bayat makro arşivleri 5y çekimle tamamla; derin ve tazeyse no-op.

    yfinance sembolleri `min_bars` eşiğiyle; FRED sembolleri (US02Y/CPI) kendi
    eşiğiyle ve YALNIZ FRED_API_KEY varsa (yoksa dürüstçe atlanır, özet not düşer).
    Dönen özet: {status, checked, filled, failed[, unchanged, fred]}."""
    from packages.data.providers.ohlcv import history

    if not history.enabled():
        return {"status": "DISABLED"}
    fred_key = bool(os.environ.get("FRED_API_KEY"))
    # sembol → (min eşik, kaynak) — tek tarama, kaynak başına doğru eşik.
    targets: dict[str, tuple[int, str]] = {s: (min_bars, "yf") for s in BACKFILL_TICKERS}
    if fred_key:
        targets.update({s: (m, "fred") for s, m in FRED_BACKFILL_MIN_BARS.items()})
    today = datetime.now(UTC).date()
    pending: list[tuple[str, int]] = []
    for sym, (need, _src) in targets.items():
        stale = _is_stale(sym, today)
        if sym in _MEMO["ok"] and not stale:
            continue
        bars = len(history.load(sym, "1d"))
        if bars >= need and not stale:
            _MEMO["ok"].add(sym)
        else:
            pending.append((sym, bars))
    if not pending:
        out = {"status": "DEEP", "checked": len(targets)}
        if not fred_key:
            out["fred"] = "NO_KEY"  # US02Y/CPI bu ortamda doldurulamaz (dürüst not)
        return out
    now = time.monotonic()
    if _MEMO["last_attempt"] and now - _MEMO["last_attempt"] < RETRY_SEC:
        return {"status": "RETRY_WAIT", "shallow": [s for s, _ in pending]}
    _MEMO["last_attempt"] = now
    filled, failed, unchanged = [], [], []
    for sym, before in pending:
        need, src = targets[sym]
        try:
            r = (
                backfill_symbol_fred(sym)
                if src == "fred"
                else backfill_symbol(sym, BACKFILL_TICKERS[sym])
            )
            if r["status"] != "OK" or r["after"] < need:
                failed.append(f"{sym}:{r['status']}")
                continue
            _MEMO["ok"].add(sym)
            if r["after"] > before:
                filled.append(f"{sym}:{before}->{r['after']}")
            else:
                unchanged.append(sym)  # tatil/kaynak gecikmesi: yeni kapanış henüz yok
        except Exception as exc:  # tek sembol hatası bekçiyi durdurmasın
            failed.append(f"{sym}:{type(exc).__name__}")
    _log.log(
        logging.WARNING if failed else logging.INFO,
        "macro_backfill: filled=%s failed=%s unchanged=%s", filled, failed, unchanged,
    )
    status = "FILLED" if filled else "FAILED" if failed else "NO_NEW_BARS"
    out = {"status": status, "filled": filled, "failed": failed}
    if unchanged:
        out["unchanged"] = unchanged
    if not fred_key:
        out["fred"] = "NO_KEY"
    return out
