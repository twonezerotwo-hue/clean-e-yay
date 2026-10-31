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
from packages.data.providers import macro as macro_provider
from packages.data.providers import news as news_provider
from packages.data.providers import ohlcv as ohlcv_provider
from packages.data.providers import options as options_provider
from packages.data.providers import price as price_provider
from packages.data.providers import rotation as rot_provider
from packages.data.providers import technical as tech_provider
from packages.data.providers import volatility as vol_provider
from packages.data.providers.news import catalyst as catalyst_engine
from packages.data.quality.dqs import QualityReport
from packages.data.quality.dqs import apply_extended_gate as dqs_apply_extended_gate
from packages.data.quality.dqs import compute as compute_dqs
from packages.data.quality.dqs import extended_metrics as dqs_extended_metrics
from packages.data.registry import assets as _asset_registry
from packages.data.registry import custom_assets as _custom_assets
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
    # Giriş kalitesi v2 — yön-bağımsız giriş bağlamı (aralık konumu, ATR-normalize uzama,
    # yaşa göre sönümlü dönüş olayları). Anahtar: symbol → timeframe → entry_context.
    # `entry_quality_v2.mode == "off"` iken HİÇ hesaplanmaz ({}), karar bayt-aynıdır.
    entry_contexts: dict[str, dict[str, dict]] = field(default_factory=dict)
    # Optional provider-neutral published capital-flow observations.  Existing
    # providers may leave this empty; rotation remains an explicit proxy.
    flow_observations: list[dict] = field(default_factory=list)
    # Official published observations are kept separate from the upcoming
    # event-risk calendar.  They feed world-state/evidence shadow analysis;
    # they do not silently become a verified future risk gate.
    macro_releases: list[Catalyst] = field(default_factory=list)
    # Historical replay provenance.  These are domain watermarks, not aliases
    # for ``generated_at``; unknown provider watermarks remain None.
    market_data_as_of: datetime | None = None
    events_available_as_of: datetime | None = None
    statements_available_as_of: datetime | None = None
    macro_available_as_of: datetime | None = None
    expectations_as_of: datetime | None = None
    flow_available_as_of: datetime | None = None
    ingested_at: datetime | None = None
    # Explicit replay semantics: AVAILABLE has a real watermark, UNAVAILABLE
    # means the domain supplied no evidence, UNKNOWN is a provenance blocker.
    provenance_domains: dict[str, dict] = field(default_factory=dict)


def _build_entry_contexts(symbols: list[str]) -> dict[str, dict[str, dict]]:
    """symbol → tf → entry_context (yalnız `entry_quality_v2.mode != off`).

    Barlar OHLCV önbelleğinden gelir (ağ yok, `get_snapshot` ile aynı pencere).
    Tek hücrenin hatası yalnız o hücreyi boş bırakır — karar zinciri etkilenmez."""
    from packages.scoring import entry_context, entry_quality

    if entry_quality.mode() == "off":
        return {}
    from packages.data.providers import ohlcv as _ohlcv

    out: dict[str, dict[str, dict]] = {}
    for s in symbols:
        for tf in TIMEFRAMES:
            try:
                ctx = entry_context.build(_ohlcv.get_bars(s, tf), tf)
            except Exception:  # bağlam üretilemedi → o hücre kısıtsız (uydurma yok)
                ctx = None
            if ctx:
                out.setdefault(s, {})[tf] = ctx
    return out


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


def _latest_timestamp(items: list[object], attribute: str = "ts") -> datetime | None:
    values = [getattr(item, attribute, None) for item in items]
    values = [value for value in values if isinstance(value, datetime)]
    return max(values) if values else None


def _latest_timestamp_before(items: list[object], cutoff: datetime, attribute: str = "ts") -> datetime | None:
    values = [getattr(item, attribute, None) for item in items]
    values = [value for value in values if isinstance(value, datetime) and value <= cutoff]
    return max(values) if values else None


def _latest_provider_ingestion(status: dict[str, dict]) -> datetime | None:
    values: list[datetime] = []
    for item in (status or {}).values():
        raw = item.get("last_success_at") if isinstance(item, dict) else None
        if not raw:
            continue
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            values.append(value if value.tzinfo is not None else value.replace(tzinfo=UTC))
        except (TypeError, ValueError):
            continue
    return max(values) if values else None


def _provider_ingestion_for(status: dict[str, dict], names: tuple[str, ...]) -> datetime | None:
    return _latest_provider_ingestion({name: status.get(name) for name in names if name in status})


