"""GET /api/v1/regime-report/current"""
from __future__ import annotations

from fastapi import APIRouter

from packages.consensus.engine import build as build_consensus
from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.regime.classifier import classify

router = APIRouter(tags=["regime"])


@router.get("/regime-report/current")
def get_regime_report_current() -> dict:
    snap = get_cached_snapshot()
    regime = classify(snap)
    cons_list = [build_consensus(s, snap, regime) for s in DEFAULT_SYMBOLS[:6]]

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
            }
        )

    return {
        "meta": {
            "snapshot_id": snap.snapshot_id,
            "generated_at": snap.generated_at.isoformat(),
            "dqs_score": snap.quality.score,
            "fallback_used": snap.quality.fallback_used,
        },
        "regime_label": regime.label,
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
                "asset_impact": h.asset_impact,
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
            }
            for c in snap.catalysts
        ],
    }
