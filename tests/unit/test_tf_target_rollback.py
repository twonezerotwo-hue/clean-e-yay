"""CP4 slice 2 — TF-target edge-gate + outcome-rollback testleri."""
from __future__ import annotations

import pytest

from packages.learning import tf_target_rollback, tf_target_store


@pytest.fixture
def fresh_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_TARGET_STORE_PATH", str(tmp_path / "tf_targets.json"))
    monkeypatch.setenv("TF_TARGET_AUTOAPPLY_PATH", str(tmp_path / "tf_autoapply.json"))
    return tmp_path


def _proposal(tf="4h", sl=1.65):
    # baseline 1.5 → 1.65 = +%10, ±%15 bant içinde (auto-apply'a uygun).
    return {"generated_at": "t", "per_timeframe": {tf: {"sl_atr_mult": sl}}}


# ── edge-gate (submit_proposal auto_apply_allowed) ─────────────────────────────

def test_band_within_auto_applies_by_default(fresh_store):
    base = {"4h": {"sl_atr_mult": 1.5}}
    rec = tf_target_store.submit_proposal(_proposal(), current_baseline=base)
    assert rec["decisions"]["4h"].startswith("auto_applied")
    assert tf_target_store.active_overrides()["4h"]["sl_atr_mult"] == 1.65
    # rollback için önceki değer yakalandı
    assert rec["applied_changes"]["4h"]["sl_atr_mult"] == 1.5


def test_gate_blocks_auto_apply(fresh_store):
    # auto_apply_allowed=False → band-içi bile gated_pending, current değişmez.
    base = {"4h": {"sl_atr_mult": 1.5}}
    rec = tf_target_store.submit_proposal(
        _proposal(), current_baseline=base, auto_apply_allowed=False
    )
    assert rec["decisions"]["4h"].startswith("gated_pending")
    assert "4h" not in tf_target_store.active_overrides()  # uygulanmadı
    assert rec["applied_changes"] == {}
    assert rec["pending_changes"]["4h"]["sl_atr_mult"] == 1.65  # owner onayına hazır


def test_revert_restores_prev(fresh_store):
    base = {"4h": {"sl_atr_mult": 1.5}}
    tf_target_store.submit_proposal(_proposal(), current_baseline=base)
    assert tf_target_store.active_overrides()["4h"]["sl_atr_mult"] == 1.65
    tf_target_store.revert_overrides({"4h": {"sl_atr_mult": 1.5}})
    assert tf_target_store.active_overrides()["4h"]["sl_atr_mult"] == 1.5


def test_revert_empty_removes_override(fresh_store):
    base = {"4h": {"sl_atr_mult": 1.5}}
    tf_target_store.submit_proposal(_proposal(), current_baseline=base)
    tf_target_store.revert_overrides({"4h": {}})  # boş → config default'a düş
    assert "4h" not in tf_target_store.active_overrides()


# ── rollback monitör ───────────────────────────────────────────────────────────

def test_no_active_when_nothing_recorded(fresh_store):
    assert tf_target_rollback.check_rollback() == {"status": "no_active"}


def test_monitoring_until_enough_outcomes(fresh_store, monkeypatch):
    tf_target_rollback.record_apply(
        prev_overrides={"4h": {"sl_atr_mult": 1.5}}, applied_tfs=["4h"],
        baseline_expectancy=-10.0, baseline_n=15,
    )
    monkeypatch.setattr(tf_target_rollback.weight_rollback,
                        "post_open_expectancy", lambda since: (3, 5.0))
    out = tf_target_rollback.check_rollback()
    assert out["status"] == "monitoring"
    assert out["post_n"] == 3


def test_confirmed_when_expectancy_holds(fresh_store, monkeypatch):
    tf_target_rollback.record_apply(
        prev_overrides={"4h": {"sl_atr_mult": 1.5}}, applied_tfs=["4h"],
        baseline_expectancy=-10.0, baseline_n=15,
    )
    monkeypatch.setattr(tf_target_rollback.weight_rollback,
                        "post_open_expectancy", lambda since: (15, 2.0))
    out = tf_target_rollback.check_rollback()
    assert out["status"] == "CONFIRMED"
    assert out["confirmed_tfs"] == ["4h"]
    assert tf_target_rollback.get_active() is None  # izleme temizlendi


def test_rolled_back_reverts_geometry(fresh_store, monkeypatch):
    # Önce auto-apply (current=1.65), sonra kötü expectancy → revert 1.5.
    tf_target_store.submit_proposal(_proposal(), current_baseline={"4h": {"sl_atr_mult": 1.5}})
    assert tf_target_store.active_overrides()["4h"]["sl_atr_mult"] == 1.65
    tf_target_rollback.record_apply(
        prev_overrides={"4h": {"sl_atr_mult": 1.5}}, applied_tfs=["4h"],
        baseline_expectancy=-10.0, baseline_n=15,
    )
    monkeypatch.setattr(tf_target_rollback.weight_rollback,
                        "post_open_expectancy", lambda since: (15, -50.0))
    out = tf_target_rollback.check_rollback()
    assert out["status"] == "ROLLED_BACK"
    assert out["reverted_tfs"] == ["4h"]
    # geometri gerçekten geri alındı
    assert tf_target_store.active_overrides()["4h"]["sl_atr_mult"] == 1.5
    assert tf_target_rollback.get_active() is None
