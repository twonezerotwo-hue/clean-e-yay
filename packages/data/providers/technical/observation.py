"""Provider-aware technical observation time.

OHLCVBar.ts remains the opening timestamp.
For verified, completed Kraken candles, the technical
observation becomes available at the candle close.
Other providers retain legacy behavior unchanged.
"""
from datetime import timedelta

from packages.data.types import OHLCVBar, Timeframe

SECONDS = {
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}


def observed_at(bars: list[OHLCVBar], timeframe: Timeframe):
    if not bars:
        return None

    last = bars[-1]

    if last.source in {"kraken_spot", "binance_spot"} and last.verified:
        return last.ts + timedelta(seconds=SECONDS[timeframe])

    return last.ts
