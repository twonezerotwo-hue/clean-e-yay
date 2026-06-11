"""Fiyat sağlayıcısı — varsayılan mock. v2.1+ ile yfinance/FRED/CoinGecko eklenecek."""
from __future__ import annotations

import os

from packages.data.providers.price import mock
from packages.data.types import PriceQuote

USE_MOCK = os.environ.get("PRICE_USE_MOCK", "true").lower() != "false"


def get_quote(symbol: str) -> PriceQuote:
    if USE_MOCK:
        return mock.get_quote(symbol)
    return mock.get_quote(symbol)


def get_quotes(symbols: list[str]) -> list[PriceQuote]:
    if USE_MOCK:
        return mock.get_quotes(symbols)
    return mock.get_quotes(symbols)
