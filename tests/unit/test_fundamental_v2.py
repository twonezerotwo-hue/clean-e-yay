"""M3 — fundamental v2 (Kripto Momentum hariç; BTC çifte sayımı fix) testleri.

- Flag KAPALI (default): canlı skor v1 (Likidite+Kripto+Rotasyon ortalaması)
  — bayt-aynı regresyon; v2 yalnız gözlem satırında.
- Flag AÇIK: canlı skor v2 (Likidite+Rotasyon; Kripto Momentum HARİÇ).
- v2 katmansız kalırsa (yalnız kripto katmanı varken flag açık) modül düşer.
- Gözlem satırı `fundamental_v2_observe:v1=..:v2=..` her iki modda da yazılır.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.consensus import engine as ce
from packages.data.registry.loader import threshold_override
from packages.regime.classifier import RegimeLayer, RegimeOutput

_FLAG_ON = {"consensus": {"fundamental_v2": True}}


def _layer(name: str, score: float) -> RegimeLayer:
    return RegimeLayer(name=name, score=score, direction="neutral", evidence=[])


def _regime(*layers: RegimeLayer) -> RegimeOutput:
    return RegimeOutput(label="NEUTRAL", layers=list(layers))


def _snap():
    return SimpleNamespace(
        technicals_by_tf=None,
        technicals={},
        headlines=[],
        rotation=SimpleNamespace(score=42.0, direction="neutral", evidence=[], status="OK"),
    )


# Likidite 90 + Kripto 40 + Rotasyon 30 → v1 = 53.33; v2 (kripto hariç) = 60.0
_LAYERS = (
    _layer("Likidite", 90.0),
    _layer("Risk İştahı", 80.0),
    _layer("Kripto Momentum", 40.0),
    _layer("Sermaye Rotasyonu", 30.0),
)


def test_helpers_v1_vs_v2() -> None:
    regime = _regime(*_LAYERS)
    assert ce._fundamental(regime) == pytest.approx(53.3333, abs=1e-3)
    assert ce._fundamental_v2(regime) == pytest.approx(60.0)


def test_flag_off_live_score_is_v1_with_observe_line() -> None:
    res = ce.build("BTCUSD", _snap(), _regime(*_LAYERS), "1d")
    fund = next(m for m in res.modules if m.name == "fundamental")
    assert fund.score == pytest.approx(53.33, abs=0.01)  # v1 canlı (bayt-aynı)
    assert any(w == "fundamental_v2_observe:v1=53.3:v2=60.0" for w in res.warnings)


def test_flag_on_live_score_is_v2() -> None:
    with threshold_override(_FLAG_ON):
        res = ce.build("BTCUSD", _snap(), _regime(*_LAYERS), "1d")
    fund = next(m for m in res.modules if m.name == "fundamental")
    assert fund.score == pytest.approx(60.0)
    # gözlem satırı iki varyantı göstermeye devam eder (rollback kanıtı)
    assert any(w == "fundamental_v2_observe:v1=53.3:v2=60.0" for w in res.warnings)


def test_flag_on_drops_module_when_only_crypto_layer() -> None:
    """F2-3 dürüst modda yalnız kripto katmanı kalmışsa: v1 yaşar (40), v2
    katmansız → flag açıkken modül düşer + redistribute."""
    regime = _regime(_layer("Risk İştahı", 80.0), _layer("Kripto Momentum", 40.0))
    with threshold_override(_FLAG_ON):
        res = ce.build("BTCUSD", _snap(), regime, "1d")
    assert "fundamental" not in {m.name for m in res.modules}
    assert any(w.startswith("fundamental_dropped:") for w in res.warnings)
    assert any(w == "fundamental_v2_observe:v1=40.0:v2=none" for w in res.warnings)
    assert sum(m.weight for m in res.modules) == pytest.approx(1.0, abs=1e-3)
    # aynı rejimde flag KAPALI → v1 (40.0) canlı kalır (regresyon)
    res_off = ce.build("BTCUSD", _snap(), regime, "1d")
    fund = next(m for m in res_off.modules if m.name == "fundamental")
    assert fund.score == pytest.approx(40.0)
