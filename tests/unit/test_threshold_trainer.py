"""CP4 (final) — otonom eşik trainer + runtime override + rollback testleri."""
from __future__ import annotations

import pytest

from packages.data.registry import loader, threshold_overrides
from packages.learning import edge_report, threshold_ab, threshold_trainer, weight_rollback


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("THRESHOLD_OVERRIDES_PATH", str(tmp_path / "thr_ov.json"))
    monkeypatch.setenv("THRESHOLD_AUTOAPPLY_PATH", str(tmp_path / "thr_aa.json"))
    monkeypatch.delenv("THRESHOLD_AUTOTUNE", raising=False)
    # cache temizle (önceki testten sızmasın)
    threshold_overrides._CACHE["key"] = None
    return tmp_path


# ── seam: flag OFF → load_thresholds bayt-aynı ─────────────────────────────────

def test_flag_off_byte_identical_even_with_override_file(fresh, monkeypatch):
    # Override dosyası VAR ama flag kapalı → load_thresholds base'i BİREBİR döner.
    threshold_overrides.set_override("paper_trading.tp_rr_ratio", 9.9, prev=2.0)
    monkeypatch.delenv("THRESHOLD_AUTOTUNE", raising=False)
    assert loader.load_thresholds() is loader._load_thresholds_base()
    assert threshold_overrides.active_tree() == {}


def test_flag_on_merges_override(fresh, monkeypatch):
    threshold_overrides.set_override("paper_trading.tp_rr_ratio", 3.5, prev=2.0)
    monkeypatch.setenv("THRESHOLD_AUTOTUNE", "1")
    eff = loader.load_thresholds()
    assert eff["paper_trading"]["tp_rr_ratio"] == 3.5
    # deep-merge: paper_trading'in diğer alanları korunur
    assert "sl_pct" in eff["paper_trading"]


def test_revert_removes_override(fresh, monkeypatch):
    monkeypatch.setenv("THRESHOLD_AUTOTUNE", "1")
    threshold_overrides.set_override("paper_trading.tp_rr_ratio", 3.5, prev=2.0)
    assert loader.load_thresholds()["paper_trading"]["tp_rr_ratio"] == 3.5
    threshold_overrides.revert("paper_trading.tp_rr_ratio")
    assert loader.load_thresholds() is loader._load_thresholds_base()


# ── trainer.train gate'leri ────────────────────────────────────────────────────

def test_train_disabled_when_flag_off(fresh):
    assert threshold_trainer.train()["status"] == "DISABLED"


def test_train_edge_unstable_blocks(fresh, monkeypatch):
    monkeypatch.setenv("THRESHOLD_AUTOTUNE", "1")
    monkeypatch.setattr(edge_report, "report", lambda: {"safe_to_autotune": False})
    assert threshold_trainer.train()["status"] == "EDGE_UNSTABLE"


def test_train_applies_when_better_and_stable(fresh, monkeypatch):
    monkeypatch.setenv("THRESHOLD_AUTOTUNE", "1")
    monkeypatch.setattr(edge_report, "report", lambda: {"safe_to_autotune": True})
    monkeypatch.setattr(weight_rollback, "pre_apply_expectancy", lambda: (15, -10.0))
    # A/B: baseline avg_return 0.01, öneri 0.02 (belirgin iyileşme)
    monkeypatch.setattr(threshold_ab, "sweep", lambda path, cands, **kw: {
        "baseline": {"avg_return_pct": 0.01},
        "recommendation": {"value": cands[-1], "avg_return_pct": 0.02},
    })
    out = threshold_trainer.train()
    assert out["status"] == "APPLIED"
    # override canlıya yazıldı (base 2.0 → +%10 aday 2.2, guardrail [1.5,4.0] içinde)
    assert threshold_overrides.get("paper_trading.tp_rr_ratio")["value"] == 2.2


def test_train_monitoring_blocks_second_apply(fresh, monkeypatch):
    monkeypatch.setenv("THRESHOLD_AUTOTUNE", "1")
    threshold_trainer._save_state({"active": {"path": "x"}, "history": []})
    assert threshold_trainer.train()["status"] == "MONITORING"


def test_train_no_change_when_not_better(fresh, monkeypatch):
    monkeypatch.setenv("THRESHOLD_AUTOTUNE", "1")
    monkeypatch.setattr(edge_report, "report", lambda: {"safe_to_autotune": True})
    monkeypatch.setattr(threshold_ab, "sweep", lambda path, cands, **kw: {
        "baseline": {"avg_return_pct": 0.02},
        "recommendation": None,
    })
    assert threshold_trainer.train()["status"] == "NO_CHANGE"


# ── rollback ───────────────────────────────────────────────────────────────────

def test_rollback_reverts_on_worse_expectancy(fresh, monkeypatch):
    monkeypatch.setenv("THRESHOLD_AUTOTUNE", "1")
    threshold_overrides.set_override("paper_trading.tp_rr_ratio", 2.2, prev=2.0)
    threshold_trainer._save_state({"active": {
        "path": "paper_trading.tp_rr_ratio", "baseline_expectancy": -10.0,
        "applied_at": "2026-06-30T00:00:00+00:00",
    }, "history": []})
    monkeypatch.setattr(weight_rollback, "post_open_expectancy", lambda since: (15, -50.0))
    out = threshold_trainer.check_rollback()
    assert out["status"] == "ROLLED_BACK"
    assert threshold_overrides.get("paper_trading.tp_rr_ratio") is None  # geri alındı


def test_rollback_confirmed_when_holds(fresh, monkeypatch):
    monkeypatch.setenv("THRESHOLD_AUTOTUNE", "1")
    threshold_overrides.set_override("paper_trading.tp_rr_ratio", 2.2, prev=2.0)
    threshold_trainer._save_state({"active": {
        "path": "paper_trading.tp_rr_ratio", "baseline_expectancy": -10.0,
        "applied_at": "2026-06-30T00:00:00+00:00",
    }, "history": []})
    monkeypatch.setattr(weight_rollback, "post_open_expectancy", lambda since: (15, 5.0))
    out = threshold_trainer.check_rollback()
    assert out["status"] == "CONFIRMED"
    assert threshold_overrides.get("paper_trading.tp_rr_ratio")["value"] == 2.2  # kaldı
