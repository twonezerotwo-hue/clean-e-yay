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
            news_setup_id,
            news_event_id,
        )
    )
    return "sig_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


__all__ = ["build_signal_id"]
