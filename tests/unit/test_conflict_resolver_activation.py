"""Faz 7 — conflict_resolver_activation.py guard testleri (INERT by default).

`shadow.affect_decision`'dan TAMAMEN BAĞIMSIZ bir kapı: enabled=false
(varsayılan) olduğu sürece activate() her zaman boş liste döner. Aktif
olduğunda sadece CANDIDATE_OPEN sembolleri manual_ready'e kuyruklar, asla
otomatik açmaz, size her zaman ≤1.0 clamp'li.
"""
from __future__ import annotations

from types import SimpleNamespace

from packages.decision import conflict_resolver, conflict_resolver_activation as cra
from packages.paper.state import PaperState

_ON = cra.ConflictActivationConfig(enabled=True)
_OFF = cra.ConflictActivationConfig(enabled=False)


def _view(symbol="BTCUSD", *, entry_tf="1h", size=0.5):
    return SimpleNamespace(
        symbol=symbol,
        decision=SimpleNamespace(entry_timeframe=entry_tf, size_multiplier=size),
    )


def _state():
    return PaperState(equity_usd=10_000.0, peak_equity_usd=10_000.0)


def _eval_returning(action, *, setup_type="TREND_LONG", direction="LONG"):
    def _fn(view, *, fingerprint=None, risk_action=None, dqs_status="OK"):
        return {
            "setup_type": setup_type,
            "setup_direction": direction,
            "conflict_final_action": action,
        }
    return _fn


def _activate(state, views, *, cfg=_ON, evaluate_fn=None):
    return cra.activate(
        state,
        ["BTCUSD"],
        risk_action="HOLD",
        dqs_status="OK",
        prices={"BTCUSD": 100.0},
        snapshot_id="snap-1",
        cfg=cfg,
        build_views=lambda symbols, *, risk_action=None: views,
        evaluate_fn=evaluate_fn,
    )


def test_noop_when_disabled_by_default():
    st = _state()
    q = _activate(st, [_view()], cfg=_OFF, evaluate_fn=_eval_returning(conflict_resolver.CANDIDATE_OPEN))
    assert q == []
    assert st.manual_ready == []


def test_candidate_open_queues_to_manual_ready():
    st = _state()
    q = _activate(st, [_view(entry_tf="1h", size=0.5)], evaluate_fn=_eval_returning(conflict_resolver.CANDIDATE_OPEN))
    assert len(q) == 1
    assert len(st.manual_ready) == 1
    m = st.manual_ready[0]
    assert (m.symbol, m.side, m.timeframe, m.size_multiplier) == ("BTCUSD", "long", "1h", 0.5)
    assert m.reason == "conflict_resolver_activation:TREND_LONG"
    # hard invariant: nothing auto-opens
    assert st.open_positions == []


def test_short_direction_maps_to_short_side():
    st = _state()
    q = _activate(
        st, [_view()],
        evaluate_fn=_eval_returning(conflict_resolver.CANDIDATE_OPEN, setup_type="TREND_SHORT", direction="SHORT"),
    )
    assert q[0]["side"] == "short" if q else False
    assert st.manual_ready[0].side == "short"


def test_no_trade_does_not_queue():
    st = _state()
    q = _activate(st, [_view()], evaluate_fn=_eval_returning(conflict_resolver.NO_TRADE))
    assert q == []


def test_watch_does_not_queue():
    st = _state()
    q = _activate(st, [_view()], evaluate_fn=_eval_returning(conflict_resolver.WATCH))
    assert q == []


def test_blocked_does_not_queue():
    st = _state()
    q = _activate(st, [_view()], evaluate_fn=_eval_returning(conflict_resolver.BLOCKED))
    assert q == []


def test_zero_size_skips():
    st = _state()
    q = _activate(st, [_view(size=0.0)], evaluate_fn=_eval_returning(conflict_resolver.CANDIDATE_OPEN))
    assert q == []


def test_size_clamped_to_one():
    st = _state()
    q = _activate(st, [_view(size=2.5)], evaluate_fn=_eval_returning(conflict_resolver.CANDIDATE_OPEN))
    assert st.manual_ready[0].size_multiplier == 1.0


def test_missing_entry_timeframe_skips():
    st = _state()
    q = _activate(st, [_view(entry_tf=None)], evaluate_fn=_eval_returning(conflict_resolver.CANDIDATE_OPEN))
    assert q == []


def test_duplicate_is_silently_deduped():
    st = _state()
    fn = _eval_returning(conflict_resolver.CANDIDATE_OPEN)
    first = _activate(st, [_view()], evaluate_fn=fn)
    second = _activate(st, [_view()], evaluate_fn=fn)
    assert len(first) == 1
    assert second == []  # aynı (symbol, side, timeframe) zaten kuyrukta
    assert len(st.manual_ready) == 1
