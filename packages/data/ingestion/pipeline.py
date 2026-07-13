"""Tek giriş noktası: piyasa görüntüsünü tek atışta üretir.

API ve worker'lar bunu çağırır. Her zaman bir `MarketSnapshot` döner;
hata durumunda DQS düşer ama exception kaçırılmaz.
"""
from __future__ import annotations

import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime

from packages.data.providers import calendar as cal_provider
from packages.data.providers import derivatives as deriv_provider
from packages.data.providers import news as news_provider
from packages.data.providers import ohlcv as ohlcv_provider
from packages.data.providers import options as options_provider
from packages.data.providers import price as price_provider
from packages.data.providers import rotation as rot_provider
from packages.data.providers import technical as tech_provider
from packages.data.providers import volatility as vol_provider
from packages.data.providers.news import catalyst as catalyst_engine
from packages.data.quality.dqs import QualityReport
from packages.data.quality.dqs import compute as compute_dqs
from packages.data.quality.dqs import extended_metrics as dqs_extended_metrics
from packages.data.registry import assets as _asset_registry
from packages.data.types import (
    TIMEFRAMES,
    Catalyst,
    CatalystImpact,
    DerivativesSnapshot,
    NewsHeadline,
    OptionsSnapshot,
    PriceQuote,
    RotationView,
    TechnicalSnapshot,
    VolatilitySnapshot,
)

# Snapshot evreni + işlem evreni TEK KAYNAKTAN: config/assets.yaml.
# Asset ekle/çıkar → tüm pipeline otomatik okur (eski hardcode liste kaldırıldı).
# snapshot_symbols() = trade + macro rolleri; trade_symbols() = işlem evreni.
DEFAULT_SYMBOLS = _asset_registry.snapshot_symbols()

# T1 — multi-TF technicals yalnızca işlem evreni (trade) sembolleri için üretilir
# (payload ve rate-limit dengesi); kalan semboller legacy 1d teknik alır.
MULTI_TF_SYMBOLS = frozenset(_asset_registry.trade_symbols())


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
    # v2.7 D2 — kripto türev zekâsı (funding/OI/squeeze proxy). Anahtar: symbol.
    # Yalnızca kripto sembolleri; karar zincirinde yalnızca kısıtlayıcı.
    derivatives: dict[str, DerivativesSnapshot] = field(default_factory=dict)
    # v2.7 D4 — realized volatility / rejim zekâsı. Anahtar: symbol → timeframe.
    # Karar zincirinde yalnızca kısıtlayıcı (asla size artırmaz).
    volatility: dict[str, dict[str, VolatilitySnapshot]] = field(default_factory=dict)
    # v2.7 D3 — options IV / skew / term structure zekâsı (yalnızca BTC/ETH).
    # Karar zincirinde yalnızca kısıtlayıcı (verified + status OK); asla size
    # artırmaz. Anahtar: symbol → OptionsSnapshot.
    options: dict[str, OptionsSnapshot] = field(default_factory=dict)
    # v2.7 D5 — haber → catalyst half-life zekâsı (deterministik, LLM yok).
    # Karar zincirinde yalnızca kısıtlayıcı (verified + yarı-ömrü dolmamış).
    catalyst_impacts: list[CatalystImpact] = field(default_factory=list)


def _make_id(now: datetime) -> str:
    return "snap::" + hashlib.sha1(now.isoformat().encode()).hexdigest()[:12]


# M2 — rejim sınıflandırıcısının makro girdileri (packages/regime/classifier.py
# katman girdileriyle hizalı). Fiyatı gelmeyenler snapshot warning'i üretir.
_REGIME_MACRO_SYMBOLS = ("CPI", "DXY", "US02Y", "US10Y", "VIX")


def _regime_macro_missing(prices: list[PriceQuote]) -> list[str]:
    """Fiyatı olmayan rejim-makro sembolleri (sıralı, deterministik)."""
    return sorted(
        q.symbol for q in prices if q.symbol in _REGIME_MACRO_SYMBOLS and q.price is None
    )


