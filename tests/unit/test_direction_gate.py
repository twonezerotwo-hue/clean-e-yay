"""Top-down location gate on direction_score (§4.5 evidence → direction).

Momentum (RSI/MACD/EMA) is the directional TRIGGER; location (fib/S-R), pattern and
volume only TILT conviction around it — asymmetrically (mild confirm, hard penalty)
and never fabricating a side from neutral momentum (DATA_POLICY).
"""
from __future__ import annotations

from packages.data.providers.technical import timeframe as tf
from packages.data.types import (
    FibonacciAnalysis,
    TechnicalChartPatterns,
    TechnicalConfluenceZone,
    TechnicalReversalSignals,
)

# Bullish momentum core ≈ 65 (rsi 70, macd-neutral, ema bullish=75 → mean 65).
_RSI, _MACD, _EMA = 70.0, 0.0, "bullish"


def _score(**kw) -> float:
    s, _ = tf._direction_score(_RSI, _MACD, _EMA, **kw)
    assert s is not None
    return s


def test_pure_momentum_is_core_when_no_evidence():
    # No location/pattern/volume evidence → score is the untouched momentum core.
    assert _score() == tf._momentum_score(_RSI, _MACD, _EMA)


def test_agreeing_evidence_confirms_mildly():
    pure = _score()
    confirmed = _score(
        fib=FibonacciAnalysis(timeframe="1D", zone="near_support", validity="sane"),
        zones=[TechnicalConfluenceZone(price=90.0, kind="support", components=["swing_support"])],
        reversal=TechnicalReversalSignals(bias="BULLISH"),
        chart=TechnicalChartPatterns(bias="BULLISH"),
    )
    assert confirmed > pure


def test_conflicting_evidence_penalizes_hard():
    # Bullish trigger but price is at resistance / premium with a bearish reversal —
    # "longing into resistance". Conviction must drop toward neutral.
    pure = _score()
    conflicted = _score(
        fib=FibonacciAnalysis(timeframe="1D", zone="near_resistance", validity="sane"),
        zones=[TechnicalConfluenceZone(price=110.0, kind="resistance", components=["swing_resistance"])],
        reversal=TechnicalReversalSignals(bias="BEARISH"),
    )
    assert conflicted < pure


def test_penalty_bites_harder_than_confirm_is_asymmetric():
    pure = _score()
    confirm_delta = _score(
        fib=FibonacciAnalysis(timeframe="1D", zone="near_support", validity="sane"),
        reversal=TechnicalReversalSignals(bias="BULLISH"),
    ) - pure
    penalty_delta = pure - _score(
        fib=FibonacciAnalysis(timeframe="1D", zone="near_resistance", validity="sane"),
        reversal=TechnicalReversalSignals(bias="BEARISH"),
    )
    assert penalty_delta > confirm_delta > 0


def test_neutral_momentum_evidence_does_not_fabricate_direction():
    # Core == 50 (rsi 50, macd 0, ema mixed) → evidence cannot manufacture a side.
    s, _ = tf._direction_score(
        50.0, 0.0, "mixed",
        fib=FibonacciAnalysis(timeframe="1D", zone="near_support", validity="sane"),
        reversal=TechnicalReversalSignals(bias="BULLISH"),
    )
    assert s == 50.0


def test_insufficient_momentum_stays_none():
    # No momentum inputs → None (NOT a fake neutral), evidence ignored.
    s, diag = tf._direction_score(
        None, None, None,
        reversal=TechnicalReversalSignals(bias="BULLISH"),
    )
    assert s is None and diag == {}


def test_short_side_symmetry():
    # Bearish core (rsi 30, ema bearish) into support with bullish reversal = conflict.
    pure, _ = tf._direction_score(30.0, 0.0, "bearish")
    conflicted, _ = tf._direction_score(
        30.0, 0.0, "bearish",
        fib=FibonacciAnalysis(timeframe="1D", zone="near_support", validity="sane"),
        reversal=TechnicalReversalSignals(bias="BULLISH"),
    )
    # Shorting into support against a bullish reversal → conviction pulled toward 50.
    assert conflicted > pure  # bearish score rises toward neutral (less conviction)


# ── Faz 2: chop guard (trend kalitesi) ────────────────────────────────────────

_CHOP_ON = tf.TechnicalConfig(chop_guard_enabled=True)    # floor 20, min_mult 0.5
_CHOP_OFF = tf.TechnicalConfig(chop_guard_enabled=False)  # explicit OFF (global config'ten bağımsız)


