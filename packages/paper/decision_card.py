"""Karar kartı (karar-destek adım 2, 2026-11-16) — owner'ın kendi araçları adayın yanında.

Owner elle işlem açarken şunlara bakıyor: üst zaman diliminde yapı yönü, fiyatın Fib geri
çekilme bölgesindeki yeri ve uzantı hedefleri, önceki dip/tepe, 0-2 çizgisi. Kart bunları
onay bekleyen adayın yanında tek yerde verir; ayrıca pozisyon süresine düşen önemli takvim
olaylarını ve sistemin aynı sembol × TF × yön adaylarının son 60 gündeki karşı-olgu sonucunu
(açılsa da açılmasa da, kapı karşı-olgu defterinden) yazar.

GÖZLEMCİ: karar, kapı ve boyut değişmez; çıktı yalnız biletin
``technical_detail.owner_card`` bölümüne yazılır (sözleşmede serbest alan). Bir bölüm
hesaplanamazsa yalnız o bölüm ``status: unavailable`` + nedenle döner; bilet kurulumu kesilmez.
"""
from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.data.types import Catalyst, OHLCVBar
from packages.elliott import zero_two
from packages.elliott.pivots import alternating_pivots

BarsFn = Callable[[str, str], list[OHLCVBar]]

# Adayın TF'sine göre "üst zaman dilimi" (yapı yönü buradan okunur).
HIGHER_TF = {"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w", "1w": "1w"}
_BAR_HOURS = {"15m": 0.25, "1h": 1.0, "4h": 4.0, "1d": 24.0, "1w": 168.0}
GOLDEN_ZONE = (0.382, 0.618)
HISTORY_DAYS = 60
EVENT_IMPORTANCE = frozenset({"high", "critical"})
_MAX_EVENTS = 5
_PIVOT_LR = 3


def _unavailable(reason: str) -> dict[str, Any]:
    return {"status": "unavailable", "reason": reason}


def _num(x: float, digits: int = 6) -> float:
    return round(float(x), digits)


def structure(bars: list[OHLCVBar], timeframe: str, side: str) -> dict[str, Any]:
    """Son iki tepe ve son iki dip: ikisi de yükseliyorsa yukarı, ikisi de düşüyorsa aşağı."""
    if not bars:
        return _unavailable("no_bars")
    piv = alternating_pivots(bars, left=_PIVOT_LR, right=_PIVOT_LR)
    highs = [p.price for p in piv if p.kind == "high"][-2:]
    lows = [p.price for p in piv if p.kind == "low"][-2:]
    if len(highs) < 2 or len(lows) < 2:
        return _unavailable("insufficient_pivots")
    if highs[1] > highs[0] and lows[1] > lows[0]:
        direction = "up"
    elif highs[1] < highs[0] and lows[1] < lows[0]:
        direction = "down"
    else:
        direction = "range"
    aligned = (direction == "up" and side == "long") or (direction == "down" and side == "short")
    return {
        "status": "ok", "timeframe": timeframe, "direction": direction, "aligned": aligned,
        "highs": [_num(h) for h in highs], "lows": [_num(v) for v in lows],
    }


def swing(bars: list[OHLCVBar], entry: float, atr: float) -> dict[str, Any]:
    """Son teyitli dip ve tepe; girişe uzaklıkları ATR cinsinden (dip girişin altındaysa +)."""
    if not bars:
        return _unavailable("no_bars")
    piv = alternating_pivots(bars, left=_PIVOT_LR, right=_PIVOT_LR)
    low = next((p for p in reversed(piv) if p.kind == "low"), None)
    high = next((p for p in reversed(piv) if p.kind == "high"), None)
    if low is None or high is None:
        return _unavailable("insufficient_pivots")
    unit = atr if math.isfinite(atr) and atr > 0 else None
    return {
        "status": "ok",
        "prev_low": _num(low.price),
        "prev_low_atr": round((entry - low.price) / unit, 2) if unit else None,
        "prev_high": _num(high.price),
        "prev_high_atr": round((high.price - entry) / unit, 2) if unit else None,
    }


