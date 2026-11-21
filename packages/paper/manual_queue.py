"""Manual-ready / rejected-signal workflow (owner approval queue).

Phase 2 port from e-yay-codex paper_trading manual_ready_trades. In DEFENSIVE/CRISIS
regimes the tick must NOT auto-open: a candidate is routed to the manual-ready queue
and only an explicit owner approval opens it.

Anti-spam rule (the critical one): a rejected/queued signal silently blocks the same
`(symbol, side, timeframe)` regardless of fingerprint drift (score 60→61, module
shift). A different timeframe or direction is a NEW candidate (recurring signal).

Owner actions:
  - approve → open via the guarded `attempt_open` (price sanity / state anomaly /
    duplicate still apply); clears the queued + rejected records for that key.
    Yalnız güncel fiyatla; fiyat kuyruk fiyatından 0,5 ATR'den fazla kaçtıysa açmaz.
  - reject  → remove from queue AND record a RejectedSignal so it stops re-appearing
    while the same signal keeps arriving; one bar of absence ends the rejection.
  - dismiss → remove from queue only (may re-queue next tick).

Ömür (2026-11-16): aday kendi zaman diliminin bir barı yaşar; eskimiş aday okuma
yüzeylerinde görünmez, onaylanamaz, anahtarı engellemez ve sonraki kuyruklamada silinir.

PAPER_SAFE / NO_EXECUTION: no real orders; approval opens a paper position only.
"""
from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta

from packages.paper import audit
from packages.paper.lifecycle import _TF_SECONDS, attempt_open
from packages.paper.state import ManualReady, PaperState, RejectedSignal
from packages.risk.engine import RiskInput, evaluate_for_open

# Canonical RiskGate actions that forbid opening a NEW position (mirror of the
# decision engine: KILL_SWITCH→blocked, RISK_REDUCE/NO_POSITION_INCREASE→hold).
_RISK_BLOCKS_NEW_OPEN = {"KILL_SWITCH", "RISK_REDUCE", "NO_POSITION_INCREASE"}

# Kuyruk ömrü (karar-destek adım 1, 2026-11-16): aday kendi zaman diliminin BİR barı
# kadar geçerlidir. Sonra fiyat ve kurulum değişmiştir; onay eski plana dayanır. Sinyal
# sürüyorsa sonraki tick taze fiyatla yeniden kuyruğa koyar. Eskiden ömür yoktu: canlı
# kuyrukta 6 haftalık adaylar aynı anahtarları sessizce engelliyordu.
_DEFAULT_TTL_SEC = 3600
# Geç onay: fiyat kuyruğa giriş fiyatından bu kadar ATR (aynı TF) uzaklaştıysa onay
# açmaz — giriş/stop planı artık geçerli değil.
LATE_PRICE_ATR = 0.5


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def ttl_seconds(timeframe: str) -> int:
    """Bir bar (saniye); bilinmeyen TF → 1 saat."""
    return int(_TF_SECONDS.get(timeframe, _DEFAULT_TTL_SEC))


def expires_at(entry: ManualReady) -> datetime | None:
    start = _parse_ts(entry.requested_at)
    return None if start is None else start + timedelta(seconds=ttl_seconds(entry.timeframe))


def is_expired(entry: ManualReady, now: datetime | None = None) -> bool:
    """Okunamayan zaman damgası da eskimiş sayılır: yaşı bilinmeyen aday onaylanmaz."""
    end = expires_at(entry)
    return end is None or (now or datetime.now(UTC)) >= end


def active(state: PaperState, now: datetime | None = None) -> list[ManualReady]:
    """Onaylanabilir (eskimemiş) adaylar — okuma yüzeyleri yalnız bunları gösterir."""
    now = now or datetime.now(UTC)
    return [m for m in state.manual_ready if not is_expired(m, now)]


