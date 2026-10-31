"""Açıklama paketi (hedef mimari: kararı en çok etkileyen kanıt).

Her karar için modül katkıları (yönü iten / karşı duran), ilk engel, son kapı
rotası ve tek satırlık "neden şimdi" özeti. Karar kaydına ve okuma yüzeylerine
gider; YZ anlatımı aynı paketten beslenir.

Saf fonksiyon: karar zincirine geri yazmaz, kararı değiştirmez.
"""
from __future__ import annotations

from typing import Any

MODULE_TR = {
    "touche": "teknik",
    "fundamental": "temel",
    "sentinel": "risk iştahı",
    "quantum": "göreceli güç",
    "news": "haber",
}
_DIRECTION_TR = {"bullish": "yükseliş", "bearish": "düşüş", "neutral": "nötr"}
_ACTION_TR = {"open_long": "long aç", "open_short": "short aç", "hold": "bekle", "blocked": "bloklu"}


def _fmt(lean: float) -> str:
    return f"{'+' if lean >= 0 else '−'}{abs(lean):.1f}"


def build(decision: Any, gate: Any = None) -> dict[str, Any]:
    """Karar → açıklama paketi. Katkı = (modül skoru − 50) × ağırlık (yön ekseni)."""
    cons = getattr(decision, "consensus", None)
    direction = getattr(cons, "direction", "neutral") or "neutral"
    sign = {"bullish": 1.0, "bearish": -1.0}.get(direction, 0.0)
    mods = sorted(
        (
            {"module": m.name, "layer": getattr(m, "layer", None),
             "lean": round((float(m.score) - 50.0) * float(m.weight), 2)}
            for m in (getattr(cons, "modules", None) or ())
        ),
        key=lambda r: -abs(r["lean"]),
    )
    drivers = [m for m in mods if sign and m["lean"] * sign > 0][:3]
    against = [m for m in mods if sign and m["lean"] * sign < 0][:2]
    blockers = list(getattr(decision, "blocked_by", None) or ())
    route = getattr(gate, "route", None)
    action = getattr(decision, "action", None)

    parts = [f"{_DIRECTION_TR.get(direction, direction)} {float(getattr(cons, 'score', 50.0) or 50.0):.1f}"]
    if drivers:
        parts.append("iten: " + ", ".join(f"{MODULE_TR.get(m['module'], m['module'])} {_fmt(m['lean'])}"
                                          for m in drivers))
    if against:
        parts.append("karşı: " + ", ".join(f"{MODULE_TR.get(m['module'], m['module'])} {_fmt(m['lean'])}"
                                           for m in against))
    tail = _ACTION_TR.get(action, action or "?")
    if blockers:
        tail += f" ({blockers[0]})"
    if route and route != "open":
        tail += f" · rota {route}"
    parts.append(tail)
    return {
        "direction": direction,
        "drivers": drivers,
        "against": against,
        "blocker": blockers[0] if blockers else None,
        "route": route,
        "why_now": " — ".join(parts),
    }


__all__ = ["MODULE_TR", "build"]
