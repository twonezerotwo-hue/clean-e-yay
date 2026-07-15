"""2026-07-13 dış denetim düzeltmeleri — üç gölge dilimi (hepsi default KAPALI).

1. `touche_speaker_tf_only` — v4 artifact'ının tek yönü konuşmacı-dışı TF
   hücrelerine KOPYALANMAZ (açıkken); kapalıyken bayt-aynı + gözlem satırı.
2. (fundamental_v3 testleri 2026-07-15'te kaldırıldı — v3 canlı yoldan söküldü,
   5y tezgâh çürüttü; kıyas kaydı macro_backtest'te kaldı.)
3. `dominant_directional` — dominant modül nötr-50 merkezli |skor−50|×ağırlık
   ile seçilir (bearish modül de dominant olabilir); kapalıyken legacy birebir
   + ayrışınca `dominant_observe` gözlem satırı.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from packages.consensus import engine as ce
from packages.data.registry.loader import threshold_override
from packages.regime.classifier import RegimeLayer, RegimeOutput


def _write_artifact(path, per_symbol: dict) -> None:
    path.write_text(
        json.dumps(
            {"generated_at": datetime.now(UTC).isoformat(), "per_symbol": per_symbol},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    p = tmp_path / "tf_scoring_v2_shadow.json"
    monkeypatch.setenv("TF_SCORING_V2_SHADOW_PATH", str(p))
    return lambda per_symbol: _write_artifact(p, per_symbol)


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


# ── 1. touche_speaker_tf_only ────────────────────────────────────────────────

def test_tf_gate_off_copies_direction_with_observe(artifact):
    """Kapı KAPALI (default): konuşmacı-dışı hücre v4 yönünü almaya devam eder
    (mevcut davranış bayt-aynı) ama kanıt satırı yazılır (applied=no)."""
    artifact({"BTCUSD": {"direction_v4": 0.4, "direction_backup": 0.2, "speaker_tf": "1d"}})
    with threshold_override({"consensus": {"touche_v4": True, "touche_speaker_tf_only": False}}):
        res = ce.build("BTCUSD", _snap(60.0), _regime(), "4h")
    assert _module(res, "touche").score == pytest.approx(70.0)  # v4 kopyası (eski davranış)
    assert "touche_tf_gate_observe:speaker=1d:cell=4h:applied=no" in res.warnings


def test_tf_gate_on_suppresses_copy_falls_to_base(artifact):
    """Kapı AÇIK: konuşmacı-dışı hücrede v4/backup sustu → TF-duyarlı zemin motor."""
    artifact({"BTCUSD": {"direction_v4": 0.4, "direction_backup": 0.2, "speaker_tf": "1d"}})
    with threshold_override({"consensus": {"touche_v4": True, "touche_speaker_tf_only": True}}):
        res = ce.build("BTCUSD", _snap(60.0), _regime(), "4h")
    assert _module(res, "touche").score == pytest.approx(60.0)  # zemin motor
    assert "touche_tf_gate_observe:speaker=1d:cell=4h:applied=yes" in res.warnings
    # Kopya bastırıldı → touche_observe kademesi de zemin kullanır
    assert not any("used=v4" in w for w in res.warnings)


def test_tf_gate_on_speaker_cell_still_speaks(artifact):
    """Kapı AÇIK ama hücre = konuşmacı TF → v4 normal konuşur (kapı dokunmaz)."""
    artifact({"BTCUSD": {"direction_v4": 0.4, "direction_backup": 0.2, "speaker_tf": "4h"}})
    with threshold_override({"consensus": {"touche_v4": True, "touche_speaker_tf_only": True}}):
        res = ce.build("BTCUSD", _snap(60.0), _regime(), "4h")
    assert _module(res, "touche").score == pytest.approx(70.0)  # v4 kendi hücresinde
    assert not any(w.startswith("touche_tf_gate_observe") for w in res.warnings)


def test_tf_gate_legacy_artifact_without_speaker_unaffected(artifact):
    """Eski artifact'ta speaker_tf yok → kapı uygulanamaz, davranış eski (dürüst)."""
    artifact({"BTCUSD": {"direction_v4": 0.4, "direction_backup": 0.2}})
    with threshold_override({"consensus": {"touche_v4": True, "touche_speaker_tf_only": True}}):
        res = ce.build("BTCUSD", _snap(60.0), _regime(), "4h")
    assert _module(res, "touche").score == pytest.approx(70.0)
    assert not any(w.startswith("touche_tf_gate_observe") for w in res.warnings)


def test_touche_shadow_row_reads_speaker(artifact):
    artifact({"BTCUSD": {"direction_v4": 0.4, "direction_backup": -0.6, "speaker_tf": "1d"}})
    v4, bak, speaker = ce._touche_shadow_row("BTCUSD")
    assert v4 == pytest.approx(70.0) and bak == pytest.approx(20.0) and speaker == "1d"
    # Geriye-uyum sarmalayıcı aynı çifti döndürür
    assert ce._touche_shadow("BTCUSD") == (v4, bak)


# NOT: fundamental_v3 testleri 2026-07-15'te KALDIRILDI — v3 canlı yoldan
# söküldü (5y tezgâh çürüttü, M15). Kıyas kaydı macro_backtest'te (fund_v3
# analiz-referansı) test_macro_backtest kapsamında kalır.


# ── 3. dominant_directional ──────────────────────────────────────────────────

def _bearish_sentinel_setup():
    """Sentinel çok bearish (5), diğer modüller ~nötr → yön-katkı dominantı
    sentinel; legacy (score×weight) ise yüksek-skorlu bir modülü seçer."""
    layers = [
        RegimeLayer(name="Likidite", score=50.0, direction="neutral", evidence=[]),
        RegimeLayer(name="Risk İştahı", score=5.0, direction="risk_off", evidence=[]),
    ]
    return _snap(50.0), _regime(layers)


def test_dominant_off_is_legacy_with_observe(artifact):
    snap, regime = _bearish_sentinel_setup()
    with threshold_override({"consensus": {"dominant_directional": False}}):
        res = ce.build("BTCUSD", snap, regime, "4h")
    assert res.dominant_module != "sentinel"  # legacy bearish'i seçemez
    assert any(
        w.startswith("dominant_observe:legacy=") and w.endswith(":directional=sentinel")
        for w in res.warnings
    )


def test_dominant_on_picks_directional(artifact):
    snap, regime = _bearish_sentinel_setup()
    with threshold_override({"consensus": {"dominant_directional": True}}):
        res = ce.build("BTCUSD", snap, regime, "4h")
    assert res.dominant_module == "sentinel"  # |5−50|×w en büyük yön katkısı


def test_dominant_no_observe_when_agreeing(artifact):
    """İki hesap aynı modülü seçiyorsa gözlem satırı yazılmaz (gürültü yok)."""
    # Touche belirgin bullish (80), kalanlar nötr → hem legacy hem directional touche.
    with threshold_override({"consensus": {"dominant_directional": False}}):
        res = ce.build("BTCUSD", _snap(80.0), _regime(), "4h")
    if res.dominant_module == "touche":
        assert not any(w.startswith("dominant_observe") for w in res.warnings)
