"""B-3 (2026-07-05) — challenger ağırlık eğitimi + quantum ayrım karnesi (cat 6).

Pinlenen sözleşme:
- İZOLASYON: run() yalnız izole rapora yazar; canlı aktif ağırlıklara dokunmaz.
- Champion matematiği REUSE: challenger ağırlık = auto_weight_trainer._propose_
  for_regime (aynı constraint'ler; toplam ~1.0, drift sınırlı).
- win_rate = WIN/(WIN+LOSS): FLAT paydadan düşer (codebase konvansiyonu).
- quantum karnesi: separation = mean(fr|q≥55) − mean(fr|q≤45); >eps DISCRIMINATES,
  <-eps INVERSE. Quantum dominant olmasa da ölçülür.
- Yetersiz veri → INSUFFICIENT/NO_DATA (uydurma yok). Determinizm.
"""
from __future__ import annotations

from packages.data.registry.loader import active_weights_version, load_active_weights
from packages.learning import challenger_trainer as ct


def _rec(regime, module, label, dir_return, q_score=50.0, fwd=None):
    return {
        "regime_label": regime,
        "dominant_module": module,
        "label": label,
        "directional_return": dir_return,
        "forward_return": dir_return if fwd is None else fwd,
        "module_contributions": {
            "quantum": {"score": q_score, "weight": 0.1, "contribution": round(q_score * 0.1, 3)}
        },
    }


def _two_module_regime(regime="NEUTRAL", n_each=6):
    """İki modül, her biri ≥MIN → PROPOSED olabilsin."""
    recs = []
    for _ in range(n_each):
        recs.append(_rec(regime, "touche", "WIN", 0.03))
        recs.append(_rec(regime, "sentinel", "LOSS", -0.03))
    return recs


# ---------------------------------------------------------------- izolasyon

def test_run_no_data_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKTEST_CHALLENGER_REPORT_PATH", str(tmp_path / "rep.json"))
    rep = ct.run(records=[])
    assert rep["status"] == "NO_DATA"
    assert (tmp_path / "rep.json").exists()


