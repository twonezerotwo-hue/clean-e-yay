"""Step 9 Phase B — controlled activation of the shadow pipeline (INERT by default).

When the owner flips `shadow.affect_decision` to true (config), the NEW agent pipeline's
entry decisions are routed to the manual_ready queue ONLY — never auto-opened. Hard
invariants, all preserved from the observation phase:

  * RiskGate stays the FINAL authority — it is re-evaluated at owner approval time
    (`manual_queue.approve` re-runs the gate), so a queued entry can still be blocked.
  * The shadow NEVER auto-opens: this module only queues to the manual_ready review
    queue; it reaches no auto-open or auto-flatten paper entry point.
  * Upper TF only SCALES DOWN — the queued `size_multiplier` is clamped to ≤ 1.0 and
    is taken from the pipeline's already-RiskGate-capped decision (never boosted).
  * 1w never produces an entry (the pipeline never assigns it an entry timeframe).

`affects_paper(cfg)` (enabled AND affect_decision) is the single activation gate; it is
double-checked here so `activate()` is a guarded no-op under the shipped
`affect_decision:false` config. This module is the ONLY shadow-side code permitted to
touch paper, and only to QUEUE for owner approval.

PAPER_SAFE / NO_EXECUTION: queues a paper candidate for owner approval; opens nothing.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from packages.decision import agent_pipeline, shadow
from packages.paper import manual_queue
from packages.paper.state import PaperState

# AgentDecision actions that represent a NEW entry intent (mirror shadow observe).
ENTRY_ACTIONS = ("SCOUT_ALLOWED", "CONFIRMATION_REQUIRED")


def _side(view: Any) -> str | None:
    """Entry side from the composed consensus (>50 bullish → long, <50 → short)."""
    score = getattr(getattr(view, "consensus", None), "direction_score", None)
    if score is None:
        return None
    if score > 50:
        return "long"
    if score < 50:
        return "short"
    return None


def activate(
    state: PaperState,
    symbols: list[str],
    *,
    risk_action: str | None,
    prices: dict[str, float],
    snapshot_id: str | None,
    cfg: shadow.ShadowConfig | None = None,
    tf_weights: dict[str, float] | None = None,
    build_views: Callable[..., Sequence[Any]] | None = None,
) -> list[dict]:
    """Route the shadow pipeline's entry decisions to manual_ready ONLY.

    Guarded no-op unless `shadow.affects_paper(cfg)` (enabled AND affect_decision). It
    never opens or sizes a position; the owner approves each manual_ready entry, at
    which point the canonical RiskGate is re-run. Returns the queued entries (entries
    already present for a (symbol, side, timeframe) are silently de-duplicated).
    """
    cfg = cfg or shadow.load_config()
    if not shadow.affects_paper(cfg):
        return []  # double-gated: observe-only unless explicitly activated
    builder = build_views or agent_pipeline.build_agent_matrix
    try:
        views = builder(symbols, risk_action=risk_action, tf_weights=tf_weights)
    except TypeError:
        # test stubs may not accept tf_weights — keep the activate path resilient
        views = builder(symbols, risk_action=risk_action)
    queued: list[dict] = []
    for v in views:
        decision = getattr(v, "decision", None)
        action = getattr(decision, "action", None)
        if action not in ENTRY_ACTIONS:
            continue
        entry_tf = getattr(decision, "entry_timeframe", None)
        side = _side(v)
        if entry_tf is None or side is None:
            continue
        # Upper TF only scales DOWN — never above the pipeline's RiskGate-capped size.
        size_mult = min(1.0, float(getattr(decision, "size_multiplier", 0.0) or 0.0))
        if size_mult <= 0.0:
            continue
        symbol = getattr(v, "symbol", "")
        entry = manual_queue.route_to_manual_ready(
            state,
            symbol=symbol,
            timeframe=entry_tf,
            side=side,
            size_multiplier=size_mult,
            requested_price=prices.get(symbol),
            reason=f"shadow_activation:{action}",
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
                    "action": action,
                }
            )
    return queued
