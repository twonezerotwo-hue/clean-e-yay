"""GET /api/v1/paper-trading/state + owner mutasyon endpoint'leri.

T1 (2026-07 dış denetim): POST /paper-trading/tick içindeki kopya karar motoru
KALDIRILDI — tek tick yolu apps/tick_worker (conflict gate + reentry guard dahil
birleşik kapılar orada). Ticket/recheck/bildirim üretimi de worker'a taşındı;
bu router yalnız okur (data/runtime/tickets.json) ve owner mutasyonlarını taşır.
"""
from __future__ import annotations

import math
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from packages.data.ingestion.pipeline import build_snapshot
from packages.notifications import list_recent, mark_ack, mark_all_ack, unread_count
from packages.paper import audit as paper_audit
from packages.paper import maintenance, manual_order, manual_queue, position_ops, ticket
from packages.paper import state as paper_state
from packages.paper.guards import price_sanity, state_anomaly
from packages.paper.lifecycle import close_position, max_drawdown_pct
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput

router = APIRouter(tags=["paper-trading"])


def _time_stop_status(p: paper_state.Position, now: datetime) -> tuple[str, int | None]:
    """UX1 — time-stop durumu backend'de; negatif geri sayım ÜRETİLMEZ.

    NONE → time-stop yok; ACTIVE → kalan saniye (>0); EXPIRED → süre geçti,
    kalan 0 (exit pending — fiyatla TIME_STOP_EXIT'te kapanır).
    """
    vu = getattr(p, "valid_until", None)
    if not vu:
        return "NONE", None
    try:
        deadline = datetime.fromisoformat(vu)
    except (ValueError, TypeError):
        return "NONE", None
    remaining = (deadline - now).total_seconds()
    if remaining <= 0:
        return "EXPIRED", 0
    return "ACTIVE", int(remaining)


def _duplicate_warning(ps: paper_state.PaperState) -> list[dict]:
    """P1 — savunmacı duplicate tespiti: aynı (symbol, timeframe) için birden
    fazla açık pozisyon (politika gereği normalde boş). Görünür uyarı için."""
    seen: dict[tuple[str, str], int] = {}
    for p in ps.open_positions:
        seen[(p.symbol, p.timeframe)] = seen.get((p.symbol, p.timeframe), 0) + 1
    return [
        {"symbol": sym, "timeframe": tf, "open_count": n}
        for (sym, tf), n in sorted(seen.items())
        if n > 1
    ]


def _serialize_state(ps: paper_state.PaperState) -> dict:
    now = datetime.now(UTC)
    open_pos = []
    unreal_total = 0.0
    for p in ps.open_positions:
        d = asdict(p)
        d["unrealized_pnl_usd"] = round(p.unrealized_pnl_usd, 2)
        ts_status, ts_remaining = _time_stop_status(p, now)
        d["time_stop_status"] = ts_status
        d["time_stop_seconds_remaining"] = ts_remaining
        unreal_total += d["unrealized_pnl_usd"]
        open_pos.append(d)
    # P1 — yeni girişler kapalı mı: aktif halt (KILL_SWITCH/RISK_REDUCE) varsa
    # yeni pozisyon açılmaz (read-only; risk hesaplamaz, persist halt'i okur).
    new_entries_disabled = bool(halt_store.active_halts())
    anomaly = state_anomaly.detect_state(ps)
    total_exposure_usd = round(sum(p.size_usd for p in ps.open_positions), 2)
    return {
        "equity_usd": round(ps.equity_usd, 2),
        "realized_pnl_usd": round(ps.realized_pnl_usd, 2),
        "unrealized_pnl_usd": round(unreal_total, 2),
        "max_drawdown_pct": max_drawdown_pct(ps),
        "sharpe_30d": 0.0,
        "total_exposure_usd": total_exposure_usd,
        "state_anomaly": {"detected": anomaly.detected, "reasons": anomaly.reasons},
        "open_positions": open_pos,
        "recent_trades": [asdict(t) for t in ps.recent_trades[-25:]],
        # P1 — additive lifecycle/audit yüzeyi (frontend hesap yapmaz).
        "new_entries_disabled": new_entries_disabled,
        "duplicate_warning": _duplicate_warning(ps),
        "audit_summary": paper_audit.summary(),
        "recent_audit_events": paper_audit.read_recent(20),
        "manual_ready_count": len(ps.manual_ready),
        # Recheck (UX-A14): her tick'te decide_matrix yan ürünü. Boşsa henüz tick
        # atılmamış. Sadece öneri — otomatik kapatma YOK; çıkış SL/TP veya manuel.
        "position_rechecks": list(ps.last_rechecks),
        "last_recheck_at": ps.last_recheck_at,
    }


