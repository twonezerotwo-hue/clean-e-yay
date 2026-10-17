"""Evidence-calibrated shadow policy is read-only and explicit."""
from __future__ import annotations

from packages.learning import shadow_policy


def test_policy_keeps_weak_modules_observe_only(monkeypatch):
    monkeypatch.setenv("BACKTEST_CHALLENGER_ENABLED", "1")
    monkeypatch.setenv("TF_SCORING_V2_SHADOW", "1")
    monkeypatch.setenv("DISCOVERY_SCAN_ENABLED", "1")
    policy = shadow_policy.evaluate()
    modules = policy["modules"]
    assert policy["live_activation"] is False
    assert policy["paper_safe"] is True
    assert modules["backtest_challenger"]["mode"] == "ACTIVE_SHADOW"
    assert modules["news_discovery"]["mode"] == "ACTIVE_SHADOW"
    assert modules["causal_calibration"]["mode"] == "OBSERVE_WEEKLY"
    assert modules["conflict_gate_learning"]["mode"] == "OBSERVE_ONLY"
    assert modules["quantum_scorecard"]["allowed_regimes"] == ["OFFENSIVE"]
    assert all(not row["live_effect"] for name, row in modules.items() if name != "quantum_scorecard")


def test_policy_flags_off_shadow_loops_without_deleting_them(monkeypatch):
    for name in ("BACKTEST_CHALLENGER_ENABLED", "TF_SCORING_V2_SHADOW", "DISCOVERY_SCAN_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    modules = shadow_policy.evaluate()["modules"]
    assert modules["backtest_challenger"]["mode"] == "DISABLED"
    assert modules["tf_scoring_v4_race"]["mode"] == "DISABLED"
    assert modules["news_discovery"]["mode"] == "DISABLED"
    assert modules["zone_proposer"]["mode"] == "OBSERVE_ONLY"