def _provider_state(status: dict[str, dict], names: tuple[str, ...]) -> str:
    states = [str((status.get(name) or {}).get("status", "unknown")).lower() for name in names]
    if any(state == "ok" for state in states):
        return "AVAILABLE"
    if states and all(state in {"disabled", "unavailable", "down", "degraded"} for state in states):
        return "UNAVAILABLE"
    return "UNKNOWN"


def _domain_provenance(
    status: dict[str, dict],
    names: tuple[str, ...],
    watermark: datetime | None,
    *,
    has_evidence: bool,
) -> dict[str, object]:
    """Return an honest AVAILABLE/UNAVAILABLE/UNKNOWN domain state."""
    state = _provider_state(status, names)
    if watermark is not None:
        return {"status": "AVAILABLE", "as_of": watermark}
    if state == "AVAILABLE":
        # A successful zero-result provider is still an as-of observation; its
        # recorded ingestion time is the only non-fabricated watermark.
        observed_at = _provider_ingestion_for(status, names)
        return {"status": "AVAILABLE", "as_of": observed_at} if observed_at else {"status": "UNKNOWN", "as_of": None}
    if state == "UNAVAILABLE" and not has_evidence:
        return {"status": "UNAVAILABLE", "as_of": None}
    return {"status": "UNKNOWN", "as_of": None}


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
    with ThreadPoolExecutor(max_workers=6) as _ex:
        _f_prices = _ex.submit(price_provider.get_quotes, syms)
        # Foreign-affairs coverage is part of the world-state input, not only
        # a UI wall.  Keep a bounded but materially wider window so a fresh
        # US/Iran/China/Russia/Israel statement cannot be pushed out by market
        # headlines before causal + technical confluence is evaluated.
        _f_news = _ex.submit(news_provider.list_headlines, 48)
        _f_cal = _ex.submit(cal_provider.list_catalysts, 8)
        _f_macro = _ex.submit(macro_provider.list_releases, now=now)
        _f_rot = _ex.submit(rot_provider.get_rotation)
        _f_deriv = _ex.submit(
            deriv_provider.get_derivatives,
            [s for s in syms if s in deriv_provider.CRYPTO_SYMBOLS],
        )
        prices = _f_prices.result()
        headlines = _f_news.result()
        catalysts = _f_cal.result()
        macro_releases = _f_macro.result()
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
    # Giriş kalitesi v2: mode=off → atlanır (sıfır maliyet, bayt-aynı). shadow/active →
    # aynı önbellekli barlardan yön-bağımsız bağlam; hücre hatası kararı düşürmez.
    entry_contexts = _build_entry_contexts(tf_syms)
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
    # Runtime keşif/custom varlıklar, kendi fiyatı yokken bütün çekirdek
    # evreni RiskGate'e kapattırmamalı. Aday snapshot'ta kalır ve açık uyarı
    # alır; DQS çekirdek karar evreni üzerinden ölçülür.
    optional_symbols = frozenset(
        symbol for symbol in syms if _custom_assets.get(symbol) is not None
    )
    quality = compute_dqs(prices, syms, optional_symbols=optional_symbols)
    # 2026-07-13 — DQS genişletme (GÖZLEM-YALNIZ: score/status'a girmez; DQS'in
    # fiyat-dışı kör noktası her snapshot'ta görünür olsun).
    quality.extended = dqs_extended_metrics(
        technicals_by_tf=technicals_by_tf, headlines=headlines,
        rotation=rotation, now=now,
    )
    # Genişletilmiş eksen çöküşü status'u OK→DEGRADED indirir (skora dokunmaz).
    # Not satırı quality.notes'a düşer → aşağıdaki warnings kopyasıyla snapshot'a taşınır.
    try:
        from packages.data.registry.loader import load_thresholds as _load_thr

        dqs_apply_extended_gate(
            quality, (_load_thr().get("data_policy") or {}).get("dqs_extended_gate")
        )
    except (OSError, KeyError, ValueError, TypeError):
        pass  # config okunamazsa kapı yok sayılır (gözlem sürer; uydurma yok)
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
        **macro_provider.get_provider_status(),
        **rot_provider.get_provider_status(),
        **deriv_provider.get_provider_status(),
        **vol_provider.get_provider_status(),
        **options_provider.get_provider_status(),
    }
    if price_provider.is_runtime_mock_explicit():
        warnings.insert(0, "PRICE_USE_MOCK=true — TEST/MOCK MODE")
    market_data_as_of = _latest_timestamp(prices)
    events_available_as_of = _latest_timestamp(headlines)
    # Statements and expectations in World-State are deterministic views of
    # the same published headline/catalyst inputs; carry that source
    # watermark, never generated_at as a fabricated availability proof.
    statements_available_as_of = events_available_as_of
    expectations_as_of = statements_available_as_of
    # Calendar rows may describe a future scheduled release.  Its event time
    # is not an availability watermark; use only past releases or the
    # provider's recorded ingestion time, never a future catalyst timestamp.
    macro_events = [*catalysts, *macro_releases]
    macro_available_as_of = _latest_timestamp_before(macro_events, now) or _provider_ingestion_for(
        provider_status, ("calendar", "macro_bls", "macro_fred", "macro_eia")
    )
    # No provider-neutral real-flow observations are ingested by this pipeline
    # yet; World-State may still expose the explicit rotation price proxy.
    flow_available_as_of = None
    ingested_at = _latest_provider_ingestion(provider_status)
    # Domain status is kept separately from the legacy watermark fields so an
    # explicitly unavailable source is not confused with unknown provenance.
    provenance_domains = {
        "market": _domain_provenance(
            provider_status, ("coingecko", "yfinance", "fred", "twelvedata", "alphavantage", "finnhub"),
            market_data_as_of, has_evidence=bool(prices),
        ),
        "events": _domain_provenance(
            provider_status, ("news", "geo_news"), events_available_as_of,
            has_evidence=bool(headlines),
        ),
        "statements": _domain_provenance(
            provider_status, ("news", "geo_news"), statements_available_as_of,
            has_evidence=bool(headlines),
        ),
        "expectations": _domain_provenance(
            provider_status, ("news", "geo_news", "calendar", "macro_bls", "macro_fred", "macro_eia"), expectations_as_of,
            has_evidence=bool(headlines or catalysts),
        ),
        "macro": _domain_provenance(
            provider_status, ("calendar", "calendar_web", "macro_bls", "macro_fred", "macro_eia"), macro_available_as_of,
            has_evidence=bool(macro_events),
        ),
        "flow": _domain_provenance(
            provider_status, ("rotation",), flow_available_as_of,
            has_evidence=bool(getattr(rotation, "per_symbol", {})),
        ),
    }
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
        entry_contexts=entry_contexts,
        market_data_as_of=market_data_as_of,
        events_available_as_of=events_available_as_of,
        statements_available_as_of=statements_available_as_of,
        macro_available_as_of=macro_available_as_of,
        expectations_as_of=expectations_as_of,
        flow_available_as_of=flow_available_as_of,
        ingested_at=ingested_at,
        provenance_domains=provenance_domains,
        macro_releases=macro_releases,
    )


