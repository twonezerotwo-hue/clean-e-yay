"""Owner manuel emir — paylaşılan iş mantığı (REST endpoint + chat aynı yoldan).

PATRON doğrudan pozisyon açar (AI değil, insan kararı). RiskGate / sinyal motoru /
duplicate BAYPAS edilir — owner yetkisi. KORUNAN güvenlik (data integrity, owner
bunları aşamaz): gerçek fiyat şart (uydurma/mock YOK), price-sanity, bakiye.
Paper-safe — GERÇEK broker emri YOK.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from packages.data.ingestion.pipeline import build_snapshot
from packages.paper import audit as paper_audit
from packages.paper import state as paper_state
from packages.paper.guards import price_sanity
from packages.paper.lifecycle import open_position
from packages.paper.state import PendingOrder

_SIDE = {
    "al": "long", "buy": "long", "long": "long", "uzun": "long",
    "satın al": "long", "satin al": "long", "satınal": "long",
    "sat": "short", "sell": "short", "short": "short", "kısa": "short", "kisa": "short",
}


class ManualOrderError(Exception):
    def __init__(self, message: str, code: int = 409) -> None:
        super().__init__(message)
        self.code = code


def normalize_side(side: str | None) -> str | None:
    return _SIDE.get((side or "").strip().lower())


def _infer_type(side: str, trigger: float, market: float) -> str:
    """Tetik fiyatı market'e göre limit mi stop mu:
    long & tetik<market → limit (ucuza al); long & tetik>market → stop (kırılımda al).
    short & tetik>market → limit (pahalıya sat); short & tetik<market → stop."""
    if side == "long":
        return "limit" if trigger < market else "stop"
    return "limit" if trigger > market else "stop"


def _new_id(symbol: str) -> str:
    return hashlib.sha1(f"{symbol}|{datetime.now(UTC).isoformat()}".encode()).hexdigest()[:10]


def place(
    symbol: str,
    side: str,
    size_usd: float,
    entry_price: float | None = None,
    timeframe: str = "1d",
    order_type: str | None = None,
    limit_price: float | None = None,
) -> dict:
    """Owner emri. order_type açıkça verilmezse: fiyat yoksa MARKET, varsa
    LIMIT/STOP (market'e göre çıkarılır). order_type='stop_limit' → entry_price stop
    tetiği, limit_price dolum fiyatı. Bekleyen emirler tick'te fiyatla dolar."""
    s = normalize_side(side)
    if s is None:
        raise ManualOrderError("yön long/short (al/sat) olmalı", 400)
    if not size_usd or size_usd <= 0:
        raise ManualOrderError("tutar sıfırdan büyük olmalı", 400)
    sym = (symbol or "").strip().upper()
    ps = paper_state.load()
    snap = build_snapshot()
    prices = {q.symbol: q.price for q in snap.prices if q.price is not None}
    market = prices.get(sym)
    if market is None or market <= 0:
        raise ManualOrderError(f"{sym} için güncel fiyat yok — emir verilemez (uydurma fiyat yok)")
    market_sane = price_sanity.price_sane_with_ohlcv_reason(sym, float(market), timeframe=timeframe)
    if market_sane is not None:
        raise ManualOrderError(f"{sym} guncel fiyati tutarsiz: {market_sane}")
    if size_usd > ps.equity_usd:
        raise ManualOrderError(
            f"yetersiz bakiye: {size_usd:.0f} dolar > {ps.equity_usd:.0f} dolar"
        )

    is_market = order_type == "market" or (
        order_type is None
        and (not entry_price or entry_price <= 0 or abs(entry_price - market) / market < 0.001)
    )
    # MARKET: anında aç.
    if is_market:
        pos = open_position(
            ps, symbol=sym, side=s, entry_price=float(market), size_multiplier=0.0,
            manual=True, size_usd_override=float(size_usd), timeframe=timeframe,
            open_reason="owner_manual", snapshot_id=snap.snapshot_id,
            open_dqs=snap.quality.score, data_verified=True,
        )
        paper_audit.record(
            "MANUAL_OPEN", position_id=pos.id, symbol=sym, side=s,
            price_used=pos.entry_price, size=pos.size_usd, reason="owner_manual",
        )
        paper_state.save(ps)
        return {
            "kind": "market", "position_id": pos.id, "symbol": sym, "side": s,
            "entry_price": pos.entry_price, "size_usd": pos.size_usd,
            "sl": pos.sl, "tp": pos.tp,
        }

    # LIMIT / STOP / STOP_LIMIT: bekleyen emir.
    if not entry_price or entry_price <= 0:
        raise ManualOrderError("limit/stop emir için tetik fiyatı gerekli", 400)
    entry_sane = price_sanity.price_sane_with_ohlcv_reason(
        sym, float(entry_price), timeframe=timeframe
    )
    if entry_sane is not None:
        raise ManualOrderError(f"{sym} için {entry_price:.2f} fiyatı geçersiz aralıkta")
    otype = order_type if order_type in ("limit", "stop", "stop_limit") else _infer_type(
        s, float(entry_price), float(market)
    )
    lp = float(limit_price) if (otype == "stop_limit" and limit_price) else None
    order = PendingOrder(
        id=_new_id(sym), symbol=sym, side=s, size_usd=float(size_usd),
        order_type=otype, trigger_price=float(entry_price), limit_price=lp,
        created_at=datetime.now(UTC).isoformat(), timeframe=timeframe, reason="owner_manual",
    )
    ps.pending_orders.append(order)
    paper_audit.record(
        "PENDING_CREATED", position_id=order.id, symbol=sym, side=s,
        price_used=order.trigger_price, size=order.size_usd, reason=otype,
    )
    paper_state.save(ps)
    return {
        "kind": otype, "order_id": order.id, "symbol": sym, "side": s,
        "size_usd": order.size_usd, "trigger_price": order.trigger_price, "market": market,
    }


def list_pending() -> list[dict]:
    ps = paper_state.load()
    return [
        {
            "id": o.id, "symbol": o.symbol, "side": o.side, "size_usd": o.size_usd,
            "order_type": o.order_type, "trigger_price": o.trigger_price,
            "created_at": o.created_at,
        }
        for o in ps.pending_orders
    ]


def cancel(order_id: str) -> bool:
    ps = paper_state.load()
    before = len(ps.pending_orders)
    ps.pending_orders = [o for o in ps.pending_orders if o.id != order_id]
    if len(ps.pending_orders) == before:
        return False
    paper_audit.record("PENDING_CANCELLED", position_id=order_id, reason="owner")
    paper_state.save(ps)
    return True


def cancel_all() -> int:
    ps = paper_state.load()
    n = len(ps.pending_orders)
    if n:
        ps.pending_orders = []
        paper_audit.record("PENDING_CANCELLED", reason="owner_all", size=n)
        paper_state.save(ps)
    return n