@router.get("/paper-trading/state")
def get_paper_state() -> dict:
    return _serialize_state(paper_state.load())


@router.get("/paper-trading/tickets")
def get_tickets() -> dict:
    """Aktif Trade Ticket'lar — broker'a manuel girmeden önce tek bakış kart.

    Son WORKER tick'inin actionable kararlarından türetilmiş (T1: üretici tick
    worker, bu endpoint data/runtime/tickets.json'dan okur); karar zincirine
    dokunmaz. insufficient_rr/invalid ticket'lar UI'da görünmez (filtreli döner).
    """
    data = ticket.load_last()
    visible = [t for t in data["tickets"] if t.get("status") == "active"]
    return {
        "tickets": visible,
        "total": len(visible),
        "last_built_at": data["built_at"],
    }


@router.get("/notifications")
def get_notifications(limit: int = 50, unread_only: bool = False) -> dict:
    """Bildirim listesi (en yeni önce). unread_only=true → sadece okunmamış."""
    items = list_recent(limit=limit, unread_only=unread_only)
    return {
        "notifications": [n.to_dict() for n in items],
        "unread_count": unread_count(),
        "total": len(items),
    }


@router.post("/notifications/{notif_id}/ack")
def ack_notification(notif_id: str) -> dict:
    """Bildirimi okundu işaretle."""
    ok = mark_ack(notif_id)
    return {"status": "ok" if ok else "not_found", "id": notif_id}


@router.post("/notifications/ack-all")
def ack_all_notifications() -> dict:
    """Tüm okunmamışları okundu işaretle."""
    n = mark_all_ack()
    return {"status": "ok", "marked": n}


@router.post("/paper-trading/positions/{position_id}/close")
def close_position_manual(position_id: str) -> dict:
    """Owner — tek açık pozisyonu manuel kapat (MANUAL exit). Paper-safe; broker yok.

    Güncel snapshot fiyatıyla kapatır (uydurma fiyat YOK — DATA_POLICY). Fiyat yok
    veya price-sanity dışıysa kapatma YAPILMAZ → 409; pozisyon olduğu gibi kalır
    (sonraki tick'te SL/TP/time-stop veya tekrar manuel denenebilir)."""
    ps = paper_state.load()
    pos = next((p for p in ps.open_positions if p.id == position_id), None)
    if pos is None:
        raise HTTPException(status_code=404, detail="position_not_found")
    snap = build_snapshot()
    prices = {q.symbol: q.price for q in snap.prices if q.price is not None}
    price = prices.get(pos.symbol)
    if price is None or price <= 0:
        raise HTTPException(status_code=409, detail="no_price_cannot_close")
    if price_sanity.price_sane_with_ohlcv_reason(pos.symbol, price, timeframe=pos.timeframe) is not None:
        raise HTTPException(status_code=409, detail="price_insane_cannot_close")
    trade = close_position(ps, pos, exit_price=price, reason="MANUAL")
    paper_state.save(ps)
    return {
        "status": "closed",
        "position_id": position_id,
        "symbol": trade.symbol,
        "side": trade.side,
        "exit_price": trade.exit_price,
        "pnl_usd": trade.pnl_usd,
    }


