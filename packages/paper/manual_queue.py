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
  - reject  → remove from queue AND record a RejectedSignal so it stops re-appearing.
  - dismiss → remove from queue only (may re-queue next tick).

PAPER_SAFE / NO_EXECUTION: no real orders; approval opens a paper position only.
"""
from __future__ import annotations

import hashlib

from packages.paper import audit
from packages.paper.lifecycle import attempt_open
from packages.paper.state import ManualReady, PaperState, RejectedSignal, utc_iso
from packages.risk.engine import RiskInput
from packages.risk.engine import evaluate as evaluate_risk

# Canonical RiskGate actions that forbid opening a NEW position (mirror of the
# decision engine: KILL_SWITCH→blocked, RISK_REDUCE/NO_POSITION_INCREASE→hold).
_RISK_BLOCKS_NEW_OPEN = {"KILL_SWITCH", "RISK_REDUCE", "NO_POSITION_INCREASE"}


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


def should_silent_block(state: PaperState, symbol: str, side: str, timeframe: str) -> bool:
    """True if this exact (symbol, side, timeframe) is already queued or rejected.

    Fingerprint-independent: a re-scored variant of the same signal must not spam.
    """
    return (
        _find_rejection(state, symbol, side, timeframe) is not None
        or _find_ready(state, symbol, side, timeframe) is not None
    )


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
) -> ManualReady | None:
    """Queue a candidate for owner approval. Returns the entry, or None if silently
    blocked (already queued/rejected — no spam)."""
    if should_silent_block(state, symbol, side, timeframe):
        return None
    requested_at = utc_iso()
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
    )
    state.manual_ready.append(entry)
    audit.record(
        "MANUAL_READY_QUEUED", position_id=entry.id, symbol=symbol, timeframe=timeframe,
        side=side, reason=reason, fingerprint=fingerprint, snapshot_id=snapshot_id,
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
    if _find_rejection(state, entry.symbol, entry.side, entry.timeframe) is None:
        state.rejected_signals.append(
            RejectedSignal(
                symbol=entry.symbol, timeframe=entry.timeframe, side=entry.side,
                rejected_at=utc_iso(), fingerprint=entry.fingerprint,
            )
        )
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
    risk_input: RiskInput | None = None,
) -> dict:
    """Owner approves: open the position — but queue membership does NOT pre-authorize.

    When `risk_input` is supplied (the API always supplies it), the canonical RiskGate
    is re-evaluated at approval time: DQS, daily-loss, drawdown and any active
    KILL_SWITCH halt can still block the open. The open then goes through the guarded
    `attempt_open` (price sanity / state anomaly / duplicate). On success, clears the
    queued + rejected records for that key.

    Returns {"status": opened|not_found|no_price|blocked, ...}."""
    entry = _find_ready_by_id(state, manual_id)
    if entry is None:
        return {"status": "not_found"}
    # Rule: re-run the canonical RiskGate/DQS/KillSwitch before opening.
    if risk_input is not None:
        rg = evaluate_risk(risk_input)
        if rg.action in _RISK_BLOCKS_NEW_OPEN:
            audit.record(
                "MANUAL_READY_BLOCKED", position_id=manual_id, symbol=entry.symbol,
                timeframe=entry.timeframe, side=entry.side, reason=f"risk_gate:{rg.action}",
            )
            return {"status": "blocked", "reason": f"risk_gate:{rg.action}"}
    price = current_price if current_price is not None else entry.requested_price
    if price is None or price <= 0:
        return {"status": "no_price"}
    pos, decision = attempt_open(
        state,
        symbol=entry.symbol,
        side=entry.side,
        entry_price=price,
        size_multiplier=entry.size_multiplier,
        timeframe=entry.timeframe,
        open_reason=f"owner_approved:{entry.reason or ''}",
        snapshot_id=entry.snapshot_id,
        fingerprint=entry.fingerprint,
    )
    if pos is None:
        return {"status": "blocked", "reason": decision.get("reason")}
    _clear_key(state, entry.symbol, entry.side, entry.timeframe)
    audit.record(
        "MANUAL_READY_APPROVED", position_id=pos.id, symbol=entry.symbol,
        timeframe=entry.timeframe, side=entry.side, price_used=price,
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
