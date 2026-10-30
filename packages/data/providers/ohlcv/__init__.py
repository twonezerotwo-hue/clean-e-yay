"""OHLCV orchestrator (T1).

Politika ([docs/DATA_POLICY.md]):
- Runtime'da **mock/fixture bar yasaktır**. Live provider başarısız olursa
  yalnız teknik tazelik sınırı içindeki gerçek cache kullanılır; daha eski
  cache hesaplamaya girmez ve boş liste döner → technicals None + DEGRADED.
- Fixture barlar yalnızca test/dev path: `TEST_USE_MOCK=true` veya açık
  `OHLCV_USE_FIXTURE=true`.

Routing:
- BTCUSD/ETHUSD → Kraken spot OHLCV when enabled, CoinGecko market_chart
  otherwise (15m/1h/1d native). Kraken is read-only and is the live fallback
  that prevents a CoinGecko outage from serving old disk bars first.
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

from packages.data.providers.ohlcv import (
    binance,
    cache,
    coingecko,
    fixtures,
    history,
    kraken,
    resample,
    yfinance,
)
from packages.data.types import TIMEFRAMES, OHLCVBar, Timeframe

# İndikatör penceresi (EMA200) + pay; cache/payload boyutunu sınırlar.
_MAX_BARS: dict[Timeframe, int] = {
    "15m": 400,
    "1h": 1600,   # 4h resample sonrası 400 bar kalsın diye geniş
    "4h": 400,
    "1d": 600,
    "1w": 400,
}

_PROVIDER_NAMES = ("ohlcv_coingecko", "ohlcv_yfinance", "ohlcv_kraken", "ohlcv_binance")
# Gerçek mum (borsa spot) kaynakları: önbellekleri sağlayıcı adına karışmaz.
_SPOT_SOURCES = frozenset({"kraken_spot", "binance_spot"})

_LOCK = threading.Lock()
_STATUS: dict[str, dict] = {
    name: {
        "status": "unknown",
        "last_success_at": None,
        "last_fallback_at": None,
        "last_error": None,
        "last_error_type": None,
        "last_retry_after": None,
        "last_cache_age_seconds": None,
        "calls": 0,
        "fallbacks": 0,
        # Internal per-symbol scope; exported as a JSON-safe list below.
        "degraded_symbols": set(),
    }
    for name in _PROVIDER_NAMES
}

# A stale bar may be retained for replay/diagnostics, but it must not remain
# in a technical calculation after the same freshness boundary used by the
# technical provider.  Returning an empty series here makes the existing
# technical snapshot and final paper gate fail closed instead of scoring old
# candles as if they were current.
_MAX_STALE_SEC: dict[Timeframe, int] = {
    "15m": 1800,
    "1h": 7200,
    "4h": 28800,
    "1d": 172800,
    "1w": 864000,
}
_RECENT_FALLBACK_WINDOW_SEC = 120.0


def _truthy(v: str | None) -> bool:
    return (v or "").lower() == "true"


def is_fixture_mode() -> bool:
    """Test/dev fixture path açık mı? Runtime'da false kalmalıdır."""
    return _truthy(os.environ.get("TEST_USE_MOCK")) or _truthy(
        os.environ.get("OHLCV_USE_FIXTURE")
    )


def _mark(
    name: str,
    *,
    ok: bool,
    error: str | None = None,
    error_type: str | None = None,
    retry_after: float | None = None,
    fallback: bool = False,
    cache_age_seconds: float | None = None,
    symbol: str | None = None,
) -> None:
    with _LOCK:
        st = _STATUS[name]
        st["calls"] += 1
        if ok:
            st["status"] = "ok"
            st["last_success_at"] = datetime.now(UTC).isoformat()
            st["last_error"] = None
            st["last_error_type"] = None
            st["last_retry_after"] = None
        else:
            st["status"] = "degraded"
            if error:
                st["last_error"] = error
            if error_type:
                st["last_error_type"] = error_type
            st["last_retry_after"] = retry_after
        if cache_age_seconds is not None:
            st["last_cache_age_seconds"] = round(float(cache_age_seconds), 1)
        if fallback:
            st["fallbacks"] += 1
            st["last_fallback_at"] = datetime.now(UTC).isoformat()
        if symbol and not ok:
            st["degraded_symbols"].add(str(symbol).upper())


