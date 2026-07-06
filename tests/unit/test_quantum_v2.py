"""quantum v2 — sembol-başı kesitsel göreceli-güç (para akışı) testleri.

- `_relative_strength`: lider/geride ayrışması, oynaklık-adil, yetersiz veri → boş.
- Flag KAPALI (default): quantum oyu v1 makro tilt (bayt-aynı); v2 gözlem satırında.
- Flag AÇIK: quantum oyu v2 (sembol-başı); v2 kanıtsız sembolde v1'e düşer.
- rotation UNAVAILABLE → quantum modülü düşer (v1/v2 fark etmez).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.consensus import engine as ce
from packages.data.providers.rotation import engine as rot
from packages.data.registry.loader import threshold_override

_FLAG_ON = {"consensus": {"quantum_v2": True}}
_FLAG_OFF = {"consensus": {"quantum_v2": False}}


# ── _relative_strength (rotation motoru) ─────────────────────────────────────

def _series(start: float, step: float, n: int = 140) -> list[float]:
    # Küçük alternatif gürültü → düz seride bile oynaklık > 0 (aksi halde vol=0
    # olan varlık RS'ten atlanır; gerçek fiyatta hep miktarda salınım vardır).
    return [start + step * i + (0.3 if i % 2 else -0.3) for i in range(n)]


def test_rs_leader_beats_laggard():
    """Yükselen varlık lider (yüksek), düşen geride (düşük), düz orta."""
    closes = {
        "SPY": _series(100, 0.5),    # güçlü yukarı
        "GLD": _series(100, 0.0),    # düz
        "BTC": _series(200, -0.5),   # aşağı
        "TLT": _series(100, 0.05),   # hafif yukarı
    }
    rs = rot._relative_strength(closes)
    # anahtar VALUE'ya map'lenir (SPY→SP500, BTC→BTCUSD, GLD→XAUUSD, TLT→TLT)
    assert rs["SP500"] > rs["TLT"] > rs["XAUUSD"] > rs["BTCUSD"]
    assert 0.0 <= rs["BTCUSD"] <= 100.0 and 0.0 <= rs["SP500"] <= 100.0


def test_rs_insufficient_history_skipped():
    """127 bardan kısa seri atlanır; <3 kullanılabilir varlık → boş dict."""
    closes = {"SPY": _series(100, 1.0, n=50), "GLD": _series(100, 1.0, n=50)}
    assert rot._relative_strength(closes) == {}


def test_rs_vol_normalizes():
    """Aynı % getiri ama düşük oynaklık → daha yüksek göreceli güç (oynaklık-adil)."""
    smooth = _series(100, 0.4)                          # düz artış, düşük vol
    choppy = [100 + 0.4 * i + (8 if i % 2 else -8) for i in range(140)]  # aynı eğim, yüksek vol
    closes = {"SPY": smooth, "BTC": choppy, "GLD": _series(100, 0.0), "TLT": _series(100, 0.0)}
    rs = rot._relative_strength(closes)
    assert rs["SP500"] > rs["BTCUSD"]  # düz olan daha güçlü RS


# ── consensus wiring ─────────────────────────────────────────────────────────

def _snap(rot_score=50.0, per_symbol=None, status="OK"):
    return SimpleNamespace(
        technicals_by_tf={"BTCUSD": {"1d": SimpleNamespace(
            direction_score=60.0, status="OK", timeframe="1d", score=60.0)}},
        technicals={},
        headlines=[],
        rotation=SimpleNamespace(score=rot_score, direction="neutral", evidence=[],
                                 status=status, per_symbol=per_symbol or {}),
        volatility={},
        derivatives={},
        options={},
    )


def _regime():
    from packages.regime.classifier import RegimeLayer, RegimeOutput
    return RegimeOutput(label="NEUTRAL", layers=[
        RegimeLayer(name="Likidite", score=55.0, direction="neutral", evidence=[]),
        RegimeLayer(name="Risk İştahı", score=60.0, direction="neutral", evidence=[])])


def _quantum(res):
    return next(m.score for m in res.modules if m.name == "quantum")


def test_flag_off_quantum_is_v1(monkeypatch):
    snap = _snap(rot_score=59.2, per_symbol={"BTCUSD": 28.0})
    with threshold_override(_FLAG_OFF):
        res = ce.build("BTCUSD", snap, _regime(), "1d")
    assert _quantum(res) == pytest.approx(59.2)   # v1 makro tilt (bayt-aynı)
    assert any(w == "quantum_v2_observe:v1=59.2:v2=28.0:used=v1" for w in res.warnings)


def test_flag_on_quantum_is_v2(monkeypatch):
    snap = _snap(rot_score=59.2, per_symbol={"BTCUSD": 28.0})
    with threshold_override(_FLAG_ON):
        res = ce.build("BTCUSD", snap, _regime(), "1d")
    assert _quantum(res) == pytest.approx(28.0)   # v2 sembol-başı
    assert any(w == "quantum_v2_observe:v1=59.2:v2=28.0:used=v2" for w in res.warnings)


def test_flag_on_no_per_symbol_falls_back(monkeypatch):
    snap = _snap(rot_score=59.2, per_symbol={})   # bu sembol için v2 yok
    with threshold_override(_FLAG_ON):
        res = ce.build("BTCUSD", snap, _regime(), "1d")
    assert _quantum(res) == pytest.approx(59.2)   # v1'e düştü
    assert not any(w.startswith("quantum_v2_observe") for w in res.warnings)


def test_rotation_unavailable_drops_quantum(monkeypatch):
    snap = _snap(status="UNAVAILABLE", per_symbol={"BTCUSD": 28.0})
    with threshold_override(_FLAG_ON):
        res = ce.build("BTCUSD", snap, _regime(), "1d")
    assert not any(m.name == "quantum" for m in res.modules)  # modül düştü
