"""Volatility orchestrator — realized vol / rejim zekâsı (v2.7 D4).

Her (symbol, timeframe) için `VolatilitySnapshot` üretir. Barlar **mevcut OHLCV
cache'inden** okunur (T1 provider) — ekstra ağ yoktur. Saf hesap `engine.py`'de.

Politika ([docs/DATA_POLICY.md]):
- Runtime'da **mock yasaktır**. Bar yoksa/yetersizse `status="DEGRADED"`,
  alanlar None döner; karar zincirine girmez, crash olmaz.
- Fixture barlar (OHLCV fixture path) `verified=False` damgalıdır ve karar
  zincirine GİRMEZ (yalnızca dashboard bağlamı).

PAPER_SAFE / NO_EXECUTION — yalnızca gözlem.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime

from packages.data.providers import ohlcv as ohlcv_provider
from packages.data.providers.volatility import engine
from packages.data.types import TIMEFRAMES, VolatilitySnapshot

_PROVIDER_NAME = "volatility"

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


def _snapshot_for(
    symbol: str, timeframe: str, *, now: datetime | None = None
) -> VolatilitySnapshot:
    bars = ohlcv_provider.get_bars(symbol, timeframe)
    inp = engine.VolInput(
        symbol=symbol,
        timeframe=timeframe,
        bars=bars,
        source="volatility_ohlcv",
        # Runtime live bar verified; fixture (test/dev) verified=False.
        verified=not ohlcv_provider.is_fixture_mode(),
    )
    snap = engine.compute(inp, now=now)
    _mark(ok=snap.status == "OK", error=snap.error)
    return snap


def get_volatility(
    symbols: list[str],
    timeframes: list[str] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, dict[str, VolatilitySnapshot]]:
    """symbol → timeframe → VolatilitySnapshot.

    Bar yoksa ilgili hücre DEGRADED döner (asla mock, asla crash)."""
    tfs = [tf for tf in (timeframes or list(TIMEFRAMES)) if tf in TIMEFRAMES]
    return {
        s: {tf: _snapshot_for(s, tf, now=now) for tf in tfs}
        for s in symbols
    }
