"""Haber istihbaratı — YZ yorumlarının (persona raporları, sohbet, Brain) ortak kanıt özeti.

Owner kararı (2026-10-05, üçüncü tur): haber keşfi ve fikirler ayrı bir panelde değil, YZ
"bilgi ve karar verirken" değerlendirme olarak tartsın. Bu modül sıkıştırılmış durum
bağlamına (`agent/llm/context.py`) giren tek bölümü üretir:

- kayıtlı varlıkların haber öngörüsü (YZ haber zinciri dahil),
- haber akışından keşif zincirleri (olay → sonuç → varlık),
- inceleme tavsiyeleri (bildirimi giden keşif adayları),
- canlı aday işlem × haber öngörüsü teyit/çelişki ve gölge karnesi.

KANITTIR, karar değildir: haber girdisi karar matrisine yalnız gölge olarak bağlı
(`affect_decision: false`). Değerler nicemlenir (güç 10'luk kova) → bağlam özeti
(önbellek anahtarı) her küçük salınımda değişmez.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

_ARROW = {"up": "↑", "down": "↓"}


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
    from packages.discovery import ideas, news_decision_shadow, news_discovery, news_forecast

    forecasts = news_forecast.load_forecasts()
    registry = set(asset_registry.trade_symbols())
    cfg = news_decision_shadow.config()
    checks = [
        {k: c[k] for k in ("symbol", "timeframe", "side", "final_action", "forecast", "relation")}
        | {"strength": _bucket(c["strength"]), "evidence": (c.get("evidence") or "")[:110]}
        for c in news_decision_shadow.checks(cells, forecasts, cfg["min_strength"])[:6]
    ]
    return {
        "note": ("Haber istihbaratı KANITTIR, karar değildir. Haber girdisi karar matrisine yalnız gölge "
                 "olarak bağlıdır (affect_decision=false); fikirler ve inceleme tavsiyeleri işlem önerisi değildir."),
        "registry_forecasts": _forecasts(forecasts, registry),
        "decision_check": checks,
        "shadow_scorecard": news_decision_shadow.compact(),
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