def test_chop_guard_off_is_passthrough():
    # Explicit OFF cfg: düşük ADX bile final skoru DEĞİŞTİRMEZ (global flag ne olursa olsun).
    s, _ = tf._direction_score(_RSI, _MACD, _EMA, adx_v=5.0, cfg=_CHOP_OFF)
    assert s == tf._momentum_score(_RSI, _MACD, _EMA)


def test_chop_guard_shadow_logged_even_when_off():
    # Flag KAPALI olsa da chop'ta "ne olurdu" gözlem değeri diag'a yazılır
    # (öğrenme katmanı yön-motorunu izlemez → manuel tespit sinyali).
    s, diag = tf._direction_score(_RSI, _MACD, _EMA, adx_v=5.0, cfg=_CHOP_OFF)
    assert s == tf._momentum_score(_RSI, _MACD, _EMA)   # final DEĞİŞMEDİ
    assert "chop_mult_shadow" in diag                   # ama gözlem kaydedildi
    assert "chop_mult" not in diag                      # uygulanmadı


def test_chop_guard_dampens_in_chop():
    # Açık + ADX floor altı → skor 50'ye doğru kısılır (ama aynı tarafta kalır).
    pure = tf._momentum_score(_RSI, _MACD, _EMA)        # ≈65 (bullish)
    s, diag = tf._direction_score(_RSI, _MACD, _EMA, adx_v=5.0, cfg=_CHOP_ON)
    assert 50.0 < s < pure          # sönümlendi ama bullish kaldı (yön çevrilmedi)
    assert "chop_mult" in diag


def test_chop_guard_inert_in_trend():
    # Açık ama ADX floor üstü (gerçek trend) → dokunmaz.
    pure = tf._momentum_score(_RSI, _MACD, _EMA)
    s, diag = tf._direction_score(_RSI, _MACD, _EMA, adx_v=30.0, cfg=_CHOP_ON)
    assert s == pure and "chop_mult" not in diag


def test_chop_guard_never_flips_side():
    # Aşırı chop (adx≈0) bile bullish'i bearish yapmaz (yalnız sönümler).
    s, _ = tf._direction_score(_RSI, _MACD, _EMA, adx_v=0.0, cfg=_CHOP_ON)
    assert s > 50.0
    # Bearish çekirdek de aynı: aşağıda kalır, yukarı çevrilmez.
    sb, _ = tf._direction_score(30.0, 0.0, "bearish", adx_v=0.0, cfg=_CHOP_ON)
    assert sb < 50.0


# ── Faz 3a: exhaustion guard (climax kovalama) ────────────────────────────────

_EXH_ON = tf.TechnicalConfig(exhaustion_guard_enabled=True)   # high 70, low 30, min_mult 0.5


def test_exhaustion_dampens_chasing_top():
    # Bullish momentum + upside tükenmesi (exh 90) → tepeyi kovalıyor → sönümle.
    pure = tf._momentum_score(_RSI, _MACD, _EMA)              # ≈76 (bullish)
    s, diag = tf._direction_score(_RSI, _MACD, _EMA, exhaustion_score=90.0, cfg=_EXH_ON)
    assert 50.0 < s < pure
    assert "exh_mult" in diag


def test_exhaustion_dampens_chasing_bottom():
    # Bearish momentum + downside tükenmesi (exh 10) → dibi kovalıyor → sönümle.
    pure, _ = tf._direction_score(30.0, 0.0, "bearish")       # <50
    s, diag = tf._direction_score(30.0, 0.0, "bearish", exhaustion_score=10.0, cfg=_EXH_ON)
    assert pure < s < 50.0
    assert "exh_mult" in diag


def test_exhaustion_no_dampen_when_riding_reversal():
    # Bullish momentum + DOWNSIDE tükenmesi (exh 10, yukarı reversal) → momentum
    # reversal'ı sürüyor, kovalamıyor → DOKUNMAZ.
    pure = tf._momentum_score(_RSI, _MACD, _EMA)
    s, diag = tf._direction_score(_RSI, _MACD, _EMA, exhaustion_score=10.0, cfg=_EXH_ON)
    assert s == pure and "exh_mult_shadow" not in diag


def test_exhaustion_shadow_when_off():
    # OFF cfg + tepeyi kovalama → gözlem yazılır ama final DEĞİŞMEZ.
    s, diag = tf._direction_score(_RSI, _MACD, _EMA, exhaustion_score=90.0, cfg=_CHOP_OFF)
    assert s == tf._momentum_score(_RSI, _MACD, _EMA)
    assert "exh_mult_shadow" in diag and "exh_mult" not in diag


