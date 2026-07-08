"""0-2 tam-strateji gölge karnesi testleri (owner nihai LONG akışı, 2026-07-08).

Sentetik yükselen 0-1-2 geometrisiyle:
- Giriş: 0.618 reclaim kapanışı tetikler; P2 dibi kırılırsa iptal.
- Yukarı hedef 1.618'e ulaşınca R1 > 0.
- House-money re-giriş: 1.618 TP sonrası dalga-1 tepesi üstünde tutunma →
  rr2 üretir; tepe altı kapanışta re-giriş yok (altın kural).
- Birleşik R = R1·(1+rr2): stop olursa (rr2=-1) net 0 (house-money tabanı).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar
from packages.learning import zero_two_strategy as zts

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(i, o, h, lo, c):
    return OHLCVBar(symbol="TEST", timeframe="4h", ts=_T0 + timedelta(hours=4 * i),
                    open=o, high=h, low=lo, close=c, volume=1.0)


def _walk(path, spread=0.4):
    return [_bar(i, c, c + spread, c - spread, c) for i, c in enumerate(path)]


def _up_path():
    # P0 dip 100 (bar 3) → P1 tepe 120 (bar 13) → P2 dip ~108 (bar 22)
    return [104, 102, 101, 100, 103, 106, 109, 112, 114, 116, 118, 119, 120,
            120.5, 118, 116, 114, 112, 110, 109, 108.5, 108, 108.5]


def _setup(bars):
    return next(s for s in zts._up_setups(bars, 3) if s.direction == "up")


def test_entry_on_618_reclaim_and_targets():
    """0.618 üstüne kapanış girişi + 1.618 hedefe yürüyüş → R1 pozitif, tp_bar dolu."""
    path = _up_path()
    # dalga 3: 0.618 (120.5-0.618*20.5=107.8) üstüne kapanış + 1.618'e (108+1.618*20.5=141) yürü
    for k in range(1, 22):
        path.append(108 + k * 2.0)
    bars = _walk(path)
    s = _setup(bars)
    ft = zts.first_trade(bars, s, 3)
    assert ft is not None
    assert ft["r1"] > 0
    assert ft["tp_bar"] is not None  # 1.618 hedefe ulaştı


def test_p2_break_invalidates_entry():
    """Giriş penceresinde P2 dibi kırılırsa setup iptal (None).

    Önce P2 pivotunu teyit eden 2 yüksek bar (fraktal koşul), SONRA giriş
    penceresinin ilk barında P2 (108) altına kırılım → first_trade None döner.
    """
    path = _up_path()
    path += [110, 111, 107.5, 106]  # 110/111: P2'yi teyit; 107.5/106: dip altı kır
    bars = _walk(path)
    s = _setup(bars)
    assert s.p2.bar_index == 21  # setup hâlâ bulundu (P2 fraktal dibi bar 21)
    assert zts.first_trade(bars, s, 3) is None


def test_house_money_reentry_produces_rr():
    """1.618 TP sonrası tepe üstünde tutunma → pullback+devam → rr2 üretilir."""
    path = _up_path()
    for k in range(1, 20):            # dalga 3: 1.618 üstüne (141) yürü
        path.append(108 + k * 2.0)
    # dalga 4: tepe (120.5) üstünde kalan pullback
    path += [143, 138, 134, 136]     # düş ama 120.5 üstünde; son bar önceki tepeyi kırar
    for k in range(1, 12):           # dalga 5: yukarı devam
        path.append(136 + k * 2.5)
    bars = _walk(path)
    s = _setup(bars)
    ft = zts.first_trade(bars, s, 3)
    assert ft is not None and ft["tp_bar"] is not None
    rr = zts.reentry_rr(bars, s, ft["tp_bar"])
    assert rr is not None


def test_reentry_aborts_when_golden_rule_broken():
    """Dalga-4 dalga-1 tepesi (120.5) altına kapanırsa re-giriş yok (None)."""
    path = _up_path()
    for k in range(1, 20):
        path.append(108 + k * 2.0)
    tp_bar_area = len(path)
    path += [143, 130, 118, 115]     # tepe 120.5 ALTINA kapanış → altın kural bozuk
    bars = _walk(path)
    s = _setup(bars)
    assert zts.reentry_rr(bars, s, tp_bar_area - 1) is None


def test_house_money_floor_combined_never_below_giveback():
    """Birleşik R = R1·(1+rr2): stop (rr2=-1) → net 0, ana paraya dokunmaz."""
    trades = [{"r1": 2.0, "rr2": -1.0}]      # kazanç 2R, re-giriş stop
    s = zts._summ(trades)
    assert s["hm_total_r"] == 0.0            # 2 + 2*(-1) = 0 (kâr geri verildi)
    trades2 = [{"r1": 2.0, "rr2": 1.5}]      # re-giriş kazandı
    s2 = zts._summ(trades2)
    assert s2["hm_total_r"] == 5.0           # 2 + 2*1.5 = 5


def test_run_if_due_skip_fresh(tmp_path, monkeypatch):
    art = tmp_path / "zts.json"
    monkeypatch.setenv("ZERO_TWO_STRATEGY_PATH", str(art))
    art.write_text(
        f'{{"generated_at": "{datetime.now(UTC).isoformat()}", "engine": "{zts._ENGINE}"}}',
        encoding="utf-8",
    )
    assert zts.run_if_due()["status"] == "SKIP_FRESH"


def test_compute_smoke(monkeypatch, tmp_path):
    """compute() sentetik tek-sembol arşivde patlamadan rapor üretir."""
    d = tmp_path / "arch"
    d.mkdir()
    path = _up_path()
    for k in range(1, 40):
        path.append(108 + k * 1.2)
    bars = _walk(path)
    import json
    (d / "TESTSYM_4h.jsonl").write_text(
        "\n".join(json.dumps(b.model_dump(mode="json")) for b in bars), encoding="utf-8"
    )
    monkeypatch.setenv("BAR_HISTORY_ENABLED", "1")
    monkeypatch.setenv("BAR_HISTORY_DIR", str(d))
    rep = zts.compute()
    assert rep["engine"] == zts._ENGINE
    assert isinstance(rep["results"], dict)
