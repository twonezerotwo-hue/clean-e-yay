"""Sermaye rotasyonu sağlayıcısı — mock-first."""
from __future__ import annotations

import hashlib
import time

from packages.data.types import RotationView


def _det(salt: str, lo: float, hi: float) -> float:
    h = int(hashlib.sha1(salt.encode()).hexdigest()[:8], 16)
    return lo + (h % 10_000) / 10_000 * (hi - lo)


def get_rotation() -> RotationView:
    block = int(time.time() // 600)
    score = _det(f"rotation-{block}", 35, 75)
    direction = "bullish" if score > 55 else "bearish" if score < 45 else "neutral"
    evidence = [
        f"BTC/GLD oranı {'yukarı' if score > 50 else 'aşağı'}",
        f"HYG/LQD spread {'daralıyor' if score > 50 else 'genişliyor'}",
        f"30g korelasyon yapısı {'risk-on' if score > 50 else 'risk-off'}",
    ]
    return RotationView(
        score=round(score, 1),
        direction=direction,  # type: ignore[arg-type]
        evidence=evidence,
    )