class RiskPlanRequest(BaseModel):
    sl: object | None = None
    tp: object | None = None


def _risk_plan_error(status_code: int, reason: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "reason": reason},
    )


def _parse_risk_price(value: object | None, field_name: str) -> tuple[float | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, f"{field_name} geçerli bir sayı olmalı."
    price = float(value)
    if not math.isfinite(price):
        return None, f"{field_name} geçerli bir sayı olmalı."
    if price <= 0:
        return None, f"{field_name} sıfırdan büyük olmalı."
    return price, None


def _risk_plan_reference(pos: paper_state.Position) -> float:
    current = getattr(pos, "current_price", None)
    if isinstance(current, (int, float)) and math.isfinite(float(current)) and float(current) > 0:
        return float(current)
    return float(pos.entry_price)


def _risk_plan_side_reason(
    pos: paper_state.Position,
    *,
    sl: float | None,
    tp: float | None,
) -> str | None:
    side = str(pos.side or "").lower()
    ref = _risk_plan_reference(pos)
    if side == "long":
        if sl is not None and sl >= ref:
            return "LONG pozisyonda stop loss current/entry fiyatının altında olmalı."
        if tp is not None and tp <= ref:
            return "LONG pozisyonda take profit current/entry fiyatının üstünde olmalı."
        return None
    if side == "short":
        if sl is not None and sl <= ref:
            return "SHORT pozisyonda stop loss current/entry fiyatının üstünde olmalı."
        if tp is not None and tp >= ref:
            return "SHORT pozisyonda take profit current/entry fiyatının altında olmalı."
        return None
    return "Pozisyon yönü okunamadığı için risk planı güncellenemez."


@router.patch("/paper-trading/positions/{position_id}/risk-plan")
def update_position_risk_plan(position_id: str, req: RiskPlanRequest):
    """Owner risk plan update for paper positions only.

    PAPER_SAFE / NO_EXECUTION: sadece local paper state SL/TP alanlarını günceller;
    broker emri üretmez ve karar motoru mantığına dokunmaz.
    """
    ps = paper_state.load()
    pos = next((p for p in ps.open_positions if p.id == position_id), None)
    if pos is None:
        if any(t.id == position_id for t in ps.recent_trades):
            return _risk_plan_error(
                400,
                "Pozisyon kapalı olduğu için risk planı güncellenemez.",
            )
        return _risk_plan_error(404, "position_not_found")
    if getattr(pos, "lifecycle_status", "OPEN") != "OPEN":
        return _risk_plan_error(400, "Pozisyon açık durumda olmadığı için risk planı güncellenemez.")

    sl, sl_error = _parse_risk_price(req.sl, "SL")
    if sl_error:
        return _risk_plan_error(400, sl_error)
    tp, tp_error = _parse_risk_price(req.tp, "TP")
    if tp_error:
        return _risk_plan_error(400, tp_error)

    side_reason = _risk_plan_side_reason(pos, sl=sl, tp=tp)
    if side_reason:
        return _risk_plan_error(400, side_reason)

    old_sl = pos.sl
    old_tp = pos.tp
    pos.sl = sl
    pos.tp = tp
    paper_audit.record(
        "MANUAL_RISK_PLAN_UPDATE",
        position_id=pos.id,
        symbol=pos.symbol,
        timeframe=pos.timeframe,
        side=pos.side,
        old_sl=old_sl,
        old_tp=old_tp,
        sl=pos.sl,
        tp=pos.tp,
        reference_price=_risk_plan_reference(pos),
        paper_safe=True,
        no_execution=True,
    )
    paper_state.save(ps)
    return {
        "status": "updated",
        "position_id": pos.id,
        "symbol": pos.symbol,
        "sl": pos.sl,
        "tp": pos.tp,
        "paper_safe": True,
        "no_execution": True,
    }


class ManualOrderRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=12)
    side: str
    size_usd: float = Field(gt=0)
    entry_price: float | None = None
    timeframe: str = "1d"
    order_type: str | None = None  # market | limit | stop | stop_limit (None → otomatik)
    limit_price: float | None = None  # stop_limit dolum fiyatı


