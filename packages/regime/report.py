"""Rejim raporu görünümü (/api/v1/regime-report/current).

Varlık durumu (CONFIRMED / BLOCKING / PENDING), katmanlar, başlıklar, katalizörler ve
olay riski özeti burada hesaplanır; API ucu yalnız çağırır (kural: API katmanında iş
mantığı yok). 25 Kasım 2026'da routers/regime_report.py'den taşındı, yanıt aynı.
"""
from __future__ import annotations

from typing import Any

from packages.data.provenance import data_provenance
from packages.data.providers.news import classify as news_classify
from packages.data.registry import assets as asset_registry
from packages.risk import event_risk


def headline_view(headline) -> dict:
    """One canonical read-only headline projection for regime and news wall."""
    return {
        "id": headline.id,
        "source": headline.source,
        "region": headline.region,
        # Additive multi-actor view: the legacy primary region remains intact.
        "countries": list(news_classify.detect_regions(headline.title)),
        "ts": headline.ts.isoformat(),
        "title": headline.title,
        "title_tr": headline.title_tr,
        "article_summary": getattr(headline, "article_summary", None),
        "sentiment": headline.sentiment,
        "asset_impact": headline.asset_impact,
        "url": headline.url,
        "actionable": bool(headline.asset_impact),
        "freshness": headline.freshness,
    }


def current_view(dv: Any) -> dict:
    """Okuma modeli görünümünden (read_model.current()) rejim raporu."""
    snap, regime = dv.snap, dv.regime
    # Tüm snapshot evreni (trade + macro) — daha önce DEFAULT_SYMBOLS[:6] ile
    # sınırlıydı (Senaryo paneli BRENT/custom asset'leri hiç göremiyordu).
    # asset_registry her çağrıda taze okunur, sonradan eklenen custom asset
    # otomatik dahil olur.
    universe = asset_registry.snapshot_symbols()
    kind_by_symbol = {a.symbol: a.kind for a in asset_registry.all_assets()}
    cons_list = [dv.consensus(s) for s in universe]

    # P0 — olay riski (yalnızca kısıtlayıcı). Hangi catalyst yeni pozisyonu
    # kısıyor, dashboard'da görünür olsun.
    ev = event_risk.assess(snap.catalysts)
    ev_levels = {t.id: t.level for t in ev.triggers}

    assets = []
    for c in cons_list:
        status = (
            "CONFIRMED"
            if c.confluence_aligned and c.direction != "neutral"
            else "BLOCKING"
            if c.direction == "neutral"
            else "PENDING"
        )
        assets.append(
            {
                "symbol": c.symbol,
                "score": c.score,
                "direction": c.direction,
                "status": status,
                "confluence_aligned": c.confluence_aligned,
                "dominant_module": c.dominant_module,
                "win_rate_signal": "INSUFFICIENT_DATA",
                # Senaryo paneli risk-on/risk-off kovasını asset sınıfına göre
                # ayırabilsin diye (cash/safe bullish ≠ risk-on).
                "kind": kind_by_symbol.get(c.symbol),
            }
        )

    return {
        "meta": {
            "snapshot_id": snap.snapshot_id,
            "generated_at": snap.generated_at.isoformat(),
            "dqs_score": snap.quality.score,
            "fallback_used": snap.quality.fallback_used,
        },
        "mode": data_provenance(snap),
        "regime_label": regime.label,
        # F2-3 — veri yetersizliğinden düşen katmanlar (flag kapalıyken hep boş).
        # Owner "Likidite neden yok?" sorusunun cevabını burada görür.
        "dropped_layers": list(regime.dropped),
        "layers": [
            {
                "name": layer.name,
                "score": layer.score,
                "direction": layer.direction,
                "evidence": layer.evidence,
            }
            for layer in regime.layers
        ],
        "assets": assets,
        "headlines": [
            headline_view(h)
            for h in snap.headlines
        ],
        "catalysts": [
            {
                "id": c.id,
                "ts": c.ts.isoformat(),
                "title": c.title,
                "importance": c.importance,
                "region": c.region,
                "hours_until": c.hours_until,
                "days_until": c.days_until,
                # P0 — bu olay event riski tetikliyor mu (NONE/WATCH/
                # NO_POSITION_INCREASE)? Yalnızca kısıtlayıcı.
                "event_level": ev_levels.get(c.id, "NONE"),
            }
            for c in snap.catalysts
        ],
        # P0 — olay riski özeti (yalnızca kısıtlayıcı; RiskGate'i bypass etmez).
        "event_risk": {
            "level": ev.level,
            "action": ev.action,
            "reason": ev.reason,
            "evidence": list(ev.evidence),
            "restrictive": ev.restrictive,
        },
    }


__all__ = ["current_view", "headline_view"]
