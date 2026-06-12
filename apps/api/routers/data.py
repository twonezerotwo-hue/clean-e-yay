"""GET /api/v1/data/snapshot — anlık piyasa snapshot'ı + provider durumu.

Politika: runtime'da mock fallback yoktur. Live provider başarısız olursa
ilgili `prices[i].price = null`, `verified=false`, `status="DATA_UNAVAILABLE"`,
`error=<sebep>` döner. Endpoint asla crash etmez, asla sahte fiyat üretmez.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.data.provenance import data_provenance

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
        "mode": data_provenance(snap),
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
        # v2.7 D2 — kripto türev zekâsı (funding/OI/squeeze proxy). symbol → snapshot.
        # squeeze_proxy GERÇEK liquidation değildir (is_proxy=true).
        "derivatives": {
            sym: {
                "symbol": d.symbol,
                "funding_rate": d.funding_rate,
                "funding_annualized": d.funding_annualized,
                "open_interest_usd": d.open_interest_usd,
                "oi_change_pct": d.oi_change_pct,
                "price_momentum_pct": d.price_momentum_pct,
                "volatility_pct": d.volatility_pct,
                "squeeze_proxy": d.squeeze_proxy,
                "squeeze_level": d.squeeze_level,
                "funding_bias": d.funding_bias,
                "is_proxy": d.is_proxy,
                "status": d.status,
                "source": d.source,
                "verified": d.verified,
                "freshness": d.freshness,
                "dqs": d.dqs,
                "ts": d.ts.isoformat(),
                "evidence": list(d.evidence),
                "error": d.error,
            }
            for sym, d in (snap.derivatives or {}).items()
        },
        # T1 — gerçek OHLCV'den multi-TF teknikler (symbol → tf → özet).
        "technicals_by_tf": {
            sym: {
                tf: {
                    "timeframe": t.timeframe,
                    "rsi": t.rsi,
                    "macd": t.macd,
                    "atr": t.atr,
                    "ema_stack": t.ema_stack,
                    "score": t.score,
                    "status": t.status,
                    "source": t.source,
                    "bars_used": t.bars_used,
                    "ts": t.ts.isoformat(),
                }
                for tf, t in by_tf.items()
            }
            for sym, by_tf in (snap.technicals_by_tf or {}).items()
        },
    }
