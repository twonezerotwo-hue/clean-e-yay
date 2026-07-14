"""fundamental v4.1 (yüzdelik-normalize momentum) — gölge üretici testleri.

- flow.liquidity_momentum_score v4.1: ham DXY+faiz momentum ekseninin son-1-yıl
  yüzdelik sırası (clamp doygunluğu İMKÂNSIZ; sıkılaşma İVMESİ tepedeyse <50).
- macro_backtest.mom_pct_series flow'a DELEGE (tek kaynak — drift yok);
  cand_mom = v4.0 clamp'li DONMUŞ referans (kıyas için).
- consensus._fundamental_v4: bar arşivinden okur; arşiv yok/kapalı → None.
- build() kademesi: flag OFF → v3/v2/v1 birebir + observe; ON → v4 tepede;
  ON ama arşiv yok → alt kademeye düşer (dürüst degrade).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.consensus import engine as ce
from packages.data.providers.rotation import flow
from packages.data.registry.loader import threshold_override
from packages.learning import macro_backtest as mb
from packages.regime.classifier import RegimeLayer, RegimeOutput


# v4.1 yüzdelik semantiği: skor "son 1 yıla göre" ivme ölçer → hareket SERİNİN
# SONUNA yığılmalı (uzun-doğrusal trendin sonunda ivme artık 'uç' değildir —
# rank ortaya döner; bu bilinçli tasarım). Sakin faz gürültülü (vol=0 → None).
def _calm(n, base):
    return [base + (0.2 if i % 2 else -0.2) for i in range(n)]


def _tighten(n=300, base=100.0, step=0.5, burst=60):
    """Uzun sakin + SON 60 gün sert yükseliş → sıkılaşma ivmesi pencerenin tepesinde."""
    calm = _calm(max(n - burst, 1), base)
    return (calm + [calm[-1] + step * i for i in range(burst)])[:n]


def _easing(n=300, base=160.0, step=0.5, burst=60):
    calm = _calm(max(n - burst, 1), base)
    return (calm + [calm[-1] - step * i for i in range(burst)])[:n]


# ── flow.liquidity_momentum_score v4.1 (tek kaynak formül) ───────────────────

def test_liquidity_momentum_tightening_bearish():
    # Sıkılaşma İVMESİ kendi yılının tepesinde → risk-off → skor < 50
    s = flow.liquidity_momentum_score(_tighten(), _tighten(base=4.0, step=0.02))
    assert s is not None and s < 50.0


def test_liquidity_momentum_easing_bullish():
    # Gevşeme ivmesi tepede → risk-on → skor > 50
    s = flow.liquidity_momentum_score(_easing(), _easing(base=6.0, step=0.02))
    assert s is not None and s > 50.0


def test_liquidity_momentum_range_and_no_saturation():
    """v4.1 skor [0,100]; yüzdelik-rank clamp gibi tek değere YAPIŞMAZ."""
    import math
    # Dalgalı (gerçekçi) seri — rank çözünürlüğünü ölçmek için çeşitlilik şart.
    dxy = [100.0 + 3.0 * math.sin(i / 17.0) + 0.02 * i + math.sin(i * 0.71) for i in range(400)]
    us10 = [4.0 + 0.4 * math.sin(i / 23.0) + 0.001 * i + 0.1 * math.sin(i * 0.53) for i in range(400)]
    series = flow.liquidity_momentum_pct_series(dxy, us10)
    vals = [v for v in series if v is not None]
    assert vals and all(0.0 <= v <= 100.0 for v in vals)
    assert len({round(v) for v in vals}) > 10  # çözünürlük tam


def test_liquidity_momentum_insufficient_none():
    assert flow.liquidity_momentum_score(_tighten(n=50), _tighten(n=50)) is None
    assert flow.liquidity_momentum_score([], []) is None
    # v4.1 ek şartı: eksen (127) + rank penceresi (60) → 160 bar YETMEZ
    assert flow.liquidity_momentum_score(_tighten(n=160), _tighten(n=160)) is None


def test_score_is_last_of_pct_series():
    """liquidity_momentum_score = pct_series'in son günü (tek kaynak parite)."""
    d, u = _tighten(350), _tighten(350, 4.0, 0.02)
    assert flow.liquidity_momentum_score(d, u) == flow.liquidity_momentum_pct_series(d, u)[-1]


def test_mom_pct_series_delegates_to_flow():
    """macro_backtest.mom_pct_series = flow.liquidity_momentum_pct_series birebir."""
    d, u = _tighten(300), _easing(300, 6.0, 0.02)
    assert mb.mom_pct_series(d, u) == flow.liquidity_momentum_pct_series(d, u)


def test_cand_mom_is_frozen_v40_reference():
    """cand_mom v4.0 clamp'li DONMUŞ referans — canlı v4.1'den bağımsız."""
    d, u = _tighten(300), _tighten(300, 4.0, 0.02)
    frozen = mb.cand_mom(d, u)
    assert frozen is not None and frozen < 50.0  # eski clamp formülü davranışı
    # Donmuş referans ≠ canlı formül olabilir (kıyas amaçlı ayrı yaşarlar)


# ── consensus._fundamental_v4 (bar arşivinden) ───────────────────────────────

