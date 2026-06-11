"""Fiyat orchestrator — sembolü doğru sağlayıcıya yönlendirir.

Kurallar:
- `PRICE_USE_MOCK=true` (default) → daima mock kullan.
- `PRICE_USE_MOCK=false` → primary live sağlayıcıyı dene. Hata/None
  durumunda mock'a düş ve `fallback=True` işaretle.
- Provider durumları process-içi sözlükte tutulur ve `get_provider_status()`
  ile snapshot/API'ye verilir.

Test/CI offline kalır: PRICE_USE_MOCK default true olduğu için live
çağrı yapılmaz.
"""
from __future__ import annotations

import os
import threading
from datetime import UTC, datetime

from packages.data.providers.price import coingecko, fred, mock, yfinance
from packages.data.types import PriceQuote

USE_MOCK = os.environ.get("PRICE_USE_MOCK", "true").lower() != "false"

# Sembol → birincil sağlayıcı modülü. Eşleşmeyen sembol mock'a düşer.
_PRIMARY = {
    **{s: coingecko for s in coingecko.SUPPORTED},
    **{s: yfinance for s in yfinance.SUPPORTED},
    **{s: fred for s in fred.SUPPORTED},
}

_PROVIDER_NAMES = ("coingecko", "yfinance", "fred", "mock")

_LOCK = threading.Lock()
_STATUS: dict[str, dict] = {
    name: {
        "status": "unknown",
        "last_success_at": None,
        "last_error": None,
        "calls": 0,
        "fallbacks": 0,
    }
    for name in _PROVIDER_NAMES
}


def _provider_name(mod) -> str:
    return mod.__name__.rsplit(".", 1)[-1]


def _mark(name: str, *, ok: bool, error: str | None = None, fallback: bool = False) -> None:
    with _LOCK:
        st = _STATUS[name]
        st["calls"] += 1
        if ok:
            st["status"] = "ok"
            st["last_success_at"] = datetime.now(UTC).isoformat()
            st["last_error"] = None
        else:
            st["status"] = "degraded"
            if error:
                st["last_error"] = error
        if fallback:
            st["fallbacks"] += 1


def get_provider_status() -> dict[str, dict]:
    """Son durum kopyası — okuma için, mutate edilmez."""
    with _LOCK:
        return {k: dict(v) for k, v in _STATUS.items()}


def reset_provider_status() -> None:
    """Test/dev için sayaç sıfırlama."""
    with _LOCK:
        for v in _STATUS.values():
            v.update(
                status="unknown",
                last_success_at=None,
                last_error=None,
                calls=0,
                fallbacks=0,
            )


def _try_live(symbol: str) -> PriceQuote | None:
    primary = _PRIMARY.get(symbol)
    if primary is None:
        return None
    name = _provider_name(primary)
    try:
        q = primary.get_quote(symbol)
    except Exception as exc:  # provider iç hatası — sessizce mock'a düş
        _mark(name, ok=False, error=str(exc)[:200])
        return None
    if q is None:
        _mark(name, ok=False, error="no_data")
        return None
    _mark(name, ok=True)
    return q


def _mock_quote(symbol: str, *, fallback: bool) -> PriceQuote:
    q = mock.get_quote(symbol)
    if fallback:
        q = q.model_copy(update={"fallback": True})
        _mark("mock", ok=True, fallback=True)
    else:
        _mark("mock", ok=True)
    return q


def get_quote(symbol: str) -> PriceQuote:
    if USE_MOCK:
        return _mock_quote(symbol, fallback=False)
    live = _try_live(symbol)
    if live is not None:
        return live
    # Live başarısız → mock fallback
    return _mock_quote(symbol, fallback=True)


def get_quotes(symbols: list[str]) -> list[PriceQuote]:
    return [get_quote(s) for s in symbols]
