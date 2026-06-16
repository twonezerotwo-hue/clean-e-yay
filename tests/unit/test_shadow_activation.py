"""Step 9 Phase B — shadow activation guard tests (INERT by default).

Pin the activation invariants: it is a no-op unless BOTH flags are set; when active it
routes entry decisions to manual_ready ONLY (never auto-opens a position); upper-TF size
is clamped to ≤ 1.0; side comes from the consensus direction; and the manual_ready
anti-spam de-dupe holds. RiskGate stays final — it re-runs at owner approval, not here.
"""
from __future__ import annotations

from types import SimpleNamespace

from packages.decision import shadow, shadow_activation
from packages.paper.state import PaperState

_ON = shadow.ShadowConfig(enabled=True, affect_decision=True)
_OFF = shadow.ShadowConfig(enabled=True, affect_decision=False)


def _view(symbol="BTCUSD", *, action="SCOUT_ALLOWED", direction=70.0, entry_tf="1h", size=0.5):
    return SimpleNamespace(
        symbol=symbol,
        decision=SimpleNamespace(action=action, entry_timeframe=entry_tf, size_multiplier=size),
        consensus=SimpleNamespace(direction_score=direction),
    )


def _state():
    return PaperState(equity_usd=10_000.0, peak_equity_usd=10_000.0)


def _activate(state, views, *, cfg=_ON):
    return shadow_activation.activate(
        state,
        ["BTCUSD"],
        risk_action="HOLD",
        prices={"BTCUSD": 100.0, "ETHUSD": 50.0},
        snapshot_id="snap-1",
        cfg=cfg,
        build_views=lambda symbols, *, risk_action=None: views,
    )


# ── gated no-op (the shipped default keeps this inert) ────────────────────────

def test_activate_noop_when_affect_decision_false():
    st = _state()
    assert _activate(st, [_view()], cfg=_OFF) == []
    assert st.manual_ready == []


def test_activate_noop_when_disabled():
    st = _state()
    cfg = shadow.ShadowConfig(enabled=False, affect_decision=True)
    assert _activate(st, [_view()], cfg=cfg) == []
    assert st.manual_ready == []


# ── when active: queue to manual_ready ONLY, never auto-open ───────────────────

def test_activate_routes_entry_to_manual_ready():
    st = _state()
    q = _activate(st, [_view(action="SCOUT_ALLOWED", direction=70, entry_tf="1h", size=0.5)])
    assert len(q) == 1
    assert len(st.manual_ready) == 1
    m = st.manual_ready[0]
    assert (m.symbol, m.side, m.timeframe, m.size_multiplier) == ("BTCUSD", "long", "1h", 0.5)
    assert m.reason == "shadow_activation:SCOUT_ALLOWED"
    # the hard invariant: nothing is auto-opened
    assert st.open_positions == []


def test_activate_confirmation_required_also_queues():
    st = _state()
    assert len(_activate(st, [_view(action="CONFIRMATION_REQUIRED")])) == 1


def test_activate_skips_non_entry_actions():
    st = _state()
    q = _activate(st, [_view(action="WATCH"), _view(symbol="ETHUSD", action="NO_TRADE")])
    assert q == []
    assert st.manual_ready == []


def test_activate_side_from_consensus_direction():
    st = _state()
    _activate(st, [_view(direction=30.0)])  # bearish consensus → short
    assert st.manual_ready[0].side == "short"


# ── upper-TF only scales DOWN (clamp ≤ 1.0; never boost) ──────────────────────

def test_activate_caps_size_at_one():
    st = _state()
    _activate(st, [_view(size=1.5)])  # defensive clamp — shadow never boosts size
    assert st.manual_ready[0].size_multiplier == 1.0


def test_activate_skips_zero_size():
    st = _state()
    assert _activate(st, [_view(size=0.0)]) == []
    assert st.manual_ready == []


def test_activate_skips_missing_entry_timeframe():
    st = _state()
    assert _activate(st, [_view(entry_tf=None)]) == []


# ── anti-spam: same (symbol, side, timeframe) de-dupes ────────────────────────

def test_activate_dedupes_same_key():
    st = _state()
    v = _view()
    _activate(st, [v])
    second = _activate(st, [v])  # already queued → silently blocked
    assert second == []
    assert len(st.manual_ready) == 1
