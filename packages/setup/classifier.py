"""Setup Classifier — EVIDENCE only (spec v2.3 §19).

Mevcut pipeline'ın zaten ürettiği kanıtları (consensus alignment, technical
agent trend/pattern/reversal okumaları, Elliott senaryosu, Zone Engine
location'ı) **tek bir setup tipine** indirger:

    TREND_LONG, TREND_SHORT, REVERSAL_LONG_WATCH, REVERSAL_SHORT_WATCH,
    REVERSAL_LONG_CONFIRMED, REVERSAL_SHORT_CONFIRMED, SCALP_LONG, SCALP_SHORT,
    RANGE_LONG, RANGE_SHORT, BREAKOUT_LONG, BREAKOUT_SHORT, PULLBACK_LONG,
    PULLBACK_SHORT, NO_TRADE

Bu modül **yeni veri üretmez** — sadece zaten hesaplanmış (consensus,
agent_pipeline, elliott, zones) kanıtları okur ve deterministik bir
sınıflandırma kuralı uygular. Hiçbir trade açmaz, hiçbir mevcut karar
zincirini (decide_for_symbol / decide_matrix / agent_decision) etkilemez —
bu paralel, gözlem amaçlı bir katmandır (bkz. packages/decision/shadow.py).

Setup var = işlem açılır demek değildir; sadece "fikir geçerli mi" sorusuna
cevap verir (spec §19.3). Final karar Conflict Resolver + RiskGate'e aittir.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SetupType = str  # bkz. modül docstring'indeki 15 değerli enum (plain str — henüz API'ye taşınmadı)

NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class SetupInputs:
    """Sınıflandırma için gereken, ZATEN HESAPLANMIŞ kanıtlar (saf veri taşıyıcı).

    Hepsi mevcut pipeline'dan okunur: consensus (ConsensusSnapshot), entry
    timeframe'in TechnicalTimeframeResult'ı, Elliott + Zone analizleri.
    """

    direction_score: float | None  # consensus.direction_score (50=neutral)
    alignment_status: str  # consensus.alignment_status: ALIGNED/PARTIAL/CONFLICTED/COUNTERTREND
    is_countertrend: bool
    entry_timeframe: str | None
    volatility_regime: str  # TfVolatilityRegime: TRENDING/RANGING/SQUEEZE/EXPANSION/UNKNOWN
    trend_label: str  # TrendStrengthLabel: TRENDING/WEAK/UNKNOWN
    is_trending: bool
    chart_pattern_names: tuple[str, ...] = ()  # uptrend_structure/downtrend_structure/ranging
    reversal_bias: str = "NEUTRAL"  # BULLISH/BEARISH/NEUTRAL
    zone_location: str | None = None  # near_support/near_resistance/mid_range/breakout/breakdown
    elliott_scenario: str | None = None
    elliott_bias: str | None = None  # REVERSAL_LONG/REVERSAL_SHORT/CONTINUATION/unknown
    elliott_confidence: float = 0.0
    # Faz 4 — additive (Volume/Liquidity-Sweep/Exhaustion motorlarından, Faz 1-2).
    # Default'lar eski davranışı DEĞİŞTİRMEZ: "unknown"/None hiçbir ek onay yolunu tetiklemez.
    liquidity_sweep_bias: str = "unknown"  # REVERSAL_LONG/REVERSAL_SHORT/unknown (packages/liquidity/sweep.py)
    exhaustion_score: float | None = None  # 0..100, 50=nötr (packages/scoring/exhaustion.py)
    volume_state: str | None = None  # VOLUME_CLIMAX/.../VOLUME_NEUTRAL (packages/volume/engine.py)
    volume_price_direction: str | None = None  # up/down/flat/unknown


@dataclass(frozen=True)
class SetupResult:
    setup_type: SetupType
    direction: str | None  # LONG/SHORT/None
    reason: str
    evidence: list[str] = field(default_factory=list)


_SCALP_TIMEFRAMES = {"15m", "1h"}
_REVERSAL_CONFIRM_MIN_CONFIDENCE = 75.0
_EXHAUSTION_EXTREME_LOW = 20.0
_EXHAUSTION_EXTREME_HIGH = 80.0


def _direction(direction_score: float | None) -> str | None:
    if direction_score is None:
        return None
    if direction_score > 50:
        return "LONG"
    if direction_score < 50:
        return "SHORT"
    return None


def classify(inputs: SetupInputs) -> SetupResult:
    """Deterministik setup sınıflandırması — sabit öncelik sırası (yukarıdan aşağı)."""
    direction = _direction(inputs.direction_score)

    if direction is None:
        return SetupResult(NO_TRADE, None, "no_clear_direction")
    if inputs.alignment_status == "CONFLICTED":
        return SetupResult(NO_TRADE, direction, "alignment_conflicted")

    # 1) Breakout — zone breakout/breakdown yönle uyumlu
    if inputs.zone_location == "breakout" and direction == "LONG":
        return SetupResult("BREAKOUT_LONG", direction, "zone_breakout", ["zone_location=breakout"])
    if inputs.zone_location == "breakdown" and direction == "SHORT":
        return SetupResult("BREAKOUT_SHORT", direction, "zone_breakdown", ["zone_location=breakdown"])

    # 2) Reversal — reversal kanıtı mevcut yönle uyumlu VE iyi konumda (support/resistance)
    reversal_dir = (
        "LONG" if inputs.reversal_bias == "BULLISH"
        else "SHORT" if inputs.reversal_bias == "BEARISH"
        else None
    )
    if reversal_dir == direction:
        good_location = (
            (direction == "LONG" and inputs.zone_location == "near_support")
            or (direction == "SHORT" and inputs.zone_location == "near_resistance")
        )
        if good_location:
            expected_reversal_bias = "REVERSAL_LONG" if direction == "LONG" else "REVERSAL_SHORT"
            ev = [f"reversal_bias={inputs.reversal_bias}", f"zone_location={inputs.zone_location}"]

            elliott_supports = (
                inputs.elliott_bias == expected_reversal_bias
                and inputs.elliott_confidence >= _REVERSAL_CONFIRM_MIN_CONFIDENCE
            )
            if elliott_supports:
                ev.append(f"elliott={inputs.elliott_scenario}@{inputs.elliott_confidence}")

            # Faz 4 — additive alternatif onay kaynakları (Elliott yoksa sayım ölmez,
            # spec §10.6 ilkesiyle uyumlu: tek bir kanıt kaynağına bağımlı değil).
            sweep_supports = inputs.liquidity_sweep_bias == expected_reversal_bias
            if sweep_supports:
                ev.append(f"liquidity_sweep={inputs.liquidity_sweep_bias}")

            exhaustion_supports = inputs.exhaustion_score is not None and (
                (direction == "LONG" and inputs.exhaustion_score <= _EXHAUSTION_EXTREME_LOW)
                or (direction == "SHORT" and inputs.exhaustion_score >= _EXHAUSTION_EXTREME_HIGH)
            )
            if exhaustion_supports:
                ev.append(f"exhaustion_score={inputs.exhaustion_score}")

            volume_supports = (
                inputs.volume_state == "VOLUME_CLIMAX"
                and (
                    (direction == "LONG" and inputs.volume_price_direction == "down")
                    or (direction == "SHORT" and inputs.volume_price_direction == "up")
                )
            )
            if volume_supports:
                ev.append(f"volume_climax_against_prior_move:{inputs.volume_price_direction}")

            if elliott_supports or sweep_supports or exhaustion_supports or volume_supports:
                return SetupResult(f"REVERSAL_{direction}_CONFIRMED", direction, "reversal_confirmed", ev)
            return SetupResult(f"REVERSAL_{direction}_WATCH", direction, "reversal_evidence_without_confirmation", ev)

    # 3) Range — RANGING rejim veya 'ranging' pattern, trend yok
    is_ranging = inputs.volatility_regime == "RANGING" or "ranging" in inputs.chart_pattern_names
    if is_ranging and not inputs.is_trending:
        return SetupResult(f"RANGE_{direction}", direction, "ranging_regime_no_trend", [f"volatility_regime={inputs.volatility_regime}"])

    # 4) Pullback — trend var, entry TF geçici karşı yönde (countertrend) ama yapısal pattern trend yönünde
    trend_pattern = (
        (direction == "LONG" and "uptrend_structure" in inputs.chart_pattern_names)
        or (direction == "SHORT" and "downtrend_structure" in inputs.chart_pattern_names)
    )
    if inputs.is_trending and inputs.is_countertrend and trend_pattern:
        return SetupResult(f"PULLBACK_{direction}", direction, "pullback_within_trend", ["is_countertrend=True", f"pattern_matches={direction}"])

    # 5) Scalp — kısa entry timeframe, güçlü trend/pattern kanıtı yok
    if inputs.entry_timeframe in _SCALP_TIMEFRAMES:
        return SetupResult(f"SCALP_{direction}", direction, "short_timeframe_entry", [f"entry_timeframe={inputs.entry_timeframe}"])

    # 6) Trend — trend var ve yapısal pattern yönle uyumlu
    if inputs.is_trending and trend_pattern:
        return SetupResult(f"TREND_{direction}", direction, "trending_with_structure", [f"trend_label={inputs.trend_label}"])

    return SetupResult(NO_TRADE, direction, "no_setup_evidence_matched")


__all__ = ["SetupInputs", "SetupResult", "classify", "NO_TRADE"]
