"""Bar-bar sinyal çıkarımı — ÜRETİM fonksiyonlarını geçmiş barlarda koşar (look-ahead yok).

Her adımda yalnızca o ana kadarki barlar (``bars[:i+1]``, üretim pencere sınırıyla) verilir.
Çıktı satırı üç şeyi taşır:

1. ESKİ karar girdileri: taban teknik motor (``build_timeframe_result`` — canlı config,
   korumalar açık) ve bileşenleri (momentum çekirdeği, kapı/chop/tükenme çarpanları,
   reversion), 4h/1d için v4 (bölge artifact'ı olmadığından S/R vekiliyle) ve v4'ün
   kanonik-0-2 varyantı.
2. ``entry_context`` JSON'u — ``entry_quality.assess`` çevrimdışı farklı config'lerle
   yeniden koşulabilsin (bağlam yeniden hesaplanmaz).
3. SONUÇ alanları (fwd getiriler, MFE/MAE): yalnızca DEĞERLENDİRME için; hiçbir özellik
   bunları kullanmaz (hindsight yalnız tanılama).

Not: ``now`` her adımda son barın zamanıdır → bayatlık kontrolü devreye girmez.
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("TEST_USE_MOCK", "true")

# Üretim pencere sınırları (packages/data/providers/ohlcv/__init__.py::_MAX_BARS);
# 1h'de hesap maliyeti için 600 (göstergeler ≤200 bar bakar).
WINDOW = {"1d": 600, "4h": 400, "1h": 600}
STRIDE = {"1d": 1, "4h": 1, "1h": 2}
WARMUP = 260
HORIZONS = (5, 10, 20)


def _fwd(bars, i: int, h: int):
    j = i + h
    return None if j >= len(bars) else bars[j].close / bars[i].close - 1.0


def _mfe_mae(bars, i: int, h: int = 20):
    """Long varsayımıyla (+) ileri en iyi/en kötü yürüyüş (%). Short için işaret çevrilir."""
    j = min(len(bars) - 1, i + h)
    if j <= i:
        return None, None
    hi = max(b.high for b in bars[i + 1:j + 1])
    lo = min(b.low for b in bars[i + 1:j + 1])
    c = bars[i].close
    return hi / c - 1.0, lo / c - 1.0


def _zone_proxy(window, closes):
    """Bölge artifact'ı çevrimdışı yok: %3 içindeki en yakın swing destek/direnç vekili."""
    from packages.data.providers.technical import indicators
    piv = indicators.swing_pivots(window, left=3, right=3)
    if piv is None:
        return 0.0
    highs, lows = piv
    px = closes[-1]
    below = [x for x in lows if x < px]
    above = [x for x in highs if x > px]
    if below and (px - max(below)) / px <= 0.03:
        return 1.0
    if above and (min(above) - px) / px <= 0.03:
        return -1.0
    return 0.0


