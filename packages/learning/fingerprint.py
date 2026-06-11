"""Sinyal fingerprint'i.

v2 (T0+): `asset|v2|timeframe|regime|direction|score_bucket|confluence|module`
legacy:    `asset|regime|direction|score_bucket|confluence|module`

v2 her zaman `v2` segmenti taşır → legacy kayıtlarla **asla çakışmaz**.
Eski (TF'siz) kayıtlar yeni fingerprint'lerle eşleşmez; mistake memory
MIN_TRADES altında NEUTRAL fallback verdiği için doğal karantinaya düşer.
"""
from __future__ import annotations

VERSION_TAG = "v2"


def bucket(score: float) -> str:
    if score >= 80:
        return "S80"
    if score >= 65:
        return "S65"
    if score >= 55:
        return "S55"
    if score <= 20:
        return "S20"
    if score <= 35:
        return "S35"
    if score <= 45:
        return "S45"
    return "S50"


def make(
    *,
    symbol: str,
    regime: str,
    direction: str,
    score: float,
    confluence: bool,
    dominant_module: str,
    timeframe: str = "1d",
) -> str:
    return "|".join(
        [
            symbol,
            VERSION_TAG,
            timeframe,
            regime,
            direction,
            bucket(score),
            "C" if confluence else "X",
            dominant_module or "?",
        ]
    )


def is_v2(fingerprint: str | None) -> bool:
    """v2 fingerprint mi? Legacy kayıtları ayırt etmek için."""
    if not fingerprint:
        return False
    parts = fingerprint.split("|")
    return len(parts) >= 3 and parts[1] == VERSION_TAG
