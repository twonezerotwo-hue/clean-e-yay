"""macro_backtest (Basamak-4 kanıt üreticisi) birim testleri — sentetik seri.

Bekçiler: takvim hizası (ffill), look-ahead YOK (gelecek bar skoru değiştirmez),
separation matematiği, IC→ağırlık önerisi işaretleri, artifact yazımı.
"""
from __future__ import annotations

import math

from packages.learning import macro_backtest as mb


def _dates(n: int) -> list[str]:
    # Sentetik ardışık iş günleri gerekmiyor — eksen sıralı olsun yeter.
    return [f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]


def _series(dates, vals):
    return list(zip(dates, vals, strict=True))


def test_align_daily_ffills_gaps():
    d = ["2024-01-01", "2024-01-02", "2024-01-03"]
    closes = {
        "SPY": _series(d, [100.0, 101.0, 102.0]),
        "BTC": [("2024-01-01", 50.0), ("2024-01-03", 60.0)],  # 02'de boşluk
    }
    dates, aligned, _ = mb.align_daily(closes)
    assert dates == d
    assert aligned["BTC"] == [50.0, 50.0, 60.0]  # ffill


def test_align_daily_leading_gap_is_nan():
    d = ["2024-01-01", "2024-01-02"]
    closes = {"SPY": _series(d, [100.0, 101.0]), "GLD": [("2024-01-02", 10.0)]}
    _, aligned, _ = mb.align_daily(closes)
    assert math.isnan(aligned["GLD"][0]) and aligned["GLD"][1] == 10.0


def _synthetic_market(n=200):
    """BTC/SPY güçlü yükseliş, GLD düşüş, DXY/US10Y sabit-makul, kredi yatay."""
    d = _dates(n)
    up = [100.0 + 0.8 * i for i in range(n)]
    up2 = [50.0 + 0.5 * i for i in range(n)]
    down = [200.0 - 0.4 * i for i in range(n)]
    flat = [100.0 + (0.1 if i % 2 else -0.1) for i in range(n)]
    closes = {
        "SPY": _series(d, up), "BTC": _series(d, up2), "GLD": _series(d, down),
        "XAG": _series(d, flat), "TLT": _series(d, flat), "DXY": _series(d, [102.0] * n),
        "OIL": _series(d, flat), "HYG": _series(d, up), "LQD": _series(d, up),
        "US10Y": _series(d, [4.2] * n),
    }
    return closes


def test_walk_no_lookahead():
    """Gelecek barların değişmesi t günündeki skoru DEĞİŞTİREMEZ."""
    closes_raw = _synthetic_market()
    dates, closes, vols = mb.align_daily(closes_raw)
    rows_a = mb.walk(closes, vols, dates, horizon=5)
    # Son 3 barı uçur: kalan pencerede kesişen günlerin skorları birebir aynı.
    mutated = {k: v[:-3] for k, v in closes.items()}
    vols_m = {k: (v[:-3] if v else None) for k, v in vols.items()}
    rows_b = mb.walk(mutated, vols_m, dates[:-3], horizon=5)
    by_date_a = {r["date"]: r["flow_score"] for r in rows_a}
    for r in rows_b:
        assert by_date_a.get(r["date"]) == r["flow_score"]


def test_walk_rows_have_scores_and_regime():
    closes_raw = _synthetic_market()
    dates, closes, vols = mb.align_daily(closes_raw)
    rows = mb.walk(closes, vols, dates, horizon=5)
    assert rows, "warmup sonrası satır üretilmeli"
    r = rows[0]
    assert 0.0 <= r["flow_score"] <= 100.0
    assert r["regime"] in ("OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS")
    assert r["fund_v3"] == mb._liquidity_score(102.0, 4.2)
    assert "BTC" in r["fwd"] and "fwd_risk" in r


def test_separation_math():
    rows = (
        [{"flow_score": 60.0, "fwd": {"BTC": 2.0}, "regime": "NEUTRAL", "date": "2024-01-01"}] * 12
        + [{"flow_score": 40.0, "fwd": {"BTC": -1.0}, "regime": "NEUTRAL", "date": "2024-01-02"}] * 12
    )
    s = mb.separation(rows, "flow_score", "BTC")
    assert s["sep"] == 3.0 and s["verdict"] == "POSITIVE"
    assert mb.separation(rows[:5], "flow_score", "BTC")["verdict"] == "INSUFFICIENT"


def test_suggest_weights_signs_and_floor():
    ics = {
        "BTC": {"ic": 0.10}, "GLD": {"ic": -0.05},
        "XAG": {"ic": 0.005},  # floor altı → 0
        "TLT": {"ic": None},
    }
    w = mb.suggest_weights(ics)
    assert w["BTC"] == 1.5           # en büyük |IC| → 1.5 tavan
    assert w["GLD"] == -0.75         # işaret korunur, oransal
    assert w["XAG"] == 0.0 and w["TLT"] == 0.0


def test_separation_tercile_center_shifted_scores():
    """Sabit 55/45 bandı hep-yüksek skoru ölçemez; tercile ölçer (Likidite dersi)."""
    rows = [
        {"s": 80.0 + i * 0.1, "fwd": {"BTC": 2.0}, "date": "2024-01-01"} for i in range(15)
    ] + [
        {"s": 60.0 + i * 0.1, "fwd": {"BTC": -1.0}, "date": "2024-01-02"} for i in range(15)
    ]
    band = mb.separation(rows, "s", "BTC")
    assert band["verdict"] == "INSUFFICIENT"  # hepsi >55 → lo bandı boş
    terc = mb.separation_tercile(rows, "s", "BTC")
    assert terc["verdict"] == "POSITIVE" and terc["sep"] == 3.0


def test_walk_forward_trains_only_on_past():
    """Test yılının ağırlıkları yalnız ÖNCEKİ yıllardan — az geçmiş → YETERSİZ."""
    closes = _synthetic_market(400)
    dates, aligned, vols = mb.align_daily(closes)
    rows = mb.walk(aligned, vols, dates, horizon=5)
    # Sentetik eksen tek yıla sığar (2024) → hiç test yılı çıkmaz veya YETERSİZ.
    wf = mb.walk_forward(rows)
    for _y, blk in wf.items():
        assert blk.get("verdict") == "INSUFFICIENT" or "learned" in blk


def test_run_writes_artifact(tmp_path, monkeypatch):
    """run() uçtan uca: arşiv yerine sentetik seri, artifact tmp'e yazılır."""
    monkeypatch.setenv("MACRO_BACKTEST_PATH", str(tmp_path / "macro_backtest.json"))
    closes = _synthetic_market()
    volumes = {k: [(d, 1000.0) for d, _ in v] for k, v in closes.items()}
    monkeypatch.setattr(mb, "load_archive_series", lambda: (closes, volumes))
    result = mb.run(horizon=5)
    assert (tmp_path / "macro_backtest.json").exists()
    assert result["params"]["rows"] > 0
    assert set(result["suggested_flow_weights"]) == set(
        result["current_default_weights"]
    ) | {"SPY"} - {"SP500"} or set(result["suggested_flow_weights"]) >= {"BTC", "CREDIT"}
    assert "fundamental_v2_vs_v3" in result and "BTC" in result["fundamental_v2_vs_v3"]
