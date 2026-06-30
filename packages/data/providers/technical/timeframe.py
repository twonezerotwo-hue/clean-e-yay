"""Per-timeframe technical feature builder (T-MTF) — pure, deterministic, paper-safe.

Packages the pure indicators into one canonical `TechnicalTimeframeResult` for a
single (symbol, closed-candle timeframe). EVIDENCE only:

  * never opens trades, never imports the decision engine / RiskGate;
  * never emits a single aggregated score — `direction_score` and `strength_score`
    stay SEPARATE axes (no "aggregated_technical_score" for all strategies);
  * insufficient / stale data becomes `indicator_quality` + `warnings` diagnostics,
    NEVER a fabricated neutral confidence (DATA_POLICY).

The builder treats `bars` as already-closed candles (closed-candle policy is the
caller's responsibility); it never peeks beyond the bars it is given.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from packages.data.providers.technical import fibonacci, indicators, patterns, reversal
from packages.data.registry import guard_overrides
from packages.data.registry.loader import load_thresholds
from packages.data.types import (
    ConfirmationSignal,
    FibonacciAnalysis,
    IndicatorQuality,
    IndicatorQualityReport,
    OHLCVBar,
    TechnicalBias,
    TechnicalChartPatterns,
    TechnicalConfluenceZone,
    TechnicalDataQuality,
    TechnicalKeyLevels,
    TechnicalReversalSignals,
    TechnicalScoreOverview,
    TechnicalTimeframeResult,
    TechnicalTimeframeSummary,
    TechnicalTrendStrength,
    TfVolatilityRegime,
    Timeframe,
)

# TF bazlı stale eşiği — packages/data/providers/technical/__init__.py ile aynı politika.
STALE_AFTER_SEC: dict[Timeframe, int] = {
    "15m": 1800,
    "1h": 7200,
    "4h": 28800,
    "1d": 172800,
    "1w": 864000,
}
# VWAP yalnızca intraday TF'lerde anlamlıdır (1d/1w'de üretilmez — per-TF semantik).
INTRADAY_TF: frozenset[Timeframe] = frozenset({"15m", "1h", "4h"})
_EMA_PERIODS = (20, 50, 200)


@dataclass(frozen=True)
class TechnicalConfig:
    """thresholds_v1.0.yaml `technical:` bloğundan türetilen deterministik params."""

    bull_cut: float = 60.0
    bear_cut: float = 40.0
    adx_trend_min: float = 20.0
    warmup: dict[str, int] = field(
        default_factory=lambda: {"rsi": 30, "macd": 60, "ema200": 220, "atr": 30, "adx": 40}
    )
    bb_squeeze_pct: float = 4.0
    bb_expansion_pct: float = 12.0
    pivot_left: int = 3
    pivot_right: int = 3
    stop_atr_mult: float = 1.5
    target_rr: float = 2.0
    # Top-down location gate (§4.5 evidence → direction). Momentum (RSI/MACD/EMA)
    # stays the directional spine/TRIGGER; location/pattern/volume evidence only
    # tilts conviction. Asymmetric by design: agreement gives a mild confirm,
    # conflict ("longing into resistance / premium") bites harder — never boosts a
    # neutral momentum into a fake signal (DATA_POLICY).
    tilt_weights: dict[str, float] = field(
        default_factory=lambda: {"location": 0.60, "pattern": 0.25, "volume": 0.15}
    )
    tilt_confirm_gain: float = 0.15   # max conviction *1.15 when evidence agrees
    tilt_penalty_gain: float = 0.40   # max conviction *0.60 when evidence conflicts
    # Faz 2 — chop guard: ADX düşükse (gerçek trend yok) momentum YÖNÜNÜ nötre çek.
    # enabled=False → HİÇ etki yok (mevcut skor birebir). Trendde (adx≥floor) etkisiz;
    # yalnız chop'ta (adx<floor) skor mesafesini 50'ye doğru kısar — asla yön çevirmez.
    chop_guard_enabled: bool = False
    chop_adx_floor: float = 20.0      # adx bunun altı = chop sayılır
    chop_min_mult: float = 0.5        # tam chop'ta (adx→0) momentum mesafesi ×bu
    # Faz 3a — exhaustion guard: momentum tükenmenin AYNI yönüne (climax) kovalıyorsa
    # sönümle. enabled=False → etki yok. Yön ASLA çevrilmez, size ASLA artmaz.
    exhaustion_guard_enabled: bool = False
    exh_high: float = 70.0            # ≥ bu = upside tükenmesi (long kovalama riski)
    exh_low: float = 30.0             # ≤ bu = downside tükenmesi (short kovalama riski)
    exh_min_mult: float = 0.5         # uçta (0/100) momentum mesafesi ×bu
    # Faz 3b — reversion (mean-reversion): uç tükenme + reversal teyidi → yönü ÇEVİR.
    # RİSK-YARATIR → default KAPALI. Yalnız reversal.bias teyit ederse tetiklenir.
    reversion_enabled: bool = False
    exh_rev_low: float = 20.0         # ≤ bu = güçlü downside tükenmesi (long reversal)
    exh_rev_high: float = 80.0        # ≥ bu = güçlü upside tükenmesi (short reversal)
    rev_magnitude: float = 25.0       # çevrilen skor 50±bu (consensus seyrelmesini aşmak için güçlü)


def load_config() -> TechnicalConfig:
    t = load_thresholds().get("technical", {}) or {}
    cuts = t.get("bias_cuts", {}) or {}
    vol = t.get("volatility", {}) or {}
    piv = t.get("swing_pivot", {}) or {}
    warm = t.get("warmup_min_bars", {}) or {}
    tlt = t.get("direction_tilt", {}) or {}
    tq = t.get("trend_quality", {}) or {}
    eg = t.get("exhaustion_guard", {}) or {}
    rv = t.get("reversion", {}) or {}
    return TechnicalConfig(
        bull_cut=float(cuts.get("bull", 60)),
        bear_cut=float(cuts.get("bear", 40)),
        adx_trend_min=float(t.get("adx_trend_min", 20)),
        warmup={
            "rsi": int(warm.get("rsi", 30)),
            "macd": int(warm.get("macd", 60)),
            "ema200": int(warm.get("ema200", 220)),
            "atr": int(warm.get("atr", 30)),
            "adx": int(warm.get("adx", 40)),
        },
        bb_squeeze_pct=float(vol.get("bb_squeeze_pct", 4.0)),
        bb_expansion_pct=float(vol.get("bb_expansion_pct", 12.0)),
        pivot_left=int(piv.get("left", 3)),
        pivot_right=int(piv.get("right", 3)),
        stop_atr_mult=float(t.get("stop_atr_mult", 1.5)),
        target_rr=float(t.get("target_rr", 2.0)),
        tilt_weights={
            "location": float(tlt.get("location", 0.60)),
            "pattern": float(tlt.get("pattern", 0.25)),
            "volume": float(tlt.get("volume", 0.15)),
        },
        tilt_confirm_gain=float(tlt.get("confirm_gain", 0.15)),
        tilt_penalty_gain=float(tlt.get("penalty_gain", 0.40)),
        # CP3 — yön güvenlik kasası: guard_safety bir guard'ı canlıda kötü bulup
        # kill-override yazdıysa enabled zorla False'a çekilir (config'e dokunmadan).
        # Override yokken `and not False` → birebir bugünkü davranış (law 2).
        chop_guard_enabled=bool(tq.get("enabled", False))
        and not guard_overrides.is_disabled("chop"),
        chop_adx_floor=float(tq.get("adx_chop_floor", 20.0)),
        chop_min_mult=float(tq.get("chop_min_mult", 0.5)),
        exhaustion_guard_enabled=bool(eg.get("enabled", False))
        and not guard_overrides.is_disabled("exhaustion"),
        exh_high=float(eg.get("exh_high", 70.0)),
        exh_low=float(eg.get("exh_low", 30.0)),
        exh_min_mult=float(eg.get("exh_min_mult", 0.5)),
        reversion_enabled=bool(rv.get("enabled", False))
        and not guard_overrides.is_disabled("reversion"),
        exh_rev_low=float(rv.get("exh_rev_low", 20.0)),
        exh_rev_high=float(rv.get("exh_rev_high", 80.0)),
        rev_magnitude=float(rv.get("rev_magnitude", 25.0)),
    )


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _q(ok: bool) -> IndicatorQuality:
    return "OK" if ok else "INSUFFICIENT_HISTORY"


def _ema_stack(emas: list[float | None]) -> str | None:
    if not all(e is not None for e in emas):
        return None
    e20, e50, e200 = emas
    if e20 > e50 > e200:  # type: ignore[operator]
        return "bullish"
    if e20 < e50 < e200:  # type: ignore[operator]
        return "bearish"
    return "mixed"


# Momentum bileşen ağırlıkları: trend (EMA dizilimi) yapısaldır, RSI ve MACD
# ivmeyi söyler. Her bileşen 50 etrafında merkezlenir (−1..+1 lean) ve ağırlıklı
# birleşir — eşit ortalama DEĞİL, yoksa hepsi aynı yöne baksa bile skor nötre
# çekilirdi (çakılan piyasanın ~42 kalması bu yüzdendi).
_MOM_WEIGHTS = {"trend": 0.40, "rsi": 0.30, "macd": 0.30}
# |MACD histogramı| bu kadar ATR olunca tam (±1) katkı. ATR-normalize: histogram
# fiyata oranlanınca (~±0.1) atıl kalıyordu — ivmeyi gerçekten ölçmüyordu.
_MACD_ATR_FULL = 1.0


def _momentum_score(
    rsi_v: float | None, macd_atr: float | None, ema_stack: str | None
) -> float | None:
    """Momentum/trend TRIGGER axis (0–100, 50 = neutral). None = insufficient.

    RSI + MACD + EMA stack are ONE momentum axis (so they are not triple-counted
    against the location/pattern/volume gate). Each is centred at 50 as a −1..+1 lean
    and combined by weight — NOT a plain average — so a unanimous bullish/bearish read
    scores strongly directional instead of being diluted toward neutral. MACD uses an
    ATR-relative histogram (price-relative was effectively inert)."""
    leans: list[tuple[float, float]] = []
    if ema_stack is not None:
        leans.append(({"bullish": 1.0, "bearish": -1.0, "mixed": 0.0}[ema_stack], _MOM_WEIGHTS["trend"]))
    if rsi_v is not None:
        leans.append((_clamp((rsi_v - 50.0) / 50.0, -1.0, 1.0), _MOM_WEIGHTS["rsi"]))
    if macd_atr is not None:
        leans.append((_clamp(macd_atr / _MACD_ATR_FULL, -1.0, 1.0), _MOM_WEIGHTS["macd"]))
    if not leans:
        return None
    num = sum(lean * wt for lean, wt in leans)
    den = sum(wt for _, wt in leans)
    return _clamp(50.0 + (num / den) * 50.0, 0.0, 100.0)


# Fib zone → bullish-favorable location (+) vs bearish-favorable (−). Aligned to the
# momentum direction later: longing near_support/breakout is good; into near_resistance
# is bad (the "where am I / is it cheap" read the score used to ignore).
_FIB_ZONE_BULL: dict[str, float] = {
    "near_support": 0.8, "breakout": 1.0, "mid_range": 0.0,
    "near_resistance": -0.8, "breakdown": -1.0, "unknown": 0.0,
}
_BIAS_BULL: dict[str, float] = {"BULLISH": 1.0, "BEARISH": -1.0, "NEUTRAL": 0.0}


def _location_alignment(
    dir_sign: float,
    fib: FibonacciAnalysis | None,
    zones: list[TechnicalConfluenceZone],
) -> float | None:
    """How well current LOCATION favors the momentum direction (−1..+1). None = no
    location evidence. + = good entry location for this side, − = chasing into S/R."""
    comps: list[float] = []
    if fib is not None and fib.validity != "unavailable" and fib.zone != "unknown":
        comps.append(_FIB_ZONE_BULL.get(fib.zone, 0.0) * dir_sign)
    if zones:
        # _confluence_zones already keys support<current / resistance>current.
        sup = any(z.kind == "support" for z in zones)
        res = any(z.kind == "resistance" for z in zones)
        struct_bull = _clamp((0.6 if sup else 0.0) - (0.6 if res else 0.0), -1.0, 1.0)
        if sup or res:
            comps.append(struct_bull * dir_sign)
    return sum(comps) / len(comps) if comps else None


def _pattern_alignment(
    dir_sign: float,
    reversal: TechnicalReversalSignals | None,
    chart: TechnicalChartPatterns | None,
) -> float | None:
    """Reversal + chart-pattern bias agreement with the momentum direction (−1..+1).
    A bearish reversal under a long trigger (e.g. divergence at the top) → penalty."""
    comps: list[float] = []
    if reversal is not None and reversal.bias != "NEUTRAL":
        comps.append(_BIAS_BULL[reversal.bias] * dir_sign)
    if chart is not None and chart.bias != "NEUTRAL":
        comps.append(_BIAS_BULL[chart.bias] * dir_sign)
    return sum(comps) / len(comps) if comps else None


def _volume_alignment(
    dir_sign: float, vwap_v: float | None, current: float | None
) -> float | None:
    """VWAP confirmation aligned to direction (−1..+1). None on non-intraday TF."""
    if vwap_v is None or current is None or vwap_v <= 0:
        return None
    return (1.0 if current > vwap_v else -1.0) * dir_sign


def _direction_score(
    rsi_v: float | None,
    macd_atr: float | None,
    ema_stack: str | None,
    *,
    fib: FibonacciAnalysis | None = None,
    zones: list[TechnicalConfluenceZone] | None = None,
    reversal: TechnicalReversalSignals | None = None,
    chart: TechnicalChartPatterns | None = None,
    vwap_v: float | None = None,
    current: float | None = None,
    adx_v: float | None = None,
    exhaustion_score: float | None = None,
    market_regime: str | None = None,
    cfg: TechnicalConfig | None = None,
) -> tuple[float | None, dict[str, float]]:
    """Top-down directional read (0–100, 50 = neutral). None = insufficient momentum.

    Order = the way a trader reads it: momentum is the TRIGGER, then location
    ("where am I / is it cheap"), pattern and volume GATE conviction around it. The
    gate is asymmetric — agreement confirms mildly, conflict bites hard — and never
    manufactures a direction from neutral momentum (DATA_POLICY). Returns the score
    plus a diagnostics map (evidence chain rule)."""
    cfg = cfg or load_config()
    core = _momentum_score(rsi_v, macd_atr, ema_stack)
    diag: dict[str, float] = {}
    if core is None:
        return None, diag
    diag["momentum"] = round(core, 2)

    dir_sign = 1.0 if core > 50.0 else (-1.0 if core < 50.0 else 0.0)
    if dir_sign == 0.0:
        return core, diag  # neutral trigger — evidence does not fabricate a side

    loc = _location_alignment(dir_sign, fib, zones or [])
    pat = _pattern_alignment(dir_sign, reversal, chart)
    vol = _volume_alignment(dir_sign, vwap_v, current)
    parts = (("location", loc), ("pattern", pat), ("volume", vol))

    num = den = 0.0
    for name, val in parts:
        if val is None:
            continue
        diag[name] = round(val, 3)
        wt = cfg.tilt_weights.get(name, 0.0)
        num += val * wt
        den += wt
    agreement = num / den if den > 0 else 0.0  # −1..+1, evidence vs momentum side

    gain = cfg.tilt_confirm_gain if agreement >= 0 else cfg.tilt_penalty_gain
    mult = 1.0 + gain * agreement
    diag["gate_mult"] = round(mult, 3)

    final = 50.0 + (core - 50.0) * mult

    # Faz 2 — chop guard. Çarpan HER ZAMAN hesaplanır (shadow gözlem) ama yalnız
    # enabled iken final'a uygulanır. Böylece flag KAPALIYKEN bile "chop'ta skor ne
    # kadar sönerdi" diag'a yazılır → öğrenme katmanı yön-motorunu İZLEMEDİĞİ için
    # tek manuel tespit sinyali budur. Trendde (adx≥floor) çarpan 1.0 (dokunmaz);
    # yön ASLA çevrilmez (yalnız sönümler).
    if adx_v is not None and cfg.chop_adx_floor > 0:
        ratio = _clamp(adx_v / cfg.chop_adx_floor, 0.0, 1.0)
        chop_mult = cfg.chop_min_mult + (1.0 - cfg.chop_min_mult) * ratio
        if chop_mult < 1.0:
            diag["chop_mult_shadow"] = round(chop_mult, 3)  # her zaman (gözlem)
            if cfg.chop_guard_enabled:
                diag["chop_mult"] = round(chop_mult, 3)      # uygulandı
                final = 50.0 + (final - 50.0) * chop_mult

    # Faz 3a — exhaustion guard: momentum tükenmenin AYNI yönüne (climax'ı) kovalıyorsa
    # sönümle. exhaustion>50 = upside tükenmesi (yukarı kovalama riski), <50 = downside
    # tükenmesi (aşağı kovalama riski). Momentum ters yöndeyse (reversal'ı sürüyorsa)
    # DOKUNMAZ. Çarpan her zaman hesaplanır (shadow); yalnız enabled iken uygulanır.
    if exhaustion_score is not None:
        dir_lean = final - 50.0
        exh_mult = 1.0
        if dir_lean > 0 and exhaustion_score >= cfg.exh_high:        # bullish → tepeyi kovalıyor
            t = _clamp((exhaustion_score - cfg.exh_high) / (100.0 - cfg.exh_high), 0.0, 1.0)
            exh_mult = 1.0 - (1.0 - cfg.exh_min_mult) * t
        elif dir_lean < 0 and exhaustion_score <= cfg.exh_low:       # bearish → dibi kovalıyor
            t = _clamp((cfg.exh_low - exhaustion_score) / cfg.exh_low, 0.0, 1.0)
            exh_mult = 1.0 - (1.0 - cfg.exh_min_mult) * t
        if exh_mult < 1.0:
            diag["exh_mult_shadow"] = round(exh_mult, 3)
            if cfg.exhaustion_guard_enabled:
                diag["exh_mult"] = round(exh_mult, 3)
                final = 50.0 + (final - 50.0) * exh_mult

    # Faz 3b — reversion (mean-reversion): momentum UÇTA tükenmiş + reversal teyidi
    # TERS yönü işaret ediyorsa yönü ÇEVİR (oversold+bullish reversal → LONG;
    # overbought+bearish reversal → SHORT). RİSK-YARATIR (counter-trend) → default
    # KAPALI + shadow; yalnız enabled iken uygulanır. Touche modül skorudur, consensus
    # ağırlığında seyrelir → magnitude güçlü tutulur (diğer modüller sert karşı çıkmadıkça
    # geçer). Reversal teyidi ŞART (yalnız exhaustion yetmez).
    rev_bias = reversal.bias if reversal is not None else "NEUTRAL"
    # Faz 4 model anahtarı: reversion yalnız TREND DIŞINDA (RANGE/TRANSITION/UNKNOWN)
    # tetiklenir — trende karşı dönüş açma. market_regime None ise (eski çağrı/unit
    # test) kapı uygulanmaz (geri uyumlu).
    regime_allows_reversion = market_regime != "TREND"
    if exhaustion_score is not None and rev_bias in ("BULLISH", "BEARISH") and regime_allows_reversion:
        rev_dir = 0.0
        if exhaustion_score <= cfg.exh_rev_low and rev_bias == "BULLISH" and final < 50.0:
            rev_dir = 1.0     # downside tükenmesi + bullish reversal → LONG
        elif exhaustion_score >= cfg.exh_rev_high and rev_bias == "BEARISH" and final > 50.0:
            rev_dir = -1.0    # upside tükenmesi + bearish reversal → SHORT
        if rev_dir != 0.0:
            rev_score = _clamp(50.0 + rev_dir * cfg.rev_magnitude, 0.0, 100.0)
            diag["reversion_shadow"] = round(rev_score, 2)
            if cfg.reversion_enabled:
                diag["reversion"] = round(rev_score, 2)
                final = rev_score

    return _clamp(final, 0.0, 100.0), diag


def _strength_score(adx_v: float | None, direction_score: float | None) -> float | None:
    """0–100 conviction (trend reality + signal alignment). None = insufficient."""
    comps: list[float] = []
    if adx_v is not None:
        comps.append(_clamp(adx_v / 50.0 * 100.0, 0.0, 100.0))
    if direction_score is not None:
        comps.append(_clamp(abs(direction_score - 50.0) * 2.0, 0.0, 100.0))
    if not comps:
        return None
    return sum(comps) / len(comps)


def _bias(direction_score: float | None, cfg: TechnicalConfig) -> TechnicalBias:
    if direction_score is None:
        return "NEUTRAL"
    if direction_score > cfg.bull_cut:
        return "BULLISH"
    if direction_score < cfg.bear_cut:
        return "BEARISH"
    return "NEUTRAL"


def _volatility_regime(
    adx_v: float | None, bb_w: float | None, cfg: TechnicalConfig
) -> TfVolatilityRegime:
    if adx_v is None and bb_w is None:
        return "UNKNOWN"
    if adx_v is not None and adx_v >= cfg.adx_trend_min:
        return "TRENDING"
    if bb_w is not None:
        if bb_w <= cfg.bb_squeeze_pct:
            return "SQUEEZE"
        if bb_w >= cfg.bb_expansion_pct:
            return "EXPANSION"
    return "RANGING"


def _market_regime(adx_v: float | None, vol_regime: str, cfg: TechnicalConfig) -> str:
    """Faz 4 — continuation/reversion MODEL ANAHTARI: TREND | RANGE | TRANSITION |
    UNKNOWN. Yeni hesap değil — adx + volatility_regime'den temiz 3'lü etiket türetir.
    TREND = momentum/continuation modeli geçerli; RANGE = mean-reversion modeli
    geçerli; TRANSITION (expansion) = belirsiz. Reversion (F3b) yalnız TREND DIŞINDA
    tetiklenir (trende karşı dönüş açma)."""
    if vol_regime == "TRENDING" or (adx_v is not None and adx_v >= cfg.adx_trend_min):
        return "TREND"
    if vol_regime in ("RANGING", "SQUEEZE"):
        return "RANGE"
    if vol_regime == "EXPANSION":
        return "TRANSITION"
    return "UNKNOWN"


def _key_levels(
    current: float | None,
    pivots: tuple[list[float], list[float]] | None,
    atr_v: float | None,
    atr_pct: float | None,
    cfg: TechnicalConfig,
) -> TechnicalKeyLevels:
    support = resistance = stop_ref = target_ref = None
    if pivots is not None and current is not None and current > 0:
        highs, lows = pivots
        below = [lvl for lvl in lows if lvl < current]
        above = [hi for hi in highs if hi > current]
        support = max(below) if below else None
        resistance = min(above) if above else None
    if atr_v is not None and current is not None and current > 0:
        # Long-oriented reference (evidence only): nearest support, else ATR buffer.
        base_stop = support if support is not None else current - cfg.stop_atr_mult * atr_v
        if base_stop is not None and base_stop < current:
            stop_ref = base_stop
            risk = current - stop_ref
            if risk > 0:
                target_ref = current + cfg.target_rr * risk
    return TechnicalKeyLevels(
        support=round(support, 6) if support is not None else None,
        resistance=round(resistance, 6) if resistance is not None else None,
        atr=round(atr_v, 6) if atr_v is not None else None,
        atr_percent=round(atr_pct, 4) if atr_pct is not None else None,
        stop_reference=round(stop_ref, 6) if stop_ref is not None else None,
        target_reference=round(target_ref, 6) if target_ref is not None else None,
    )


def _trend_strength(
    adx_t: tuple[float, float, float] | None, cfg: TechnicalConfig
) -> TechnicalTrendStrength:
    if adx_t is None:
        return TechnicalTrendStrength()
    adx_v, plus_di, minus_di = adx_t
    is_tr = adx_v >= cfg.adx_trend_min
    return TechnicalTrendStrength(
        adx=round(adx_v, 2),
        plus_di=round(plus_di, 2),
        minus_di=round(minus_di, 2),
        is_trending=is_tr,
        label="TRENDING" if is_tr else "WEAK",
    )


def _confluence_zones(
    current: float | None,
    atr_pct: float | None,
    support: float | None,
    resistance: float | None,
    vwap_v: float | None,
    fib: FibonacciAnalysis | None,
) -> list[TechnicalConfluenceZone]:
    if current is None or current <= 0:
        return []
    tol_pct = _clamp(atr_pct if atr_pct is not None else 1.0, 0.25, 2.0)
    zones: list[TechnicalConfluenceZone] = []
    for role in ("support", "resistance"):
        comps: list[str] = []
        prices: list[float] = []
        sw = support if role == "support" else resistance
        if sw is not None:
            comps.append(f"swing_{role}")
            prices.append(sw)
        if (
            fib is not None
            and fib.nearest_level is not None
            and fib.nearest_level.role == role
            and fib.nearest_level.price > 0
        ):
            comps.append(f"fib_{fib.nearest_level.label}")
            prices.append(fib.nearest_level.price)
        if vwap_v is not None and vwap_v > 0:
            vrole = "support" if vwap_v <= current else "resistance"
            if vrole == role:
                comps.append("vwap")
                prices.append(vwap_v)
        if len(prices) >= 2:
            anchor = sum(prices) / len(prices)
            if anchor > 0 and all(abs(p - anchor) / anchor * 100.0 <= tol_pct for p in prices):
                zones.append(
                    TechnicalConfluenceZone(
                        price=round(anchor, 6), kind=role, components=comps  # type: ignore[arg-type]
                    )
                )
    return zones


def _confirmations(
    rsi_v: float | None,
    macd_t: tuple[float, float, float] | None,
    ema_stack: str | None,
    current: float | None,
    vwap_v: float | None,
) -> list[ConfirmationSignal]:
    """TIMING gates only (fired/not) — the same magnitude is scored once elsewhere."""
    sigs: list[ConfirmationSignal] = []
    if macd_t is not None:
        hist = macd_t[2]
        sigs.append(
            ConfirmationSignal(
                name="macd_histogram_positive", fired=hist > 0, detail=f"hist={hist:.6f}"
            )
        )
    if rsi_v is not None:
        sigs.append(
            ConfirmationSignal(name="rsi_above_50", fired=rsi_v > 50.0, detail=f"rsi={rsi_v:.1f}")
        )
    if ema_stack is not None:
        sigs.append(
            ConfirmationSignal(
                name="ema_stack_bullish", fired=ema_stack == "bullish", detail=ema_stack
            )
        )
    if vwap_v is not None and current is not None:
        sigs.append(
            ConfirmationSignal(name="above_vwap", fired=current > vwap_v, detail=f"vwap={vwap_v:.4f}")
        )
    return sigs


def build_timeframe_result(
    symbol: str,
    timeframe: Timeframe,
    bars: list[OHLCVBar],
    *,
    now: datetime | None = None,
    config: TechnicalConfig | None = None,
    fibonacci_analysis: FibonacciAnalysis | None = None,
) -> TechnicalTimeframeResult:
    """Build the canonical per-TF technical result from real closed OHLCV bars."""
    now = now or datetime.now(UTC)
    cfg = config or load_config()
    n = len(bars)
    closes = [b.close for b in bars]
    current = closes[-1] if closes else None

    # ── indicators (closed-candle input only) ─────────────────────────────────
    rsi_v = indicators.rsi(closes)
    macd_t = indicators.macd(closes)
    atr_v = indicators.atr(bars)
    atr_pct = indicators.atr_percent(bars)
    adx_t = indicators.adx(bars)
    emas = [indicators.ema(closes, p) for p in _EMA_PERIODS]
    bb_w = indicators.bollinger_width(closes)
    pivots = indicators.swing_pivots(bars, left=cfg.pivot_left, right=cfg.pivot_right)
    vwap_v = indicators.vwap(bars) if timeframe in INTRADAY_TF else None

    macd_norm = macd_t[2] / current * 100.0 if (macd_t is not None and current and current > 0) else None
    # ATR-relative MACD histogram for the momentum score (price-relative was inert).
    macd_atr = macd_t[2] / atr_v if (macd_t is not None and atr_v and atr_v > 0) else None
    ema_stack = _ema_stack(emas)
    adx_v = adx_t[0] if adx_t is not None else None

    # ── data quality / warm-up (insufficient = diagnostic, never fake value) ───
    iq = IndicatorQualityReport(
        rsi=_q(rsi_v is not None and n >= cfg.warmup["rsi"]),
        macd=_q(macd_norm is not None and n >= cfg.warmup["macd"]),
        ema200=_q(emas[2] is not None and n >= cfg.warmup["ema200"]),
        atr=_q(atr_v is not None and n >= cfg.warmup["atr"]),
        adx=_q(adx_t is not None and n >= cfg.warmup["adx"]),
    )
    stale = bool(bars) and (
        (now - bars[-1].ts).total_seconds() > STALE_AFTER_SEC.get(timeframe, 172800)
    )
    warnings: list[str] = []
    if not bars:
        warnings.append("no_bars")
    if stale:
        warnings.append("stale_last_bar")
    for name, q in (
        ("rsi", iq.rsi), ("macd", iq.macd), ("ema200", iq.ema200), ("atr", iq.atr), ("adx", iq.adx)
    ):
        if q == "INSUFFICIENT_HISTORY":
            warnings.append(f"insufficient_history:{name}")
    core_ok = iq.rsi == "OK" and iq.atr == "OK"
    status = "OK" if (bars and not stale and core_ok) else "DEGRADED"

    # ── fibonacci (per-TF semantics: only 1D / 4H) ────────────────────────────
    fib = fibonacci_analysis
    if fib is None and timeframe in ("4h", "1d"):
        fib = fibonacci.analyze(
            bars, timeframe=("1D" if timeframe == "1d" else "4H"), current_price=current
        )

    # ── reversal + chart patterns (section 4.5; EVIDENCE only) ────────────────
    reversal_signals = reversal.detect(bars, left=cfg.pivot_left, right=cfg.pivot_right)
    chart_patterns = patterns.detect(bars, left=cfg.pivot_left, right=cfg.pivot_right)

    # ── structure first (location is read BEFORE the momentum trigger) ────────
    key_levels = _key_levels(current, pivots, atr_v, atr_pct, cfg)
    trend = _trend_strength(adx_t, cfg)
    vol_regime = _volatility_regime(adx_v, bb_w, cfg)
    market_regime = _market_regime(adx_v, vol_regime, cfg)  # Faz 4 — model anahtarı
    zones = _confluence_zones(
        current, atr_pct, key_levels.support, key_levels.resistance, vwap_v, fib
    )

    # ── scoring (SEPARATE axes) — top-down: momentum trigger gated by location/
    #    pattern/volume evidence (§4.5 now feeds direction, no longer evidence-only).
    # Faz 3a — exhaustion (climax kovalama riski). Lokal import: paket-init cycle'ı
    # (timeframe ↔ scoring) önler. Volume climax + liquidity sweep beslenir →
    # RSI+getiri'ye ek climax kanıtı (shadow'daki agent_pipeline ile aynı girdiler).
    from packages.liquidity import sweep as _sweep_engine
    from packages.scoring import exhaustion as _exhaustion_engine
    from packages.volume import engine as _volume_engine
    _vol = _volume_engine.analyze(bars, timeframe=timeframe)
    _swp = _sweep_engine.analyze(bars, timeframe=timeframe)
    _exh = _exhaustion_engine.analyze(bars, timeframe=timeframe, volume=_vol, sweep=_swp)
    exhaustion_score = _exh.score if _exh.validity != "unavailable" else None

    direction, dir_diag = _direction_score(
        rsi_v, macd_atr, ema_stack,
        fib=fib, zones=zones, reversal=reversal_signals, chart=chart_patterns,
        vwap_v=vwap_v, current=current, adx_v=adx_v,
        exhaustion_score=exhaustion_score, market_regime=market_regime, cfg=cfg,
    )
    strength = _strength_score(adx_v, direction)
    bias = _bias(direction, cfg)

    evidence: list[str] = []
    if direction is not None:
        evidence.append(f"direction_score={direction:.1f}")
        gm = dir_diag.get("gate_mult")
        if gm is not None and abs(gm - 1.0) >= 0.01:
            evidence.append(f"location_gate=×{gm}")
        cm = dir_diag.get("chop_mult_shadow")
        if cm is not None:
            applied = "chop_guard" if cfg.chop_guard_enabled else "chop_guard_shadow"
            evidence.append(f"{applied}=×{cm}")
        em = dir_diag.get("exh_mult_shadow")
        if em is not None:
            applied = "exhaustion_guard" if cfg.exhaustion_guard_enabled else "exhaustion_guard_shadow"
            evidence.append(f"{applied}=×{em}")
        rv = dir_diag.get("reversion_shadow")
        if rv is not None:
            applied = "reversion" if cfg.reversion_enabled else "reversion_shadow"
            evidence.append(f"{applied}→{rv}")
    else:
        evidence.append("direction_unavailable_insufficient_data")
    if trend.label != "UNKNOWN":
        evidence.append(f"adx={trend.adx} ({trend.label})")
    evidence.append(f"volatility_regime={vol_regime}")
    evidence.append(f"market_regime={market_regime}")  # Faz 4 — model anahtarı
    if fib is not None and fib.validity != "unavailable":
        evidence.append(f"fib_zone={fib.zone}")
    if reversal_signals is not None and reversal_signals.bias != "NEUTRAL":
        evidence.append(
            f"reversal_bias={reversal_signals.bias} ({len(reversal_signals.signals)} signals)"
        )
    if chart_patterns is not None and chart_patterns.active_patterns:
        evidence.append(f"pattern={chart_patterns.active_patterns[0].name}")
    for z in zones:
        evidence.append(f"confluence:{z.kind}@{z.price} [{'+'.join(z.components)}]")

    summary = TechnicalTimeframeSummary(bias=bias, evidence=evidence, warnings=warnings)

    return TechnicalTimeframeResult(
        symbol=symbol,
        timeframe=timeframe,
        data_quality=TechnicalDataQuality(
            status=status, bars_used=n, stale=stale, indicator_quality=iq, warnings=warnings
        ),
        score_overview=TechnicalScoreOverview(
            direction_score=round(direction, 2) if direction is not None else None,
            strength_score=round(strength, 2) if strength is not None else None,
            location_gate_multiplier=dir_diag.get("gate_mult"),
            chop_guard_multiplier=dir_diag.get("chop_mult_shadow"),
            exhaustion_guard_multiplier=dir_diag.get("exh_mult_shadow"),
            reversion_score=dir_diag.get("reversion_shadow"),
            market_regime=market_regime,
        ),
        key_levels=key_levels,
        confirmation_signals=_confirmations(rsi_v, macd_t, ema_stack, current, vwap_v),
        trend_strength=trend,
        volatility_regime=vol_regime,
        confluence_zones=zones,
        timeframe_summary=summary,
        fibonacci_analysis=fib,
        reversal_signals=reversal_signals,
        chart_pattern_analysis=chart_patterns,
        status=status,
        source=bars[-1].source if bars else "none",
        ts=bars[-1].ts if bars else now,
    )
