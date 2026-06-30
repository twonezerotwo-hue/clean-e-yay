"""CP4 slice 3 — per-TF trailing autotuner (tf_trail_mult + trainer Rule 4) testleri."""
from __future__ import annotations

import pytest

from packages.learning import tf_target_store, tf_target_trainer
from packages.risk import trade_economics as te


@pytest.fixture
def fresh_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_TARGET_STORE_PATH", str(tmp_path / "tf_targets.json"))
    monkeypatch.delenv("TF_TARGET_TRAIL_AUTOTUNE", raising=False)
    return tmp_path


# ── seam: tf_trail_mult (açılış yolu bunu çarpan olarak kullanır) ───────────────

def test_flag_off_is_neutral_even_with_override(fresh_store, monkeypatch):
    # Store'da trail_mult=1.5 olsa BİLE flag kapalıyken 1.0 (bayt-aynı garanti).
    tf_target_store.submit_proposal(
        {"generated_at": "t", "per_timeframe": {"4h": {"trail_mult": 1.5}}},
        current_baseline={"4h": {"trail_mult": 1.0}},
    )
    monkeypatch.delenv("TF_TARGET_TRAIL_AUTOTUNE", raising=False)
    assert te.tf_trail_mult("4h") == 1.0


def test_flag_on_applies_override(fresh_store, monkeypatch):
    tf_target_store.submit_proposal(
        {"generated_at": "t", "per_timeframe": {"4h": {"trail_mult": 1.15}}},
        current_baseline={"4h": {"trail_mult": 1.0}},
    )
    monkeypatch.setenv("TF_TARGET_TRAIL_AUTOTUNE", "1")
    assert te.tf_trail_mult("4h") == pytest.approx(1.15)


def test_flag_on_no_override_is_neutral(fresh_store, monkeypatch):
    monkeypatch.setenv("TF_TARGET_TRAIL_AUTOTUNE", "1")
    assert te.tf_trail_mult("1h") == 1.0


def test_override_clamped_to_guardrail(fresh_store, monkeypatch):
    # Store guardrail clamp'i submit'te de var; resolver ikinci güvenlik kemeri.
    monkeypatch.setenv("TF_TARGET_TRAIL_AUTOTUNE", "1")
    tf_target_store._save({"current": {"4h": {"trail_mult": 9.0}}, "history": []})
    assert te.tf_trail_mult("4h") == tf_target_store.GUARDRAIL["trail_mult"][1]  # 2.0


# ── trainer Rule 4: EXIT_EARLY → trail_mult ↑ ──────────────────────────────────

def _stats(**kw):
    base = dict(
        timeframe="4h", trades=20, wins=10, win_rate=0.5, sl_hit=2, tp_hit=2,
        time_stop=2, other_exit=14, sl_hit_rate=0.1, tp_hit_rate=0.1,
        time_stop_rate=0.1, avg_mae_pct=0.3, avg_mfe_pct=2.0, avg_pnl=1.0,
    )
    base.update(kw)
    return tf_target_trainer.TfStats(**base)


def test_rule4_loosens_trail_on_low_capture(fresh_store):
    # Trailing-yoğun + düşük yakalama → trail_mult ↑.
    stats = _stats(trailing_exit=12, trailing_rate=0.60, avg_capture=0.28)
    baseline = {"sl_atr_mult": 1.5, "rr": 2.0, "sl_pct_floor": 0.015,
                "sl_pct_cap": 0.05, "trail_mult": 1.0}
    new, nudges = tf_target_trainer._nudge_tf(stats, baseline)
    codes = {(n.param, n.delta_pct > 0) for n in nudges}
    assert ("trail_mult", True) in codes
    assert new["trail_mult"] > 1.0


def test_rule4_silent_when_capture_healthy(fresh_store):
    # Yakalama sağlıklı → trail dokunulmaz.
    stats = _stats(trailing_exit=12, trailing_rate=0.60, avg_capture=0.95)
    baseline = {"sl_atr_mult": 1.5, "rr": 2.0, "sl_pct_floor": 0.015,
                "sl_pct_cap": 0.05, "trail_mult": 1.0}
    new, nudges = tf_target_trainer._nudge_tf(stats, baseline)
    assert all(n.param != "trail_mult" for n in nudges)
    assert new["trail_mult"] == 1.0
