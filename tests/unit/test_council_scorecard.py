"""Konsey karnesi testleri — katmanlar-arası kombinasyon analizi.

Sentetik outcome setiyle: modül yayılımı yön/işaret doğru; sanki-filtreler
veriden türetilir (en kötü rejim/en iyi modül); az veri → INSUFFICIENT;
artifact yaz/oku turu.
"""
from __future__ import annotations

from packages.learning import council_scorecard as cs
from packages.learning import outcomes as om


def _entry(i, regime, pnl, conf, mc):
    fp = f"SYM|v2|4h|{regime}|bullish|S55|C|touche"
    return {
        "trade_id": f"t{i}", "symbol": "SYM", "side": "long", "timeframe": "4h",
        "opened_at": None, "closed_at": None,
        "opening_signal": {"fingerprint": fp, "data_verified": True,
                           "predicted_confidence": conf,
                           "module_contributions": mc},
        "exit": {},
        "outcome": {"entry_price": 100.0, "exit_price": 100.0 + pnl / 10,
                    "pnl_usd": pnl, "risk_pct": 0.02, "size_usd": 1000.0},
    }


def _synth_outcomes(n=80):
    """fundamental güçlü → kazanır; OFFENSIVE → kaybeder (bilinen yapı)."""
    outs = []
    for i in range(n):
        fund_strong = i % 2 == 0
        offensive = i % 4 == 3
        regime = "OFFENSIVE" if offensive else "NEUTRAL"
        win = fund_strong and not offensive
        pnl = 30.0 if win else -20.0
        mc = {"fundamental": 20.0 if fund_strong else 5.0, "touche": 15.0}
        conf = 0.45 if i % 3 == 0 else 0.30
        outs.append(om.build_outcome_from_log_entry(_entry(i, regime, pnl, conf, mc)))
    return outs


def test_insufficient_below_min_rows():
    rep = cs.compute(outcomes=_synth_outcomes(10))
    assert rep["status"] == "INSUFFICIENT"


def test_module_spread_finds_fundamental():
    """Yapıyı bilerek kurduk: fundamental yayılımı pozitif ve en üstte olmalı."""
    rep = cs.compute(outcomes=_synth_outcomes(80))
    assert rep["status"] == "OK"
    spreads = rep["module_spreads"]
    assert spreads, "yayılım tablosu boş olmamalı"
    top = spreads[0]
    assert top["module"] == "fundamental"
    assert top["win_spread"] > 30  # güçlü-vs-zayıf isabet farkı bariz


def test_what_if_derives_filters_from_data():
    """Sanki-filtreler veriden türetilir: en kötü rejim (OFFENSIVE) ve en iyi
    modülün (fundamental) zayıfı filtrelenir; konsey filtresi isabeti taşır."""
    rep = cs.compute(outcomes=_synth_outcomes(80))
    filters = {w["filter"]: w for w in rep["what_if"]}
    assert any("OFFENSIVE" in f for f in filters)
    assert any("fundamental-zayıfken" in f for f in filters)
    base = filters["taban (hepsi)"]
    combo = filters["üçü birden (konsey filtresi)"]
    assert combo["win_pct"] > base["win_pct"]


def test_run_if_due_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCIL_SCORECARD_PATH", str(tmp_path / "c.json"))
    monkeypatch.setattr(
        cs, "compute",
        lambda now=None, outcomes=None: {
            "generated_at": "2026-07-12T00:00:00+00:00",
            "engine": "council_scorecard_v1", "status": "OK", "n": 80},
    )
    assert cs.run_if_due()["status"] == "OK"
    vm = cs.viewmodel()
    assert vm["status"] == "OK" and vm["shadow_only"] is True
