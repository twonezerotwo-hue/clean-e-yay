"""5 yillik OHLCV backfill — bar arsivini (data/runtime/bar_history) derinlestirir.

Mantik `packages.learning.macro_backfill`e TASINDI (learning worker ayni isi
otomatik yapar — AWS arsivi kendini doldurur, kural 6 senkron). Bu script elle
kosum icin ince sarmalayici olarak kalir.

Kullanim:  python scripts/backfill_history.py [--range 5y] [SEMBOL ...]
PAPER_SAFE — yalniz veri arsivi yazar; canli karara/paper'a dokunmaz.
"""
from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--range", default="5y", help="Yahoo range (5y/10y/max)")
    ap.add_argument("symbols", nargs="*", help="alt kume (bos=hepsi)")
    args = ap.parse_args()

    os.environ.setdefault("BAR_HISTORY_ENABLED", "1")  # arsiv yazimi icin sart
    from packages.learning.macro_backfill import BACKFILL_TICKERS, backfill_symbol

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
        print(f"{s:8} {r['before']:6} {r['fetched']:8} {r['after']:6}  ~{r['years']}y")
    return 0


if __name__ == "__main__":
    sys.exit(main())
