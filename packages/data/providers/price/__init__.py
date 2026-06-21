"""Fiyat orchestrator.

Politika ([docs/DATA_POLICY.md]):
- Runtime'da **mock fallback yasaktır**.
- Live provider başarısız olursa quote `price=None`, `status="DATA_UNAVAILABLE"`,
  `verified=False`, `error=<sebep>` ile döner. Mock'a düşülmez.
- Mock yalnızca test/dev path için: `TEST_USE_MOCK=true` (conftest tarafından
  set edilir) veya açık `PRICE_USE_MOCK=true` runtime opt-in (dashboard'da
  kırmızı banner görünür).

Env değişkenleri her çağrıda okunur (modül-seviyesi cache yok), böylece
test monkeypatch ve runtime override doğru çalışır.
"""
from __future__ import annotations

import os
import threading
from datetime import UTC, datetime

from packages.data.providers.price import coingecko, fred, mock, yfinance
from packages.data.types import PriceQuote

# Sembol → birincil sağlayıcı modülü.
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


# ---------- Env / mod sorgusu ----------

def _truthy(v: str | None) -> bool:
    return (v or "").lower() == "true"


def is_test_mock_allowed() -> bool:
    """Test fixture açık mı? conftest TEST_USE_MOCK=true ile gelir."""
    return _truthy(os.environ.get("TEST_USE_MOCK"))


def is_runtime_mock_explicit() -> bool:
    """Runtime opt-in: PRICE_USE_MOCK=true → dashboard kırmızı banner."""
    return _truthy(os.environ.get("PRICE_USE_MOCK"))


def is_mock_mode() -> bool:
    """Herhangi bir nedenle mock kullanılıyor mu?"""
    return is_test_mock_allowed() or is_runtime_mock_explicit()


# ---------- Provider status ----------

def _mark(
    name: str,
    *,
    ok: bool,
    error: str | None = None,
    fallback: bool = False,
) -> None:
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


def _mark_disabled(name: str, *, error: str) -> None:
    """Provider config eksik (örn. API key yok) → 'disabled' = beklenen durum.

    'degraded' DEĞİL — kullanıcının opsiyonel bir entegrasyonu açmama
    tercihi runtime hatası gibi sayılmamalı.
    """
    with _LOCK:
        st = _STATUS[name]
        st["calls"] += 1
        st["status"] = "disabled"
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


# ---------- Quote akışı ----------

def _provider_name(mod) -> str:
    return mod.__name__.rsplit(".", 1)[-1]


def _data_unavailable(symbol: str, *, source: str, error: str) -> PriceQuote:
    return PriceQuote(
        symbol=symbol,
        price=None,
        source=source,
        verified=False,
        status="DATA_UNAVAILABLE",
        error=error,
    )


def _try_live(symbol: str) -> PriceQuote:
    """Birincil live provider'ı dener. Başarısızsa DATA_UNAVAILABLE döner.

    Asla mock'a düşmez.
    """
    primary = _PRIMARY.get(symbol)
    if primary is None:
        _mark("mock", ok=False, error="no_live_provider_mapped")
        return _data_unavailable(
            symbol,
            source="none",
            error="no live provider configured for symbol",
        )
    name = _provider_name(primary)
    try:
        q = primary.get_quote(symbol)
    except Exception as exc:
        msg = str(exc)[:200] or "provider raised"
        _mark(name, ok=False, error=msg)
        return _data_unavailable(symbol, source=name, error=msg)
    if q is None:
        # Provider veri getiremedi. Sebep CONFIG eksikliği mi (örn. API key
        # yok → 'disabled', beklenen durum, degraded sayılmaz) yoksa gerçek
        # bir hata mı ('degraded')? Provider'ı önce çağırıyoruz ki patch'li/
        # test provider'ı kısa devre olmasın — config kontrolü yalnızca None
        # döndüğünde ayrıştırma için.
        cfg_err = _config_missing(name)
        if cfg_err:
            _mark_disabled(name, error=cfg_err)
            return _data_unavailable(symbol, source=name, error=cfg_err)
        reason = _explain_none(name)
        _mark(name, ok=False, error=reason)
        return _data_unavailable(symbol, source=name, error=reason)
    _mark(name, ok=True)
    return q


def _config_missing(provider_name: str) -> str | None:
    """Provider'ı çağırmadan önce config eksikliğini tespit et.

    None döner → provider çağrılabilir; str döner → disabled olarak işaretle.
    """
    if provider_name == "fred" and not os.environ.get("FRED_API_KEY"):
        return "FRED_API_KEY missing (set to enable Fed/macro series)"
    return None


def _explain_none(provider_name: str) -> str:
    return "provider returned no data"


def _mock_quote(symbol: str) -> PriceQuote:
    q = mock.get_quote(symbol)
    _mark("mock", ok=True)
    return q


def get_quote(symbol: str) -> PriceQuote:
    if is_mock_mode():
        return _mock_quote(symbol)
    return _try_live(symbol)


def get_quotes(symbols: list[str]) -> list[PriceQuote]:
    return [get_quote(s) for s in symbols]
