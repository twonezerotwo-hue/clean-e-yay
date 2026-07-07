"""Y-3 — backtest-challenger geçmiş penceresi (lookback_days) testleri.

- lookback 0/yok → mevcut davranış (router serisi, derinleştirme YOK — bayt-aynı).
- lookback router derinliğini aşınca BTC yfinance BTC-USD ile derinleşir (yalnız
  izole challenger kanalı) ve pencereye kırpılır.
- Derin seri gelmezse (ağ/hata) mevcut seriyle sürer (dürüst düşüş).
"""
from __future__ import annotations

from types import SimpleNamespace

from packages.data.registry.loader import threshold_override
from packages.learning import backtest_recon as br


def _bars(n):
    return [SimpleNamespace(ts=f"t{i}", close=100.0 + i) for i in range(n)]


def _patch_router(monkeypatch, n=365):
    import packages.data.providers.ohlcv as ohlcv_pkg
    monkeypatch.setattr(ohlcv_pkg, "get_bars", lambda sym, tf: _bars(n))
    from packages.data.providers.price import fred
    monkeypatch.setattr(fred, "get_history", lambda sym: [])


def test_lookback_zero_keeps_router_series(monkeypatch):
    _patch_router(monkeypatch)
    from packages.data.providers.ohlcv import yfinance as yf
    called = {"n": 0}
    def _no_call(*a, **kw):
        called["n"] += 1
        return _bars(730)
    monkeypatch.setattr(yf, "fetch_by_ticker", _no_call)
    with threshold_override({"backtest_challenger": {"lookback_days": 0}}):
        bars_by_symbol, _ = br._load_series()
    assert len(bars_by_symbol["BTCUSD"]) == 365
    assert called["n"] == 0  # eski davranış: derin çekim hiç denenmez


def test_lookback_deepens_btc_via_yfinance(monkeypatch):
    _patch_router(monkeypatch)
    from packages.data.providers.ohlcv import yfinance as yf
    monkeypatch.setattr(yf, "fetch_by_ticker",
                        lambda ticker, symbol, tf: _bars(800))
    with threshold_override({"backtest_challenger": {"lookback_days": 730}}):
        bars_by_symbol, _ = br._load_series()
    assert len(bars_by_symbol["BTCUSD"]) == 730  # pencereye kırpıldı
    # Diğer semboller router'dan aynen (yalnız BTC derinleşir).
    other = next(s for s in bars_by_symbol if s != "BTCUSD")
    assert len(bars_by_symbol[other]) == 365


def test_lookback_falls_back_when_deep_fetch_fails(monkeypatch):
    _patch_router(monkeypatch)
    from packages.data.providers.ohlcv import yfinance as yf
    def _boom(*a, **kw):
        raise OSError("network down")
    monkeypatch.setattr(yf, "fetch_by_ticker", _boom)
    with threshold_override({"backtest_challenger": {"lookback_days": 730}}):
        bars_by_symbol, _ = br._load_series()
    assert len(bars_by_symbol["BTCUSD"]) == 365  # dürüst düşüş, patlama yok
