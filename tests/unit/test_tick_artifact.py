"""Ekran tick'in karar verdiği anı okur (süreç-içi tek kaynak).

- get_cached_snapshot varsayılan sembol setinde tick'in taze snapshot'ını döner;
  yayın bayatsa ya da özel sembol seti istenirse eski önbellek yolu koşar.
- decide_matrix_for aynı snapshot / sembol / keşif bayrağı için tick'in kararını
  döner, uymazsa yeniden hesaplar.
- /decision/matrix tick yayını varken kararı yeniden hesaplamaz. Hepsi offline.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from packages.data.ingestion import pipeline
from packages.decision import engine, paper_policy, tick_artifact


def test_cached_snapshot_prefers_fresh_tick_snapshot(monkeypatch):
    tick_snap = SimpleNamespace(snapshot_id="tick-1")
    monkeypatch.setattr(pipeline, "build_snapshot", lambda symbols=None: pytest.fail("ikinci snapshot kuruldu"))
    pipeline.publish_tick_snapshot(tick_snap)
    assert pipeline.get_cached_snapshot() is tick_snap


def test_stale_tick_snapshot_falls_back_to_cache(monkeypatch):
    own = SimpleNamespace(snapshot_id="api-1")
    pipeline._CACHE.clear()
    monkeypatch.setattr(pipeline, "build_snapshot", lambda symbols=None: own)
    pipeline._TICK_SNAPSHOT = (time.monotonic() - pipeline._TICK_MAX_AGE_SEC - 1, SimpleNamespace(snapshot_id="old"))
    try:
        assert pipeline.get_cached_snapshot() is own
    finally:
        pipeline._CACHE.clear()


def test_custom_symbol_set_does_not_use_tick_snapshot(monkeypatch):
    own = SimpleNamespace(snapshot_id="api-2")
    pipeline._CACHE.clear()
    monkeypatch.setattr(pipeline, "build_snapshot", lambda symbols=None: own)
    pipeline.publish_tick_snapshot(SimpleNamespace(snapshot_id="tick-2"))
    try:
        assert pipeline.get_cached_snapshot(["BTCUSD"]) is own
    finally:
        pipeline._CACHE.clear()


def test_decide_matrix_for_reuses_matching_tick_decision(monkeypatch):
    snap = SimpleNamespace(snapshot_id="s-1")
    tick_artifact.publish(snap, ["A", "B"], paper_exploration=True, regime="R", risk="K", decisions=["d1", "d2"])
    monkeypatch.setattr(engine, "decide_matrix", lambda *a, **k: pytest.fail("karar yeniden hesaplandı"))
    regime, risk, decisions = tick_artifact.decide_matrix_for(["A", "B"], snap, None, paper_exploration=True)
    assert (regime, risk, decisions) == ("R", "K", ["d1", "d2"])


@pytest.mark.parametrize(
    ("snapshot_id", "symbols", "exploration"),
    [("s-2", ["A", "B"], True), ("s-1", ["A"], True), ("s-1", ["A", "B"], False)],
)
def test_decide_matrix_for_recomputes_on_mismatch(monkeypatch, snapshot_id, symbols, exploration):
    tick_artifact.publish(
        SimpleNamespace(snapshot_id="s-1"), ["A", "B"], paper_exploration=True,
        regime="R", risk="K", decisions=["tick"],
    )
    calls = []
    monkeypatch.setattr(engine, "decide_matrix", lambda *a, **k: calls.append(1) or ("R2", "K2", ["fresh"]))
    out = tick_artifact.decide_matrix_for(
        symbols, SimpleNamespace(snapshot_id=snapshot_id), None, paper_exploration=exploration,
    )
    assert out == ("R2", "K2", ["fresh"]) and calls == [1]


def test_decision_matrix_endpoint_serves_tick_decision(monkeypatch):
    from apps.api.main import app
    from packages.data.registry import assets as asset_registry
    from packages.paper import state as paper_state
    from packages.risk.engine import risk_input_from_state

    snap = pipeline.build_snapshot()
    ps = paper_state.load()
    symbols = asset_registry.trade_symbols()
    exploration = paper_policy.enabled()
    regime, risk, decisions = engine.decide_matrix(
        symbols, snap, risk_input_from_state(ps, snap.quality.score),
        open_positions=ps.open_positions, paper_exploration=exploration,
    )
    pipeline.publish_tick_snapshot(snap)
    tick_artifact.publish(snap, symbols, paper_exploration=exploration, regime=regime, risk=risk, decisions=decisions)
    monkeypatch.setattr(engine, "decide_matrix", lambda *a, **k: pytest.fail("API kararı yeniden hesapladı"))

    resp = TestClient(app).get("/api/v1/decision/matrix")
    assert resp.status_code == 200
    body = resp.json()
    assert body["snapshot_id"] == snap.snapshot_id
    assert len(body["cells"]) == len(decisions)
