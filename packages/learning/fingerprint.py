"""Sinyal fingerprint'i — `asset|regime|direction|score_bucket|dominant_module`."""
from __future__ import annotations


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
) -> str:
    return "|".join(
        [
            symbol,
            regime,
            direction,
            bucket(score),
            "C" if confluence else "X",
            dominant_module or "?",
        ]
    )