def fib(bars: list[OHLCVBar], frame: str, entry: float) -> dict[str, Any]:
    """Fiyatın son salınımı ne kadar geri çektiği (0 = salınım ucu, 1 = başlangıcı) + uzantılar."""
    from packages.data.providers.technical import fibonacci

    if not bars:
        return _unavailable("no_bars")
    a = fibonacci.analyze(bars, timeframe=frame, current_price=entry)  # type: ignore[arg-type]
    if a.validity == "unavailable" or a.swing_high is None or a.swing_low is None:
        return _unavailable(";".join(a.diagnostics) or "fib_unavailable")
    span = a.swing_high - a.swing_low
    if span <= 0:
        return _unavailable("invalid_swing")
    if a.trend_direction == "uptrend":
        ratio: float | None = (a.swing_high - entry) / span
    elif a.trend_direction == "downtrend":
        ratio = (entry - a.swing_low) / span
    else:
        ratio = None
    return {
        "status": "ok", "frame": frame, "trend": a.trend_direction, "zone": a.zone,
        "validity": a.validity, "swing_high": _num(a.swing_high), "swing_low": _num(a.swing_low),
        "retracement": round(ratio, 3) if ratio is not None else None,
        "in_golden_zone": ratio is not None and GOLDEN_ZONE[0] <= ratio <= GOLDEN_ZONE[1],
        "extensions": [{"ratio": lv.ratio, "price": _num(lv.price)} for lv in a.levels if lv.kind == "extension"],
    }


def zero_two_line(bars: list[OHLCVBar], side: str) -> dict[str, Any]:
    """En son 0-1-2 kurulumu: geçerliliği (owner kuralı), yönü, çizginin bugünkü değeri."""
    if not bars:
        return _unavailable("no_bars")
    events = zero_two.analyze(bars, left=_PIVOT_LR, right=_PIVOT_LR)
    if not events:
        return {"status": "ok", "found": False}
    ev = max(events, key=lambda e: e.setup.p2.bar_index)
    s = ev.setup
    line = zero_two.line_value(s, len(bars) - 1)
    close = bars[-1].close
    return {
        "status": "ok", "found": True, "direction": s.direction, "validity": ev.status,
        "aligned": (s.direction == "up") == (side == "long"),
        "line_price": _num(line),
        "price_on_trend_side": close >= line if s.direction == "up" else close <= line,
        "last_touch": ev.touches[-1].kind if ev.touches else None,
        "p2_nearest_fib": s.nearest_fib,
    }


def hold_hours(timeframe: str) -> float:
    """Pozisyonun süre stopu (config); yoksa 8 bar."""
    from packages.paper.lifecycle import _timeframe_time_stop_hours

    configured = _timeframe_time_stop_hours(timeframe)
    return float(configured) if configured > 0 else 8 * _BAR_HOURS.get(timeframe, 1.0)


def events(catalysts: Iterable[Catalyst], now: datetime, hours: float) -> dict[str, Any]:
    """Pozisyon süresine düşen yüksek/kritik takvim olayları (en yakın önce)."""
    end = now + timedelta(hours=hours)
    items = []
    for c in catalysts or ():
        ts = c.ts if c.ts.tzinfo else c.ts.replace(tzinfo=UTC)
        if c.importance in EVENT_IMPORTANCE and now <= ts <= end:
            items.append({
                "title": c.title, "ts": ts.isoformat(), "importance": c.importance,
                "hours_until": round((ts - now).total_seconds() / 3600, 1),
            })
    items.sort(key=lambda e: e["ts"])
    return {"status": "ok", "hold_hours": round(hours, 1), "items": items[:_MAX_EVENTS]}


# Gün dosyası → (sembol, TF, yön) başına [adet, net R toplamı, kazanan]. Yalnız değişen dosya
# yeniden okunur (bugünkü); eski günler (mtime, boyut) imzasıyla önbellekte kalır.
_DAY_CACHE: dict[str, tuple[tuple[float, int], dict[tuple[str, str, str], list[float]]]] = {}


