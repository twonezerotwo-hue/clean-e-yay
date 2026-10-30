"""Açıklama sonrası çapraz teyit: dolar ve varlığın kendi fiyatı sürprizin yönünde mi?

Owner kuralı: verinin beklentiden yüksek/düşük gelmesi tek başına yetmez; dolar
endeksi, getiriler ve varlığın fiyatı yönü doğrulamalı, ilk tepki hızla dönebilir.
Açıklama anındaki fiyat (snapshot deposu) ile şimdiki fiyat karşılaştırılır:

  PENDING       açıklamadan bu yana 15 dk dolmadı        → katkı 0
  CONFIRMED     dolar ve varlık tablodaki yönde          → katkı 1
  WEAK          hareket eşiğin altında                    → katkı 0,5
  CONTRADICTED  dolar ya da varlık ters yönde (dönüş dahil) → katkı 0
  UNAVAILABLE   açıklama anı ya da fiyat yok               → katkı 0

Her turda yeniden bakılır; ilk tepki dönerse teyit kendiliğinden düşer. US10Y
FRED'den günlük geldiği için gün içi teyitte kullanılmaz. Karar vermez; yalnız
nedensellik katmanındaki sürpriz katkısını ölçekler (bayrakla).
"""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta

from packages.macro import matrix

WAIT = timedelta(minutes=15)
_DEADBAND = {"DXY": 0.0005}
_DEFAULT_DEADBAND = 0.001
_BASELINE_GAP_S = 900
_BASELINES: OrderedDict[str, dict[str, float]] = OrderedDict()


def _price_map(prices: Mapping[str, object] | Iterable[object] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(prices, Mapping):
        items: Iterable[tuple[object, object]] = prices.items()
    else:  # snapshot deposundaki satırlar sözlük, canlı fiyatlar PriceQuote
        items = ((q.get("symbol") if isinstance(q, Mapping) else getattr(q, "symbol", None), q) for q in (prices or ()))
    for symbol, quote in items:
        raw = quote.get("price") if isinstance(quote, Mapping) else getattr(quote, "price", quote)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if symbol and value > 0:
            out[str(symbol)] = value
    return out


def _baseline(event_id: str, released_at: datetime) -> dict[str, float]:
    if event_id in _BASELINES:
        return _BASELINES[event_id]
    from packages.data import snapshot_store

    doc = snapshot_store.nearest(released_at, side="before", max_gap_seconds=_BASELINE_GAP_S)
    prices = _price_map((doc or {}).get("data_snapshot", {}).get("prices") or [])
    # Bulunamayan taban da saklanır: depo her turda yeniden taranmaz.
    _BASELINES[event_id] = prices
    while len(_BASELINES) > 64:
        _BASELINES.popitem(last=False)
    return prices


def assess(
    *,
    event_id: str,
    topic: str | None,
    normalized: float | None,
    released_at: datetime | None,
    symbol: str,
    asset_class: str | None,
    prices_now: Mapping[str, object] | Iterable[object] | None,
    now: datetime,
) -> tuple[float, str]:
    """Sürpriz katkısı için ölçek (0, 0,5, 1) ve teyit durumu."""
    if released_at is None or not normalized:
        return 0.0, "UNAVAILABLE"
    if now - released_at < WAIT:
        return 0.0, "PENDING"
    base, current = _baseline(event_id, released_at), _price_map(prices_now)
    sign = 1 if normalized > 0 else -1
    checks: list[int | None] = []
    for sym in dict.fromkeys(("DXY", symbol)):
        weight = matrix.weight(topic, sym, asset_class if sym == symbol else None)
        if weight == 0:
            if sym == symbol:
                return 0.0, "NO_DIRECTION"
            continue  # bu konuda doların beklenen yönü yok
        if sym not in base or sym not in current:
            checks.append(None)
            continue
        move = current[sym] / base[sym] - 1.0
        if abs(move) < _DEADBAND.get(sym, _DEFAULT_DEADBAND):
            checks.append(0)
        else:
            checks.append(1 if move * sign * (1 if weight > 0 else -1) > 0 else -1)
    if -1 in checks:
        return 0.0, "CONTRADICTED"
    if not checks or None in checks:
        return 0.0, "UNAVAILABLE"
    if all(c == 1 for c in checks):
        return 1.0, "CONFIRMED"
    return 0.5, "WEAK"


def reset_cache() -> None:
    _BASELINES.clear()
