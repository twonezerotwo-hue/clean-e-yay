"""I2 — Olgunluk Kapısı testleri.

- assess() dört basamağı da doğru verir (az örnek → net-yok → edge-stabil-değil → oto).
- INVERSE net sinyaldir (ters ama güçlü kanıt); FLAT/PENDING zayıftır.
- ready_to_propose / ready_to_autotune bayrakları basamakla tutarlı.
- evidence_bus entegrasyonu: her kayıt maturity damgası taşır; GLOBAL edge_safe
  basamak-3'ü basamak-2'ye kısar; viewmodel by_maturity sayacı üretir.
"""
from __future__ import annotations

from packages.learning import evidence_bus as eb
from packages.learning import maturity_gate as mg


def test_level0_insufficient_samples() -> None:
    r = mg.assess(n_samples=5, verdict="DISCRIMINATES", edge_safe=True)
    assert r["level"] == 0 and r["maturity"] == "INSUFFICIENT"
    assert r["reason"] == "az_ornek"
    assert not r["ready_to_propose"] and not r["ready_to_autotune"]


def test_level0_none_samples() -> None:
    assert mg.assess(n_samples=None, verdict="STABLE")["level"] == 0


def test_level1_enough_samples_weak_verdict() -> None:
    r = mg.assess(n_samples=50, verdict="FLAT", edge_safe=True)
    assert r["level"] == 1 and r["maturity"] == "OBSERVED"
    assert r["reason"] == "net_sinyal_yok"
    assert not r["ready_to_propose"]


def test_level2_clear_verdict_edge_not_safe() -> None:
    r = mg.assess(n_samples=50, verdict="DISCRIMINATES", edge_safe=False)
    assert r["level"] == 2 and r["maturity"] == "PROPOSABLE"
    assert r["reason"] == "net_sinyal_edge_stabil_degil"
    assert r["ready_to_propose"] and not r["ready_to_autotune"]


def test_level3_clear_verdict_edge_safe() -> None:
    r = mg.assess(n_samples=50, verdict="DISCRIMINATES", edge_safe=True)
    assert r["level"] == 3 and r["maturity"] == "ACTIONABLE"
    assert r["ready_to_propose"] and r["ready_to_autotune"]


def test_level3_edge_unknown_still_actionable() -> None:
    # edge_safe=None (bilinmiyor/uygulanamaz) → basamak-3 için stabil şartı ARANMAZ
    assert mg.assess(n_samples=50, verdict="STABLE", edge_safe=None)["level"] == 3


def test_inverse_is_clear_signal() -> None:
    # INVERSE ters ama GÜÇLÜ kanıt → net sinyaldir (basamak-1'de takılmaz)
    assert mg.assess(n_samples=50, verdict="INVERSE", edge_safe=True)["level"] == 3


def test_pending_is_weak() -> None:
    assert mg.assess(n_samples=99, verdict="PENDING")["level"] == 1


def test_none_verdict_is_weak() -> None:
    assert mg.assess(n_samples=99, verdict=None)["level"] == 1


# ---------------------------------------------------------- evidence_bus entegre

def _fake_clear_live():
    return [eb.EvidenceRecord(topic="signal_quality", subject="touche@NEUTRAL",
                              source=eb.LIVE, regime="NEUTRAL", n_samples=40,
                              statistic=0.6, verdict="DISCRIMINATES")]


def _fake_edge_unsafe():
    return [eb.EvidenceRecord(topic="edge_stability", subject="global", source=eb.LIVE,
                              n_samples=200, statistic=0.5, verdict="UNSTABLE",
                              detail={"safe_to_autotune": False})]


def _fake_edge_safe():
    return [eb.EvidenceRecord(topic="edge_stability", subject="global", source=eb.LIVE,
                              n_samples=200, statistic=0.1, verdict="STABLE",
                              detail={"safe_to_autotune": True})]


def test_collect_stamps_maturity(monkeypatch) -> None:
    monkeypatch.setattr(eb, "_SOURCES", (_fake_clear_live, _fake_edge_safe))
    recs = eb.collect()
    sq = next(r for r in recs if r.topic == "signal_quality")
    assert sq.maturity is not None
    assert sq.maturity["maturity"] == "ACTIONABLE"  # net + global edge stabil


def test_global_edge_unsafe_caps_at_proposable(monkeypatch) -> None:
    monkeypatch.setattr(eb, "_SOURCES", (_fake_clear_live, _fake_edge_unsafe))
    recs = eb.collect()
    sq = next(r for r in recs if r.topic == "signal_quality")
    # global edge stabil DEĞİL → net sinyal bile basamak-3 alamaz, 2'de kalır
    assert sq.maturity["level"] == 2


def test_viewmodel_counts_maturity(monkeypatch) -> None:
    monkeypatch.setattr(eb, "_SOURCES", (_fake_clear_live, _fake_edge_safe))
    vm = eb.viewmodel()
    assert "by_maturity" in vm
    assert vm["by_maturity"].get("ACTIONABLE", 0) >= 1
