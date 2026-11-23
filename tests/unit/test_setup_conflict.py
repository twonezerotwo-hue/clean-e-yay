"""setup_conflict — canlı çakışma kapısının kurulum/çakışma girdisi.

Agent Mode ayarları 22 Kasım 2026'da silindi; varsayılan ayarlardaki etkisi aynen
korunur: kurulum yoksa çakışma çözücüye "agent_mode:no_setup_or_profile" engeli gider.
"""
from __future__ import annotations

from types import SimpleNamespace

from packages.data.providers import ohlcv
from packages.decision import setup_conflict


def _view():
    return SimpleNamespace(
        symbol="BTCUSD",
        consensus=SimpleNamespace(direction_score=50.0, alignment_status="CONFLICTED", is_countertrend=False),
        decision=SimpleNamespace(entry_timeframe="1d", action="HOLD", size_multiplier=0.0, confidence=None),
        economics=None,
        agent=SimpleNamespace(per_timeframe={}),
    )


def test_no_setup_keeps_default_agent_mode_block(monkeypatch):
    monkeypatch.setattr(ohlcv, "get_bars", lambda *a, **k: [])
    out = setup_conflict.evaluate_symbol(_view(), fingerprint=None, risk_action="ALLOW", dqs_status="OK")
    assert out["setup_type"] == "NO_TRADE"
    assert out["mode_filter_passed"] is False
    assert out["mode_filter_blocked_reason"] == "no_setup_or_profile"
    assert "agent_mode:no_setup_or_profile" in out["conflict_blocked_by"]
    assert out["conflict_final_action"] == "NO_TRADE"
    assert "target_comparison" not in out


def test_failure_is_fail_open(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(ohlcv, "get_bars", boom)
    assert setup_conflict.evaluate_symbol(_view(), fingerprint=None, risk_action="ALLOW", dqs_status="OK") == {}
