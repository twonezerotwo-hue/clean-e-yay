"""Mock fiyat sağlayıcı — yalnızca TEST/DEV path için.

Önemli: bu modüldeki fonksiyonlar runtime'da çağrılmaz. Orchestrator
(`packages.data.providers.price.__init__`) `TEST_USE_MOCK=true` veya
açık `PRICE_USE_MOCK=true` durumunda devreye sokar. Her quote
`verified=False`, `status="MOCK"` damgalıdır; learning ve karar
katmanları bu damgaya bakarak filtreler.
"""
from __future__ import annotations

import hashlib
import math
import time

from packages.data.types import PriceQuote

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
    h = int(hashlib.sha1(symbol.encode()).hexdigest()[:8], 16) % 1000
    return 0.005 * math.sin((t + h) / 90.0)


def get_quote(symbol: str, *, t: float | None = None) -> PriceQuote:
    base = BASELINE.get(symbol)
    if base is None:
        return PriceQuote(
            symbol=symbol,
            price=None,
            source="mock",
            verified=False,
            status="DATA_UNAVAILABLE",
            error="symbol not in mock baseline",
        )
    now = t if t is not None else time.time()
    price = round(base * (1.0 + _wiggle(symbol, now)), 4)
    return PriceQuote(
        symbol=symbol,
        price=price,
        source="mock",
        verified=False,
        status="MOCK",
    )


def get_quotes(symbols: list[str]) -> list[PriceQuote]:
    now = time.time()
    return [get_quote(s, t=now) for s in symbols]
