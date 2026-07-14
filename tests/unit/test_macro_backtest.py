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


# ── Fundamental formül adayları (Basamak-4 revizyonu) ────────────────────────

def _noisy(base, drift, n=300):
    return [base + drift * i + (1.5 if i % 2 else -1.5) for i in range(n)]


def test_zscore_direction():
    assert mb._zscore(_noisy(100.0, 0.2)) > 0      # son değer kendi yılına göre yüksek
    assert mb._zscore(_noisy(100.0, -0.2)) < 0
    assert mb._zscore([100.0] * 300) is None       # sıfır varyans → None (uydurma yok)
    assert mb._zscore([1.0] * 10) is None          # yetersiz pencere


def test_cand_z_tightening_is_bearish():
    # DXY ve faiz kendi yıllık dağılımının tepesinde → likidite sıkı → skor < 50
    s = mb.cand_z(_noisy(100.0, 0.05), _noisy(4.0, 0.005))
    assert s is not None and s < 50.0
    # Gevşeme → skor > 50
    s2 = mb.cand_z(_noisy(115.0, -0.05), _noisy(5.5, -0.005))
    assert s2 is not None and s2 > 50.0


def test_cand_mom_direction_and_center():
    up = mb.cand_mom(_noisy(100.0, 0.1, 200), _noisy(4.0, 0.01, 200))
    down = mb.cand_mom(_noisy(120.0, -0.1, 200), _noisy(6.0, -0.01, 200))
    assert up is not None and up < 50.0            # sıkılaşma → risk-off
    assert down is not None and down > 50.0        # gevşeme → risk-on
    assert mb.cand_mom([100.0] * 50, [4.0] * 50) is None  # yetersiz → None


def test_cand_credit_uses_credit_axis_when_available():
    dxy, rate = _noisy(100.0, 0.0, 200), _noisy(4.0, 0.0, 200)
    hyg_up, lqd_flat = _noisy(80.0, 0.1, 200), _noisy(110.0, 0.0, 200)
    with_credit = mb.cand_credit(dxy, rate, hyg_up, lqd_flat)
    without = mb.cand_credit(dxy, rate, None, None)
    assert with_credit is not None and without is not None
    assert with_credit > without                   # kredi risk-on ekseni skoru yükseltir


def test_score_distribution_math():
    rows = [{"s": 60.0}] * 3 + [{"s": 40.0}] * 1
    d = mb.score_distribution(rows, "s")
    assert d["n"] == 4 and d["pct_hi55"] == 75.0 and d["pct_lo45"] == 25.0


def test_fundamental_candidates_keys():
    prefix = {"DXY": _noisy(100.0, 0.05), "US10Y": _noisy(4.0, 0.005)}
    c = mb.fundamental_candidates(prefix)
    # cand_mom_pct walk() içinde ön-hesapla enjekte edilir (tam seri ister);
    # prefix-bazlı üretici ilk üç adayı döndürür.
    assert set(c) == set(mb.CANDIDATE_KEYS) - {"cand_mom_pct"}
    assert c["cand_z"] is not None and c["cand_credit"] is not None  # kredi verisiz de yaşar


def test_mom_pct_series_no_lookahead_and_range():
    import math
    # Deterministik ama ÇEŞİTLİ seri (salt-düzenli desen ham ekseni 2 değere
    # indirir — gerçek piyasada olmaz; sin-karışımı rank çözünürlüğünü test eder).
    dxy = [100.0 + 3.0 * math.sin(i / 17.0) + 0.02 * i + math.sin(i * 0.71) for i in range(400)]
    us10 = [4.0 + 0.4 * math.sin(i / 23.0) + 0.001 * i + 0.1 * math.sin(i * 0.53) for i in range(400)]
    full = mb.mom_pct_series(dxy, us10)
    cut = mb.mom_pct_series(dxy[:-30], us10[:-30])
    # Gelecek barlar kesilince kesişen günlerin değeri DEĞİŞMEZ (look-ahead yok)
    assert full[: len(cut)] == cut
    vals = [v for v in full if v is not None]
    assert vals and all(0.0 <= v <= 100.0 for v in vals)
    # Yüzdelik-rank çözünürlüğü: skorlar tabana/tavana yapışmaz, band dolu
    assert len({round(v) for v in vals}) > 10


def test_mom_pct_insufficient_is_none():
    out = mb.mom_pct_series(_noisy(100.0, 0.1, 100), _noisy(4.0, 0.01, 100))
    assert all(v is None for v in out)  # min_n=60 pencere dolmadan üretmez


def test_appetite_score_matches_live_formula():
    # Canlı _appetite_layer ile birebir: düşük VIX = yüksek iştah.
    assert mb._appetite_score(12.0) == 100.0
    assert mb._appetite_score(20.0) == 68.0
    assert mb._appetite_score(37.0) == 0.0   # yüksek VIX → 0 (kriz)


def test_walk_uses_vix_appetite_layer_for_crisis():
    """VIX yüksek + diğer katmanlar düşük → CRISIS proxy'de görünebilir."""
    d = _dates(200)
    down = [200.0 - 0.5 * i for i in range(200)]   # BTC/SPY çöküyor
    closes = {
        "SPY": _series(d, down), "BTC": _series(d, down), "GLD": _series(d, down),
        "XAG": _series(d, down), "TLT": _series(d, down), "DXY": _series(d, _rising_seq(200)),
        "OIL": _series(d, down), "HYG": _series(d, down), "LQD": _series(d, [100.0] * 200),
        "US10Y": _series(d, _rising_seq(200, 4.0, 0.02)),
        "VIX": _series(d, [45.0] * 200),   # kriz seviyesi VIX
    }
    dates, aligned, vols = mb.align_daily(closes)
    rows = mb.walk(aligned, vols, dates, horizon=5)
    assert rows
    # VIX katmanı ortalamayı aşağı çeker → en az bir DEFENSIVE/CRISIS gün
    assert any(r["regime"] in ("DEFENSIVE", "CRISIS") for r in rows)


def _rising_seq(n, start=100.0, step=0.3):
    return [start + step * i for i in range(n)]


def test_weights_evidence_structure():
    rows = (
        [{"regime": "NEUTRAL", "cand_mom": 60.0, "flow_score": 60.0,
          "fwd": {"BTC": 2.0}, "date": "2024-01-01"}] * 20
        + [{"regime": "NEUTRAL", "cand_mom": 40.0, "flow_score": 40.0,
            "fwd": {"BTC": -1.0}, "date": "2024-01-02"}] * 20
    )
    ev = mb.weights_evidence(rows)
    assert set(ev) == {"OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS"}
    neu = ev["NEUTRAL"]["measured"]
    assert "fundamental" in neu and "quantum" in neu
    assert neu["fundamental"]["edge_verdict"] == "POSITIVE"  # yüksek skor → yüksek getiri
    # touche/news/sentinel ölçülemez (geçmiş skor yok) → unmeasured
    assert set(ev["NEUTRAL"]["unmeasured"]) == {"touche", "news", "sentinel"}


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
