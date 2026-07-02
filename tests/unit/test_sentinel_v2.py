"""M4 — sentinel v2 (çok-girdili stres kompoziti) testleri.

- Flag KAPALI (default): canlı skor v1 (yalnız VIX katmanı) — bayt-aynı
  regresyon; v2 yalnız gözlem satırında.
- Flag AÇIK: canlı skor v2 (VIX + realized-vol z + squeeze proxy + options).
- Eksik girdi ağırlığı kalanlara redistribute edilir (yalnız VIX varsa v2 == v1).
- DATA_POLICY: verified=False veya status!=OK girdi kompozite GİRMEZ.
- Shock durumunda volatility bileşeni 25 ile tavanlanır.
- Gözlem satırı `sentinel_v2_observe:v1=..:v2=..` her iki modda da yazılır.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.consensus import engine as ce
from packages.data.registry.loader import threshold_override
from packages.regime.classifier import RegimeLayer, RegimeOutput

_FLAG_ON = {"sentinel_v2": {"enabled": True}}


def _layer(name: str, score: float) -> RegimeLayer:
    return RegimeLayer(name=name, score=score, direction="neutral", evidence=[])


def _regime(vix_score: float = 80.0) -> RegimeOutput:
    return RegimeOutput(
        label="NEUTRAL",
        layers=[
            _layer("Likidite", 60.0),
            _layer("Risk İştahı", vix_score),
            _layer("Sermaye Rotasyonu", 40.0),
        ],
    )


def _vol(zscore: float | None, state: str = "normal", status: str = "OK", verified: bool = True):
    return SimpleNamespace(vol_zscore=zscore, vol_state=state, status=status, verified=verified)


def _deriv(squeeze: float | None, status: str = "OK", verified: bool = True):
    return SimpleNamespace(squeeze_proxy=squeeze, status=status, verified=verified)


def _opt(regime: str, status: str = "OK", verified: bool = True):
    return SimpleNamespace(regime=regime, status=status, verified=verified)


def _snap(volatility=None, derivatives=None, options=None):
    return SimpleNamespace(
        technicals_by_tf=None,
        technicals={},
        headlines=[],
        rotation=SimpleNamespace(score=42.0, direction="neutral", evidence=[], status="OK"),
        volatility=volatility or {},
        derivatives=derivatives or {},
        options=options or {},
    )


def test_v2_only_vix_equals_v1() -> None:
    """Diğer girdiler yoksa ağırlık VIX'e redistribute edilir → v2 == v1."""
    regime = _regime(vix_score=79.9)
    assert ce._sentinel_v2(regime, _snap(), "BTCUSD", "4h") == pytest.approx(79.9)


def test_v2_full_composite_math() -> None:
    """VIX 80 ×0.5 + vol(z=+1→25) ×0.25 + deriv(squeeze 40→60) ×0.15 + options
    NORMAL(70) ×0.10 = 40 + 6.25 + 9 + 7 = 62.25."""
    snap = _snap(
        volatility={"BTCUSD": {"4h": _vol(1.0)}},
        derivatives={"BTCUSD": _deriv(40.0)},
        options={"BTCUSD": _opt("NORMAL")},
    )
    assert ce._sentinel_v2(_regime(80.0), snap, "BTCUSD", "4h") == pytest.approx(62.25)


def test_v2_shock_caps_volatility_component() -> None:
    """Shock'ta vol bileşeni ≤25: z=-2 normalde 100 verirdi, shock 25'e kıstırır.
    VIX 80 ×(0.5/0.75) + 25 ×(0.25/0.75) = 53.33 + 8.33 = 61.67."""
    snap = _snap(volatility={"BTCUSD": {"4h": _vol(-2.0, state="shock")}})
    assert ce._sentinel_v2(_regime(80.0), snap, "BTCUSD", "4h") == pytest.approx(61.6667, abs=1e-3)


def test_v2_unverified_or_degraded_inputs_excluded() -> None:
    """DATA_POLICY: verified=False / status!=OK girdi kompozite girmez → v2 == v1."""
    snap = _snap(
        volatility={"BTCUSD": {"4h": _vol(2.0, verified=False)}},
        derivatives={"BTCUSD": _deriv(90.0, status="DEGRADED")},
        options={"BTCUSD": _opt("PUT_SKEW_STRESS", verified=False)},
    )
    assert ce._sentinel_v2(_regime(80.0), snap, "BTCUSD", "4h") == pytest.approx(80.0)


def test_v2_no_inputs_returns_none() -> None:
    """Hiç girdi yoksa (VIX dahil) skor uydurulmaz — modül düşer."""
    regime = RegimeOutput(label="NEUTRAL", layers=[_layer("Likidite", 60.0)])
    assert ce._sentinel_v2(regime, _snap(), "BTCUSD", "4h") is None


def test_flag_off_live_score_is_v1_with_observe_line() -> None:
    snap = _snap(volatility={"BTCUSD": {"4h": _vol(1.0)}})
    res = ce.build("BTCUSD", snap, _regime(80.0), "4h")
    sent = next(m for m in res.modules if m.name == "sentinel")
    assert sent.score == pytest.approx(80.0)  # v1 canlı (bayt-aynı)
    # v2: 80×(0.5/0.75) + 25×(0.25/0.75) = 61.7 — gözlem satırında yan yana
    assert any(w == "sentinel_v2_observe:v1=80.0:v2=61.7" for w in res.warnings)


def test_flag_on_live_score_is_v2() -> None:
    snap = _snap(volatility={"BTCUSD": {"4h": _vol(1.0)}})
    with threshold_override(_FLAG_ON):
        res = ce.build("BTCUSD", snap, _regime(80.0), "4h")
    sent = next(m for m in res.modules if m.name == "sentinel")
    assert sent.score == pytest.approx(61.67, abs=0.01)
    # gözlem satırı iki varyantı göstermeye devam eder (rollback kanıtı)
    assert any(w == "sentinel_v2_observe:v1=80.0:v2=61.7" for w in res.warnings)
    assert sum(m.weight for m in res.modules) == pytest.approx(1.0, abs=1e-3)


def test_flag_on_vix_missing_composite_survives() -> None:
    """v1 tek göstergesi (VIX) düştüğünde v2 kalan girdilerle yaşar — M4'ün
    kırılganlık gerekçesinin testi. v1=none → flag kapalı olsa modül düşerdi."""
    regime = RegimeOutput(label="NEUTRAL", layers=[_layer("Likidite", 60.0)])
    snap = _snap(derivatives={"BTCUSD": _deriv(40.0)})
    with threshold_override(_FLAG_ON):
        res = ce.build("BTCUSD", snap, regime, "4h")
    sent = next(m for m in res.modules if m.name == "sentinel")
    assert sent.score == pytest.approx(60.0)  # 100−40, ağırlık tümüyle deriv'e
    assert any(w == "sentinel_v2_observe:v1=none:v2=60.0" for w in res.warnings)


def test_custom_weights_from_config() -> None:
    snap = _snap(volatility={"BTCUSD": {"4h": _vol(0.0)}})  # vol bileşeni 50
    cfg = {"sentinel_v2": {"enabled": True, "weights": {"vix": 0.8, "volatility": 0.2}}}
    with threshold_override(cfg):
        res = ce.build("BTCUSD", snap, _regime(80.0), "4h")
    sent = next(m for m in res.modules if m.name == "sentinel")
    # deriv/options girdisi yok → 0.8/0.2 zaten normalize: 80×0.8 + 50×0.2 = 74
    assert sent.score == pytest.approx(74.0)
