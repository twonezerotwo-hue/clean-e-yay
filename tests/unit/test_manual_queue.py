"""Phase 2b — manual-ready / rejected-signal workflow tests (ported from e-yay-codex).

Acceptance:
- DEFENSIVE/CRISIS candidate is queued, not auto-opened;
- the same (symbol, side, timeframe) does not spam (silent block, fingerprint-independent);
- a different timeframe/direction is a new candidate (recurring);
- owner approve opens via the guarded path and clears the queue;
- reject records a rejection (silent-blocks re-queue); dismiss just removes.
"""
from __future__ import annotations

import pytest

from packages.paper import manual_queue
from packages.paper import state as paper_state
from packages.paper.state import ManualReady, RejectedSignal


@pytest.fixture
def st(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    return paper_state._initial_state()


def _queue(st, *, symbol="BTCUSD", side="long", tf="1d", price=60_000.0, fp="fp-a"):
    return manual_queue.route_to_manual_ready(
        st, symbol=symbol, timeframe=tf, side=side, size_multiplier=1.0,
        requested_price=price, reason="defensive", fingerprint=fp, snapshot_id="snap-1",
    )


# ---------- routing + anti-spam ----------

def test_route_queues_candidate(st) -> None:
    entry = _queue(st)
    assert entry is not None
    assert len(st.manual_ready) == 1
    assert st.manual_ready[0].symbol == "BTCUSD" and st.manual_ready[0].side == "long"


def test_same_signal_is_silently_blocked(st) -> None:
    assert _queue(st) is not None
    # Same (symbol, side, tf) → silent block, no duplicate queue entry.
    assert _queue(st) is None
    assert len(st.manual_ready) == 1


def test_silent_block_survives_fingerprint_drift(st) -> None:
    assert _queue(st, fp="btc|60|aligned") is not None
    # Totally different fingerprint, same symbol+side+tf → still blocked.
    assert manual_queue.should_silent_block(st, "BTCUSD", "long", "1d") is True
    assert _queue(st, fp="btc|61|shifted") is None


def test_different_timeframe_is_new_candidate(st) -> None:
    assert _queue(st, tf="1d") is not None
    assert _queue(st, tf="4h") is not None  # different tf → not blocked
    assert len(st.manual_ready) == 2


def test_is_recurring_signal(st) -> None:
    _queue(st, side="long", tf="1d")
    assert manual_queue.is_recurring_signal(st, "BTCUSD", "long", "4h") is True   # diff tf
    assert manual_queue.is_recurring_signal(st, "BTCUSD", "short", "1d") is True  # diff side
    assert manual_queue.is_recurring_signal(st, "BTCUSD", "long", "1d") is False  # same
    assert manual_queue.is_recurring_signal(st, "ETHUSD", "long", "1d") is False  # none


# ---------- owner actions ----------

def test_dismiss_removes_only(st) -> None:
    entry = _queue(st)
    assert manual_queue.dismiss(st, entry.id) is True
    assert st.manual_ready == []
    assert st.rejected_signals == []                 # no rejection recorded
    assert manual_queue.dismiss(st, entry.id) is False  # already gone
    # dismissed → not blocked → can re-queue
    assert _queue(st) is not None


def test_reject_records_rejection_and_blocks(st) -> None:
    entry = _queue(st)
    assert manual_queue.reject(st, entry.id) is True
    assert st.manual_ready == []
    assert len(st.rejected_signals) == 1
    # rejected → re-queue is silently blocked
    assert manual_queue.should_silent_block(st, "BTCUSD", "long", "1d") is True
    assert _queue(st) is None


def test_approve_opens_and_clears(st) -> None:
    entry = _queue(st, price=60_000.0)
    res = manual_queue.approve(st, entry.id, current_price=60_000.0)
    assert res["status"] == "opened"
    assert len(st.open_positions) == 1
    assert st.open_positions[0].symbol == "BTCUSD"
    # queue + any rejection cleared for that key
    assert st.manual_ready == []
    assert manual_queue.should_silent_block(st, "BTCUSD", "long", "1d") is False


def test_approve_not_found_and_no_price(st) -> None:
    assert manual_queue.approve(st, "missing", current_price=60_000.0)["status"] == "not_found"
    entry = _queue(st, price=None)
    assert manual_queue.approve(st, entry.id, current_price=None)["status"] == "no_price"


def test_approve_blocked_by_price_guard(st) -> None:
    """Owner approval still passes through the guards — contaminated price is blocked."""
    entry = _queue(st, price=None)
    res = manual_queue.approve(st, entry.id, current_price=30.0)  # silver-like contamination
    assert res["status"] == "blocked"
    assert res["reason"] == "price_insane"
    assert len(st.open_positions) == 0
    assert len(st.manual_ready) == 1  # stays queued


# ---------- purge ----------

def test_purge_preserves_while_queued(st) -> None:
    st.rejected_signals.append(
        RejectedSignal(symbol="BTCUSD", timeframe="1d", side="long", rejected_at="t")
    )
    st.manual_ready.append(
        ManualReady(id="x", symbol="BTCUSD", timeframe="1d", side="long",
                    requested_at="t", size_multiplier=1.0)
    )
    manual_queue.purge_stale_rejection(st, "BTCUSD", "long", "1d")
    assert len(st.rejected_signals) == 1  # queue present → keep

    st.manual_ready.clear()
    manual_queue.purge_stale_rejection(st, "BTCUSD", "long", "1d")
    assert st.rejected_signals == []      # no queue → purge


def test_state_roundtrip_preserves_queue(st) -> None:
    _queue(st)
    st.rejected_signals.append(
        RejectedSignal(symbol="ETHUSD", timeframe="4h", side="short", rejected_at="t")
    )
    restored = paper_state.PaperState.from_dict(st.to_dict())
    assert len(restored.manual_ready) == 1
    assert len(restored.rejected_signals) == 1
    assert restored.manual_ready[0].symbol == "BTCUSD"
