"""Explicit, bounded paper-only exploration policy.

The normal decision gates remain authoritative.  In an explicitly configured
``PAPER_ONLY`` + ``NO_EXECUTION`` process, this policy may let a candidate that
was stopped only by the confidence/EV *soft* gates reach the existing guarded
paper opener at a capped size.  Risk, stale-data, session, price-sanity,
duplicate and position-cap checks remain hard gates.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from packages.data.registry.loader import load_thresholds

_TRUE = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class PaperAutoOpenConfig:
    enabled: bool = False
    min_confidence: float = 0.20
    max_negative_ev: float = -0.40
    max_size_multiplier: float = 0.35


def load_config() -> PaperAutoOpenConfig:
    raw = (load_thresholds().get("paper_trading") or {}).get("paper_auto_open") or {}
    try:
        min_confidence = min(1.0, max(0.0, float(raw.get("min_confidence", 0.20))))
    except (TypeError, ValueError):
        min_confidence = 0.20
    try:
        max_negative_ev = min(0.0, float(raw.get("max_negative_ev", -0.40)))
    except (TypeError, ValueError):
        max_negative_ev = -0.40
    try:
        max_size = min(1.0, max(0.05, float(raw.get("max_size_multiplier", 0.35))))
    except (TypeError, ValueError):
        max_size = 0.35
    return PaperAutoOpenConfig(
        enabled=bool(raw.get("enabled", False)),
        min_confidence=min_confidence,
        max_negative_ev=max_negative_ev,
        max_size_multiplier=max_size,
    )


def environment_allows() -> bool:
    """Do not let a future live process inherit paper exploration accidentally."""
    return (
        os.environ.get("PAPER_ONLY", "").strip().lower() in _TRUE
        and os.environ.get("NO_EXECUTION", "").strip().lower() in _TRUE
    )


def enabled() -> bool:
    cfg = load_config()
    return cfg.enabled and environment_allows()


def allows_confidence(confidence: float, cfg: PaperAutoOpenConfig | None = None) -> bool:
    cfg = cfg or load_config()
    return float(confidence) >= cfg.min_confidence


def allows_expected_value(expected_value: float | None, cfg: PaperAutoOpenConfig | None = None) -> bool:
    cfg = cfg or load_config()
    return expected_value is not None and float(expected_value) >= cfg.max_negative_ev


def cap_size(size_multiplier: float, cfg: PaperAutoOpenConfig | None = None) -> float:
    cfg = cfg or load_config()
    return round(max(0.0, min(float(size_multiplier), cfg.max_size_multiplier)), 3)


__all__ = [
    "PaperAutoOpenConfig",
    "allows_confidence",
    "allows_expected_value",
    "cap_size",
    "enabled",
    "environment_allows",
    "load_config",
]
