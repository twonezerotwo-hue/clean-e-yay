"""AgentDecision (T2) — deterministic action from cross-TF consensus + RiskGate.

Bridges consensus EVIDENCE into one high-level action with an entry timeframe. It
does NOT open trades (the paper open / sizing is the matrix + RiskGate's job) and
NEVER bypasses the RiskGate (`risk_gate_required` is always true). Hard invariants:

  * RiskGate is final and TF-agnostic — KILL_SWITCH / RISK_REDUCE /
    NO_POSITION_INCREASE dominate any bullish technical read.
  * Upper TF only SCALES DOWN: size_multiplier ≤ 1.0 and is never boosted by
    agreement/alignment; countertrend applies an extra reduction cap.
  * 1w yields bias/filter only — it never produces an entry timeframe.
  * Countertrend is never an automatic full entry (SCOUT_ALLOWED /
    CONFIRMATION_REQUIRED + manual_ready_required).
  * Insufficient / degraded consensus → NO_TRADE / WATCH, never a fabricated entry.
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.data.registry.loader import load_thresholds
from packages.data.types import AgentDecision, ConsensusSnapshot, Timeframe

_KEY_TO_TF: dict[str, Timeframe] = {"m15": "15m", "h1": "1h", "h4": "4h", "d1": "1d", "w1": "1w"}
_TF_RANK: dict[Timeframe, int] = {"15m": 0, "1h": 1, "4h": 2, "1d": 3, "1w": 4}
_RESTRICTIVE = {"KILL_SWITCH", "RISK_REDUCE", "NO_POSITION_INCREASE"}


@dataclass(frozen=True)
class DecisionConfig:
    strength_min: float = 40.0
    scout_alignment_min: float = 60.0
    countertrend_size_cap: float = 0.5


def load_config() -> DecisionConfig:
    d = load_thresholds().get("decision", {}) or {}
    return DecisionConfig(
        strength_min=float(d.get("strength_min", 40)),
        scout_alignment_min=float(d.get("scout_alignment_min", 60)),
        countertrend_size_cap=float(d.get("countertrend_size_cap", 0.5)),
    )


def _tf_risk() -> dict[Timeframe, dict]:
    return load_thresholds().get("timeframe_risk", {}) or {}


def _executable_tfs(tf_risk: dict[Timeframe, dict]) -> set[Timeframe]:
    """TFs that may produce an entry (paper_execution=true) — excludes 1w."""
    return {
        tf  # type: ignore[misc]
        for tf, pol in tf_risk.items()
        if (pol or {}).get("paper_execution", False)
    }


def _entry_base_multiplier(tf: Timeframe, tf_risk: dict[Timeframe, dict]) -> float:
    pol = tf_risk.get(tf, {}) or {}
    return min(1.0, float(pol.get("risk_multiplier", 1.0)))  # never > 1.0


def _entry_timeframe(
    consensus: ConsensusSnapshot, executable: set[Timeframe]
) -> tuple[Timeframe | None, str | None]:
    """Lowest executable TF whose bias matches the consensus lean. 1w excluded."""
    if consensus.direction_score is None:
        return None, None
    if consensus.direction_score > 50:
        lean = "BULLISH"
    elif consensus.direction_score < 50:
        lean = "BEARISH"
    else:
        return None, "NEUTRAL"
    cands = [
        tf
        for key, bias in consensus.per_timeframe_bias.items()
        if (tf := _KEY_TO_TF.get(key)) in executable and bias == lean
    ]
    if not cands:
        return None, lean
    return min(cands, key=lambda t: _TF_RANK[t]), lean


def decide(
    asset: str,
    consensus: ConsensusSnapshot,
    *,
    risk_action: str | None = None,
    config: DecisionConfig | None = None,
) -> AgentDecision:
    """Deterministic high-level decision. RiskGate action (if any) is applied first."""
    cfg = config or load_config()
    tf_risk = _tf_risk()
    executable = _executable_tfs(tf_risk)

    # ── RiskGate first (final, TF-agnostic) ───────────────────────────────────
    if risk_action == "KILL_SWITCH":
        return AgentDecision(
            asset=asset, action="KILL_SWITCH", size_multiplier=0.0,
            reason="risk_gate: KILL_SWITCH", blocking_agents=["risk:KILL_SWITCH"],
        )
    if risk_action == "RISK_REDUCE":
        return AgentDecision(
            asset=asset, action="RISK_REDUCE", size_multiplier=0.0,
            reason="risk_gate: RISK_REDUCE", blocking_agents=["risk:RISK_REDUCE"],
        )
    if risk_action == "NO_POSITION_INCREASE":
        return AgentDecision(
            asset=asset, action="NO_TRADE", size_multiplier=0.0,
            reason="risk_gate: NO_POSITION_INCREASE", blocking_agents=["risk:NO_POSITION_INCREASE"],
        )

    # ── Insufficient evidence → NO_TRADE (never a fake entry) ─────────────────
    if consensus.direction_score is None:
        return AgentDecision(
            asset=asset, action="NO_TRADE", size_multiplier=0.0,
            reason="insufficient consensus (no valid timeframe)",
            blocking_agents=["technical:insufficient_data"],
        )

    entry_tf, lean = _entry_timeframe(consensus, executable)
    confidence = round((consensus.alignment_score / 100.0) * (consensus.agreement_score / 100.0), 3)

    # No executable entry TF (e.g. only 1w directional, or NEUTRAL lean) → WATCH/NO_TRADE.
    if entry_tf is None:
        action = "NO_TRADE" if lean == "NEUTRAL" else "WATCH"
        reason = (
            "neutral consensus — no directional entry"
            if lean == "NEUTRAL"
            else "directional bias only on non-executable TF (e.g. 1w) — bias/filter only"
        )
        return AgentDecision(
            asset=asset, action=action, entry_timeframe=None, size_multiplier=0.0,
            confidence=confidence, reason=reason, supporting_agents=["technical"],
        )

    base = _entry_base_multiplier(entry_tf, tf_risk)

    # ── Conflicted → WATCH ────────────────────────────────────────────────────
    if consensus.alignment_status == "CONFLICTED":
        return AgentDecision(
            asset=asset, action="WATCH", entry_timeframe=entry_tf, size_multiplier=0.0,
            confidence=confidence, reason="conflicting timeframes — wait",
            supporting_agents=["technical"], blocking_agents=["technical:conflicted"],
        )

    # ── Countertrend → never auto full entry; extra size cap; manual-ready ────
    if consensus.is_countertrend:
        action = "SCOUT_ALLOWED" if consensus.confirmed_count > 0 else "CONFIRMATION_REQUIRED"
        size = round(base * cfg.countertrend_size_cap, 4)  # only reduces
        req = [] if consensus.confirmed_count > 0 else [f"trigger_confirmation:{entry_tf}"]
        return AgentDecision(
            asset=asset, action=action, entry_timeframe=entry_tf, size_multiplier=size,
            confidence=confidence, reason="countertrend setup — reduced, manual-ready",
            supporting_agents=["technical"], required_confirmations=req,
            manual_ready_required=True,
        )

    # ── Trend-aligned ─────────────────────────────────────────────────────────
    strength = consensus.strength_score or 0.0
    aligned_strong = (
        consensus.alignment_status == "ALIGNED"
        and consensus.alignment_score >= cfg.scout_alignment_min
        and strength >= cfg.strength_min
        and consensus.confirmed_count > 0
    )
    if aligned_strong:
        return AgentDecision(
            asset=asset, action="SCOUT_ALLOWED", entry_timeframe=entry_tf,
            size_multiplier=round(base, 4),  # NO boost — base TF cap only
            confidence=confidence, reason="aligned + confirmed — scout entry (RiskGate sizes)",
            supporting_agents=["technical"],
        )

    # Aligned/partial but pending trigger or weak strength → confirmation first.
    req = [f"trigger_confirmation:{entry_tf}"]
    if strength < cfg.strength_min:
        req.append("strength_below_min")
    return AgentDecision(
        asset=asset, action="CONFIRMATION_REQUIRED", entry_timeframe=entry_tf,
        size_multiplier=round(base, 4),  # prospective cap; RiskGate is final
        confidence=confidence, reason="directional but unconfirmed — needs trigger",
        supporting_agents=["technical"], required_confirmations=req,
    )
