"""Decision Gates — tick_worker'ın per-decision rotalama mantığını TEK saf
fonksiyona çıkarır. Davranış değişmez (apply_gates'ten önceki inline kod ile
birebir aynı sıralama/öncelik) — yalnızca okunabilirlik/test edilebilirlik
için ayrıştırılmıştır.

Sıra (öncelik): session_gate (block > manual_ready > open ile size kısıtla) →
conflict_gate (Faz 8, block > manual_ready > open ile size kısıtla). İlk
"block" diyen kazanır; ikisi de "open" derse çarpanlar birlikte uygulanır;
biri "manual_ready" derse o rotaya gidilir (reason kaynağa göre seçilir).

`packages/paper/session_gate.py` ile `packages/decision/conflict_gate.py`'ın
TEK birleşme noktası budur — `attempt_open()` (tick_worker/main.py) hâlâ
sistemdeki TEK gerçek paper-açma çağrısıdır, bu modül ona giden girdiyi
hazırlar, kendisi hiçbir state mutate etmez.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from packages.decision import conflict_gate
from packages.mode import profile_selector
from packages.paper import session_gate


@dataclass(frozen=True)
class GateDecision:
    route: str  # "open" | "manual_ready" | "block"
    effective_multiplier: float
    reason: str | None = None  # manual_ready için; "open"/"block" için anlamsız
    session_attribution: dict = field(default_factory=dict)  # attempt_open(**...) için


_BLOCK = GateDecision(route="block", effective_multiplier=0.0)


def apply_gates(
    d: Any,
    *,
    side: str,
    now: datetime,
    regime: Any,
    gate_cfg: conflict_gate.ConflictGateConfig,
    conflict_by_symbol: dict[str, dict],
) -> GateDecision:
    """Bir (symbol, timeframe) kararı için session_gate + Conflict Gate'i sırayla
    uygular ve tek bir rotalama kararı döner. `gate_cfg.enabled=False` ise
    Conflict Gate her zaman inert'tir (fail-open) — eski davranış değişmez."""
    gate = session_gate.evaluate_open(
        d.symbol, side, d.timeframe, now_utc=now, regime=regime, risk_action=d.risk.action,
    )
    if gate.route == "block":
        return _BLOCK

    cr_result = conflict_by_symbol.get(d.symbol) or {}
    cr_profile = profile_selector.select_profile(cr_result.get("setup_type") or "NO_TRADE", d.timeframe)
    cgate = conflict_gate.evaluate(
        trade_profile=cr_profile,
        conflict_final_action=cr_result.get("conflict_final_action"),
        cfg=gate_cfg,
    )
    if cgate.route == "block":
        return _BLOCK

    combined_mult = gate.effective_multiplier * cgate.effective_multiplier
    if gate.route == "manual_ready" or cgate.route == "manual_ready":
        reason = gate.reason_code if gate.route == "manual_ready" else f"conflict_gate:{cr_profile}"
        return GateDecision(
            route="manual_ready",
            effective_multiplier=combined_mult,
            reason=reason,
            session_attribution=gate.attribution(),
        )

    return GateDecision(
        route="open",
        effective_multiplier=combined_mult,
        session_attribution=gate.attribution(),
    )


__all__ = ["GateDecision", "apply_gates"]