@router.post("/paper-trading/positions/open")
def open_position_manual(req: ManualOrderRequest) -> dict:
    """Owner manuel emir — PATRON doğrudan pozisyon açar (AI değil, insan kararı).

    RiskGate (NO_POSITION_INCREASE), sinyal motoru ve duplicate kontrolü BAYPAS
    edilir — owner yetkisi. KORUNAN güvenlik (data integrity, owner bunları aşamaz):
    gerçek fiyat şart (uydurma/mock YOK), price-sanity (geçersiz fiyat reddedilir),
    bakiye sınırı. Paper-safe — GERÇEK broker emri YOK; sadece kâğıt pozisyon."""
    try:
        res = manual_order.place(
            symbol=req.symbol, side=req.side, size_usd=req.size_usd,
            entry_price=req.entry_price, timeframe=req.timeframe,
            order_type=req.order_type, limit_price=req.limit_price,
        )
    except manual_order.ManualOrderError as exc:
        raise HTTPException(status_code=exc.code, detail=str(exc)) from exc
    return {"status": "ok", **res}


class ModifyRequest(BaseModel):
    sl: float | None = None
    tp: float | None = None


class TrailingRequest(BaseModel):
    distance_pct: float = Field(gt=0)
    activate_pct: float | None = None


class PartialCloseRequest(BaseModel):
    fraction: float | None = None
    size_usd: float | None = None


class ScaleInRequest(BaseModel):
    size_usd: float = Field(gt=0)


def _pos_op(fn, *args, **kwargs) -> dict:
    try:
        return fn(*args, **kwargs)
    except position_ops.PositionOpError as exc:
        raise HTTPException(status_code=exc.code, detail=str(exc)) from exc


@router.post("/paper-trading/positions/{pos_ref}/modify")
def modify_position(pos_ref: str, req: ModifyRequest) -> dict:
    return {"status": "ok", **_pos_op(position_ops.modify_sltp, pos_ref, sl=req.sl, tp=req.tp)}


@router.post("/paper-trading/positions/{pos_ref}/trailing")
def trailing_position(pos_ref: str, req: TrailingRequest) -> dict:
    return {"status": "ok", **_pos_op(position_ops.set_trailing, pos_ref, req.distance_pct, req.activate_pct)}


@router.post("/paper-trading/positions/{pos_ref}/partial-close")
def partial_close_position(pos_ref: str, req: PartialCloseRequest) -> dict:
    return {"status": "ok", **_pos_op(position_ops.partial_close, pos_ref, fraction=req.fraction, size_usd=req.size_usd)}


@router.post("/paper-trading/positions/{pos_ref}/scale-in")
def scale_in_position(pos_ref: str, req: ScaleInRequest) -> dict:
    return {"status": "ok", **_pos_op(position_ops.scale_in, pos_ref, req.size_usd)}


@router.post("/paper-trading/positions/{pos_ref}/flip")
def flip_position(pos_ref: str) -> dict:
    return {"status": "ok", **_pos_op(position_ops.flip, pos_ref)}


@router.get("/paper-trading/orders")
def list_pending_orders() -> dict:
    """Owner bekleyen (limit/stop) emirleri."""
    orders = manual_order.list_pending()
    return {"orders": orders, "total": len(orders)}


@router.delete("/paper-trading/orders/{order_id}")
def cancel_pending_order(order_id: str) -> dict:
    if not manual_order.cancel(order_id):
        raise HTTPException(status_code=404, detail="order_not_found")
    return {"status": "cancelled", "order_id": order_id}


@router.delete("/paper-trading/orders")
def cancel_all_pending_orders() -> dict:
    return {"status": "cancelled", "count": manual_order.cancel_all()}


