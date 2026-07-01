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


# ── CP4-fix #2: outlier-direnç ─────────────────────────────────────────────────

def test_winsorize_clamps_extremes_keeps_order() -> None:
    pnls = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 1000.0]
    w = edge_report._winsorize(pnls, pct=0.1)
    assert len(w) == len(pnls)
    assert max(w) < 1000.0  # dev değer kıstırıldı (üst kuyruk)
    assert w[-1] == w[8]  # 1000 → üst sınıra (9.0) çekildi; konum korunur


def test_outlier_concentration() -> None:
    # Tek dev işlem → yüksek yoğunlaşma
    assert edge_report._outlier_concentration([1.0, 1.0, 1.0, 100.0]) > 0.9
    # Dağılmış → düşük
    assert edge_report._outlier_concentration([5.0, 5.0, 5.0, 5.0]) == 0.25


def test_safe_to_autotune_false_when_outlier_dependent(monkeypatch) -> None:
    from packages.learning import outcomes as om

    def _o(pnl, regime="NEUTRAL"):
        return om.CanonicalOutcome(
            trade_id="t", symbol="X", timeframe="1d", opened_at=None, closed_at=None,
            duration_seconds=None, direction="long", open_price=1.0, close_price=1.0,
            pnl=pnl, pnl_pct=None, open_reason=None, close_reason=None, fingerprint=None,
            regime=regime, dominant_module="touche", candidate_action=None,
            final_action=None, data_verified=True,
        )

    # Tutarlı win-rate + çoğu pozitif ama tek dev outlier → STABLE olsa bile gate kapalı.
    outs = [_o(1.0), _o(-0.5)] * 8 + [_o(500.0)]  # 500 tek başına baskın
    monkeypatch.setattr(om, "outcomes_from_state", lambda *a, **k: outs)
    r = edge_report.report()
    assert r["outlier_dependent"] is True
    assert r["safe_to_autotune"] is False
    assert "regime_coverage" in r
