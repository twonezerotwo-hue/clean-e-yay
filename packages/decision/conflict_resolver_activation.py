"""Faz 7 — Conflict Resolver'ın kontrollü aktivasyonu (INERT by default).

`shadow_activation.py` ile AYNI güvenlik deseni, ama TAMAMEN BAĞIMSIZ bir
config flag'iyle (`conflict_resolver_activation.enabled`) — eski
`shadow.affect_decision` mekanizmasıyla hiç karışmaz, ikisi birbirini
etkilemez. Owner `conflict_resolver_activation.enabled` true yapana kadar
bu modülün `activate()` çağrısı her zaman no-op'tur (boş liste döner).

Hard invariant'lar (shadow_activation.py'dan birebir):
  * RiskGate FINAL otoritedir — `manual_queue.approve()` onay anında RiskGate'i
    YENİDEN çalıştırır; kuyruğa girmiş olmak hiçbir şeyi önceden onaylamaz.
  * Bu modül ASLA otomatik açmaz — sadece `manual_ready` kuyruğuna ekler.
  * Size her zaman ≤ 1.0 clamp'li (zaten RiskGate-capped decision'dan alınır,
    asla büyütülmez).
  * Sadece Conflict Resolver'ın `CANDIDATE_OPEN` dediği semboller kuyruğa girer
    (BLOCKED/NO_TRADE/WATCH asla kuyruğa girmez).

PAPER_SAFE / NO_EXECUTION: owner onayı için kuyruğa ekler; hiçbir şey açmaz.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from packages.data.registry.loader import load_thresholds
from packages.decision import agent_pipeline, conflict_resolver, shadow
from packages.paper import manual_queue
from packages.paper.state import PaperState


@dataclass(frozen=True)
class ConflictActivationConfig:
    """`conflict_resolver_activation:` config bloğu — varsayılan: tamamen kapalı."""

    enabled: bool = False


def load_config() -> ConflictActivationConfig:
    c = load_thresholds().get("conflict_resolver_activation") or {}
    return ConflictActivationConfig(enabled=bool(c.get("enabled", False)))


def activate(
    state: PaperState,
    symbols: list[str],
    *,
    risk_action: str | None,
    dqs_status: str,
    prices: dict[str, float],
    snapshot_id: str | None,
    cfg: ConflictActivationConfig | None = None,
    build_views: Callable[..., Sequence[Any]] | None = None,
    evaluate_fn: Callable[..., dict] | None = None,
) -> list[dict]:
    """Conflict Resolver'ın CANDIDATE_OPEN dediği sembolleri manual_ready'e kuyrukla.

    Guarded no-op: `cfg.enabled` false ise (varsayılan) hiçbir şey yapmaz. Owner her
    manual_ready girdisini onayladığında RiskGate yeniden çalışır (manual_queue.approve).
    `evaluate_fn` testler için enjekte edilebilir (varsayılan `shadow.evaluate_symbol`).
    """
    cfg = cfg or load_config()
    if not cfg.enabled:
        return []  # tek aktivasyon kapısı — varsayılan kapalı

    builder = build_views or agent_pipeline.build_agent_matrix
    evaluator = evaluate_fn or shadow.evaluate_symbol
    try:
        views = builder(symbols, risk_action=risk_action)
    except TypeError:
        views = builder(symbols, risk_action=risk_action)

    queued: list[dict] = []
    for v in views:
        symbol = getattr(v, "symbol", None)
        if not symbol:
            continue
        result = evaluator(
            v, fingerprint=None, risk_action=risk_action, dqs_status=dqs_status
        )
        if result.get("conflict_final_action") != conflict_resolver.CANDIDATE_OPEN:
            continue

        decision = getattr(v, "decision", None)
        entry_tf = getattr(decision, "entry_timeframe", None)
        direction = result.get("setup_direction")
        side = "long" if direction == "LONG" else "short" if direction == "SHORT" else None
        if entry_tf is None or side is None:
            continue
        # Upper TF only scales DOWN — never above the pipeline's RiskGate-capped size.
        size_mult = min(1.0, float(getattr(decision, "size_multiplier", 0.0) or 0.0))
        if size_mult <= 0.0:
            continue

        entry = manual_queue.route_to_manual_ready(
            state,
            symbol=symbol,
            timeframe=entry_tf,
            side=side,
            size_multiplier=size_mult,
            requested_price=prices.get(symbol),
            reason=f"conflict_resolver_activation:{result.get('setup_type')}",
            snapshot_id=snapshot_id,
        )
        if entry is not None:
            queued.append(
                {
                    "symbol": entry.symbol,
                    "timeframe": entry.timeframe,
                    "side": entry.side,
                    "size_multiplier": entry.size_multiplier,
                    "manual_ready_id": entry.id,
                    "setup_type": result.get("setup_type"),
                }
            )
    return queued


__all__ = ["ConflictActivationConfig", "activate", "load_config"]
