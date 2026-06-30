"""CP2 — edge_report (walk-forward stabilite + counterfactual) testleri."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from packages.learning import edge_report


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.jsonl"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


def test_stability_insufficient() -> None:
    r = edge_report.walk_forward_stability([1.0, -1.0, 2.0])  # < 4*3
    assert r["ready"] is False
    assert r["reason"] == "insufficient_outcomes"


def test_stability_stable_consistent_edge() -> None:
    # Her segmentte ~aynı kazanç oranı → düşük std, pozitif → stable.
    pnls = [10.0, -5.0, 10.0] * 6  # 18 örnek, her segment benzer
    r = edge_report.walk_forward_stability(pnls, folds=3)
    assert r["ready"] is True
    assert r["stable"] is True
    assert r["win_rate_std"] <= 0.15


def test_stability_unstable_drift() -> None:
    # İlk yarı hep kazanç, ikinci yarı hep kayıp → yüksek std → unstable.
    pnls = [10.0] * 8 + [-10.0] * 8
    r = edge_report.walk_forward_stability(pnls, folds=4)
    assert r["ready"] is True
    assert r["stable"] is False


def test_report_shape(fresh_env) -> None:
    r = edge_report.report()
    assert "verdict" in r and r["verdict"] in {"STABLE", "UNSTABLE", "INSUFFICIENT"}
    assert "stability" in r and "counterfactual" in r
    assert "safe_to_autotune" in r
    # Boş state → yetersiz → oto-tune güvenli değil.
    assert r["verdict"] == "INSUFFICIENT"
    assert r["safe_to_autotune"] is False


def test_edge_report_endpoint(fresh_env) -> None:
    from apps.api.main import app
    client = TestClient(app)
    resp = client.get("/api/v1/learning/edge-report")
    assert resp.status_code == 200
    body = resp.json()
    assert "verdict" in body and "stability" in body
