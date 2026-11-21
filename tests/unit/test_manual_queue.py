"""Phase 2b — manual-ready / rejected-signal workflow tests (ported from e-yay-codex).

Acceptance:
- DEFENSIVE/CRISIS candidate is queued, not auto-opened;
- the same (symbol, side, timeframe) does not spam (silent block, fingerprint-independent);
- a different timeframe/direction is a new candidate (recurring);
- owner approve opens via the guarded path and clears the queue;
- reject records a rejection (silent-blocks re-queue); dismiss just removes.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.paper import manual_queue
from packages.paper import state as paper_state
from packages.paper.state import ManualReady, RejectedSignal

# Dilim-0 — approve→attempt_open yolu OHLCV referans kapısından geçer (conftest seed).
pytestmark = pytest.mark.usefixtures("seed_ohlcv_reference")


@pytest.fixture
def st(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    return paper_state._initial_state()


def _risk(dqs: float = 90.0):
    from packages.risk.engine import RiskInput
    return RiskInput(
        dqs_score=dqs, equity_usd=100_000.0, peak_equity_usd=100_000.0,
        daily_pnl_usd=0.0, open_position_count=0,
    )


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
    res = manual_queue.approve(st, entry.id, risk_input=_risk(), catalysts=[], current_price=60_000.0)
    assert res["status"] == "opened"
    assert len(st.open_positions) == 1
    assert st.open_positions[0].symbol == "BTCUSD"
    # queue + any rejection cleared for that key
    assert st.manual_ready == []
    assert manual_queue.should_silent_block(st, "BTCUSD", "long", "1d") is False


def test_approve_not_found_and_no_price(st) -> None:
    assert manual_queue.approve(st, "missing", risk_input=_risk(), catalysts=[], current_price=60_000.0)["status"] == "not_found"
    entry = _queue(st, price=None)
    assert manual_queue.approve(st, entry.id, risk_input=_risk(), catalysts=[], current_price=None)["status"] == "no_price"


def test_approve_blocked_by_price_guard(st) -> None:
    """Owner approval still passes through the guards — contaminated price is blocked."""
    entry = _queue(st, price=None)
    res = manual_queue.approve(st, entry.id, risk_input=_risk(), catalysts=[], current_price=30.0)  # silver-like contamination
    assert res["status"] == "blocked"
    assert res["reason"] == "price_insane"
    assert len(st.open_positions) == 0
    assert len(st.manual_ready) == 1  # stays queued


def test_approve_reruns_riskgate_and_blocks(st) -> None:
    """Queue membership is NOT pre-authorization: DQS<55 → RiskGate KILL_SWITCH blocks."""
    entry = _queue(st, price=60_000.0)
    res = manual_queue.approve(st, entry.id, current_price=60_000.0, catalysts=[], risk_input=_risk(dqs=40.0))
    assert res["status"] == "blocked"
    assert res["reason"].startswith("risk_gate:")
    assert len(st.open_positions) == 0
    assert len(st.manual_ready) == 1  # stays queued


def test_approve_opens_when_riskgate_open(st) -> None:
    entry = _queue(st, price=60_000.0)
    res = manual_queue.approve(st, entry.id, current_price=60_000.0, catalysts=[], risk_input=_risk(dqs=90.0))
    assert res["status"] == "opened"
    assert len(st.open_positions) == 1


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


# ---------- kuyruk ömrü, ret süresi, geç onay (karar-destek adım 1) ----------

_T0 = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def _queue_at(st, when, *, tf="1h", price=60_000.0, side="long"):
    return manual_queue.route_to_manual_ready(
        st, symbol="BTCUSD", timeframe=tf, side=side, size_multiplier=1.0,
        requested_price=price, reason="defensive", now=when,
    )


@pytest.mark.parametrize(("tf", "bar"), [("15m", 15), ("1h", 60), ("4h", 240), ("1d", 1440)])
def test_entry_lives_exactly_one_bar(st, tf, bar) -> None:
    entry = _queue_at(st, _T0, tf=tf)
    assert manual_queue.active(st, _T0 + timedelta(minutes=bar - 1)) == [entry]
    assert manual_queue.active(st, _T0 + timedelta(minutes=bar)) == []
    assert manual_queue.is_expired(entry, _T0 + timedelta(minutes=bar)) is True


def test_unreadable_timestamp_counts_as_expired(st) -> None:
    st.manual_ready.append(
        ManualReady(id="x", symbol="BTCUSD", timeframe="1h", side="long", requested_at="t", size_multiplier=1.0)
    )
    assert manual_queue.active(st, _T0) == []


def test_expired_entry_no_longer_blocks_and_is_replaced(st) -> None:
    """Eskiden: 6 haftalık aday aynı anahtarı kalıcı engelliyordu."""
    old = _queue_at(st, _T0, price=60_000.0)
    later = _T0 + timedelta(hours=1, minutes=5)
    assert manual_queue.should_silent_block(st, "BTCUSD", "long", "1h", later) is False
    fresh = _queue_at(st, later, price=61_000.0)
    assert fresh is not None and fresh.id != old.id
    assert [m.id for m in st.manual_ready] == [fresh.id]  # eskisi çıktı
    assert fresh.requested_price == 61_000.0


def test_purge_expired_keeps_live_entries(st) -> None:
    _queue_at(st, _T0, tf="1h")
    live = _queue_at(st, _T0, tf="1d")
    assert manual_queue.purge_expired(st, _T0 + timedelta(hours=2)) == 1
    assert st.manual_ready == [live]


def test_rejection_holds_while_signal_keeps_coming(st) -> None:
    entry = _queue_at(st, _T0)
    assert manual_queue.reject(st, entry.id) is True
    rej = st.rejected_signals[0]
    rej.rejected_at = rej.last_seen_at = _T0.isoformat()
    # Sinyal her 30 dakikada geliyor → ret sürer, 3 saat sonra bile.
    for minutes in range(30, 181, 30):
        assert _queue_at(st, _T0 + timedelta(minutes=minutes)) is None
    assert st.manual_ready == [] and len(st.rejected_signals) == 1


def test_rejection_lapses_after_one_bar_gap(st) -> None:
    entry = _queue_at(st, _T0)
    manual_queue.reject(st, entry.id)
    rej = st.rejected_signals[0]
    rej.rejected_at = rej.last_seen_at = _T0.isoformat()
    back = _queue_at(st, _T0 + timedelta(hours=1, minutes=1))  # bir bar görünmedi → yeni aday
    assert back is not None
    assert st.rejected_signals == []


def test_approve_after_expiry_is_blocked_and_removed(st) -> None:
    entry = _queue_at(st, _T0)
    res = manual_queue.approve(st, entry.id, risk_input=_risk(), catalysts=[], current_price=60_000.0, now=_T0 + timedelta(hours=1))
    assert res == {"status": "blocked", "reason": "expired"}
    assert st.manual_ready == [] and st.open_positions == []


def test_approve_never_falls_back_to_queued_price(st) -> None:
    entry = _queue_at(st, datetime.now(UTC), price=60_000.0)
    assert manual_queue.approve(st, entry.id, risk_input=_risk(), catalysts=[], current_price=None)["status"] == "no_price"
    assert manual_queue.approve(st, entry.id, risk_input=_risk(), catalysts=[], current_price=float("nan"))["status"] == "no_price"
    assert st.open_positions == []


def test_approve_blocks_when_price_ran_away(st) -> None:
    entry = _queue_at(st, datetime.now(UTC), price=60_000.0)
    res = manual_queue.approve(st, entry.id, risk_input=_risk(), catalysts=[], current_price=60_600.0, atr=1_000.0)  # 0,6 ATR
    assert res["status"] == "blocked" and res["reason"] == "price_moved:0.60atr"
    assert st.open_positions == [] and len(st.manual_ready) == 1


def test_approve_opens_within_late_price_limit(st) -> None:
    entry = _queue_at(st, datetime.now(UTC), price=60_000.0)
    res = manual_queue.approve(st, entry.id, risk_input=_risk(), catalysts=[], current_price=60_400.0, atr=1_000.0)  # 0,4 ATR
    assert res["status"] == "opened"
    assert len(st.open_positions) == 1


def test_state_roundtrip_preserves_queue(st) -> None:
    _queue(st)
    st.rejected_signals.append(
        RejectedSignal(symbol="ETHUSD", timeframe="4h", side="short", rejected_at="t")
    )
    restored = paper_state.PaperState.from_dict(st.to_dict())
    assert len(restored.manual_ready) == 1
    assert len(restored.rejected_signals) == 1
    assert restored.manual_ready[0].symbol == "BTCUSD"


def test_state_roundtrip_keeps_rejection_last_seen(st) -> None:
    st.rejected_signals.append(
        RejectedSignal(symbol="ETHUSD", timeframe="4h", side="short", rejected_at="t", last_seen_at="s")
    )
    restored = paper_state.PaperState.from_dict(st.to_dict())
    assert restored.rejected_signals[0].last_seen_at == "s"
    # Eski kayıt (alan yok) okunur, None gelir.
    legacy = st.to_dict()
    legacy["rejected_signals"] = [{"symbol": "X", "timeframe": "1h", "side": "long", "rejected_at": "t"}]
    assert paper_state.PaperState.from_dict(legacy).rejected_signals[0].last_seen_at is None


# ---------- HTTP endpoints (thin router; logic lives in manual_queue) ----------

@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(paper_state, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    from apps.api.main import app

    return TestClient(app)


def _seed_queue(symbol="BTCUSD", side="long", tf="1d") -> str:
    s = paper_state.load()
    manual_queue.route_to_manual_ready(
        s, symbol=symbol, timeframe=tf, side=side, size_multiplier=1.0,
        requested_price=60_000.0, reason="defensive",
    )
    paper_state.save(s)
    return s.manual_ready[0].id


def test_get_manual_ready_endpoint(api) -> None:
    mid = _seed_queue()
    r = api.get("/api/v1/paper-trading/manual-ready")
    assert r.status_code == 200
    body = r.json()
    assert len(body["manual_ready"]) == 1
    assert body["manual_ready"][0]["id"] == mid
    assert body["rejected_count"] == 0


def test_get_endpoint_hides_expired_and_counts_live_only(api) -> None:
    s = paper_state.load()
    s.manual_ready.append(
        ManualReady(id="old", symbol="ETHUSD", timeframe="1h", side="short",
                    requested_at="2026-10-01T07:21:13+00:00", size_multiplier=1.0)
    )
    s.rejected_signals.append(
        RejectedSignal(symbol="NVDA", timeframe="1h", side="long", rejected_at="2026-09-30T23:01:32+00:00")
    )
    paper_state.save(s)
    mid = _seed_queue()
    body = api.get("/api/v1/paper-trading/manual-ready").json()
    assert [m["id"] for m in body["manual_ready"]] == [mid]
    assert body["rejected_count"] == 0
    assert api.get("/api/v1/paper-trading/state").json()["manual_ready_count"] == 1


def test_dismiss_endpoint(api) -> None:
    mid = _seed_queue()
    r = api.post(f"/api/v1/paper-trading/manual-ready/{mid}/dismiss")
    assert r.status_code == 200 and r.json()["status"] == "dismissed"
    assert paper_state.load().manual_ready == []
    assert paper_state.load().rejected_signals == []  # dismiss ≠ anti-spam


def test_reject_endpoint_records_block(api) -> None:
    mid = _seed_queue()
    r = api.post(f"/api/v1/paper-trading/manual-ready/{mid}/reject")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    reloaded = paper_state.load()
    assert reloaded.manual_ready == [] and len(reloaded.rejected_signals) == 1


def test_approve_unknown_id_returns_404(api) -> None:
    r = api.post("/api/v1/paper-trading/manual-ready/does-not-exist/approve")
    assert r.status_code == 404


def test_state_endpoint_surfaces_manual_ready_count(api) -> None:
    _seed_queue()
    r = api.get("/api/v1/paper-trading/state")
    assert r.status_code == 200
    assert r.json()["manual_ready_count"] == 1


# ---------- F4 (21 Kasım 2026): olay riski her açılış yolunda ----------

def _cpi_in(hours: float):
    from packages.data.types import Catalyst
    ts = datetime.now(UTC) + timedelta(hours=hours)
    return Catalyst(id="cpi-test", ts=ts, title="CPI", importance="high",
                    verified=True, hours_until=hours, source="test")


def test_approve_is_blocked_inside_event_window(st) -> None:
    entry = _queue(st, price=60_000.0)
    res = manual_queue.approve(st, entry.id, risk_input=_risk(), catalysts=[_cpi_in(2)],
                               current_price=60_000.0)
    assert res == {"status": "blocked", "reason": "risk_gate:NO_POSITION_INCREASE"}
    assert st.open_positions == []


def test_approve_requires_risk_input_and_catalysts(st) -> None:
    entry = _queue(st, price=60_000.0)
    with pytest.raises(TypeError):
        manual_queue.approve(st, entry.id, current_price=60_000.0)  # eski kod: RiskGate'siz açardı


def test_owner_manual_paths_see_event_window(st) -> None:
    from types import SimpleNamespace

    from packages.paper import idea_order, manual_order
    from packages.risk import engine

    assert engine.evaluate_for_open(_risk(), [_cpi_in(2)]).action == "NO_POSITION_INCREASE"
    assert engine.evaluate_for_open(_risk(), []).action == "HOLD"
    snap = SimpleNamespace(quality=SimpleNamespace(score=90.0), catalysts=[_cpi_in(2)])
    blocked = manual_order.risk_block(st, snap)
    assert blocked is not None and "NO_POSITION_INCREASE" in blocked
    snap_clear = SimpleNamespace(quality=SimpleNamespace(score=90.0), catalysts=[])
    assert manual_order.risk_block(st, snap_clear) is None
    # Fikir panosu önizlemesi: tick'in kaydettiği RiskGate kararı (olay riski dahil) kısıtlar.
    latest = {"dqs": {"score": 90.0},
              "risk_state": {"action": "NO_POSITION_INCREASE", "reason": "Olay riski", "evidence": []}}
    assert idea_order._risk_action(st, latest)[0] == "NO_POSITION_INCREASE"
