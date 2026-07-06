"""Sermaye rotasyonu sağlayıcısı — gerçek OHLCV momentum/oran motoru (P0 parity).

Eski Codex `capital_rotation_provider.py` hash-mock'u kaldırıldı. Skor artık
Clean OHLCV cache'inin 1d barlarından, `engine.compute()` ile gerçek 30g
momentum + çapraz oran analizinden gelir.

Politika ([docs/DATA_POLICY.md]):
- Runtime'da **mock skor yasaktır**. Veri yetersizse `RotationView.status=
  "UNAVAILABLE"`, nötr 50 skor + DEGRADED provider status döner; consensus
  quantum modülü düşer ve ağırlığı redistribute edilir (mock skor karar
  zincirine girmez).
- Fixture barlar yalnızca test/dev path (`TEST_USE_MOCK=true`) üstünden
  ohlcv sağlayıcısından gelir ve `verified=False` damgalıdır.

PAPER_SAFE / NO_EXECUTION — yalnızca gözlem.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime

from packages.data.providers import ohlcv as ohlcv_provider
from packages.data.providers.rotation import engine
from packages.data.types import RotationView

_SOURCE = "ohlcv_1d_rotation"

_LOCK = threading.Lock()
_STATUS: dict[str, dict] = {
    "rotation": {
        "status": "unknown",
        "last_success_at": None,
        "last_error": None,
        "calls": 0,
        "fallbacks": 0,
    }
}


def _mark(*, ok: bool, error: str | None = None) -> None:
    with _LOCK:
        st = _STATUS["rotation"]
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


def _load_closes() -> dict[str, list[float]]:
    """Rotasyon anahtarı → 1d kapanış serisi. Veri yoksa anahtar atlanır
    (asla mock, asla crash)."""
    closes: dict[str, list[float]] = {}
    for key, symbol in engine.ROTATION_SYMBOLS.items():
        bars = ohlcv_provider.get_bars(symbol, "1d")
        if bars:
            closes[key] = [b.close for b in bars]
    return closes


def get_rotation() -> RotationView:
    """Gerçek 1d OHLCV momentum/oran analizinden rotasyon görünümü.

    Veri yetersizse `status="UNAVAILABLE"`, nötr 50 skor — mock üretilmez.
    """
    result = engine.compute(_load_closes())
    if not result.available:
        _mark(ok=False, error=result.error or "rotation unavailable")
        return RotationView(
            score=50.0,
            direction="neutral",
            evidence=[],
            status="UNAVAILABLE",
            source=_SOURCE,
            verified=False,
            error=result.error,
        )
    _mark(ok=True)
    return RotationView(
        score=result.score,
        direction=result.direction,  # type: ignore[arg-type]
        evidence=result.evidence,
        status="OK",
        source=_SOURCE,
        verified=True,
        per_symbol=result.per_symbol,
    )
