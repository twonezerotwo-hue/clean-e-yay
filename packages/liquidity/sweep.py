"""Liquidity Sweep Engine — top-level `analyze()` (EVIDENCE only, spec §13).

Belirlenmiş bir aralığın (lookback penceresinin "kurulu" kısmı) swing high/
low'unu son K bar içinde delip (sweep) sonra geri içine dönen (reclaim)
fiyat hareketini tespit eder — klasik "stop hunt / liquidity grab" yapısı.
`fibonacci.py`/`zones/engine.py` ile aynı desen: pure fonksiyon, validity/
diagnostics, uydurma seviye yok. `packages/liquidity/rotation.py`'a
dokunmaz — o modülün yanına eklenen bağımsız bir dosyadır.

Hiçbir karar zincirine bağlı DEĞİLDİR — additive read surface.
"""
from __future__ import annotations

from packages.data.registry.loader import load_thresholds
from packages.data.types import LiquiditySweepAnalysis, OHLCVBar

_DEFAULT_LOOKBACK_BARS = 40
_DEFAULT_RECENT_BARS = 5  # sweep/reclaim aranacak "son K bar" penceresi
_DEFAULT_MIN_BARS = 15


def _cfg() -> dict:
    try:
        return load_thresholds().get("liquidity_sweep") or {}
    except (OSError, KeyError, ValueError):
        return {}


def _config() -> dict:
    c = _cfg()
    return {
        "lookback_bars": int(c.get("lookback_bars", _DEFAULT_LOOKBACK_BARS)),
        "recent_bars": int(c.get("recent_bars", _DEFAULT_RECENT_BARS)),
        "min_bars": int(c.get("min_bars", _DEFAULT_MIN_BARS)),
    }


def analyze(bars: list[OHLCVBar], *, timeframe: str) -> LiquiditySweepAnalysis:
    cfg = _config()
    diag: list[str] = []

    if not bars or len(bars) < cfg["min_bars"]:
        diag.append(f"insufficient_bars:{len(bars) if bars else 0}")
        return LiquiditySweepAnalysis(timeframe=timeframe, validity="unavailable", diagnostics=diag)

    window = bars[-cfg["lookback_bars"] :]
    recent_n = min(cfg["recent_bars"], len(window) - 1)
    if recent_n < 1:
        diag.append("insufficient_recent_window")
        return LiquiditySweepAnalysis(timeframe=timeframe, validity="weak", diagnostics=diag)

    established = window[:-recent_n]
    recent = window[-recent_n:]
    if not established:
        diag.append("no_established_range")
        return LiquiditySweepAnalysis(timeframe=timeframe, validity="weak", diagnostics=diag)

    swing_high = max(b.high for b in established)
    swing_low = min(b.low for b in established)

    # Low sweep: recent bir bar swing_low'un altına indi mi? Sonra close geri üstüne döndü mü?
    low_swept_bars = [b for b in recent if b.low < swing_low]
    low_sweep_price = min((b.low for b in low_swept_bars), default=None)
    low_reclaimed = bool(low_swept_bars) and recent[-1].close > swing_low

    # High sweep: recent bir bar swing_high'ın üstüne çıktı mı? Sonra close geri altına döndü mü?
    high_swept_bars = [b for b in recent if b.high > swing_high]
    high_sweep_price = max((b.high for b in high_swept_bars), default=None)
    high_reclaimed = bool(high_swept_bars) and recent[-1].close < swing_high

    if low_swept_bars and low_reclaimed:
        state = "LOW_SWEEP_RECLAIMED"
        bias = "REVERSAL_LONG"
        sweep_price, reclaim_price = low_sweep_price, recent[-1].close
    elif high_swept_bars and high_reclaimed:
        state = "HIGH_SWEEP_RECLAIMED"
        bias = "REVERSAL_SHORT"
        sweep_price, reclaim_price = high_sweep_price, recent[-1].close
    elif low_swept_bars:
        state = "LOW_SWEEP_PENDING"
        bias = "unknown"
        sweep_price, reclaim_price = low_sweep_price, None
    elif high_swept_bars:
        state = "HIGH_SWEEP_PENDING"
        bias = "unknown"
        sweep_price, reclaim_price = high_sweep_price, None
    else:
        state = "NO_SWEEP"
        bias = "unknown"
        sweep_price, reclaim_price = None, None

    return LiquiditySweepAnalysis(
        timeframe=timeframe,
        state=state,  # type: ignore[arg-type]
        swing_high=round(swing_high, 6),
        swing_low=round(swing_low, 6),
        sweep_price=round(sweep_price, 6) if sweep_price is not None else None,
        reclaim_price=round(reclaim_price, 6) if reclaim_price is not None else None,
        bias=bias,  # type: ignore[arg-type]
        validity="sane",
        diagnostics=diag,
    )


__all__ = ["analyze"]
