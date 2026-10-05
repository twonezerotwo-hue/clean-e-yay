"""Keşif teknik analiz özeti — yeni hesap yok, motor çıktısının kompakt hali."""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from packages.data.providers.technical.timeframe import build_timeframe_result
from packages.data.types import OHLCVBar
from packages.discovery import scanner


def _wave_bars(n: int = 320) -> list[OHLCVBar]:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    out = []
    for i in range(n):
        c = 100.0 + i * 0.15 + 3.0 * math.sin(i / 9.0)
        out.append(OHLCVBar(symbol="TEST", timeframe="1d", ts=t0 + timedelta(days=i), open=c - 0.4,
                            high=c + 1.0, low=c - 1.0, close=c, volume=1000.0 + i, source="test",
                            verified=True))
    return out


def test_ta_summary_from_real_engine_has_levels_and_bias():
    ta = scanner._ta_summary(build_timeframe_result("TEST", "1d", _wave_bars()))
    assert set(ta) >= {"bias", "trend", "support", "resistance", "stop_reference",
                       "target_reference", "patterns", "confirmations", "fib", "evidence"}
    assert ta["bias"] in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert isinstance(ta["patterns"], list) and isinstance(ta["confirmations"], list)
    if ta["support"] is not None and ta["resistance"] is not None:
        assert ta["support"] <= ta["resistance"]


def test_ta_summary_tolerates_missing_fields():
    stub = SimpleNamespace(status="OK", score_overview=SimpleNamespace(direction_score=70.0),
                           key_levels=SimpleNamespace(atr=1.2))
    ta = scanner._ta_summary(stub)
    assert ta["support"] is None and ta["patterns"] == [] and ta["fib"] is None
