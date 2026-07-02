"""T-1 — üst-TF hiza filtresi (`technical.htf_alignment`) testleri.

- Flag KAPALI (default): skor bayt-aynı; karşıtlıkta shadow satırı yazılır.
- Flag AÇIK: alt TF sinyali üst basamağın yönüne TERSse 50'ye doğru kısılır
  (karşıtlık gücüyle orantılı, çarpan [min_mult..1.0]).
- YALNIZ KÜÇÜLTÜR: aynı yön → dokunmaz (boost yok); üst TF nötr bandında
  (|lean|<5) → dokunmaz; üst TF verisi yok → dokunmaz; yön ASLA çevrilmez.
- 1d'nin üst basamağı yok → hiç etki yok.
"""
from __future__ import annotations

from types import SimpleNamespace

from packages.consensus import engine as ce
from packages.data.registry.loader import threshold_override

_FLAG_ON = {"technical": {"htf_alignment": {"enabled": True, "min_mult": 0.6}}}


def _tech(direction_score: float | None, timeframe: str) -> SimpleNamespace:
    return SimpleNamespace(
        status="OK",
        direction_score=direction_score,
        score=direction_score if direction_score is not None else 50.0,
        timeframe=timeframe,
    )


def _snap(by_tf: dict[str, float | None]) -> SimpleNamespace:
    return SimpleNamespace(
        technicals_by_tf={"BTCUSD": {tf: _tech(ds, tf) for tf, ds in by_tf.items()}},
        technicals={},
    )


def test_flag_off_score_identical_with_shadow_warning():
    # 15m long (70) vs 1h net short (20) — default'ta skor DEĞİŞMEZ, shadow satırı var.
    snap = _snap({"15m": 70.0, "1h": 20.0})
    score, warnings = ce._touche("BTCUSD", snap, "15m")
    assert score == 70.0
    assert any(w.startswith("htf_alignment_shadow:") for w in warnings)


def test_flag_on_opposing_htf_dampens_toward_neutral():
    snap = _snap({"15m": 70.0, "1h": 20.0})
    with threshold_override(_FLAG_ON):
        score, warnings = ce._touche("BTCUSD", snap, "15m")
    # htf lean = -30 → strength 0.6 → mult = 1 - 0.4*0.6 = 0.76 → 50 + 20*0.76 = 65.2
    assert score == 50.0 + 20.0 * 0.76
    assert 50.0 < score < 70.0  # kısıldı ama yön çevrilmedi
    assert any(w.startswith("htf_alignment:") for w in warnings)


def test_flag_on_full_opposition_uses_min_mult():
    # Üst TF tam uçta (0 → lean -50, strength 1.0) → çarpan tam min_mult.
    snap = _snap({"15m": 70.0, "1h": 0.0})
    with threshold_override(_FLAG_ON):
        score, _ = ce._touche("BTCUSD", snap, "15m")
    assert score == 50.0 + 20.0 * 0.6  # 62.0
    assert score > 50.0  # asla flip yok


def test_flag_on_aligned_htf_never_boosts():
    snap = _snap({"15m": 70.0, "1h": 80.0})
    with threshold_override(_FLAG_ON):
        score, warnings = ce._touche("BTCUSD", snap, "15m")
    assert score == 70.0
    assert not any("htf_alignment" in w for w in warnings)


def test_flag_on_neutral_htf_band_untouched():
    # Üst TF 47 (|lean|=3 < 5 nötr bandı) → sönümleme yok.
    snap = _snap({"15m": 70.0, "1h": 47.0})
    with threshold_override(_FLAG_ON):
        score, warnings = ce._touche("BTCUSD", snap, "15m")
    assert score == 70.0
    assert not any("htf_alignment" in w for w in warnings)


def test_flag_on_missing_htf_untouched():
    snap = _snap({"15m": 70.0})  # 1h hücresi yok
    with threshold_override(_FLAG_ON):
        score, warnings = ce._touche("BTCUSD", snap, "15m")
    assert score == 70.0
    assert not any("htf_alignment" in w for w in warnings)


def test_1d_has_no_higher_step():
    snap = _snap({"1d": 70.0})
    with threshold_override(_FLAG_ON):
        score, warnings = ce._touche("BTCUSD", snap, "1d")
    assert score == 70.0
    assert not any("htf_alignment" in w for w in warnings)


def test_bearish_ltf_against_bullish_htf_dampens_symmetrically():
    # Ayna senaryo: 15m short (30) vs 1h long (80 → lean +30, strength 0.6).
    snap = _snap({"15m": 30.0, "1h": 80.0})
    with threshold_override(_FLAG_ON):
        score, _ = ce._touche("BTCUSD", snap, "15m")
    assert score == 50.0 - 20.0 * 0.76  # 34.8 — hâlâ bearish tarafta
    assert 30.0 < score < 50.0


def test_ladder_uses_one_step_up_only():
    # 15m'in basamağı 1h'tir; 4h ters olsa bile 1h aynı yönse dokunulmaz.
    snap = _snap({"15m": 70.0, "1h": 70.0, "4h": 10.0})
    with threshold_override(_FLAG_ON):
        score, _ = ce._touche("BTCUSD", snap, "15m")
    assert score == 70.0
