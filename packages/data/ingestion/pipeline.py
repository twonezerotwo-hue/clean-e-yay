"""Tek giriş noktası: piyasa görüntüsünü tek atışta üretir.

API ve worker'lar bunu çağırır. Her zaman bir `MarketSnapshot` döner;
hata durumunda DQS düşer ama exception kaçırılmaz.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from packages.data.providers import calendar as cal_provider
from packages.data.providers import news as news_provider
from packages.data.providers import ohlcv as ohlcv_provider
from packages.data.providers import price as price_provider
from packages.data.providers import rotation as rot_provider
from packages.data.providers import technical as tech_provider
from packages.data.quality.dqs import QualityReport
from packages.data.quality.dqs import compute as compute_dqs
from packages.data.types import (
    TIMEFRAMES,
    Catalyst,
    NewsHeadline,
    PriceQuote,
    RotationView,
    TechnicalSnapshot,
)

DEFAULT_SYMBOLS = ["BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD", "DXY", "US10Y", "VIX"]

# T1 — multi-TF technicals yalnızca ana 4 sembol için üretilir (payload ve
# rate-limit dengesi); kalan semboller legacy 1d teknik alır.
MULTI_TF_SYMBOLS = frozenset(DEFAULT_SYMBOLS[:4])


@dataclass
class MarketSnapshot:
    snapshot_id: str
    generated_at: datetime
    prices: list[PriceQuote]
    technicals: dict[str, TechnicalSnapshot]
    headlines: list[NewsHeadline]
    catalysts: list[Catalyst]
    rotation: RotationView
    quality: QualityReport
    warnings: list[str] = field(default_factory=list)
    provider_status: dict[str, dict] = field(default_factory=dict)
    # T0 contract seed — T1'de OHLCV bazlı multi-TF technicals doldurur.
    # None → yalnızca legacy `technicals` (1d) mevcut. Anahtar: symbol → tf.
    technicals_by_tf: dict[str, dict[str, TechnicalSnapshot]] | None = None


def _make_id(now: datetime) -> str:
    return "snap::" + hashlib.sha1(now.isoformat().encode()).hexdigest()[:12]


def build_snapshot(symbols: list[str] | None = None) -> MarketSnapshot:
    syms = symbols or DEFAULT_SYMBOLS
    now = datetime.now(UTC)
    prices = price_provider.get_quotes(syms)
    # T1 — gerçek OHLCV'den multi-TF technicals; legacy `technicals` 1d'den
    # beslenmeye devam eder (geriye uyum).
    tf_syms = [s for s in syms if s in MULTI_TF_SYMBOLS]
    technicals_by_tf = {
        s: {tf: tech_provider.get_snapshot(s, tf) for tf in TIMEFRAMES}
        for s in tf_syms
    }
    technicals = {
        s: (
            technicals_by_tf[s]["1d"]
            if s in technicals_by_tf
            else tech_provider.get_snapshot(s, "1d")
        )
        for s in syms
    }
    headlines = news_provider.list_headlines(14)
    catalysts = cal_provider.list_catalysts(8)
    rotation = rot_provider.get_rotation()
    quality = compute_dqs(prices, syms)
    warnings = list(quality.notes)
    degraded_tfs = [
        f"{s}:{tf}"
        for s, by_tf in technicals_by_tf.items()
        for tf in TIMEFRAMES
        if by_tf[tf].status == "DEGRADED"
    ]
    if degraded_tfs:
        warnings.append("technicals DEGRADED: " + ", ".join(degraded_tfs))
    provider_status = {
        **price_provider.get_provider_status(),
        **ohlcv_provider.get_provider_status(),
    }
    if price_provider.is_runtime_mock_explicit():
        warnings.insert(0, "PRICE_USE_MOCK=true — TEST/MOCK MODE")
    return MarketSnapshot(
        snapshot_id=_make_id(now),
        generated_at=now,
        prices=prices,
        technicals=technicals,
        headlines=headlines,
        catalysts=catalysts,
        rotation=rotation,
        quality=quality,
        warnings=warnings,
        provider_status=provider_status,
        technicals_by_tf=technicals_by_tf or None,
    )


# Basit zaman cache — aynı saniye içinde yeniden hesaplamadan kaçınmak için
_CACHE: dict[str, tuple[float, MarketSnapshot]] = {}
_TTL_SEC = 30.0


def get_cached_snapshot(symbols: list[str] | None = None) -> MarketSnapshot:
    key = "|".join(symbols or DEFAULT_SYMBOLS)
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and (now - cached[0]) < _TTL_SEC:
        return cached[1]
    snap = build_snapshot(symbols)
    _CACHE[key] = (now, snap)
    return snap