def test_exhaustion_never_flips_side():
    # Aşırı tükenme (exh 100) bile bullish'i bearish'e çevirmez.
    s, _ = tf._direction_score(_RSI, _MACD, _EMA, exhaustion_score=100.0, cfg=_EXH_ON)
    assert s > 50.0


# ── Faz 3b: reversion (mean-reversion — uçta yönü ÇEVİR) ──────────────────────

_REV_ON = tf.TechnicalConfig(reversion_enabled=True)   # rev_low 20, rev_high 80, mag 25


def test_reversion_long_on_oversold_with_bullish_reversal():
    # Bearish momentum + güçlü downside tükenmesi (exh 10) + BULLISH reversal teyidi
    # → yön LONG'a çevrilir (mean-reversion).
    s, diag = tf._direction_score(
        30.0, 0.0, "bearish", exhaustion_score=10.0,
        reversal=TechnicalReversalSignals(bias="BULLISH"), cfg=_REV_ON,
    )
    assert s > 50.0 and "reversion" in diag  # bearish iken long'a döndü


def test_reversion_short_on_overbought_with_bearish_reversal():
    # Bullish momentum + güçlü upside tükenmesi (exh 90) + BEARISH reversal → SHORT.
    s, diag = tf._direction_score(
        70.0, 0.0, "bullish", exhaustion_score=90.0,
        reversal=TechnicalReversalSignals(bias="BEARISH"), cfg=_REV_ON,
    )
    assert s < 50.0 and "reversion" in diag


def test_reversion_requires_reversal_confirmation():
    # Uç tükenme TEK BAŞINA yetmez — reversal NEUTRAL ise çevirme yok.
    s, diag = tf._direction_score(
        30.0, 0.0, "bearish", exhaustion_score=10.0,
        reversal=TechnicalReversalSignals(bias="NEUTRAL"), cfg=_REV_ON,
    )
    assert s < 50.0 and "reversion_shadow" not in diag  # bearish kaldı


def test_reversion_shadow_when_off():
    # OFF cfg: reversion_score gözlem yazılır ama final ÇEVRİLMEZ.
    s, diag = tf._direction_score(
        30.0, 0.0, "bearish", exhaustion_score=10.0,
        reversal=TechnicalReversalSignals(bias="BULLISH"), cfg=_CHOP_OFF,
    )
    assert s < 50.0  # hâlâ bearish (çevrilmedi)
    assert "reversion_shadow" in diag and "reversion" not in diag


def test_reversion_skipped_when_momentum_already_aligned():
    # Momentum zaten bullish + downside tükenmesi + bullish reversal → çevirecek bir
    # şey yok (final<50 şartı sağlanmaz) → reversion tetiklenmez.
    s, diag = tf._direction_score(
        70.0, 0.0, "bullish", exhaustion_score=10.0,
        reversal=TechnicalReversalSignals(bias="BULLISH"), cfg=_REV_ON,
    )
    assert s > 50.0 and "reversion_shadow" not in diag


# ── Faz 4: trend/range market_regime (model anahtarı) ─────────────────────────

_CFG = tf.TechnicalConfig()  # adx_trend_min=20


def test_market_regime_classifier():
    assert tf._market_regime(30.0, "TRENDING", _CFG) == "TREND"
    assert tf._market_regime(10.0, "RANGING", _CFG) == "RANGE"
    assert tf._market_regime(10.0, "SQUEEZE", _CFG) == "RANGE"
    assert tf._market_regime(None, "EXPANSION", _CFG) == "TRANSITION"
    assert tf._market_regime(None, "UNKNOWN", _CFG) == "UNKNOWN"
    assert tf._market_regime(25.0, "RANGING", _CFG) == "TREND"  # adx≥20 → trend baskın


def test_reversion_suppressed_in_trend_regime():
    # Reversion setup'ı tam (bearish + exh 10 + bullish reversal) AMA rejim TREND →
    # trende karşı dönüş AÇMA: reversion tetiklenmez.
    s, diag = tf._direction_score(
        30.0, 0.0, "bearish", exhaustion_score=10.0,
        reversal=TechnicalReversalSignals(bias="BULLISH"),
        market_regime="TREND", cfg=_REV_ON,
    )
    assert s < 50.0 and "reversion_shadow" not in diag  # bastırıldı


def test_reversion_allowed_in_range_regime():
    # Aynı setup + rejim RANGE → mean-reversion modeli geçerli → çevirir.
    s, diag = tf._direction_score(
        30.0, 0.0, "bearish", exhaustion_score=10.0,
        reversal=TechnicalReversalSignals(bias="BULLISH"),
        market_regime="RANGE", cfg=_REV_ON,
    )
    assert s > 50.0 and "reversion" in diag
