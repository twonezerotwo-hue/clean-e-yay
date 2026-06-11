"""GET /api/v1/data/snapshot — anlık piyasa snapshot'ı + provider durumu.

Politika: runtime'da mock fallback yoktur. Live provider başarısız olursa
ilgili `prices[i].price = null`, `verified=false`, `status="DATA_UNAVAILABLE"`,
`error=<sebep>` döner. Endpoint asla crash etmez, asla sahte fiyat üretmez.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.data.providers import price as price_provider

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
        "mode": {
            "mock_mode": price_provider.is_mock_mode(),
            "mock_warning": price_provider.is_runtime_mock_explicit(),
            "test_mock": price_provider.is_test_mock_allowed(),
        },
        "prices": [
            {
                "symbol": p.symbol,
                "price": p.price,
                "ts": p.ts.isoformat(),
                "source": p.source,
                "verified": p.verified,
                "status": p.status,
                "error": p.error,
                "fallback": p.fallback,
            }
            for p in snap.prices
        ],
        "dqs": {
            "score": q.score,
            "status": q.status,
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
