"""calibration guardrail (flag-gated) + jump ledger (observe-only) testleri."""
from __future__ import annotations

import json
from types import SimpleNamespace

from packages.learning import calibration_audit, calibration_store


# inflation_delta + guardrail

def test_inflation_delta_signed():
    assert calibration_store.inflation_delta(0.114, 0.547) == 0.433
    assert calibration_store.inflation_delta(0.60, 0.50) == -0.10


def test_guardrail_off_is_passthrough(monkeypatch):
    monkeypatch.setattr(calibration_store, "_guardrail_cfg", lambda: {"enabled": False})
    val, src = calibration_store.apply_inflation_guardrail(0.114, 0.547, "fitted")
    assert (val, src) == (0.547, "fitted")


def test_guardrail_on_caps_excess_inflation(monkeypatch):
    monkeypatch.setattr(
        calibration_store, "_guardrail_cfg",
        lambda: {"enabled": True, "max_inflation_delta": 0.25},
    )
    val, src = calibration_store.apply_inflation_guardrail(0.114, 0.547, "fitted")
    assert src == "fitted_capped"
    assert val == 0.364  # raw 0.114 + 0.25


def test_guardrail_on_within_band_passthrough(monkeypatch):
    monkeypatch.setattr(
        calibration_store, "_guardrail_cfg",
        lambda: {"enabled": True, "max_inflation_delta": 0.25},
    )
    val, src = calibration_store.apply_inflation_guardrail(0.40, 0.55, "fitted")
    assert (val, src) == (0.55, "fitted")  # delta 0.15 < 0.25


def test_guardrail_skips_non_fitted_source(monkeypatch):
    monkeypatch.setattr(
        calibration_store, "_guardrail_cfg",
        lambda: {"enabled": True, "max_inflation_delta": 0.05},
    )
    val, src = calibration_store.apply_inflation_guardrail(0.114, 0.90, "identity")
    assert (val, src) == (0.90, "identity")


# jump ledger

def _fake_decision_position(delta_big: bool = True):
    cons = SimpleNamespace(
        score=55.7, dominant_module="touche", direction="long", confluence_aligned=True
    )
    decision = SimpleNamespace(
        symbol="NVDA", timeframe="1d", raw_confidence=0.114,
        confidence=0.547, confidence_source="fitted",
        fingerprint="NVDA|neutral|long", consensus=cons,
    )
    position = SimpleNamespace(
        id="abc123", symbol="NVDA", timeframe="1d", side="long",
        predicted_confidence=0.547 if delta_big else 0.20,
        tier="STRONG", size_usd=15000.0, entry_price=192.53,
    )
    return decision, position


def test_build_row_captures_jump_and_factors():
    decision, position = _fake_decision_position()
    row = calibration_audit.build_row(decision, position, regime="NEUTRAL")
    assert row["symbol"] == "NVDA"
    assert row["raw_confidence"] == 0.114
    assert row["fitted_confidence"] == 0.547
    assert row["inflation_delta"] == 0.433
    assert row["tier"] == "STRONG"
    assert row["size_usd"] == 15000.0
    assert row["dominant_module"] == "touche"
    assert row["regime"] == "NEUTRAL"
    assert row["position_id"] == "abc123"


def test_record_open_appends_and_summarizes(tmp_path, monkeypatch):
    ledger = tmp_path / "calibration_jumps.jsonl"
    monkeypatch.setenv("CALIBRATION_AUDIT_PATH", str(ledger))
    decision, position = _fake_decision_position()
    written = calibration_audit.record_open(decision, position, regime="NEUTRAL")
    assert written is not None
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["inflation_delta"] == 0.433
    recent = calibration_audit.read_recent(10)
    assert len(recent) == 1
    summ = calibration_audit.summary_viewmodel()
    assert summ["count"] == 1
    assert summ["fitted_count"] == 1
    assert summ["max_inflation_delta"] == 0.433
    assert summ["by_tier"].get("STRONG") == 1
    assert summ["by_dominant_module"].get("touche") == 1


def test_record_open_best_effort_on_bad_path(tmp_path, monkeypatch):
    # Yazilamayan path -> None doner, exception sizdirmaz (tick dusmez).
    bad_parent = tmp_path / "not_a_directory"
    bad_parent.write_text("x", encoding="utf-8")
    monkeypatch.setenv("CALIBRATION_AUDIT_PATH", str(bad_parent / "x.jsonl"))
    decision, position = _fake_decision_position()
    assert calibration_audit.record_open(decision, position) is None
