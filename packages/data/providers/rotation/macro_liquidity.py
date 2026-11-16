"""Bar arşivinden makro likidite okuması — fundamental v4 ve rejim Likidite TEK giriş.

DXY ve US10Y tarihle eşlenir; son ortak gün `MAX_AGE_DAYS`ten eskiyse skor
üretilmez (STALE). Böylece donmuş bir seri güncel seriyle sessizce birleşemez.
Arşiv yok/kısa → UNAVAILABLE (çağıran kendi yedeğine düşer). Salt-okur, asla
raise etmez. PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

# Takvim günü: hafta sonu + uzun tatil (4 gün) + bir gün gecikme sığar.
MAX_AGE_DAYS = 5

OK = "OK"
STALE = "STALE"
UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class LiquidityReading:
    status: str
    score: float | None = None
    as_of: date | None = None


# Dosya imzası + gün değişmedikçe tick içi hücreler tek hesabı paylaşır.
_MEMO: dict = {"key": None, "val": None}


def _compute(dxy_bars: list, us10y_bars: list, today: date) -> LiquidityReading:
    from packages.data.providers.rotation import flow

    dxy, us10y, as_of = flow.align_closes_by_date(dxy_bars, us10y_bars)
    if as_of is None:
        return LiquidityReading(UNAVAILABLE)
    if (today - as_of).days > MAX_AGE_DAYS:
        return LiquidityReading(STALE, as_of=as_of)
    score = flow.liquidity_momentum_score(dxy, us10y)
    return LiquidityReading(OK if score is not None else UNAVAILABLE, score, as_of)


def read(today: date | None = None) -> LiquidityReading:
    """Güncel okuma. `today` yalnız ölçüm/test için verilir."""
    try:
        from packages.data.providers.ohlcv import history

        def _sig(sym: str):
            try:
                st = history._path(sym, "1d").stat()
                return (st.st_size, int(st.st_mtime))
            except OSError:
                return None

        day = today or datetime.now(UTC).date()
        key = (history.enabled(), _sig("DXY"), _sig("US10Y"), day)
        if _MEMO["key"] == key:
            return _MEMO["val"]
        val = _compute(history.load("DXY", "1d"), history.load("US10Y", "1d"), day)
        _MEMO["key"], _MEMO["val"] = key, val
        return val
    except (OSError, ValueError, TypeError, AttributeError):
        return LiquidityReading(UNAVAILABLE)


__all__ = ["MAX_AGE_DAYS", "OK", "STALE", "UNAVAILABLE", "LiquidityReading", "read"]
