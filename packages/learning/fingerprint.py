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


def parse(fingerprint: str | None) -> dict[str, str | None]:
    """Fingerprint'i bileşenlerine ayır (v2 + legacy + malformed-safe).

    v2     (8 parça): ``asset|v2|tf|regime|direction|score_bucket|confluence|module``
    legacy (6 parça): ``asset|regime|direction|score_bucket|confluence|module``

    Tanınmayan/malformed fingerprint → tüm alanlar None (crash yok).
    """
    out: dict[str, str | None] = {
        "symbol": None,
        "version": None,
        "timeframe": None,
        "regime": None,
        "direction": None,
        "score_bucket": None,
        "confluence": None,
        "dominant_module": None,
    }
    if not fingerprint:
        return out
    parts = fingerprint.split("|")
    if is_v2(fingerprint) and len(parts) >= 8:
        out.update(
            symbol=parts[0],
            version="v2",
            timeframe=parts[2],
            regime=parts[3],
            direction=parts[4],
            score_bucket=parts[5],
            confluence=parts[6],
            dominant_module=parts[7],
        )
    elif not is_v2(fingerprint) and len(parts) >= 6:
        out.update(
            symbol=parts[0],
            version="legacy",
            regime=parts[1],
            direction=parts[2],
            score_bucket=parts[3],
            confluence=parts[4],
            dominant_module=parts[5],
        )
    return out


def dominant_module(fingerprint: str | None) -> str | None:
    """v2 (parts[7]) ve legacy (parts[5]) fingerprint'ten dominant module.

    Eski koddaki ``parts[5]`` her zaman → v2'de score_bucket'ı module sanıyordu.
    Bu helper v2/legacy/malformed'ı ayırır.
    """
    return parse(fingerprint)["dominant_module"]
