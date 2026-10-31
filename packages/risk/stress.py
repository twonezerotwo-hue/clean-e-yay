"""Stres testi ve kuyruk riski (hedef mimari: ln_stress) — salt rapor.

Açık paper pozisyonlarına arşivdeki GERÇEK günlük getirileri uygular:
- Tarihsel portföy günlük P&L dağılımı (pozisyonlar o günlerde tutulsaydı) →
  VaR 95/99 ve CVaR 95/99 (beklenen kuyruk kaybı), % başlangıç sermayesi.
- En kötü tarihsel gün ve en kötü ardışık 5 gün.
- Pozisyon başına en ters tek gün.
Sonuç günlük zarar sınırıyla (risk_gates.max_daily_loss_pct) kıyaslanır ve
aşılıyorsa uyarı verir; limit DEĞİŞTİRMEZ, RiskGate'e dokunmaz.

Fiyat yalnız diskten (bar arşivi + OHLCV önbelleği); ağ yok. Arşivi olmayan
pozisyon rapora girmez ve `unpriced` listesinde görünür (uydurma yok).
"""
from __future__ import annotations

from datetime import date
from itertools import pairwise
from typing import Any

from packages.data.registry.loader import load_thresholds

_MIN_DAYS = 60


def _daily_returns(symbol: str) -> dict[date, float]:
    from packages.data.providers.ohlcv import cache, history

    try:
        cached = cache.load(symbol, "1d")
        bars = history.merged(history.load(symbol, "1d"), list(cached.bars) if cached else [])
    except Exception:
        return {}
    out: dict[date, float] = {}
    for prev, cur in pairwise(bars):
        if prev.close:
            out[cur.ts.date()] = cur.close / prev.close - 1.0
    return out


def _tail(losses: list[float], q: float) -> tuple[float, float]:
    """(VaR, CVaR) — kayıp olarak pozitif değer; q = 0.95 / 0.99."""
    ordered = sorted(losses, reverse=True)
    k = max(1, round(len(ordered) * (1.0 - q)))
    return ordered[k - 1], sum(ordered[:k]) / k


def report(state: Any) -> dict[str, Any]:
    th = load_thresholds()
    equity = float(getattr(state, "equity_usd", 0.0) or 0.0)
    limit_pct = float((th.get("risk_gates") or {}).get("max_daily_loss_pct", 0.02)) * 100.0
    positions = list(getattr(state, "open_positions", None) or [])
    exposures: list[tuple[str, float]] = []   # (sembol, işaretli USD maruziyet)
    unpriced: list[str] = []
    series: dict[str, dict[date, float]] = {}
    for p in positions:
        sym = p.symbol
        if sym not in series:
            series[sym] = _daily_returns(sym)
        if len(series[sym]) < _MIN_DAYS:
            unpriced.append(sym)
            continue
        sign = 1.0 if p.side == "long" else -1.0
        exposures.append((sym, sign * float(getattr(p, "size_usd", 0.0) or 0.0)))
    base = {
        "positions": len(positions), "priced": len(exposures), "unpriced": sorted(set(unpriced)),
        "equity_usd": round(equity, 2), "daily_loss_limit_pct": round(limit_pct, 3),
    }
    if not exposures or equity <= 0:
        return {**base, "status": "NO_EXPOSURE" if not positions else "NO_DATA"}

    days = sorted(set.intersection(*(set(series[s]) for s, _ in exposures)))
    pnl = [sum(usd * series[s][d] for s, usd in exposures) for d in days]
    losses = [-x / equity * 100.0 for x in pnl]          # % sermaye, kayıp pozitif
    var95, cvar95 = _tail(losses, 0.95)
    var99, cvar99 = _tail(losses, 0.99)
    worst_i = max(range(len(losses)), key=losses.__getitem__)
    five = [sum(losses[i:i + 5]) for i in range(len(losses) - 4)] or [0.0]
    per_position = []
    for s, usd in exposures:
        worst = min(usd * r for r in series[s].values())
        per_position.append({"symbol": s, "exposure_usd": round(usd, 2),
                             "worst_day_pct": round(-worst / equity * 100.0, 3)})
    warn = cvar99 > limit_pct
    return {
        **base,
        "status": "OK",
        "days": len(days),
        "window": {"from": days[0].isoformat(), "to": days[-1].isoformat()},
        "var_95_pct": round(var95, 3), "cvar_95_pct": round(cvar95, 3),
        "var_99_pct": round(var99, 3), "cvar_99_pct": round(cvar99, 3),
        "worst_day_pct": round(losses[worst_i], 3), "worst_day": days[worst_i].isoformat(),
        "worst_5d_pct": round(max(five), 3),
        "per_position": per_position,
        "exceeds_daily_limit": warn,
        "note": (
            "Kuyruk kaybı (CVaR 99) günlük zarar sınırını aşıyor: açık kitap tarihsel kötü "
            "günde RiskGate frenine takılır." if warn else
            "Kuyruk kaybı günlük zarar sınırının içinde."
        ),
    }


__all__ = ["report"]
