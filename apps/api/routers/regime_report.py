"""GET /api/v1/regime-report/current"""
from __future__ import annotations

from fastapi import APIRouter

from packages.consensus.engine import build as build_consensus
from packages.data.ingestion.pipeline import get_cached_snapshot
from packages.data.provenance import data_provenance
from packages.data.registry import assets as asset_registry
from packages.regime.classifier import classify
from packages.risk import event_risk

router = APIRouter(tags=["regime"])


@router.get("/regime-report/current")
def get_regime_report_current() -> dict:
    snap = get_cached_snapshot()
    regime = classify(snap)
    # Tüm snapshot evreni (trade + macro) — daha önce DEFAULT_SYMBOLS[:6] ile
    # sınırlıydı (Senaryo paneli BRENT/custom asset'leri hiç göremiyordu).
    # asset_registry her çağrıda taze okunur, sonradan eklenen custom asset
    # otomatik dahil olur.
    universe = asset_registry.snapshot_symbols()
    kind_by_symbol = {a.symbol: a.kind for a in asset_registry.all_assets()}
    cons_list = [build_consensus(s, snap, regime) for s in universe]

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
            {
                "id": h.id,
                "source": h.source,
                "region": h.region,
                "ts": h.ts.isoformat(),
                "title": h.title,
                "title_tr": h.title_tr,
                "sentiment": h.sentiment,
                # M1 — v2 sınıflandırıcı gözlemi: owner v1/v2 ayrışmasını buradan
                # izleyip `news.sentiment_v2` aktivasyon kararını verir.
                "sentiment_v2": h.sentiment_v2,
                "asset_impact": h.asset_impact,
                # UI haber kartlarından kaynak makaleye geçiş için.
                "url": h.url,
                # P0 — haber yalnızca bağlam/analytics; deterministik kararı
                # belirleyen sembol etkisi varsa actionable, yoksa context-only.
                "actionable": bool(h.asset_impact),
                "freshness": h.freshness,
            }
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
