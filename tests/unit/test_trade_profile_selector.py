from __future__ import annotations

from packages.mode.profile_selector import select_profile


def test_no_trade_yields_no_profile():
    assert select_profile("NO_TRADE", "1d") is None


def test_scalp_setup_always_scalp_profile():
    assert select_profile("SCALP_LONG", "4h") == "SCALP"  # setup zaten kısa TF şartını uyguladı


def test_15m_maps_to_intraday():
    assert select_profile("TREND_LONG", "15m") == "INTRADAY"


def test_4h_maps_to_tactical():
    assert select_profile("TREND_LONG", "4h") == "TACTICAL"


def test_1d_maps_to_swing():
    assert select_profile("TREND_LONG", "1d") == "SWING"


def test_1w_maps_to_position():
    assert select_profile("TREND_LONG", "1w") == "POSITION"


def test_unknown_timeframe_yields_none():
    assert select_profile("TREND_LONG", None) is None
    assert select_profile("TREND_LONG", "3d") is None