def build_snapshot(symbols: list[str] | None = None) -> MarketSnapshot:
    # Taze okunur (modül-seviyesi DEFAULT_SYMBOLS/MULTI_TF_SYMBOLS DEĞİL) —
    # kullanıcı runtime'da custom trade asset eklerse bir sonraki snapshot'ta
    # otomatik dahil olur (process restart gerekmez).
    syms = symbols or _asset_registry.snapshot_symbols()
    now = datetime.now(UTC)
    multi_tf_syms = frozenset(_asset_registry.trade_symbols())
    tf_syms = [s for s in syms if s in multi_tf_syms]

    # Bağımsız ağ çağrılarını PARALEL çalıştır — seri toplam (~40s, provider'lar
    # yavaşken) yerine en yavaş çağrı kadar (~max). Her provider kendi HTTP
    # timeout'unu (4-8s) zaten uygular; havuz yalnızca eşzamanlılık ekler.
    with ThreadPoolExecutor(max_workers=5) as _ex:
        _f_prices = _ex.submit(price_provider.get_quotes, syms)
        _f_news = _ex.submit(news_provider.list_headlines, 14)
        _f_cal = _ex.submit(cal_provider.list_catalysts, 8)
        _f_rot = _ex.submit(rot_provider.get_rotation)
        _f_deriv = _ex.submit(
            deriv_provider.get_derivatives,
            [s for s in syms if s in deriv_provider.CRYPTO_SYMBOLS],
        )
        prices = _f_prices.result()
        headlines = _f_news.result()
        catalysts = _f_cal.result()
        rotation = _f_rot.result()
        derivatives = _f_deriv.result()

    # T1 — gerçek OHLCV'den multi-TF technicals (disk cache — hızlı, seri).
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
    # Bağımlı adımlar: catalyst_impacts←headlines, options←volatility (aşağıda).
    # v2.7 D5 — başlıkları deterministik catalyst etkilerine çevir (network yok).
    catalyst_impacts = catalyst_engine.build_impacts(headlines, now=now)
    # v2.7 D4 — realized volatility / rejim (OHLCV cache'inden, ekstra ağ yok).
    volatility = vol_provider.get_volatility(tf_syms, list(TIMEFRAMES))
    # v2.7 D3 — options IV / skew / term structure (yalnızca BTC/ETH). IV-RV
    # spread için D4 realized vol (1d) beslenir; ekstra ağ sadece Deribit chain.
    opt_syms = [s for s in syms if s in options_provider.CRYPTO_SYMBOLS]
    realized_1d = {
        s: (volatility.get(s, {}).get("1d").realized_vol if volatility.get(s, {}).get("1d") else None)
        for s in opt_syms
    }
    options = options_provider.get_options(
        opt_syms, realized_vol_by_symbol=realized_1d, now=now
    )
    quality = compute_dqs(prices, syms)
    # 2026-07-13 — DQS genişletme (GÖZLEM-YALNIZ: score/status'a girmez; DQS'in
    # fiyat-dışı kör noktası her snapshot'ta görünür olsun).
    quality.extended = dqs_extended_metrics(
        technicals_by_tf=technicals_by_tf, headlines=headlines,
        rotation=rotation, now=now,
    )
    warnings = list(quality.notes)
    warnings.append(
        "dqs_extended:" + ":".join(
            f"{k}={'na' if v is None else v}" for k, v in sorted(quality.extended.items())
        )
    )
    degraded_tfs = [
        f"{s}:{tf}"
        for s, by_tf in technicals_by_tf.items()
        for tf in TIMEFRAMES
        if by_tf[tf].status == "DEGRADED"
    ]
    if degraded_tfs:
        # Piyasası kapalı sembolleri ayır: bunlar veri hatası değil (hafta sonu/
        # tatil → taze bar yok). 'DEGRADED' yerine 'piyasa kapalı' etiketlenir.
        closed_syms: set[str] = set()
        try:
            from packages import market_sessions

            for s in {d.split(":")[0] for d in degraded_tfs}:
                ctx = market_sessions.asset_context(s, now)
                if ctx.relevant_markets and not ctx.any_relevant_market_open:
                    closed_syms.add(s)
        except Exception:
            closed_syms = set()
        real_degraded = [d for d in degraded_tfs if d.split(":")[0] not in closed_syms]
        if real_degraded:
            warnings.append("technicals DEGRADED: " + ", ".join(real_degraded))
        if closed_syms:
            warnings.append("piyasa kapalı (market closed): " + ", ".join(sorted(closed_syms)))
    # DATA_POLICY: veri yoksa mock üretilmez — açık warning + DEGRADED status.
    if not headlines:
        warnings.append("news_unavailable")
    if not catalysts:
        warnings.append("calendar_unavailable")
    if rotation.status == "UNAVAILABLE":
        warnings.append("rotation_unavailable: " + (rotation.error or "data insufficient"))
    # M2 — rejim sınıflandırıcısının makro girdileri (FRED/endeks) düşünce açık
    # uyarı: eksik veri sessiz kalmasın (F2-3 flag'i kapalıyken default'la
    # hesaplanır — owner bu uyarıdan fark eder; açıkken katman düşer).
    missing_macro = _regime_macro_missing(prices)
    if missing_macro:
        warnings.append("macro_data_missing: " + ", ".join(missing_macro))
    degraded_deriv = [s for s, d in derivatives.items() if d.status == "DEGRADED"]
    if degraded_deriv:
        warnings.append("derivatives_degraded: " + ", ".join(sorted(degraded_deriv)))
    degraded_vol = [
        f"{s}:{tf}"
        for s, by_tf in volatility.items()
        for tf, v in by_tf.items()
        if v.status == "DEGRADED"
    ]
    if degraded_vol:
        warnings.append("volatility_degraded: " + ", ".join(sorted(degraded_vol)))
    degraded_opt = [s for s, o in options.items() if o.status != "OK"]
    if degraded_opt:
        warnings.append("options_degraded: " + ", ".join(sorted(degraded_opt)))
    provider_status = {
        **price_provider.get_provider_status(),
        **ohlcv_provider.get_provider_status(),
        **news_provider.get_provider_status(),
        **cal_provider.get_provider_status(),
        **rot_provider.get_provider_status(),
        **deriv_provider.get_provider_status(),
        **vol_provider.get_provider_status(),
        **options_provider.get_provider_status(),
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
        derivatives=derivatives,
        volatility=volatility,
        options=options,
        catalyst_impacts=catalyst_impacts,
    )


