"""Owner manuel emir — paylaşılan iş mantığı (REST endpoint + chat aynı yoldan).

PATRON doğrudan pozisyon açar (AI değil, insan kararı). Sinyal motoru ve
duplicate filtreleri owner akışında aranmaz; ancak son RiskGate ve KORUNAN
güvenlikler (data integrity, gerçek fiyat şartı, price-sanity, bakiye) owner
tarafından aşılamaz.
Paper-safe — GERÇEK broker emri YOK.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime

from packages.data.ingestion.pipeline import build_snapshot
from packages.paper import audit as paper_audit
from packages.paper import state as paper_state
from packages.paper.guards import price_sanity
from packages.paper.lifecycle import _ensure_daily_anchor, open_position
from packages.paper.state import PaperState, PendingOrder
from packages.risk.engine import RiskInput
from packages.risk.engine import evaluate as evaluate_risk

_SIDE = {
    "al": "long", "buy": "long", "long": "long", "uzun": "long",
    "satın al": "long", "satin al": "long", "satınal": "long",
    "sat": "short", "sell": "short", "short": "short", "kısa": "short", "kisa": "short",
}


class ManualOrderError(Exception):
    def __init__(self, message: str, code: int = 409, reason: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        # Makine-okunur engel sebebi ("risk_gate" | "no_price" | "price_insane" |
        # "insufficient_balance"): çağıran (örn. fikir onayı) mesajı ayrıştırmadan
        # kullanıcıya doğru durumu gösterir. Mesaj metni değişmez.
        self.reason = reason


RISK_BLOCKS_NEW_OPEN = {"KILL_SWITCH", "RISK_REDUCE", "NO_POSITION_INCREASE"}


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
    open_reason: str = "owner_manual",
    guard: Callable[[PaperState, float], None] | None = None,
) -> dict:
    """Owner emri. order_type açıkça verilmezse: fiyat yoksa MARKET, varsa
    LIMIT/STOP (market'e göre çıkarılır). order_type='stop_limit' → entry_price stop
    tetiği, limit_price dolum fiyatı. Bekleyen emirler tick'te fiyatla dolar.

    `open_reason`: pozisyona/denetime yazılan köken etiketi. "owner" ile başlamalı —
    öğrenme kohortları (learning/cohorts) MANUAL'ı bu önekle ayırır; otomatik
    kalibrasyona sızmaz. `guard(ps, size_usd)`: defter kilidi İÇİNDE, RiskGate'ten
    önce çağrılır; ManualOrderError fırlatarak açılışı durdurabilir (varsayılan None →
    davranış birebir eski). Aynı kilit altında olduğundan çift tıklama/yarış güvenlidir."""
    s = normalize_side(side)
    if s is None:
        raise ManualOrderError("yön long/short (al/sat) olmalı", 400)
    if not size_usd or size_usd <= 0:
        raise ManualOrderError("tutar sıfırdan büyük olmalı", 400)
    sym = (symbol or "").strip().upper()
    # T3 — ağ çağrısı (snapshot) kilit DIŞINDA; defter mutasyonu tek kilit altında.
    snap = build_snapshot()
    prices = {q.symbol: q.price for q in snap.prices if q.price is not None}
    market = prices.get(sym)
    if market is None or market <= 0:
        raise ManualOrderError(
            f"{sym} için güncel fiyat yok — emir verilemez (uydurma fiyat yok)", reason="no_price"
        )
    market_sane = price_sanity.price_sane_with_ohlcv_reason(sym, float(market), timeframe=timeframe)
    if market_sane is not None:
        raise ManualOrderError(
            f"{sym} guncel fiyati tutarsiz: {market_sane}", reason="price_insane"
        )

    with paper_state.transaction("manual_order:place") as ps:
        # Owner komutu bile son ve tek RiskGate'den geçer. Bu kontrol hem
        # market açılışını hem bekleyen emri kapsar; API/chat arasında bypass
        # farkı oluşmasını engeller. Gün çapasını burada da yenilemek, tick
        # henüz çalışmamışsa eski günlük zararın yeni güne taşınmasını önler.
        _ensure_daily_anchor(ps)
        if guard is not None:
            guard(ps, float(size_usd))
        risk = evaluate_risk(
            RiskInput(
                dqs_score=snap.quality.score,
                equity_usd=ps.equity_usd,
                peak_equity_usd=ps.peak_equity_usd,
                daily_pnl_usd=ps.daily_pnl_usd,
                open_position_count=len(ps.open_positions),
                daily_anchor_date=ps.daily_anchor_date,
                mtm_equity_usd=ps.mtm_equity_usd,
            )
        )
        if risk.action in RISK_BLOCKS_NEW_OPEN:
            raise ManualOrderError(
                f"RiskGate engelledi: {risk.action} — {risk.reason}", 409, reason="risk_gate"
            )
        if size_usd > ps.equity_usd:
            raise ManualOrderError(
                f"yetersiz bakiye: {size_usd:.0f} dolar > {ps.equity_usd:.0f} dolar",
                reason="insufficient_balance",
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
                open_reason=open_reason, snapshot_id=snap.snapshot_id,
                open_dqs=snap.quality.score, data_verified=True,
            )
            paper_audit.record(
                "MANUAL_OPEN", position_id=pos.id, symbol=sym, side=s,
                price_used=pos.entry_price, size=pos.size_usd, reason=open_reason,
            )
            return {
                "kind": "market", "position_id": pos.id, "symbol": sym, "side": s,
                "entry_price": pos.entry_price, "size_usd": pos.size_usd,
                "sl": pos.sl, "tp": pos.tp,
                "opened_at": pos.opened_at, "timeframe": pos.timeframe,
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
    # T3 — explicit txn: bulunamadıysa yazmadan bırak (abort commit sonrası no-op).
    txn = paper_state.begin("manual_order:cancel")
    try:
        ps = txn.state
        before = len(ps.pending_orders)
        ps.pending_orders = [o for o in ps.pending_orders if o.id != order_id]
        if len(ps.pending_orders) == before:
            return False
        paper_audit.record("PENDING_CANCELLED", position_id=order_id, reason="owner")
        txn.commit()
        return True
    finally:
        txn.abort()


def cancel_all() -> int:
    txn = paper_state.begin("manual_order:cancel_all")
    try:
        ps = txn.state
        n = len(ps.pending_orders)
        if n:
            ps.pending_orders = []
            paper_audit.record("PENDING_CANCELLED", reason="owner_all", size=n)
            txn.commit()
        return n
    finally:
        txn.abort()
