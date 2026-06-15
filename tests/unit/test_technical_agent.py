"""TechnicalAgent (T2) tests — stance logic + architecture guards.

Builds real per-TF results via the feature builder (deterministic synthetic bars),
then checks the agent's stance, invalidation, and missing_data behaviour. The
agent must ABSTAIN/DEGRADED on missing data and must never expose trade/size fields.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.agent import technical_agent
from packages.data.providers.technical import timeframe as tf
from packages.data.types import OHLCVBar


def _bars(n, *, step, start=100.0, tf_label="1d", spacing_h=24):
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    out = []
    for i in range(n):
        c = start + step * i
        out.append(
            OHLCVBar(
                symbol="BTCUSD",
                timeframe=tf_label,
                ts=t0 + timedelta(hours=spacing_h * i),
                open=c,
                high=c + 0.5,
                low=c - 0.5,
                close=c,
                volume=1000.0 + i,
                source="fixture",
            )
        )
    return out


def _result(tf_label, step, *, n=260, spacing_h=24):
    bars = _bars(n, step=step, tf_label=tf_label, spacing_h=spacing_h)
    return tf.build_timeframe_result("BTCUSD", tf_label, bars, now=bars[-1].ts)


def test_technical_agent_allow_on_aligned_uptrend():
    per_tf = {
        "1d": _result("1d", 1.0),
        "4h": _result("4h", 1.0, spacing_h=4),
        "1h": _result("1h", 1.0, spacing_h=1),
    }
    out = technical_agent.evaluate("BTCUSD", per_tf)
    assert out.agent == "technical"
    assert out.stance == "ALLOW"
    assert out.direction_score is not None and out.direction_score > 60.0
    assert out.invalidation is not None and out.invalidation.price is not None
    assert out.missing_data == []
    assert len(out.used_observations) == 3


def test_technical_agent_abstain_on_missing():
    # All timeframes built from too few bars → degraded / no direction.
    per_tf = {
        "1d": _result("1d", 1.0, n=5),
        "4h": _result("4h", 1.0, n=5, spacing_h=4),
    }
    out = technical_agent.evaluate("BTCUSD", per_tf)
    assert out.stance == "ABSTAIN"
    assert out.direction_score is None
    assert set(out.missing_data) == {"d1", "h4"}


def test_technical_agent_abstain_on_empty():
    out = technical_agent.evaluate("BTCUSD", {})
    assert out.stance == "ABSTAIN"
    assert out.missing_data == ["no_timeframes"]


def test_technical_agent_caution_on_conflict():
    per_tf = {
        "1d": _result("1d", 1.0),                  # BULLISH
        "1h": _result("1h", -1.0, spacing_h=1),    # BEARISH
    }
    out = technical_agent.evaluate("BTCUSD", per_tf)
    assert out.stance == "CAUTION"


def test_technical_agent_per_timeframe_uses_contract_keys():
    per_tf = {"1d": _result("1d", 1.0), "15m": _result("15m", 1.0, spacing_h=1)}
    out = technical_agent.evaluate("BTCUSD", per_tf)
    assert set(out.per_timeframe.keys()) == {"d1", "m15"}


def test_technical_agent_is_paper_safe():
    out = technical_agent.evaluate("BTCUSD", {"1d": _result("1d", 1.0)})
    # The agent never trades or sizes — no execution surface on its output.
    for forbidden in ("size", "action", "order", "quantity", "risk_multiplier"):
        assert not hasattr(out, forbidden)
