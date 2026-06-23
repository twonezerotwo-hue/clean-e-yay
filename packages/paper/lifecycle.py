"""Paper trading lifecycle: open / tick (price update + SL/TP + time-stop) / close.

P1 — lifecycle state machine + audit trail. Pozisyon durumları:
OPEN → (EXPIRED_PENDING_PRICE | EXIT_PENDING | ERROR_STATE) → terminal Trade
(CLOSED | FORCE_CLOSED). Fiyat yoksa **fake fiyat uydurulmaz** (DATA_POLICY):
exit beklemeye alınır, sonraki tick'te fiyat gelince kapanır. Her open/close/
blocked/expired olayı `packages/paper/audit.py` ile audit log'a yazılır.

PAPER_SAFE / NO_EXECUTION: gerçek emir yok; RiskGate/halt yalnızca kısıtlayıcı.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta

from packages.data.registry.loader import load_thresholds
from packages.learning import decision_log
from packages.paper import audit, conviction, execution_sim, sizing
from packages.paper.guards import price_sanity, state_anomaly
from packages.paper.state import PaperState, Position, Trade, utc_iso

# Zorla kapanış nedenleri → terminal lifecycle_status=FORCE_CLOSED + ayrı audit
# aksiyonu (KILL_SWITCH_EXIT / RISK_REDUCE_EXIT). Diğerleri normal CLOSED.
_FORCE_CLOSE_REASONS = {"KILL_SWITCH_EXIT", "RISK_REDUCE_EXIT", "MANUAL"}
_FORCE_AUDIT_ACTION = {
    "KILL_SWITCH_EXIT": "KILL_SWITCH_EXIT",
    "RISK_REDUCE_EXIT": "RISK_REDUCE_EXIT",
}


def _timeframe_time_stop_hours(timeframe: str) -> int:
    """thresholds.timeframe_risk[tf].time_stop_hours; yoksa 0 (time-stop yok)."""
    cfg = load_thresholds().get("timeframe_risk") or {}
    pol = cfg.get(timeframe) or {}
    return int(pol.get("time_stop_hours", 0))


def _sl_pct_for(symbol: str) -> float:
    th = load_thresholds()["paper_trading"]
    return float(th["sl_pct"].get(symbol, 0.04))


def _tp_rr() -> float:
    return float(load_thresholds()["paper_trading"]["tp_rr_ratio"])


def _max_pos_usd() -> float:
    return float(load_thresholds()["paper_trading"]["max_position_usd"])


def _new_id(symbol: str, opened_at: str) -> str:
    return hashlib.sha1(f"{symbol}|{opened_at}".encode()).hexdigest()[:10]


def _ensure_daily_anchor(state: PaperState) -> None:
    today = date.today().isoformat()
    if state.daily_anchor_date != today:
        state.daily_anchor_date = today
        state.daily_pnl_usd = 0.0


def open_position(
    state: PaperState,
    *,
    symbol: str,
    side: str,
    entry_price: float,
    size_multiplier: float,
    fingerprint: str | None = None,
    data_verified: bool = False,
    predicted_confidence: float | None = None,
    raw_confidence: float | None = None,
    confidence_source: str | None = None,
    timeframe: str = "1d",
    open_reason: str | None = None,
    snapshot_id: str | None = None,
    scale_in: bool = False,
    open_dqs: float | None = None,
    open_risk_action: str | None = None,
    open_session_action: str | None = None,
    open_session_phase: str | None = None,
    open_session_reason: str | None = None,
    open_session_size_multiplier: float | None = None,
    open_session_primary_market_open: bool | None = None,
    open_session_evidence: str | None = None,
    manual: bool = False,
    size_usd_override: float | None = None,
) -> Position:
    # Konviksiyon kademesi (kalibre p(win) → risk çarpanları). Zayıf konviksiyon:
    # küçük boyut + YAKIN stop + KISA vade + sıkı trailing. Floor (min_open_confidence)
    # decide_for_symbol'da uygulanır; burası açılan pozisyonun risk profilini biçer.
    # MANUEL (owner) emir: kademe çarpanı uygulanmaz; boyutu owner belirler.
    tier = conviction.tier_for(None) if manual else conviction.tier_for(predicted_confidence)
    sl_pct = _sl_pct_for(symbol) * tier.sl_mult
    tp_pct = sl_pct * _tp_rr()
    if size_usd_override is not None:
        # Owner manuel emir: tam dolar tutarı (kademe/sizing baypas).
        size = max(0.0, float(size_usd_override))
    else:
        # Canonical sizing: deterministic multiplier → USD (no AI boost; capped).
        # Kademe size_mult tabanı yalnızca KÜÇÜLTÜR (≤1.0 kademelerde).
        size = sizing.compute_size_usd(
            size_multiplier * tier.size_mult, max_position_usd=_max_pos_usd()
        )
    opened_at = utc_iso()
    sl = entry_price * (1 - sl_pct) if side == "long" else entry_price * (1 + sl_pct)
    tp = entry_price * (1 + tp_pct) if side == "long" else entry_price * (1 - tp_pct)
    # T2 — TF time-stop: 15m kısa (6sa), 1d uzun (672sa); 0 → time-stop yok.
    # Kademe time_mult ile kısalır (zayıf konviksiyon = kısa vade).
    stop_hours = _timeframe_time_stop_hours(timeframe) * tier.time_mult
    valid_until = (
        (datetime.now(UTC) + timedelta(hours=stop_hours)).isoformat()
        if stop_hours > 0
        else None
    )
    pos = Position(
        id=_new_id(f"{symbol}|{timeframe}", opened_at),
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        current_price=entry_price,
        size_usd=round(size, 2),
        sl=round(sl, 4),
        tp=round(tp, 4),
        opened_at=opened_at,
        fingerprint=fingerprint,
        data_verified=bool(data_verified),
        predicted_confidence=predicted_confidence,
        raw_confidence=raw_confidence,
        confidence_source=confidence_source,
        timeframe=timeframe,
        valid_until=valid_until,
        lifecycle_status="OPEN",
        time_stop_expired=False,
        pending_exit_reason=None,
        open_reason=open_reason,
        snapshot_id=snapshot_id,
        scale_in=bool(scale_in),
        open_dqs=open_dqs,
        open_risk_action=open_risk_action,
        open_session_action=open_session_action,
        open_session_phase=open_session_phase,
        open_session_reason=open_session_reason,
        open_session_size_multiplier=open_session_size_multiplier,
        open_session_primary_market_open=open_session_primary_market_open,
        open_session_evidence=open_session_evidence,
        tier="MANUAL" if manual else tier.name,
        trail_distance_pct=tier.trail_distance,
        trail_activate_pct=conviction.trail_activate(),
        trail_peak=entry_price,
        trail_active=False,
    )
    state.open_positions.append(pos)
    audit.record(
        "OPENED",
        position_id=pos.id,
        symbol=symbol,
        timeframe=timeframe,
        side=side,
        tier=tier.name,
        price_used=pos.entry_price,
        size=pos.size_usd,
        reason=open_reason,
        fingerprint=fingerprint,
        snapshot_id=snapshot_id,
        scale_in=bool(scale_in),
    )
    return pos


def find_open(state: PaperState, symbol: str, timeframe: str) -> Position | None:
    """Aynı (symbol, timeframe) için açık pozisyon (yön fark etmez); yoksa None."""
    for p in state.open_positions:
        if p.symbol == symbol and p.timeframe == timeframe:
            return p
    return None


def evaluate_open(
    state: PaperState, *, symbol: str, timeframe: str, side: str, scale_in: bool = False
) -> dict:
    """P1 — duplicate / scale-in politikası (saf, yan etkisiz).

    Aynı (symbol, timeframe) için **yön fark etmeksizin** ikinci pozisyon
    AÇILMAZ — `scale_in=True` explicit verilmedikçe. Bu, hedge/flip'i bilinçli
    olarak engeller (en güvenli politika). Farklı timeframe serbest.
    """
    existing = find_open(state, symbol, timeframe)
    if existing is None:
        return {"allowed": True, "duplicate": False, "reason": None}
    if scale_in:
        return {
            "allowed": True, "duplicate": True, "reason": "scale_in",
            "existing_side": existing.side,
        }
    reason = (
        "duplicate_same_tf" if existing.side == side
        else "opposite_dir_same_tf_no_hedge"
    )
    return {
        "allowed": False, "duplicate": True, "reason": reason,
        "existing_side": existing.side,
    }


def attempt_open(
    state: PaperState,
    *,
    symbol: str,
    side: str,
    entry_price: float | None,
    size_multiplier: float,
    timeframe: str = "1d",
    scale_in: bool = False,
    open_reason: str | None = None,
    snapshot_id: str | None = None,
    fingerprint: str | None = None,
    data_verified: bool = False,
    predicted_confidence: float | None = None,
    raw_confidence: float | None = None,
    confidence_source: str | None = None,
    open_dqs: float | None = None,
    open_risk_action: str | None = None,
    open_session_action: str | None = None,
    open_session_phase: str | None = None,
    open_session_reason: str | None = None,
    open_session_size_multiplier: float | None = None,
    open_session_primary_market_open: bool | None = None,
    open_session_evidence: str | None = None,
) -> tuple[Position | None, dict]:
    """P1 — tek açılış giriş noktası: denetim → blocked/opened + audit.

    Fiyat yok/≤0 → OPEN_BLOCKED(no_price) (fake fiyat YOK). Duplicate (scale_in
    değilse) → OPEN_BLOCKED. Aksi halde `open_position`. tick_worker ve paper
    router AYNI yoldan açar (drift yok). Döner: (Position|None, decision).
    """
    audit.record(
        "OPEN_ATTEMPT", symbol=symbol, timeframe=timeframe, side=side,
        price_used=entry_price, reason=open_reason, snapshot_id=snapshot_id,
        scale_in=bool(scale_in),
    )
    if entry_price is None or entry_price <= 0:
        decision = {"allowed": False, "duplicate": False, "reason": "no_price"}
        audit.record(
            "OPEN_BLOCKED", symbol=symbol, timeframe=timeframe, side=side,
            reason="no_price", snapshot_id=snapshot_id,
        )
        return None, decision
    # Price sanity (absolute bounds): cross-pair contamination / absurd price must
    # not open a position. Restrictive-only; never opens.
    sane_reason = price_sanity.price_sane_reason(symbol, entry_price)
    if sane_reason is not None:
        decision = {"allowed": False, "duplicate": False, "reason": "price_insane"}
        audit.record(
            "OPEN_BLOCKED", symbol=symbol, timeframe=timeframe, side=side,
            reason="price_insane", detail=sane_reason, price_used=entry_price,
            snapshot_id=snapshot_id,
        )
        return None, decision
    # State anomaly: corrupt accounting (equity/realized/daily PnL absurd) blocks
    # NEW opens only — existing position management/close stays possible.
    anomaly = state_anomaly.detect_state(state)
    if anomaly.detected:
        decision = {
            "allowed": False, "duplicate": False, "reason": "state_anomaly",
            "anomaly_reasons": anomaly.reasons,
        }
        audit.record(
            "OPEN_BLOCKED", symbol=symbol, timeframe=timeframe, side=side,
            reason="state_anomaly", detail="; ".join(anomaly.reasons),
            snapshot_id=snapshot_id,
        )
        return None, decision
    decision = evaluate_open(
        state, symbol=symbol, timeframe=timeframe, side=side, scale_in=scale_in
    )
    if not decision["allowed"]:
        audit.record(
            "OPEN_BLOCKED", symbol=symbol, timeframe=timeframe, side=side,
            reason=decision["reason"], snapshot_id=snapshot_id, duplicate=True,
        )
        return None, decision
    pos = open_position(
        state, symbol=symbol, side=side, entry_price=entry_price,
        size_multiplier=size_multiplier, fingerprint=fingerprint,
        data_verified=data_verified, predicted_confidence=predicted_confidence,
        raw_confidence=raw_confidence, confidence_source=confidence_source,
        timeframe=timeframe, open_reason=open_reason, snapshot_id=snapshot_id,
        scale_in=scale_in, open_dqs=open_dqs, open_risk_action=open_risk_action,
        open_session_action=open_session_action,
        open_session_phase=open_session_phase,
        open_session_reason=open_session_reason,
        open_session_size_multiplier=open_session_size_multiplier,
        open_session_primary_market_open=open_session_primary_market_open,
        open_session_evidence=open_session_evidence,
    )
    return pos, decision


def close_position(
    state: PaperState,
    pos: Position,
    *,
    exit_price: float,
    reason: str,
    close_size: float | None = None,
) -> Trade:
    # close_size verilmişse ve pozisyon boyutundan küçükse KISMİ kapatma: o kadar
    # realize edilir, pozisyon kalan boyutla AÇIK kalır. Aksi halde tam kapatma.
    full = close_size is None or close_size >= pos.size_usd - 1e-6
    realized_size = pos.size_usd if full else float(close_size)
    # Realized fill P&L — formalized in execution_sim (no broker; paper fill math).
    pnl = execution_sim.realized_pnl(pos.side, pos.entry_price, exit_price, realized_size)
    lifecycle_status = "FORCE_CLOSED" if reason in _FORCE_CLOSE_REASONS else "CLOSED"
    trade = Trade(
        id=pos.id,
        symbol=pos.symbol,
        side=pos.side,
        entry_price=pos.entry_price,
        exit_price=round(exit_price, 4),
        pnl_usd=round(pnl, 2),
        opened_at=pos.opened_at,
        closed_at=utc_iso(),
        close_reason=reason,
        fingerprint=pos.fingerprint,
        data_verified=pos.data_verified,
        predicted_confidence=pos.predicted_confidence,
        raw_confidence=pos.raw_confidence,
        confidence_source=pos.confidence_source,
        timeframe=pos.timeframe,
        lifecycle_status=lifecycle_status,
        open_reason=pos.open_reason,
        snapshot_id=pos.snapshot_id,
        open_dqs=pos.open_dqs,
        open_risk_action=pos.open_risk_action,
        open_session_action=pos.open_session_action,
        open_session_phase=pos.open_session_phase,
        open_session_reason=pos.open_session_reason,
        open_session_size_multiplier=pos.open_session_size_multiplier,
        open_session_primary_market_open=pos.open_session_primary_market_open,
        open_session_evidence=pos.open_session_evidence,
    )
    state.recent_trades.append(trade)
    # Signal attribution: kapanan trade'in karar izini kalıcı decision_log'a yaz
    # (best-effort; lifecycle'ı kesmez).
    decision_log.record_close(trade)
    if full:
        state.open_positions = [p for p in state.open_positions if p.id != pos.id]
    else:
        # Kısmi: pozisyon kalan boyutla açık kalır (trailing peak/SL korunur).
        pos.size_usd = round(pos.size_usd - realized_size, 2)
    state.realized_pnl_usd = round(state.realized_pnl_usd + trade.pnl_usd, 2)
    _ensure_daily_anchor(state)
    state.daily_pnl_usd = round(state.daily_pnl_usd + trade.pnl_usd, 2)
    state.equity_usd = round(state.equity_usd + trade.pnl_usd, 2)
    if state.equity_usd > state.peak_equity_usd:
        state.peak_equity_usd = state.equity_usd
    audit.record(
        _FORCE_AUDIT_ACTION.get(reason, "CLOSED"),
        position_id=pos.id,
        symbol=pos.symbol,
        timeframe=pos.timeframe,
        side=pos.side,
        reason=reason,
        price_used=round(exit_price, 4),
        size=realized_size,
        pnl=trade.pnl_usd,
        lifecycle_status=lifecycle_status,
        snapshot_id=pos.snapshot_id,
        open_reason=pos.open_reason,
    )
    return trade


def _valid_position(pos: Position) -> bool:
    """Pozisyon alanları tutarlı mı (ERROR_STATE guard'ı)."""
    try:
        return (
            pos.entry_price is not None and pos.entry_price > 0
            and pos.size_usd is not None and pos.size_usd > 0
            and pos.side in ("long", "short")
        )
    except (TypeError, ValueError):
        return False


def _set_status(pos: Position, status: str, pending_reason: str | None = None) -> None:
    pos.lifecycle_status = status
    pos.pending_exit_reason = pending_reason


def _time_stop_due(pos: Position, now: datetime) -> bool:
    if not pos.valid_until:
        return False
    try:
        return now >= datetime.fromisoformat(pos.valid_until)
    except ValueError:
        return False


def _trailing_breached(pos: Position, price: float) -> bool:
    """Trailing stop: lehteki tepe fiyatı (highwater) izler. Pozisyon
    trail_activate kadar lehe geçince DEVREYE girer; sonra tepe fiyattan
    trail_distance kadar geri çekilirse exit verir. Sadece kârı korur —
    açılış stop'unu (SL) gevşetmez, asla zarara doğru genişlemez."""
    dist = pos.trail_distance_pct
    if not dist or pos.entry_price <= 0:
        return False
    act = pos.trail_activate_pct or 0.0
    if pos.side == "long":
        if pos.trail_peak is None or price > pos.trail_peak:
            pos.trail_peak = price
        if (pos.trail_peak - pos.entry_price) / pos.entry_price >= act:
            pos.trail_active = True
        return bool(pos.trail_active and price <= pos.trail_peak * (1 - dist))
    # short
    if pos.trail_peak is None or price < pos.trail_peak:
        pos.trail_peak = price
    if (pos.entry_price - pos.trail_peak) / pos.entry_price >= act:
        pos.trail_active = True
    return bool(pos.trail_active and price >= pos.trail_peak * (1 + dist))


def _pending_triggered(order, price: float) -> bool:
    """Limit: long fiyat ≤ tetik / short ≥ tetik. Stop & stop_limit: long ≥ tetik /
    short ≤ tetik."""
    if order.order_type == "limit":
        return price <= order.trigger_price if order.side == "long" else price >= order.trigger_price
    return price >= order.trigger_price if order.side == "long" else price <= order.trigger_price


def trigger_pending_orders(
    state: PaperState, prices: dict[str, float], now: datetime | None = None
) -> list[Position]:
    """Bekleyen limit/stop emirleri güncel fiyatla kontrol et; tetiklenenleri
    pozisyona çevir (tetik fiyatından doldur) ve kuyruktan çıkar. Fiyat yoksa/
    geçersizse atlanır (uydurma fiyat YOK)."""
    opened: list[Position] = []
    for o in list(state.pending_orders):
        price = prices.get(o.symbol)
        if price is None or price <= 0:
            continue
        if not price_sanity.tick_price_usable(o.symbol, price, o.trigger_price):
            continue
        if not _pending_triggered(o, float(price)):
            continue
        # stop_limit: tetik sonrası limit fiyatından dolar; diğerleri tetik fiyatından.
        fill_price = (
            o.limit_price if (o.order_type == "stop_limit" and o.limit_price) else o.trigger_price
        )
        pos = open_position(
            state,
            symbol=o.symbol,
            side=o.side,
            entry_price=float(fill_price),
            size_multiplier=0.0,
            manual=True,
            size_usd_override=float(o.size_usd),
            timeframe=o.timeframe,
            open_reason=f"pending_{o.order_type}",
        )
        state.pending_orders = [x for x in state.pending_orders if x.id != o.id]
        audit.record(
            "PENDING_FILLED", position_id=pos.id, symbol=o.symbol, side=o.side,
            price_used=pos.entry_price, size=pos.size_usd, reason=o.order_type,
        )
        opened.append(pos)
    return opened


def tick(
    state: PaperState,
    prices: dict[str, float],
    now: datetime | None = None,
) -> list[Trade]:
    """Pozisyon fiyatlarını günceller; SL/TP'ye değen veya time-stop'u
    dolan pozisyonları kapatır.

    T2 — time-stop (TIME_STOP_EXIT) için de güncel fiyat şarttır; fiyatı
    olmayan pozisyon kapatılmaz (mock fiyat yok — DATA_POLICY), sonraki
    tick'te tekrar denenir.
    """
    now = now or datetime.now(UTC)
    # Önce bekleyen limit/stop emirleri tetikle (yeni pozisyonlar aynı tick'te yönetilir).
    trigger_pending_orders(state, prices, now)
    closed: list[Trade] = []
    for pos in list(state.open_positions):
        # P1 — bozuk pozisyon → ERROR_STATE; kapatma denenmez (fake fiyat YOK).
        if not _valid_position(pos):
            if pos.lifecycle_status != "ERROR_STATE":
                _set_status(pos, "ERROR_STATE")
                audit.record(
                    "ERROR", position_id=pos.id, symbol=pos.symbol,
                    timeframe=pos.timeframe, reason="invalid_position_fields",
                )
            continue
        due = _time_stop_due(pos, now)
        pos.time_stop_expired = due
        price = prices.get(pos.symbol)
        # Price sanity: a contaminated tick (out of bounds AND a large jump vs the
        # last price) is treated as "no usable price" — never close/manage on
        # garbage. The next in-range tick resumes normal handling.
        if price is not None and not price_sanity.tick_price_usable(
            pos.symbol, price, pos.current_price
        ):
            price = None
        if price is None or price <= 0:
            # Fiyat yok: time-stop dolduysa EXPIRED_PENDING_PRICE — fake fiyatla
            # kapatma YOK (DATA_POLICY). Geçişte bir kez audit (spam yok).
            if due and pos.lifecycle_status != "EXPIRED_PENDING_PRICE":
                _set_status(pos, "EXPIRED_PENDING_PRICE", "TIME_STOP_EXIT")
                audit.record(
                    "TIME_STOP_EXPIRED", position_id=pos.id, symbol=pos.symbol,
                    timeframe=pos.timeframe, reason="no_price_exit_pending",
                )
                audit.record(
                    "EXIT_PENDING", position_id=pos.id, symbol=pos.symbol,
                    timeframe=pos.timeframe, reason="TIME_STOP_EXIT",
                )
            continue
        pos.current_price = price
        # SL/TP kontrol — formalized fill simulation (fill at observed tick price).
        fill = execution_sim.simulate_exit_fill(
            side=pos.side, entry_price=pos.entry_price, sl=pos.sl, tp=pos.tp,
            size_usd=pos.size_usd, price=price,
        )
        if fill is not None:
            closed.append(
                close_position(state, pos, exit_price=fill.fill_price, reason=fill.reason)
            )
            continue
        # Trailing stop — SL/TP değmediyse kâr-koruma çıkışı (kademe trail_distance'ı).
        if _trailing_breached(pos, price):
            closed.append(
                close_position(state, pos, exit_price=price, reason="TRAILING_STOP_EXIT")
            )
            continue
        if due:
            # Fiyat geldi → bekleyen time-stop'u şimdi kapat (EXPIRED→CLOSED).
            closed.append(
                close_position(state, pos, exit_price=price, reason="TIME_STOP_EXIT")
            )
            continue
        # Normal aktif — bekleyen exit varsa temizle (OPEN'a dön).
        if pos.lifecycle_status != "OPEN":
            _set_status(pos, "OPEN")
    return closed


def flatten_all(
    state: PaperState, prices: dict[str, float], *, reason: str = "KILL_SWITCH_EXIT"
) -> list[Trade]:
    """G5 — KILL_SWITCH halt: tüm açık pozisyonları kapat (KILL_SWITCH_EXIT).

    Sadece risk azaltıcı; fiyatı olmayan pozisyon **EXIT_PENDING**'e alınır
    (mock fiyat uydurulmaz — DATA_POLICY), bir sonraki tick'te tekrar denenir.
    """
    closed: list[Trade] = []
    for pos in list(state.open_positions):
        price = prices.get(pos.symbol)
        # Don't realize PnL at a contaminated price even under KILL_SWITCH — hold
        # to EXIT_PENDING and retry on the next in-range tick.
        if price is not None and not price_sanity.tick_price_usable(
            pos.symbol, price, pos.current_price
        ):
            price = None
        if price is None or price <= 0:
            if pos.lifecycle_status != "EXIT_PENDING":
                _set_status(pos, "EXIT_PENDING", reason)
                audit.record(
                    "EXIT_PENDING", position_id=pos.id, symbol=pos.symbol,
                    timeframe=pos.timeframe, reason=reason,
                )
            continue
        closed.append(close_position(state, pos, exit_price=price, reason=reason))
    return closed


def max_drawdown_pct(state: PaperState) -> float:
    if state.peak_equity_usd <= 0:
        return 0.0
    return round(
        max(0.0, (state.peak_equity_usd - state.equity_usd) / state.peak_equity_usd),
        4,
    )
