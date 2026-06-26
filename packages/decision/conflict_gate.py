"""Conflict Gate — eski decide_matrix önerisini yeni Conflict Resolver'ın
verdict'i ile birleştirir. Saf fonksiyon, I/O yok. Varsayılan: enabled=false
(inert) — owner ayrı onay verene kadar mevcut paper-açma davranışı değişmez.

`conflict_resolver_activation.py`'dan FARKLI bir köprü: o yeni sistemin
CANDIDATE_OPEN dediği YENİ girişleri manual_ready'e ekler (eski sistem hiç
önermemiş olsa bile). Bu modül ise ESKİ sistemin zaten önerdiği açılışı,
trade_profile bazlı kademeli sıkılıkla süzer/küçültür/bloklar — iki köprü
birbirini eski sistemi bozmadan tamamlar.

Trade profile bazlı kademeli sıkılık (owner onaylı tasarım):
  SCALP       OFF         — Conflict Resolver'a bakılmaz, eski sistem tek başına açar.
  INTRADAY    SOFT        — NO_TRADE/BLOCKED ise size %50; WATCH/CANDIDATE_OPEN normal.
  TACTICAL    SOFT_PLUS   — BLOCKED ise açılmaz; NO_TRADE ise size %50; WATCH/CANDIDATE_OPEN normal.
  SWING       HARD        — sadece CANDIDATE_OPEN açılır.
  POSITION    HARD_MANUAL — CANDIDATE_OPEN bile olsa otomatik açılmaz, manual_ready'e gider.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from packages.data.registry.loader import load_thresholds
from packages.decision import conflict_resolver

_DEFAULT_PROFILE_MODES: dict[str, str] = {
    "SCALP": "OFF",
    "INTRADAY": "SOFT",
    "TACTICAL": "SOFT_PLUS",
    "SWING": "HARD",
    "POSITION": "HARD_MANUAL",
}
_SOFT_REDUCE_FACTOR = 0.5
_VALID_MODES = {"OFF", "SOFT", "SOFT_PLUS", "HARD", "HARD_MANUAL"}


@dataclass(frozen=True)
class ConflictGateConfig:
    enabled: bool = False
    profile_modes: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_PROFILE_MODES))


def load_config() -> ConflictGateConfig:
    c = load_thresholds().get("conflict_gate") or {}
    modes = dict(_DEFAULT_PROFILE_MODES)
    modes.update({k: v for k, v in (c.get("profile_modes") or {}).items() if v in _VALID_MODES})
    return ConflictGateConfig(enabled=bool(c.get("enabled", False)), profile_modes=modes)


@dataclass(frozen=True)
class GateResult:
    route: str  # "open" | "manual_ready" | "block" — bkz. packages/paper/session_gate.py
    effective_multiplier: float  # ≤ 1.0 — eski sistemin size_multiplier'ına çarpılır


_INERT = GateResult(route="open", effective_multiplier=1.0)


def evaluate(
    *,
    trade_profile: str | None,
    conflict_final_action: str | None,
    cfg: ConflictGateConfig | None = None,
) -> GateResult:
    """Eski sistemin (action, size) önerisini yeni Conflict Resolver'ın verdict'iyle süzer.

    Fail-open: `cfg.enabled` false, `trade_profile` None, veya profil bilinmiyorsa
    her zaman `_INERT` döner — eski sistemin davranışı değişmez.
    """
    cfg = cfg or load_config()
    if not cfg.enabled or not trade_profile:
        return _INERT

    mode = cfg.profile_modes.get(trade_profile, "OFF")
    verdict = conflict_final_action or conflict_resolver.NO_TRADE

    if mode == "OFF":
        return _INERT

    if mode == "SOFT":
        if verdict in (conflict_resolver.NO_TRADE, conflict_resolver.BLOCKED):
            return GateResult(route="open", effective_multiplier=_SOFT_REDUCE_FACTOR)
        return _INERT

    if mode == "SOFT_PLUS":
        if verdict == conflict_resolver.BLOCKED:
            return GateResult(route="block", effective_multiplier=0.0)
        if verdict == conflict_resolver.NO_TRADE:
            return GateResult(route="open", effective_multiplier=_SOFT_REDUCE_FACTOR)
        return _INERT

    if mode == "HARD":
        if verdict == conflict_resolver.CANDIDATE_OPEN:
            return _INERT
        return GateResult(route="block", effective_multiplier=0.0)

    if mode == "HARD_MANUAL":
        if verdict == conflict_resolver.CANDIDATE_OPEN:
            return GateResult(route="manual_ready", effective_multiplier=1.0)
        return GateResult(route="block", effective_multiplier=0.0)

    return _INERT  # bilinmeyen mode — fail-open


__all__ = ["ConflictGateConfig", "GateResult", "evaluate", "load_config"]
