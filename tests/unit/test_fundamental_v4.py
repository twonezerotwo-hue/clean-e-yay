"""fundamental v4 (Basamak-4 formül revizyonu, ADAY B) — gölge üretici testleri.

- flow.liquidity_momentum_score: değişim-bazlı makro likidite (sıkılaşma→<50).
- macro_backtest.cand_mom flow'a DELEGE (tek kaynak — drift yok).
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


def _rising(n=160, start=100.0, step=0.4):
    return [start + step * i for i in range(n)]


def _falling(n=160, start=160.0, step=0.4):
    return [start - step * i for i in range(n)]


# ── flow.liquidity_momentum_score (tek kaynak formül) ────────────────────────

def test_liquidity_momentum_tightening_bearish():
    # DXY + faiz YÜKSELİYOR → sıkılaşma → risk-off → skor < 50
    s = flow.liquidity_momentum_score(_rising(), _rising())
    assert s is not None and s < 50.0


def test_liquidity_momentum_easing_bullish():
    # DXY + faiz DÜŞÜYOR → gevşeme → risk-on → skor > 50
    s = flow.liquidity_momentum_score(_falling(), _falling())
    assert s is not None and s > 50.0


def test_liquidity_momentum_opposite_axes_partial_cancel():
    # DXY yükselir (sıkı) ama faiz düşer (gevşek) → iki eksen kısmen dengelenir;
    # skor tek-eksen uçlarının arasında (merkez yapısal 50, band ~[12,88]).
    up_down = flow.liquidity_momentum_score(_rising(), _falling())
    assert up_down is not None and 12.0 < up_down < 88.0


def test_liquidity_momentum_insufficient_none():
    assert flow.liquidity_momentum_score(_rising(n=50), _rising(n=50)) is None
    assert flow.liquidity_momentum_score([], []) is None


def test_cand_mom_delegates_to_flow():
    """macro_backtest.cand_mom = flow.liquidity_momentum_score birebir (tek kaynak)."""
    dxy, us10 = _rising(), _falling()
    assert mb.cand_mom(dxy, us10) == flow.liquidity_momentum_score(dxy, us10)


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
    macro_archive("DXY", _rising())
    macro_archive("US10Y", _rising())
    v4 = ce._fundamental_v4()
    assert v4 is not None and v4 < 50.0  # sıkılaşma
    assert v4 == pytest.approx(flow.liquidity_momentum_score(_rising(), _rising()))


def test_fundamental_v4_no_archive_is_none(monkeypatch, tmp_path):
    monkeypatch.setenv("BAR_HISTORY_ENABLED", "1")
    monkeypatch.setenv("BAR_HISTORY_DIR", str(tmp_path))
    ce._FUND_V4_MEMO["key"] = None
    assert ce._fundamental_v4() is None  # dosya yok → None (kademe düşer)


def test_fundamental_v4_memo_invalidates_on_change(macro_archive):
    macro_archive("DXY", _rising())
    macro_archive("US10Y", _rising())
    first = ce._fundamental_v4()
    macro_archive("DXY", _falling())   # dosya değişti (boyut/mtime)
    macro_archive("US10Y", _falling())
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
    macro_archive("DXY", _rising())
    macro_archive("US10Y", _rising())
    v4_val = ce._fundamental_v4()
    with threshold_override({"consensus": {"fundamental_v2": True, "fundamental_v4": False}}):
        res = ce.build("BTCUSD", _snap(), _regime(), "4h")
    fund = next(m for m in res.modules if m.name == "fundamental")
    # v2 canlı (Likidite+Rotasyon ort = (55+80)/2 = 67.5), v4 DEĞİL (bayt-aynı)
    assert fund.score == pytest.approx(67.5)
    obs = next(w for w in res.warnings if w.startswith("fundamental_v4_observe"))
    assert f"v4={v4_val:.1f}" in obs and obs.endswith(":used=v2")


def test_build_v4_on_tops_the_ladder(macro_archive):
    macro_archive("DXY", _rising())
    macro_archive("US10Y", _rising())
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