def purge_expired(state: PaperState, now: datetime | None = None) -> int:
    """Eskimiş adayları kuyruktan çıkarır (her biri denetim kaydına); çıkan sayıyı döner."""
    now = now or datetime.now(UTC)
    gone = [m for m in state.manual_ready if is_expired(m, now)]
    if gone:
        state.manual_ready = [m for m in state.manual_ready if not is_expired(m, now)]
        for m in gone:
            audit.record(
                "MANUAL_READY_EXPIRED", position_id=m.id, symbol=m.symbol, timeframe=m.timeframe,
                side=m.side, reason=m.reason,
            )
    return len(gone)


def rejection_active(rej: RejectedSignal, now: datetime | None = None) -> bool:
    """Ret, aynı sinyal gelmeye devam ettikçe geçerlidir. Sinyal en az bir bar görünmeyip
    geri gelirse yeni aday sayılır (eskiden ret kalıcıydı; temizleyici hiç çağrılmıyordu)."""
    last = _parse_ts(rej.last_seen_at) or _parse_ts(rej.rejected_at)
    if last is None:
        return False
    return ((now or datetime.now(UTC)) - last).total_seconds() < ttl_seconds(rej.timeframe)


def active_rejection_count(state: PaperState, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    return sum(1 for r in state.rejected_signals if rejection_active(r, now))


def _make_id(symbol: str, timeframe: str, side: str, requested_at: str) -> str:
    return hashlib.sha1(f"{symbol}|{timeframe}|{side}|{requested_at}".encode()).hexdigest()[:10]


def _find_ready(state: PaperState, symbol: str, side: str, timeframe: str) -> ManualReady | None:
    for m in state.manual_ready:
        if m.symbol == symbol and m.side == side and m.timeframe == timeframe:
            return m
    return None


def _find_ready_by_id(state: PaperState, manual_id: str) -> ManualReady | None:
    for m in state.manual_ready:
        if m.id == manual_id:
            return m
    return None


def _find_rejection(state: PaperState, symbol: str, side: str, timeframe: str) -> RejectedSignal | None:
    for r in state.rejected_signals:
        if r.symbol == symbol and r.side == side and r.timeframe == timeframe:
            return r
    return None


def should_silent_block(
    state: PaperState, symbol: str, side: str, timeframe: str, now: datetime | None = None,
) -> bool:
    """True if this exact (symbol, side, timeframe) is queued (not expired) or its
    rejection is still active.

    Fingerprint-independent: a re-scored variant of the same signal must not spam.
    """
    now = now or datetime.now(UTC)
    rej = _find_rejection(state, symbol, side, timeframe)
    if rej is not None and rejection_active(rej, now):
        return True
    ready = _find_ready(state, symbol, side, timeframe)
    return ready is not None and not is_expired(ready, now)


def is_recurring_signal(state: PaperState, symbol: str, side: str, timeframe: str) -> bool:
    """True if a queued candidate exists for `symbol` but with a different side/tf."""
    for m in state.manual_ready:
        if m.symbol == symbol and (m.side != side or m.timeframe != timeframe):
            return True
    return False


def route_to_manual_ready(
    state: PaperState,
    *,
    symbol: str,
    timeframe: str,
    side: str,
    size_multiplier: float,
    requested_price: float | None,
    reason: str | None = None,
    fingerprint: str | None = None,
    snapshot_id: str | None = None,
    signal_id: str | None = None,
    decision_id: str | None = None,
    news_setup_id: str | None = None,
    news_event_id: str | None = None,
    news_evidence_id: str | None = None,
    now: datetime | None = None,
) -> ManualReady | None:
    """Queue a candidate for owner approval. Returns the entry, or None if silently
    blocked (already queued/rejected — no spam).

    Önce eskimiş adaylar çıkar. Aktif ret varsa sinyalin hâlâ geldiği yazılır
    (``last_seen_at``) ve aday sessizce düşer; ret süresi dolmuşsa silinir, aday yeni sayılır."""
    now = now or datetime.now(UTC)
    purge_expired(state, now)
    rej = _find_rejection(state, symbol, side, timeframe)
    if rej is not None:
        if rejection_active(rej, now):
            rej.last_seen_at = now.isoformat()
            return None
        state.rejected_signals = [r for r in state.rejected_signals if r is not rej]
        audit.record(
            "MANUAL_READY_REJECTION_LAPSED", symbol=symbol, timeframe=timeframe, side=side,
            reason=f"rejected_at:{rej.rejected_at}",
        )
    if _find_ready(state, symbol, side, timeframe) is not None:
        return None
    requested_at = now.isoformat()
    entry = ManualReady(
        id=_make_id(symbol, timeframe, side, requested_at),
        symbol=symbol,
        timeframe=timeframe,
        side=side,
        requested_at=requested_at,
        size_multiplier=size_multiplier,
        requested_price=requested_price,
        reason=reason,
        fingerprint=fingerprint,
        snapshot_id=snapshot_id,
        signal_id=signal_id,
        decision_id=decision_id,
        news_setup_id=news_setup_id,
        news_event_id=news_event_id,
        news_evidence_id=news_evidence_id,
    )
    state.manual_ready.append(entry)
    audit.record(
        "MANUAL_READY_QUEUED", position_id=entry.id, symbol=symbol, timeframe=timeframe,
        side=side, reason=reason, fingerprint=fingerprint, snapshot_id=snapshot_id,
        signal_id=signal_id, decision_id=decision_id, news_setup_id=news_setup_id,
        news_event_id=news_event_id, news_evidence_id=news_evidence_id,
    )
    return entry


def dismiss(state: PaperState, manual_id: str) -> bool:
    """Remove a queued candidate (no rejection recorded — may re-queue next tick)."""
    entry = _find_ready_by_id(state, manual_id)
    if entry is None:
        return False
    state.manual_ready = [m for m in state.manual_ready if m.id != manual_id]
    audit.record(
        "MANUAL_READY_DISMISSED", position_id=manual_id, symbol=entry.symbol,
        timeframe=entry.timeframe, side=entry.side,
    )
    return True


def reject(state: PaperState, manual_id: str) -> bool:
    """Owner rejects a candidate: remove it AND record a RejectedSignal so the same
    (symbol, side, timeframe) is silently blocked from re-queueing."""
    entry = _find_ready_by_id(state, manual_id)
    if entry is None:
        return False
    state.manual_ready = [m for m in state.manual_ready if m.id != manual_id]
    now_iso = datetime.now(UTC).isoformat()
    existing = _find_rejection(state, entry.symbol, entry.side, entry.timeframe)
    if existing is None:
        state.rejected_signals.append(
            RejectedSignal(
                symbol=entry.symbol, timeframe=entry.timeframe, side=entry.side,
                rejected_at=now_iso, fingerprint=entry.fingerprint, last_seen_at=now_iso,
            )
        )
    else:
        existing.rejected_at = now_iso
        existing.last_seen_at = now_iso
    audit.record(
        "MANUAL_READY_REJECTED", position_id=manual_id, symbol=entry.symbol,
        timeframe=entry.timeframe, side=entry.side,
    )
    return True


def _clear_key(state: PaperState, symbol: str, side: str, timeframe: str) -> None:
    state.manual_ready = [
        m for m in state.manual_ready
        if not (m.symbol == symbol and m.side == side and m.timeframe == timeframe)
    ]
    state.rejected_signals = [
        r for r in state.rejected_signals
        if not (r.symbol == symbol and r.side == side and r.timeframe == timeframe)
    ]


def approve(
    state: PaperState,
    manual_id: str,
    *,
    current_price: float | None,
    risk_input: RiskInput,
    catalysts: list,
    atr: float | None = None,
    now: datetime | None = None,
) -> dict:
    """Owner approves: open the position — but queue membership does NOT pre-authorize.

    Eskimiş aday açılmaz (``blocked``/``expired``, kuyruktan çıkar). The canonical
    RiskGate is ALWAYS re-evaluated at approval time (`risk_input` and the snapshot's
    `catalysts` are required, F4): DQS, daily-loss, drawdown, any active halt and the
    high-impact event window can still block the open. Açılış yalnız GÜNCEL fiyatla yapılır (kuyruk fiyatına düşülmez); fiyat
    kuyruk fiyatından ``LATE_PRICE_ATR`` ATR'den fazla kaçtıysa ``price_moved``. The open
    then goes through the guarded `attempt_open` (price sanity / state anomaly /
    duplicate). On success, clears the queued + rejected records for that key.

    Returns {"status": opened|not_found|no_price|blocked, ...}."""
    now = now or datetime.now(UTC)
    entry = _find_ready_by_id(state, manual_id)
    if entry is None:
        return {"status": "not_found"}
    if is_expired(entry, now):
        state.manual_ready = [m for m in state.manual_ready if m.id != manual_id]
        audit.record(
            "MANUAL_READY_EXPIRED", position_id=manual_id, symbol=entry.symbol,
            timeframe=entry.timeframe, side=entry.side, reason="approve_after_expiry",
        )
        return {"status": "blocked", "reason": "expired"}
    # Rule: re-run the canonical RiskGate/DQS/KillSwitch before opening.
    open_dqs = risk_input.dqs_score
    rg = evaluate_for_open(risk_input, catalysts, now=now)
    open_risk_action: str | None = rg.action
    if rg.action in _RISK_BLOCKS_NEW_OPEN:
        audit.record(
            "MANUAL_READY_BLOCKED", position_id=manual_id, symbol=entry.symbol,
            timeframe=entry.timeframe, side=entry.side, reason=f"risk_gate:{rg.action}",
        )
        return {"status": "blocked", "reason": f"risk_gate:{rg.action}"}
    price = current_price
    if price is None or not math.isfinite(price) or price <= 0:
        return {"status": "no_price"}
    ref = entry.requested_price
    if atr is not None and math.isfinite(atr) and atr > 0 and ref is not None and math.isfinite(ref) and ref > 0:
        drift = abs(price - ref) / atr
        if drift > LATE_PRICE_ATR:
            reason = f"price_moved:{drift:.2f}atr"
            audit.record(
                "MANUAL_READY_BLOCKED", position_id=manual_id, symbol=entry.symbol,
                timeframe=entry.timeframe, side=entry.side, reason=reason,
            )
            return {"status": "blocked", "reason": reason}
    pos, decision = attempt_open(
        state,
        symbol=entry.symbol,
        side=entry.side,
        entry_price=price,
        size_multiplier=entry.size_multiplier,
        timeframe=entry.timeframe,
        open_reason=f"owner_approved:{entry.reason or ''}",
        snapshot_id=entry.snapshot_id,
        signal_id=entry.signal_id,
        decision_id=entry.decision_id,
        news_setup_id=entry.news_setup_id,
        news_event_id=entry.news_event_id,
        news_evidence_id=entry.news_evidence_id,
        fingerprint=entry.fingerprint,
        open_dqs=open_dqs,
        open_risk_action=open_risk_action,
    )
    if pos is None:
        return {"status": "blocked", "reason": decision.get("reason")}
    _clear_key(state, entry.symbol, entry.side, entry.timeframe)
    audit.record(
        "MANUAL_READY_APPROVED", position_id=pos.id, symbol=entry.symbol,
        timeframe=entry.timeframe, side=entry.side, price_used=price,
        snapshot_id=pos.snapshot_id, signal_id=pos.signal_id,
        decision_id=pos.decision_id, news_setup_id=pos.news_setup_id,
        news_event_id=pos.news_event_id, news_evidence_id=pos.news_evidence_id,
    )
    return {"status": "opened", "position_id": pos.id, "price": price}


def purge_stale_rejection(state: PaperState, symbol: str, side: str, timeframe: str) -> None:
    """Drop a rejection only if no queued candidate keeps it relevant (different tf
    with an active queue keeps the block consistent)."""
    if _find_ready(state, symbol, side, timeframe) is not None:
        return
    state.rejected_signals = [
        r for r in state.rejected_signals
        if not (r.symbol == symbol and r.side == side and r.timeframe == timeframe)
    ]
