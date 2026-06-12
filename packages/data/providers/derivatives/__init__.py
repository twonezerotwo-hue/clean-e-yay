"""Türev (derivatives) orchestrator — funding/OI/squeeze proxy (v2.7 D2).

**Yalnızca kripto sembolleri** (BTCUSD/ETHUSD) için `DerivativesSnapshot`
üretir. Ham funding + OI Binance public futures'tan; kısa vadeli momentum +
volatilite mevcut OHLCV cache'inden (1h barlar) türetilir — ekstra ağ yok.

Politika ([docs/DATA_POLICY.md]):
- Runtime'da **mock yasaktır**. Live provider başarısız olursa `status=
  "DEGRADED"`, alanlar None döner; karar zincirine girmez, crash olmaz.
- Fixture verisi yalnızca test/dev path (`TEST_USE_MOCK` /
  `DERIVATIVES_USE_FIXTURE`) ve `verified=False` damgalı.

PAPER_SAFE / NO_EXECUTION — yalnızca gözlem.
"""
from __future__ import annotations

import os
import threading
from datetime import UTC, datetime

from packages.data.providers import ohlcv as ohlcv_provider
from packages.data.providers.derivatives import binance, engine, fixtures
from packages.data.types import DerivativesSnapshot

# Türev zekâsı yalnızca bu kripto sembolleri için anlamlıdır.
CRYPTO_SYMBOLS = frozenset(binance.SUPPORTED)

_PROVIDER_NAME = "derivatives_binance"

_LOCK = threading.Lock()
_STATUS: dict[str, dict] = {
    _PROVIDER_NAME: {
        "status": "unknown",
        "last_success_at": None,
        "last_error": None,
        "calls": 0,
        "fallbacks": 0,
    }
}


def _truthy(v: str | None) -> bool:
    return (v or "").lower() == "true"


def is_fixture_mode() -> bool:
    """Test/dev fixture path açık mı? Runtime'da false kalmalıdır."""
    return _truthy(os.environ.get("TEST_USE_MOCK")) or _truthy(
        os.environ.get("DERIVATIVES_USE_FIXTURE")
    )


def _mark(*, ok: bool, error: str | None = None) -> None:
    with _LOCK:
        st = _STATUS[_PROVIDER_NAME]
        st["calls"] += 1
        if ok:
            st["status"] = "ok"
            st["last_success_at"] = datetime.now(UTC).isoformat()
            st["last_error"] = None
        else:
            st["status"] = "degraded"
            if error:
                st["last_error"] = error


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


def _momentum_and_vol(symbol: str) -> tuple[float | None, float | None]:
    """1h OHLCV cache'inden kısa vadeli momentum + volatilite (ekstra ağ yok).

    momentum = son ~6 saatlik % değişim; volatilite = son ~14 barın ortalama
    (high-low)/close oranı. Yetersiz bar → None (squeeze proxy o bileşeni atlar).
    """
    bars = ohlcv_provider.get_bars(symbol, "1h")
    if not bars or len(bars) < 7:
        return None, None
    closes = [b.close for b in bars]
    look = closes[-7]
    momentum = (closes[-1] - look) / look if look else None
    window = bars[-14:]
    ranges = [(b.high - b.low) / b.close for b in window if b.close]
    vol = sum(ranges) / len(ranges) if ranges else None
    return momentum, vol


def _snapshot_for(symbol: str, *, now: datetime | None = None) -> DerivativesSnapshot:
    raw = fixtures.fetch(symbol) if is_fixture_mode() else binance.fetch(symbol)
    if raw is None:
        _mark(ok=False, error=f"{symbol}: derivatives unavailable")
        return DerivativesSnapshot(
            symbol=symbol,
            status="DEGRADED",
            source=_PROVIDER_NAME,
            verified=False,
            error="provider unavailable",
            evidence=["türev sağlayıcısı yanıt vermedi → DEGRADED (mock yok)"],
        )
    momentum, vol = _momentum_and_vol(symbol)
    inp = engine.DerivInput(
        symbol=symbol,
        funding_rate=raw.funding_rate,
        open_interest_usd=raw.open_interest_usd,
        oi_change_pct=raw.oi_change_pct,
        price_momentum_pct=momentum,
        volatility_pct=vol,
        source=_PROVIDER_NAME,
        # Runtime live veri verified; fixture (test/dev) verified=False.
        verified=not is_fixture_mode(),
        ts=now or datetime.now(UTC),
    )
    snap = engine.compute(inp, now=now)
    _mark(ok=snap.status == "OK", error=snap.error)
    return snap


def get_derivatives(
    symbols: list[str] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, DerivativesSnapshot]:
    """Kripto sembolleri için türev snapshot'ları (symbol → DerivativesSnapshot).

    Sadece desteklenen kripto sembolleri işlenir; diğerleri atlanır. Veri
    yoksa ilgili sembol DEGRADED döner (asla mock, asla crash)."""
    syms = [s for s in (symbols or CRYPTO_SYMBOLS) if s in CRYPTO_SYMBOLS]
    return {s: _snapshot_for(s, now=now) for s in sorted(syms)}
