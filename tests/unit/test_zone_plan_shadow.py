"""Bölge-planı gölge yürütücüsü testleri (owner öğretim seansı 2026-07-11).

Sentetik plan (core 100-110, deep 80, top 200) ile owner'ın dallı planının
tüm dalları:
- Dal 1: parçalı dolum + BE silahlanması + LOG-fib merdiven TP + basamak-trailing.
- BE kuralı: ortalama girişe geri sarma → TAM 0 gerçekleşen; 1B kalıcılıkla
  yeniden giriş.
- Dal 2a: destek kırılımı → işlem-yok boşluğu → derin ortalama-düşürme →
  kırılan desteğin retest'inde derin lot TP.
- Dal 2b: kalıcı geri-alım → yüksek bakiye + desteğin %3 altı sert stop.
- log_fib: owner'ın grafiğindeki BASILI değerlerle birebir (126.230,09→44.048,58
  üstünde 0,236=56.472,68 vb.) — log-ölçek fib kanıtı.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.data.types import OHLCVBar
from packages.learning import zone_plan_shadow as zps

_T0 = datetime(2026, 7, 1, tzinfo=UTC)


def _bar(i, o, h, lo, c):
    return OHLCVBar(symbol="TEST", timeframe="1d", ts=_T0 + timedelta(days=i),
                    open=o, high=h, low=lo, close=c, volume=1.0)


def _plan(**over):
    p = {
        "id": "t", "symbol": "TEST", "timeframe": "1d",
        "top": 200.0, "core_low": 100.0, "core_high": 110.0, "deep": 80.0,
        "entry_parts": 3, "deep_add_mult": 1.0, "reclaim_size_mult": 2.0,
        "reclaim_stop_pct": 0.03, "kalici_closes": 2,
        "tp_levels": (0.236, 0.382, 0.5, 0.618, 0.786, 1.0),
        "valid_from": "", "note": "",
    }
    p.update(over)
    return p


def _names(res):
    return [e["event"] for e in res["events"]]


def test_log_fib_matches_owner_chart_values():
    """Owner'ın 2026-07-11 grafiğindeki basılı fib değerleri (126.230,09 →
    44.048,58) LOG hesapla birebir tutmalı — lineer fib bu sayıları VEREMEZ."""
    top, dip = 126230.09, 44048.58
    assert zps.log_fib(dip, top, 0.236) == pytest.approx(56472.68, abs=1.0)
    assert zps.log_fib(dip, top, 0.382) == pytest.approx(65855.82, abs=1.0)
    assert zps.log_fib(dip, top, 0.5) == pytest.approx(74567.12, abs=1.0)
    assert zps.log_fib(dip, top, 0.618) == pytest.approx(84430.75, abs=1.0)
    assert zps.log_fib(dip, top, 0.786) == pytest.approx(100766.33, abs=1.0)


def test_wait_state_above_core():
    """Fiyat çekirdeğe inmeden hiçbir şey olmaz (WAIT, dolum 0, PnL 0)."""
    bars = [_bar(i, 130, 132, 120, 130) for i in range(5)]
    res = zps.simulate(bars, _plan())
    assert res["state"] == "WAIT"
    assert res["filled_parts"] == 0
    assert res["realized_pct"] == 0.0
    assert res["events"] == []


def test_dal1_fills_ladder_tp_and_trailing():
    """Çekirdek dolumu → BE silahlanır → merdiven TP'leri LOG-fib basamağından
    → alt basamak altına kapanışta trailing çıkışı; toplam R pozitif."""
    bars = [
        _bar(0, 120, 121, 119, 120),
        _bar(1, 112, 112, 99, 105),    # 3 parça dolar (110/105/100), avg 105
        _bar(2, 106, 113, 104, 112),   # kapanış 110 üstü → BE silahlanır
        _bar(3, 113, 123, 112, 121),   # rung0 (0,236) vurulur
        _bar(4, 122, 136, 120, 133),   # rung1 (0,382) vurulur
        _bar(5, 130, 131, 118, 119),   # rung0 altına kapanış → trailing çıkışı
    ]
    res = zps.simulate(bars, _plan())
    assert res["state"] == "COMPLETED"
    assert res["filled_parts"] == 3
    assert res["open_size"] == 0.0
    names = _names(res)
    assert names.count("CORE_FILL") == 3
    assert "BE_ARMED" in names
    assert names.count("TP_RUNG") == 2
    assert "TRAIL_EXIT" in names
    # İlk TP fiyatı = avg(105)→top(200) LOG fib 0,236 basamağı
    tp0 = next(e for e in res["events"] if e["event"] == "TP_RUNG")
    assert tp0["price"] == pytest.approx(zps.log_fib(105.0, 200.0, 0.236), abs=0.01)
    assert res["realized_pct"] > 0


def test_be_exit_is_exactly_zero_then_1b_reentry():
    """Yükselip ortalama girişe geri sarma → TAM 0 gerçekleşen (owner: '0 zarar
    ile çıkarım'); sonra kalici_closes kapanış bölge üstü → 1B yeniden giriş."""
    bars = [
        _bar(0, 112, 112, 99, 105),      # 3 parça dolar, avg 105
        _bar(1, 106, 112, 105.5, 111),   # BE silahlanır (kapanış > 110)
        _bar(2, 110, 111, 104, 106),     # low ≤ 105 → BE çıkışı (tam 0)
        _bar(3, 108, 113, 107, 112),     # kalıcılık 1
        _bar(4, 112, 114, 111, 113),     # kalıcılık 2 → 1B yeniden giriş
    ]
    res = zps.simulate(bars, _plan())
    names = _names(res)
    assert "BE_EXIT" in names
    assert "REENTRY_1B" in names
    assert res["realized_pct"] == 0.0     # BE = kuruşu kuruşuna sıfır
    assert res["open_size"] == 1.0        # yeniden giriş tek lot
    assert res["state"] == "CORE"


def test_dal2a_no_trade_gap_deep_add_and_retest_tp():
    """Destek kırılımı → derin katmana kadar İŞLEM-YOK → derinde ortalama
    düşürme → kırılan desteğin alttan retest'inde derin lot TP (+20/lot)."""
    bars = [
        _bar(0, 112, 112, 99.5, 104),  # 3 parça dolar
        _bar(1, 103, 104, 95, 96),     # destek kırılımı (kapanış < 100)
        _bar(2, 95, 97, 90, 91),       # işlem-yok bölgesi — hiçbir olay yok
        _bar(3, 88, 89, 79, 85),       # derin (80) → ortalama düşürme
        _bar(4, 90, 101, 89, 99),      # retest (high ≥ 100) → derin lot TP
    ]
    res = zps.simulate(bars, _plan())
    names = _names(res)
    assert "SUPPORT_BREAK" in names
    assert "DEEP_ADD" in names
    assert "RETEST_TP" in names
    assert "BE_ARMED" not in names        # destek kırılınca BE rejimi yok
    # bar 2 (boşluk) hiçbir olay üretmedi
    gap_events = [e for e in res["events"] if e["ts"].startswith("2026-07-03")]
    assert gap_events == []
    # Derin lot: 80 → 100 retest TP = +20; ref=105 → %19.05
    assert res["realized_pct"] == pytest.approx(20 / 105 * 100, abs=0.05)
    assert res["open_size"] == pytest.approx(1.0)   # çekirdek lotları hâlâ açık
    assert res["state"] == "UNDER_SUPPORT"


def test_dal2b_reclaim_add_and_hard_stop():
    """Kalıcı geri-alım → yüksek bakiye eklenir + stop desteğin %3 altı;
    stop değince TÜM pozisyon oradan kapanır (RECLAIM_STOPPED)."""
    bars = [
        _bar(0, 112, 112, 99.5, 104),   # dolum
        _bar(1, 103, 104, 95, 96),      # kırılım
        _bar(2, 88, 89, 79, 85),        # derin ekleme (80)
        _bar(3, 90, 101, 89, 99),       # retest TP (+20)
        _bar(4, 100, 112, 99, 111),     # kalıcılık 1
        _bar(5, 111, 113, 110, 112),    # kalıcılık 2 → reclaim add (2.0 @ 112), stop 97
        _bar(6, 108, 109, 95, 96),      # low ≤ 97 → sert stop, hepsi 97'den
    ]
    res = zps.simulate(bars, _plan())
    names = _names(res)
    assert "RECLAIM_ADD" in names
    assert "HARD_STOP" in names
    assert res["state"] == "RECLAIM_STOPPED"
    assert res["open_size"] == 0.0
    # Gerçekleşen: retest +20; stop: (97-105)·1 + (97-112)·2 = -38 → net -18
    assert res["realized_pct"] == pytest.approx(-18 / 105 * 100, abs=0.05)
    stop_ev = next(e for e in res["events"] if e["event"] == "HARD_STOP")
    assert stop_ev["price"] == pytest.approx(97.0)  # 100 · (1 - 0.03)


def test_valid_from_skips_earlier_bars():
    """valid_from öncesi barlar plana dahil değil (tarihî bar dolum tetiklemez)."""
    bars = [_bar(0, 112, 112, 99, 105), _bar(1, 120, 125, 115, 124)]
    res = zps.simulate(bars, _plan(valid_from="2026-07-02"))
    assert res["filled_parts"] == 0
    assert res["state"] == "WAIT"


def test_load_plans_validates_and_filters(tmp_path, monkeypatch):
    """YAML'dan plan yükleme: geçerli plan normalize edilir; katman sırası bozuk
    plan sessizce elenir; dosya yoksa boş liste."""
    y = tmp_path / "zone_plans.yaml"
    y.write_text(
        "version: 1\n"
        "plans:\n"
        "  - id: ok\n"
        "    symbol: BTCUSD\n"
        "    top: 126230.09\n"
        "    core: [52000, 50100]\n"   # ters sırada verilse de normalize edilir
        "    deep: 44203.72\n"
        "  - id: bozuk\n"
        "    symbol: BTCUSD\n"
        "    top: 100\n"
        "    core: [200, 300]\n"       # core > top → elenir
        "    deep: 400\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZONE_PLANS_PATH", str(y))
    plans = zps.load_plans()
    assert len(plans) == 1
    p = plans[0]
    assert p["id"] == "ok"
    assert p["core_low"] == 50100.0 and p["core_high"] == 52000.0
    assert p["kalici_closes"] == 5          # default
    assert p["tp_levels"][0] == 0.236       # default merdiven

    monkeypatch.setenv("ZONE_PLANS_PATH", str(tmp_path / "yok.yaml"))
    assert zps.load_plans() == []


def test_run_if_due_no_plans_is_noop(tmp_path, monkeypatch):
    """Plan dosyası yoksa NO_PLANS döner ve artifact YAZILMAZ (tam no-op)."""
    monkeypatch.setenv("ZONE_PLANS_PATH", str(tmp_path / "yok.yaml"))
    out_path = tmp_path / "zone_plan_shadow.json"
    monkeypatch.setenv("ZONE_PLAN_SHADOW_PATH", str(out_path))
    assert zps.run_if_due() == {"status": "NO_PLANS"}
    assert not out_path.exists()
