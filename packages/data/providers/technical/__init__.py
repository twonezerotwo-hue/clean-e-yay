"""Teknik analiz sağlayıcısı — mock-first, deterministik."""
from __future__ import annotations

import hashlib
import time

from packages.data.types import TIMEFRAMES, TechnicalSnapshot


def _det(symbol: str, salt: str, lo: float, hi: float) -> float:
    h = int(hashlib.sha1(f"{symbol}|{salt}".encode()).hexdigest()[:8], 16)
    return lo + (h % 10_000) / 10_000 * (hi - lo)


def get_snapshot(symbol: str, timeframe: str = "1d") -> TechnicalSnapshot:
    t = time.time() // 300  # 5 dakikalık deterministik blok
    rsi = _det(symbol, f"rsi-{timeframe}-{t}", 30, 70)
    macd = _det(symbol, f"macd-{timeframe}-{t}", -1.5, 1.5)
    atr = _det(symbol, f"atr-{timeframe}-{t}", 0.5, 3.0)
    ema_h = _det(symbol, f"ema-{timeframe}-{t}", 0, 1)
    stack = "bullish" if ema_h > 0.6 else "bearish" if ema_h < 0.4 else "mixed"
    score = max(0.0, min(100.0, 50.0 + (rsi - 50) * 0.6 + macd * 5))
    # T0: geçerli tüm timeframe'ler passthrough; bilinmeyen → "1d"
    tf_lit: str = timeframe if timeframe in TIMEFRAMES else "1d"
    return TechnicalSnapshot(
        symbol=symbol,
        timeframe=tf_lit,  # type: ignore[arg-type]
        rsi=round(rsi, 2),
        macd=round(macd, 3),
        atr=round(atr, 3),
        ema_stack=stack,  # type: ignore[arg-type]
        score=round(score, 2),
    )