# Basit zaman cache — aynı saniye içinde yeniden hesaplamadan kaçınmak için
_CACHE: dict[str, tuple[float, MarketSnapshot]] = {}
_TTL_SEC = 30.0
_REFRESHING: set[str] = set()
_REFRESH_LOCK = threading.Lock()


def _refresh_async(key: str, symbols: list[str] | None) -> None:
    """Arka planda yeniden derle; başarısızsa eski cache korunur (mock yok)."""
    try:
        snap = build_snapshot(symbols)
        _CACHE[key] = (time.monotonic(), snap)
    except Exception:
        pass
    finally:
        with _REFRESH_LOCK:
            _REFRESHING.discard(key)


def get_cached_snapshot(symbols: list[str] | None = None) -> MarketSnapshot:
    """Stale-while-revalidate: taze cache anında döner; bayatsa ESKİ kopya yine
    anında döner ve yenileme ARKA PLANDA yapılır — istek hiçbir zaman
    build_snapshot'ı beklemez. Yalnızca cache hiç yoksa (ilk çağrı) senkron derler.
    Bu, canlı provider yavaşladığında cockpit/brief'in donmasını engeller."""
    key = "|".join(symbols or DEFAULT_SYMBOLS)
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached is not None:
        if (now - cached[0]) >= _TTL_SEC:
            with _REFRESH_LOCK:
                if key not in _REFRESHING:
                    _REFRESHING.add(key)
                    threading.Thread(
                        target=_refresh_async, args=(key, symbols), daemon=True
                    ).start()
        return cached[1]
    snap = build_snapshot(symbols)
    _CACHE[key] = (now, snap)
    return snap