@router.get("/paper-trading/manual-ready")
def get_manual_ready() -> dict:
    """P2 — owner-approval kuyruğu (read-only; frontend hesap yapmaz)."""
    ps = paper_state.load()
    return {
        "manual_ready": [asdict(m) for m in ps.manual_ready],
        "rejected_count": len(ps.rejected_signals),
    }


@router.post("/paper-trading/manual-ready/{manual_id}/approve")
def approve_manual_ready(manual_id: str) -> dict:
    """P2 — owner onayı. Karar/guard mantığı manual_queue'da; RiskGate/DQS/KillSwitch
    açılış anında YENİDEN kontrol edilir (kuyrukta olmak otomatik güvenli değildir)."""
    ps = paper_state.load()
    snap = build_snapshot()
    prices = {q.symbol: q.price for q in snap.prices if q.price is not None}
    risk_in = RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=ps.equity_usd,
        peak_equity_usd=ps.peak_equity_usd,
        daily_pnl_usd=ps.daily_pnl_usd,
        open_position_count=len(ps.open_positions),
    )
    entry = next((m for m in ps.manual_ready if m.id == manual_id), None)
    result = manual_queue.approve(
        ps, manual_id,
        current_price=prices.get(entry.symbol) if entry else None,
        risk_input=risk_in,
    )
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="not_found")
    paper_state.save(ps)
    return result


@router.post("/paper-trading/manual-ready/{manual_id}/reject")
def reject_manual_ready(manual_id: str) -> dict:
    """P2 — owner reddi: kuyruktan çıkar + anti-spam rejection kaydı (re-queue block)."""
    ps = paper_state.load()
    if not manual_queue.reject(ps, manual_id):
        raise HTTPException(status_code=404, detail="not_found")
    paper_state.save(ps)
    return {"status": "rejected"}


@router.post("/paper-trading/manual-ready/{manual_id}/dismiss")
def dismiss_manual_ready(manual_id: str) -> dict:
    """P2 — kuyruktan çıkar (rejection KAYDETMEZ; sonraki tick'te yeniden düşebilir)."""
    ps = paper_state.load()
    if not manual_queue.dismiss(ps, manual_id):
        raise HTTPException(status_code=404, detail="not_found")
    paper_state.save(ps)
    return {"status": "dismissed"}


# Test/dev: pozisyonları sıfırla
@router.post("/paper-trading/reset")
def reset() -> dict:
    ps = paper_state._initial_state()
    # SL/TP olmadan sadece son trade ve pozisyonları temizle, equity sıfırlama:
    # gerçek "reset" davranışı için _initial_state yeterli
    paper_state.save(ps)
    paper_audit.record("STATE_REPAIRED", reason="manual_reset")
    return _serialize_state(ps)


# ── Phase 2e — owner-admin maintenance (archive / repair / reset) ─────────────
# Thin HTTP layer: all logic lives in packages/paper/maintenance.py. Paper-safe,
# NO_EXECUTION — these never open/close/resize a trade and never touch a broker.


@router.post("/paper-trading/maintenance/archive")
def post_maintenance_archive(reason: str = "manual") -> dict:
    """Owner-admin — arşivle: mevcut paper state'in zaman damgalı kopyası (mutasyon yok)."""
    return maintenance.archive_state(reason).to_dict()


@router.post("/paper-trading/maintenance/repair")
def post_maintenance_repair(dry_run: bool = True) -> dict:
    """Owner-admin — onar: dry_run=true rapor (yazım yok); false önce arşivler, sonra yazar."""
    return maintenance.repair_state(dry_run=dry_run).to_dict()


@router.post("/paper-trading/maintenance/reset")
def post_maintenance_reset(reason: str = "owner_reset", preserve_learning: bool = True) -> dict:
    """Owner-admin — sıfırla: önce arşivler, sonra temiz initial state (learning/decision log korunur)."""
    return maintenance.reset_state(reason, preserve_learning=preserve_learning).to_dict()
