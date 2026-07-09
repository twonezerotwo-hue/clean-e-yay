"""Karar-kanıt tüketicisi testleri (2026-07-09).

Tüm learning'lerin TEK birleşik fikri; VARSAYILAN GÖLGE (boyut değişmez),
LEARNING_ADVISOR_APPLY=1 iken yalnız KISAR (no-boost). EVIDENCE-only.
"""
from __future__ import annotations

import json

from packages.decision import learning_advisor as la


def test_neutral_when_no_evidence():
    """Kanıt yoksa CONFIRM + size_hint 1.0 (nötr — fikri saptırmaz)."""
    a = la.advise(symbol="BTCUSD", timeframe="4h", regime="OFFENSIVE",
                  dominant_module="sentinel", mistake_action="NEUTRAL")
    assert a.stance == "CONFIRM" and a.size_hint == 1.0 and a.reasons == []


def test_mistake_avoid_escalates():
    a = la.advise(symbol="BTCUSD", timeframe="4h", regime="OFFENSIVE",
                  dominant_module="touche", mistake_action="AVOID")
    assert a.stance == "AVOID" and a.size_hint == 0.0
    assert "mistake_memory" in a.sources


def test_strictest_verdict_wins():
    """AVOID > CAUTION > CONFIRM — birden çok kaynak varsa en katı kazanır."""
    a = la.advise(symbol="BTCUSD", timeframe="4h", regime="OFFENSIVE",
                  dominant_module="touche", mistake_action="WARNING",
                  calibrated_confidence=0.30, min_confidence=0.5,
                  expected_value=-0.2)
    assert a.stance == "CAUTION" and a.size_hint == 0.7
    # WARNING + düşük güven + negatif EV → 3 gerekçe
    assert len(a.reasons) >= 3


def test_reflection_weak_memory_causes_caution(tmp_path, monkeypatch):
    art = tmp_path / "reflection.json"
    art.write_text(json.dumps({
        "per_symbol": {"BTCUSD": {"summary": {"n": 4, "win_pct": 25.0}, "lessons": []}}
    }), encoding="utf-8")
    monkeypatch.setenv("REFLECTION_PATH", str(art))
    a = la.advise(symbol="BTCUSD", timeframe="4h", regime="OFFENSIVE",
                  dominant_module="touche", mistake_action="NEUTRAL")
    assert a.stance == "CAUTION" and "reflection" in a.sources


def test_meta_gate_skip_causes_caution():
    a = la.advise(symbol="ETHUSD", timeframe="1h", regime="NEUTRAL",
                  dominant_module="quantum", mistake_action="NEUTRAL",
                  meta_report={"verdict": "SKIP"})
    assert a.stance == "CAUTION" and "meta_gate" in a.sources


def test_apply_flag_default_off(monkeypatch):
    """Flag KAPALI (default) → apply_enabled False (boyut bayt-aynı kalır)."""
    monkeypatch.delenv("LEARNING_ADVISOR_APPLY", raising=False)
    assert la.apply_enabled() is False
    monkeypatch.setenv("LEARNING_ADVISOR_APPLY", "1")
    assert la.apply_enabled() is True


def test_size_hint_only_reduces():
    """Hiçbir hüküm boyutu 1.0 üstüne çıkarmaz (no-boost)."""
    for ma in ("NEUTRAL", "WARNING", "AVOID"):
        a = la.advise(symbol="X", timeframe="4h", regime="OFFENSIVE",
                      dominant_module="sentinel", mistake_action=ma)
        assert a.size_hint <= 1.0
