"""Giriş bağlamı — bir (sembol, TF) için YÖN-BAĞIMSIZ fiyat konumu / uzama özellikleri.

Yön skoru "hangi yön tercih ediliyor"u söyler; bu modül yalnız "fiyat şu an nerede,
ne kadar uzamış, yakın zamanda hangi dönüş olayları oldu"yu ölçer. Kararı ``entry_quality``
verir (saf, YALNIZ kısıtlayıcı). Burada karar YOK.

Çıktı JSON-uyumlu bir sözlüktür (snapshot'a gömülür, tekrar oynatılabilir). Tüm özellikler
yalnızca çağıranın verdiği barlardan, SON bara kadar hesaplanır — look-ahead yok.
Eksik veri (hacim yok, bar yetersiz) → ilgili alan ``None`` / yok; uydurma değer yok.
"""
from __future__ import annotations

from packages.data.providers.technical import indicators
from packages.data.types import OHLCVBar
from packages.scoring import reversal_events

CONTEXT_VERSION = 1
MIN_BARS = 60
_WINDOW = 300                    # EMA50/ATR/BB için yeterli, maliyet sınırlı
RANGE_WINDOWS = (20, 60, 120)    # aralık konumu pencereleri (bar)
_VWAP_BARS = 20
_RUN_BODY_ATR = 0.6              # "impulsive" mum: gövde ≥ 0.6 ATR


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(x, nd)


def _range_pos(bars: list[OHLCVBar], n: int) -> float | None:
    if len(bars) < n:
        return None
    win = bars[-n:]
    lo = min(b.low for b in win)
    hi = max(b.high for b in win)
    if hi <= lo:
        return 0.5
    return (bars[-1].close - lo) / (hi - lo)


def _run(bars: list[OHLCVBar], atr: float) -> tuple[int, int]:
    """Son barlardan geriye ardışık 'impulsive' aynı-yön mum sayısı ve yönü
    (+1 yukarı, −1 aşağı, 0 yok)."""
    if atr <= 0:
        return 0, 0
    direction = 0
    n = 0
    for b in reversed(bars[-12:]):
        body = (b.close - b.open) / atr
        d = 1 if body >= _RUN_BODY_ATR else (-1 if body <= -_RUN_BODY_ATR else 0)
        if d == 0:
            break
        if direction == 0:
            direction = d
        elif d != direction:
            break
        n += 1
    return direction, n


def build(bars: list[OHLCVBar], timeframe: str) -> dict | None:
    """Son kapanışa göre giriş bağlamı. Yetersiz veri (<``MIN_BARS``) → None."""
    if not bars or len(bars) < MIN_BARS:
        return None
    win = bars[-_WINDOW:]
    closes = [b.close for b in win]
    px = closes[-1]
    atr = indicators.atr(win)
    if atr is None or atr <= 0 or px <= 0:
        return None

    ctx: dict = {
        "v": CONTEXT_VERSION,
        "tf": timeframe,
        "n": len(win),
        "atr_pct": _r(atr / px * 100.0),
        "range_pos": {str(n): _r(_range_pos(win, n)) for n in RANGE_WINDOWS if len(win) >= n},
    }
    e20 = indicators.ema(closes, 20)
    e50 = indicators.ema(closes, 50)
    ctx["ext_ema20"] = _r((px - e20) / atr) if e20 is not None else None
    ctx["ext_ema50"] = _r((px - e50) / atr) if e50 is not None else None
    vw = indicators.vwap(win[-_VWAP_BARS:])   # hacim yoksa None (FX/altın CFD)
    ctx["ext_vwap"] = _r((px - vw) / atr) if vw is not None else None
    ctx["rsi"] = _r(indicators.rsi(closes), 2)

    last20 = closes[-20:]
    mean = sum(last20) / 20.0
    sd = (sum((c - mean) ** 2 for c in last20) / 20.0) ** 0.5
    ctx["bb_pctb"] = _r((px - (mean - 2 * sd)) / (4 * sd)) if sd > 0 else None

    ctx["move5_atr"] = _r((px - closes[-6]) / atr) if len(closes) >= 6 else None
    # Son barın yapısı (bilgi alanları: tanılama + climax olayı aynı tanımı kullanır).
    last = win[-1]
    ctx["body_atr"] = _r((last.close - last.open) / atr)
    ctx["range_atr"] = _r((last.high - last.low) / atr)
    ctx["atr_ratio"] = _r(reversal_events.atr_expansion(win))
    ctx["vol_ratio"] = _r(reversal_events.volume_ratio(win, len(win) - 1))
    run_dir, run_len = _run(win, atr)
    ctx["run_dir"] = run_dir
    ctx["run_len"] = run_len

    events, pullback = reversal_events.detect(win)
    ctx["events"] = [e.to_dict() for e in events]
    ctx["pullback"] = pullback
    return ctx


__all__ = ["CONTEXT_VERSION", "MIN_BARS", "RANGE_WINDOWS", "build"]
