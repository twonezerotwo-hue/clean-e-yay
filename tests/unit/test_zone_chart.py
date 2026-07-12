"""Bölge önerisi grafik çizicisi testleri (SVG; salt-görsel katman).

Sentetik confluence serisiyle: SVG yapısal olarak doğru (mum/çizgi/bant/etiket
öğeleri var), LOG y-ekseni doğru yönde (yüksek fiyat üstte), owner planı
bindirmesi etiketlenir, veri yetersizse boş-grafik döner.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar
from packages.learning import zone_chart as zc
from packages.learning import zone_proposer as zp

_T0 = datetime(2020, 1, 6, tzinfo=UTC)


def _bar(i, hi, lo, close=None):
    c = close if close is not None else (hi + lo) / 2
    return OHLCVBar(symbol="TEST", timeframe="1w", ts=_T0 + timedelta(weeks=i),
                    open=c, high=hi, low=lo, close=c, volume=1.0)


def _series():
    import math
    g = math.log10(1.005)
    bars = []
    for i in range(60):
        s = 10 ** (2 + g * i)
        if i in (6, 30):
            bars.append(_bar(i, s * 1.05, s * 1.00))
        elif i == 20:
            bars.append(_bar(i, s * 1.60, s * 1.50, close=s * 1.55))
        elif i == 45:
            bars.append(_bar(i, s * 1.95, s * 1.85, close=s * 1.90))
        elif 46 <= i <= 54:
            f = 1.85 - (i - 45) * 0.085
            bars.append(_bar(i, s * (f + 0.05), s * f, close=s * (f + 0.02)))
        else:
            bars.append(_bar(i, s * 1.20, s * 1.15, close=s * 1.17))
    return bars


_CFG = {"pivot_span": 3, "min_weekly_bars": 20, "horizon_bars": 12,
        "cluster_tol_pct": 3.0, "min_confluence": 2, "max_zones": 5}


def test_render_svg_structure_and_layers():
    """SVG: mumlar + trend çizgileri + bölge bandı + fib etiketi + yıl ekseni."""
    bars = _series()
    analysis = zp.analyze_bars(bars, _CFG)
    assert analysis["status"] == "OK" and analysis["zones"]
    svg = zc.render_svg(bars, analysis, title="TEST — haftalık")
    assert svg.startswith("<svg")
    assert svg.count("<rect") > 60          # mum gövdeleri + bölge bantları
    assert 'stroke="#ef5350" stroke-width="2"' in svg    # dip (destek) çizgisi
    assert 'stroke="#4caf50" stroke-width="2"' in svg    # tepe (direnç) çizgisi
    assert "araç:" in svg                    # confluence bölge etiketi
    assert 'stroke-dasharray="6 4"' in svg   # fib kesikli çizgisi
    assert ">2020<" in svg and ">2021<" in svg  # yıl ekseni


def test_render_svg_log_scale_orientation():
    """LOG eksen: yüksek fiyatın y'si küçük (üstte) — mum fitilleri düzgün."""
    bars = _series()
    analysis = zp.analyze_bars(bars, _CFG)
    svg = zc.render_svg(bars, analysis, title="T")
    # İlk mumun fitil satırı: y1 (high) < y2 (low) olmalı
    import re
    m = re.search(r'<line x1="[\d.]+" y1="([\d.]+)" x2="[\d.]+" y2="([\d.]+)" '
                  r'stroke="#(?:26a69a|ef5350)" stroke-width="1"/>', svg)
    assert m is not None
    assert float(m.group(1)) < float(m.group(2))


def test_owner_plan_overlay_labeled():
    """Owner planı verilince turkuaz katman çizgileri + OWNER etiketi çizilir."""
    bars = _series()
    analysis = zp.analyze_bars(bars, _CFG)
    plan = {"symbol": "TEST", "core_low": 110.0, "core_high": 118.0, "deep": 95.0}
    svg = zc.render_svg(bars, analysis, title="T", owner_plans=[plan])
    assert "OWNER çekirdek üst" in svg
    assert "OWNER derin" in svg
    assert 'stroke="#26c6da"' in svg
    # plansızsa owner katmanı yok
    svg2 = zc.render_svg(bars, analysis, title="T")
    assert "OWNER" not in svg2


def test_render_svg_insufficient_data():
    """2'den az bar → boş-grafik (yine geçerli SVG)."""
    svg = zc.render_svg([_bar(0, 101, 99)], {"zones": [], "draw": {}}, title="X")
    assert svg.startswith("<svg") and "veri yok" in svg


def test_review_html_from_artifact(tmp_path, monkeypatch):
    """İnceleme sayfası: artifact'taki zone'lu asset başlık+grafik+tablo olarak
    gelir; artifact yoksa yönlendirme notu."""
    out = tmp_path / "zone_proposer.json"
    monkeypatch.setenv("ZONE_PROPOSER_PATH", str(out))
    monkeypatch.setattr(zp, "_universe", lambda cfg: ["TEST"])
    monkeypatch.setattr(zp, "_weekly_bars", lambda sym: _series())
    monkeypatch.setattr(zp, "_cfg", lambda: dict(_CFG))
    assert zp.run_if_due()["status"] == "OK"

    page = zc.review_html()
    assert "<h2>TEST</h2>" in page
    assert "<svg" in page and "kaynaklar" in page

    # artifact yokken yönlendirme
    monkeypatch.setenv("ZONE_PROPOSER_PATH", str(tmp_path / "yok.json"))
    assert "Henüz artifact yok" in zc.review_html()


def test_chart_svg_no_data_returns_none(monkeypatch):
    monkeypatch.setattr(zp, "_weekly_bars", lambda sym: [])
    assert zc.chart_svg("YOKBOYLE") is None
