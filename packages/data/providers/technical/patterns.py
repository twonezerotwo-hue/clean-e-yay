"""Chart-pattern detection (section 4.5) — swing-structure read (HH/HL vs LH/LL).

Pure function over closed OHLCV bars. EVIDENCE only — never opens a trade, never feeds
a single aggregate score, and is not the RiskGate. Too few bars/pivots → None (absent,
never fabricated). A clean higher-highs + higher-lows structure is an uptrend; lower-
highs + lower-lows is a downtrend; anything mixed is ranging (a real read, not a guess).
"""
from __future__ import annotations

from packages.data.providers.technical import indicators
from packages.data.types import ChartPattern, OHLCVBar, TechnicalChartPatterns

_MIN_BARS = 20


def detect(
    bars: list[OHLCVBar], *, left: int = 2, right: int = 2
) -> TechnicalChartPatterns | None:
    """Read the swing structure into one active pattern + bias, or None on no data."""
    if len(bars) < _MIN_BARS:
        return None
    piv = indicators.swing_pivots(bars, left=left, right=right)
    if piv is None:
        return None
    highs, lows = piv
    if len(highs) < 2 or len(lows) < 2:
        return TechnicalChartPatterns(
            active_patterns=[ChartPattern(name="ranging", detail="insufficient swing structure")],
            bias="NEUTRAL",
        )
    higher_high = highs[-1] > highs[-2]
    higher_low = lows[-1] > lows[-2]
    lower_high = highs[-1] < highs[-2]
    lower_low = lows[-1] < lows[-2]
    if higher_high and higher_low:
        return TechnicalChartPatterns(
            active_patterns=[
                ChartPattern(name="uptrend_structure", detail="higher highs + higher lows")
            ],
            bias="BULLISH",
        )
    if lower_high and lower_low:
        return TechnicalChartPatterns(
            active_patterns=[
                ChartPattern(name="downtrend_structure", detail="lower highs + lower lows")
            ],
            bias="BEARISH",
        )
    return TechnicalChartPatterns(
        active_patterns=[ChartPattern(name="ranging", detail="mixed swing structure")],
        bias="NEUTRAL",
    )
