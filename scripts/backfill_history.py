"""5 yillik OHLCV backfill — bar arsivini (data/runtime/bar_history) derinlestirir.

Canli fetch araligina (yfinance 2y) DOKUNMAZ; tek-seferlik 5y ceker ve arsiv
dosyasini birlestirip yeniden yazar (mevcut taze barlar korunur, eski bosluk
5y cekimle doldurulur). Backtest history.merged(load, live) ile 5yil gorur.

Kaynak: yfinance (makro/rotasyon; BTC dahil BTC-USD ticker'i ile — coingecko
free ~1yil siniri backfill'e yetmez). CPI / 2yil getirisi ayri kaynak (FRED),
bu arac kapsaminda degil.

Kullanim:  python scripts/backfill_history.py [--range 5y] [SEMBOL ...]
PAPER_SAFE — yalniz veri arsivi yazar; canli karara/paper'a dokunmaz.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Backfill icin Yahoo ticker'lari (rotasyon 9 sembolu; BTC = BTC-USD).
BACKFILL_TICKERS: dict[str, str] = {
    "BTCUSD": "BTC-USD",
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "BRENT": "BZ=F",
    "DXY": "DX-Y.NYB",
    "SP500": "^GSPC",
    "TLT": "TLT",
    "HYG": "HYG",
    "LQD": "LQD",
    # Getiri egrisi bacaklari (Likidite yarisi olcumu icin; ^TNX=10Y, ^FVX=5Y).
    # Yahoo yield ticker'lari yuzde-birim doner (~4.3). 2Y icin temiz Yahoo
    # ticker'i yok → FRED (DGS2) ayri kaynak, bu arac disi.
    "US10Y": "^TNX",
    "US05Y": "^FVX",
}


def _fetch(ticker: str, symbol: str, rng: str):
    from packages.data.providers.ohlcv import yfinance
    orig = yfinance._TF_PLAN["1d"]
    yfinance._TF_PLAN["1d"] = (orig[0], rng)  # gecici; canli plan degismez
    try:
        return yfinance.fetch_by_ticker(ticker, symbol, "1d") or []
    finally:
        yfinance._TF_PLAN["1d"] = orig


def backfill_symbol(symbol: str, ticker: str, rng: str) -> dict:
    from packages.data.providers.ohlcv import history
    fetched = _fetch(ticker, symbol, rng)
    if not fetched:
        return {"symbol": symbol, "status": "FETCH_EMPTY"}
    existing = history.load(symbol, "1d")
    # merged(fetched, existing): cakisan ts'te MEVCUT (canli-kalite) kazanir,
    # eski bosluk fetched'ten dolar.
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
        "fetched": len(fetched), "after": len(merged),
        "from": merged[0].ts.date().isoformat(), "to": merged[-1].ts.date().isoformat(),
        "years": round(yrs, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--range", default="5y", help="Yahoo range (5y/10y/max)")
    ap.add_argument("symbols", nargs="*", help="alt kume (bos=hepsi)")
    args = ap.parse_args()

    os.environ.setdefault("BAR_HISTORY_ENABLED", "1")  # arsiv yazimi icin sart
    syms = args.symbols or list(BACKFILL_TICKERS)
    print(f"{'SEMBOL':8} {'ONCE':>6} {'CEKILEN':>8} {'SONRA':>6}  ARALIK")
    for s in syms:
        t = BACKFILL_TICKERS.get(s)
        if t is None:
            print(f"{s:8} ticker YOK (BACKFILL_TICKERS'a ekle)")
            continue
        r = backfill_symbol(s, t, args.range)
        if r["status"] != "OK":
            print(f"{s:8} {r['status']}")
            continue
        print(f"{s:8} {r['before']:6} {r['fetched']:8} {r['after']:6}  "
              f"{r['from']} -> {r['to']} (~{r['years']}y)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