def _day_stats(path: Path) -> dict[tuple[str, str, str], list[float]]:
    st = path.stat()
    sig = (st.st_mtime, st.st_size)
    hit = _DAY_CACHE.get(str(path))
    if hit is not None and hit[0] == sig:
        return hit[1]
    agg: dict[tuple[str, str, str], list[float]] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            net_r = row.get("net_r")
            if not isinstance(net_r, (int, float)) or isinstance(net_r, bool) or not math.isfinite(net_r):
                continue
            key = (str(row.get("symbol")), str(row.get("timeframe")), str(row.get("side")))
            acc = agg.setdefault(key, [0, 0.0, 0])
            acc[0] += 1
            acc[1] += float(net_r)
            acc[2] += 1 if net_r > 0 else 0
    _DAY_CACHE[str(path)] = (sig, agg)
    return agg


def history(symbol: str, timeframe: str, side: str, now: datetime, folder: Path | None = None) -> dict[str, Any]:
    """Aynı sembol × TF × yön adaylarının son 60 gün karşı-olgu sonucu (maliyet dahil net R)."""
    if folder is None:
        from packages.learning import gate_counterfactual

        folder = gate_counterfactual._dir()
    if not folder.exists():
        return _unavailable("no_ledger")
    key = (symbol, timeframe, side)
    n, total, wins = 0, 0.0, 0
    for back in range(HISTORY_DAYS):
        path = folder / f"{(now - timedelta(days=back)).date().isoformat()}.jsonl"
        if not path.exists():
            continue
        acc = _day_stats(path).get(key)
        if acc:
            n += int(acc[0])
            total += acc[1]
            wins += int(acc[2])
    return {
        "status": "ok", "days": HISTORY_DAYS, "n": n,
        "mean_net_r": round(total / n, 3) if n else None,
        "win_rate": round(wins / n, 3) if n else None,
    }


def build_owner_card(
    symbol: str,
    timeframe: str,
    side: str,
    entry: float,
    atr: float,
    *,
    catalysts: Iterable[Catalyst] = (),
    now: datetime | None = None,
    bars_fn: BarsFn | None = None,
    ledger_dir: Path | None = None,
) -> dict[str, Any]:
    """Tüm bölümler; her biri ayrı korunur (biri düşerse diğerleri ve bilet sürer)."""
    now = now or datetime.now(UTC)
    if bars_fn is None:
        from packages.data.providers import ohlcv

        bars_fn = ohlcv.get_bars
    memo: dict[str, list[OHLCVBar]] = {}

    def bars(tf: str) -> list[OHLCVBar]:
        if tf not in memo:
            memo[tf] = list(bars_fn(symbol, tf) or [])
        return memo[tf]

    htf = HIGHER_TF.get(timeframe, "1d")
    frame, frame_tf = ("1D", "1d") if timeframe in ("1d", "1w") else ("4H", "4h")
    sections: dict[str, Callable[[], dict[str, Any]]] = {
        "structure": lambda: structure(bars(htf), htf, side),
        "swing": lambda: swing(bars(timeframe), entry, atr),
        "fib": lambda: fib(bars(frame_tf), frame, entry),
        "zero_two": lambda: zero_two_line(bars(timeframe), side),
        "events": lambda: events(catalysts, now, hold_hours(timeframe)),
        "history": lambda: history(symbol, timeframe, side, now, ledger_dir),
    }
    card: dict[str, Any] = {"version": 1, "timeframe": timeframe, "side": side}
    for name, fn in sections.items():
        try:
            card[name] = fn()
        except Exception as exc:  # gözlemci: bölüm düşer ve nedeni görünür, bilet sürer
            card[name] = _unavailable(f"error:{type(exc).__name__}")
    return card


__all__ = ["build_owner_card", "events", "fib", "history", "hold_hours", "structure", "swing", "zero_two_line"]
