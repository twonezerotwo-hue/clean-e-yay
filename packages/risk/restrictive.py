"""Kısıtlayıcı alt risk kapılarının ortak iskeleti (vadeli, oynaklık, opsiyon, katalizör).

Seviyeler yalnız kısıtlar: NONE ve WATCH boyutu değiştirmez, CAUTION ×0.5,
NO_POSITION_INCREASE yeni pozisyonu durdurur. Zaman dilimi ağırlığı etkiyi yumuşatır,
asla artırmaz. Dört modül bu iskeleti ayrı ayrı kopyalıyordu (21 Kasım 2026, revizyon
grubu 2 F5); her modül artık yalnız kendi eşlemesini tutar.

PAPER_SAFE / NO_EXECUTION — yalnızca gözlem + kısıtlama.
"""
from __future__ import annotations

import dataclasses
from typing import Literal

from packages.data.registry.loader import load_thresholds

Level = Literal["NONE", "WATCH", "CAUTION", "NO_POSITION_INCREASE"]

LEVEL_RANK: dict[Level, int] = {
    "NONE": 0,
    "WATCH": 1,
    "CAUTION": 2,
    "NO_POSITION_INCREASE": 3,
}

LEVEL_SIZE_FACTOR: dict[Level, float] = {
    "NONE": 1.0,
    "WATCH": 1.0,
    "CAUTION": 0.5,
    "NO_POSITION_INCREASE": 0.0,
}

# Bu ağırlığın altındaki timeframe'lerde NO_POSITION_INCREASE block'a dönmez,
# CAUTION'a düşürülür (düşük ağırlıklı TF'ler hard-block edilmez).
BLOCK_WEIGHT_MIN = 0.75

_BASE_FIELDS = {"level", "size_factor", "block", "reason", "evidence"}


def timeframe_weight(section: str, timeframe: str) -> float:
    """`thresholds.<section>.timeframe_weight[timeframe]` ∈ [0, 1]; yoksa 1.0."""
    cfg = (load_thresholds().get(section) or {}).get("timeframe_weight") or {}
    try:
        return max(0.0, min(1.0, float(cfg.get(timeframe, 1.0))))
    except (TypeError, ValueError):
        return 1.0


def apply_timeframe(verdict, weight: float, off_reason: str):
    """Timeframe ağırlığını uygula. weight=1.0 tam etki; 0.0 etki yok.

    Düşük ağırlıkta NO_POSITION_INCREASE block'a DÖNMEZ — etki yumuşatılır
    (size_factor 1.0'a doğru çekilir). Asla artırmaz. Verdict sınıfının ek alanları
    (ör. opsiyon rejimi) korunur."""
    if verdict.level == "NONE":
        return verdict
    w = max(0.0, min(1.0, weight))
    if w == 0.0:
        extra = {f.name: getattr(verdict, f.name) for f in dataclasses.fields(verdict)
                 if f.name not in _BASE_FIELDS}
        return type(verdict)(reason=off_reason, **extra)
    eff_size = max(0.0, min(1.0, 1.0 - (1.0 - verdict.size_factor) * w))
    block = verdict.block and w >= BLOCK_WEIGHT_MIN
    eff_level = "CAUTION" if verdict.block and not block else verdict.level
    return dataclasses.replace(
        verdict,
        level=eff_level,
        size_factor=eff_size,
        block=block,
        reason=verdict.reason + (f" (tf×{w:g})" if w < 1.0 else ""),
        evidence=list(verdict.evidence),
    )
