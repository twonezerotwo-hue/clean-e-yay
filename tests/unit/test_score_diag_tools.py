"""scripts/score_diag — veri temizleme, bölünme düzeltmesi, yürütme simülasyonu, TEST disiplini.

Ağ yok: yalnız sentetik veri. Düzenek çalışma zamanında import edilmez ama kararları
(``scripts/score_diag`` raporlarına bakılarak verilen eşikler) buradan çıktığı için
temel invariantları (zıt yön yok, look-ahead yok, ücret R'yi düşürür) kilitleriz.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# Düzenek bir DEV aracıdır (pandas/numpy ister); CI'ın yalın bağımlılık setinde (pandas yok)
# bu testler atlanır, geliştirici ortamında çalışır.
pd = pytest.importorskip("pandas")
pytest.importorskip("numpy")

from packages.data.types import OHLCVBar  # noqa: E402
from scripts.score_diag import compare, data, metrics, prep  # noqa: E402

T0 = datetime(2020, 1, 1, tzinfo=UTC)


def bar(i: int, o: float, h: float, lo: float, c: float, v: float | None = 100.0, tf: str = "1d") -> OHLCVBar:
    return OHLCVBar(symbol="T", timeframe=tf, ts=T0 + timedelta(days=i), open=o, high=h, low=lo, close=c, volume=v)


def flat(n: int, px: float = 100.0) -> list[OHLCVBar]:
    return [bar(i, px, px * 1.002, px * 0.998, px) for i in range(n)]


# ------------------------------------------------------------------ veri temizleme

def test_clean_drops_isolated_close_spike_but_keeps_real_crash_days():
    bars = flat(10)
    # tek bar: kapanış -%30 sonra ertesi açılış geri +%40 (hatalı tick) → atılır
    bars[5] = bar(5, 100, 101, 69, 70)
    bars[6] = bar(6, 100, 101, 99, 100)
    out, st = data.clean(bars)
    assert st["spike_dropped"] == 1 and len(out) == 9
    # gerçek kriz: düşüş geri dönmüyor (ertesi gün de aşağıda) → korunur
    crash = flat(10)
    crash[5] = bar(5, 100, 101, 69, 70)
    crash[6] = bar(6, 70, 72, 66, 68)
    out2, st2 = data.clean(crash)
    assert st2["spike_dropped"] == 0 and len(out2) == 10


def test_clean_clips_absurd_wicks_and_fixes_bad_open():
    bars = flat(10)
    bars[4] = bar(4, 100, 100.3, 5.0, 100)          # low=5: sahte fitil
    out, st = data.clean(bars)
    assert st["wick_clipped"] >= 1 and out[4].low >= 99.0
    bars = flat(10)
    bars[4] = bar(4, 200, 200, 99.8, 100)            # açılış 2x ama kapanış normal
    out, st = data.clean(bars)
    assert st["open_fixed"] == 1 and out[4].open == pytest.approx(100.0)


def test_apply_splits_adjusts_history_and_rejects_unverified_ratio(monkeypatch):
    # 2:1 bölünme: eski fiyatlar 200, bölünmeden sonra 100
    pre = [bar(i, 200, 201, 199, 200) for i in range(5)]
    post = [bar(5 + i, 100, 101, 99, 100) for i in range(5)]
    d = (T0 + timedelta(days=5)).strftime("%Y%m%d")
    monkeypatch.setitem(data.SPLITS, "TST", [(d, 2.0)])
    adj = data.apply_splits("TST", pre + post)
    assert all(b.close == pytest.approx(100.0) for b in adj)
    assert adj[0].volume == pytest.approx(200.0)                      # hacim ters yönde ölçeklenir
    monkeypatch.setitem(data.SPLITS, "TST", [(d, 3.0)])               # veriyle uyuşmayan oran
    with pytest.raises(ValueError):
        data.apply_splits("TST", pre + post)


def test_longest_segment_drops_data_holes():
    a = [bar(i, 100, 101, 99, 100) for i in range(5)]
    b = [bar(100 + i, 100, 101, 99, 100) for i in range(20)]
    seg = data.longest_segment(a + b, 15.0)
    assert len(seg) == 20 and seg[0].ts == b[0].ts


def test_resample_4h_equity_sessions_and_fx_buckets():
    hours = [OHLCVBar(symbol="E", timeframe="1h", ts=datetime(2020, 1, 2, h, tzinfo=UTC), open=10 + h,
                      high=11 + h, low=9 + h, close=10.5 + h, volume=1.0) for h in range(9, 16)]
    eq = data.resample_4h(hours, "equity", "E")
    assert len(eq) == 2 and eq[0].open == hours[0].open and eq[-1].close == hours[-1].close
    fx_hours = [OHLCVBar(symbol="F", timeframe="1h", ts=datetime(2020, 1, 2, h, tzinfo=UTC), open=1, high=1.1,
                         low=0.9, close=1, volume=None) for h in range(0, 8)]
    fx = data.resample_4h(fx_hours, "fx", "F")
    assert len(fx) == 2 and fx[0].volume is None


# ------------------------------------------------------------------ yürütme simülasyonu

def _trend(n: int, step: float) -> list[OHLCVBar]:
    out, px = [], 100.0
    for i in range(n):
        o, c = px, px * (1 + step)
        out.append(bar(i, o, max(o, c) * 1.001, min(o, c) * 0.999, c))
        px = c
    return out


def _sig(i: int, side: int, size: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame([{"i": i, "side": side, "size": size, "atr": 1.0}])


def test_simulate_long_in_uptrend_wins_short_loses_and_costs_reduce_r():
    bars = _trend(80, 0.01)
    long_tr = metrics.simulate(bars, _sig(10, 1), "1d", "T", "equity")
    short_tr = metrics.simulate(bars, _sig(10, -1), "1d", "T", "equity")
    assert long_tr and short_tr
    assert long_tr[0]["r_gross"] > 0 and short_tr[0]["r_gross"] < 0
    assert long_tr[0]["r_net"] < long_tr[0]["r_gross"]                # ücret R'yi düşürür
    free = metrics.simulate(bars, _sig(10, 1), "1d", "T", "equity", cost_mult=0.0)
    assert free[0]["r_net"] == pytest.approx(free[0]["r_gross"])
    # giriş sonraki barın açılışında (look-ahead yok)
    assert long_tr[0]["entry_i"] == 11


def test_simulate_skips_wait_rows_and_zero_size_and_one_position_at_a_time():
    bars = _trend(120, 0.001)
    sig = pd.DataFrame([{"i": 10, "side": 0, "size": 1.0, "atr": 1.0},
                        {"i": 11, "side": 1, "size": 0.0, "atr": 1.0},
                        {"i": 12, "side": 1, "size": 1.0, "atr": 1.0},
                        {"i": 13, "side": 1, "size": 1.0, "atr": 1.0}])
    tr = metrics.simulate(bars, sig, "1d", "T", "equity")
    assert len(tr) >= 1 and tr[0]["sig_i"] == 12                      # WAIT/boyut-0 satırları açılmadı
    assert all(t["sig_i"] != 13 for t in tr[:1])                       # pozisyon açıkken yeni giriş yok


def test_portfolio_metrics_basic_identities():
    bars = _trend(200, 0.002)
    sig = pd.DataFrame([{"i": i, "side": 1, "size": 1.0, "atr": 1.0} for i in range(10, 180, 7)])
    tr = pd.DataFrame(metrics.simulate(bars, sig, "1d", "T", "equity"))
    m = metrics.portfolio_metrics(tr)
    assert m["n"] == len(tr) and m["long_n"] == m["n"] and m["short_n"] == 0
    assert m["total_r"] == pytest.approx((tr["r_net"] * tr["size"]).sum())
    assert m["max_dd_r"] >= 0
    assert metrics.portfolio_metrics(pd.DataFrame()) == {"n": 0}


def test_spearman_matches_known_values():
    assert metrics.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert metrics.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert pd.isna(metrics.spearman([1, 2], [1, 2]))


# ------------------------------------------------------------------ YENİ yön üretmez

def test_new_side_never_flips_and_asserts_on_violation():
    cand = pd.Series([1, -1, 0, 1, -1])
    rep = pd.DataFrame({"verdict": ["ok", "wait", "none", "reduce", "ok"]})
    out = compare.new_side(cand, rep)
    assert out.tolist() == [1, 0, 0, 1, -1]
    assert ((out == 0) | (out == cand)).all()


def test_test_split_is_chronological_and_purged():
    n = 400
    df = pd.DataFrame({"series": "S", "tf": "1d", "i": range(n),
                       "ts": pd.date_range("2010-01-01", periods=n, freq="D", tz="UTC")})
    out = prep.assign_splits(df)
    order = out["split"].tolist()
    first_val, first_test = order.index("val"), order.index("test")
    assert first_val < first_test
    assert "test" not in order[:first_test] and "train" not in order[first_val:]
    assert (out["split"] == "purge").sum() >= 2
    # purge sınırlarda: train→val ve val→test geçişlerinden hemen önce
    assert order[first_test - 1] == "purge"


def test_frozen_config_roundtrip(tmp_path):
    from packages.scoring import entry_quality
    cfg = entry_quality.EntryQualityConfig(mode="shadow", q_wait=0.33, range_weights={"20": 0.1, "60": 0.6, "120": 0.3})
    p = tmp_path / "f.json"
    sha = compare.freeze(cfg, p, {"x": 1})
    assert len(sha) == 16
    back = compare.load_frozen(p)
    assert back.q_wait == 0.33 and back.range_weights["60"] == 0.6 and back.mode == "shadow"
    assert back.ema20 == cfg.ema20            # tuple alanlar tuple olarak döner


# ------------------------------------------------------------------ sahibin bar arşivi okuyucusu

def test_bar_history_universe_reads_jsonl_cleans_and_classifies(tmp_path, monkeypatch):
    import json

    monkeypatch.chdir(Path(__file__).resolve().parents[2])      # config/assets.yaml göreli yol
    bars = [bar(i, 100 + i * 0.1, 100.5 + i * 0.1, 99.5 + i * 0.1, 100 + i * 0.1) for i in range(500)]
    lines = [json.dumps(b.model_dump(mode="json")) for b in bars]
    lines.insert(10, "{bozuk satir")                              # bozuk satır atlanır
    (tmp_path / "BTCUSD_1d.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "BTCUSD_15m.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")   # desteklenmeyen TF
    (tmp_path / "KISA_1d.jsonl").write_text("\n".join(lines[:50]) + "\n", encoding="utf-8")  # çok kısa
    uni = data.bar_history_universe(tmp_path)
    assert list(uni) == [("BTCUSD", "1d")]
    ser, got = uni[("BTCUSD", "1d")]
    assert ser.asset_class == "crypto" and len(got) == 500 and got[0].ts < got[-1].ts