def get_provider_status() -> dict[str, dict]:
    with _LOCK:
        out = {k: dict(v) for k, v in _STATUS.items()}
    for info in out.values():
        if isinstance(info.get("degraded_symbols"), set):
            info["degraded_symbols"] = sorted(info["degraded_symbols"])
    # A provider can have a successful request for one symbol and a stale
    # fallback for another in the same snapshot.  The last event wins; do not
    # let the later success hide the fallback from health/provenance views.
    for info in out.values():
        success = str(info.get("last_success_at") or "")
        fallback = str(info.get("last_fallback_at") or "")
        recent_fallback = False
        if fallback:
            try:
                recent_fallback = (
                    datetime.now(UTC)
                    - datetime.fromisoformat(fallback)
                ).total_seconds() <= _RECENT_FALLBACK_WINDOW_SEC
            except (TypeError, ValueError):
                recent_fallback = False
        # A later successful symbol must not hide a stale fallback that
        # happened in the same snapshot.  The short window also lets the
        # provider recover to OK after a clean subsequent cycle instead of
        # leaving a historical fallback stuck forever.
        if fallback and (recent_fallback or not success or fallback >= success):
            info["status"] = "degraded"
            if not info.get("last_error_type"):
                info["last_error_type"] = "stale_cache"
            if not info.get("last_error"):
                info["last_error"] = "serving stale cache"
    return out


def reset_provider_status() -> None:
    with _LOCK:
        for v in _STATUS.values():
            v.update(
                status="unknown",
                last_success_at=None,
                last_fallback_at=None,
                last_error=None,
                last_error_type=None,
                last_retry_after=None,
                last_cache_age_seconds=None,
                calls=0,
                fallbacks=0,
                degraded_symbols=set(),
            )


def _provider_for(symbol: str):
    if symbol in coingecko.SUPPORTED:
        return coingecko, "ohlcv_coingecko"
    if symbol in yfinance.SUPPORTED:
        return yfinance, "ohlcv_yfinance"
    return None, None


def _binance_bars(symbol: str, tf: Timeframe) -> list[OHLCVBar]:
    """Binance spot gerçek mumları: taze güvenilir önbellek → canlı → bayat önbellek."""
    cached = cache.load(symbol, tf)
    trusted = (
        cached is not None
        and len(cached.bars) >= binance.MIN_BARS
        and all(b.source == "binance_spot" and b.verified for b in cached.bars)
    )
    if trusted and cached.fresh:
        _mark("ohlcv_binance", ok=True, cache_age_seconds=cached.age_seconds)
        return cached.bars
    live = binance.get_bars(symbol, tf)
    if live is not None:
        live = live[-_MAX_BARS[tf]:]
        cache.save(symbol, tf, live)
        _mark("ohlcv_binance", ok=True)
        return live
    _mark("ohlcv_binance", ok=False, error="real_candles_unavailable", symbol=symbol)
    if trusted and cached.age_seconds <= _MAX_STALE_SEC[tf]:
        _mark(
            "ohlcv_binance", ok=False, error="serving_previous_real_candles", error_type="stale_cache",
            fallback=True, cache_age_seconds=cached.age_seconds, symbol=symbol,
        )
        return cached.bars
    return []


