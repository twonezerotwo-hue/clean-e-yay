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
        # v2.7 D4 — realized volatility / rejim (symbol → tf → snapshot).
        # Mevcut OHLCV cache'inden; karar zincirinde yalnızca kısıtlayıcı.
        "volatility": {
            sym: {
                tf: {
                    "symbol": v.symbol,
                    "timeframe": v.timeframe,
                    "realized_vol": v.realized_vol,
                    "rv_short": v.rv_short,
                    "rv_medium": v.rv_medium,
                    "rv_long": v.rv_long,
                    "vol_zscore": v.vol_zscore,
                    "regime": v.regime,
                    "vol_state": v.vol_state,
                    "status": v.status,
                    "source": v.source,
                    "verified": v.verified,
                    "freshness": v.freshness,
                    "dqs": v.dqs,
                    "bars_used": v.bars_used,
                    "ts": v.ts.isoformat(),
                    "evidence": list(v.evidence),
                    "error": v.error,
                }
                for tf, v in by_tf.items()
            }
            for sym, by_tf in (snap.volatility or {}).items()
        },
        # v2.7 D3 — options IV / skew / term structure zekâsı (yalnızca BTC/ETH).
        # skew_25d GERÇEK 25Δ greeks değildir (is_proxy=true); karar zincirinde
        # yalnızca kısıtlayıcı (verified + status OK).
        "options": {
            sym: {
                "symbol": o.symbol,
                "underlying_price": o.underlying_price,
                "atm_iv": o.atm_iv,
                "realized_vol": o.realized_vol,
                "iv_rv_spread": o.iv_rv_spread,
                "skew_25d": o.skew_25d,
                "put_call_oi_ratio": o.put_call_oi_ratio,
                "term_front_iv": o.term_front_iv,
                "term_next_iv": o.term_next_iv,
                "term_long_iv": o.term_long_iv,
                "term_slope": o.term_slope,
                "front_expiry": o.front_expiry,
                "next_expiry": o.next_expiry,
                "long_expiry": o.long_expiry,
                "contracts_used": o.contracts_used,
                "regime": o.regime,
                "is_proxy": o.is_proxy,
                "status": o.status,
                "source": o.source,
                "verified": o.verified,
                "freshness": o.freshness,
                "dqs": o.dqs,
                "ts": o.ts.isoformat(),
                "evidence": list(o.evidence),
                "error": o.error,
            }
            for sym, o in (snap.options or {}).items()
        },
        # v2.7 D5 — haber catalyst half-life zekâsı (deterministik; LLM yok).
        # Yalnızca verified + yarı-ömrü dolmamış impact karar zincirini kısıtlar;
        # rumor (verified=false) ve CONTEXT_ONLY yalnızca bağlamdır.
        "catalyst_impacts": [
            {
                "catalyst_id": c.catalyst_id,
                "headline_id": c.headline_id,
                "event_type": c.event_type,
                "surprise_level": c.surprise_level,
                "affected_assets": list(c.affected_assets),
                "affected_timeframes": list(c.affected_timeframes),
                "timeframe_bias": c.timeframe_bias,
                "expected_half_life_minutes": c.expected_half_life_minutes,
                "valid_until": c.valid_until.isoformat() if c.valid_until else None,
                "decay_curve": c.decay_curve,
                "confidence": c.confidence,
                "actionability": c.actionability,
                "verified": c.verified,
                "source": c.source,
                "region": c.region,
                "freshness": c.freshness,
                "ts": c.ts.isoformat(),
                "evidence": list(c.evidence),
            }
            for c in (snap.catalyst_impacts or [])
        ],
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
