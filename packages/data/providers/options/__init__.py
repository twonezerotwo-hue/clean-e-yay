"""Options orchestrator — IV / skew / term structure zekâsı (v2.7 D3).

**Yalnızca kripto sembolleri** (BTCUSD/ETHUSD) için `OptionsSnapshot` üretir.
Ham options chain Deribit public API'den (veya fixture'dan); realized vol
karşılaştırması D4 realized volatility'den (1d) opsiyonel olarak beslenir —
ekstra ağ yok.

Politika ([docs/DATA_POLICY.md]):
- Runtime'da **mock yasaktır**. Live provider başarısız olursa `status=
  "DEGRADED"`/`"UNAVAILABLE"`, alanlar None döner; karar zincirine girmez,
  crash olmaz.
- Fixture verisi yalnızca test/dev path (`TEST_USE_MOCK` /
  `OPTIONS_USE_FIXTURE`) ve `verified=False` damgalı (karar zincirine GİRMEZ).

PAPER_SAFE / NO_EXECUTION — yalnızca gözlem.
"""
from __future__ import annotations

import os
import threading
from datetime import UTC, datetime

from packages.data.providers.options import deribit, engine, fixtures
from packages.data.types import OptionsSnapshot

# Options zekâsı yalnızca bu kripto sembolleri için anlamlıdır.
CRYPTO_SYMBOLS = frozenset(deribit.SUPPORTED)

_PROVIDER_NAME = "options_deribit"

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
        os.environ.get("OPTIONS_USE_FIXTURE")
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


def _snapshot_for(
    symbol: str,
    *,
    realized_vol: float | None,
    now: datetime | None = None,
) -> OptionsSnapshot:
    raw = fixtures.fetch(symbol) if is_fixture_mode() else deribit.fetch(symbol)
    if raw is None:
        _mark(ok=False, error=f"{symbol}: options unavailable")
        return OptionsSnapshot(
            symbol=symbol,
            status="DEGRADED",
            source=_PROVIDER_NAME,
            verified=False,
            error="provider unavailable",
            evidence=["options sağlayıcısı yanıt vermedi → DEGRADED (mock yok)"],
        )
    quotes = [
        engine.OptionQuote(
            expiry_ts=q.expiry_ts,
            strike=q.strike,
            option_type=q.option_type,  # type: ignore[arg-type]
            mark_iv=q.mark_iv,
            open_interest=q.open_interest,
            expiry_label=q.expiry_label,
        )
        for q in raw.quotes
    ]
    inp = engine.OptionsInput(
        symbol=symbol,
        underlying_price=raw.underlying_price,
        quotes=quotes,
        realized_vol=realized_vol,
        source=_PROVIDER_NAME,
        # Runtime live veri verified; fixture (test/dev) verified=False.
        verified=not is_fixture_mode(),
        ts=now or datetime.now(UTC),
    )
    snap = engine.compute(inp, now=now)
    _mark(ok=snap.status == "OK", error=snap.error)
    return snap


def get_options(
    symbols: list[str] | None = None,
    *,
    realized_vol_by_symbol: dict[str, float | None] | None = None,
    now: datetime | None = None,
) -> dict[str, OptionsSnapshot]:
    """Kripto sembolleri için options snapshot'ları (symbol → OptionsSnapshot).

    Sadece desteklenen kripto sembolleri işlenir; diğerleri atlanır. Veri
    yoksa ilgili sembol DEGRADED/UNAVAILABLE döner (asla mock, asla crash).
    `realized_vol_by_symbol` D4 realized vol'den (1d) IV-RV spread için
    opsiyonel beslenir."""
    rv = realized_vol_by_symbol or {}
    syms = [s for s in (symbols or CRYPTO_SYMBOLS) if s in CRYPTO_SYMBOLS]
    return {
        s: _snapshot_for(s, realized_vol=rv.get(s), now=now) for s in sorted(syms)
    }
