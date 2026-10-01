from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from packages.forecast import build_forecasts
from packages.portfolio import build_portfolio_risk


def _technical(atr: float = 10.0):
    return SimpleNamespace(key_levels=SimpleNamespace(atr=atr, atr_percent=None))


def test_forecast_bands_are_monotonic_and_direction_is_shadow_only():
    rows = build_forecasts(
        ["BRENT"],
        prices={"BRENT": SimpleNamespace(symbol="BRENT", price=80.0, status="OK")},
        impacts={"BRENT": SimpleNamespace(direction_score=0.8, confidence=0.75)},
        technicals={"BRENT": {"1d": _technical()}},
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    daily = next(row for row in rows if row.horizon == "1d")
    assert daily.available is True
    assert daily.p10 < daily.p25 < daily.p50 < daily.p75 < daily.p90
    assert daily.directional_bias == "BULLISH"
    assert daily.current_price == 80.0
    assert daily.volatility_source == "ATR:1d"


def test_forecast_does_not_fabricate_missing_volatility_or_price():
    rows = build_forecasts(
        ["BTCUSD", "XAUUSD"],
        prices={"BTCUSD": SimpleNamespace(symbol="BTCUSD", price=100.0, status="OK")},
        impacts={"BTCUSD": SimpleNamespace(direction_score=None, confidence=0.0)},
    )
    btc = next(row for row in rows if row.symbol == "BTCUSD" and row.horizon == "1d")
    xau = next(row for row in rows if row.symbol == "XAUUSD" and row.horizon == "1d")
    assert btc.available is False
    assert "observed_volatility" in btc.missing_inputs
    assert xau.available is False
    assert "verified_current_price" in xau.missing_inputs


def test_portfolio_risk_is_read_only_and_reports_thesis_conflict():
    state = SimpleNamespace(
        equity_usd=10_000.0,
        open_positions=[
            SimpleNamespace(symbol="BTCUSD", side="long", size_usd=2_000.0),
            SimpleNamespace(symbol="XAUUSD", side="short", size_usd=1_000.0),
        ],
    )
    report = build_portfolio_risk(
        state,
        impacts={
            "BTCUSD": SimpleNamespace(direction_score=-0.5, confidence=0.8),
            "XAUUSD": SimpleNamespace(direction_score=-0.4, confidence=0.8),
        },
    )
    assert report.status == "OK"
    assert report.gross_exposure_usd == 3_000.0
    assert report.net_exposure_usd == 1_000.0
    assert report.symbol_exposure["BTCUSD"]["gross_pct"] == 0.2
    assert report.thesis_conflicts[0]["symbol"] == "BTCUSD"
    assert "positions_against_world_thesis" in report.warnings

