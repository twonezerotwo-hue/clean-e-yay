"""I3 — Kaynak Seçici testleri.

- include_shadow(): DEFAULT OFF; yalnız truthy env ile ON.
- Flag OFF → salt-canlı: fallback-only rejim GÖRÜNMEZ, augmented boş (sızıntı yok).
- Flag ON → ince/boş rejime DAMGALI backtest fallback; canlı live_n kirlenmez.
- Canlı yeterli rejim flag ON'da bile augment EDİLMEZ (canlı önce).
- Fallback önceliği: backtest shadow'dan önce.
- Gerçek veriyle crash yok.
"""
from __future__ import annotations

from packages.learning import evidence_bus as eb
from packages.learning import source_selector as ss


def _live(regime: str, n: int):
    return eb.EvidenceRecord(topic="signal_quality", subject=f"touche@{regime}",
                             source=eb.LIVE, regime=regime, n_samples=n,
                             statistic=0.5, verdict="DISCRIMINATES")


def _backtest(regime: str, n: int):
    return eb.EvidenceRecord(topic="quantum_discrimination", subject=f"quantum@{regime}",
                             source=eb.BACKTEST, regime=regime, n_samples=n,
                             statistic=0.01, verdict="DISCRIMINATES")


def _shadow(regime: str, n: int):
    return eb.EvidenceRecord(topic="discovery_candidate", subject=f"shadow@{regime}",
                             source=eb.SHADOW, regime=regime, n_samples=n,
                             statistic=0.4, verdict="RESOLVED")


# NEUTRAL: canlı güçlü (40). OFFENSIVE: canlı ince (5) + backtest(80)+shadow(60).
# DEFENSIVE: canlı YOK, yalnız backtest(100).
_RECORDS = [
    _live("NEUTRAL", 40),
    _live("OFFENSIVE", 5),
    _backtest("OFFENSIVE", 80),
    _shadow("OFFENSIVE", 60),
    _backtest("DEFENSIVE", 100),
]


def test_flag_default_off(monkeypatch) -> None:
    monkeypatch.delenv(ss.FLAG, raising=False)
    assert ss.include_shadow() is False


def test_flag_truthy_values(monkeypatch) -> None:
    for v in ("1", "true", "YES", "on"):
        monkeypatch.setenv(ss.FLAG, v)
        assert ss.include_shadow() is True
    for v in ("0", "false", "", "no"):
        monkeypatch.setenv(ss.FLAG, v)
        assert ss.include_shadow() is False


def test_off_is_live_only(monkeypatch) -> None:
    """Flag OFF → hiçbir shadow/backtest kanıt sızmaz (salt-canlı)."""
    monkeypatch.delenv(ss.FLAG, raising=False)
    cov = ss.regime_coverage(records=_RECORDS)
    assert cov["include_shadow"] is False
    pr = cov["per_regime"]
    # fallback-only rejim (DEFENSIVE) OFF'ta GÖRÜNMEZ
    assert "DEFENSIVE" not in pr
    # hiçbir rejimde augmented yok
    assert all(not e["augmented"] for e in pr.values())
    # ince canlı rejim OFF'ta desteklenmez → source_used none
    assert pr["OFFENSIVE"]["source_used"] == "none"
    assert pr["NEUTRAL"]["source_used"] == "live"


def test_on_augments_thin_and_empty(monkeypatch) -> None:
    monkeypatch.setenv(ss.FLAG, "1")
    cov = ss.regime_coverage(records=_RECORDS)
    assert cov["include_shadow"] is True
    pr = cov["per_regime"]
    # boş canlı rejim (DEFENSIVE) artık görünür + backtest damgalı fallback
    assert pr["DEFENSIVE"]["live_n"] == 0 and pr["DEFENSIVE"]["thin"]
    assert pr["DEFENSIVE"]["source_used"] == eb.BACKTEST
    assert pr["DEFENSIVE"]["augmented"][0]["source"] == eb.BACKTEST
    # ince canlı rejim (OFFENSIVE) da desteklenir; canlı sayı KİRLENMEZ
    assert pr["OFFENSIVE"]["live_n"] == 5  # gerçek hücre değişmedi
    assert pr["OFFENSIVE"]["source_used"] == eb.BACKTEST


def test_live_sufficient_not_augmented(monkeypatch) -> None:
    """Canlı yeterli rejim flag ON'da bile fallback ALMAZ (canlı önce)."""
    monkeypatch.setenv(ss.FLAG, "1")
    pr = ss.regime_coverage(records=_RECORDS)["per_regime"]
    assert pr["NEUTRAL"]["source_used"] == "live"
    assert not pr["NEUTRAL"]["augmented"]


def test_fallback_priority_backtest_over_shadow() -> None:
    # OFFENSIVE'de hem backtest(80) hem shadow(60) var → backtest seçilir
    best = ss._best_fallback([_shadow("OFFENSIVE", 60), _backtest("OFFENSIVE", 80)])
    assert best is not None and best.source == eb.BACKTEST


def test_fallback_shadow_when_only_shadow() -> None:
    # yalnız shadow varsa shadow damgalı seçilir (shadow yolu ölü değil)
    best = ss._best_fallback([_shadow("CRISIS", 30)])
    assert best is not None and best.source == eb.SHADOW


def test_real_data_does_not_crash(monkeypatch) -> None:
    monkeypatch.delenv(ss.FLAG, raising=False)
    vm = ss.viewmodel()
    assert "per_regime" in vm and vm["include_shadow"] is False
