"""GET /api/v1/paper-trading/state, POST /api/v1/paper-trading/tick"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, build_snapshot, get_cached_snapshot
from packages.decision.engine import decide_matrix
from packages.paper import audit as paper_audit
from packages.paper import maintenance, manual_queue, session_gate
from packages.paper import state as paper_state
from packages.paper.guards import price_sanity
from packages.paper import manual_order, position_ops
from packages.paper.lifecycle import (
    attempt_open,
    close_position,
    flatten_all,
    max_drawdown_pct,
)
from packages.paper.lifecycle import (
    tick as price_tick,
)
from packages.paper.recheck import compute_rechecks
from packages.paper.ticket import build_tickets_from_decisions
from packages.notifications import append_many, list_recent, mark_ack, mark_all_ack, unread_count
from packages.notifications import detector as notif_detector

# Tick-içi geçici state (proses ömrü) — diff detector için
_PREV_STATE: dict = {"ticket_ids": set(), "verdicts": {}, "risk_action": None, "dqs": None}
_LAST_TICKETS: list[dict] = []
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
    return {
        "equity_usd": round(ps.equity_usd, 2),
        "realized_pnl_usd": round(ps.realized_pnl_usd, 2),
        "unrealized_pnl_usd": round(unreal_total, 2),
        "max_drawdown_pct": max_drawdown_pct(ps),
        "sharpe_30d": 0.0,
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

    Son tick'in actionable kararlarından türetilmiş; karar zincirine dokunmaz.
    insufficient_rr/invalid ticket'lar UI'da görünmez (filtreli döner).
    """
    visible = [t for t in _LAST_TICKETS if t.get("status") == "active"]
    return {
        "tickets": visible,
        "total": len(visible),
        "last_built_at": datetime.now(UTC).isoformat() if _LAST_TICKETS else None,
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


@router.post("/paper-trading/tick")
def post_paper_tick() -> dict:
    ps = paper_state.load()
    now = datetime.now(UTC)
    snap = build_snapshot()
    # None fiyatlar lifecycle'a aktarılmaz; mock fiyat dağıtılmaz.
    prices = {q.symbol: q.price for q in snap.prices if q.price is not None}
    verified_flags = {q.symbol: q.verified for q in snap.prices}

    # Önce mevcut pozisyonları fiyatla güncelle (SL/TP)
    closed = price_tick(ps, prices)

    risk_in = RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=ps.equity_usd,
        peak_equity_usd=ps.peak_equity_usd,
        daily_pnl_usd=ps.daily_pnl_usd,
        open_position_count=len(ps.open_positions),
    )

    # G5 — breach varsa halt'i persist et; KILL_SWITCH seviyesinde halt
    # aktifse mevcut pozisyonları düzleştir (KILL_SWITCH_EXIT). Sadece risk
    # azaltıcı; yeni açılışlar zaten risk engine'deki halt ile bloklanır.
    actions: list[dict] = []
    halts = halt_store.sync(risk_in)
    if any(h.level == "KILL_SWITCH" for h in halts):
        for cls in flatten_all(ps, prices):
            closed.append(cls)
        risk_in = RiskInput(
            dqs_score=snap.quality.score,
            equity_usd=ps.equity_usd,
            peak_equity_usd=ps.peak_equity_usd,
            daily_pnl_usd=ps.daily_pnl_usd,
            open_position_count=len(ps.open_positions),
        )

    # T2 — (symbol, timeframe) karar uzayı. 1w decide_matrix içinde zaten
    # paper_execution=false ile hold'a düşer; fingerprint TF segmenti taşır.
    _regime, _risk, decisions = decide_matrix(
        DEFAULT_SYMBOLS[:4], snap, risk_in, open_positions=ps.open_positions
    )

    # Recheck — açık pozisyonları fresh karara karşı değerlendir (read-only öneri).
    rechecks = compute_rechecks(ps.open_positions, decisions)
    ps.last_rechecks = [r.to_dict() for r in rechecks]
    ps.last_recheck_at = datetime.now(UTC).isoformat()

    # Trade Tickets — actionable kararlar için canlı kart payload'ı (observer).
    tickets = build_tickets_from_decisions(decisions, snap, ps)
    ticket_dicts = [t.to_dict() for t in tickets]
    global _LAST_TICKETS
    _LAST_TICKETS = ticket_dicts

    # Notification detector — state değişimlerini bildirime çevir (observer).
    notifs = []
    notifs += notif_detector.detect_new_tickets(_PREV_STATE["ticket_ids"], ticket_dicts)
    notifs += notif_detector.detect_expiring_tickets(ticket_dicts)
    notifs += notif_detector.detect_recheck_changes(_PREV_STATE["verdicts"], ps.last_rechecks)
    notifs += notif_detector.detect_risk_gate_change(
        _PREV_STATE["risk_action"], _risk.action, _risk.reason,
    )
    notifs += notif_detector.detect_dqs_drop(
        _PREV_STATE["dqs"], snap.quality.score if snap.quality else None,
    )
    if notifs:
        append_many(notifs)

    _PREV_STATE["ticket_ids"] = {t["id"] for t in ticket_dicts if t.get("status") == "active"}
    _PREV_STATE["verdicts"] = {r["position_id"]: r["verdict"] for r in ps.last_rechecks}
    _PREV_STATE["risk_action"] = _risk.action
    _PREV_STATE["dqs"] = snap.quality.score if snap.quality else None

    for cls in closed:
        actions.append(
            {
                "symbol": cls.symbol,
                "action": "close",
                "reason": cls.close_reason,
                "timeframe": cls.timeframe,
            }
        )

    for d in decisions:
        entry = {"symbol": d.symbol, "timeframe": d.timeframe}
        if d.action == "blocked":
            actions.append({**entry, "action": "blocked", "reason": d.reason})
            continue
        if d.action == "hold":
            actions.append({**entry, "action": "hold", "reason": d.reason})
            continue
        side = "long" if d.action == "open_long" else "short"
        # Market-session gate: deterministic session context (block / manual_ready /
        # size clamp ≤ 1.0). RiskGate is already applied in decide_matrix; sessions
        # only RESTRICT further — never relax, never boost. AI cannot override this.
        gate = session_gate.evaluate_open(
            d.symbol, side, d.timeframe, now_utc=now,
            regime=_regime, risk_action=d.risk.action,
        )
        if gate.route == "block":
            actions.append(
                {**entry, "action": "blocked", "reason": gate.reason_code or "market_session_block"}
            )
            continue
        session_mult = gate.effective_multiplier
        # P2 — owner-approval kuyruğu: seans manual_ready VEYA DEFENSIVE/CRISIS rejim.
        # Otomatik açılış YOK; (symbol, side, tf) tekrarında spam olmaz (silent block).
        if gate.route == "manual_ready" or _regime in ("DEFENSIVE", "CRISIS"):
            mr_reason = gate.reason_code if gate.route == "manual_ready" else d.reason
            queued = manual_queue.route_to_manual_ready(
                ps, symbol=d.symbol, timeframe=d.timeframe, side=side,
                size_multiplier=d.size_multiplier * session_mult,
                requested_price=prices.get(d.symbol),
                reason=mr_reason, fingerprint=d.fingerprint, snapshot_id=snap.snapshot_id,
            )
            if queued is not None:
                actions.append({**entry, "action": "manual_ready", "reason": mr_reason})
            else:
                actions.append({**entry, "action": "hold", "reason": "manual_ready_silent_block"})
            continue
        # P1 — açılış tek yoldan (attempt_open): duplicate/scale-in politikası +
        # fiyat denetimi + audit burada. Seans çarpanı kısıtlayıcı uygulanır
        # (final_size = base * min(1.0, session_multiplier)) + seans attribution.
        pos, decision = attempt_open(
            ps,
            symbol=d.symbol,
            side=side,
            entry_price=prices.get(d.symbol),
            size_multiplier=d.size_multiplier * session_mult,
            timeframe=d.timeframe,
            open_reason=d.reason,
            snapshot_id=snap.snapshot_id,
            fingerprint=d.fingerprint,
            data_verified=verified_flags.get(d.symbol, False),
            predicted_confidence=d.confidence,
            raw_confidence=d.raw_confidence,
            confidence_source=d.confidence_source,
            open_dqs=snap.quality.score,
            open_risk_action=d.risk.action,
            **gate.attribution(),
        )
        if pos is not None:
            actions.append({**entry, "action": "open", "reason": d.reason})
        elif decision["reason"] == "no_price":
            actions.append({**entry, "action": "blocked", "reason": "fiyat yok"})
        elif decision.get("duplicate"):
            actions.append({**entry, "action": "hold", "reason": "zaten açık (aynı TF)"})
        else:
            actions.append({**entry, "action": "blocked", "reason": decision["reason"]})

    paper_state.save(ps)

    return {
        "tick_at": datetime.now(UTC).isoformat(),
        "signals_processed": len(decisions),
        "actions": actions,
    }


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
