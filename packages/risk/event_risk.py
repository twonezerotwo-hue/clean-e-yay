"""Olay riski (event risk) — yalnızca KISITLAYICI takvim-olay gate'i (P0).

Yaklaşan, doğrulanmış (verified) yüksek etkili takvim olayları (CPI, FOMC,
NFP, Jackson Hole, …) yeni pozisyon açılışını kısar. Bu modül:

- ASLA size artırmaz.
- ASLA RiskGate / DQS / KillSwitch / halt gate'lerini gevşetmez.
- RiskEngine'e **ek kısıtlayıcı candidate** olarak girer (`risk_candidates`);
  RiskEngine max-priority seçtiği için DQS KILL_SWITCH / halt her zaman event
  riskini ezer — bypass yok.
- Yalnızca `verified=True` olayları sayar (fixture/test event'leri = verified
  False → karar zincirine girmez, sadece bağlam).

Üretebildiği seviyeler (yalnızca kısıtlayıcı taksonomi):
  NONE                 → etki yok
  WATCH                → uyarı (yeni pozisyonu bloklamaz; "CAUTION" karşılığı)
  NO_POSITION_INCREASE → yeni pozisyon açılışı durur

PAPER_SAFE / NO_EXECUTION — yalnızca gözlem + kısıtlama.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from packages.data.registry.loader import load_thresholds
from packages.data.types import Catalyst, utcnow
from packages.risk.engine import RiskAction

EventRiskLevel = Literal["NONE", "WATCH", "NO_POSITION_INCREASE"]

# Event riski yalnızca bu iki RiskAction'ı üretebilir (kısıtlayıcı taksonomi).
_LEVEL_TO_ACTION: dict[EventRiskLevel, RiskAction | None] = {
    "NONE": None,
    "WATCH": "WATCH",
    "NO_POSITION_INCREASE": "NO_POSITION_INCREASE",
}


@dataclass
class EventTrigger:
    id: str
    title: str
    importance: str
    hours_until: float
    days_until: int | None
    level: EventRiskLevel  # bu olayın tek başına ürettiği seviye


@dataclass
class EventRiskResult:
    level: EventRiskLevel = "NONE"
    action: RiskAction | None = None
    reason: str = "Yaklaşan yüksek etkili doğrulanmış olay yok."
    evidence: list[str] = field(default_factory=list)
    triggers: list[EventTrigger] = field(default_factory=list)

    @property
    def restrictive(self) -> bool:
        """Yeni pozisyon açılışını fiilen bloklar mı?"""
        return self.action == "NO_POSITION_INCREASE"


def _config() -> dict:
    cfg = load_thresholds().get("event_risk") or {}
    high = {str(x).lower() for x in (cfg.get("high_importance") or ["high", "critical"])}
    return {
        "block_window_hours": float(cfg.get("block_window_hours", 24)),
        "watch_window_hours": float(cfg.get("watch_window_hours", 72)),
        "high_importance": high,
    }


def _event_level(
    cat: Catalyst,
    *,
    block_h: float,
    watch_h: float,
    high_imp: set[str],
) -> EventRiskLevel:
    """Tek olayın ürettiği kısıtlama seviyesi.

    - Yüksek etkili (high/critical) + block penceresi içinde → NO_POSITION_INCREASE
    - Yüksek etkili + watch penceresi içinde                 → WATCH
    - Orta etkili (medium) + block penceresi içinde          → WATCH
    - aksi                                                   → NONE
    """
    h = cat.hours_until
    if h is None or h < 0:
        return "NONE"
    imp = str(cat.importance).lower()
    if imp in high_imp:
        if h <= block_h:
            return "NO_POSITION_INCREASE"
        if h <= watch_h:
            return "WATCH"
        return "NONE"
    if imp == "medium" and h <= block_h:
        return "WATCH"
    return "NONE"


_LEVEL_RANK: dict[EventRiskLevel, int] = {
    "NONE": 0,
    "WATCH": 1,
    "NO_POSITION_INCREASE": 2,
}


def assess(
    catalysts: list[Catalyst],
    *,
    now: datetime | None = None,
) -> EventRiskResult:
    """Yaklaşan olaylardan toplam event riski.

    Yalnızca `verified=True` olaylar sayılır. Sonuç en kısıtlayıcı tetikleyiciyi
    yansıtır; tüm tetikleyiciler `triggers`'ta görünür (dashboard için).
    """
    cfg = _config()
    ref = now or utcnow()

    triggers: list[EventTrigger] = []
    for cat in catalysts:
        if not cat.verified:
            continue
        # hours_until snapshot anına göre üretilir; `now` farklıysa yeniden hesapla.
        hours_until = cat.hours_until
        if now is not None and cat.ts is not None:
            hours_until = round((cat.ts - ref).total_seconds() / 3600, 1)
        cat_eff = cat.model_copy(update={"hours_until": hours_until})
        lvl = _event_level(
            cat_eff,
            block_h=cfg["block_window_hours"],
            watch_h=cfg["watch_window_hours"],
            high_imp=cfg["high_importance"],
        )
        if lvl == "NONE":
            continue
        triggers.append(
            EventTrigger(
                id=cat.id,
                title=cat.title,
                importance=str(cat.importance),
                hours_until=hours_until if hours_until is not None else -1.0,
                days_until=cat.days_until,
                level=lvl,
            )
        )

    if not triggers:
        return EventRiskResult()

    triggers.sort(key=lambda t: (-_LEVEL_RANK[t.level], t.hours_until))
    top = max(_LEVEL_RANK[t.level] for t in triggers)
    level: EventRiskLevel = next(k for k, v in _LEVEL_RANK.items() if v == top)
    action = _LEVEL_TO_ACTION[level]

    lead = triggers[0]
    window = "yeni pozisyon açılışı durdu" if level == "NO_POSITION_INCREASE" else "dikkat"
    reason = (
        f"Olay riski ({level}): «{lead.title}» {lead.hours_until:.0f}sa içinde "
        f"({lead.importance}) — {window}."
    )
    evidence = [
        f"{t.title} · {t.importance} · ~{t.hours_until:.0f}sa → {t.level}"
        for t in triggers[:5]
    ]
    return EventRiskResult(
        level=level,
        action=action,
        reason=reason,
        evidence=evidence,
        triggers=triggers,
    )


def risk_candidates(
    catalysts: list[Catalyst],
    *,
    now: datetime | None = None,
) -> list[tuple[RiskAction, str, list[str]]]:
    """RiskEngine.evaluate'e verilecek ek kısıtlayıcı candidate listesi.

    Boş liste → event riski yok. En fazla bir candidate üretir (en kısıtlayıcı
    seviye). Action her zaman WATCH veya NO_POSITION_INCREASE — yani gevşetici
    olamaz; RiskEngine max-priority seçtiği için DQS/halt'ı asla ezemez.
    """
    res = assess(catalysts, now=now)
    if res.action is None:
        return []
    return [(res.action, res.reason, list(res.evidence))]
