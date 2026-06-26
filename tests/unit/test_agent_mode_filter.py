from __future__ import annotations

from packages.mode import filter as mode_filter
from packages.mode.config import AgentModeConfig

DEFAULT = AgentModeConfig()


def test_default_config_passes_trend_setup():
    result = mode_filter.evaluate(
        setup_type="TREND_LONG", trade_profile="SWING", is_countertrend=False, cfg=DEFAULT
    )
    assert result.passed
    assert result.blocked_reason is None


def test_no_trade_or_no_profile_fails():
    result = mode_filter.evaluate(
        setup_type="NO_TRADE", trade_profile=None, is_countertrend=False, cfg=DEFAULT
    )
    assert not result.passed
    assert result.blocked_reason == "no_setup_or_profile"


def test_disabled_profile_blocks():
    cfg = AgentModeConfig(disabled_trade_profiles=("SCALP",))
    result = mode_filter.evaluate(
        setup_type="SCALP_LONG", trade_profile="SCALP", is_countertrend=False, cfg=cfg
    )
    assert not result.passed
    assert result.blocked_reason == "SCALP_disabled"
    assert result.watch_tracking_enabled is True


def test_enabled_allowlist_blocks_others():
    cfg = AgentModeConfig(enabled_trade_profiles=("SWING", "POSITION"))
    result = mode_filter.evaluate(
        setup_type="SCALP_LONG", trade_profile="SCALP", is_countertrend=False, cfg=cfg
    )
    assert not result.passed
    assert result.blocked_reason == "SCALP_not_in_enabled_profiles"


def test_counter_context_blocked_when_disabled():
    cfg = AgentModeConfig(allow_counter_context_trades=False)
    result = mode_filter.evaluate(
        setup_type="PULLBACK_LONG", trade_profile="TACTICAL", is_countertrend=True, cfg=cfg
    )
    assert not result.passed
    assert result.blocked_reason == "counter_context_trades_disabled"


def test_reversal_strategy_type_blocked_when_disabled():
    cfg = AgentModeConfig(allow_reversal_trades=False)
    result = mode_filter.evaluate(
        setup_type="REVERSAL_LONG_WATCH", trade_profile="TACTICAL", is_countertrend=False, cfg=cfg
    )
    assert not result.passed
    assert result.blocked_reason == "reversal_trades_disabled"


def test_range_strategy_type_blocked_when_disabled():
    cfg = AgentModeConfig(allow_range_trades=False)
    result = mode_filter.evaluate(
        setup_type="RANGE_SHORT", trade_profile="INTRADAY", is_countertrend=False, cfg=cfg
    )
    assert not result.passed
    assert result.blocked_reason == "range_trades_disabled"


def test_breakout_strategy_type_blocked_when_disabled():
    cfg = AgentModeConfig(allow_breakout_trades=False)
    result = mode_filter.evaluate(
        setup_type="BREAKOUT_LONG", trade_profile="TACTICAL", is_countertrend=False, cfg=cfg
    )
    assert not result.passed
    assert result.blocked_reason == "breakout_trades_disabled"


def test_scalp_setup_has_no_strategy_type_gate():
    cfg = AgentModeConfig(
        allow_reversal_trades=False, allow_trend_follow_trades=False,
        allow_range_trades=False, allow_breakout_trades=False,
    )
    result = mode_filter.evaluate(
        setup_type="SCALP_LONG", trade_profile="SCALP", is_countertrend=False, cfg=cfg
    )
    assert result.passed
