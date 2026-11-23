"""Owner'ın el-çizimi bölge planları: LOG-fib ve plan yükleme (zone_proposer).

Gölge plan yürütücüsü (zone_plan_shadow) 22 Kasım 2026'da silindi; planlar bölge
grafiğinde katman olarak kalır. log_fib owner'ın grafiğindeki basılı değerlerle birebir.
"""
from __future__ import annotations

import pytest

from packages.learning import zone_proposer as zp


def test_log_fib_matches_owner_chart_values():
    """Owner'ın 2026-07-11 grafiğindeki basılı fib değerleri (126.230,09 →
    44.048,58) LOG hesapla birebir tutmalı — lineer fib bu sayıları VEREMEZ."""
    top, dip = 126230.09, 44048.58
    assert zp.log_fib(dip, top, 0.236) == pytest.approx(56472.68, abs=1.0)
    assert zp.log_fib(dip, top, 0.382) == pytest.approx(65855.82, abs=1.0)
    assert zp.log_fib(dip, top, 0.5) == pytest.approx(74567.12, abs=1.0)
    assert zp.log_fib(dip, top, 0.618) == pytest.approx(84430.75, abs=1.0)
    assert zp.log_fib(dip, top, 0.786) == pytest.approx(100766.33, abs=1.0)


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
    plans = zp.load_plans()
    assert len(plans) == 1
    p = plans[0]
    assert p["id"] == "ok"
    assert p["core_low"] == 50100.0 and p["core_high"] == 52000.0
    assert p["kalici_closes"] == 5          # default
    assert p["tp_levels"][0] == 0.236       # default merdiven

    monkeypatch.setenv("ZONE_PLANS_PATH", str(tmp_path / "yok.yaml"))
    assert zp.load_plans() == []
