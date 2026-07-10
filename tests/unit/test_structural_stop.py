"""P2 parça-2 — yapısal stop yerleşimi testleri.

Kritik güvenceler:
- Stop = son N-bar dip/tepe (buffer kadar ötede); tp = mevcut TF rr × yapısal_R.
- floor/cap güvenlik bandı (aşırı yakın/uzak yapısal stop kıstırılır).
- Yetersiz bar / yapı yanlış tarafta → sl_basis="invalid" (uydurma yok; ATR'ye düşer).
"""
from __future__ import annotations

import pytest

from packages.risk import trade_economics as te


@pytest.fixture(autouse=True)
def _fixed_params(monkeypatch):
    # rr/floor/cap'i sabitle → deterministik (config'ten bağımsız).
    monkeypatch.setattr(te, "_tf_params", lambda tf: {
        "rr": 2.0, "sl_pct_floor": 0.005, "sl_pct_cap": 0.10, "sl_atr_mult": 1.5})


def test_long_stop_at_recent_low():
    """Long: stop son 10 barın dibinin biraz altında; tp = entry + 2R."""
    lows = [96, 95, 94, 93, 97, 98, 96, 95, 94, 96]   # dip 93
    highs = [x + 2 for x in lows]
    t = te.compute_structural_targets("BTCUSD", "long", 100.0,
                                      highs=highs, lows=lows, timeframe="4h")
    assert t.sl_basis == "structural"
    assert t.sl < 100.0 and t.sl == pytest.approx(100 * (1 - (100 - 93 * 0.999) / 100), rel=1e-3)
    # tp = entry + rr × sl_distance (2R)
    assert t.tp == pytest.approx(100.0 + 2.0 * t.sl_distance, rel=1e-6)


def test_short_stop_at_recent_high():
    """Short: stop son 10 barın tepesinin biraz üstünde (ayna)."""
    highs = [104, 105, 106, 107, 103, 102, 104, 105, 106, 104]  # tepe 107
    lows = [x - 2 for x in highs]
    t = te.compute_structural_targets("BTCUSD", "short", 100.0,
                                      highs=highs, lows=lows, timeframe="4h")
    assert t.sl_basis == "structural" and t.sl > 100.0
    assert t.tp == pytest.approx(100.0 - 2.0 * t.sl_distance, rel=1e-6)


def test_cap_clamps_far_structural_stop():
    """Çok derin dip (raw %20 > cap %10) → stop cap'e kıstırılır (aşırı risk korunur)."""
    lows = [80] * 10                    # dip 80 → raw ~%20
    t = te.compute_structural_targets("BTCUSD", "long", 100.0,
                                      highs=[102] * 10, lows=lows, timeframe="4h")
    assert t.sl == pytest.approx(90.0, rel=1e-6)      # cap %10 → sl 90
    assert any("clamped_to_cap" in n for n in t.notes)


def test_floor_clamps_near_structural_stop():
    """Çok yakın dip (raw < floor %0.5) → stop floor'a açılır (gürültü-stop korunur)."""
    lows = [99.9] * 10                  # dip ~entry → raw ~%0.1 < floor
    t = te.compute_structural_targets("BTCUSD", "long", 100.0,
                                      highs=[101] * 10, lows=lows, timeframe="4h")
    assert t.sl == pytest.approx(99.5, rel=1e-6)      # floor %0.5 → sl 99.5
    assert any("clamped_to_floor" in n for n in t.notes)


def test_invalid_when_entry_wrong_side():
    """Long ama entry son dibin ALTINDA → yapı geçersiz (invalid, ATR'ye düşer)."""
    lows = [105, 106, 104, 107, 105, 106, 104, 105, 106, 104]  # dip 104 > entry 100
    t = te.compute_structural_targets("BTCUSD", "long", 100.0,
                                      highs=[108] * 10, lows=lows, timeframe="4h")
    assert t.sl_basis == "invalid"


def test_invalid_when_insufficient_bars():
    t = te.compute_structural_targets("BTCUSD", "long", 100.0,
                                      highs=[102], lows=[98], timeframe="4h")
    assert t.sl_basis == "invalid"


def test_same_adaptive_shape_as_tf_targets():
    """compute_tf_targets ile AYNI AdaptiveTargets şekli (shadow kıyası bedava)."""
    lows = [95, 94, 93, 96, 97, 96, 95, 94, 96, 95]
    t = te.compute_structural_targets("BTCUSD", "long", 100.0,
                                      highs=[x + 2 for x in lows], lows=lows, timeframe="4h")
    assert isinstance(t, te.AdaptiveTargets)
    assert t.tp_basis == "structural_rr" and t.sl_distance > 0


# ---------------- lifecycle open_position wire ----------------

class _Bar:
    def __init__(self, hi, lo):
        self.high, self.low = hi, lo


def _open(monkeypatch, tmp_path, *, enabled):
    import importlib
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    from packages.paper import lifecycle
    from packages.paper import state as ps
    importlib.reload(ps)
    monkeypatch.setattr(lifecycle, "_structural_stop_cfg",
                        lambda: {"enabled": enabled, "lookback": 10, "buffer_pct": 0.001})
    monkeypatch.setattr(lifecycle, "_recent_bars_for_stop",
                        lambda s, tf, count=15: [_Bar(102, 93)] * 10)
    # yapısal motor sabit sl=93 döndürsün → wire'ın onu kullandığı ölçülür
    monkeypatch.setattr(lifecycle, "compute_structural_targets", lambda *a, **k: te.AdaptiveTargets(
        sl=93.0, tp=114.0, rr=2.0, sl_basis="structural", tp_basis="structural_rr",
        rr_floor_met=True, sl_distance=7.0))
    st = ps.load()
    return lifecycle.open_position(
        st, symbol="BTCUSD", side="long", entry_price=100.0, size_multiplier=1.0,
        timeframe="4h", atr=1.0, data_verified=True)


def test_open_uses_structural_when_enabled(tmp_path, monkeypatch):
    """Flag açık → açılış stop'u yapısal motordan (sl=93)."""
    pos = _open(monkeypatch, tmp_path, enabled=True)
    assert pos.sl == 93.0


def test_open_ignores_structural_when_disabled(tmp_path, monkeypatch):
    """Flag kapalı → yapısal motor devrede DEĞİL; sl ATR motorundan (≠93, bayt-aynı)."""
    pos = _open(monkeypatch, tmp_path, enabled=False)
    assert pos.sl != 93.0 and pos.sl < 100.0   # ATR/TF motoru long stop üretti