# Basit zaman cache — aynı saniye içinde yeniden hesaplamadan kaçınmak için
_CACHE: dict[str, tuple[float, MarketSnapshot]] = {}
_TTL_SEC = 30.0
_REFRESHING: set[str] = set()
_REFRESH_LOCK = threading.Lock()

# Tick'in karar verdiği snapshot. Supervisor'da tick ve API aynı süreçtedir;
# ekran, brifing ve YZ ayrı bir an kurmak yerine bunu okur. Tick takılırsa
# (yayın bayatlarsa) eski önbellek yoluna düşülür; ekran hiç beklemez.
_TICK_SNAPSHOT: tuple[float, MarketSnapshot] | None = None
_TICK_MAX_AGE_SEC = 180.0


def publish_tick_snapshot(snap: MarketSnapshot) -> None:
    """Tick yeni snapshot'ı kurduğunda çağırır (yalnız tick yazar)."""
    global _TICK_SNAPSHOT
    _TICK_SNAPSHOT = (time.monotonic(), snap)


def latest_tick_snapshot(max_age_sec: float = _TICK_MAX_AGE_SEC) -> MarketSnapshot | None:
    item = _TICK_SNAPSHOT
    if item is None or (time.monotonic() - item[0]) > max_age_sec:
        return None
    return item[1]


def reset_tick_snapshot() -> None:
    """Testler arası sızıntıyı önlemek için (conftest)."""
    global _TICK_SNAPSHOT
    _TICK_SNAPSHOT = None


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
    Bu, canlı provider yavaşladığında cockpit/brief'in donmasını engeller.

    Varsayılan sembol setinde tick'in taze snapshot'ı varsa o döner: ekran tick'in
    karar verdiği anı görür, aynı veri ikinci kez çekilmez."""
    if symbols is None:
        tick_snap = latest_tick_snapshot()
        if tick_snap is not None:
            return tick_snap
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
