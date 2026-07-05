"""I1 — Kanıt Otobüsü testleri.

- collect() tüm kaynakları tek normalize listeye toplar.
- İZOLASYON: bir kaynak patlarsa atlanır, otobüs düşmez.
- viewmodel() kaynak/konu/hüküm sayaçları üretir.
- Gerçek kaynaklar crash'siz çalışır + kaynak damgaları geçerli.
"""
from __future__ import annotations

from packages.learning import evidence_bus as eb


def _fake_live():
    return [eb.EvidenceRecord(topic="signal_quality", subject="touche@NEUTRAL",
                              source=eb.LIVE, regime="NEUTRAL", n_samples=12,
                              statistic=0.6, verdict="DISCRIMINATES")]


def _fake_backtest():
    return [eb.EvidenceRecord(topic="quantum_discrimination", subject="quantum@DEFENSIVE",
                              source=eb.BACKTEST, regime="DEFENSIVE", n_samples=101,
                              statistic=0.005, verdict="DISCRIMINATES")]


def _boom():
    raise RuntimeError("kaynak patladi")


def test_collect_merges_sources(monkeypatch) -> None:
    monkeypatch.setattr(eb, "_SOURCES", (_fake_live, _fake_backtest))
    recs = eb.collect()
    assert len(recs) == 2
    assert {r.source for r in recs} == {eb.LIVE, eb.BACKTEST}
    assert recs[0].topic == "signal_quality"


def test_failing_source_is_isolated(monkeypatch) -> None:
    monkeypatch.setattr(eb, "_SOURCES", (_fake_live, _boom, _fake_backtest))
    recs = eb.collect()
    # patlayan kaynak atlanır, diğer ikisi gelir → otobüs düşmez
    assert len(recs) == 2


def test_viewmodel_summarizes(monkeypatch) -> None:
    monkeypatch.setattr(eb, "_SOURCES", (_fake_live, _fake_backtest))
    vm = eb.viewmodel()
    assert vm["total"] == 2
    assert vm["by_source"] == {eb.LIVE: 1, eb.BACKTEST: 1}
    assert vm["by_topic"]["signal_quality"] == 1
    assert vm["by_verdict"]["DISCRIMINATES"] == 2
    assert len(vm["records"]) == 2 and "topic" in vm["records"][0]


def test_real_sources_do_not_crash() -> None:
    """Gerçek kaynaklar (yerel veriyle) crash'siz; kaynak damgaları geçerli."""
    recs = eb.collect()
    assert isinstance(recs, list)
    valid = {eb.LIVE, eb.SHADOW, eb.BACKTEST}
    assert all(r.source in valid for r in recs)
