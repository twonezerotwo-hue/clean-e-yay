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
from datetime import UTC, datetime, timedelta

from packages.data.registry.loader import load_thresholds
from packages.learning import decision_log
from packages.paper import audit, conviction, execution_sim, sizing
from packages.paper.guards import price_sanity, state_anomaly
from packages.paper.state import PaperState, Position, Trade, utc_iso
from packages.risk.trade_economics import (
    compute_fixed_targets,
    compute_structural_targets,
    compute_tf_targets,
    tf_targets_enabled,
    tf_trail_mult,
    tf_trailing_mults,
)

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


def _max_pos_usd() -> float:
    return float(load_thresholds()["paper_trading"]["max_position_usd"])


# P2 — kapanış-bazlı stop yardımcıları.
_TF_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}


def _close_based_stop_enabled() -> bool:
    """P2 flag'i (default False → SL tetikleme fitil, bayt-aynı). monkeypatch-seam."""
    return bool((load_thresholds().get("exit_close_based_stop") or {}).get("enabled", False))


def _structural_stop_cfg() -> dict:
    """P2 parça-2 — yapısal stop yerleşimi config (default enabled False → SL yeri
    mevcut ATR motoruyla, bayt-aynı). monkeypatch-seam."""
    return load_thresholds().get("exit_structural_stop") or {}


def _recent_bars_for_stop(symbol: str, timeframe: str, count: int = 15) -> list:
    """Yapısal stop için son barlar (ohlcv disk cache, ağ yok). Yoksa boş liste
    → çağıran ATR motoruna düşer (uydurma seviye yok). Saf/defansif."""
    try:
        from packages.data.providers.ohlcv import cache as ohlcv_cache
        cached = ohlcv_cache.load(symbol, timeframe)  # type: ignore[arg-type]
    except Exception:
        return []
    if not cached or not cached.bars:
        return []
    return list(cached.bars)[-count:]


def _last_closed_close(symbol: str, timeframe: str, now: datetime) -> float | None:
    """Pozisyon TF'inin son KAPANMIŞ barının kapanışı (kapanış-bazlı SL tetiği).

    Forming (henüz kapanmamış) bar ATLANIR — yoksa kapanış-bazlı avantaj kaybolur
    (forming close ≈ tick). ohlcv 1d/TF disk cache okur (ağ yok). Cache yok/yetersiz/
    bilinmeyen TF → None (çağıran fitil davranışına düşer; uydurma yok). Saf/defansif."""
    tf_sn = _TF_SECONDS.get(timeframe)
    if tf_sn is None:
        return None
    try:
        from packages.data.providers.ohlcv import cache as ohlcv_cache
        cached = ohlcv_cache.load(symbol, timeframe)  # type: ignore[arg-type]
    except Exception:
        return None
    if not cached or not cached.bars:
        return None
    now_ts = now.timestamp()
    for b in reversed(cached.bars):
        ts = b.ts if b.ts.tzinfo else b.ts.replace(tzinfo=UTC)
        if ts.timestamp() + tf_sn <= now_ts:  # bar kapanmış (açılış + TF süresi geçti)
            return float(b.close) if b.close and b.close > 0 else None
    return None


def _new_id(symbol: str, opened_at: str) -> str:
    return hashlib.sha1(f"{symbol}|{opened_at}".encode()).hexdigest()[:10]


