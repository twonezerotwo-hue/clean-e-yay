"""Tek karar kaynağı (read_model): okuma yüzeyleri tick'in kararını okur.

- Tick aynı görüntü için yayımladıysa karar, rejim ve risk yeniden hesaplanmaz.
- İşlem evrenindeki sembolün konsensüsü kararın kendisinden gelir.
- Evren dışı sembolün konsensüsü tick'in rejimiyle bir kez hesaplanır (önbellekli).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.decision import engine, paper_policy, read_model, tick_artifact


@pytest.fixture
def tick_view(monkeypatch):
    snap = SimpleNamespace(snapshot_id="tick-rm", quality=SimpleNamespace(score=90.0))
    ps = SimpleNamespace(open_positions=[], equity_usd=100_000.0, peak_equity_usd=100_000.0,
                         daily_pnl_usd=0.0, mtm_equity_usd=None)
    symbols = ["BTCUSD", "ETHUSD"]
    monkeypatch.setattr("packages.data.registry.assets.trade_symbols", lambda: symbols)
    monkeypatch.setattr(paper_policy, "enabled", lambda: False)
    regime = SimpleNamespace(label="NEUTRAL")
    risk = SimpleNamespace(action="HOLD")
    decisions = [
        SimpleNamespace(symbol=s, timeframe=tf, consensus=f"cons:{s}:{tf}")
        for s in symbols for tf in ("1d", "4h")
    ]
    tick_artifact.publish(snap, symbols, paper_exploration=False, regime=regime, risk=risk,
                          decisions=decisions)
    monkeypatch.setattr(engine, "decide_matrix", lambda *a, **k: pytest.fail("karar yeniden hesaplandı"))
    yield snap, ps, regime, risk
    tick_artifact.reset()


def test_current_reads_tick_publication_without_recompute(tick_view, monkeypatch):
    snap, ps, regime, risk = tick_view
    monkeypatch.setattr("packages.risk.engine.risk_input_from_state", lambda *a, **k: None)
    dv = read_model.current(snap, ps)
    assert dv.regime is regime and dv.risk is risk and len(dv.decisions) == 4
    assert dv.consensus("ETHUSD", "4h") == "cons:ETHUSD:4h"
    assert dv.source == "tick" and dv.published_age_sec is not None


def test_off_universe_consensus_uses_tick_regime_once(tick_view, monkeypatch):
    snap, ps, regime, _risk = tick_view
    monkeypatch.setattr("packages.risk.engine.risk_input_from_state", lambda *a, **k: None)
    calls = []

    def fake_build(symbol, snap_, regime_, timeframe="1d"):
        calls.append((symbol, timeframe))
        assert regime_ is regime and snap_ is snap
        return f"built:{symbol}"

    monkeypatch.setattr("packages.consensus.engine.build", fake_build)
    dv = read_model.current(snap, ps)
    assert dv.consensus("DXY") == "built:DXY"
    assert dv.consensus("DXY") == "built:DXY"
    assert calls == [("DXY", "1d")]


def test_world_state_reads_tick_publication(monkeypatch):
    snap = SimpleNamespace(snapshot_id="tick-world")
    world = object()
    tick_artifact.publish_world(snap, world)
    monkeypatch.setattr("packages.world_state.engine.build", lambda *a, **k: pytest.fail("yeniden kuruldu"))
    try:
        assert tick_artifact.world_for(snap) is world
    finally:
        tick_artifact.reset()
