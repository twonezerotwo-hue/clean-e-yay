"""Eşik önericisi testleri: canlı eşik yalnız config dosyasından gelir, öneri uygulanmaz.

21 Kasım 2026 owner kararı: otomatik eşik uygulaması (THRESHOLD_AUTOTUNE + dosya
tabanlı runtime override) kaldırıldı. Eski kod bu testlerin ilk ikisinde düşer.
"""
from __future__ import annotations

import json

import pytest

from packages.data.registry import loader
from packages.learning import edge_report, threshold_ab, threshold_trainer


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("THRESHOLD_AUTOAPPLY_PATH", str(tmp_path / "thr_aa.json"))
    return tmp_path


def _stable_and_better(monkeypatch):
    monkeypatch.setattr(edge_report, "report", lambda: {"safe_to_autotune": True})
    monkeypatch.setattr(threshold_ab, "sweep", lambda path, cands, **kw: {
        "baseline": {"avg_return_pct": 0.01},
        "recommendation": {"value": cands[-1], "avg_return_pct": 0.02},
    })


def test_old_override_file_and_flag_do_not_change_live_thresholds(fresh, monkeypatch):
    # Eski kurulumun kalıntısı: override dosyası VAR ve bayrak AÇIK → yine config.
    ov = fresh / "thr_ov.json"
    ov.write_text(json.dumps({"overrides": {"paper_trading.tp_rr_ratio": {
        "value": 9.9, "prev": 2.0}}}), encoding="utf-8")
    monkeypatch.setenv("THRESHOLD_OVERRIDES_PATH", str(ov))
    monkeypatch.setenv("THRESHOLD_AUTOTUNE", "1")
    base = loader._load_thresholds_base()
    assert loader.load_thresholds() is base
    assert loader.load_thresholds()["paper_trading"]["tp_rr_ratio"] == base[
        "paper_trading"]["tp_rr_ratio"]


def test_train_proposes_but_never_changes_live_threshold(fresh, monkeypatch):
    _stable_and_better(monkeypatch)
    before = loader.load_thresholds()["paper_trading"]["tp_rr_ratio"]
    out = threshold_trainer.train()
    assert out["status"] == "PROPOSED"
    assert loader.load_thresholds()["paper_trading"]["tp_rr_ratio"] == before
    hist = threshold_trainer._load_state()["history"]
    tp = [h for h in hist if h["path"] == "paper_trading.tp_rr_ratio"]
    assert tp and tp[0]["event"] == "PROPOSED" and tp[0]["from"] == before
    view = threshold_trainer.status_viewmodel()
    assert view["enabled"] is False
    assert view["active_overrides"] == {} and view["monitor"] is None


def test_train_runs_at_most_once_a_day(fresh, monkeypatch):
    _stable_and_better(monkeypatch)
    assert threshold_trainer.train()["status"] == "PROPOSED"
    assert threshold_trainer.train()["status"] == "RECENT"


def test_train_edge_unstable_blocks(fresh, monkeypatch):
    monkeypatch.setattr(edge_report, "report", lambda: {"safe_to_autotune": False})
    assert threshold_trainer.train()["status"] == "EDGE_UNSTABLE"


def test_train_no_change_when_not_better(fresh, monkeypatch):
    monkeypatch.setattr(edge_report, "report", lambda: {"safe_to_autotune": True})
    monkeypatch.setattr(threshold_ab, "sweep", lambda path, cands, **kw: {
        "baseline": {"avg_return_pct": 0.02},
        "recommendation": None,
    })
    assert threshold_trainer.train()["status"] == "NO_CHANGE"


def test_old_monitoring_entry_is_closed_into_history(fresh, monkeypatch):
    monkeypatch.setattr(edge_report, "report", lambda: {"safe_to_autotune": False})
    threshold_trainer._save_state({"active": {
        "path": "paper_trading.tp_rr_ratio", "from": 2.0, "to": 2.2,
        "status": "MONITORING"}, "history": []})
    threshold_trainer.train()
    st = threshold_trainer._load_state()
    assert st["active"] is None
    assert st["history"][0]["event"] == "AUTO_APPLY_REMOVED"
    assert st["history"][0]["to"] == 2.2
