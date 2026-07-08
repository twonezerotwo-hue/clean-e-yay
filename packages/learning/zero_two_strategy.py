"""0-2 tam-strateji gölge karnesi (SALT-ANALİZ / read-only; canlıya dokunmaz).

Owner'ın 0-2 yönteminin BÜTÜN kural setini (kalibrasyon 2026-07-08, BTC 4h/1h/1d
üzerinden) mekanik ölçer — `zero_two_scorecard.py` fitil/kırılım işlemlerini
ölçüyordu; bu modül owner'ın nihai LONG akışını uçtan uca simüle eder:

- **Giriş:** geçerli up-setup'ta (0=dip,1=tepe,2=dip; dalga-1 çizgiye değmemiş)
  nokta 2 sonrası fiyat dalga-1'in 0.618 geri çekilmesinin ÜSTÜNE kapanır → long.
  Önce P2 dibi kırılırsa setup iptal. Stop = P2 dibinin %0.1 altı.
- **Yukarı hedef (klasik, P2'den):** 1.236 uzantı → %50 + stop break-even;
  1.618 uzantı → kalanı kapat.
- **Aşağı trailing:** bir bar 0-2 çizgisinin altında kapanırsa kalanı çık.
- **House-money re-giriş:** ilk işlem 1.618 TP'ye ulaştıysa, dalga-4 dalga-1
  tepesi (P1) üstünde kaldığı sürece cebe giren kâr (R1) kadar riskle re-giriş
  (dalga 5). Stop P1 altı kapanış; birleşik = R1·(1+rr2) → stop olursa net 0
  (ana paraya dokunmaz).

Kalibrasyon bulgusu: house-money re-giriş tutarlı değer katıyor; taban setup
tespiti pivot `right`'a duyarlı (işaret değiştirebiliyor) → o yüzden right=2 ve
3 BİRLİKTE raporlanır, ve bu KARARA bağlanmaz — kanıt büyüyene dek yalnız gölge.

Config-flag YOK (ölü-flag yasağı; `exit_backtest` deseni): salt-analiz,
karara/paper'a/ağırlığa dokunmaz. Interval-kapılı (haftalık). Fitilsiz barlar
(CoinGecko 1h/1d) ATLANMAZ — giriş/hedef/trailing kapanış-bazlı çalışır; yalnız
fitil-değme nüansı ölçülemez (rapor `flat_note` ile işaretler).
"""
from __future__ import annotations

import json
import os
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from packages.elliott import zero_two

_ENGINE = "zero_two_strategy_v1"
_INTERVAL_ENV = "ZERO_TWO_STRATEGY_INTERVAL_SEC"
_DEFAULT_INTERVAL_SEC = 7 * 24 * 3600

_TIMEFRAMES = ("1h", "4h", "1d")
_RIGHTS = (2, 3)              # pivot duyarlılığı — ikisi de raporlanır (kırılganlık)
_CRYPTO = frozenset({"BTCUSD", "ETHUSD", "DODO", "SKYAI"})

STOP_PAD = 0.001
ENTRY_FIB = 0.618
EXT_HALF, EXT_FULL, EXT_W5 = 1.236, 1.618, 2.618
ENTRY_WINDOW = 20
REENTRY_WINDOW = 30
HORIZON = 120
_MIN_BARS = 80


def _path() -> Path:
    return Path(os.environ.get("ZERO_TWO_STRATEGY_PATH", "data/runtime/zero_two_strategy.json"))


def _interval_sec() -> int:
    try:
        return int(os.environ.get(_INTERVAL_ENV, str(_DEFAULT_INTERVAL_SEC)))
    except ValueError:
        return _DEFAULT_INTERVAL_SEC


def _up_setups(bars: list, right: int) -> list:
    return [s for s in zero_two.find_setups(bars, left=right, right=right) if s.direction == "up"]