def _native_bars(symbol: str, tf: Timeframe) -> list[OHLCVBar]:
    if kraken.enabled_for(symbol):
        cached_kraken = cache.load(symbol, tf)

        trusted_cache = (
            cached_kraken is not None
            and len(cached_kraken.bars) >= 200
            and all(
                b.source == "kraken_spot" and b.verified
                for b in cached_kraken.bars
            )
        )

        if trusted_cache and cached_kraken.fresh:
            _mark("ohlcv_kraken", ok=True, cache_age_seconds=cached_kraken.age_seconds)
            return cached_kraken.bars

        live_kraken = kraken.get_bars(symbol, tf)

        if live_kraken is not None:
            live_kraken = live_kraken[-_MAX_BARS[tf]:]
            cache.save(symbol, tf, live_kraken)
            _mark("ohlcv_kraken", ok=True)
            return live_kraken

        _mark(
            "ohlcv_kraken",
            ok=False,
            error="real_candles_unavailable",
            symbol=symbol,
        )

        if trusted_cache:
            if cached_kraken.age_seconds > _MAX_STALE_SEC[tf]:
                _mark(
                    "ohlcv_kraken",
                    ok=False,
                    error="stale cache exceeds technical freshness",
                    error_type="stale_cache_expired",
                    fallback=True,
                    cache_age_seconds=cached_kraken.age_seconds,
                    symbol=symbol,
                )
                # Kraken uzun süre kapalı: aynı nitelikte (gerçek mum) Binance spot
                # denenir; CoinGecko'ya bilerek düşülmez.
                if binance.enabled_for(symbol):
                    return _binance_bars(symbol, tf)
                return []
            _mark(
                "ohlcv_kraken",
                ok=False,
                error="serving_previous_real_candles",
                error_type="stale_cache",
                fallback=True,
                cache_age_seconds=cached_kraken.age_seconds,
                symbol=symbol,
            )
            return cached_kraken.bars

    # Binance spot (owner kararı 2026-10-30): Kraken'den sonra, CoinGecko'dan önce
    # gerçek mum kaynağı; CoinGecko'nun aylık kotasına bağımlılığı kaldırır.
    if binance.enabled_for(symbol):
        spot = _binance_bars(symbol, tf)
        if spot:
            return spot

    provider, name = _provider_for(symbol)
    if provider is None or name is None:
        return []
    cached = cache.load(symbol, tf)
    if cached is not None and any(
        b.source in _SPOT_SOURCES for b in cached.bars
    ):
        cached = None
    if cached is not None and cached.fresh:
        _mark(name, ok=True, cache_age_seconds=cached.age_seconds)
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
    provider_meta = provider.last_fetch_error() if hasattr(provider, "last_fetch_error") else {}
    _mark(
        name,
        ok=False,
        error=(provider_meta or {}).get("message") or error,
        error_type=(provider_meta or {}).get("type"),
        retry_after=(provider_meta or {}).get("retry_after"),
        symbol=symbol,
    )
    if cached is not None:
        # Stale ama gerçek veri — TF freshness kuralı DEGRADED işaretler.
        if cached.age_seconds > _MAX_STALE_SEC[tf]:
            _mark(
                name,
                ok=False,
                error="stale cache exceeds technical freshness",
                error_type="stale_cache_expired",
                fallback=True,
                cache_age_seconds=cached.age_seconds,
                symbol=symbol,
            )
            return []
        _mark(
            name,
            ok=False,
            error="serving stale cache",
            error_type="stale_cache",
            fallback=True,
            cache_age_seconds=cached.age_seconds,
            symbol=symbol,
        )
        return cached.bars
    return []


def get_bars(symbol: str, timeframe: str = "1d") -> list[OHLCVBar]:
    """Sembol+TF için OHLCV barları. Veri yoksa boş liste — asla crash,
    runtime'da asla fixture."""
    tf: Timeframe = timeframe if timeframe in TIMEFRAMES else "1d"  # type: ignore[assignment]
    if is_fixture_mode():
        return fixtures.get_bars(symbol, tf)
    if tf in ("4h", "1w") and (kraken.enabled_for(symbol) or binance.enabled_for(symbol)):
        direct = _native_bars(symbol, tf)

        if direct and all(
            b.source in _SPOT_SOURCES and b.verified
            for b in direct
        ):
            bars = direct
        elif tf == "4h":
            base = get_bars(symbol, "1h")
            bars = resample.resample(base, "4h")[-_MAX_BARS["4h"]:]
        else:
            base = get_bars(symbol, "1d")
            bars = resample.resample(base, "1w")[-_MAX_BARS["1w"]:]

    elif tf == "4h":
        base = get_bars(symbol, "1h")
        bars = resample.resample(base, "4h")[-_MAX_BARS["4h"]:]

    elif tf == "1w" and symbol in coingecko.SUPPORTED:
        base = get_bars(symbol, "1d")
        bars = resample.resample(base, "1w")[-_MAX_BARS["1w"]:]

    else:
        bars = _native_bars(symbol, tf)
    # Bar arşivi (BAR_HISTORY_ENABLED, default OFF → no-op): kapanmış barları
    # kalıcı biriktirir ki karne pencereleri _MAX_BARS tavanını aşabilsin.
    # Asla raise etmez; fixture yolu yukarıda zaten ayrıldı (arşive giremez).
    history.append_new(symbol, tf, bars)
    return bars