def extract(name: str, tf: str, bars: list, start: int = WARMUP) -> list[dict]:
    from packages.data.providers.technical import indicators
    from packages.data.providers.technical import timeframe as tfm
    from packages.elliott import zero_two
    from packages.scoring import entry_context
    from packages.scoring import tf_scoring_v2 as v2
    from packages.scoring import tf_scoring_v4 as v4

    cfg = tfm.load_config()
    w = WINDOW[tf]
    stride = STRIDE[tf]
    rows: list[dict] = []
    n = len(bars)
    for i in range(start, n, stride):
        window = bars[max(0, i - w + 1): i + 1]
        b = bars[i]
        closes = [x.close for x in window]
        r: dict = {"series": name, "tf": tf, "i": i, "ts": b.ts.isoformat(), "close": b.close,
                   "open": b.open, "high": b.high, "low": b.low}
        # ---- sonuç (yalnız değerlendirme)
        for h in HORIZONS:
            r[f"f{h}"] = _fwd(bars, i, h)
        r["mfe20"], r["mae20"] = _mfe_mae(bars, i, 20)
        nxt = bars[i + 1] if i + 1 < n else None
        r["next_open"] = nxt.open if nxt else None

        # ---- ESKİ taban motor (canlı config) ve bileşenleri
        res = tfm.build_timeframe_result(name, tf, window, now=b.ts, config=cfg)
        so = res.score_overview
        r["base"] = so.direction_score
        r["gate"] = so.location_gate_multiplier
        r["chop"] = so.chop_guard_multiplier
        r["exh_mult"] = so.exhaustion_guard_multiplier
        r["reversion"] = so.reversion_score
        r["market_regime"] = so.market_regime
        rsi_v = indicators.rsi(closes)
        macd_t = indicators.macd(closes)
        atr_v = indicators.atr(window)
        macd_atr = macd_t[2] / atr_v if (macd_t is not None and atr_v and atr_v > 0) else None
        emas = [indicators.ema(closes, p) for p in (20, 50, 200)]
        stack = tfm._ema_stack(emas)
        r["rsi"], r["macd_atr"], r["stack"] = rsi_v, macd_atr, stack
        r["core"] = tfm._momentum_score(rsi_v, macd_atr, stack)
        r["atr"] = atr_v
        adx_t = indicators.adx(window)
        r["adx"] = adx_t[0] if adx_t else None

        # ---- v4 (4h/1d): bileşenler + S/R vekil bölge + kanonik 0-2
        if tf in v4.WEIGHTS:
            base_leans = v2.collect_leans(tf, window)
            zl = _zone_proxy(window, closes)
            for variant, canon in (("v4", False), ("v4c", True)):
                lv = v4.compute_leans(tf, window, [], base_leans, canonical_zero_two=canon)
                lv["bolge"] = zl
                lv["uyumsuzluk"] = v4.gated_divergence(closes, zl)
                s = v4.tf_direction(tf, lv)
                r[variant] = None if s is None else 50.0 + 50.0 * s
                for k, v in lv.items():
                    r[f"{variant}_{k}"] = v
            # 0-2 merceği geçerlilik tanılaması (eski lens son setup'ı geçerli sayıyor mu?)
            try:
                setups = zero_two.find_setups(window, left=2, right=2)
                evs = zero_two.analyze(window, left=2, right=2)
                r["zz_old_setup"] = bool(setups)
                r["zz_old_valid"] = (
                    bool(evs) and evs[-1].status == zero_two.STATUS_VALID if setups else None
                )
            except Exception:
                r["zz_old_setup"], r["zz_old_valid"] = None, None

        # ---- giriş bağlamı (JSON) — çevrimdışı assess için
        ctx = entry_context.build(window, tf)
        r["ctx"] = json.dumps(ctx, separators=(",", ":")) if ctx else None
        rows.append(r)
    return rows


def _job(args):
    name, tf, cache = args
    sys.path.insert(0, os.getcwd())
    from scripts.score_diag import data as D
    uni = D.universe(Path(cache))
    s, bars = uni[(name, tf)]
    rows = extract(name, tf, bars)
    for r in rows:
        r["asset_class"] = s.asset_class
    return name, tf, rows


def run_all(cache: str, out_dir: str, workers: int = 4, only: list[str] | None = None) -> None:
    import pandas as pd

    from scripts.score_diag import data as D
    uni = D.universe(Path(cache))
    jobs = [(n, tf, cache) for (n, tf) in uni if tf in WINDOW and (not only or f"{n}_{tf}" in only)]
    # en uzun işler önce (yük dengesi)
    jobs.sort(key=lambda j: -len(uni[(j[0], j[1])][1]) / STRIDE[j[1]])
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for name, tf, rows in ex.map(_job, jobs):
            df = pd.DataFrame(rows)
            df.to_csv(Path(out_dir) / f"{name}_{tf}.csv.gz", index=False)
            print(f"done {name}_{tf}: {len(df)} rows", flush=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="data/score_diag_cache")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    run_all(a.cache, a.out, a.workers, a.only)
