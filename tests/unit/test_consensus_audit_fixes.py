"""2026-07-13 dış denetim düzeltmelerinin canlı hali.

- Baskın modül nötr-50 merkezli |skor−50|×ağırlık ile seçilir (ayı modül de baskın olabilir).
- 4h kalibrasyon düşürmesi: ters ölçülen modül o TF'nin canlı oyundan çıkar, skoru izlenebilir.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from packages.consensus import engine as ce
from packages.data.registry.loader import threshold_override
from packages.regime.classifier import RegimeLayer, RegimeOutput


def _snap(direction_score: float = 60.0, tf: str = "4h"):
    tech = SimpleNamespace(
        direction_score=direction_score, status="OK", timeframe=tf, score=direction_score
    )
    return SimpleNamespace(
        technicals_by_tf={"BTCUSD": {tf: tech}},
        technicals={},
        headlines=[],
        rotation=SimpleNamespace(score=50.0, direction="neutral", evidence=[], status="OK"),
        volatility={},
        derivatives={},
        options={},
    )


def _regime(layers=None, label="NEUTRAL"):
    if layers is None:
        layers = [
            RegimeLayer(name="Likidite", score=55.0, direction="neutral", evidence=[]),
            RegimeLayer(name="Risk İştahı", score=60.0, direction="neutral", evidence=[]),
        ]
    return RegimeOutput(label=label, layers=layers)


def _module(res, name):
    return next(m for m in res.modules if m.name == name)


def _bearish_sentinel_setup():
    """Sentinel çok bearish (5), diğer modüller ~nötr → yön-katkı dominantı
    sentinel; legacy (score×weight) ise yüksek-skorlu bir modülü seçer."""
    layers = [
        RegimeLayer(name="Likidite", score=50.0, direction="neutral", evidence=[]),
        RegimeLayer(name="Risk İştahı", score=5.0, direction="risk_off", evidence=[]),
    ]
    return _snap(50.0), _regime(layers)


def test_dominant_is_directional_contribution():
    snap, regime = _bearish_sentinel_setup()
    res = ce.build("BTCUSD", snap, regime, "4h")
    assert res.dominant_module == "sentinel"  # |5−50|×w en büyük yön katkısı


def test_4h_calibration_drop_is_live_only_and_traceable():
    """4h inverse modules leave the live vote, with their scores auditable."""
    snap_4h = _snap(60.0, "4h")
    snap_4h.generated_at = datetime.now(UTC)
    snap_1h = _snap(60.0, "1h")
    snap_1h.generated_at = datetime.now(UTC)
    with threshold_override({"consensus": {"timeframe_module_drop": {"4h": ["fundamental"]}}}):
        four_hour = ce.build("BTCUSD", snap_4h, _regime(), "4h")
        one_hour = ce.build("BTCUSD", snap_1h, _regime(), "1h")

    assert "fundamental" not in {m.name for m in four_hour.modules}
    assert any(w.startswith("timeframe_module_drop:4h:fundamental:score=") for w in four_hour.warnings)
    assert "fundamental" in {m.name for m in one_hour.modules}
