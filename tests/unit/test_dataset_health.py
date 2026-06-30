"""CP1 — öğrenme veri-hazırlık (dataset_health) testleri.

- Boş state → hiçbir öğrenici hazır değil, all_ready False.
- Yeterli verified+confidence outcome → calibration ready, kapsama yüzdeleri.
- Endpoint /api/v1/learning/dataset-health şekli.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.jsonl"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


def _trade(ps, i: int, *, verified: bool, conf: float | None, pnl: float = 10.0):
    return ps.Trade(
        id=f"t{i}",
        symbol="BTCUSD",
        side="long",
        entry_price=100.0,
        exit_price=101.0,
        pnl_usd=pnl,
        opened_at="2026-06-01T00:00:00+00:00",
        closed_at="2026-06-01T01:00:00+00:00",
        close_reason="TP_HIT",
        data_verified=verified,
        predicted_confidence=conf,
        timeframe="1h",
        mae_pct=0.5,
        mfe_pct=1.2,
    )


def test_empty_state_not_ready(fresh_env) -> None:
    from packages.learning import dataset_health
    r = dataset_health.report()
    assert r["total"] == 0
    assert r["trainable"] == 0
    assert r["all_ready"] is False
    assert all(item["ready"] is False for item in r["learners"])


def test_calibration_ready_weights_not(fresh_env) -> None:
    from packages.learning import dataset_health
    ps = fresh_env
    state = ps.load()
    # 12 verified + confidence → calibration (≥10) ready, weights (≥20) değil.
    for i in range(12):
        state.recent_trades.append(_trade(ps, i, verified=True, conf=0.6))
    ps.save(state)

    r = dataset_health.report()
    assert r["total"] == 12
    assert r["verified"] == 12
    assert r["trainable"] == 12
    assert r["coverage"]["verified_pct"] == 1.0
    assert r["coverage"]["confidence_pct"] == 1.0
    cal = next(item for item in r["learners"] if item["name"] == "calibration")
    weights = next(item for item in r["learners"] if item["name"] == "weights_metrics")
    assert cal["ready"] is True
    assert weights["ready"] is False
    assert r["all_ready"] is False


def test_unverified_not_trainable(fresh_env) -> None:
    from packages.learning import dataset_health
    ps = fresh_env
    state = ps.load()
    for i in range(5):
        state.recent_trades.append(_trade(ps, i, verified=False, conf=0.6))
    ps.save(state)
    r = dataset_health.report()
    assert r["total"] == 5
    assert r["verified"] == 0
    assert r["trainable"] == 0  # verified değil → kalibrasyon yakıtı değil


def test_dataset_health_endpoint(fresh_env) -> None:
    from apps.api.main import app
    client = TestClient(app)
    resp = client.get("/api/v1/learning/dataset-health")
    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body and "coverage" in body and "learners" in body
    assert "all_ready" in body
