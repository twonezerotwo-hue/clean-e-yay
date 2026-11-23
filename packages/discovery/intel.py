"""Haber istihbaratı — YZ yorumlarının (persona raporları, sohbet, Brain) ortak kanıt özeti.

Owner kararı (2026-10-05, üçüncü tur): haber keşfi ve fikirler ayrı bir panelde değil, YZ
"bilgi ve karar verirken" değerlendirme olarak tartsın. Bu modül sıkıştırılmış durum
bağlamına (`agent/llm/context.py`) giren tek bölümü üretir:

- kayıtlı varlıkların haber öngörüsü (YZ haber zinciri dahil),
- haber akışından keşif zincirleri (olay → sonuç → varlık),
- inceleme tavsiyeleri (bildirimi giden keşif adayları),
- canlı aday işlem × haber öngörüsü teyit/çelişki.

KANITTIR, karar değildir: haber öngörüsü karar matrisine bağlı değildir. Değerler nicemlenir (güç 10'luk kova) → bağlam özeti
(önbellek anahtarı) her küçük salınımda değişmez.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

_ARROW = {"up": "↑", "down": "↓"}
_ENTRY_SIDE = {"open_long": "long", "open_short": "short"}
MIN_FORECAST_STRENGTH = 20  # bu güçten zayıf haber öngörüsü teyit/çelişki sayılmaz


def forecast_checks(cells: Iterable[Mapping[str, Any]], forecasts: Mapping[str, Mapping[str, Any]],
                    min_strength: int = MIN_FORECAST_STRENGTH) -> list[dict]:
    """Canlı aday işlemler × haber öngörüsü: teyit / çelişki (çelişkiler ve güçlüler önce).
    Brifing ve sohbet bağlamı için kanıttır; karar değişmez. (Eski news_decision_shadow
    defteri 22 Kasım 2026'da silindi; bu saf kontrol oradan taşındı.)"""
    out = []
    for c in cells:
        side = _ENTRY_SIDE.get(str(c.get("candidate_action") or ""))
        f = forecasts.get(str(c.get("symbol") or "")) or {}
        if side is None or f.get("direction") not in ("up", "down") or int(f.get("strength") or 0) < min_strength:
            continue
        ev = (f.get("evidence") or [{}])[0]
        agree = (side == "long") == (f["direction"] == "up")
        out.append({
            "symbol": c["symbol"], "timeframe": c.get("timeframe"), "side": side,
            "final_action": c.get("action"), "live_score": c.get("score"),
            "forecast": f["direction"], "strength": int(f["strength"]),
            "relation": "confirm" if agree else "conflict", "evidence": ev.get("title"),
        })
    out.sort(key=lambda r: (r["relation"] != "conflict", -r["strength"], r["symbol"], str(r["timeframe"])))
    return out


def _bucket(strength: Any) -> int:
    return int(int(strength or 0) // 10 * 10)


def _forecasts(forecasts: Mapping[str, Mapping[str, Any]], registry: set[str], limit: int = 6) -> list[dict]:
    rows = [f for s, f in forecasts.items() if s in registry and f.get("direction") in ("up", "down")
            and int(f.get("strength") or 0) >= 20]
    rows.sort(key=lambda f: (-int(f.get("strength") or 0), f["symbol"]))
    out = []
    for f in rows[:limit]:
        ev = (f.get("evidence") or [{}])[0]
        out.append({"symbol": f["symbol"], "direction": f["direction"], "strength": _bucket(f.get("strength")),
                    "headlines": f.get("n_headlines"), "top_evidence": (ev.get("title") or "")[:110],
                    "via_ai_chain": ev.get("origin") == "llm"})
    return out


def _discovery(events: Iterable[Mapping[str, Any]], limit: int = 5) -> list[dict]:
    out = []
    for ev in list(events)[:limit]:
        assets = []
        for a in ev.get("assets") or []:
            if a.get("status") not in ("valid", "registry"):
                continue
            tag = " (takipte)" if a["status"] == "registry" else ""
            assets.append(f"{a.get('symbol')}{_ARROW.get(a.get('direction') or '', '')}{tag}")
        out.append({"headline": (ev.get("title") or "")[:110], "consequence": ev.get("consequence"),
                    "assets": assets})
    return out


def compact_for_context(cells: Iterable[Mapping[str, Any]]) -> dict:
    """YZ bağlamına giren haber istihbaratı (cells: canlı karar matrisi hücreleri)."""
    from packages.data.registry import assets as asset_registry
    from packages.discovery import ideas, news_discovery, news_forecast

    forecasts = news_forecast.load_forecasts()
    registry = set(asset_registry.trade_symbols())
    checks = [
        {k: c[k] for k in ("symbol", "timeframe", "side", "final_action", "forecast", "relation")}
        | {"strength": _bucket(c["strength"]), "evidence": (c.get("evidence") or "")[:110]}
        for c in forecast_checks(cells, forecasts)[:6]
    ]
    return {
        "note": ("Haber istihbaratı KANITTIR, karar değildir. Haber öngörüsü karar matrisine "
                 "bağlı değildir; fikirler ve inceleme tavsiyeleri işlem önerisi değildir."),
        "registry_forecasts": _forecasts(forecasts, registry),
        "decision_check": checks,
        "discovery_chains": _discovery(news_discovery.viewmodel(limit_events=5).get("events") or []),
        "review_recommendations": [
            {k: r[k] for k in ("symbol", "name", "chain", "mechanism", "technical", "ai_verdict")}
            for r in ideas.review_recommendations()[:3]
        ],
        "top_ideas": ideas.compact_for_chat()["top"],
    }


def empty() -> dict:
    return {"note": "haber istihbaratı okunamadı", "registry_forecasts": [], "decision_check": [],
            "shadow_scorecard": {}, "discovery_chains": [], "review_recommendations": [], "top_ideas": []}


__all__ = ["compact_for_context", "empty"]