def first_trade(bars: list, setup, right: int) -> dict | None:
    """0.618-reclaim giriş + fib hedef + 0-2 trailing. R1 + (varsa) 1.618 TP barı."""
    if not zero_two.wave1_clean(bars, setup):
        return None
    w1 = setup.p1.price - setup.p0.price
    if w1 <= 0:
        return None
    fib_lv = setup.p1.price - ENTRY_FIB * w1
    p2_low = setup.p2.price
    start = setup.p2.bar_index + right + 1

    entry_idx = None
    for j in range(start, min(len(bars), start + ENTRY_WINDOW)):
        if bars[j].low < p2_low * (1 - STOP_PAD):
            return None  # setup dibi kırıldı
        if bars[j].close > fib_lv:
            entry_idx = j
            break
    if entry_idx is None:
        return None

    entry = bars[entry_idx].close
    stop = p2_low * (1 - STOP_PAD)
    unit = entry - stop
    if unit <= 0 or unit / entry < 0.0005:
        return None
    t1 = p2_low + EXT_HALF * w1
    t2 = p2_low + EXT_FULL * w1

    realized, remaining, half_done, be = 0.0, 1.0, False, False
    tp_bar = None
    for j in range(entry_idx + 1, min(len(bars), entry_idx + 1 + HORIZON)):
        b = bars[j]
        stop_now = entry if be else stop
        if b.low <= stop_now:
            realized += remaining * ((stop_now - entry) / unit)
            remaining = 0.0
            break
        if b.high >= t2:
            realized += remaining * ((t2 - entry) / unit)
            remaining = 0.0
            tp_bar = j
            break
        if not half_done and b.high >= t1:
            realized += 0.5 * ((t1 - entry) / unit)
            remaining -= 0.5
            half_done = True
            be = True
        lv = zero_two.line_value(setup, j)
        if lv > 0 and b.close < lv:
            realized += remaining * ((b.close - entry) / unit)
            remaining = 0.0
            break
    if remaining > 0:
        last = bars[min(len(bars) - 1, entry_idx + HORIZON)].close
        realized += remaining * ((last - entry) / unit)
    return {"r1": realized, "tp_bar": tp_bar}


def reentry_rr(bars: list, setup, tp_bar: int) -> float | None:
    """House-money re-giriş getiri katsayısı (rr2). Altın kural bozulursa None.

    Re-giriş, dalga-1 tepesi (P1) üstünde tutunma sonrası (pullback→devam kapanışı);
    stop P1 altı; hedef dalga-5 2.618 uzantısı; 0-2 çizgi-altı kapanış da çıkış."""
    p1 = setup.p1.price
    w1 = setup.p1.price - setup.p0.price
    p2_low = setup.p2.price
    re_idx = None
    for j in range(tp_bar + 1, min(len(bars), tp_bar + REENTRY_WINDOW)):
        if bars[j].close < p1:
            return None  # altın kural bozuk → re-giriş yok
        if (
            j > tp_bar + 2
            and bars[j].close > bars[j - 1].high
            and bars[j - 1].close < bars[j - 2].close
        ):
            re_idx = j
            break
    if re_idx is None:
        return None
    e2 = bars[re_idx].close
    s2 = p1 * (1 - STOP_PAD)
    u2 = e2 - s2
    if u2 <= 0:
        return None
    tgt = p2_low + EXT_W5 * w1
    exit2 = None
    for k in range(re_idx + 1, min(len(bars), re_idx + 1 + HORIZON)):
        b = bars[k]
        if b.close < s2:
            exit2 = b.close
            break
        if b.high >= tgt:
            exit2 = tgt
            break
        lv = zero_two.line_value(setup, k)
        if lv > 0 and b.close < lv:
            exit2 = b.close
            break
    if exit2 is None:
        exit2 = bars[min(len(bars) - 1, re_idx + HORIZON)].close
    return (exit2 - e2) / u2


def measure(bars: list, right: int) -> dict:
    """Bir sembol×TF×right için işlem kayıtları + huni."""
    setups = _up_setups(bars, right)
    funnel = {"up_setup": len(setups), "entered": 0, "tp1618": 0}
    trades: list[dict] = []
    for s in setups:
        ft = first_trade(bars, s, right)
        if ft is None:
            continue
        funnel["entered"] += 1
        rec = {"r1": ft["r1"], "rr2": None}
        if ft["tp_bar"] is not None and ft["r1"] > 0:
            funnel["tp1618"] += 1
            rec["rr2"] = reentry_rr(bars, s, ft["tp_bar"])
        trades.append(rec)
    return {"funnel": funnel, "trades": trades}


