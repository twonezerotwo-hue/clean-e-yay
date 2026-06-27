"""DefiLlama — DeFi TVL/likidite verisi (key gerektirmez, public API).

Henüz karar zincirine/rotasyon motoruna bağlanmadı — bu modül sadece
fetch katmanını sağlar (DATA_POLICY: hata → None, mock yok). Dashboard'a
bağlamak ayrı bir adımdır.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

API_CHAINS = "https://api.llama.fi/v2/chains"
API_PROTOCOL = "https://api.llama.fi/protocol"
TIMEOUT_SEC = 6.0

_DEFAULT_TTL_SEC = 1800  # TVL günlük değişir, sık çağrı gerekmez
_LOCK = threading.Lock()
_CHAIN_CACHE: tuple[float, dict[str, float]] | None = None
_PROTOCOL_CACHE: dict[str, tuple[float, "ProtocolTvl"]] = {}


@dataclass(frozen=True)
class ProtocolTvl:
    protocol: str
    tvl_usd: float
    chain_tvls: dict[str, float]


def _get_json(url: str) -> dict | list | None:
    req = urllib.request.Request(url, headers={"User-Agent": "clean-e-yay/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def get_chain_tvl(chain: str) -> float | None:
    """Zincir başına toplam TVL (USD). Hata/timeout → None."""
    global _CHAIN_CACHE
    now = time.monotonic()
    with _LOCK:
        if _CHAIN_CACHE and (now - _CHAIN_CACHE[0]) < _DEFAULT_TTL_SEC:
            return _CHAIN_CACHE[1].get(chain)
    data = _get_json(API_CHAINS)
    if not isinstance(data, list):
        return None
    by_chain = {
        str(row.get("name", "")).lower(): float(row.get("tvl") or 0.0)
        for row in data
        if isinstance(row, dict)
    }
    with _LOCK:
        _CHAIN_CACHE = (now, by_chain)
    return by_chain.get(chain.lower())


def get_protocol_tvl(protocol: str) -> ProtocolTvl | None:
    """Protokol bazlı TVL (örn. 'aave', 'uniswap'). Hata → None."""
    now = time.monotonic()
    with _LOCK:
        cached = _PROTOCOL_CACHE.get(protocol)
        if cached and (now - cached[0]) < _DEFAULT_TTL_SEC:
            return cached[1]
    data = _get_json(f"{API_PROTOCOL}/{protocol}")
    if not isinstance(data, dict):
        return None
    tvl_series = data.get("tvl") or []
    if not tvl_series:
        return None
    latest = tvl_series[-1]
    tvl_usd = latest.get("totalLiquidityUSD")
    if tvl_usd is None:
        return None
    chain_tvls_raw = data.get("currentChainTvls") or {}
    result = ProtocolTvl(
        protocol=protocol,
        tvl_usd=float(tvl_usd),
        chain_tvls={k: float(v) for k, v in chain_tvls_raw.items()},
    )
    with _LOCK:
        _PROTOCOL_CACHE[protocol] = (now, result)
    return result
