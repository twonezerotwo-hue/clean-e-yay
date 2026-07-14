"""Momentum-Likidite rejim katmanı (Basamak-4 CRISIS-maskesi düzeltmesi).

Kök neden: seviye-Likidite formülü 5y'da ≥55'e sıkışıp rejim ortalamasını
şişiriyor → CRISIS maskeleniyor. Flag açıkken Likidite katmanı DEĞİŞİM-bazlı
(momentum, M16 v4) → seviye şişmesi kırılır. Default KAPALI = bayt-aynı.
NOT (M19 birleştirme): tek anahtar artık `consensus.fundamental_v4` (eski
ayrı `regime.liquidity_momentum` kaldırıldı — fundamental + rejim tek düğme).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.data.registry.loader import threshold_override
from packages.regime import classifier as rc


@pytest.fixture
def macro_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("BAR_HISTORY_ENABLED", "1")
    monkeypatch.setenv("BAR_HISTORY_DIR", str(tmp_path))
    rc._LIQ_MOM_MEMO["key"] = None

    def _write(sym: str, closes: list[float]) -> None:
        base = datetime(2021, 1, 1, tzinfo=UTC)
        lines = [
            json.dumps({
                "symbol": sym, "timeframe": "1d",
                "ts": (base + timedelta(days=i)).isoformat(),
                "open": c, "high": c, "low": c, "close": c,
                "volume": 0.0, "source": "test", "verified": True,
            })
            for i, c in enumerate(closes)
        ]
        (tmp_path / f"{sym}_1d.jsonl").write_text("\n".join(lines), encoding="utf-8")

    return _write


# v4.1 yüzdelik semantiği: rejim-değişimli seri (önce sakin, sonra sert
# hareket) — sıkılaşma İVMESİ kendi yılının tepesinde olsun (saf-monoton seri
# rank ortasında kalır; sakin faz gürültülü, vol=0 ekseni None yapar).
def _tighten(n=300, base=100.0, step=0.5, burst=60):
    """Uzun sakin + SON 60 gün sert yükseliş (ivme pencerenin tepesinde)."""
    calm = [base + (0.2 if i % 2 else -0.2) for i in range(n - burst)]
    return calm + [calm[-1] + step * i for i in range(burst)]


def _snap(dxy=104.0, us10=4.3):
    q = lambda s, p: SimpleNamespace(symbol=s, price=p)  # noqa: E731
    return SimpleNamespace(prices=[q("DXY", dxy), q("US10Y", us10), q("US02Y", 4.3)])


def _liq(snap):
    return rc._liquidity_layer(snap, drop_missing=True)


def test_flag_off_is_level_formula(macro_archive):
    """Flag KAPALIYKEN seviye formülü birebir (arşiv okunmaz). Flag artık
    CANLI (2026-07-13) → kapalı-davranış testi explicit kapatır."""
    macro_archive("DXY", _tighten())
    macro_archive("US10Y", _tighten(base=4.0, step=0.02))
    with threshold_override({"consensus": {"fundamental_v4": False}}):
        layer = _liq(_snap(dxy=104.0, us10=4.3))
    # Seviye: 100 - (104-100)*2 - (4.3-4)*5 = 100-8-1.5 = 90.5
    assert layer.score == pytest.approx(90.5)
    assert "momentum" not in " ".join(layer.evidence)


def test_flag_on_uses_momentum(macro_archive):
    from packages.data.providers.rotation import flow
    macro_archive("DXY", _tighten())     # DXY yükseliyor → sıkılaşma
    macro_archive("US10Y", _tighten(base=4.0, step=0.02))
    expected = flow.liquidity_momentum_score(_tighten(), _tighten(base=4.0, step=0.02))
    with threshold_override({"consensus": {"fundamental_v4": True}}):
        layer = _liq(_snap(dxy=104.0, us10=4.3))
    assert layer.score == pytest.approx(round(expected, 1))
    assert layer.score < 50.0  # sıkılaşma → düşük (seviye 90.5 olurdu — şişme kırıldı)
    assert "momentum" in " ".join(layer.evidence)


def test_flag_on_no_archive_falls_back_to_level(monkeypatch, tmp_path):
    """Flag açık ama arşiv yok → seviye formülüne düşer (dürüst degrade)."""
    monkeypatch.setenv("BAR_HISTORY_ENABLED", "1")
    monkeypatch.setenv("BAR_HISTORY_DIR", str(tmp_path))  # boş
    rc._LIQ_MOM_MEMO["key"] = None
    with threshold_override({"consensus": {"fundamental_v4": True}}):
        layer = _liq(_snap(dxy=104.0, us10=4.3))
    assert layer.score == pytest.approx(90.5)  # seviye formülü (v4 üretemedi)


def test_crisis_visible_with_momentum(macro_archive):
    """Bütünsel: DXY+faiz güçlü yükseliş + VIX kriz + varlıklar çöküş →
    momentum-Likidite ile rejim CRISIS/DEFENSIVE olabilir (seviye ile OFFENSIVE)."""
    macro_archive("DXY", _tighten(step=0.6))
    macro_archive("US10Y", _tighten(base=4.0, step=0.02))
    snap = SimpleNamespace(
        prices=[
            SimpleNamespace(symbol="DXY", price=118.0),
            SimpleNamespace(symbol="US10Y", price=5.5),
            SimpleNamespace(symbol="US02Y", price=5.5),
            SimpleNamespace(symbol="VIX", price=45.0),
        ],
        technicals={"BTCUSD": SimpleNamespace(score=10.0, rsi=20.0, ema_stack="bearish")},
        rotation=SimpleNamespace(score=15.0, direction="risk_off", evidence=[], status="OK"),
    )
    with threshold_override({"consensus": {"fundamental_v4": True}, "regime": {"drop_unavailable_layers": True}}):
        out_mom = rc.classify(snap, stateful=False)
    with threshold_override({"consensus": {"fundamental_v4": False}, "regime": {"drop_unavailable_layers": True}}):
        out_lvl = rc.classify(snap, stateful=False)
    order = ["CRISIS", "DEFENSIVE", "NEUTRAL", "OFFENSIVE"]
    # Momentum varyantı en az seviye kadar (veya daha) karamsar rejim üretir.
    assert order.index(out_mom.label) <= order.index(out_lvl.label)