def _summ(trades: list[dict]) -> dict:
    """İlk-işlem ve house-money birleşik R istatistikleri."""
    n = len(trades)
    if not n:
        return {"n": 0}
    r1 = [t["r1"] for t in trades]
    combined, re_rr = [], []
    re_n = re_win = 0
    for t in trades:
        c = t["r1"]
        if t["rr2"] is not None:
            re_n += 1
            re_rr.append(t["rr2"])
            if t["rr2"] > 0:
                re_win += 1
            c = t["r1"] + (t["r1"] if t["r1"] > 0 else 0.0) * t["rr2"]
        combined.append(c)
    return {
        "n": n,
        "ilk_avg_r": round(statistics.mean(r1), 3),
        "ilk_total_r": round(sum(r1), 2),
        "ilk_win_pct": round(sum(1 for r in r1 if r > 0) / n * 100, 1),
        "hm_avg_r": round(statistics.mean(combined), 3),
        "hm_total_r": round(sum(combined), 2),
        "reentry_n": re_n,
        "reentry_win": re_win,
        "reentry_avg_rr": round(statistics.mean(re_rr), 3) if re_rr else None,
    }


def _symbols() -> list[str]:
    from packages.data.providers.ohlcv import history
    from packages.data.providers.rotation.engine import ROTATION_SYMBOLS

    syms = set(ROTATION_SYMBOLS.values()) | _CRYPTO
    try:
        arch_dir = Path(os.environ.get(history._DIR_ENV, history._DEFAULT_DIR))
        for f in arch_dir.glob("*.jsonl"):
            stem, _, tf = f.stem.rpartition("_")
            if stem and tf in _TIMEFRAMES:
                syms.add(stem)
    except OSError:
        pass
    return sorted(syms)


def compute(now: datetime | None = None) -> dict:
    """Arşiv+canlı barlarda tam-strateji karnesi. Asla raise etmez."""
    now = now or datetime.now(UTC)
    from packages.data.providers.ohlcv import get_bars, history

    # (tf, right, grup) -> trade listesi
    acc: dict[tuple, list[dict]] = defaultdict(list)
    funnels: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
    scanned: list[str] = []
    flat_syms: list[str] = []

    for symbol in _symbols():
        grp = "kripto" if symbol in _CRYPTO else "diger"
        for tf in _TIMEFRAMES:
            try:
                bars = history.merged(history.load(symbol, tf), get_bars(symbol, tf) or [])
            except Exception:
                continue
            if len(bars) < _MIN_BARS:
                continue
            scanned.append(f"{symbol}_{tf}")
            if sum(1 for b in bars if b.high <= b.low) / len(bars) > 0.5:
                flat_syms.append(f"{symbol}_{tf}")
            for right in _RIGHTS:
                res = measure(bars, right)
                acc[(tf, right, grp)].extend(res["trades"])
                for k, v in res["funnel"].items():
                    funnels[(tf, right, grp)][k] += v

    def _key(tf, right, grp):
        return f"{tf}|right{right}|{grp}"

    results = {}
    for (tf, right, grp), trades in acc.items():
        results[_key(tf, right, grp)] = {
            "funnel": dict(funnels[(tf, right, grp)]),
            **_summ(trades),
        }

    return {
        "generated_at": now.isoformat(),
        "engine": _ENGINE,
        "scanned": scanned,
        "flat_note": flat_syms,  # fitilsiz: kapanış-bazlı ölçüldü, fitil nüansı yok
        "results": results,
        "note": (
            "SALT-ANALIZ: owner 0-2 tam-akisi (0.618 giris + fib hedef + 0-2 "
            "trailing + house-money re-giris). Canli karara dokunmaz. right=2/3 "
            "birlikte (taban pivot-duyarli); house-money re-giris tutarli deger "
            "katiyor. Kanit arsivle buyur."
        ),
    }


def _write(report: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def run_if_due() -> dict:
    """learning_worker adımı (interval-kapılı, haftalık). Flag YOK (salt-analiz)."""
    try:
        p = _path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            gen = datetime.fromisoformat(str(data.get("generated_at")))
            age = (datetime.now(UTC) - gen).total_seconds()
            if data.get("engine") == _ENGINE and 0 <= age < _interval_sec():
                return {"status": "SKIP_FRESH", "age_sec": int(age)}
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass
    rep = compute()
    _write(rep)
    return {"status": "OK", "scanned": len(rep["scanned"]), "cells": len(rep["results"])}


__all__ = [
    "compute",
    "first_trade",
    "measure",
    "reentry_rr",
    "run_if_due",
]
