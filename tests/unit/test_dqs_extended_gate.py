"""DQS çok-eksen GATE (M14 observe→eşik, FAZ-2 2026-07-16).

Sözleşme:
- enabled=false / cfg yok / extended yok → rapor BAYT-AYNI (gölge-önce).
- İhlal → OK→DEGRADED + not; SKOR asla değişmez (KILL_SWITCH zinciri kazayla
  tetiklenemez); BLOCKED dokunulmaz; DEGRADED yükseltilmez.
- Eşiği 0 eksen MUAF; değeri None eksen ihlal SAYILMAZ (ölçülemedi ≠ bozuk).
- Watchdog REGISTRY kaydı var (OFF→ON geçişinde arm, E-6 deseni).
"""
from __future__ import annotations

import dataclasses

from packages.data.quality.dqs import QualityReport, apply_extended_gate

_CFG = {
    "enabled": True,
    "technical_bars_min": 40.0,
    "artifact_freshness_min": 30.0,
    "news_diversity_min": 0.0,
    "rotation_coverage_min": 0.0,
}


def _report(status="OK", extended=None) -> QualityReport:
    return QualityReport(
        score=85.0, freshness=90.0, completeness=100.0, drift=100.0,
        reconciliation=100.0, decision_usage=80.0, status=status,
        extended=extended,
    )


def test_disabled_is_byte_identical():
    ext = {"technical_bars": 5.0, "artifact_freshness": 0.0}
    r = _report(extended=dict(ext))
    before = dataclasses.asdict(r)
    apply_extended_gate(r, {**_CFG, "enabled": False})
    apply_extended_gate(r, None)
    apply_extended_gate(r, {})
    assert dataclasses.asdict(r) == before


def test_no_extended_is_noop():
    r = _report(extended=None)
    apply_extended_gate(r, _CFG)
    assert r.status == "OK" and r.notes == []


def test_breach_degrades_but_score_untouched():
    r = _report(extended={"technical_bars": 12.3, "artifact_freshness": 95.0})
    apply_extended_gate(r, _CFG)
    assert r.status == "DEGRADED"
    assert r.score == 85.0  # skora DOKUNMAZ
    assert any("dqs_extended_gate" in n and "technical_bars=12.3<40" in n for n in r.notes)


def test_healthy_axes_stay_ok():
    r = _report(extended={"technical_bars": 63.6, "artifact_freshness": 98.7,
                          "news_diversity": 100.0, "rotation_coverage": 100.0})
    apply_extended_gate(r, _CFG)
    assert r.status == "OK" and r.notes == []


def test_blocked_never_changes_and_none_axis_ignored():
    r = _report(status="BLOCKED", extended={"technical_bars": None,
                                            "artifact_freshness": 1.0})
    apply_extended_gate(r, _CFG)
    assert r.status == "BLOCKED"          # en kötü durum korunur
    assert any("artifact_freshness=1.0<30" in n for n in r.notes)  # görünürlük sürer
    assert not any("technical_bars" in n for n in r.notes)          # None ihlal değil


def test_zero_threshold_axis_exempt():
    # news/rotation eşiği 0 → çökse bile kapı tetiklenmez (yalnız-gözlem).
    r = _report(extended={"news_diversity": 0.0, "rotation_coverage": 0.0,
                          "technical_bars": 60.0, "artifact_freshness": 98.0})
    apply_extended_gate(r, _CFG)
    assert r.status == "OK" and r.notes == []


def test_watchdog_registry_has_gate_flag():
    from packages.learning.activation_watchdog import REGISTRY

    src = REGISTRY["data_policy_dqs_extended_gate"]["source"]
    assert src == ("thresholds", ("data_policy", "dqs_extended_gate", "enabled"))