def _ensure_daily_anchor(state: PaperState) -> None:
    # F1-4 — gün çapası UTC: sistemin geri kalanı (opened_at/closed_at/audit)
    # UTC damgalı; date.today() lokal gün kullanınca gün sınırında daily-loss
    # reset'i UTC'ye göre saatlerce kayıyordu.
    today = datetime.now(UTC).date().isoformat()
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
    atr: float | None = None,
    module_contributions: dict[str, float] | None = None,
) -> Position:
    # Konviksiyon kademesi (kalibre p(win) → risk çarpanları). Zayıf konviksiyon:
    # küçük boyut + YAKIN stop + KISA vade + sıkı trailing. Floor (min_open_confidence)
    # decide_for_symbol'da uygulanır; burası açılan pozisyonun risk profilini biçer.
    # MANUEL (owner) emir: kademe çarpanı uygulanmaz; boyutu owner belirler.
    tier = conviction.tier_for(None) if manual else conviction.tier_for(predicted_confidence)
    # SL/TP motoru seçimi: thresholds.timeframe_targets.enabled true ise TF-duyarlı
    # compute_tf_targets (ATR-çapalı + floor/cap; ATR yoksa TF-ölçekli fallback);
    # false ise mevcut compute_fixed_targets (sembol-bazlı sabit-% + tier). Geri
    # dönüş tek flag ile — bozulma yok. shadow.evaluate_symbol her iki motoru
    # her tick yan yana hesaplar, yani aktivasyon öncesi tam gözlem var.
    # P2 parça-2 — YAPISAL stop yerleşimi (flag default OFF → aşağıdaki ATR motoru,
    # bayt-aynı). Açıkken sl = son N-bar dip/tepe (owner "son dip altı"); yapı
    # geçersiz/bar yok → ATR motoruna düşer (uydurma seviye yok).
    targets = None
    sscfg = _structural_stop_cfg()
    if sscfg.get("enabled", False):
        _bars = _recent_bars_for_stop(symbol, timeframe)
        if _bars:
            _st = compute_structural_targets(
                symbol, side, entry_price,
                highs=[float(b.high) for b in _bars],
                lows=[float(b.low) for b in _bars],
                timeframe=timeframe, atr=atr,
                predicted_confidence=predicted_confidence, manual=manual,
                lookback=int(sscfg.get("lookback", 10)),
                buffer_pct=float(sscfg.get("buffer_pct", 0.001)),
            )
            if _st.sl_basis != "invalid":
                targets = _st
    if targets is None:
        if tf_targets_enabled():
            targets = compute_tf_targets(
                symbol, side, entry_price, timeframe=timeframe, atr=atr,
                predicted_confidence=predicted_confidence, manual=manual,
            )
        else:
            targets = compute_fixed_targets(
                symbol, side, entry_price, predicted_confidence=predicted_confidence, manual=manual,
            )
    sl, tp = targets.sl, targets.tp
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
    # T2 — TF time-stop: 15m kısa (6sa), 1d uzun (672sa); 0 → time-stop yok.
    # Kademe time_mult ile kısalır (zayıf konviksiyon = kısa vade).
    stop_hours = _timeframe_time_stop_hours(timeframe) * tier.time_mult
    valid_until = (
        (datetime.now(UTC) + timedelta(hours=stop_hours)).isoformat()
        if stop_hours > 0
        else None
    )
    # TF-farkında trailing (forensics: düz trailing higher-TF'de erken çıkıp kârı
    # geri veriyor). Flag OFF → mult (1.0,1.0), düz değer birebir (bayt-aynı). Eski
    # (düz) değerler shadow olarak OPENED audit'ine yazılır (paraşüt + kıyas).
    _trail_dist_mult, _trail_act_mult = tf_trailing_mults(timeframe)
    _trail_dist_flat = tier.trail_distance * tf_trail_mult(timeframe)
    _trail_act_flat = conviction.trail_activate()
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
        # CP4 slice 3 — öğrenilen per-TF trailing gevşemesi. Flag OFF → tf_trail_mult
        # 1.0 döner, trail_distance birebir tier.trail_distance (bayt-aynı). MANUEL
        # emirde de uygulanır (timeframe'e bağlı, tier'dan bağımsız çarpan).
        trail_distance_pct=_trail_dist_flat * _trail_dist_mult,
        trail_activate_pct=_trail_act_flat * _trail_act_mult,
        trail_peak=entry_price,
        trail_active=False,
        # F1-3 — consensus modül katkı vektörü (manuel/legacy açılışta None).
        open_module_contributions=module_contributions,
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
        # TF-farkında trailing shadow (eski düz değer paraşüt + kıyas): canlı
        # kullanılan vs eski-düz. Flag OFF iken ikisi eşit (bayt-aynı gözlem).
        trail_distance_used=round(pos.trail_distance_pct, 5),
        trail_distance_flat=round(_trail_dist_flat, 5),
        trail_activate_used=round(pos.trail_activate_pct, 5),
        trail_activate_flat=round(_trail_act_flat, 5),
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
    atr: float | None = None,
    module_contributions: dict[str, float] | None = None,
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
    sane_reason = price_sanity.price_sane_with_ohlcv_reason(
        symbol, entry_price, timeframe=timeframe
    )
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
        atr=atr,
        module_contributions=module_contributions,
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
    closed_at = utc_iso()
    # F1-5 — kısmi kapanışta trade id benzersiz olmalı: aynı pos.id ile birden çok
    # Trade üretmek decision_log kurtarma dedupe'unda (outcomes_from_state,
    # trade_id bazlı) kısmi leg'lerden birini düşürüyordu. Tam kapanış pos.id'yi
    # birebir korur (mevcut davranış); kısmi leg türetilmiş deterministik id alır.
    trade_id = (
        pos.id
        if full
        else hashlib.sha1(f"{pos.id}|{closed_at}|{realized_size}".encode()).hexdigest()[:10]
    )
    # F1-1 — açılış risk mesafesi (R-multiple paydası): |entry−SL|/entry.
    # SL'siz/legacy pozisyon → None (uydurma yok; R hesaplanamaz, outcome'da None).
    open_risk_pct = (
        round(abs(pos.entry_price - pos.sl) / pos.entry_price, 6)
        if pos.sl is not None and pos.entry_price > 0
        else None
    )
    # Realized fill P&L — formalized in execution_sim (no broker; paper fill math).
    pnl = execution_sim.realized_pnl(pos.side, pos.entry_price, exit_price, realized_size)
    lifecycle_status = "FORCE_CLOSED" if reason in _FORCE_CLOSE_REASONS else "CLOSED"
    trade = Trade(
        id=trade_id,
        symbol=pos.symbol,
        side=pos.side,
        entry_price=pos.entry_price,
        exit_price=round(exit_price, 4),
        pnl_usd=round(pnl, 2),
        opened_at=pos.opened_at,
        closed_at=closed_at,
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
        mae_pct=pos.mae_pct,
        mfe_pct=pos.mfe_pct,
        open_risk_pct=open_risk_pct,
        open_module_contributions=pos.open_module_contributions,
        # F4-3 — partial-TP shadow izi: r-hit görüldü mü + hipotetik strateji PnL'i
        # (yalnız r-hit'li, gerçek ptp uygulanmamış TAM kapanışlarda dolar).
        ptp_r_hit=pos.ptp_r_hit_at is not None,
        ptp_shadow_pnl_usd=_ptp_shadow_pnl(pos, exit_price, full),
        # Exit-forensics — kapanan dilimin $ büyüklüğü (kısmi legde realized_size).
        size_usd=round(realized_size, 2),
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


def _update_excursions(pos: Position, price: float) -> None:
    """Pozisyon süresince MAE/MFE'yi monoton ilerlet (yakıt: tf_target_trainer).

    MAE = entry'ye göre ters yönde gördüğü en uç hareket (%, pozitif sayı).
    MFE = entry'ye göre lehte gördüğü en uç hareket (%, pozitif sayı).
    Saf hesap; tick fiyatı güvenli (price_sanity'den geçmiş) varsayılır.
    """
    if pos.entry_price <= 0 or price <= 0:
        return
    diff = (price - pos.entry_price) / pos.entry_price * 100.0
    favorable = diff if pos.side == "long" else -diff
    adverse = -diff if pos.side == "long" else diff
    if favorable > pos.mfe_pct:
        pos.mfe_pct = round(favorable, 4)
    if adverse > pos.mae_pct:
        pos.mae_pct = round(adverse, 4)


def _partial_tp_cfg() -> dict:
    """F4-3 — `partial_tp` config'i (enabled DEFAULT False = davranış bayt-aynı).

    trigger_r: kısmi kapatmanın tetiklendiği kâr mesafesi (R katı; R=|entry−SL|).
    close_fraction: tetikte kapatılan oran. breakeven: kalan yarının SL'i girişe
    çekilsin mi (yalnız SIKILAŞTIRIR — SL asla gevşetilmez)."""
    try:
        raw = load_thresholds().get("partial_tp") or {}
        return {
            "enabled": bool(raw.get("enabled", False)),
            "trigger_r": max(0.1, float(raw.get("trigger_r", 1.0))),
            "close_fraction": min(0.9, max(0.1, float(raw.get("close_fraction", 0.5)))),
            "breakeven": bool(raw.get("breakeven", True)),
        }
    except (OSError, KeyError, ValueError, TypeError):
        return {"enabled": False, "trigger_r": 1.0, "close_fraction": 0.5, "breakeven": True}


def _ptp_observe_and_apply(
    state: PaperState, pos: Position, price: float, closed: list[Trade]
) -> None:
    """F4-3 — partial-TP: shadow gözlemi HER ZAMAN, gerçek aksiyon yalnız flag ON.

    Gözlem (flag'ten bağımsız): kâr ilk kez trigger_r×R'ye değince damgala
    (ptp_r_hit_at/ptp_price_at_r); r-hit SONRASI fiyat girişe dönerse
    ptp_be_touched=True (breakeven senaryosu gerçekleşirdi). Tick-fiyat
    bazlı dürüst yaklaşım — gap'te kaçan seviye uydurulmaz.

    Aksiyon (partial_tp.enabled=True): tetikte close_fraction kadar kısmi
    kapat (PARTIAL_TP_EXIT; F1-5 benzersiz leg id) + breakeven açıksa SL'i
    girişe çek (yalnız sıkılaştırır). RiskGate/DQS/halt'ı bypass etmez —
    yalnız kâr realize eder ve riski KÜÇÜLTÜR."""
    if pos.sl is None or pos.entry_price <= 0:
        return  # R tanımsız (SL'siz/legacy) — uydurma risk mesafesi yok
    risk = abs(pos.entry_price - pos.sl)
    if risk <= 0:
        return
    favorable = (price - pos.entry_price) if pos.side == "long" else (pos.entry_price - price)
    cfg = _partial_tp_cfg()
    if pos.ptp_r_hit_at is None:
        if favorable >= cfg["trigger_r"] * risk:
            pos.ptp_r_hit_at = utc_iso()
            pos.ptp_price_at_r = round(price, 4)
            if cfg["enabled"] and not pos.ptp_done:
                closed.append(
                    close_position(
                        state, pos, exit_price=price, reason="PARTIAL_TP_EXIT",
                        close_size=pos.size_usd * cfg["close_fraction"],
                    )
                )
                pos.ptp_done = True
                if cfg["breakeven"]:
                    tighter = (
                        pos.entry_price > pos.sl if pos.side == "long"
                        else pos.entry_price < pos.sl
                    )
                    if tighter:
                        pos.sl = round(pos.entry_price, 4)
        return
    # r-hit sonrası: fiyat girişe geri döndü mü (shadow breakeven kanıtı)
    if not pos.ptp_be_touched:
        returned = price <= pos.entry_price if pos.side == "long" else price >= pos.entry_price
        if returned:
            pos.ptp_be_touched = True


def _ptp_shadow_pnl(pos: Position, exit_price: float, full: bool) -> float | None:
    """F4-3 — 'trigger'da %X kapat + breakeven' stratejisinin HİPOTETİK PnL'i.

    Yalnız: TAM kapanış + r-hit görülmüş + gerçek partial-TP UYGULANMAMIŞ
    pozisyonlarda hesaplanır (gerçek uygulananın ölçümü zaten gerçek leg'ler).
    Kapatılan kısım r-hit fiyatından; kalan kısım be_touched ise girişten (0),
    değilse gerçek çıkış fiyatından realize edilmiş sayılır."""
    if not full or pos.ptp_done or pos.ptp_r_hit_at is None or pos.ptp_price_at_r is None:
        return None
    frac = _partial_tp_cfg()["close_fraction"]
    first = execution_sim.realized_pnl(
        pos.side, pos.entry_price, pos.ptp_price_at_r, pos.size_usd * frac
    )
    rest_size = pos.size_usd * (1.0 - frac)
    rest = (
        0.0 if pos.ptp_be_touched
        else execution_sim.realized_pnl(pos.side, pos.entry_price, exit_price, rest_size)
    )
    return round(first + rest, 2)


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
        _update_excursions(pos, price)
        # P2 — kapanış-bazlı SL: flag açıkken SL tetiği tick yerine son KAPANMIŞ
        # bar kapanışı (fitil-avı bağışık). Kapanış yoksa None → fitil davranışı
        # (güvenli fallback). Flag kapalıyken sl_trig=None → tetikleme bayt-aynı.
        # TP her zaman tick `price` ile (kâr al fitille; owner kuralı yalnız STOP).
        sl_trig = (
            _last_closed_close(pos.symbol, pos.timeframe, now)
            if _close_based_stop_enabled() else None
        )
        # SL/TP kontrol — formalized fill simulation (fill at observed tick price).
        fill = execution_sim.simulate_exit_fill(
            side=pos.side, entry_price=pos.entry_price, sl=pos.sl, tp=pos.tp,
            size_usd=pos.size_usd, price=price, sl_trigger_price=sl_trig,
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
        # F4-3 — partial-TP: shadow gözlemi her tick; gerçek kısmi kapatma yalnız
        # flag ON. SL/TP/trailing/time-stop'tan SONRA çalışır — tam çıkış her
        # zaman önceliklidir (gap'te TP'ye giden pozisyon parçalanmaz).
        _ptp_observe_and_apply(state, pos, price, closed)
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
        _update_excursions(pos, price)
        closed.append(close_position(state, pos, exit_price=price, reason=reason))
    return closed


def max_drawdown_pct(state: PaperState) -> float:
    if state.peak_equity_usd <= 0:
        return 0.0
    return round(
        max(0.0, (state.peak_equity_usd - state.equity_usd) / state.peak_equity_usd),
        4,
    )
