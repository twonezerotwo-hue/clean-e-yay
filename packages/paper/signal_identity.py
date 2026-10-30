"""Canonical identity for one paper signal.

The identity is deterministic and deliberately independent from wall-clock time.
It links the technical decision, the matching news setup, the ticket,
notification and paper position without changing any decision authority.
"""
from __future__ import annotations

import hashlib


def build_signal_id(
    *,
    symbol: str,
    timeframe: str,
    side: str,
    fingerprint: str | None = None,
    decision_id: str | None = None,
    news_setup_id: str | None = None,
    news_event_id: str | None = None,
) -> str:
    """Return a stable, privacy-safe identity for one evidence-backed signal."""
    raw = "|".join(
        str(value or "")
        for value in (
            str(symbol or "").upper(),
            str(timeframe or ""),
            str(side or "").lower(),
            fingerprint,
            decision_id,
            news_setup_id,
            news_event_id,
        )
    )
    return "sig_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_audit_id(
    snapshot_id: str | None,
    decision_id: str | None,
    signal_id: str | None,
) -> str | None:
    """Karar → açılış → kapanış → öğrenme kaydını tek anahtarla bağlar.

    Saklanan yeni bir alan değildir: pozisyon ve işlemin zaten taşıdığı üç
    kimlikten türetilir, böylece eski kayıtlar için de aynı değer hesaplanır.
    Üçü de yoksa None.
    """
    if not (snapshot_id or decision_id or signal_id):
        return None
    raw = "|".join(str(value or "") for value in (snapshot_id, decision_id, signal_id))
    return "aud_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_evidence_id(
    *, event_id: str, source_id: str, asset: str, direction: str | None,
    timeframe: str, decision_id: str | None = None,
) -> str:
    """Stable shared identity for a news/macro/technical evidence row."""
    raw = "|".join(str(value or "") for value in (
        event_id, source_id, str(asset or "").upper(), direction, timeframe, decision_id,
    ))
    return "ev_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


__all__ = ["build_evidence_id", "build_signal_id"]
