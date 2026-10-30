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
from packages.regime.classifier import RegimeLayer, RegimeOutput


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


def test_v2_excludes_crypto_momentum() -> None:
    assert ce._fundamental_v2(_regime(*_LAYERS)) == pytest.approx(60.0)  # Likidite + Rotasyon


def test_live_score_is_v2_when_v4_archive_missing(monkeypatch) -> None:
    monkeypatch.setattr(ce, "_fundamental_v4", lambda: None)
    res = ce.build("BTCUSD", _snap(), _regime(*_LAYERS), "1d")
    fund = next(m for m in res.modules if m.name == "fundamental")
    assert fund.score == pytest.approx(60.0)
    assert "fundamental_fallback:v2:BTCUSD:1d" in res.warnings


def test_live_score_is_v4_when_archive_present(monkeypatch) -> None:
    monkeypatch.setattr(ce, "_fundamental_v4", lambda: 22.0)
    res = ce.build("BTCUSD", _snap(), _regime(*_LAYERS), "1d")
    assert next(m for m in res.modules if m.name == "fundamental").score == pytest.approx(22.0)
    assert not any(w.startswith("fundamental_fallback") for w in res.warnings)


def test_drops_module_when_only_crypto_layer(monkeypatch) -> None:
    """Yalnız kripto katmanı kalmışsa v2 katmansız → modül düşer, ağırlık dağılır."""
    monkeypatch.setattr(ce, "_fundamental_v4", lambda: None)
    regime = _regime(_layer("Risk İştahı", 80.0), _layer("Kripto Momentum", 40.0))
    res = ce.build("BTCUSD", _snap(), regime, "1d")
    assert "fundamental" not in {m.name for m in res.modules}
    assert any(w.startswith("fundamental_dropped:") for w in res.warnings)
    assert sum(m.weight for m in res.modules) == pytest.approx(1.0, abs=1e-3)
