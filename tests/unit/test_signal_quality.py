"""FAZ-4 — sinyal kalitesi ayrım karnesi testleri.

- Rejim başına modül: kazanan katkısı > kaybeden → DISCRIMINATES; tersi INVERSE;
  eşit → FLAT; az örnek → INSUFFICIENT.
- Rejim ayrımı bağımsız (aynı modül bir rejimde ayırır, başkasında ayırmaz).
- pnl==0 başabaş + vektörsüz outcome karneye girmez.
- SALT-GÖZLEM: karne yalnız regime/pnl/module_contributions okur.
"""
from __future__ import annotations

from types import SimpleNamespace

from packages.learning import signal_quality as sq


def _o(regime: str, pnl: float, contribs: dict | None) -> SimpleNamespace:
    return SimpleNamespace(regime=regime, pnl=pnl, module_contributions=contribs)


def test_discriminates_when_win_contrib_higher() -> None:
    outs = [_o("NEUTRAL", +1.0, {"touche": 40.0, "news": 10.0}) for _ in range(6)] + [
        _o("NEUTRAL", -1.0, {"touche": 10.0, "news": 10.0}) for _ in range(6)
    ]
    card = sq.regime_module_scorecard(outs)
    touche = card["per_regime"]["NEUTRAL"]["touche"]
    assert touche["verdict"] == "DISCRIMINATES"
    assert touche["separation"] > 0
    # news kazanan/kaybeden eşit katkı → ayırt etmiyor
    assert card["per_regime"]["NEUTRAL"]["news"]["verdict"] == "FLAT"


def test_inverse_when_loss_contrib_higher() -> None:
    outs = [_o("DEFENSIVE", +1.0, {"quantum": 10.0}) for _ in range(6)] + [
        _o("DEFENSIVE", -1.0, {"quantum": 40.0}) for _ in range(6)
    ]
    q = sq.regime_module_scorecard(outs)["per_regime"]["DEFENSIVE"]["quantum"]
    assert q["verdict"] == "INVERSE"
    assert q["separation"] < 0


def test_insufficient_below_min_samples() -> None:
    outs = [_o("NEUTRAL", +1.0, {"touche": 40.0}) for _ in range(2)] + [
        _o("NEUTRAL", -1.0, {"touche": 10.0}) for _ in range(2)
    ]
    t = sq.regime_module_scorecard(outs)["per_regime"]["NEUTRAL"]["touche"]
    assert t["verdict"] == "INSUFFICIENT"
    assert t["n_win"] == 2 and t["n_loss"] == 2


def test_regime_split_independent() -> None:
    """touche NEUTRAL'da ayırır, DEFENSIVE'de (eşit katkı) ayırmaz."""
    outs = (
        [_o("NEUTRAL", +1.0, {"touche": 40.0}) for _ in range(6)]
        + [_o("NEUTRAL", -1.0, {"touche": 10.0}) for _ in range(6)]
        + [_o("DEFENSIVE", +1.0, {"touche": 20.0}) for _ in range(6)]
        + [_o("DEFENSIVE", -1.0, {"touche": 20.0}) for _ in range(6)]
    )
    card = sq.regime_module_scorecard(outs)
    assert card["per_regime"]["NEUTRAL"]["touche"]["verdict"] == "DISCRIMINATES"
    assert card["per_regime"]["DEFENSIVE"]["touche"]["verdict"] == "FLAT"


def test_breakeven_and_missing_vectors_excluded() -> None:
    outs = [_o("NEUTRAL", 0.0, {"touche": 99.0}) for _ in range(10)] + [
        _o("NEUTRAL", +1.0, None) for _ in range(10)
    ]
    card = sq.regime_module_scorecard(outs)
    # başabaş + vektörsüz → hiç modül toplanmaz
    assert card["per_regime"]["NEUTRAL"] == {}


def test_summary_and_overall_present() -> None:
    outs = [_o("NEUTRAL", +1.0, {"touche": 40.0}) for _ in range(6)] + [
        _o("NEUTRAL", -1.0, {"touche": 10.0}) for _ in range(6)
    ]
    card = sq.regime_module_scorecard(outs)
    assert "touche@NEUTRAL" in card["summary"]
    assert card["overall"]["touche"]["verdict"] == "DISCRIMINATES"
    assert "salt-gözlem" in card["note"]
