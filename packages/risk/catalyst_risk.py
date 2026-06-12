"""Catalyst riski — yalnızca KISITLAYICI haber-catalyst gate'i (v2.7 D5).

Yaklaşan/taze, doğrulanmış (verified) yüksek etkili haber catalyst'leri (CPI,
FOMC, ateşkes, eskalasyon, exchange outage, …) etkilenen (symbol, timeframe)
hücrelerinde yeni pozisyon açılışını kısar. Bu modül:

- ASLA size artırmaz (size_factor ≤ 1.0).
- ASLA RiskGate / DQS / KillSwitch / halt gate'lerini gevşetmez/bypass etmez —
  decision engine'de RiskGate hard gate'lerinden SONRA, yalnızca küçültücü olarak
  uygulanır.
- Yalnızca `verified=True` + yarı-ömrü dolmamış (`now ≤ valid_until`) impact'leri
  sayar. **Rumor** (`verified=False`) ve fixture impact'ler karar zincirine
  GİRMEZ (yalnızca dashboard bağlamı).
- Yön bağımsızdır: catalyst belirsizliği her yönde risklidir (bias yalnızca
  bağlamdır, asla size artırmaya kullanılmaz).

Taksonomi (yalnızca kısıtlayıcı):
  NONE / CONTEXT_ONLY   → etki yok (boost yok)
  WATCH                 → bağlam uyarısı (size değişmez)
  CAUTION               → size ×0.5
  NO_POSITION_INCREASE  → yeni pozisyon açılışı durur (block)

PAPER_SAFE / NO_EXECUTION — yalnızca gözlem + kısıtlama.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from packages.data.types import CatalystActionability, CatalystImpact, utcnow

CatalystRiskLevel = Literal["NONE", "WATCH", "CAUTION", "NO_POSITION_INCREASE"]

# CONTEXT_ONLY → gate'te NONE (yalnızca bağlam, karar zincirine girmez).
_ACTION_TO_LEVEL: dict[CatalystActionability, CatalystRiskLevel] = {
    "CONTEXT_ONLY": "NONE",
    "WATCH": "WATCH",
    "CAUTION": "CAUTION",
    "NO_POSITION_INCREASE": "NO_POSITION_INCREASE",
}

_LEVEL_RANK: dict[CatalystRiskLevel, int] = {
    "NONE": 0,
    "WATCH": 1,
    "CAUTION": 2,
    "NO_POSITION_INCREASE": 3,
}

_LEVEL_SIZE_FACTOR: dict[CatalystRiskLevel, float] = {
    "NONE": 1.0,
    "WATCH": 1.0,
    "CAUTION": 0.5,
    "NO_POSITION_INCREASE": 0.0,
}


@dataclass
class CatalystVerdict:
    level: CatalystRiskLevel = "NONE"
    size_factor: float = 1.0      # ≤ 1.0 — asla artırmaz
    block: bool = False           # True → yeni pozisyon açılışı durur
    reason: str = "Aktif catalyst riski yok."
    evidence: list[str] = field(default_factory=list)
    event_type: str | None = None


def _is_active(imp: CatalystImpact, *, symbol: str, timeframe: str, now: datetime) -> bool:
    """Impact bu (symbol, timeframe) hücresini şu an kısıtlıyor mu?

    Yalnızca: verified + symbol etkilenen + timeframe etkilenen + yarı-ömrü
    dolmamış (valid_until geçmemiş) + actionability gerçekten kısıtlayıcı."""
    if not imp.verified:
        return False
    if symbol not in imp.affected_assets:
        return False
    if timeframe not in imp.affected_timeframes:
        return False
    if imp.valid_until is not None and now > imp.valid_until:
        return False
    return _ACTION_TO_LEVEL.get(imp.actionability, "NONE") != "NONE"


def assess(
    impacts: list[CatalystImpact] | None,
    symbol: str,
    timeframe: str,
    *,
    now: datetime | None = None,
) -> CatalystVerdict:
    """Bu (symbol, timeframe) için en kısıtlayıcı aktif catalyst verdict'i.

    Boş/etkisiz → NONE (size_factor 1.0). Yön bağımsızdır."""
    ref = now or utcnow()
    active = [
        imp
        for imp in (impacts or [])
        if _is_active(imp, symbol=symbol, timeframe=timeframe, now=ref)
    ]
    if not active:
        return CatalystVerdict()

    # En kısıtlayıcı seviye belirleyicidir.
    def lvl(imp: CatalystImpact) -> CatalystRiskLevel:
        return _ACTION_TO_LEVEL[imp.actionability]

    lead = max(active, key=lambda imp: _LEVEL_RANK[lvl(imp)])
    level = lvl(lead)
    evidence = [
        f"{imp.event_type} ({imp.actionability})"
        + (f" · surprise {imp.surprise_level:+.2f}" if imp.surprise_level else "")
        for imp in sorted(active, key=lambda imp: -_LEVEL_RANK[lvl(imp)])[:4]
    ]
    window = {
        "WATCH": "dikkat (size değişmez)",
        "CAUTION": "size ×0.5",
        "NO_POSITION_INCREASE": "yeni pozisyon durdu",
    }[level]
    reason = (
        f"Catalyst riski ({level}): «{lead.event_type}» "
        f"yarı-ömür ≈ {lead.expected_half_life_minutes}dk — {window}."
    )
    return CatalystVerdict(
        level=level,
        size_factor=_LEVEL_SIZE_FACTOR[level],
        block=(level == "NO_POSITION_INCREASE"),
        reason=reason,
        evidence=evidence,
        event_type=lead.event_type,
    )
