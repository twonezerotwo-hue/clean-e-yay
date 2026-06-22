"""CoinGecko fiyat sağlayıcı — kripto (BTC/ETH).

Demo API anahtarı (`COINGECKO_API_KEY`) varsa kimlik doğrulamalı çağrılır
(`x-cg-demo-api-key`). Hata/timeout → None döner; orchestrator DATA_UNAVAILABLE
verir (MOCK YOK, fallback YOK).

Aylık limit koruması: Demo plan 10.000 çağrı/ay. Spot fiyat sürekli 30sn'de
çağrılırsa limit ~1.5 günde biter. Bu yüzden modül seviyesinde
`COINGECKO_PRICE_TTL_SEC` (varsayılan 900sn = 15dk) TTL cache'i ile çağrı
sıklığı sabitlenir; cache içindeki taze değer ağ çağrısı yapmadan döner.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

from packages.data.providers import coingecko_auth
from packages.data.types import PriceQuote, utcnow

API = "https://api.coingecko.com/api/v3/simple/price"
TIMEOUT_SEC = 4.0

# CoinGecko id ↔ bizim sembolümüz
_SYMBOL_MAP = {
    "BTCUSD": "bitcoin",
    "ETHUSD": "ethereum",
}

SUPPORTED = frozenset(_SYMBOL_MAP.keys())

# Aylık ücretsiz limiti korumak için modül-seviyesi TTL cache.
_DEFAULT_TTL_SEC = 900
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, PriceQuote]] = {}


def _ttl_sec() -> float:
    try:
        return float(os.environ.get("COINGECKO_PRICE_TTL_SEC", _DEFAULT_TTL_SEC))
    except (TypeError, ValueError):
        return float(_DEFAULT_TTL_SEC)


def _fetch(symbol: str, cg_id: str) -> PriceQuote | None:
    url = f"{API}?ids={cg_id}&vs_currencies=usd"
    req = urllib.request.Request(url, headers=coingecko_auth.headers())
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


def get_quote(symbol: str) -> PriceQuote | None:
    cg_id = _SYMBOL_MAP.get(symbol)
    if cg_id is None:
        return None
    ttl = _ttl_sec()
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(symbol)
        if cached and (now - cached[0]) < ttl:
            return cached[1]
    quote = _fetch(symbol, cg_id)
    # Yalnızca başarılı (taze) sonucu cache'le — None'ı cache'leme ki
    # bir sonraki cycle tekrar denesin (stale fallback YOK).
    if quote is not None:
        with _LOCK:
            _CACHE[symbol] = (now, quote)
    return quote
