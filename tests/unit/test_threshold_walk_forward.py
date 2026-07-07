"""Y-4 — walk-forward doğrulama testleri (threshold_ab.sweep).

- Flag OFF → çıktı birebir eski şekil (walk_forward anahtarı bile yok).
- Flag ON → aday eğitim penceresinde seçilir; doğrulama penceresinde baseline'ı
  geçmezse öneri YOK (aşırı-uyum kapıda ölür); iki pencerede de geçerse önerilir.
Motor koşulmaz — run_signal_backtest sahte sonuçla (pencere + entry_ts'li
trade listesi) monkeypatch'lenir; sahte, override edilen eşiği load_thresholds
üzerinden görür (seam gerçek).
"""
from __future__ import annotations

from packages.data.registry.loader import load_thresholds, threshold_override
from packages.learning import threshold_ab

_PARAM = "paper_trading.tp_rr_ratio"
_WF_ON = {"threshold_ab": {"walk_forward": True, "split_ratio": 0.7}}


def _fake_result(train_avg: float, val_avg: float) -> dict:
    # 10 günlük pencere; split 0.7 → gün ≤7 eğitim, sonrası doğrulama.
    def t(day, pnl):
        return {"entry_ts": f"2026-06-{day:02d}T00:00:00+00:00", "pnl_pct": pnl}
    trades = [t(2, train_avg), t(5, train_avg), t(9, val_avg), t(10, val_avg)]
    n = len(trades)
    avg = round(sum(x["pnl_pct"] for x in trades) / n, 5)
    return {
        "status": "ok", "total_trades": n,
        "win_rate": round(sum(1 for x in trades if x["pnl_pct"] > 0) / n, 4),
        "avg_return_pct": avg, "profit_factor": None,
        "window": {"from": "2026-06-01T00:00:00+00:00",
                   "to": "2026-06-11T00:00:00+00:00"},
        "trades": trades,
    }


def _patch_backtest(monkeypatch, table: dict[float, tuple[float, float]]):
    """Eşik değeri → (train_avg, val_avg). Sahte, seam'den geçen değeri okur."""
    def fake(symbol="BTCUSD", timeframe="1d"):
        v = float(load_thresholds().get("paper_trading", {}).get("tp_rr_ratio"))
        tr, va = table[round(v, 2)]
        return _fake_result(tr, va)
    monkeypatch.setattr(threshold_ab.strategy_backtest, "run_signal_backtest", fake)


def test_flag_off_output_shape_unchanged(monkeypatch):
    _patch_backtest(monkeypatch, {2.0: (0.5, 0.5), 2.5: (2.0, -1.0)})
    rep = threshold_ab.sweep(_PARAM, [2.5])
    assert "walk_forward" not in rep
    assert "train" not in rep["baseline"] or rep["baseline"].get("train") is None
    assert "train" not in rep["runs"][0]
    # Eski davranış: tam-pencere ortalamasına göre öneri (2.5 full avg 0.5 = baseline
    # 0.5'i GEÇMEZ → öneri yok).
    assert rep["recommendation"] is None


def test_wf_blocks_overfit_candidate(monkeypatch):
    # 2.5 eğitimde parlak (2.0) ama doğrulamada çöküyor (−1.0) → öneri YOK.
    _patch_backtest(monkeypatch, {2.0: (0.5, 0.5), 2.5: (2.0, -1.0)})
    with threshold_override(_WF_ON):
        rep = threshold_ab.sweep(_PARAM, [2.5])
    assert rep["walk_forward"] == {"enabled": True, "split_ratio": 0.7}
    assert rep["best"]["value"] == 2.5          # eğitimde seçildi
    assert rep["best"]["validation"]["avg_return_pct"] == -1.0
    assert rep["recommendation"] is None         # doğrulama teyidi düştü


def test_wf_confirms_genuine_candidate(monkeypatch):
    # 3.0 iki pencerede de baseline'ı geçiyor → önerilir.
    _patch_backtest(monkeypatch, {2.0: (0.5, 0.5), 3.0: (1.5, 1.2)})
    with threshold_override(_WF_ON):
        rep = threshold_ab.sweep(_PARAM, [3.0])
    assert rep["recommendation"] is not None
    assert rep["recommendation"]["value"] == 3.0
    assert rep["baseline"]["train"]["avg_return_pct"] == 0.5
    assert rep["baseline"]["validation"]["avg_return_pct"] == 0.5


def test_wf_selection_is_train_window(monkeypatch):
    # Eğitim kazananı (2.5) doğrulamada düşerse, doğrulamada iyi olan diğer aday
    # (3.0) ARKA KAPIDAN önerilMEZ — walk-forward disiplini seçimi eğitime kilitler.
    _patch_backtest(monkeypatch, {2.0: (0.5, 0.5), 2.5: (2.0, -1.0), 3.0: (1.0, 1.0)})
    with threshold_override(_WF_ON):
        rep = threshold_ab.sweep(_PARAM, [2.5, 3.0])
    assert rep["best"]["value"] == 2.5
    assert rep["recommendation"] is None
