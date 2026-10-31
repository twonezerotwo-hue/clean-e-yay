"""Performans kanıtı: maliyet sonrası net getiri, en büyük düşüş ve al-tut kıyası.

Salt raporlama (hedef mimari 7. aşama): karar, eşik ya da RiskGate'i değiştirmez.
Fiyatlar yalnız diskten okunur (bar arşivi + OHLCV önbelleği); ağ çağrısı yok.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any

from packages.data.registry.loader import load_thresholds


def cost_r() -> float:
    """İşlem başı varsayılan gidiş-dönüş maliyeti (R) — EV kapısıyla aynı varsayım."""
    try:
        return float((load_thresholds().get("ev_gate") or {}).get("cost_r", 0.1))
    except (OSError, KeyError, ValueError, TypeError):
        return 0.1


def _ts(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def max_drawdown_r(outcomes: list) -> float | None:
    """Kapanış sırasına göre birikimli R eğrisinin en derin tepe-dip düşüşü (≤ 0)."""
    rows = sorted((o for o in outcomes if o.r_multiple is not None), key=lambda o: str(o.closed_at or ""))
    if not rows:
        return None
    eq = peak = dd = 0.0
    for o in rows:
        eq += float(o.r_multiple)
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 3)


def _close_at(symbol: str, when: datetime) -> float | None:
    from packages.data.providers.ohlcv import cache, history

    try:
        cached = cache.load(symbol, "1d")
        bars = history.merged(history.load(symbol, "1d"), list(cached.bars) if cached else [])
    except Exception:
        return None
    last = None
    for b in bars:
        if b.ts <= when:
            last = b.close
        else:
            break
    return last


def buy_and_hold(outcomes: list, initial_equity: float) -> dict[str, Any] | None:
    """Sistemin net getirisi (% başlangıç sermayesi) vs aynı dönemde işlem gören
    varlıkların eşit ağırlıklı al-tut getirisi. Fiyat yoksa None (uydurma yok)."""
    opened = [t for t in (_ts(o.opened_at) for o in outcomes) if t]
    closed = [t for t in (_ts(o.closed_at) for o in outcomes) if t]
    if not opened or not closed or initial_equity <= 0:
        return None
    start, end = min(opened), max(closed)
    rets = []
    for sym in sorted({o.symbol for o in outcomes}):
        p0, p1 = _close_at(sym, start), _close_at(sym, end)
        if p0 and p1:
            rets.append(p1 / p0 - 1.0)
    if not rets:
        return None
    c = cost_r()
    gross = sum(float(o.pnl) for o in outcomes)
    cost_usd = sum(
        c * abs(float(o.pnl) / float(o.r_multiple))
        for o in outcomes if o.r_multiple not in (None, 0)
    )
    return {
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "symbols_priced": len(rets),
        "system_net_return_pct": round((gross - cost_usd) / initial_equity * 100.0, 3),
        "benchmark_return_pct": round(sum(rets) / len(rets) * 100.0, 3),
    }


def significance(outcomes: list) -> dict[str, Any] | None:
    """Ortalama R sıfırdan büyük mü: t istatistiği ve tek yönlü p (normal yaklaşım)."""
    r = [float(o.r_multiple) for o in outcomes if o.r_multiple is not None]
    n = len(r)
    if n < 2:
        return None
    mean = sum(r) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in r) / (n - 1))
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    p = 0.5 * math.erfc(t / math.sqrt(2.0))
    return {"n": n, "mean_r": round(mean, 4), "t_stat": round(t, 3), "p_value": round(p, 4)}


def regime_calibration(outcomes: list) -> dict[str, dict[str, Any]]:
    """Rejim başına söylenen güven (predicted_confidence ort.) vs gerçekleşen isabet."""
    rows: dict[str, list] = defaultdict(list)
    for o in outcomes:
        if o.predicted_confidence is not None and o.pnl != 0:
            rows[str(o.regime or "UNKNOWN")].append(o)
    out = {}
    for regime, items in sorted(rows.items()):
        predicted = sum(float(o.predicted_confidence) for o in items) / len(items)
        actual = sum(1 for o in items if o.pnl > 0) / len(items)
        out[regime] = {"n": len(items), "predicted": round(predicted, 3), "actual": round(actual, 3),
                       "gap": round(actual - predicted, 3)}
    return out


__all__ = ["buy_and_hold", "cost_r", "max_drawdown_r", "regime_calibration", "significance"]
