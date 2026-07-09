"""SMC setup sekans dedektörü — owner yapısal sistemi (EVIDENCE only, salt-gözlem).

Owner'ın ana giriş mantığını (2026-07-09) TEK sekansa dizer — mevcut yapısal
primitifleri (market_structure BOS/CHoCH + liquidity_sweep) birleştirir ve
EKSİK olan iki parçayı ekler: **retest dedektörü** + **sekans state-machine**.

Owner LONG sekansı:
    düşüşle likidite alınır (sweep REVERSAL_LONG)
      → CHoCH (yukarı karakter değişimi)
      → BOS (yukarı yapı kırılımı)
      → kırılan seviye RETEST edilir
      → LONG hazır · stop son dip altı · hedef önceki tepe
SHORT sekansı ayna.

Aşamalar sırayla sayılır (state-machine): NONE < SWEPT < CHOCH < BOS < RETEST
< READY. Her aşama bir öncekini gerektirir (owner'ın sırası birebir).

KURALLAR: saf fonksiyon, look-ahead yok, uydurma seviye yok (yetersiz → NONE).
Canlı skora/karara BAĞLI DEĞİL — ölçüm/karne tüketir, sonra kanıtla + owner
onayıyla yapısal beyne (touche revizyonu) girer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from packages.data.types import OHLCVBar
from packages.liquidity import sweep as liquidity_sweep
from packages.signals import market_structure

# Sekans aşamaları (owner sırası). Sayısal → "ne kadar ilerledi" kıyaslanır.
STAGE_NONE = "NONE"
STAGE_SWEPT = "SWEPT"       # likidite alındı
STAGE_CHOCH = "CHOCH"       # + karakter değişimi
STAGE_BOS = "BOS"           # + yapı kırılımı
STAGE_RETEST = "RETEST"     # + kırılan seviye test edildi
STAGE_READY = "READY"       # tam sekans → giriş aranır
_ORDER = {STAGE_NONE: 0, STAGE_SWEPT: 1, STAGE_CHOCH: 2, STAGE_BOS: 3,
          STAGE_RETEST: 4, STAGE_READY: 5}

_RETEST_TOL = 0.004   # kırılan seviyeye "değme" toleransı (±%0.4)
_RETEST_LOOKBACK = 8  # retest'i son kaç barda ara
_MIN_BARS = 24


@dataclass(frozen=True)
class SetupSignal:
    direction: str            # long | short | none
    stage: str                # NONE..READY
    ready: bool               # tam sekans tamam mı
    swept: bool
    choch: bool
    bos: bool
    retested: bool
    entry: float | None = None        # tetik barı kapanışı
    stop: float | None = None         # yapısal invalidasyon (son dip/tepe)
    broken_level: float | None = None  # retest edilen seviye
    reasons: list[str] = field(default_factory=list)


def _empty(reason: str) -> SetupSignal:
    return SetupSignal(direction="none", stage=STAGE_NONE, ready=False,
                       swept=False, choch=False, bos=False, retested=False,
                       reasons=[reason])


def _retest_ok(bars: list[OHLCVBar], level: float, *, long: bool) -> bool:
    """Kırılan seviye retest edildi mi: son barlardan biri seviyeye DEĞDİ
    (tolerans içinde) VE güncel kapanış kırılım yönünde tutundu."""
    if level <= 0:
        return False
    lo_band, hi_band = level * (1 - _RETEST_TOL), level * (1 + _RETEST_TOL)
    touched = any(
        b.low <= hi_band and b.high >= lo_band
        for b in bars[-_RETEST_LOOKBACK:]
    )
    held = bars[-1].close > level if long else bars[-1].close < level
    return touched and held


def detect(
    bars: list[OHLCVBar],
    *,
    timeframe: str = "4h",
    structure: market_structure.MarketStructure | None = None,
    sweep=None,
) -> SetupSignal:
    """Owner setup sekansını değerlendir → SetupSignal. Yetersiz veri → none."""
    if len(bars) < _MIN_BARS:
        return _empty("insufficient_bars")
    ms = structure if structure is not None else market_structure.analyze(bars)
    if ms is None:
        return _empty("no_structure")
    if sweep is None:
        try:
            sweep = liquidity_sweep.analyze(bars, timeframe=timeframe)
        except Exception:
            sweep = None

    # Yön adayı: CHoCH (dönüş, en güçlü) > BOS > trend.
    if ms.choch == "bullish" or ms.bos == "bullish":
        direction, long = "long", True
    elif ms.choch == "bearish" or ms.bos == "bearish":
        direction, long = "short", False
    else:
        return _empty(f"no_directional_break ({ms.trend.lower()})")

    reasons: list[str] = [f"structure={ms.trend} choch={ms.choch} bos={ms.bos}"]

    # 1) Likidite alındı mı (yön uyumlu sweep).
    want = "REVERSAL_LONG" if long else "REVERSAL_SHORT"
    swept = sweep is not None and getattr(sweep, "bias", "unknown") == want \
        and getattr(sweep, "validity", "unavailable") != "unavailable"
    if swept:
        reasons.append(f"likidite alındı ({want})")

    # 2/3) CHoCH ve BOS (yön uyumlu).
    choch = ms.choch == ("bullish" if long else "bearish")
    bos = ms.bos == ("bullish" if long else "bearish")
    if choch:
        reasons.append("CHoCH teyidi")
    if bos:
        reasons.append("BOS teyidi")

    # 4) Retest: kırılan seviye = long'da son tepe (kırılan direnç), short'ta son dip.
    broken = ms.last_high if long else ms.last_low
    retested = _retest_ok(bars, broken, long=long) if broken else False
    if retested:
        reasons.append(f"retest {broken:.6g}")

    # Aşama: her biri bir öncekini gerektirir (owner sırası).
    stage = STAGE_NONE
    if swept:
        stage = STAGE_SWEPT
        if choch:
            stage = STAGE_CHOCH
            if bos:
                stage = STAGE_BOS
                if retested:
                    stage = STAGE_READY
    ready = stage == STAGE_READY

    entry = bars[-1].close
    stop = ms.last_low if long else ms.last_high
    return SetupSignal(
        direction=direction, stage=stage, ready=ready,
        swept=swept, choch=choch, bos=bos, retested=retested,
        entry=round(entry, 8),
        stop=round(stop, 8) if stop else None,
        broken_level=round(broken, 8) if broken else None,
        reasons=reasons,
    )


def stage_rank(stage: str) -> int:
    """Aşama sıra numarası (kıyas/karne için)."""
    return _ORDER.get(stage, 0)


__all__ = [
    "STAGE_BOS", "STAGE_CHOCH", "STAGE_NONE", "STAGE_READY",
    "STAGE_RETEST", "STAGE_SWEPT", "SetupSignal", "detect", "stage_rank",
]
