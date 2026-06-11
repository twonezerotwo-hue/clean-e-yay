"""Mock fiyat sağlayıcı — deterministik, test ve baseline kullanımı için."""
from __future__ import annotations

import hashlib
import math
import time

from packages.data.types import PriceQuote

# Baseline değerleri — gerçek piyasaya yakın ama deterministik
BASELINE = {
    "BTCUSD": 68_000.0,
    "ETHUSD": 3_500.0,
    "XAUUSD": 2_350.0,
    "XAGUSD": 28.0,
    "BRENT": 82.0,
    "DXY": 104.0,
    "US10Y": 4.3,
    "VIX": 14.0,
    "QQQ": 460.0,
    "SP500": 5_300.0,
}


def _wiggle(symbol: str, t: float) -> float:
    """Deterministik sinüs salınımı. Aynı (symbol, t) için aynı sonuç."""
    h = int(hashlib.sha1(symbol.encode()).hexdigest()[:8], 16) % 1000
    return 0.005 * math.sin((t + h) / 90.0)  # ±%0.5


def get_quote(symbol: str, *, t: float | None = None) -> PriceQuote:
    base = BASELINE.get(symbol)
    if base is None:
        return PriceQuote(symbol=symbol, price=0.0, source="mock", fallback=True)
    now = t if t is not None else time.time()
    price = base * (1.0 + _wiggle(symbol, now))
    return PriceQuote(symbol=symbol, price=round(price, 4), source="mock")


def get_quotes(symbols: list[str]) -> list[PriceQuote]:
    now = time.time()
    return [get_quote(s, t=now) for s in symbols]