def test_isolation_no_live_weight_change(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKTEST_CHALLENGER_REPORT_PATH", str(tmp_path / "rep.json"))
    before = active_weights_version()
    rep = ct.run(records=_two_module_regime())
    after = active_weights_version()
    assert before == after  # canlı ağırlık versiyonu DEĞİŞMEDİ
    # Rapordaki champion = canlı aktif ağırlık (okundu, yazılmadı).
    champ = rep["regimes"]["NEUTRAL"]["champion_weights"]
    live = load_active_weights()["regimes"]["NEUTRAL"]
    assert champ == live


# ---------------------------------------------------------------- ağırlık math

# Champion ağırlıkları PİNLE — test ortamdan bağımsız olsun (aktif weights
# lokalde untracked, CI'da baseline; sabit taban → deterministik kıyas).
_PINNED_WEIGHTS = {
    "regimes": {
        "NEUTRAL": {"touche": 0.40, "fundamental": 0.20, "news": 0.15, "sentinel": 0.15, "quantum": 0.10},
        "OFFENSIVE": {"touche": 0.40, "fundamental": 0.20, "news": 0.15, "sentinel": 0.15, "quantum": 0.10},
        "DEFENSIVE": {"touche": 0.30, "fundamental": 0.25, "news": 0.15, "sentinel": 0.20, "quantum": 0.10},
        "CRISIS": {"touche": 0.20, "fundamental": 0.30, "news": 0.15, "sentinel": 0.25, "quantum": 0.10},
    },
    "constraints": {"min_module_floor": 0.02, "max_delta_per_module": 0.03, "max_total_drift": 0.10},
}


def test_reuses_champion_math(monkeypatch, tmp_path):
    """Challenger ağırlık = champion `_propose_for_regime` reuse: normalize (sum≈1),
    geçerli dağılım, her champion modülü için delta. (Per-modül delta sınırı
    normalizasyon SONRASI garanti DEĞİL — o yüzden asıl değişmezleri doğrularız.)"""
    monkeypatch.setenv("BACKTEST_CHALLENGER_REPORT_PATH", str(tmp_path / "rep.json"))
    monkeypatch.setattr(ct, "load_active_weights", lambda: _PINNED_WEIGHTS)
    rep = ct.run(records=_two_module_regime())
    d = rep["regimes"]["NEUTRAL"]
    assert d["status"] == "PROPOSED"
    w = d["challenger_weights"]
    assert abs(sum(w.values()) - 1.0) < 1e-3          # normalize (trainer sözleşmesi)
    assert all(0.0 < v <= 1.0 for v in w.values())    # geçerli dağılım
    assert d["champion_weights"] == _PINNED_WEIGHTS["regimes"]["NEUTRAL"]  # okundu, yazılmadı
    assert {x["module"] for x in d["deltas"]} == set(_PINNED_WEIGHTS["regimes"]["NEUTRAL"])


def test_win_rate_excludes_flat():
    """touche: 3 WIN + 1 LOSS + 2 FLAT → win_rate = 3/(3+1) = 0.75, trades = 6."""
    recs = (
        [_rec("NEUTRAL", "touche", "WIN", 0.03) for _ in range(3)]
        + [_rec("NEUTRAL", "touche", "LOSS", -0.03)]
        + [_rec("NEUTRAL", "touche", "FLAT", 0.001) for _ in range(2)]
    )
    perfs = ct._perfs_for(recs)
    assert len(perfs) == 1
    p = perfs[0]
    assert p.module == "touche"
    assert p.trades == 6
    assert p.wins == 3
    assert p.win_rate == 0.75


def test_insufficient_regime_status(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKTEST_CHALLENGER_REPORT_PATH", str(tmp_path / "rep.json"))
    # Tek modül → çeşitlilik yok → INSUFFICIENT.
    recs = [_rec("NEUTRAL", "touche", "WIN", 0.03) for _ in range(6)]
    rep = ct.run(records=recs)
    assert rep["regimes"]["NEUTRAL"]["status"] == "INSUFFICIENT"


# ---------------------------------------------------------------- quantum karne

def _quantum_regime(bull_fwd, bear_fwd, regime="DEFENSIVE", n=5):
    recs = []
    for _ in range(n):
        recs.append(_rec(regime, "touche", "WIN", 0.01, q_score=60.0, fwd=bull_fwd))
        recs.append(_rec(regime, "touche", "LOSS", -0.01, q_score=40.0, fwd=bear_fwd))
    return recs


def test_quantum_scorecard_discriminates():
    # Yüksek quantum → yüksek forward-return → DISCRIMINATES.
    recs = _quantum_regime(bull_fwd=0.02, bear_fwd=-0.02)
    sc = ct.quantum_scorecard(recs)["per_regime"]["DEFENSIVE"]
    assert sc["status"] == "OK"
    assert sc["separation"] > 0
    assert sc["verdict"] == "DISCRIMINATES"


def test_quantum_scorecard_inverse():
    # Yüksek quantum → DÜŞÜK forward-return → INVERSE (TERS).
    recs = _quantum_regime(bull_fwd=-0.02, bear_fwd=0.02)
    sc = ct.quantum_scorecard(recs)["per_regime"]["DEFENSIVE"]
    assert sc["separation"] < 0
    assert sc["verdict"] == "INVERSE"


def test_quantum_scorecard_insufficient():
    recs = _quantum_regime(bull_fwd=0.02, bear_fwd=-0.02, n=2)  # 4 kayıt < min 8
    sc = ct.quantum_scorecard(recs)["per_regime"]["DEFENSIVE"]
    assert sc["status"] == "INSUFFICIENT"


def test_pearson_guards():
    assert ct._pearson([1.0, 2.0], [1.0, 2.0]) is None       # n<3
    assert ct._pearson([5.0, 5.0, 5.0], [1.0, 2.0, 3.0]) is None  # sıfır varyans


# ---------------------------------------------------------------- determinizm

def test_deterministic(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKTEST_CHALLENGER_REPORT_PATH", str(tmp_path / "rep.json"))
    recs = _two_module_regime() + _quantum_regime(0.02, -0.02)
    r1 = ct.run(records=list(recs))
    r2 = ct.run(records=list(recs))
    assert r1["regimes"] == r2["regimes"]
    assert r1["quantum_scorecard"] == r2["quantum_scorecard"]