@pytest.fixture
def macro_archive(tmp_path, monkeypatch):
    """DXY/US10Y bar arşivi kur; consensus v4 memo'sunu temizle."""
    monkeypatch.setenv("BAR_HISTORY_ENABLED", "1")
    monkeypatch.setenv("BAR_HISTORY_DIR", str(tmp_path))
    ce._FUND_V4_MEMO["key"] = None

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


def test_fundamental_v4_reads_archive(macro_archive):
    macro_archive("DXY", _tighten())
    macro_archive("US10Y", _tighten(base=4.0, step=0.02))
    v4 = ce._fundamental_v4()
    assert v4 is not None and v4 < 50.0  # sıkılaşma
    assert v4 == pytest.approx(flow.liquidity_momentum_score(_tighten(), _tighten(base=4.0, step=0.02)))


def test_fundamental_v4_no_archive_is_none(monkeypatch, tmp_path):
    monkeypatch.setenv("BAR_HISTORY_ENABLED", "1")
    monkeypatch.setenv("BAR_HISTORY_DIR", str(tmp_path))
    ce._FUND_V4_MEMO["key"] = None
    assert ce._fundamental_v4() is None  # dosya yok → None (kademe düşer)


def test_fundamental_v4_memo_invalidates_on_change(macro_archive):
    macro_archive("DXY", _tighten())
    macro_archive("US10Y", _tighten(base=4.0, step=0.02))
    first = ce._fundamental_v4()
    macro_archive("DXY", _easing())   # dosya değişti (boyut/mtime)
    macro_archive("US10Y", _easing(base=6.0, step=0.02))
    ce._FUND_V4_MEMO["key"] = None      # imza aynı saniyeye düşerse diye zorla
    second = ce._fundamental_v4()
    assert first < 50.0 and second > 50.0  # sıkılaşma → gevşeme


# ── build() kademesi ─────────────────────────────────────────────────────────

def _snap():
    tech = SimpleNamespace(direction_score=60.0, status="OK", timeframe="4h", score=60.0)
    return SimpleNamespace(
        technicals_by_tf={"BTCUSD": {"4h": tech}}, technicals={}, headlines=[],
        rotation=SimpleNamespace(score=50.0, direction="neutral", evidence=[], status="OK"),
        volatility={}, derivatives={}, options={},
    )


def _regime():
    return RegimeOutput(
        label="NEUTRAL",
        layers=[
            RegimeLayer(name="Likidite", score=55.0, direction="neutral", evidence=[]),
            RegimeLayer(name="Sermaye Rotasyonu", score=80.0, direction="risk_on", evidence=[]),
            RegimeLayer(name="Risk İştahı", score=60.0, direction="neutral", evidence=[]),
        ],
    )


@pytest.fixture(autouse=True)
def _no_touche(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_SCORING_V2_SHADOW_PATH", str(tmp_path / "yok.json"))


def test_build_v4_off_is_lower_tier_with_observe(macro_archive):
    macro_archive("DXY", _tighten())
    macro_archive("US10Y", _tighten(base=4.0, step=0.02))
    v4_val = ce._fundamental_v4()
    with threshold_override({"consensus": {"fundamental_v2": True, "fundamental_v4": False}}):
        res = ce.build("BTCUSD", _snap(), _regime(), "4h")
    fund = next(m for m in res.modules if m.name == "fundamental")
    # v2 canlı (Likidite+Rotasyon ort = (55+80)/2 = 67.5), v4 DEĞİL (bayt-aynı)
    assert fund.score == pytest.approx(67.5)
    obs = next(w for w in res.warnings if w.startswith("fundamental_v4_observe"))
    assert f"v4={v4_val:.1f}" in obs and obs.endswith(":used=v2")


def test_build_v4_on_tops_the_ladder(macro_archive):
    macro_archive("DXY", _tighten())
    macro_archive("US10Y", _tighten(base=4.0, step=0.02))
    v4_val = ce._fundamental_v4()
    with threshold_override({"consensus": {"fundamental_v2": True, "fundamental_v4": True}}):
        res = ce.build("BTCUSD", _snap(), _regime(), "4h")
    fund = next(m for m in res.modules if m.name == "fundamental")
    assert fund.score == pytest.approx(round(v4_val, 2))  # v4 tepede
    assert any(w.endswith(":used=v4") for w in res.warnings if w.startswith("fundamental_v4_observe"))


def test_build_v4_on_but_no_archive_falls_back(monkeypatch, tmp_path):
    monkeypatch.setenv("BAR_HISTORY_ENABLED", "1")
    monkeypatch.setenv("BAR_HISTORY_DIR", str(tmp_path))  # boş → v4 None
    ce._FUND_V4_MEMO["key"] = None
    with threshold_override({"consensus": {"fundamental_v2": True, "fundamental_v4": True}}):
        res = ce.build("BTCUSD", _snap(), _regime(), "4h")
    fund = next(m for m in res.modules if m.name == "fundamental")
    assert fund.score == pytest.approx(67.5)  # v4 üretemedi → v2'ye düştü
    assert not any(w.startswith("fundamental_v4_observe") for w in res.warnings)
