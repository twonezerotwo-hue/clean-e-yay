"""GET /api/v1/data/snapshot — anlık piyasa snapshot'ı + provider durumu.

Frontend buradan DataQualityPanel / ProviderStatusPanel / SnapshotPanel /
MarketDataPanel için veri okur. `PRICE_USE_MOCK` false ise live sağlayıcı
çağrılır; hata durumunda otomatik mock fallback olur ve `dqs.fallback_used`
true olur.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot

router = APIRouter(tags=["data"])


@router.get("/data/snapshot")
def get_snapshot() -> dict:
    snap = get_cached_snapshot()
    q = snap.quality
    return {
        "meta": {
            "snapshot_id": snap.snapshot_id,
            "generated_at": snap.generated_at.isoformat(),
            "symbols": DEFAULT_SYMBOLS,
        },
        "prices": [
            {
                "symbol": p.symbol,
                "price": p.price,
                "ts": p.ts.isoformat(),
                "source": p.source,
                "fallback": p.fallback,
            }
            for p in snap.prices
        ],
        "dqs": {
            "score": q.score,
            "freshness": q.freshness,
            "completeness": q.completeness,
            "drift": q.drift,
            "reconciliation": q.reconciliation,
            "decision_usage": q.decision_usage,
            "fallback_used": q.fallback_used,
            "notes": list(q.notes),
        },
        "provider_status": snap.provider_status,
        "warnings": list(snap.warnings),
    }
