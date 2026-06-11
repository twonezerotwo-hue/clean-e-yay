"""CoinGecko fiyat sağlayıcı — kripto (BTC/ETH).

Public REST API, anahtar gerektirmez. Hata/timeout durumunda None döner;
orchestrator mock'a düşer.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from packages.data.types import PriceQuote, utcnow

API = "https://api.coingecko.com/api/v3/simple/price"
TIMEOUT_SEC = 4.0

# CoinGecko id ↔ bizim sembolümüz
_SYMBOL_MAP = {
    "BTCUSD": "bitcoin",
    "ETHUSD": "ethereum",
}

SUPPORTED = frozenset(_SYMBOL_MAP.keys())


def get_quote(symbol: str) -> PriceQuote | None:
    cg_id = _SYMBOL_MAP.get(symbol)
    if cg_id is None:
        return None
    url = f"{API}?ids={cg_id}&vs_currencies=usd"
    req = urllib.request.Request(url, headers={"User-Agent": "clean-e-yay/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    px = data.get(cg_id, {}).get("usd")
    if px is None:
        return None
    return PriceQuote(
        symbol=symbol,
        price=float(px),
        ts=utcnow(),
        source="coingecko",
        verified=True,
        status="OK",
        fallback=False,
    )
