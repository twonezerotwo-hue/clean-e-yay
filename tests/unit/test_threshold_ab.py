"""CP4 — config-injection seam (threshold_override) + eşik A/B taraması testleri."""
from __future__ import annotations

from packages.data import strategy_backtest
from packages.data.registry import loader
from packages.learning import threshold_ab


# ── seam: load_thresholds + threshold_override ─────────────────────────────────

def test_no_override_is_byte_identical():
    # Override yokken load_thresholds base'i BİREBİR (aynı obje) döner → sıcak yol
    # bayt-aynı, zero-copy.
    a = loader.load_thresholds()
    b = loader.load_thresholds()
    assert a is b
    assert a is loader._load_thresholds_base()


def test_override_deep_merges_and_clears():
    base_val = loader.load_thresholds().get("paper_trading", {}).get("sl_pct")
    with loader.threshold_override({"paper_trading": {"sl_pct": 0.999}}):
        eff = loader.load_thresholds()
        assert eff["paper_trading"]["sl_pct"] == 0.999
        # deep-merge: paper_trading'in DİĞER alanları korunur (üzerine yazılmaz)
        assert "tp_rr_ratio" in eff["paper_trading"]
    # scope dışında base'e döner
    assert loader.load_thresholds().get("paper_trading", {}).get("sl_pct") == base_val


def test_empty_override_is_noop():
    a = loader.load_thresholds()
    with loader.threshold_override(None):
        assert loader.load_thresholds() is a
    with loader.threshold_override({}):
        assert loader.load_thresholds() is a


def test_nested_builder():
    assert threshold_ab._nested("a.b.c", 5) == {"a": {"b": {"c": 5}}}
    assert threshold_ab._nested("x", 1) == {"x": 1}


# ── A/B sweep — seam'i backtest scope'unda gerçekten uyguluyor mu ──────────────

def test_sweep_applies_override_during_backtest(monkeypatch):
    # Sentetik skaler path (base'de yok) — fake_bt o an ETKİN değeri metğe yansıtır
    # → sweep'in her değer için override'ı backtest scope'unda enjekte ettiğini kanıtlar.
    def fake_bt(symbol, timeframe):
        eff = loader.load_thresholds().get("ab_probe", {}).get("value", 0.0)
        return {
            "status": "ok", "total_trades": 10, "win_rate": 0.5,
            "avg_return_pct": eff,  # etkin override değerini geri yansıt
            "profit_factor": 1.2,
        }

    monkeypatch.setattr(strategy_backtest, "run_signal_backtest", fake_bt)
    out = threshold_ab.sweep("ab_probe.value", [0.01, 0.02, 0.03])
    seen = {r["value"]: r["avg_return_pct"] for r in out["runs"]}
    assert seen == {0.01: 0.01, 0.02: 0.02, 0.03: 0.03}  # her override uygulandı
    assert out["best"]["value"] == 0.03  # en yüksek avg_return
    # baseline (override yok) → path base'de yok → 0.0; öneri: best(0.03) > 0.0 → var
    assert out["baseline"]["avg_return_pct"] == 0.0
    assert out["recommendation"]["value"] == 0.03


def test_multi_symbol_sweep_aggregates_trade_weighted(monkeypatch):
    # Her sembol farklı trade sayısı/return → sepet trade-ağırlıklı ortalanmalı.
    per_sym = {
        "BTCUSD": {"status": "ok", "total_trades": 10, "win_rate": 0.5, "avg_return_pct": 0.02, "profit_factor": 2.0},
        "ETHUSD": {"status": "ok", "total_trades": 30, "win_rate": 0.6, "avg_return_pct": 0.04, "profit_factor": 2.0},
    }
    monkeypatch.setattr(strategy_backtest, "run_signal_backtest",
                        lambda s, t: dict(per_sym[s]))
    out = threshold_ab.sweep("paper_trading.tp_rr_ratio", [2.0],
                             symbols=["BTCUSD", "ETHUSD"])
    b = out["baseline"]
    assert b["total_trades"] == 40  # 10 + 30
    # trade-ağırlıklı: (0.02*10 + 0.04*30) / 40 = 0.035
    assert b["avg_return_pct"] == 0.035
    assert out["symbols"] == ["BTCUSD", "ETHUSD"]


def test_sweep_no_recommendation_when_not_better(monkeypatch):
    # Tüm değerler baseline ile aynı → öneri YOK (sadece açıkça iyiyse önerir).
    monkeypatch.setattr(
        strategy_backtest, "run_signal_backtest",
        lambda s, t: {"status": "ok", "total_trades": 5, "win_rate": 0.4,
                      "avg_return_pct": 0.01, "profit_factor": 1.0},
    )
    out = threshold_ab.sweep("paper_trading.sl_pct", [0.01, 0.02])
    assert out["recommendation"] is None
