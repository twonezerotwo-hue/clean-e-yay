"""OHLCV orchestrator (T1).

Politika ([docs/DATA_POLICY.md]):
- Runtime'da **mock/fixture bar yasaktır**. Live provider başarısız olursa
  önce disk cache'teki (stale de olsa) gerçek veri kullanılır; o da yoksa
  boş liste döner → technicals None + DEGRADED.
- Fixture barlar yalnızca test/dev path: `TEST_USE_MOCK=true` veya açık
  `OHLCV_USE_FIXTURE=true`.

Routing:
- BTCUSD/ETHUSD → CoinGecko market_chart (15m/1h/1d native).
- XAU/XAG/DXY/VIX/... → Yahoo chart (15m/1h/1d/1w native).
- 4h = 1h barlarından resample (her iki kaynak için).
- 1w = kripto için 1d barlarından resample; yfinance native 1wk.

Disk cache `data/runtime/ohlcv/` altında, TTL TF'e orantılı — live
provider rate-limit yemez, testler network'e bağımlı olmaz.
"""
from __future__ import annotations

import os
import threading
from datetime import UTC, datetime

from packages.data.providers.ohlcv import cache, coingecko, fixtures, resample, yfinance
from packages.data.types import TIMEFRAMES, OHLCVBar, Timeframe

# İndikatör penceresi (EMA200) + pay; cache/payload boyutunu sınırlar.
_MAX_BARS: dict[Timeframe, int] = {
    "15m": 400,
    "1h": 1600,   # 4h resample sonrası 400 bar kalsın diye geniş
    "4h": 400,
    "1d": 600,
    "1w": 400,
}

_PROVIDER_NAMES = ("ohlcv_coingecko", "ohlcv_yfinance")

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


def _truthy(v: str | None) -> bool:
    return (v or "").lower() == "true"


def is_fixture_mode() -> bool:
    """Test/dev fixture path açık mı? Runtime'da false kalmalıdır."""
    return _truthy(os.environ.get("TEST_USE_MOCK")) or _truthy(
        os.environ.get("OHLCV_USE_FIXTURE")
    )


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
    with _LOCK:
        return {k: dict(v) for k, v in _STATUS.items()}


def reset_provider_status() -> None:
    with _LOCK:
        for v in _STATUS.values():
            v.update(
                status="unknown",
                last_success_at=None,
                last_error=None,
                calls=0,
                fallbacks=0,
            )


def _provider_for(symbol: str):
    if symbol in coingecko.SUPPORTED:
        return coingecko, "ohlcv_coingecko"
    if symbol in yfinance.SUPPORTED:
        return yfinance, "ohlcv_yfinance"
    return None, None


def _native_bars(symbol: str, tf: Timeframe) -> list[OHLCVBar]:
    provider, name = _provider_for(symbol)
    if provider is None or name is None:
        return []
    cached = cache.load(symbol, tf)
    if cached is not None and cached.fresh:
        return cached.bars
    try:
        bars = provider.get_bars(symbol, tf)
        error = None if bars else "provider returned no data"
    except Exception as exc:
        bars = None
        error = str(exc)[:200] or "provider raised"
    if bars:
        bars = bars[-_MAX_BARS[tf]:]
        _mark(name, ok=True)
        cache.save(symbol, tf, bars)
        return bars
    _mark(name, ok=False, error=error)
    if cached is not None:
        # Stale ama gerçek veri — TF freshness kuralı DEGRADED işaretler.
        _mark(name, ok=False, error="serving stale cache", fallback=True)
        return cached.bars
    return []


def get_bars(symbol: str, timeframe: str = "1d") -> list[OHLCVBar]:
    """Sembol+TF için OHLCV barları. Veri yoksa boş liste — asla crash,
    runtime'da asla fixture."""
    tf: Timeframe = timeframe if timeframe in TIMEFRAMES else "1d"  # type: ignore[assignment]
    if is_fixture_mode():
        return fixtures.get_bars(symbol, tf)
    if tf == "4h":
        base = get_bars(symbol, "1h")
        return resample.resample(base, "4h")[-_MAX_BARS["4h"]:]
    if tf == "1w" and symbol in coingecko.SUPPORTED:
        base = get_bars(symbol, "1d")
        return resample.resample(base, "1w")[-_MAX_BARS["1w"]:]
    return _native_bars(symbol, tf)
