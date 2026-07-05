"""B serisi — challenger_trainer.viewmodel() (öğrenme paneli görünümü) testleri.

- Flag kapalı → enabled False + DISABLED.
- Flag açık ama rapor yok → NO_DATA + boş listeler.
- Rapor var → quantum ayrım karnesi + aday ağırlık satırları + terfi bloğu.
- SALT-GÖZLEM: viewmodel yalnız raporu + B-4 evaluate'i okur.
"""
from __future__ import annotations

import json

import pytest

from packages.learning import challenger_trainer as ct


@pytest.fixture
def vm_env(tmp_path, monkeypatch):
    # İzole yollar: rapor + challenger jsonl + governor (B-4 evaluate okur).
    monkeypatch.setenv("BACKTEST_CHALLENGER_REPORT_PATH", str(tmp_path / "report.json"))
    monkeypatch.setenv("BACKTEST_CHALLENGER_PATH", str(tmp_path / "challenger.jsonl"))
    return tmp_path


def test_disabled_when_flag_off(vm_env, monkeypatch) -> None:
    monkeypatch.delenv("BACKTEST_CHALLENGER_ENABLED", raising=False)
    vm = ct.viewmodel()
    assert vm["enabled"] is False
    assert vm["status"] == "DISABLED"
    assert vm["quantum"] == [] and vm["weights"] == []


def test_no_data_when_report_missing(vm_env, monkeypatch) -> None:
    monkeypatch.setenv("BACKTEST_CHALLENGER_ENABLED", "1")
    vm = ct.viewmodel()
    assert vm["enabled"] is True
    assert vm["status"] == "NO_DATA"
    assert vm["quantum"] == [] and vm["weights"] == []
    # B-4 terfi bloğu her zaman var (veri yokken NOT_READY).
    assert vm["promotion"]["status"] == "NOT_READY"


def test_data_state_flattens_report(vm_env, monkeypatch) -> None:
    monkeypatch.setenv("BACKTEST_CHALLENGER_ENABLED", "1")
    report = {
        "generated_at": "2026-07-05T00:00:00+00:00",
        "status": "OK",
        "source_records": 329,
        "loss_aware": False,
        "regimes": {
            "NEUTRAL": {
                "status": "PROPOSED", "records": 143,
                "deltas": [
                    {"module": "touche", "from": 0.30, "to": 0.29, "delta": -0.01},
                    {"module": "sentinel", "from": 0.10, "to": 0.11, "delta": 0.01},
                ],
            },
            "OFFENSIVE": {"status": "INSUFFICIENT", "records": 79, "deltas": []},
        },
        "quantum_scorecard": {
            "per_regime": {
                "DEFENSIVE": {"n": 101, "mean_quantum": 40.0, "separation": 0.0051,
                              "correlation": 0.18, "verdict": "DISCRIMINATES", "status": "OK"},
                "NEUTRAL": {"n": 143, "mean_quantum": 55.0, "separation": -0.018,
                            "correlation": -0.14, "verdict": "INVERSE", "status": "OK"},
            },
            "summary": "quantum en güçlü DEFENSIVE'da ayrışıyor",
        },
    }
    (vm_env / "report.json").write_text(json.dumps(report), encoding="utf-8")

    vm = ct.viewmodel()
    assert vm["enabled"] is True and vm["status"] == "OK"
    assert vm["source_records"] == 329
    # Quantum: DISCRIMINATES önce sıralanır.
    assert vm["quantum"][0]["regime"] == "DEFENSIVE"
    assert vm["quantum"][0]["verdict"] == "DISCRIMINATES"
    verdicts = {q["regime"]: q["verdict"] for q in vm["quantum"]}
    assert verdicts["NEUTRAL"] == "INVERSE"
    # Ağırlık: PROPOSED önce; deltalar en fazla 3, champion/challenger alanlı.
    assert vm["weights"][0]["regime"] == "NEUTRAL"
    assert vm["weights"][0]["status"] == "PROPOSED"
    assert vm["weights"][0]["deltas"][0]["module"] == "touche"
    assert vm["weights"][0]["deltas"][0]["champion"] == 0.30
    assert vm["regime_histogram"] == {"NEUTRAL": 143, "OFFENSIVE": 79}
    assert "promotion" in vm and "honesty" in vm
